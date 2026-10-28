"""One prospectively frozen cost-sensitive TRAIN fit; no consumed holdout reuse."""

import argparse
import json
import subprocess
import time
from pathlib import Path

import run_red_closed_loop_status as loop

from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel

SEED = 2026092137
INITIAL_SHA = "fc4098a62bd910ba47860476c2be92ca05bd102c29f7ce0eb391352bcb93b0c7"


def run(args):
    lab, balanced = loop.lab, loop.balanced
    if args.output.exists() or subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new packet and clean committed source required")
    if (lab.common._binding(args.frozen)["sha256"] != lab.K_SHA
            or lab.common._binding(args.initial)["sha256"] != INITIAL_SHA
            or lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256):
        raise ValueError("frozen input differs")
    frozen = TrainerPracticeThreeHeadModel.from_dict(loop.load(args.frozen))
    initial = TrainerPracticeThreeHeadModel.from_dict(loop.load(args.initial))
    sources = lab.common._source_rows(args.batch)
    if {r["source_id"] for _, r in sources} != set(frozen.train_root_ids):
        raise ValueError("TRAIN ancestry differs")
    paths = sorted(args.training.glob("*/target.json"))
    targets = [loop.load(p) for p in paths]
    if len(targets) != 94 or any(t["role"] != "train" or t["root"] not in frozen.train_root_ids
            or t["return_schema"] != loop.RETURN_SCHEMA for t in targets):
        raise ValueError("only the audited94TRAIN return contexts permitted")
    if set(initial.train_capture_ids) != {
            *frozen.train_capture_ids, *(t["capture_id"] for t in targets)}:
        raise ValueError("TRAIN inventory differs from frozen initial fit")
    cartridge = RedPracticeCartridge(args.rom.read_bytes())
    holdout = [r for r in balanced.balanced_recipes(cartridge, seed=SEED)
               if r["role"] == "holdout"]
    older = loop.load(args.parent / "plan.json")["recipes"]
    prior = loop.load(args.training.parent / "plan.json")["holdout_recipes"]
    old_configs = {loop.canonical_sha256([r["practice"], r["conditions"]])
                   for r in [*older, *prior] if r["role"] == "holdout"}
    assert not old_configs & {loop.canonical_sha256([r["practice"], r["conditions"]])
                              for r in holdout}
    starts = []
    for row in older:
        if row["role"] == "train":
            folder = args.parent / row["id"]
            capture = loop.open_battle_scenario_capture(folder / "capture.state",
                                                        folder / "capture.state.json")
            if capture.manifest.partition is not loop.ScenarioPartition.TRAIN:
                raise ValueError("evaluation screen must be TRAIN")
            starts.append((row["id"], capture))
    assert len(starts) == 64
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {
        "source_commit": commit, "seed": SEED, "frozen": lab.common._binding(args.frozen),
        "initial": lab.common._binding(args.initial),
        "train_targets": [lab.common._binding(p) for p in paths],
        "holdout_recipes": holdout, "fits": 1, "epochs": 6000,
        "learning_rate": .03, "training_objective": "expected_regret", "warm_start": True,
        "minimum_relative_TRAIN_regret_reduction": .30, "max_episodes": 192,
        "max_minutes": 30, "authority_promotions": 0, "independent_heldout_roots": 0,
        "train_start_ids": [c.manifest.capture_id for _, c in starts]})
    start = time.monotonic()

    def deadline():
        if time.monotonic() - start > 1800:
            raise TimeoutError("cost-sensitive packet30minute limit")

    try:
        candidate, regret = balanced.fit_selector(
            targets, frozen, epochs=6000, seed=SEED,
            training_objective="expected_regret", initial=initial)
        initial_regret = sum(max(t["returns"]) - t["returns"][
            initial.move.predict_index(t["vectors"])] for t in targets) / len(targets)
        lab.write(args.output / "candidate-model.json", candidate.to_dict())
        lab.write(args.output / "fit.json", {**regret, "initial_regret": initial_regret,
            "examples": len(targets), "fits": 1,
            "candidate": lab.common._binding(args.output / "candidate-model.json")})
        result = {"fits": 1, "regret": regret, "initial_regret": initial_regret,
                  "screen": None, "withheld": None, "authority_promotions": 0}
        if regret["candidate_regret"] > .70 * initial_regret:
            result["stop"] = "TRAIN_fit_gate_failed"
        else:
            baseline = loop.evaluate(args, starts, frozen, args.output / "train-baseline",
                                     cartridge, status=False, deadline=deadline)
            screen = loop.evaluate(args, starts, candidate, args.output / "train-screen",
                                   cartridge, status=True, deadline=deadline)
            result["screen"] = loop.gate(screen, baseline)
            if result["screen"]["passed"]:
                held = [(r["id"], lab.materialize(args, r, i, sources, cartridge, commit))
                        for i, r in enumerate(holdout)]
                hb = loop.evaluate(args, held, frozen, args.output / "held-baseline",
                                   cartridge, status=False, deadline=deadline)
                hc = loop.evaluate(args, held, candidate, args.output / "held-candidate",
                                   cartridge, status=True, deadline=deadline)
                result["withheld"] = loop.gate(hc, hb)
        lab.write(args.output / "result.json", result)
        print(json.dumps(result), flush=True)
    except Exception as error:
        lab.write(args.output / "failure.json", {"type": type(error).__name__, "error": str(error)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "batch", "parent", "training", "frozen", "initial", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
