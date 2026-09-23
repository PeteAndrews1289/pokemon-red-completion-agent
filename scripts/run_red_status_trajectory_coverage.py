"""Collect fixed-index native learner states and measured TRAIN contrasts; no fit."""

import argparse
import json
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path

import run_red_closed_loop_status as loop

from pokemon_red_completion.battle_scenario_capture import open_battle_scenario_capture
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_balanced_status_features import (
    BALANCED_STATUS_NAMES,
    project_balanced_status_moves,
)
from pokemon_red_completion.red_battle_practice_cartridge import RedPracticeCartridge
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES, status_choice_slots
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.scenario_lab import ScenarioPartition

INDICES = (2, 3, 5, 8)
ACTOR_SHA = "b8f3a53daf6e23b194ff34ba4a475a0cf3ea662731ad5dafdcebc460e05e369a"


def reopen_snapshot(args, folder, cartridge, frozen):
    capture = open_battle_scenario_capture(folder / "capture.state", folder / "capture.state.json")
    binding = loop.load(folder / "binding.json")
    if capture.manifest.partition is not ScenarioPartition.TRAIN:
        raise ValueError("snapshot cannot relabel an evaluation state")
    if capture.manifest.state_sha256 != binding["state_sha256"]:
        raise ValueError("snapshot bytes differ from logged boundary")
    with PyBoyAdapter(args.rom, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(capture.state_bytes)
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        legacy = PokemonRedObservationEncoder(reader, True, cartridge.public_base_stats)
        if prepare_red_battle_scenario(legacy, raw, allow_no_attack=True
                ).initial_observation_sha256 != capture.manifest.initial_observation_sha256:
            raise ValueError("snapshot legacy observation differs")
        encoder = loop.lab.replace(legacy, include_status_context=True)
        observation = encoder.snapshot_from_raw(raw).to_dict()
        if canonical_sha256(observation) != binding["policy_observation_sha256"]:
            raise ValueError("snapshot actor observation differs after restore")
        prepared = prepare_red_battle_scenario(
            encoder, raw, allow_no_attack=True, allow_status_moves=True)
        projected = project_balanced_status_moves(observation, prepared.features)
        legal = tuple(s + 1 for s, ok in zip(
            prepared.features.slot_indices, prepared.features.legal_mask, strict=True) if ok)
        slots = status_choice_slots(projected, legal, frozen.move)
    return capture, len(slots) == 2


def target_diagnostics(targets, actor):
    aliases = defaultdict(list)
    negative = positive = errors = high_cost_errors = unstable = 0
    gaps = []
    for target in targets:
        status = next(i for i, row in enumerate(target["vectors"])
                      if row[BALANCED_STATUS_NAMES.index("choice.status")])
        damage = 1 - status
        gap = target["returns"][status] - target["returns"][damage]
        negative += gap < -.05
        positive += gap > .05
        selected = actor.move.predict_index(target["vectors"])
        regret = max(target["returns"]) - target["returns"][selected]
        errors += regret > .05
        high_cost_errors += regret >= 1
        timing = target["timing_returns"]
        differences = [s - d for s, d in zip(timing[str(target["slots"][status])],
                         timing[str(target["slots"][damage])], strict=True)]
        unstable += min(differences) < -.05 and max(differences) > .05
        gaps.append(max(differences) - min(differences))
        key = tuple(target["vectors"][status][len(STATUS_MOVE_NAMES):])
        aliases[key].append((target["capture_id"], gap))
    conflicts = [rows for rows in aliases.values()
                 if min(x[1] for x in rows) < -.05 and max(x[1] for x in rows) > .05]
    return {"contexts": len(targets), "status_worse": negative, "status_better": positive,
            "frozen_actor_errors": errors, "high_cost_errors": high_cost_errors,
            "timing_sign_changes": unstable, "maximum_timing_gap_range": max(gaps, default=0.),
            "unique_compact_inputs": len(aliases), "conflicting_exact_input_groups": conflicts,
            "duplicate_input_groups": sum(len(rows) > 1 for rows in aliases.values())}


def run(args):
    lab = loop.lab
    if args.output.exists() or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=lab.ROOT).strip():
        raise ValueError("new packet and committed source required")
    for path, sha in ((args.frozen, lab.K_SHA), (args.actor, ACTOR_SHA),
                      (args.rom, lab.common.ROM_SHA256)):
        if lab.common._binding(path)["sha256"] != sha:
            raise ValueError("frozen input differs")
    frozen = TrainerPracticeThreeHeadModel.from_dict(loop.load(args.frozen))
    actor = TrainerPracticeThreeHeadModel.from_dict(loop.load(args.actor))
    if actor.train_root_ids != frozen.train_root_ids:
        raise ValueError("actor TRAIN ancestry differs")
    parent = loop.load(args.parent / "plan.json")
    if parent["seed"] != loop.balanced.SEED:
        raise ValueError("only original balanced TRAIN starts permitted")
    starts = []
    for row in parent["recipes"]:
        if row["role"] != "train":
            continue
        folder = args.parent / row["id"]
        capture = open_battle_scenario_capture(
            folder / "capture.state", folder / "capture.state.json")
        if (capture.manifest.partition is not ScenarioPartition.TRAIN
                or capture.manifest.root_lineage_id not in actor.train_root_ids
                or capture.manifest.capture_id not in actor.train_capture_ids):
            raise ValueError("non-TRAIN capture forbidden")
        starts.append((row["id"], capture))
    assert len(starts) == 64
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=lab.ROOT).decode().strip()
    args.output.mkdir(mode=0o700)
    lab.write(args.output / "plan.json", {
        "source_commit": commit, "actor": lab.common._binding(args.actor),
        "frozen": lab.common._binding(args.frozen),
        "parent": lab.common._binding(args.parent / "plan.json"),
        "decision_indices": INDICES, "offsets": loop.OFFSETS, "max_turns": 40,
        "max_episodes": 1600, "max_minutes": 45, "max_fits": 0,
        "return_schema": loop.RETURN_SCHEMA, "independent_heldout_roots": 0,
        "starts": [{"name": name, "capture_id": c.manifest.capture_id,
                    "manifest_sha256": c.manifest_sha256} for name, c in starts]})
    cartridge = RedPracticeCartridge(args.rom.read_bytes())
    started = time.monotonic()

    def deadline():
        if time.monotonic() - started > 2700:
            raise TimeoutError("trajectory packet45minute limit")

    cases, targets = [], []
    try:
        trajectories = args.output / "trajectories"
        trajectories.mkdir(mode=0o700)
        target_dir = args.output / "targets"
        target_dir.mkdir(mode=0o700)
        for name, start in starts:
            deadline()
            directory = trajectories / name
            episode = lab.play(args, start, actor, directory, cartridge, horizon=40,
                               capture_decisions=INDICES, capture_source_commit=commit)
            rows = []
            for index in INDICES:
                snapshot = directory / "snapshots" / f"decision-{index:03d}"
                if not snapshot.exists():
                    rows.append({"index": index, "status": "censored",
                                 "reason": "not_reached" if index > episode["decision_count"]
                                 else "non_main_boundary"})
                    continue
                capture, eligible = reopen_snapshot(args, snapshot, cartridge, frozen)
                if not eligible:
                    rows.append({"index": index, "status": "censored",
                                 "reason": "no_status_damage_contrast"})
                    continue
                target_output = target_dir / f"{name}-decision-{index:03d}"
                target_output.mkdir(mode=0o700)
                loop.measure(args, capture, target_output, cartridge, frozen, actor, deadline)
                target = loop.load(target_output / "target.json")
                targets.append(target)
                rows.append({"index": index, "status": "measured",
                             "capture_id": capture.manifest.capture_id})
            case = {"case": name, "stop": episode["stop_reason"],
                    "decisions": episode["decision_count"], "samples": rows}
            lab.write(directory / "coverage.json", case)
            cases.append(case)
            print(json.dumps({"case": name, "contexts": len(targets)}), flush=True)
        report = {"cases": cases, "diagnostics": target_diagnostics(targets, actor),
                  "trajectories": len(cases), "fits": 0, "authority_promotions": 0,
                  "sample_counts": dict(Counter(s["status"] for c in cases for s in c["samples"]))}
        lab.write(args.output / "result.json", report)
        print(json.dumps(report["diagnostics"]), flush=True)
    except Exception as error:
        lab.write(args.output / "failure.json", {"type": type(error).__name__, "error": str(error)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rom", "parent", "actor", "frozen", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
