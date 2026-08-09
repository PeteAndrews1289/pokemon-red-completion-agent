#!/usr/bin/env python3
"""Run one explicitly uncounted portable clean-start learned-stack rehearsal."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pokemon_red_completion.battle_control_model import load_battle_control_model_artifact
from pokemon_red_completion.battle_switch_target_model import (
    load_battle_switch_target_model_artifact,
)
from pokemon_red_completion.clean_start_campaign import derive_initial_wait_frames
from pokemon_red_completion.clean_start_player import (
    CleanStartPlayerError,
    run_portable_clean_start,
)
from pokemon_red_completion.collection_protocol import (
    collection_document_sha256,
    load_committed_collection_registry,
    objective_graph_document,
)
from pokemon_red_completion.learned_battle_policy import load_battle_model_artifact
from pokemon_red_completion.planner_model import load_objective_model_artifact
from pokemon_red_completion.planner_semantics import ObjectiveFeatureProjector
from pokemon_red_completion.provenance import (
    canonical_sha256,
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
    parser.add_argument("--battle-switch-target-model", type=Path)
    parser.add_argument("--execute-battle-switch-target", action="store_true")
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
    parser.add_argument(
        "--baseline-timing",
        action="store_true",
        help=(
            "disable initial-wait and battle-start perturbations for an explicitly uncounted "
            "integration baseline"
        ),
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
    if args.execute_battle_switch_target and args.battle_switch_target_model is None:
        parser.error("--execute-battle-switch-target requires --battle-switch-target-model")
    if args.require_teacher_free_battle and args.battle_model is None:
        parser.error("--require-teacher-free-battle requires --battle-model")
    if args.battle_switch_target_model is not None and args.battle_model is None:
        parser.error("--battle-switch-target-model requires --battle-model")
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
        load_battle_model_artifact(args.battle_model) if args.battle_model is not None else None
    )
    battle_control_model = (
        load_battle_control_model_artifact(args.battle_control_model)
        if args.battle_control_model is not None
        else None
    )
    battle_switch_target_artifact = (
        load_battle_switch_target_model_artifact(args.battle_switch_target_model)
        if args.battle_switch_target_model is not None
        else None
    )
    if (
        args.execute_battle_switch_target
        and battle_switch_target_artifact is not None
        and not battle_switch_target_artifact.causal_trial_authority
    ):
        parser.error("switch-target artifact lacks isolated causal-trial authority")
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
    offsets = None if args.baseline_timing else schedule.offsets(args.diagnostic_seed)
    schedule_sha256 = (
        None if args.baseline_timing else schedule.schedule_sha256(args.diagnostic_seed)
    )
    initial_wait_frames = (
        0 if args.baseline_timing else derive_initial_wait_frames(args.diagnostic_seed)
    )
    diagnostic_root = {
        "battle_schedule_sha256": schedule_sha256,
        "counted": False,
        "harness_seed": args.diagnostic_seed,
        "initial_wait_frames": initial_wait_frames,
        "timing_mode": (
            "canonical_unperturbed_baseline"
            if args.baseline_timing
            else "derived_initial_wait_and_battle_offsets"
        ),
    }
    model_identities = {
        "battle_control": (
            _model_identity(args.battle_control_model, battle_control_model)
            if battle_control_model is not None
            else None
        ),
        "battle_move": (
            _model_identity(args.battle_model, battle_model) if battle_model is not None else None
        ),
        "battle_switch_target": (
            _model_identity(
                args.battle_switch_target_model,
                battle_switch_target_artifact.model,
            )
            if battle_switch_target_artifact is not None
            else None
        ),
        "objective": _model_identity(args.objective_model, objective_model),
        "training_candidate": (
            _model_identity(args.training_candidate_model, training_candidate_model)
            if training_candidate_model is not None
            else None
        ),
        "training_control": (
            _model_identity(args.training_control_model, training_control_model)
            if training_control_model is not None
            else None
        ),
    }
    try:
        report = run_portable_clean_start(
            resolve_rom_path(args.rom),
            objective_model=objective_model,
            battle_model=battle_model,
            battle_control_model=battle_control_model,
            execute_battle_control_model=args.execute_battle_control,
            battle_switch_target_model=(
                battle_switch_target_artifact.model
                if battle_switch_target_artifact is not None
                else None
            ),
            execute_battle_switch_target_model=args.execute_battle_switch_target,
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
    except Exception as error:
        failure: dict[str, object] = {
            "exception_type": type(error).__name__,
            "message": str(error),
            "stage": "portable_clean_start_execution",
        }
        if isinstance(error, CleanStartPlayerError) and error.evidence is not None:
            failure["evidence"] = error.evidence
        _emit(
            {
                "claim": (
                    "One uncounted diagnostic root failed closed. It cannot enter or replace "
                    "the future ten-root campaign."
                ),
                "diagnostic_root": diagnostic_root,
                "failure": failure,
                "model_identities": model_identities,
                "promotion_eligible": False,
                "schema": "pokemon-red-portable-clean-start-rehearsal-v1",
                "source": source.public_dict(),
                "status": "failed_uncounted_rehearsal",
            },
            args.out,
        )
        return 2
    payload = {
        "claim": (
            "One uncounted diagnostic root exercised the portable clean-start loop. "
            "It cannot enter or replace the future ten-root campaign."
        ),
        "diagnostic_root": diagnostic_root,
        "model_identities": model_identities,
        "promotion_eligible": False,
        "run": report.public_dict(),
        "schema": "pokemon-red-portable-clean-start-rehearsal-v1",
        "source": source.public_dict(),
        "status": "passed_uncounted_rehearsal",
    }
    _emit(payload, args.out)
    return 0


def _model_identity(path: Path | None, model: object) -> dict[str, str]:
    if path is None:
        raise ValueError("model identity requires an artifact path")
    payload_path = path / "model.jsonl" if path.is_dir() else path
    artifact_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest()
    to_dict = getattr(model, "to_dict", None)
    to_json = getattr(model, "to_json", None)
    if callable(to_dict):
        model_sha256 = canonical_sha256(to_dict())
    elif callable(to_json):
        model_sha256 = hashlib.sha256(to_json().encode("ascii")).hexdigest()
    else:
        raise TypeError("authenticated model does not expose a canonical representation")
    return {
        "artifact_sha256": artifact_sha256,
        "model_sha256": model_sha256,
    }


def _emit(payload: dict[str, object], destination: Path | None) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(encoded, encoding="ascii")
    print(encoded, end="")


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
