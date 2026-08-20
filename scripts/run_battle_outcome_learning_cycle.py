#!/usr/bin/env python3
"""Collect one Red train/development outcome pair and publish a bounded model update."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker  # noqa: E402
from pokemon_red_completion.battle_outcome_learning import (  # noqa: E402
    run_battle_outcome_learning_cycle,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    open_battle_scenario_capture,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.learned_battle_policy import (  # noqa: E402
    load_battle_model_artifact,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_battle_outcome_runtime import (  # noqa: E402
    collect_red_battle_outcome_example,
)
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402


class BattleOutcomeCycleError(RuntimeError):
    """Raised when an official bounded cycle violates its frozen inputs."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--train-state", type=Path, required=True)
    parser.add_argument("--train-manifest", type=Path, required=True)
    parser.add_argument("--development-state", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--prior-l2", type=float, default=0.1)
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - clean source establishes this
        raise AssertionError("clean source identity lacks a commit")
    train_capture = open_battle_scenario_capture(
        args.train_state,
        args.train_manifest,
    )
    development_capture = open_battle_scenario_capture(
        args.development_state,
        args.development_manifest,
    )
    if train_capture.manifest.partition is not ScenarioPartition.TRAIN:
        raise BattleOutcomeCycleError("train capture has the wrong partition")
    if development_capture.manifest.partition is not ScenarioPartition.DEVELOPMENT:
        raise BattleOutcomeCycleError("development capture has the wrong partition")
    if any(
        capture.manifest.source_commit != source.git_commit
        for capture in (train_capture, development_capture)
    ):
        raise BattleOutcomeCycleError("capture source differs from the published runner")

    base_model = load_battle_model_artifact(args.base_model)
    if not isinstance(base_model, MaskedMLPMoveRanker):
        raise BattleOutcomeCycleError("bounded outcome adaptation requires the nonlinear prior")
    rom_path = resolve_rom_path(args.rom)

    def session_factory():  # type: ignore[no-untyped-def]
        return PyBoyAdapter(rom_path)

    train_collection = collect_red_battle_outcome_example(
        train_capture,
        session_factory=session_factory,
    )
    development_collection = collect_red_battle_outcome_example(
        development_capture,
        session_factory=session_factory,
    )
    informative = (
        train_collection.example.learner_update_eligible
        and development_collection.example.learner_update_eligible
    )
    cycle = (
        run_battle_outcome_learning_cycle(
            base_model,
            training_examples=(train_collection.example,),
            development_examples=(development_collection.example,),
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            prior_l2=args.prior_l2,
        )
        if informative
        else None
    )

    private_root = open_private_root(
        args.private_root,
        repository_root=PROJECT_ROOT,
    )
    writer = private_root.begin_artifact(
        f"red-battle-outcome-update-{uuid.uuid4().hex}",
        kind="battle_outcome_cycle",
    )
    updated_model = None if cycle is None else cycle.update.model
    model_sha256 = (
        None
        if updated_model is None
        else hashlib.sha256(updated_model.to_json().encode("ascii")).hexdigest()
    )
    with writer:
        writer.append(
            "outcomes",
            {
                "record_type": "battle_outcome_collection",
                "split": ScenarioPartition.TRAIN.value,
                "collection": train_collection.public_dict(),
            },
        )
        writer.append(
            "outcomes",
            {
                "record_type": "battle_outcome_collection",
                "split": ScenarioPartition.DEVELOPMENT.value,
                "collection": development_collection.public_dict(),
            },
        )
        if cycle is not None and updated_model is not None and model_sha256 is not None:
            writer.append(
                "model",
                {
                    "record_type": "battle_model_candidate",
                    "model": updated_model.to_dict(),
                    "model_sha256": model_sha256,
                    "source": source.public_dict(),
                    "authority": "shadow_only",
                },
            )
            writer.append(
                "evaluation",
                {
                    "record_type": "battle_outcome_learning_cycle",
                    "cycle": cycle.public_dict(),
                    "claim": "plumbing_evidence_only",
                    "promotion_gate_passed": False,
                    "reason_promotion_false": "independent_unseen_gate_not_run",
                },
            )
        else:
            writer.append(
                "evaluation",
                {
                    "record_type": "battle_outcome_no_update",
                    "claim": "insufficient_preference_signal",
                    "train_learner_update_eligible": (
                        train_collection.example.learner_update_eligible
                    ),
                    "development_learner_update_eligible": (
                        development_collection.example.learner_update_eligible
                    ),
                    "promotion_gate_passed": False,
                    "model_written": False,
                },
            )
    return {
        "schema": "pokemon-red-battle-outcome-cycle-receipt-v1",
        "status": "ok" if cycle is not None else "insufficient_signal",
        "artifact": writer.summary.public_dict(),
        "cycle": None if cycle is None else cycle.public_dict(),
        "model_sha256": model_sha256,
        "claim": (
            "plumbing_evidence_only"
            if cycle is not None
            else "insufficient_preference_signal"
        ),
        "authority_promoted": False,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(_run(args), ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
