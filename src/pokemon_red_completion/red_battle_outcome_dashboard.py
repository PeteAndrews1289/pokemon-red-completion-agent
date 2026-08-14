"""View-only projection of the first real Red outcome-learning cycle."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence

from pokemon_red_completion.progress_dashboard import (
    DashboardExperimentState,
    DashboardLearningComponent,
    DashboardModelState,
    DashboardSnapshot,
    ProgressDashboardError,
)

BATTLE_OUTCOME_EVIDENCE_SCHEMA = (
    "pokemon-red-battle-outcome-learning-cycle-evidence-v1"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def battle_outcome_dashboard_snapshot(
    evidence: Mapping[str, object],
) -> DashboardSnapshot:
    """Build the human-facing, path-free result view from public evidence."""

    if not isinstance(evidence, Mapping):
        raise TypeError("battle outcome evidence must be a mapping")
    if evidence.get("schema") != BATTLE_OUTCOME_EVIDENCE_SCHEMA:
        raise ProgressDashboardError("battle outcome evidence schema is unsupported")
    if evidence.get("status") != "plumbing_complete_candidate_rejected":
        raise ProgressDashboardError("battle outcome evidence status is unsupported")

    captures = _sequence(evidence, "captures")
    if len(captures) != 2 or any(not isinstance(row, Mapping) for row in captures):
        raise ProgressDashboardError("battle outcome evidence must contain two captures")
    collection = _mapping(evidence, "counterfactual_collection")
    train = _mapping(collection, "train")
    development = _mapping(collection, "development")
    learner = _mapping(evidence, "learner_update")
    protected = _mapping(evidence, "protected_access")

    measured_candidates = _count(collection, "measured_candidates")
    train_examples = _count(learner, "training_examples")
    development_examples = _count(learner, "development_examples")
    base_correct = _count(learner, "base_development_correct")
    updated_correct = _count(learner, "updated_development_correct")
    if train_examples != 1 or development_examples != 1:
        raise ProgressDashboardError(
            "first outcome dashboard requires its one-train/one-development evidence"
        )
    if base_correct > development_examples or updated_correct > development_examples:
        raise ProgressDashboardError("development correctness exceeds its denominator")
    if updated_correct >= base_correct:
        raise ProgressDashboardError("rejected outcome candidate does not reproduce regression")

    base_model_sha256 = _sha256(learner, "base_model_sha256")
    updated_model_sha256 = _sha256(learner, "updated_model_sha256")
    loss_before = _finite_nonnegative(learner, "objective_loss_before")
    loss_after = _finite_nonnegative(learner, "objective_loss_after")
    if loss_after >= loss_before:
        raise ProgressDashboardError("outcome update does not reproduce lower fit loss")

    actions = _count(train, "actions") + _count(development, "actions")
    frames = _count(train, "frames") + _count(development, "frames")
    teacher_queries = _count(protected, "teacher_queries")
    sealed_opened = _count(protected, "red_sealed_test_cases_opened")
    crystal_opened = _count(protected, "crystal_contexts_opened")
    full_replays = _count(protected, "full_game_replays")
    if teacher_queries or sealed_opened or crystal_opened or full_replays:
        raise ProgressDashboardError("protected-access counters must remain zero")

    return DashboardSnapshot(
        game="Pokémon Red",
        run_status="paused",
        stage="Outcome learner · candidate rejected",
        message=(
            "The teacher-free counterfactual loop worked, but one training state overfit: "
            "the frozen prior was correct on development and the update was not."
        ),
        frame_count=frames,
        actions=actions,
        stage_progress=1.0,
        location="Pokémon Mansion 1F · authenticated snapshots",
        collection_target=124,
        model=DashboardModelState(
            mode="shadow",
            candidate="Prior-preserving Red battle outcome candidate",
            choice=(
                f"Rejected: development fell from {base_correct}/{development_examples} "
                f"to {updated_correct}/{development_examples}"
            ),
            decisions=measured_candidates,
            teacher_queries=teacher_queries,
            fallbacks=0,
        ),
        experiment=DashboardExperimentState(
            phase="blocked",
            zero_shot_completed=len(captures),
            zero_shot_total=len(captures),
            adaptation_completed=train_examples,
            adaptation_total=train_examples,
            sealed_completed=0,
            sealed_total=200,
            predictions_committed=False,
            heading="Battle outcome learning",
            eyebrow="Red model-first laboratory",
            counter_labels=(
                "Authenticated captures",
                "Learner updates",
                "Unseen promotion battles",
            ),
        ),
        learning_components=(
            DashboardLearningComponent(
                name="Outcome-adapted battle MLP",
                scope=(
                    "One-state outcome update; frozen prior is the comparator; "
                    "development regressed"
                ),
                status="blocked",
                authority="shadow_only",
                train_examples=train_examples,
                validation_examples=development_examples,
                validation_correct=updated_correct,
                baseline_correct=base_correct,
                baseline_id=f"frozen_prior_{base_model_sha256[:12]}",
                model_sha256=updated_model_sha256,
                independent_validation_units=development_examples,
                candidate_count_results=((4, updated_correct, development_examples),),
            ),
        ),
        events=(
            (
                f"Collected {measured_candidates} controller-proven move outcomes from "
                f"{len(captures)} authenticated states"
            ),
            "Every counterfactual used exactly 2,048 pre-attack frames",
            f"Training objective fell {loss_before:.4f} → {loss_after:.4f}",
            (
                f"Untouched development regressed {base_correct}/{development_examples} → "
                f"{updated_correct}/{development_examples}; no authority granted"
            ),
            "Teacher 0 · sealed Red 0 · Crystal 0 · full-game replays 0",
            "Next: smallest battle learning curve, then one thin navigation and party adapter",
        ),
    )


def _mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ProgressDashboardError(f"battle outcome {key.replace('_', ' ')} is invalid")
    return value


def _sequence(source: Mapping[str, object], key: str) -> Sequence[object]:
    value = source.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ProgressDashboardError(f"battle outcome {key.replace('_', ' ')} is invalid")
    return value


def _count(source: Mapping[str, object], key: str) -> int:
    value = source.get(key)
    if type(value) is not int or value < 0:  # noqa: E721
        raise ProgressDashboardError(f"battle outcome {key.replace('_', ' ')} is invalid")
    return value


def _sha256(source: Mapping[str, object], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ProgressDashboardError(f"battle outcome {key.replace('_', ' ')} is invalid")
    return value


def _finite_nonnegative(source: Mapping[str, object], key: str) -> float:
    value = source.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ProgressDashboardError(f"battle outcome {key.replace('_', ' ')} is invalid")
    return float(value)


__all__ = [
    "BATTLE_OUTCOME_EVIDENCE_SCHEMA",
    "battle_outcome_dashboard_snapshot",
]
