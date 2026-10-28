"""One retained-preference TRAIN update followed by gated prospective evaluation."""

import argparse
import json
import subprocess
import time
from pathlib import Path

import run_red_closed_loop_status as loop

from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_status_retention_fit import fit_retaining_negatives
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel

SEEDS = (2026092201, 2026092202, 2026092203, 2026092204)
INITIAL_SHA = "fc4098a62bd910ba47860476c2be92ca05bd102c29f7ce0eb391352bcb93b0c7"


def run(args):
    lab, balanced = loop.lab, loop.balanced
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and committed source required")
    for path, digest in ((args.frozen, lab.K_SHA), (args.initial, INITIAL_SHA),
                         (args.rom, lab.common.ROM_SHA256)):
        if lab.common._binding(path)["sha256"] != digest:
            raise ValueError("frozen input differs")
    frozen = TrainerPracticeThreeHeadModel.from_dict(loop.load(args.frozen))
    initial = TrainerPracticeThreeHeadModel.from_dict(loop.load(args.initial))
    continuation = None
    if args.continue_numeric is not None:
        previous = args.continue_numeric.parent
        old_result, old_fit = loop.load(previous / "result.json"), loop.load(previous / "fit.json")
        if (args.solver != "slsqp" or old_result["screen"] is not None
                or old_result["withheld"] is not None
                or old_fit["solver_result"]["message"] != "Iteration limit reached"
                or old_fit["retention_regressions"] != 0
                or lab.common._binding(args.continue_numeric) != old_fit["candidate"]):
            raise ValueError("only retained pre-evaluation numeric-cap continuation permitted")
        continuation = TrainerPracticeThreeHeadModel.from_dict(loop.load(args.continue_numeric))
    old_paths = sorted(args.old.glob("*/target.json"))
    new_paths = sorted(args.new.glob("*/target.json"))
    groups = [[loop.load(p) for p in paths] for paths in (old_paths, new_paths)]
    if continuation is not None:
        old_plan = loop.load(args.continue_numeric.parent / "plan.json")
        if (old_plan["groups"] != [[lab.common._binding(p) for p in paths]
                                   for paths in (old_paths, new_paths)]
                or old_plan["initial"] != lab.common._binding(args.initial)
                or old_plan["frozen"] != lab.common._binding(args.frozen)):
            raise ValueError("numeric continuation cannot change data or retention anchor")
    if [len(g) for g in groups] != [94, 97]:
        raise ValueError("audited TRAIN inventories differ")
    sources = lab.common._source_rows(args.batch)
    if {r["source_id"] for _, r in sources} != set(frozen.train_root_ids):
        raise ValueError("TRAIN origins differ")
    cartridge = RedPracticeCartridge(args.rom.read_bytes())
    parent = loop.load(args.parent / "plan.json")
    prior = loop.load(args.old.parent / "plan.json")
    old_configs = {loop.canonical_sha256([r["practice"], r["conditions"]])
                   for r in [*parent["recipes"], *prior["holdout_recipes"]]
                   if r["role"] == "holdout"}
    held = []
    for seed in SEEDS:
        rows = [r for r in balanced.balanced_recipes(cartridge, seed=seed)
                if r["role"] == "holdout"]
        for row in rows:
            digest = loop.canonical_sha256([row["practice"], row["conditions"]])
            if digest in old_configs:
                raise ValueError("withheld configuration duplicates previous inventory")
            old_configs.add(digest)
            held.append({**row, "id": row["id"] + f"-cohort-{seed}", "cohort": seed})
    assert len(held) == 128
    if continuation is not None and held != old_plan["holdout_recipes"]:
        raise ValueError("numeric continuation cannot change evaluation inventory")
    starts = []
    for row in parent["recipes"]:
        if row["role"] != "train":
            continue
        folder = args.parent / row["id"]
        c = loop.open_battle_scenario_capture(
            folder / "capture.state", folder / "capture.state.json")
        if c.manifest.partition is not loop.ScenarioPartition.TRAIN:
            raise ValueError("screen capture not TRAIN")
        starts.append((row["id"], c))
    assert len(starts) == 64
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {
        "source_commit": commit, "initial": lab.common._binding(args.initial),
        "solver": args.solver,
        "numeric_continuation": lab.common._binding(args.continue_numeric)
        if args.continue_numeric else None,
        "frozen": lab.common._binding(args.frozen), "fits": 1,
        "epochs": 6000 if args.solver == "backtracking" else 0,
        "max_solver_iterations": (5000 if continuation else 500) if args.solver == "slsqp" else 0,
        "solver_ftol": 1e-9 if args.solver == "slsqp" else None,
        "groups": [[lab.common._binding(p) for p in paths] for paths in (old_paths, new_paths)],
        "continuations": [sorted({t["continuation_sha256"] for t in g}) for g in groups],
        "holdout_recipes": held, "max_episodes": 384, "max_minutes": 45,
        "objective": "retained-weighted-cross-entropy-v1", "learning_rate": .03,
        "soft_target_scale": 3, "cost_weight_clip": [.1, 4], "group_weight": "equal",
        "retention": "initial-correct status-worse-at-every-offset; score margin min(initial,0.05)",
        "backtracking_halvings": 12, "authority_promotions": 0, "independent_heldout_roots": 0})
    began = time.monotonic()

    def deadline():
        if time.monotonic() - began > 2700:
            raise TimeoutError("retention packet45minute limit")

    try:
        actor, fit = fit_retaining_negatives(groups, initial, frozen, solver=args.solver,
            continuation=continuation, max_solver_iterations=5000 if continuation else 500)
        lab.write(args.output / "candidate-model.json", actor.to_dict())
        lab.write(args.output / "fit.json", {**fit,
            "candidate": lab.common._binding(args.output / "candidate-model.json")})
        solved = (args.solver == "backtracking" or (
            fit["solver_result"]["success"] and
            fit["solver_result"]["minimum_constraint_slack"] >= -1e-8))
        fit_gate = (solved and fit["retention_regressions"] == 0 and
                    fit["groups"][1]["candidate"]["regret"] <= .75 *
                    fit["groups"][1]["initial"]["regret"] and
                    fit["groups"][0]["candidate"]["regret"] <=
                    fit["groups"][0]["initial"]["regret"])
        result = {"fit_gate": fit_gate, "screen": None, "withheld": None,
                  "fits": 1, "authority_promotions": 0}
        print(json.dumps({"fit": fit, "gate": fit_gate}), flush=True)
        if fit_gate:
            baseline = loop.evaluate(args, starts, frozen, args.output / "train-baseline",
                                     cartridge, status=False, deadline=deadline)
            screen = loop.evaluate(args, starts, actor, args.output / "train-screen",
                                   cartridge, status=True, deadline=deadline)
            result["screen"] = loop.gate(screen, baseline)
            print(json.dumps(result["screen"]), flush=True)
            if result["screen"]["passed"]:
                captures = [(r["id"], lab.materialize(args, r, i, sources, cartridge, commit))
                            for i, r in enumerate(held)]
                hb = loop.evaluate(args, captures, frozen, args.output / "held-baseline",
                                   cartridge, status=False, deadline=deadline)
                hc = loop.evaluate(args, captures, actor, args.output / "held-candidate",
                                   cartridge, status=True, deadline=deadline)
                result["withheld"] = loop.gate(hc, hb)
                result["cohorts"] = {str(seed): loop.gate(
                    [r for r in hc if r["case"].endswith(str(seed))],
                    [r for r in hb if r["case"].endswith(str(seed))]) for seed in SEEDS}
        lab.write(args.output / "result.json", result)
        print(json.dumps(result), flush=True)
    except Exception as error:
        lab.write(args.output / "failure.json", {"type": type(error).__name__, "error": str(error)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "batch", "parent", "old", "new", "initial", "frozen", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--solver", choices=("backtracking", "slsqp"), default="backtracking")
    parser.add_argument("--continue-numeric", type=Path)
    run(parser.parse_args())
