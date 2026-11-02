"""Evaluation-only next stage; requires independently verified TRAIN qualification."""

import argparse
import subprocess
import time
from copy import copy
from pathlib import Path

from audit_red_status_learning import audit
from audit_red_timing_selector_preparation import inspect
from run_red_timing_selector_preparation import combined

COHORTS = (2026092201, 2026092202, 2026092203, 2026092204)


def validate_recipes(recipes, candidate):
    if len(recipes) != 128 or len({r["id"] for r in recipes}) != 128:
        raise ValueError("expected128unique previously frozen comparison recipes")
    if any(r["role"] != "holdout" for r in recipes):
        raise ValueError("nonreserved recipe entered the comparison")
    for seed in COHORTS:
        if sum(r["id"].endswith(str(seed)) for r in recipes) != 32:
            raise ValueError("reserved cohort inventory differs")
    if candidate.damage_reference is None:
        raise ValueError("comparison candidate lacks its frozen damage component")


def run(args):
    # Stop before ROM access, output creation or materialization when prerequisites fail.
    readiness = inspect(args.root, args.packet)
    if not readiness["ready_to_prepare_reserved_comparison"]:
        raise ValueError("reserved comparison blocked by " + readiness["first_unpassed_gate"])
    lab, loop = combined.lab, combined.loop
    out = args.packet / "reserved-comparison"  # one exact output per qualified packet
    if out.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("one-shot reserved comparison requires new output and committed source")
    parent, _, _, _, frozen = combined.previous.load_inputs(args.root)
    recipes = parent["holdout_recipes"]
    candidate_path = args.packet / "combination/candidate-model.json"
    candidate = combined.model(candidate_path)
    validate_recipes(recipes, candidate)
    sources = lab.common._source_rows(args.root / "red-fresh-trainer-train-batch-20260917")
    if {r["source_id"] for _, r in sources} != set(frozen.train_root_ids):
        raise ValueError("comparison TRAIN ancestry differs")
    if lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256:
        raise ValueError("comparison cartridge differs")
    cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    out.mkdir(mode=0o700)
    binding = lab.common._binding(candidate_path)
    lab.write(out / "plan.json", {"schema": "pokemon.red.qualified-battler-comparison.v1",
        "source_commit": commit, "readiness": readiness, "candidate": binding,
        "frozen": parent["frozen"], "recipes": recipes, "max_episodes": 256,
        "max_frames": 30720000, "max_minutes": 90, "fits": 0,
        "cohorts": COHORTS, "independent_natural_roots": 0, "actor_promotions": 0,
        "gate": "original_aggregate_gate;per_cohort_reporting;no_live_promotion"})
    started = time.monotonic()

    def deadline():
        if time.monotonic() - started > 5400:
            raise TimeoutError("reserved comparison90minute cap")

    runtime = copy(args)
    runtime.output = out
    try:
        captures = []
        for i, recipe in enumerate(recipes):
            deadline()
            c = lab.materialize(runtime, recipe, i, sources, cartridge, commit)
            if c.manifest.capture_id in candidate.train_capture_ids:
                raise ValueError("reserved capture appears in fitting ancestry")
            captures.append((recipe["id"], c))
        baseline = loop.evaluate(runtime, captures, frozen, out / "held-baseline", cartridge,
                                 status=False, deadline=deadline)
        selected = loop.evaluate(runtime, captures, candidate, out / "held-candidate", cartridge,
                                 status=True, deadline=deadline)
        combined.verify_screen(out / "held-baseline", frozen, frozen)
        combined.verify_screen(out / "held-candidate", candidate, frozen)
        verified = audit(out)
        if (verified["episodes"] != 256 or verified["frames"] > 30720000 or
                binding != lab.common._binding(candidate_path)):
            raise ValueError("comparison count, budget or frozen model differs")
        lab.write(out / "result.json", {"gate": loop.gate(selected, baseline),
            "cohorts": {str(seed): loop.gate(
                [r for r in selected if r["case"].endswith(str(seed))],
                [r for r in baseline if r["case"].endswith(str(seed))]) for seed in COHORTS},
            "audit": verified, "fits": 0, "actor_promotions": 0,
            "natural_party_qualified": False, "live_story_ready": False})
    except Exception as exc:
        lab.write(out / "failure.json", {"type": type(exc).__name__, "error": str(exc)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "packet", "rom"):
        parser.add_argument("--"+name, type=Path, required=True)
    run(parser.parse_args())
