"""TRAIN-only RNG diversity diagnostic; no fit, evaluation or promotion."""

import argparse
import random
import subprocess
import time
from pathlib import Path
from statistics import fmean, stdev

import run_red_closed_loop_status as loop
from audit_red_status_learning import audit
from red_status_root_coverage import crossed_recipes

from pokemon_red_completion.red_status_execution_learning import eligible_target
from pokemon_red_completion.red_status_practice import condition_train_randomness
from pokemon_red_completion.red_status_win_conditioned_returns import win_conditioned_return

lab = loop.lab
SEED = 2026092281


def fork_rng(args, capture, directory, cartridge, commit, seed):
    if capture.manifest.partition is not lab.ScenarioPartition.TRAIN:
        raise ValueError("RNG forks cannot relabel evaluation captures")
    directory.mkdir(mode=0o700)
    with lab.PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        reader = lab.PokemonRedStateReader(emulator)
        encoder = lab.PokemonRedObservationEncoder(reader, True, cartridge.public_base_stats)
        raw = reader.read()
        observation = encoder.snapshot_from_raw(raw).to_dict()
        digest = lab.canonical_sha256(observation)
        if digest != capture.manifest.initial_observation_sha256:
            raise ValueError("source observation binding differs")
        frame = emulator.frame_count
        intervention = condition_train_randomness(reader, emulator._require_backend().memory,
            partition=capture.manifest.partition, seed=seed)
        if (emulator.frame_count != frame or
                encoder.snapshot_from_raw(reader.read()).to_dict() != observation):
            raise ValueError("RNG fork advanced frames or altered semantic observation")
        state = emulator.save_state_bytes()
        manifest = lab.build_battle_scenario_capture_payload(
            capture_id=f"rng-{capture.manifest.capture_id}-{seed:04x}",
            root_lineage_id=capture.manifest.root_lineage_id,
            partition=lab.ScenarioPartition.TRAIN, state_bytes=state,
            initial_observation_sha256=digest, source_commit=commit,
            expected_map=raw.map_id, expected_battle_state=2,
            source_state_sha256=capture.manifest.state_sha256,
            observation_schema=lab.OBSERVATION_SCHEMA_V2)
        lab.write(directory / "capture.state", state)
        lab.write(directory / "capture.state.json", manifest)
        lab.write(directory / "intervention.json", {**intervention,
            "parent_manifest_sha256": capture.manifest_sha256,
            "parent_state_sha256": capture.manifest.state_sha256,
            "observation_sha256": digest, "frames_advanced": 0})
    return lab.open_battle_scenario_capture(directory / "capture.state",
                                           directory / "capture.state.json")


def run(args):
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new output and committed source required")
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
               if r["source_index"] == 0 and r["contrast"] == 0
               and int(r["id"].split("-")[-2]) == 0
               and r["family"] in {"sleep", "confusion", "heal", "rest"}]
    if len(recipes) != 4:
        raise ValueError("four prospective contexts required")
    seeds = random.Random(SEED).sample(range(65536), 32)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {"seed": SEED, "recipes": recipes, "rng_seeds": seeds,
        "source_commit": commit, "frozen": lab.common._binding(frozen_path),
        "rom": lab.common._binding(args.rom), "max_episodes": 256, "max_minutes": 30,
        "max_frames": 30720000, "max_fits": 0, "teacher_continuation": "K_damage_only",
        "independent_natural_roots": 0, "actor_memory_writes": 0,
        "sources": [lab.common._binding(p / "source.state.json") for p, _ in sources]})
    started = time.monotonic()
    summaries = []
    try:
        for i, recipe in enumerate(recipes):
            capture = lab.materialize(args, recipe, i, sources, cartridge, commit)
            slots, vectors = loop.balanced.context_view(args, capture, cartridge, frozen)
            if not eligible_target({"role": "train", "vectors": vectors}):
                raise ValueError("diagnostic requires an awake binary context")
            folder = args.output / recipe["id"]
            values = {str(s): [] for s in slots}
            signatures = {str(s): set() for s in slots}
            for seed in seeds:
                if time.monotonic()-started > 1800:
                    raise TimeoutError("RNG diagnostic30minute cap")
                child = fork_rng(args, capture, folder / f"seed-{seed}", cartridge, commit, seed)
                for slot in slots:
                    episode = lab.play(args, child, frozen, folder / f"branch-{seed}-{slot}",
                                       cartridge, first_slot=slot, offset=0, horizon=40)
                    projected = loop.project_balanced_status_moves(
                        episode["decisions"][0]["observation"],
                        lab.BattleFeatureProjector(lab.PokemonRedBattleCatalog()).project(
                            episode["decisions"][0]["observation"]))
                    if vectors != [projected.candidate_vectors[projected.candidate_slots.index(s)]
                                   for s in slots]:
                        raise ValueError("RNG branch policy inputs differ")
                    values[str(slot)].append(win_conditioned_return(episode))
                    signatures[str(slot)].add(lab.canonical_sha256([
                        (d["move_slot"], d["state_after"]["party_hp"], d["opponent_hp_after"])
                        for d in episode["decisions"]]))
                if len(values[str(slots[0])]) % 8 == 0:
                    print({"family": recipe["family"], "pairs": len(values[str(slots[0])])},
                          flush=True)
            gaps = [b-a for a, b in zip(values[str(slots[0])], values[str(slots[1])], strict=True)]
            summary = {"family": recipe["family"], "slots": slots,
                "capture_id": capture.manifest.capture_id, "vectors": vectors,
                "rng_returns": values, "mean_gap_slot1_minus_slot0": fmean(gaps),
                "gap_standard_error_descriptive": stdev(gaps)/len(gaps)**.5,
                "first_half_gap": fmean(gaps[:16]), "second_half_gap": fmean(gaps[16:]),
                "distinct_trajectories": {k: len(v) for k, v in signatures.items()}}
            lab.write(folder / "diagnostic.json", summary)
            summaries.append(summary)
        native = audit(args.output)
        if native["episodes"] != 256 or native["frames"] > 30720000:
            raise ValueError("diagnostic native budget differs")
        result = {"contexts": summaries, "native": native, "seconds": time.monotonic()-started,
            "diverse_contexts": sum(any(v > 1 for v in s["distinct_trajectories"].values())
                                    for s in summaries), "fits": 0, "actor_promotions": 0}
        lab.write(args.output / "result.json", result)
        print({k: v for k, v in result.items() if k != "contexts"}, flush=True)
    except Exception as exc:
        lab.write(args.output / "failure.json", {"type": type(exc).__name__, "error": str(exc)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "rom", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    run(parser.parse_args())
