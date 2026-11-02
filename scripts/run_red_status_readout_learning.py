"""Inspect a frozen hidden representation, then run one separately frozen readout fit."""

import argparse
import json
import subprocess
import time
from pathlib import Path

import run_red_closed_loop_status as loop
from audit_red_closed_loop_status import model
from audit_red_status_learning import sha
from run_red_status_execution_learning import INITIAL_SHA

from pokemon_red_completion import red_status_readout_learning as readout
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_status_execution_learning import split_targets

BASIS_SHA = "0734686a10ffa0d231ea4b7456261f53b55d6e7762a1455fb3974af9118e5951"


def load_basis(root, inputs, initial, learned):
    if not learned:
        return initial, None
    previous = root / "red-status-execution-learning-20260921-v1"
    binding = loop.lab.common._binding(previous / "candidate-model.json")
    result = loop.load(previous / "result.json")
    fit = loop.load(previous / "fit.json")
    if (binding["sha256"] != BASIS_SHA or fit["candidate"] != binding
            or result["screen"] is not None or result["withheld"] is not None):
        raise ValueError("learned basis must be the unevaluated frozen TRAIN candidate")
    if loop.load(previous / "fit-inputs.json") != inputs:
        raise ValueError("basis TRAIN inputs differ")
    closed = loop.load(root / "red-status-readout-learning-20260921-v1/result.json")
    if closed["fit_gate"] or closed["screen"] is not None or closed["withheld"] is not None:
        raise ValueError("original readout experiment must remain rejected and unevaluated")
    return model(Path(binding["path"])), binding


def load_inputs(root):
    previous = root / "red-status-execution-learning-20260921-v1"
    plan, inputs = (loop.load(previous / name) for name in ("plan.json", "fit-inputs.json"))
    binding = loop.lab.common._binding
    for key, digest in (("initial", INITIAL_SHA), ("frozen", loop.lab.K_SHA)):
        if binding(Path(plan[key]["path"])) != plan[key] or plan[key]["sha256"] != digest:
            raise ValueError("frozen model binding differs")
    initial, frozen = (model(Path(plan[k]["path"])) for k in ("initial", "frozen"))
    groups = []
    for index, bindings in enumerate(inputs["groups"]):
        raw = []
        for item in bindings:
            p = Path(item["path"])
            if binding(p) != item:
                raise ValueError("target binding differs")
            raw.append(loop.load(p))
        g, report = split_targets(raw)
        if report != inputs["eligibility"][index]:
            raise ValueError("eligible TRAIN inventory differs")
        groups.append(g)
    if [len(g) for g in groups] != [92, 94, 126]:
        raise ValueError("TRAIN group sizes differ")
    return plan, inputs, groups, initial, frozen


def run(args):
    lab, binding = loop.lab, loop.lab.common._binding
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and clean committed source required")
    parent, inputs, groups, initial, frozen = load_inputs(args.root)
    basis, basis_binding = load_basis(args.root, inputs, initial, args.learned_basis)
    retention_groups = None
    reward_binding = None
    if args.reward_view is not None:
        from build_red_status_reward_view import validate_view
        view = validate_view(args.reward_view, args.root)
        if view["inputs_sha256"] != loop.canonical_sha256(inputs):
            raise ValueError("v2 view does not bind original inputs")
        prior = loop.load(args.root / "red-status-feature-readout-learning-20260921-v1/result.json")
        if prior["screen"] is None or prior["screen"]["passed"] or prior["withheld"] is not None:
            raise ValueError("reward correction requires the closed rejected feature screen")
        retention_groups, groups = groups, view["groups"]
        reward_binding = binding(args.reward_view)
    problem = readout.prepare_readout(groups, initial, frozen, basis=basis,
                                     retention_groups=retention_groups)
    identities = {"inputs_sha256": loop.canonical_sha256(inputs),
                  "initial_sha256": parent["initial"]["sha256"],
                  "frozen_sha256": parent["frozen"]["sha256"],
                  "learner_source_sha256": sha(Path(readout.__file__))}
    if basis_binding is not None:
        identities["basis_sha256"] = basis_binding["sha256"]
    if reward_binding is not None:
        identities["reward_view_sha256"] = reward_binding["sha256"]
    anchor_slack = (float(min(problem.constraints @ problem.anchor - problem.minimum))
                    if len(problem.minimum) else 0.)
    if args.inspect:
        result = {**identities, "representation": readout.representation_check(problem),
                  "anchor_minimum_constraint_slack": anchor_slack,
                  "protected_preferences": len(problem.protected),
                  "fits": 0, "gameplay_episodes": 0}
        lab.write(args.output, result)
        print(json.dumps(result), flush=True)
        return
    if args.inspection is None or args.rom is None:
        raise ValueError("fit requires prior inspection and ROM")
    inspection = loop.load(args.inspection)
    if any(inspection.get(k) != v for k, v in identities.items()):
        raise ValueError("representation inspection does not bind these inputs/source")
    if not inspection["representation"]["individually_correctable_errors"]:
        raise ValueError("representation cannot correct measured high-cost errors")
    if basis_binding is not None and (anchor_slack < -1e-8 or len(problem.protected) != 182):
        raise ValueError("learned basis anchor does not retain the original182preferences")
    if binding(args.rom)["sha256"] != lab.common.ROM_SHA256:
        raise ValueError("cartridge differs")
    prior = loop.load(args.root / "red-status-execution-learning-20260921-v1/result.json")
    if prior["screen"] is not None or prior["withheld"] is not None:
        raise ValueError("previous correction inventory already evaluated")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {
        "source_commit": commit, **identities, "inspection": binding(args.inspection),
        **({"basis": basis_binding} if basis_binding is not None else {}),
        **({"reward_view": reward_binding} if reward_binding is not None else {}),
        "initial": parent["initial"], "frozen": parent["frozen"], "rom": binding(args.rom),
        "groups": inputs["groups"], "eligibility": inputs["eligibility"],
        "continuations": inputs["continuations"], "holdout_recipes": parent["holdout_recipes"],
        "max_fits": 1, "max_solver_iterations": 500, "solver_ftol": 1e-9,
        "anchor_l2": .001, "max_episodes": 384, "max_minutes": 45,
        "authority_promotions": 0, "independent_heldout_roots": 0})
    began = time.monotonic()

    def deadline():
        if time.monotonic() - began > 2700:
            raise TimeoutError("readout packet45minute limit")

    try:
        candidate, fit = readout.fit_readout(groups, initial, frozen, basis=basis,
                                           retention_groups=retention_groups)
        lab.write(args.output / "candidate-model.json", candidate.to_dict())
        lab.write(args.output / "fit.json", {**fit,
            "candidate": binding(args.output / "candidate-model.json")})
        passed = (fit["solver_result"]["success"] and
                  fit["solver_result"]["minimum_constraint_slack"] >= -1e-8 and
                  fit["retention_regressions"] == 0 and
                  fit["groups"][0]["candidate"]["regret"] <=
                  fit["groups"][0]["initial"]["regret"] and
                  sum(g["candidate"]["regret"] for g in fit["groups"][1:]) <=
                  .75 * sum(g["initial"]["regret"] for g in fit["groups"][1:]))
        result = {"fit_gate": passed, "screen": None, "withheld": None, "fits": 1,
                  "authority_promotions": 0}
        print(json.dumps({"fit": fit, "gate": passed}), flush=True)
        if passed:
            cartridge = RedPracticeCartridge(args.rom.read_bytes())
            starts = []
            balanced = args.root / "red-balanced-status-learning-20260921-v1"
            for r in loop.load(balanced / "plan.json")["recipes"]:
                if r["role"] != "train":
                    continue
                folder = balanced / r["id"]
                c = loop.open_battle_scenario_capture(folder / "capture.state",
                                                       folder / "capture.state.json")
                if c.manifest.partition is not loop.ScenarioPartition.TRAIN:
                    raise ValueError("screen capture not TRAIN")
                starts.append((r["id"], c))
            assert len(starts) == 64
            base = loop.evaluate(args, starts, frozen, args.output / "train-baseline",
                                 cartridge, status=False, deadline=deadline)
            chosen = loop.evaluate(args, starts, candidate, args.output / "train-screen",
                                   cartridge, status=True, deadline=deadline)
            result["screen"] = loop.gate(chosen, base)
            print(json.dumps(result["screen"]), flush=True)
            if result["screen"]["passed"]:
                sources = lab.common._source_rows(
                    args.root / "red-fresh-trainer-train-batch-20260917")
                if {r["source_id"] for _, r in sources} != set(frozen.train_root_ids):
                    raise ValueError("TRAIN roots differ")
                captures = [(r["id"], lab.materialize(args, r, i, sources, cartridge, commit))
                            for i, r in enumerate(parent["holdout_recipes"])]
                base = loop.evaluate(args, captures, frozen, args.output / "held-baseline",
                                     cartridge, status=False, deadline=deadline)
                chosen = loop.evaluate(args, captures, candidate, args.output / "held-candidate",
                                       cartridge, status=True, deadline=deadline)
                result["withheld"] = loop.gate(chosen, base)
                result["cohorts"] = {str(s): loop.gate(
                    [r for r in chosen if r["case"].endswith(str(s))],
                    [r for r in base if r["case"].endswith(str(s))]) for s in (2026092201,
                        2026092202, 2026092203, 2026092204)}
        lab.write(args.output / "result.json", result)
        print(json.dumps(result), flush=True)
    except Exception as error:
        lab.write(args.output / "failure.json", {"type": type(error).__name__, "error": str(error)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--inspection", type=Path)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--learned-basis", action="store_true")
    parser.add_argument("--reward-view", type=Path)
    run(parser.parse_args())
