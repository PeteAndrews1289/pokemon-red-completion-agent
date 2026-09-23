"""Frozen on-policy TRAIN collection and one execution-aware regularized update."""

import argparse
import json
import subprocess
import time
from pathlib import Path

import run_red_closed_loop_status as loop
from audit_red_closed_loop_status import model, verify_screen
from audit_red_status_learning import audit
from run_red_status_trajectory_coverage import reopen_snapshot

from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_status_execution_learning import eligible_target, split_targets
from pokemon_red_completion.red_status_retention_fit import fit_retaining_negatives

ACTOR_SHA = "eb11d733a1fdab3d1ec7cfe0d72a472c682475465f7ab89ce8751fa66148aab8"
INITIAL_SHA = "fc4098a62bd910ba47860476c2be92ca05bd102c29f7ce0eb391352bcb93b0c7"
INDICES = (2, 3, 4, 5, 6, 8, 12, 19)


def run(args):
    lab, root = loop.lab, args.root
    bind = lab.common._binding
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and clean committed source required")
    parent = root / "red-balanced-status-learning-20260921-v1"
    old = root / "red-closed-loop-status-learning-20260921-v1/round-1"
    later = root / "red-status-trajectory-coverage-20260921-v1/targets"
    previous = root / "red-status-retention-fit-20260921-v3"
    frozen_path = root / "red-trainer-J-canonical-20260920-v1/candidate-model.json"
    initial_path, actor_path = old / "candidate-model.json", previous / "candidate-model.json"
    for path, expected in ((frozen_path, lab.K_SHA), (initial_path, INITIAL_SHA),
                           (actor_path, ACTOR_SHA), (args.rom, lab.common.ROM_SHA256)):
        if bind(path)["sha256"] != expected:
            raise ValueError("frozen input differs")
    frozen, initial, actor = (model(p) for p in (frozen_path, initial_path, actor_path))
    if loop.load(previous / "result.json")["withheld"] is not None:
        raise ValueError("comparison inventory must remain unopened")
    held = loop.load(previous / "plan.json")["holdout_recipes"]
    sources = lab.common._source_rows(root / "red-fresh-trainer-train-batch-20260917")
    if {r["source_id"] for _, r in sources} != set(frozen.train_root_ids):
        raise ValueError("TRAIN origins differ")
    paths = [sorted(d.glob("*/target.json")) for d in (old, later)]
    groups, eligibility = [], []
    for rows in paths:
        group, report = split_targets([loop.load(p) for p in rows])
        groups.append(group)
        eligibility.append(report)
    if [len(p) for p in paths] != [94, 97]:
        raise ValueError("previous target inventory differs")
    starts = []
    for row in loop.load(parent / "plan.json")["recipes"]:
        if row["role"] != "train":
            continue
        folder = parent / row["id"]
        c = loop.open_battle_scenario_capture(
            folder / "capture.state", folder / "capture.state.json")
        if c.manifest.partition is not loop.ScenarioPartition.TRAIN:
            raise ValueError("non-TRAIN start")
        starts.append(("execution-" + row["id"], c))
    assert len(starts) == 64 and len(held) == 128
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {
        "source_commit": commit, "actor": bind(actor_path), "initial": bind(initial_path),
        "frozen": bind(frozen_path), "rom": bind(args.rom), "decision_indices": INDICES,
        "old_groups": [[bind(p) for p in ps] for ps in paths], "eligibility": eligibility,
        "holdout_recipes": held, "offsets": loop.OFFSETS, "return_schema": loop.RETURN_SCHEMA,
        "anchor_l2": .001, "max_solver_iterations": 2000, "max_fits": 1,
        "max_episodes": 3520, "max_minutes": 90, "max_turns": 40,
        "starts": [{"name": n, "manifest_sha256": c.manifest_sha256,
                    "capture_id": c.manifest.capture_id} for n, c in starts],
        "authority_promotions": 0, "independent_heldout_roots": 0})
    cartridge, began = RedPracticeCartridge(args.rom.read_bytes()), time.monotonic()

    def deadline():
        if time.monotonic() - began > 5400:
            raise TimeoutError("execution-learning90minute limit")

    try:
        trajectories, target_dir = args.output / "trajectories", args.output / "targets"
        trajectories.mkdir()
        target_dir.mkdir()
        targets, coverage = [], []
        for name, start in starts:
            deadline()
            directory = trajectories / name
            episode = lab.play(args, start, actor, directory, cartridge, horizon=40,
                               capture_decisions=INDICES, capture_source_commit=commit)
            for index in INDICES:
                snapshot = directory / "snapshots" / f"decision-{index:03d}"
                record = {"case": name, "index": index}
                if not snapshot.exists():
                    coverage.append({**record, "status": "not_reached_or_non_main"})
                    continue
                capture, contrast = reopen_snapshot(args, snapshot, cartridge, frozen)
                if not contrast:
                    coverage.append({**record, "status": "no_contrast"})
                    continue
                _, vectors = loop.balanced.context_view(args, capture, cartridge, frozen)
                if not eligible_target({"role": "train", "vectors": vectors}):
                    coverage.append({**record, "status": "predecision_sleep"})
                    continue
                output = target_dir / f"{name}-decision-{index:03d}"
                output.mkdir()
                loop.measure(args, capture, output, cartridge, frozen, actor, deadline)
                targets.append(loop.load(output / "target.json"))
                coverage.append({**record, "status": "measured"})
            lab.write(directory / "coverage.json", {
                "case": name, "decisions": episode["decision_count"],
                "stop": episode["stop_reason"]})
            print(json.dumps({"trajectory": name, "new_contexts": len(targets)}), flush=True)
        lab.write(args.output / "coverage.json", coverage)
        # Verify native labels and logs before admitting any new target to fitting.
        target_audit = audit(target_dir, projector=loop.project_balanced_status_moves,
                             return_value=loop.closed_loop_return,
                             plan_path=args.output / "plan.json")
        lab.write(args.output / "target-audit.json", target_audit)
        group, report = split_targets(targets)
        if len(group) != len(targets) or not group:
            raise ValueError("collection admitted sleep/no targets")
        groups.append(group)
        eligibility.append(report)
        lab.write(args.output / "fit-inputs.json", {
            "groups": [[bind(p) for p in ps] for ps in
                       (*paths, sorted(target_dir.glob("*/target.json")))],
            "eligibility": eligibility,
            "continuations": [sorted({t["continuation_sha256"] for t in g}) for g in groups]})
        deadline()
        candidate, fit = fit_retaining_negatives(groups, initial, frozen, solver="slsqp",
            max_solver_iterations=2000, anchor_l2=.001)
        lab.write(args.output / "candidate-model.json", candidate.to_dict())
        lab.write(args.output / "fit.json", {**fit,
            "candidate": bind(args.output / "candidate-model.json")})
        passed = (fit["solver_result"]["success"] and
                  fit["solver_result"]["minimum_constraint_slack"] >= -1e-8 and
                  fit["retention_regressions"] == 0 and
                  fit["groups"][0]["candidate"]["regret"] <=
                  fit["groups"][0]["initial"]["regret"] and
                  sum(g["candidate"]["regret"] for g in fit["groups"][1:]) <=
                  .75 * sum(g["initial"]["regret"] for g in fit["groups"][1:]))
        result = {"fit_gate": passed, "screen": None, "withheld": None, "fits": 1,
                  "new_contexts": len(targets), "authority_promotions": 0}
        print(json.dumps({"fit": fit, "gate": passed}), flush=True)
        if passed:
            base = loop.evaluate(args, starts, frozen, args.output / "train-baseline",
                                 cartridge, status=False, deadline=deadline)
            chosen = loop.evaluate(args, starts, candidate, args.output / "train-screen",
                                   cartridge, status=True, deadline=deadline)
            verify_screen(args.output / "train-screen", candidate, frozen)
            result["screen"] = loop.gate(chosen, base)
            print(json.dumps(result["screen"]), flush=True)
            if result["screen"]["passed"]:
                captures = [(r["id"], lab.materialize(args, r, i, sources, cartridge, commit))
                            for i, r in enumerate(held)]
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
    for name in ("root", "rom", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
