from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.living_dex_goal_policy import (
    LivingDexGoalDecisionMode,
    LivingDexGoalPolicyError,
    LivingDexGoalShadowPolicy,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_FEATURE_NAMES,
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexOptionValueModel,
)


def _model(
    *, acquire_success: float = 0.8, unlock_success: float = 0.2
) -> LivingDexOptionValueModel:
    features = len(LIVING_DEX_OPTION_FEATURE_NAMES)
    outcomes = len(LIVING_DEX_OPTION_OUTCOME_NAMES)
    coefficients = np.zeros((features, outcomes), dtype=np.float64)
    acquire = LIVING_DEX_OPTION_FEATURE_NAMES.index("kind.acquire")
    unlock = LIVING_DEX_OPTION_FEATURE_NAMES.index("kind.unlock_access")
    coefficients[acquire, 0] = acquire_success
    coefficients[unlock, 0] = unlock_success
    return LivingDexOptionValueModel(
        coefficients=coefficients,
        intercept=np.zeros(outcomes, dtype=np.float64),
        feature_mean=np.zeros(features, dtype=np.float64),
        feature_scale=np.ones(features, dtype=np.float64),
        train_dataset_sha256="a" * 64,
        settled_examples=8,
        censored_examples=0,
        ridge=0.25,
        maximum_importance_weight=4.0,
    )


def _question(
    *,
    safety: float = 0.0,
    storage: float = 0.1,
    include_restore: bool = False,
    include_storage: bool = False,
) -> GoalManagerQuestion:
    situation = GoalSituation(
        story_pressure=0.6,
        collection_pressure=0.9,
        team_pressure=0.1,
        evolution_pressure=0.2,
        safety_pressure=safety,
        resource_pressure=0.2,
        storage_pressure=storage,
        recovery_pressure=0.0,
        exploration_pressure=0.3,
    )
    available = {GoalKind.ADVANCE_STORY, GoalKind.ACQUIRE_SPECIES}
    if include_restore:
        available.add(GoalKind.RESTORE_TEAM)
    if include_storage:
        available.add(GoalKind.MANAGE_STORAGE)
    opportunities = tuple(
        GoalOpportunity(
            binding_ref=f"private:{kind.value}",
            kind=kind,
            availability=(
                GoalAvailability.AVAILABLE if kind in available else GoalAvailability.UNAVAILABLE
            ),
            estimated_effort=(0.2 if kind in available else None),
            estimated_risk=(0.1 if kind in available else None),
            unavailable_reason=(
                None if kind in available else GoalUnavailableReason.MISSING_CAPABILITY
            ),
        )
        for kind in GoalKind
    )
    return GoalManagerQuestion(situation, opportunities)


def test_causal_model_ranks_supported_semantic_goals_without_binding_identity() -> None:
    policy = LivingDexGoalShadowPolicy(_model())

    selected = policy.select(_question())

    assert selected.kind is GoalKind.ACQUIRE_SPECIES
    assert policy.decisions == 1
    assert policy.model_decisions == 1
    assert policy.deterministic_decisions == 0
    decision = policy.last_decision
    assert decision is not None
    assert decision.mode is LivingDexGoalDecisionMode.MODEL_SHADOW
    assert {row.goal_kind for row in decision.scores} == {
        GoalKind.ADVANCE_STORY,
        GoalKind.ACQUIRE_SPECIES,
    }
    encoded = str(decision.public_dict())
    assert "private:acquire_species" not in encoded
    assert "binding_ref" not in encoded


def test_restoration_stays_inside_the_deterministic_safety_shell() -> None:
    policy = LivingDexGoalShadowPolicy(_model(acquire_success=1.0))

    selected = policy.select(_question(safety=0.9, include_restore=True))

    assert selected.kind is GoalKind.RESTORE_TEAM
    assert policy.model_decisions == 0
    assert policy.deterministic_decisions == 1
    assert policy.last_decision is not None
    assert policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY
    assert policy.last_decision.scores == ()


def test_critical_storage_pressure_stays_inside_deterministic_safety_shell() -> None:
    policy = LivingDexGoalShadowPolicy(_model(acquire_success=1.0))

    selected = policy.select(_question(storage=0.9, include_storage=True))

    assert selected.kind is GoalKind.MANAGE_STORAGE
    assert policy.model_decisions == 0
    assert policy.deterministic_decisions == 1
    assert policy.last_decision is not None
    assert policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY


def test_single_supported_model_option_falls_back_deterministically() -> None:
    question = _question()
    opportunities = tuple(
        replace(
            item,
            availability=(
                GoalAvailability.AVAILABLE
                if item.kind is GoalKind.ADVANCE_STORY
                else GoalAvailability.UNAVAILABLE
            ),
            estimated_effort=(0.2 if item.kind is GoalKind.ADVANCE_STORY else None),
            estimated_risk=(0.1 if item.kind is GoalKind.ADVANCE_STORY else None),
            unavailable_reason=(
                None
                if item.kind is GoalKind.ADVANCE_STORY
                else GoalUnavailableReason.MISSING_CAPABILITY
            ),
        )
        for item in question.opportunities
    )
    policy = LivingDexGoalShadowPolicy(_model())

    selected = policy.select(GoalManagerQuestion(question.situation, opportunities))

    assert selected.kind is GoalKind.ADVANCE_STORY
    assert policy.last_decision is not None
    assert policy.last_decision.mode is LivingDexGoalDecisionMode.DETERMINISTIC_UNSUPPORTED


def test_model_tie_break_is_semantic_not_candidate_position() -> None:
    model = _model(acquire_success=0.0, unlock_success=0.0)
    first = LivingDexGoalShadowPolicy(model).select(_question())
    question = _question()
    reversed_question = GoalManagerQuestion(
        question.situation,
        tuple(reversed(question.opportunities)),
    )
    second = LivingDexGoalShadowPolicy(model).select(reversed_question)

    assert first.kind is second.kind


def test_policy_rejects_non_model_and_invalid_prediction() -> None:
    with pytest.raises(TypeError, match="option-value model"):
        LivingDexGoalShadowPolicy(object())  # type: ignore[arg-type]

    model = _model()
    with pytest.raises(ValueError, match="parameters differ"):
        replace(model, coefficients=np.full_like(model.coefficients, np.nan))


def test_shadow_score_rejects_nonfinite_values() -> None:
    policy = LivingDexGoalShadowPolicy(_model())
    question = _question()
    original = policy.model.scores

    class _BadModel:
        model_sha256 = "b" * 64

        def scores(self, menu, utility):  # type: ignore[no-untyped-def]
            values = list(original(menu, utility))
            values[0] = float("nan")
            return tuple(values)

        def predict_candidate(self, context, candidate):  # type: ignore[no-untyped-def]
            return policy.model.predict_candidate(context, candidate)

    object.__setattr__(policy, "model", _BadModel())
    with pytest.raises(LivingDexGoalPolicyError, match="invalid score"):
        policy.select(question)
