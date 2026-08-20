from __future__ import annotations

import json

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalCurriculumRequirements,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalManagerError,
    GoalManagerExample,
    GoalManagerQuestion,
    GoalNeed,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
    audit_goal_curriculum,
    bind_goal_selection,
)


def _situation(primary: GoalKind, *, variant: float = 0.0) -> GoalSituation:
    pressure = {
        GoalKind.ADVANCE_STORY: "story_pressure",
        GoalKind.ACQUIRE_SPECIES: "collection_pressure",
        GoalKind.RESTORE_TEAM: "safety_pressure",
    }
    values = {
        "story_pressure": 0.10 + variant,
        "collection_pressure": 0.12 + variant,
        "team_pressure": 0.15,
        "evolution_pressure": 0.15,
        "safety_pressure": 0.08 + variant,
        "resource_pressure": 0.10,
        "storage_pressure": 0.10,
        "recovery_pressure": 0.0,
        "exploration_pressure": 0.20,
    }
    values[pressure[primary]] = 0.90 + variant
    return GoalSituation(**values)


def _opportunities(prefix: str = "red") -> tuple[GoalOpportunity, ...]:
    return (
        GoalOpportunity(
            f"{prefix}.story-binding",
            GoalKind.ADVANCE_STORY,
            GoalAvailability.AVAILABLE,
            estimated_effort=0.20,
            estimated_risk=0.20,
        ),
        GoalOpportunity(
            f"{prefix}.collection-binding",
            GoalKind.ACQUIRE_SPECIES,
            GoalAvailability.AVAILABLE,
            estimated_effort=0.35,
            estimated_risk=0.10,
        ),
        GoalOpportunity(
            f"{prefix}.healing-binding",
            GoalKind.RESTORE_TEAM,
            GoalAvailability.AVAILABLE,
            estimated_effort=0.10,
            estimated_risk=0.01,
        ),
    )


def _example(
    index: int,
    primary: GoalKind,
    *,
    partition: str,
    environment: str,
    reverse: bool = False,
) -> GoalManagerExample:
    opportunities = _opportunities(environment)
    if reverse:
        opportunities = tuple(reversed(opportunities))
    selected = next(
        slot for slot, opportunity in enumerate(opportunities) if opportunity.kind is primary
    )
    variant = 0.001 * index if partition == "train" else 0.03 + 0.001 * index
    return GoalManagerExample(
        decision_id=f"decision-{partition}-{environment}-{index}",
        episode_id=f"episode-{partition}-{environment}-{index}",
        decision_index=0,
        root_lineage_id=f"root-{partition}-{environment}-{index}",
        partition=partition,
        environment_id=environment,
        actor="deterministic_teacher",
        policy_id="portable-goal-teacher-v1",
        question=GoalManagerQuestion(
            situation=_situation(primary, variant=variant),
            opportunities=opportunities,
        ),
        selected_candidate_index=selected,
        outcome_status=GoalDecisionOutcome.SUCCEEDED,
    )


def _small_requirements(*, held_out: tuple[str, ...] = ()) -> GoalCurriculumRequirements:
    return GoalCurriculumRequirements(
        required_needs=(
            GoalNeed.STORY_PROGRESS,
            GoalNeed.COLLECTION_PROGRESS,
            GoalNeed.SAFETY,
        ),
        required_selected_goal_kinds=(
            GoalKind.ADVANCE_STORY,
            GoalKind.ACQUIRE_SPECIES,
            GoalKind.RESTORE_TEAM,
        ),
        minimum_train_examples=3,
        minimum_validation_examples=3,
        minimum_train_examples_per_need=1,
        minimum_validation_examples_per_need=1,
        minimum_train_selections_per_kind=1,
        minimum_validation_selections_per_kind=1,
        minimum_multiway_train_examples=3,
        minimum_context_dependent_menus=1,
        held_out_environment_ids=held_out,
    )


def test_satisfaction_factory_produces_portable_need_pressures() -> None:
    situation = GoalSituation.from_satisfaction(
        story=0.25,
        collection=0.10,
        team=0.50,
        evolution=0.40,
        safety=0.90,
        resources=0.80,
        storage=0.75,
        control=1.0,
        world_knowledge=0.20,
    )

    assert situation.pressure(GoalNeed.STORY_PROGRESS) == 0.75
    assert situation.pressure(GoalNeed.COLLECTION_PROGRESS) == 0.90
    assert situation.pressure(GoalNeed.CONTROL_RECOVERY) == 0.0


def test_policy_projection_is_invariant_to_title_and_binding_identity() -> None:
    situation = _situation(GoalKind.ACQUIRE_SPECIES)
    red = GoalManagerQuestion(situation, _opportunities("pokemon.red"))
    crystal = GoalManagerQuestion(situation, _opportunities("pokemon.crystal"))

    assert red.policy_input == crystal.policy_input
    assert red.ordered_policy_input_sha256 == crystal.ordered_policy_input_sha256
    encoded = json.dumps(dict(red.policy_input), default=list, sort_keys=True)
    assert not any(
        token in encoded
        for token in (
            "pokemon.red",
            "story-binding",
            "map_id",
            "objective_id",
            "species_id",
            "binding_index",
        )
    )


def test_unavailable_goal_is_visible_but_cannot_be_bound() -> None:
    question = GoalManagerQuestion(
        _situation(GoalKind.ADVANCE_STORY),
        (
            GoalOpportunity(
                "story",
                GoalKind.ADVANCE_STORY,
                GoalAvailability.UNKNOWN,
                unavailable_reason=GoalUnavailableReason.WORLD_STATE_UNKNOWN,
            ),
            GoalOpportunity(
                "heal",
                GoalKind.RESTORE_TEAM,
                GoalAvailability.AVAILABLE,
                estimated_effort=0.1,
                estimated_risk=0.0,
            ),
        ),
    )

    assert question.available_indices == (1,)
    with pytest.raises(GoalManagerError, match="unavailable"):
        bind_goal_selection(question, 0)
    assert bind_goal_selection(question, 1).binding_ref == "heal"


def test_goal_manager_refuses_two_destinations_disguised_as_two_goals() -> None:
    duplicate_story_options = (
        GoalOpportunity(
            "first-story-destination",
            GoalKind.ADVANCE_STORY,
            GoalAvailability.AVAILABLE,
            estimated_effort=0.2,
            estimated_risk=0.1,
        ),
        GoalOpportunity(
            "second-story-destination",
            GoalKind.ADVANCE_STORY,
            GoalAvailability.AVAILABLE,
            estimated_effort=0.3,
            estimated_risk=0.1,
        ),
    )

    with pytest.raises(GoalManagerError, match="one option per kind"):
        GoalManagerQuestion(
            _situation(GoalKind.ADVANCE_STORY),
            duplicate_story_options,
        )


def test_failed_and_interrupted_choices_never_become_imitation_targets() -> None:
    succeeded = _example(
        0,
        GoalKind.ADVANCE_STORY,
        partition="train",
        environment="pokemon.red",
    )
    failed = GoalManagerExample(
        **{
            field: getattr(succeeded, field)
            for field in (
                "decision_id",
                "episode_id",
                "decision_index",
                "root_lineage_id",
                "partition",
                "environment_id",
                "actor",
                "policy_id",
                "question",
                "selected_candidate_index",
            )
        },
        outcome_status=GoalDecisionOutcome.FAILED,
        failure_reason=GoalFailureReason.OUTCOME_NOT_VERIFIED,
    )
    interrupted = GoalManagerExample(
        **{
            field: getattr(succeeded, field)
            for field in (
                "decision_id",
                "episode_id",
                "decision_index",
                "root_lineage_id",
                "partition",
                "environment_id",
                "actor",
                "policy_id",
                "question",
                "selected_candidate_index",
            )
        },
        outcome_status=GoalDecisionOutcome.INTERRUPTED,
        failure_reason=GoalFailureReason.EXTERNAL_INTERRUPTION,
    )

    assert succeeded.teacher_choice_target == 0
    assert failed.teacher_choice_target is None
    assert interrupted.teacher_choice_target is None


def test_recorded_policy_input_round_trips_without_private_bindings() -> None:
    original = GoalManagerQuestion(
        _situation(GoalKind.RESTORE_TEAM),
        _opportunities("private-title-binding"),
    )

    restored = GoalManagerQuestion.from_policy_input(original.policy_input)

    assert restored.policy_input == original.policy_input
    assert all(
        item.binding_ref.startswith("recorded-policy-candidate:") for item in restored.opportunities
    )
    assert not any("private-title-binding" in item.binding_ref for item in restored.opportunities)


def test_curriculum_admits_context_dependent_choices_and_held_out_title() -> None:
    kinds = (
        GoalKind.ADVANCE_STORY,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.RESTORE_TEAM,
    )
    train = tuple(
        _example(
            index,
            kind,
            partition="train",
            environment="pokemon.red",
            reverse=index % 2 == 1,
        )
        for index, kind in enumerate(kinds)
    )
    validation = tuple(
        _example(
            index,
            kind,
            partition="validation",
            environment="pokemon.crystal",
            reverse=index % 2 == 0,
        )
        for index, kind in enumerate(kinds)
    )

    audit = audit_goal_curriculum(
        train + validation,
        requirements=_small_requirements(held_out=("pokemon.crystal",)),
    )

    assert audit.ready_for_training
    assert audit.context_dependent_menu_count == 1
    assert audit.multiway_train_examples == 3
    assert audit.train_validation_context_overlap_count == 0
    assert audit.public_dict()["model_input_excludes_environment_identity"] is True


def test_curriculum_rejects_a_fixed_story_priority_and_title_leakage() -> None:
    train = tuple(
        _example(
            index,
            GoalKind.ADVANCE_STORY,
            partition="train",
            environment="pokemon.crystal" if index == 0 else "pokemon.red",
        )
        for index in range(3)
    )
    validation = tuple(
        _example(
            index,
            GoalKind.ADVANCE_STORY,
            partition="validation",
            environment="pokemon.crystal",
        )
        for index in range(3)
    )

    audit = audit_goal_curriculum(
        train + validation,
        requirements=_small_requirements(held_out=("pokemon.crystal",)),
    )

    assert not audit.ready_for_training
    assert "candidate_menus_do_not_require_context" in audit.reasons
    assert "held_out_environment_used_for_training:pokemon.crystal" in audit.reasons
    assert "insufficient_train_selected_kind:acquire_species" in audit.reasons


def test_curriculum_rejects_replayed_contexts_as_extra_training_data() -> None:
    kinds = (
        GoalKind.ADVANCE_STORY,
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.RESTORE_TEAM,
    )
    train = tuple(
        _example(
            index,
            kind,
            partition="train",
            environment="pokemon.red",
            reverse=index % 2 == 1,
        )
        for index, kind in enumerate(kinds)
    )
    replay = GoalManagerExample(
        decision_id="replayed-decision",
        episode_id="replayed-episode",
        decision_index=0,
        root_lineage_id="replayed-root",
        partition="train",
        environment_id="pokemon.red",
        actor="deterministic_teacher",
        policy_id="portable-goal-teacher-v1",
        question=train[0].question,
        selected_candidate_index=train[0].selected_candidate_index,
        outcome_status=GoalDecisionOutcome.SUCCEEDED,
    )
    validation = tuple(
        _example(
            index,
            kind,
            partition="validation",
            environment="pokemon.crystal",
        )
        for index, kind in enumerate(kinds)
    )

    audit = audit_goal_curriculum(
        train + (replay,) + validation,
        requirements=_small_requirements(),
    )

    assert not audit.ready_for_training
    assert audit.replicated_teacher_choice_example_count == 1
    assert "replicated_policy_context" in audit.reasons
