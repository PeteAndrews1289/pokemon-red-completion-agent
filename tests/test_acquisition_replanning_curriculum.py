from __future__ import annotations

import pytest

from pokemon_red_completion.acquisition_replanning_curriculum import (
    ACQUISITION_REPLANNING_EPISODES,
    AcquisitionReplanningCurriculumError,
    AcquisitionReplanningInventory,
    acquisition_replanning_behavior_contract,
    acquisition_replanning_design_record,
    acquisition_replanning_evidence_contract,
    assess_acquisition_replanning_episode,
)
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_composition_runtime import (
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_development import (
    GoalManagerDevelopmentResult,
    GoalManagerDevelopmentStep,
)


def _collection(*, remaining: int, captures: int, specimens: int) -> LivingCollectionCheckpoint:
    return LivingCollectionCheckpoint(
        registered_species=specimens,
        living_species=specimens,
        required_specimens_remaining=remaining,
        retained_captures=captures,
        storage_headroom=10,
        undeclared_specimen_losses=0,
        completion_contract_sha256="a" * 64,
        specimen_ledger_sha256=f"{specimens:064x}",
        required_specimens_sha256=f"{remaining:064x}",
        specimen_counts=((f"pokemon:national:{specimens:03d}", specimens),),
    )


def _step(
    ordinal: int,
    kind: GoalKind,
    before: LivingCollectionCheckpoint,
    after: LivingCollectionCheckpoint,
    *,
    menu: str,
) -> GoalManagerDevelopmentStep:
    return GoalManagerDevelopmentStep(
        decision_ordinal=ordinal,
        selected_kind=kind,
        status=GoalDecisionOutcome.SUCCEEDED,
        behavior_probability=0.5,
        base_probability=0.5,
        available_goal_count=3,
        actions_executed=10,
        frames_executed=100,
        semantic_state_changed=True,
        policy_context_sha256=("b" if ordinal == 1 else "c") * 64,
        available_menu_sha256=menu * 64,
        collection_before=before,
        collection_after=after,
    )


def _current_inventory() -> AcquisitionReplanningInventory:
    return AcquisitionReplanningInventory(
        acquisition_train_roots=6,
        previously_used_roots=2,
        unused_roots=4,
        unused_roots_with_multiple_initial_choices=4,
        authenticated_post_acquisition_captures=0,
        prior_durable_post_acquisition_choice_count=1,
    )


def test_current_inventory_fails_only_the_post_acquisition_boundary() -> None:
    inventory = _current_inventory()

    assert inventory.existing_contexts_support_execution is False
    assert inventory.public_dict() == {
        "schema": "pokemon.core.acquisition-replanning-inventory.v1",
        "status": "existing_contexts_insufficient",
        "acquisition_train_roots": 6,
        "previously_used_roots": 2,
        "unused_roots": 4,
        "unused_roots_with_multiple_initial_choices": 4,
        "authenticated_post_acquisition_captures": 0,
        "prior_durable_post_acquisition_choice_count": 1,
        "model_predictions": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "outcomes_added": 0,
    }


def test_inventory_requires_an_exact_root_denominator() -> None:
    with pytest.raises(AcquisitionReplanningCurriculumError, match="denominator"):
        AcquisitionReplanningInventory(
            acquisition_train_roots=6,
            previously_used_roots=1,
            unused_roots=4,
            unused_roots_with_multiple_initial_choices=4,
            authenticated_post_acquisition_captures=0,
            prior_durable_post_acquisition_choice_count=1,
        )


def test_behavior_is_balanced_repeatable_and_teacher_free() -> None:
    behavior = acquisition_replanning_behavior_contract()

    assert behavior["planned_episodes"] == ACQUISITION_REPLANNING_EPISODES == 16
    assert behavior["first_decision_schedule_per_root"] == [
        "acquire_species",
        "acquire_species",
        "develop_team",
        "explore",
    ]
    assert behavior["first_decision_schedule_scope"] == "per_trial_within_each_root"
    acquisition_trials_per_root = behavior["first_decision_schedule_per_root"].count(
        "acquire_species"
    )
    acquisition_first_roots = (
        behavior["root_lineages"] if acquisition_trials_per_root else 0
    )
    assert acquisition_first_roots >= 3
    assert behavior["maximum_controller_started_decisions_per_episode"] == 2
    assert behavior["learned_choice_decisions_after_intervention"] == 1
    assert behavior["first_decision_is_model_prediction"] is False
    assert behavior["minimum_initial_executable_choices"] == 3
    assert behavior["minimum_post_acquisition_executable_choices"] == 2
    assert behavior["retain_all_claimed_failures"] is True
    assert behavior["replacement_or_retry_allowed"] is False
    assert behavior["teacher_queries"] == 0


def test_evidence_gate_is_descriptive_and_requires_cross_root_replanning() -> None:
    gate = acquisition_replanning_evidence_contract()

    assert gate["minimum_admitted_acquisition_first_episodes"] == 4
    assert gate["minimum_verified_distinct_goal_replans"] == 4
    assert gate["minimum_root_lineages_with_verified_replan"] == 3
    assert gate["fit_partition"] == "train_only"
    assert gate["unseen_comparison"] is False
    assert gate["authority_promotion"] is False
    assert gate["transfer_claim"] is False


def test_design_record_is_path_free_and_execution_closed() -> None:
    record = acquisition_replanning_design_record(_current_inventory())
    encoded = str(record)

    assert len(record["design_sha256"]) == 64
    assert record["capability_gap"]["execution_authorized"] is False
    assert record["zero_effects"] == {
        "model_predictions": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "episode_attempts": 0,
        "verified_outcomes": 0,
        "model_fits": 0,
        "unseen_comparisons": 0,
        "authority_promotions": 0,
        "transfer_results": 0,
    }
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_episode_assessment_requires_real_acquisition_then_distinct_replan() -> None:
    before = _collection(remaining=10, captures=2, specimens=2)
    acquired = _collection(remaining=9, captures=3, specimens=3)
    result = GoalManagerDevelopmentResult(
        model_sha256="d" * 64,
        seed=1,
        steps=(
            _step(1, GoalKind.ACQUIRE_SPECIES, before, acquired, menu="1"),
            _step(2, GoalKind.DEVELOP_TEAM, acquired, acquired, menu="2"),
        ),
        policy_context_changes=1,
        available_menu_changes=1,
        stopped_reason="decision_limit",
    )

    assessment = assess_acquisition_replanning_episode(result)

    assert assessment.qualifies is True
    assert assessment.reasons == ()


def test_episode_assessment_rejects_repeated_acquisition_without_replanning() -> None:
    before = _collection(remaining=10, captures=2, specimens=2)
    acquired = _collection(remaining=9, captures=3, specimens=3)
    result = GoalManagerDevelopmentResult(
        model_sha256="d" * 64,
        seed=1,
        steps=(
            _step(1, GoalKind.ACQUIRE_SPECIES, before, acquired, menu="1"),
            _step(2, GoalKind.ACQUIRE_SPECIES, acquired, acquired, menu="2"),
        ),
        policy_context_changes=1,
        available_menu_changes=1,
        stopped_reason="decision_limit",
    )

    assessment = assess_acquisition_replanning_episode(result)

    assert assessment.qualifies is False
    assert assessment.reasons == ("second_goal_did_not_change",)
