from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalManagerExample,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
)
from pokemon_red_completion.goal_manager_development import GoalManagerDevelopmentTarget
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
)
from pokemon_red_completion.goal_manager_outcome_learning import (
    GoalManagerOutcomeLearningError,
    fit_goal_manager_outcome_successor_update,
    fit_goal_manager_outcome_update,
    fit_goal_manager_train_outcome_update,
    outcome_update_configuration,
    require_unchanged_guard_winners,
)


def _question(*, safety: float, storage: float) -> GoalManagerQuestion:
    return GoalManagerQuestion(
        GoalSituation(
            story_pressure=0.2,
            collection_pressure=0.7,
            team_pressure=0.5,
            evolution_pressure=0.6,
            safety_pressure=safety,
            resource_pressure=0.3,
            storage_pressure=storage,
            recovery_pressure=0.0,
            exploration_pressure=0.2,
        ),
        (
            GoalOpportunity(
                "story",
                GoalKind.ADVANCE_STORY,
                GoalAvailability.AVAILABLE,
                estimated_effort=0.8,
                estimated_risk=0.4,
            ),
            GoalOpportunity(
                "storage",
                GoalKind.MANAGE_STORAGE,
                GoalAvailability.AVAILABLE,
                estimated_effort=0.2,
                estimated_risk=0.05,
            ),
            GoalOpportunity(
                "restore",
                GoalKind.RESTORE_TEAM,
                GoalAvailability.AVAILABLE,
                estimated_effort=0.1,
                estimated_risk=0.01,
            ),
        ),
    )


def _row(
    index: int,
    *,
    selected: int,
    reward: float = 1.0,
    partition: str = "development",
) -> tuple[GoalManagerExample, GoalManagerDevelopmentTarget]:
    question = _question(safety=0.3 + index * 0.1, storage=0.8 - index * 0.1)
    decision = f"decision-{index}"
    probability = 1.0 / 3.0
    example = GoalManagerExample(
        decision_id=decision,
        episode_id="episode",
        decision_index=index,
        root_lineage_id="root",
        partition=partition,
        environment_id="pokemon.mainline:red:gb:us:rev0",
        actor="exploratory_goal_manager",
        policy_id="red-goal-manager-outcome-development-v1",
        question=question,
        selected_candidate_index=selected,
        outcome_status=(
            GoalDecisionOutcome.SUCCEEDED if reward == 1.0 else GoalDecisionOutcome.FAILED
        ),
        failure_reason=(None if reward == 1.0 else GoalFailureReason.BINDING_FAILED),
    )
    target = GoalManagerDevelopmentTarget(
        decision_id=decision,
        selected_candidate_index=selected,
        reward=reward,
        behavior_probability=probability,
        importance_weight=3.0,
    )
    return example, target


def _model() -> GoalManagerLinearModel:
    width = len(GOAL_MANAGER_FEATURE_NAMES)
    return GoalManagerLinearModel(
        weights=np.zeros(width),
        feature_mean=np.zeros(width),
        feature_scale=np.ones(width),
        l2=0.02,
        training_epochs=1,
    )


def test_single_frozen_update_reinforces_both_successes() -> None:
    rows = (_row(0, selected=1), _row(1, selected=2))

    result = fit_goal_manager_outcome_update(_model(), rows)

    assert result.after.weighted_binary_cross_entropy < (
        result.before.weighted_binary_cross_entropy
    )
    assert all(
        after > before
        for before, after in zip(
            result.before.selected_probabilities,
            result.after.selected_probabilities,
            strict=True,
        )
    )
    assert result.maximum_weight_delta > 0.0
    assert outcome_update_configuration()["update_steps"] == 1
    assert outcome_update_configuration()["hyperparameter_search"] is False


def test_train_only_update_requires_explicit_train_partition() -> None:
    rows = (
        _row(0, selected=1, partition="train"),
        _row(1, selected=1, partition="train"),
    )

    result = fit_goal_manager_train_outcome_update(_model(), rows)

    assert result.after.weighted_binary_cross_entropy < (
        result.before.weighted_binary_cross_entropy
    )
    with pytest.raises(GoalManagerOutcomeLearningError, match="row differs"):
        fit_goal_manager_train_outcome_update(
            _model(),
            (_row(2, selected=1, partition="development"),),
        )


def test_negative_outcome_reduces_selected_probability() -> None:
    positive = _row(0, selected=1)
    negative = _row(1, selected=2, reward=-1.0)
    base = _model()

    result = fit_goal_manager_outcome_update(base, (positive, negative))

    assert result.after.selected_probabilities[0] > result.before.selected_probabilities[0]
    assert result.after.selected_probabilities[1] < result.before.selected_probabilities[1]


def test_update_rejects_changed_target_identity() -> None:
    example, target = _row(0, selected=1)

    with pytest.raises(GoalManagerOutcomeLearningError, match="row differs"):
        fit_goal_manager_outcome_update(
            _model(),
            ((example, replace(target, selected_candidate_index=2)),),
        )


def test_guard_rejects_a_winner_flip() -> None:
    base = _model()
    guard = _row(0, selected=1)[0]
    weights = base.weights.copy()
    weights[GOAL_MANAGER_FEATURE_NAMES.index("candidate.kind.manage_storage")] = 100.0
    candidate = GoalManagerLinearModel(
        weights=weights,
        feature_mean=base.feature_mean,
        feature_scale=base.feature_scale,
        l2=base.l2,
        training_epochs=1,
    )

    with pytest.raises(GoalManagerOutcomeLearningError, match="protected"):
        require_unchanged_guard_winners(base, candidate, (guard,))


def test_successor_uses_only_fresh_row_and_preserves_aligned_anchor() -> None:
    fresh = _row(0, selected=1)
    anchor = _row(1, selected=1)

    result = fit_goal_manager_outcome_successor_update(
        _model(),
        (fresh,),
        (anchor,),
    )

    assert result.update.before.examples == 1
    assert result.anchor_before.examples == 1
    assert (
        result.update.after.selected_probabilities[0]
        > (result.update.before.selected_probabilities[0])
    )
    assert (
        result.anchor_after.selected_probabilities[0]
        >= (result.anchor_before.selected_probabilities[0])
    )


def test_successor_rejects_anchor_regression() -> None:
    fresh = _row(0, selected=1)
    opposed_anchor = _row(1, selected=2)

    with pytest.raises(GoalManagerOutcomeLearningError, match="regressed"):
        fit_goal_manager_outcome_successor_update(
            _model(),
            (fresh,),
            (opposed_anchor,),
        )


def test_successor_rejects_fresh_anchor_identity_overlap() -> None:
    row = _row(0, selected=1)

    with pytest.raises(GoalManagerOutcomeLearningError, match="overlaps"):
        fit_goal_manager_outcome_successor_update(_model(), (row,), (row,))
