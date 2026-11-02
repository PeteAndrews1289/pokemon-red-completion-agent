"""Broad TRAIN-only paired RNG data; zero fits, no campaign/evaluation access."""

import argparse
import random
import subprocess
import time
from copy import copy
from pathlib import Path
from statistics import fmean, stdev

from audit_red_status_learning import audit
from red_status_root_coverage import crossed_recipes
from run_red_randomized_training_diagnostic import fork_rng, lab, loop
from run_red_status_trajectory_coverage import reopen_snapshot

from pokemon_red_completion.red_status_execution_learning import eligible_target
from pokemon_red_completion.red_status_win_conditioned_returns import (
    RETURN_SCHEMA,
    win_conditioned_return,
)

SEED = 2026092282
SCHEMA = "pokemon.red.paired-rng-train-target.v1"


def measure(args, capture, directory, cartridge, frozen, seeds, commit, deadline):
    slots, vectors = loop.balanced.context_view(args, capture, cartridge, frozen)
    if not eligible_target({"role": "train", "vectors": vectors}):
        return None
    directory.mkdir(mode=0o700)
    values = {str(s): [] for s in slots}
    for seed in seeds:
        deadline()
        child = fork_rng(args, capture, directory / f"seed-{seed}", cartridge, commit, seed)
        for slot in slots:
            deadline()
            ep = lab.play(args, child, frozen, directory / f"branch-{seed}-{slot}", cartridge,
                          first_slot=slot, offset=0, horizon=40)
            obs = ep["decisions"][0]["observation"]
            view = loop.project_balanced_status_moves(obs,
                lab.BattleFeatureProjector(lab.PokemonRedBattleCatalog()).project(obs))
            if vectors != [view.candidate_vectors[view.candidate_slots.index(s)] for s in slots]:
                raise ValueError("paired RNG observation differs")
            values[str(slot)].append(win_conditioned_return(ep))
    gaps = [b-a for a, b in zip(*(values[str(s)] for s in slots), strict=True)]
    target = {"schema": SCHEMA, "role": "train", "root": capture.manifest.root_lineage_id,
        "capture_id": capture.manifest.capture_id, "slots": slots, "vectors": vectors,
        "rng_seeds": seeds, "rng_returns": values,
        "returns": [fmean(values[str(s)]) for s in slots],
        "return_schema": RETURN_SCHEMA, "teacher_continuation": "K_damage_only",
        "continuation_sha256": lab.canonical_sha256(frozen.to_dict()),
        "manifest_sha256": capture.manifest_sha256, "state_sha256": capture.manifest.state_sha256,
        "first_half_gap": fmean(gaps[:16]), "second_half_gap": fmean(gaps[16:]),
        "gap_standard_error_descriptive": stdev(gaps)/32**.5}
    lab.write(directory / "target.json", target)
    return target


def run(args):
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new packet and committed source required")
    diagnostic = args.root / "red-rng-training-diagnostic-20260922-v1"
    if lab.common._binding(diagnostic / "result.json")["sha256"] != (
            "5653cb34f5e47656eb88685c8deeee6be02fd86ee3fcad14de7cd01128ebe052"):
        raise ValueError("completed RNG diagnostic differs")
    checked = loop.load(diagnostic / "independent-audit.json")
    if checked["result"] != lab.common._binding(diagnostic / "result.json"):
        raise ValueError("diagnostic audit binding differs")
    frozen_path = args.root / "red-trainer-J-canonical-20260920-v1/candidate-model.json"
    if (lab.common._binding(frozen_path)["sha256"] != lab.K_SHA or
            lab.common._binding(args.rom)["sha256"] != lab.common.ROM_SHA256):
        raise ValueError("K or cartridge differs")
    frozen = lab.TrainerPracticeThreeHeadModel.from_dict(loop.load(frozen_path))
    sources = sorted(lab.common._source_rows(args.root / "red-fresh-trainer-train-batch-20260917"),
                     key=lambda p: p[1]["source_id"])
    roots = [r["source_id"] for _, r in sources]
    if set(roots) != set(frozen.train_root_ids):
        raise ValueError("TRAIN ancestry differs")
    cartridge = lab.RedPracticeCartridge(args.rom.read_bytes())
    recipes = [r for r in crossed_recipes(cartridge, roots, seed=SEED)
               if r["source_index"] in (0, 1) and
               int(r["id"].split("-")[-2]) == r["source_index"]]
    if len(recipes) != 64:
        raise ValueError("64prospective contexts required")
    seeds = random.Random(SEED).sample(range(65536), 32)
    excluded = set()
    for directory in [diagnostic, *(args.root / f"red-outcome-value-pilot-20260922-v{v}"
                                    for v in (1, 2, 3))]:
        for path in directory.glob("**/capture.state.json"):
            excluded.add(lab.open_battle_scenario_capture(path.with_suffix(""), path
                                                         ).manifest.state_sha256)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {"source_commit": commit, "seed": SEED,
        "recipes": recipes, "rng_seeds": seeds, "frozen": lab.common._binding(frozen_path),
        "rom": lab.common._binding(args.rom), "diagnostic_audit": checked,
        "sources": [lab.common._binding(p / "source.state.json") for p, _ in sources],
        "max_episodes": 8256, "max_minutes": 90, "max_frames": 990720000,
        "max_fits": 0, "capture_decisions": [2], "actor_promotions": 0,
        "excluded_state_sha256": sorted(excluded), "independent_natural_roots": 0,
        "teacher_continuation": "K_damage_only", "old_reserved_access": False})
    started = time.monotonic()

    def deadline():
        if time.monotonic()-started > 5400:
            raise TimeoutError("randomized collection90minute cap")

    runtime = copy(args)
    runtime.output = args.output / "starts"
    for name in ("starts", "targets", "trajectories"):
        (args.output / name).mkdir()
    coverage, targets = [], []
    try:
        for i, recipe in enumerate(recipes):
            deadline()
            capture = lab.materialize(runtime, recipe, i, sources, cartridge, commit)
            trajectory = args.output / "trajectories" / recipe["id"]
            if capture.manifest.state_sha256 in excluded:
                raise ValueError("start overlaps consumed capture")
            lab.play(args, capture, frozen, trajectory, cartridge, horizon=40,
                     damage_only=True, capture_decisions=(2,), capture_source_commit=commit)
            states = [("opening", capture)]
            snapshot = trajectory / "snapshots/decision-002"
            if snapshot.exists():
                child, contrast = reopen_snapshot(args, snapshot, cartridge, frozen)
                if contrast:
                    states.append(("later-002", child))
                else:
                    coverage.append({"case": recipe["id"], "kind": "later-002",
                                     "family": recipe["family"], "status": "no_contrast"})
            else:
                coverage.append({"case": recipe["id"], "kind": "later-002",
                                 "family": recipe["family"], "status": "not_reached"})
            for kind, state in states:
                if state.manifest.state_sha256 in excluded:
                    raise ValueError("measurement overlaps consumed capture")
                excluded.add(state.manifest.state_sha256)
                target = measure(args, state, args.output / "targets" / (recipe["id"]+"-"+kind),
                                 cartridge, frozen, seeds, commit, deadline)
                if target:
                    targets.append(target)
                coverage.append({"case": recipe["id"], "kind": kind, "family": recipe["family"],
                                 "status": "measured" if target else "predecision_sleep"})
            print({"trajectory": i+1, "contexts": len(targets),
                   "elapsed_seconds": round(time.monotonic()-started)}, flush=True)
        lab.write(args.output / "coverage.json", coverage)
        native = audit(args.output)  # targets are nested; separate target audit is required.
        if native["episodes"] != 64+64*len(targets) or native["frames"] > 990720000:
            raise ValueError("native inventory or budget differs")
        gate = (sum(c["kind"] == "opening" and c["status"] == "measured" for c in coverage) == 64
                and sum(c["kind"] == "later-002" and c["status"] == "measured"
                        for c in coverage) >= 16)
        result = {"targets": len(targets), "coverage_passed": gate, "native": native,
            "seconds": time.monotonic()-started, "fits": 0, "actor_promotions": 0,
            "split_half_sign_disagreements": sum(t["first_half_gap"]*t["second_half_gap"] < 0
                                                 for t in targets)}
        lab.write(args.output / "result.json", result)
        print(result, flush=True)
    except Exception as exc:
        lab.write(args.output / "failure.json", {"type": type(exc).__name__, "error": str(exc)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "rom", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    run(parser.parse_args())
