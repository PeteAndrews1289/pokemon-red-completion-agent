from __future__ import annotations

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
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
    GoalManagerModelError,
    LearnedGoalManagerPolicy,
    canonical_goal_manager_model_sha256,
    evaluate_goal_manager_model,
    fixed_priority_goal_index,
    goal_manager_feature_matrix,
    highest_pressure_goal_index,
)

_KINDS = (
    GoalKind.ADVANCE_STORY,
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.RESTORE_TEAM,
)


def _question(
    index: int,
    target_kind: GoalKind,
    *,
    prefix: str,
    permutation: tuple[int, ...] = (0, 1, 2),
    unavailable_kind: GoalKind | None = None,
) -> GoalManagerQuestion:
    cycle = index % 17
    base = 0.04 + cycle * 0.002
    pressures = {
        "story_pressure": base,
        "collection_pressure": base + 0.01,
        "team_pressure": 0.15,
        "evolution_pressure": 0.12,
        "safety_pressure": base + 0.02,
        "resource_pressure": 0.08,
        "storage_pressure": 0.08,
        "recovery_pressure": 0.0,
        "exploration_pressure": 0.20,
    }
    pressure_field = {
        GoalKind.ADVANCE_STORY: "story_pressure",
        GoalKind.ACQUIRE_SPECIES: "collection_pressure",
        GoalKind.RESTORE_TEAM: "safety_pressure",
    }
    pressures[pressure_field[target_kind]] = 0.82 + cycle * 0.005
    effort = {
        GoalKind.ADVANCE_STORY: 0.05,
        GoalKind.ACQUIRE_SPECIES: 0.35,
        GoalKind.RESTORE_TEAM: 0.20,
    }
    risk = {
        GoalKind.ADVANCE_STORY: 0.30,
        GoalKind.ACQUIRE_SPECIES: 0.12,
        GoalKind.RESTORE_TEAM: 0.01,
    }
    options = []
    for kind in _KINDS:
        if kind is unavailable_kind:
            options.append(
                GoalOpportunity(
                    f"{prefix}.{kind.value}.{index}",
                    kind,
                    GoalAvailability.UNAVAILABLE,
                    unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                )
            )
        else:
            options.append(
                GoalOpportunity(
                    f"{prefix}.{kind.value}.{index}",
                    kind,
                    GoalAvailability.AVAILABLE,
                    estimated_effort=effort[kind],
                    estimated_risk=risk[kind],
                )
            )
    return GoalManagerQuestion(
        GoalSituation(**pressures),
        tuple(options[position] for position in permutation),
    )


def _example(
    index: int,
    target_kind: GoalKind,
    *,
    partition: str = "train",
    environment: str = "pokemon.red",
    permutation: tuple[int, ...] = (0, 1, 2),
) -> GoalManagerExample:
    question = _question(
        index,
        target_kind,
        prefix=environment,
        permutation=permutation,
    )
    selected = next(
        slot
        for slot, opportunity in enumerate(question.opportunities)
        if opportunity.kind is target_kind
    )
    return GoalManagerExample(
        decision_id=f"decision-{partition}-{environment}-{index}",
        episode_id=f"episode-{partition}-{environment}-{index}",
        decision_index=0,
        root_lineage_id=f"root-{partition}-{environment}-{index}",
        partition=partition,
        environment_id=environment,
        actor="deterministic_teacher",
        policy_id="portable-goal-teacher-v1",
        question=question,
        selected_candidate_index=selected,
        outcome_status=GoalDecisionOutcome.SUCCEEDED,
    )


def _training() -> tuple[GoalManagerExample, ...]:
    permutations = ((0, 1, 2), (2, 0, 1), (1, 2, 0))
    return tuple(
        _example(
            index,
            _KINDS[index % len(_KINDS)],
            permutation=permutations[index % len(permutations)],
        )
        for index in range(45)
    )


def test_feature_projection_has_no_game_or_binding_identity() -> None:
    red = _question(1, GoalKind.ACQUIRE_SPECIES, prefix="pokemon.red")
    crystal = _question(1, GoalKind.ACQUIRE_SPECIES, prefix="pokemon.crystal")

    assert goal_manager_feature_matrix(red) == pytest.approx(goal_manager_feature_matrix(crystal))
    assert not any(
        token in name
        for name in GOAL_MANAGER_FEATURE_NAMES
        for token in (
            "game",
            "title",
            "map",
            "objective",
            "species_id",
            "binding",
            "index",
            "slot",
        )
    )


def test_shared_model_learns_context_not_fixed_goal_priority() -> None:
    model = GoalManagerLinearModel.fit(_training(), epochs=600)
    validation = tuple(
        _example(
            100 + index,
            _KINDS[index % len(_KINDS)],
            partition="validation",
            environment="pokemon.crystal",
            permutation=((1, 0, 2), (0, 2, 1), (2, 1, 0))[index % 3],
        )
        for index in range(18)
    )

    metrics = evaluate_goal_manager_model(model, validation)

    assert metrics.accuracy >= 0.94
    assert metrics.lowest_effort_baseline_accuracy == pytest.approx(1 / 3)
    assert metrics.public_dict()["baselines"] == {
        "fixed_priority": {
            "accuracy": pytest.approx(1 / 3),
            "paired_comparison": {
                "wins": 12,
                "losses": 0,
                "two_sided_exact_p": pytest.approx(0.00048828125),
            },
        },
        "highest_pressure": {
            "accuracy": 1.0,
            "paired_comparison": {
                "wins": 0,
                "losses": 0,
                "two_sided_exact_p": 1.0,
            },
        },
        "lowest_effort": {
            "accuracy": pytest.approx(1 / 3),
            "paired_comparison": {
                "wins": 12,
                "losses": 0,
                "two_sided_exact_p": pytest.approx(0.00048828125),
            },
        },
    }
    assert dict(metrics.environment_accuracy)["pokemon.crystal"] >= 0.94


def test_preregistered_baselines_ignore_bindings_and_candidate_positions() -> None:
    forward = _question(7, GoalKind.RESTORE_TEAM, prefix="pokemon.red")
    reordered = _question(
        7,
        GoalKind.RESTORE_TEAM,
        prefix="pokemon.crystal",
        permutation=(2, 0, 1),
    )

    for selector in (fixed_priority_goal_index, highest_pressure_goal_index):
        assert forward.opportunities[selector(forward)].kind is (
            reordered.opportunities[selector(reordered)].kind
        )


def test_model_is_permutation_equivariant_and_binding_invariant() -> None:
    model = GoalManagerLinearModel.fit(_training(), epochs=500)
    forward = _question(80, GoalKind.RESTORE_TEAM, prefix="pokemon.red")
    reordered = _question(
        80,
        GoalKind.RESTORE_TEAM,
        prefix="pokemon.crystal",
        permutation=(2, 0, 1),
    )

    forward_by_kind = {
        item.kind: probability
        for item, probability in zip(
            forward.opportunities,
            model.probabilities(forward),
            strict=True,
        )
    }
    reordered_by_kind = {
        item.kind: probability
        for item, probability in zip(
            reordered.opportunities,
            model.probabilities(reordered),
            strict=True,
        )
    }

    assert forward_by_kind == pytest.approx(reordered_by_kind)
    assert forward.opportunities[model.predict(forward)].kind is GoalKind.RESTORE_TEAM
    assert reordered.opportunities[model.predict(reordered)].kind is GoalKind.RESTORE_TEAM


def test_unavailable_candidates_receive_exactly_zero_probability() -> None:
    model = GoalManagerLinearModel.fit(_training(), epochs=500)
    question = _question(
        90,
        GoalKind.ACQUIRE_SPECIES,
        prefix="pokemon.red",
        unavailable_kind=GoalKind.ACQUIRE_SPECIES,
    )
    probabilities = model.probabilities(question)
    unavailable = next(
        index
        for index, item in enumerate(question.opportunities)
        if item.kind is GoalKind.ACQUIRE_SPECIES
    )

    assert probabilities[unavailable] == 0.0
    assert np.sum(probabilities) == pytest.approx(1.0)
    assert model.predict(question) != unavailable


def test_live_policy_binds_model_choice_without_teacher_fallback() -> None:
    model = GoalManagerLinearModel.fit(_training(), epochs=500)
    policy = LearnedGoalManagerPolicy(model, confidence_threshold=0.50)
    question = _question(95, GoalKind.RESTORE_TEAM, prefix="pokemon.red")

    selection = policy.select(question)

    assert selection.kind is GoalKind.RESTORE_TEAM
    assert selection.binding_ref.startswith("pokemon.red.")
    assert policy.learned_choice_decisions == 1
    assert policy.public_dict()["teacher_queries"] == 0
    assert policy.public_dict()["teacher_fallbacks"] == 0


def test_live_policy_rejects_probability_on_a_masked_option() -> None:
    class InvalidScorer:
        def probabilities(self, question: GoalManagerQuestion) -> np.ndarray:
            return np.asarray((0.1, 0.45, 0.45), dtype=np.float64)

        def to_dict(self) -> dict[str, object]:
            return {"model_id": "invalid-test-scorer"}

    question = _question(
        96,
        GoalKind.ACQUIRE_SPECIES,
        prefix="pokemon.red",
        unavailable_kind=GoalKind.ADVANCE_STORY,
    )
    policy = LearnedGoalManagerPolicy(InvalidScorer())

    with pytest.raises(GoalManagerModelError, match="unavailable"):
        policy.select(question)


def test_model_round_trip_preserves_canonical_identity() -> None:
    model = GoalManagerLinearModel.fit(_training(), epochs=100)
    restored = GoalManagerLinearModel.from_dict(model.to_dict())

    assert canonical_goal_manager_model_sha256(restored) == (
        canonical_goal_manager_model_sha256(model)
    )
    assert not restored.weights.flags.writeable


def test_fitting_rejects_validation_or_failed_teacher_rows() -> None:
    validation = _example(
        1,
        GoalKind.ADVANCE_STORY,
        partition="validation",
    )
    with pytest.raises(GoalManagerModelError, match="training-partition"):
        GoalManagerLinearModel.fit((validation,))

    successful = _example(2, GoalKind.ACQUIRE_SPECIES)
    failed = GoalManagerExample(
        decision_id=successful.decision_id,
        episode_id=successful.episode_id,
        decision_index=successful.decision_index,
        root_lineage_id=successful.root_lineage_id,
        partition=successful.partition,
        environment_id=successful.environment_id,
        actor=successful.actor,
        policy_id=successful.policy_id,
        question=successful.question,
        selected_candidate_index=successful.selected_candidate_index,
        outcome_status=GoalDecisionOutcome.FAILED,
        failure_reason=GoalFailureReason.OUTCOME_NOT_VERIFIED,
    )
    with pytest.raises(GoalManagerModelError, match="successful teacher"):
        GoalManagerLinearModel.fit((successful, failed))
