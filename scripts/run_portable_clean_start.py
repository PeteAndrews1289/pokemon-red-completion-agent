#!/usr/bin/env python3
"""Run one explicitly uncounted portable clean-start learned-stack rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.battle_control_model import load_battle_control_model_artifact
from pokemon_red_completion.clean_start_campaign import derive_initial_wait_frames
from pokemon_red_completion.clean_start_player import run_portable_clean_start
from pokemon_red_completion.collection_protocol import (
    collection_document_sha256,
    load_committed_collection_registry,
    objective_graph_document,
)
from pokemon_red_completion.learned_battle_policy import load_battle_model_artifact
from pokemon_red_completion.planner_model import load_objective_model_artifact
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.quest import quest_graph_payload
from pokemon_red_completion.rom import resolve_rom_path
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.training_candidate_model import load_training_candidate_model
from pokemon_red_completion.training_control_model import load_training_control_model

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--objective-model", type=Path, required=True)
    parser.add_argument("--battle-model", type=Path)
    parser.add_argument("--battle-control-model", type=Path)
    parser.add_argument("--execute-battle-control", action="store_true")
    parser.add_argument("--require-teacher-free-battle", action="store_true")
    parser.add_argument("--battle-confidence-threshold", type=float, default=0.0)
    parser.add_argument("--battle-control-confidence-threshold", type=float, default=0.0)
    parser.add_argument("--training-control-model", type=Path)
    parser.add_argument("--training-control-model-sha256")
    parser.add_argument("--execute-training-control", action="store_true")
    parser.add_argument("--training-candidate-model", type=Path)
    parser.add_argument("--training-candidate-model-sha256")
    parser.add_argument("--execute-training-candidate", action="store_true")
    parser.add_argument(
        "--diagnostic-seed",
        type=int,
        required=True,
        help="uncounted root; counted campaign assignments are intentionally unsupported",
    )
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=2)
    args = parser.parse_args(argv)
    _require_pair(
        parser,
        args.training_control_model,
        args.training_control_model_sha256,
        name="training control",
    )
    _require_pair(
        parser,
        args.training_candidate_model,
        args.training_candidate_model_sha256,
        name="training candidate",
    )
    if args.execute_battle_control and args.battle_control_model is None:
        parser.error("--execute-battle-control requires --battle-control-model")
    if args.require_teacher_free_battle and args.battle_model is None:
        parser.error("--require-teacher-free-battle requires --battle-model")
    if args.execute_training_control and args.training_control_model is None:
        parser.error("--execute-training-control requires --training-control-model")
    if args.execute_training_candidate and args.training_candidate_model is None:
        parser.error("--execute-training-candidate requires --training-candidate-model")
    if type(args.diagnostic_seed) is not int or not 0 <= args.diagnostic_seed < (1 << 64):  # noqa: E721
        parser.error("--diagnostic-seed must be a uint64")

    source = detect_source_identity(REPOSITORY_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(REPOSITORY_ROOT, source)
    graph_sha256 = collection_document_sha256(
        objective_graph_document(quest_graph_payload(COMPLETION_QUEST))
    )
    objective_model = load_objective_model_artifact(
        args.objective_model,
        expected_feature_names=ObjectiveFeatureProjector(COMPLETION_QUEST).feature_names,
        expected_objective_graph_sha256=graph_sha256,
    )
    battle_model = (
        load_battle_model_artifact(args.battle_model)
        if args.battle_model is not None
        else None
    )
    battle_control_model = (
        load_battle_control_model_artifact(args.battle_control_model)
        if args.battle_control_model is not None
        else None
    )
    training_control_model = (
        load_training_control_model(
            args.training_control_model,
            expected_sha256=args.training_control_model_sha256,
        )
        if args.training_control_model is not None
        else None
    )
    training_candidate_model = (
        load_training_candidate_model(
            args.training_candidate_model,
            expected_sha256=args.training_candidate_model_sha256,
        )
        if args.training_candidate_model is not None
        else None
    )
    schedule = load_committed_collection_registry(REPOSITORY_ROOT).schedule
    offsets = schedule.offsets(args.diagnostic_seed)
    schedule_sha256 = schedule.schedule_sha256(args.diagnostic_seed)
    initial_wait_frames = derive_initial_wait_frames(args.diagnostic_seed)
    report = run_portable_clean_start(
        resolve_rom_path(args.rom),
        objective_model=objective_model,
        battle_model=battle_model,
        battle_control_model=battle_control_model,
        execute_battle_control_model=args.execute_battle_control,
        battle_confidence_threshold=args.battle_confidence_threshold,
        battle_control_confidence_threshold=args.battle_control_confidence_threshold,
        require_teacher_free_battle=args.require_teacher_free_battle,
        training_control_model=training_control_model,
        execute_training_control_model=args.execute_training_control,
        training_candidate_model=training_candidate_model,
        execute_training_candidate_model=args.execute_training_candidate,
        initial_wait_frames=initial_wait_frames,
        battle_start_offsets=offsets,
        watch=args.watch,
        speed=args.speed if args.watch else None,
    )
    payload = {
        "claim": (
            "One uncounted diagnostic root exercised the portable clean-start loop. "
            "It cannot enter or replace the future ten-root campaign."
        ),
        "diagnostic_root": {
            "battle_schedule_sha256": schedule_sha256,
            "counted": False,
            "harness_seed": args.diagnostic_seed,
            "initial_wait_frames": initial_wait_frames,
        },
        "model_identities": {
            "battle_control": (
                collection_document_sha256(battle_control_model.to_dict())
                if battle_control_model is not None
                else None
            ),
            "battle_move": (
                hashlib.sha256(battle_model.to_json().encode("ascii")).hexdigest()
                if battle_model is not None
                else None
            ),
            "objective": report.objective_policy.get("model_sha256"),
            "training_candidate": (
                args.training_candidate_model_sha256
                if training_candidate_model is not None
                else None
            ),
            "training_control": (
                args.training_control_model_sha256
                if training_control_model is not None
                else None
            ),
        },
        "promotion_eligible": False,
        "run": report.public_dict(),
        "schema": "pokemon-red-portable-clean-start-rehearsal-v1",
        "source": source.public_dict(),
        "status": "passed_uncounted_rehearsal",
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding="ascii")
    print(encoded, end="")
    return 0


def _require_pair(
    parser: argparse.ArgumentParser,
    path: Path | None,
    digest: str | None,
    *,
    name: str,
) -> None:
    if (path is None) != (digest is None):
        parser.error(f"{name} requires both a model and exact SHA-256")


if __name__ == "__main__":
    raise SystemExit(main())
