#!/usr/bin/env python3
"""Run the frozen 1/2/4-context Red battle outcome learning curve."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.battle_neural_model import MaskedMLPMoveRanker  # noqa: E402
from pokemon_red_completion.battle_outcome_learning import (  # noqa: E402
    run_battle_outcome_learning_curve,
)
from pokemon_red_completion.battle_scenario_capture import (  # noqa: E402
    BattleScenarioCapture,
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
    RedBattleOutcomeCollection,
    collect_red_battle_outcome_example,
)
from pokemon_red_completion.rom import resolve_rom_path  # noqa: E402
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.scenario_outcome_adapters import (  # noqa: E402
    BATTLE_TURN_OBJECTIVE,
)

TRAIN_CONTEXTS = 4
DEVELOPMENT_CONTEXTS = 4
TRAINING_SIZES = (1, 2, 4)


class BattleOutcomeCurveError(RuntimeError):
    """Raised when the prospective curve catalog or boundary drifts."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument(
        "--train-capture",
        type=Path,
        nargs=2,
        action="append",
        metavar=("STATE", "MANIFEST"),
        required=True,
    )
    parser.add_argument(
        "--development-capture",
        type=Path,
        nargs=2,
        action="append",
        metavar=("STATE", "MANIFEST"),
        required=True,
    )
    return parser


def _run(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - clean source establishes this
        raise AssertionError("clean source identity lacks a commit")
    train_captures = _open_captures(
        args.train_capture,
        expected_count=TRAIN_CONTEXTS,
        partition=ScenarioPartition.TRAIN,
    )
    development_captures = _open_captures(
        args.development_capture,
        expected_count=DEVELOPMENT_CONTEXTS,
        partition=ScenarioPartition.DEVELOPMENT,
    )
    captures = (*train_captures, *development_captures)
    _require_catalog(captures, source_commit=source.git_commit)

    base_model = load_battle_model_artifact(args.base_model)
    if not isinstance(base_model, MaskedMLPMoveRanker):
        raise BattleOutcomeCurveError("battle outcome curve requires the nonlinear prior")
    rom_path = resolve_rom_path(args.rom)

    def session_factory():  # type: ignore[no-untyped-def]
        return PyBoyAdapter(rom_path)

    train_collections = tuple(
        collect_red_battle_outcome_example(
            capture,
            session_factory=session_factory,
        )
        for capture in train_captures
    )
    development_collections = tuple(
        collect_red_battle_outcome_example(
            capture,
            session_factory=session_factory,
        )
        for capture in development_captures
    )
    _require_complete_collections((*train_collections, *development_collections))
    curve = run_battle_outcome_learning_curve(
        base_model,
        training_examples=tuple(item.example for item in train_collections),
        development_examples=tuple(item.example for item in development_collections),
        training_sizes=TRAINING_SIZES,
        epochs=100,
        learning_rate=0.01,
        prior_l2=0.1,
    )

    private_root = open_private_root(
        args.private_root,
        repository_root=PROJECT_ROOT,
    )
    writer = private_root.begin_artifact(
        f"red-battle-learning-curve-{uuid.uuid4().hex}",
        kind="battle_outcome_learning_curve",
    )
    with writer:
        for split, collections in (
            (ScenarioPartition.TRAIN, train_collections),
            (ScenarioPartition.DEVELOPMENT, development_collections),
        ):
            for catalog_index, collection in enumerate(collections):
                writer.append(
                    "outcomes",
                    {
                        "record_type": "battle_outcome_collection",
                        "split": split.value,
                        "catalog_index": catalog_index,
                        "collection": collection.public_dict(),
                    },
                )
        for point in curve.points:
            if point.update is None:
                continue
            writer.append(
                "models",
                {
                    "record_type": "battle_learning_curve_model",
                    "training_size": point.training_size,
                    "model": point.update.model.to_dict(),
                    "model_sha256": point.update.report.updated_model_sha256,
                    "source": source.public_dict(),
                    "authority": "shadow_only",
                },
            )
        writer.append(
            "evaluation",
            {
                "record_type": "battle_outcome_learning_curve",
                "curve": curve.public_dict(),
                "claim": "descriptive_initial_curve_only",
                "promotion_gate_passed": False,
                "reason_promotion_false": "independent_unseen_gate_not_run",
            },
        )
    return {
        "schema": "pokemon-red-battle-outcome-learning-curve-receipt-v1",
        "status": "ok",
        "artifact": writer.summary.public_dict(),
        "objective_id": BATTLE_TURN_OBJECTIVE.objective_id,
        "objective_sha256": BATTLE_TURN_OBJECTIVE.objective_sha256,
        "train_capture_ids": [item.manifest.capture_id for item in train_captures],
        "development_capture_ids": [
            item.manifest.capture_id for item in development_captures
        ],
        "curve": curve.public_dict(),
        "claim": "descriptive_initial_curve_only",
        "authority_promoted": False,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }


def _open_captures(
    pairs: object,
    *,
    expected_count: int,
    partition: ScenarioPartition,
) -> tuple[BattleScenarioCapture, ...]:
    if not isinstance(pairs, list) or len(pairs) != expected_count:
        raise BattleOutcomeCurveError(
            f"curve requires exactly {expected_count} {partition.value} captures"
        )
    captures = tuple(
        open_battle_scenario_capture(pair[0], pair[1])
        for pair in pairs
        if isinstance(pair, list) and len(pair) == 2
    )
    if len(captures) != expected_count:
        raise BattleOutcomeCurveError("curve capture arguments are malformed")
    if any(item.manifest.partition is not partition for item in captures):
        raise BattleOutcomeCurveError(f"curve {partition.value} capture has the wrong partition")
    return captures


def _require_catalog(
    captures: tuple[BattleScenarioCapture, ...],
    *,
    source_commit: str,
) -> None:
    if any(item.manifest.source_commit != source_commit for item in captures):
        raise BattleOutcomeCurveError("curve capture source differs from the published runner")
    for values, subject in (
        (tuple(item.manifest.capture_id for item in captures), "capture identity"),
        (tuple(item.manifest.root_lineage_id for item in captures), "root lineage"),
        (
            tuple(item.manifest.source_state_sha256 for item in captures),
            "root state",
        ),
        (tuple(item.manifest.state_sha256 for item in captures), "capture state"),
        (
            tuple(item.manifest.initial_observation_sha256 for item in captures),
            "initial observation",
        ),
        (tuple(item.manifest_sha256 for item in captures), "capture manifest"),
    ):
        if any(value is None for value in values):
            raise BattleOutcomeCurveError(f"curve {subject} binding is unavailable")
        if len(values) != len(set(values)):
            raise BattleOutcomeCurveError(f"curve repeats a {subject}")


def _require_complete_collections(
    collections: tuple[RedBattleOutcomeCollection, ...],
) -> None:
    for collection in collections:
        available = int(collection.example.usable_mask.sum())
        measured = sum(item is not None for item in collection.outcomes)
        if measured != available:
            raise BattleOutcomeCurveError(
                "curve collection lacks an available candidate outcome"
            )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(_run(args), ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
