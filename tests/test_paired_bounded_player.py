from __future__ import annotations

import json

import pytest

from pokemon_red_completion.bounded_player_episode import (
    BoundedPlayerResult,
    BoundedPlayerStep,
    BoundedPlayerStopReason,
)
from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.paired_bounded_player import (
    PairedBoundedPlayerArm,
    PairedBoundedPlayerError,
    PairedBoundedPlayerVerdict,
    compare_paired_bounded_player_arms,
)


def _collection(
    *,
    registered: int = 10,
    living: int = 10,
    remaining: int = 5,
    retained: int = 3,
    storage: int = 2,
    ledger: str = "2",
    required: str = "3",
) -> LivingCollectionCheckpoint:
    return LivingCollectionCheckpoint(
        registered_species=registered,
        living_species=living,
        required_specimens_remaining=remaining,
        retained_captures=retained,
        storage_headroom=storage,
        undeclared_specimen_losses=0,
        completion_contract_sha256="1" * 64,
        specimen_ledger_sha256=ledger * 64,
        required_specimens_sha256=required * 64,
        specimen_counts=(("pokemon:red:living:starter", living),),
    )


def _arm(
    arm_id: str,
    *,
    initial: LivingCollectionCheckpoint | None = None,
    final: LivingCollectionCheckpoint | None = None,
    actions: int = 5,
    frames: int = 50,
    recovery: bool = False,
    completion: bool = False,
    manifest: str = "6",
    selected_kind: GoalKind = GoalKind.MANAGE_STORAGE,
    status: GoalDecisionOutcome = GoalDecisionOutcome.SUCCEEDED,
) -> PairedBoundedPlayerArm:
    initial = initial or _collection()
    final = final or initial
    step = BoundedPlayerStep(
        decision_ordinal=1,
        selected_kind=selected_kind,
        status=status,
        failure_reason=(
            None
            if status is GoalDecisionOutcome.SUCCEEDED
            else GoalFailureReason.OUTCOME_NOT_VERIFIED
        ),
        recovery_attempt=recovery,
        available_goal_count=3,
        actions_executed=actions,
        frames_executed=frames,
        semantic_state_changed=True,
        policy_context_sha256="4" * 64,
        available_menu_sha256="5" * 64,
        collection_before=initial,
        collection_after=final,
    )
    return PairedBoundedPlayerArm(
        arm_id=arm_id,
        starting_state_sha256="7" * 64,
        starting_semantic_state_sha256="8" * 64,
        starting_collection=initial,
        trajectory_manifest_sha256=manifest * 64,
        episode=BoundedPlayerResult(
            authority_id=arm_id,
            stop_reason=(
                BoundedPlayerStopReason.COMPLETION_REACHED
                if completion
                else (
                    BoundedPlayerStopReason.VERIFIED_FAILURE
                    if status is GoalDecisionOutcome.FAILED
                    else BoundedPlayerStopReason.DECISION_LIMIT
                )
            ),
            steps=(step,),
            completion_satisfied=completion,
        ),
    )


def test_verified_progress_dominates_lower_cost() -> None:
    initial = _collection()
    learned = _arm(
        "learned-goal-manager",
        initial=initial,
        final=_collection(remaining=4, retained=4, ledger="9", required="a"),
        actions=20,
        frames=200,
        completion=True,
        selected_kind=GoalKind.ACQUIRE_SPECIES,
    )
    baseline = _arm(
        "completion-first-teacher",
        initial=initial,
        actions=1,
        frames=10,
        selected_kind=GoalKind.ACQUIRE_SPECIES,
        status=GoalDecisionOutcome.FAILED,
    )

    result = compare_paired_bounded_player_arms(
        pair_id="red-pair-001",
        learned=learned,
        baseline=baseline,
    )

    assert result.verdict is PairedBoundedPlayerVerdict.LEARNED_ADVANTAGE
    assert result.decision_basis == "verified_progress_dominance"


def test_cost_breaks_a_tie_only_after_equal_progress() -> None:
    learned = _arm("learned-goal-manager", actions=4, frames=40)
    baseline = _arm("completion-first-teacher", actions=5, frames=50)

    result = compare_paired_bounded_player_arms(
        pair_id="red-pair-002",
        learned=learned,
        baseline=baseline,
    )

    assert result.verdict is PairedBoundedPlayerVerdict.LEARNED_ADVANTAGE
    assert result.decision_basis == "equal_progress_lower_cost"


def test_equal_progress_with_mixed_cost_is_incomparable() -> None:
    learned = _arm("learned-goal-manager", actions=4, frames=60)
    baseline = _arm("completion-first-teacher", actions=5, frames=50)

    result = compare_paired_bounded_player_arms(
        pair_id="red-pair-002b",
        learned=learned,
        baseline=baseline,
    )

    assert result.verdict is PairedBoundedPlayerVerdict.INCOMPARABLE
    assert result.decision_basis == "equal_progress_mixed_cost_tradeoff"


def test_mixed_progress_is_incomparable_instead_of_scalarized() -> None:
    initial = _collection()
    learned = _arm(
        "learned-goal-manager",
        initial=initial,
        final=_collection(registered=11, living=11, ledger="9", required="a"),
        selected_kind=GoalKind.ACQUIRE_SPECIES,
    )
    baseline = _arm(
        "completion-first-teacher",
        initial=initial,
        final=_collection(storage=3),
    )

    result = compare_paired_bounded_player_arms(
        pair_id="red-pair-003",
        learned=learned,
        baseline=baseline,
    )

    assert result.verdict is PairedBoundedPlayerVerdict.INCOMPARABLE
    assert result.decision_basis == "mixed_verified_progress_tradeoff"


def test_different_successful_goal_kinds_are_not_treated_as_equal_progress() -> None:
    learned = _arm("learned-goal-manager", selected_kind=GoalKind.ADVANCE_STORY)
    baseline = _arm(
        "completion-first-teacher",
        selected_kind=GoalKind.RESTORE_TEAM,
    )

    result = compare_paired_bounded_player_arms(
        pair_id="red-pair-003b",
        learned=learned,
        baseline=baseline,
    )

    assert result.verdict is PairedBoundedPlayerVerdict.INCOMPARABLE
    assert result.decision_basis == "mixed_verified_progress_tradeoff"


def test_pair_rejects_different_starting_state() -> None:
    learned = _arm("learned-goal-manager")
    baseline = _arm("completion-first-teacher")
    baseline = PairedBoundedPlayerArm(
        arm_id=baseline.arm_id,
        starting_state_sha256="b" * 64,
        starting_semantic_state_sha256=baseline.starting_semantic_state_sha256,
        starting_collection=baseline.starting_collection,
        trajectory_manifest_sha256=baseline.trajectory_manifest_sha256,
        episode=baseline.episode,
    )

    with pytest.raises(PairedBoundedPlayerError, match="same state"):
        compare_paired_bounded_player_arms(
            pair_id="red-pair-004",
            learned=learned,
            baseline=baseline,
        )


def test_pair_rejects_different_starting_semantic_state() -> None:
    learned = _arm("learned-goal-manager")
    baseline = _arm("completion-first-teacher")
    baseline = PairedBoundedPlayerArm(
        arm_id=baseline.arm_id,
        starting_state_sha256=baseline.starting_state_sha256,
        starting_semantic_state_sha256="b" * 64,
        starting_collection=baseline.starting_collection,
        trajectory_manifest_sha256=baseline.trajectory_manifest_sha256,
        episode=baseline.episode,
    )

    with pytest.raises(PairedBoundedPlayerError, match="same state"):
        compare_paired_bounded_player_arms(
            pair_id="red-pair-004b",
            learned=learned,
            baseline=baseline,
        )


def test_arm_rejects_episode_from_another_authority() -> None:
    episode = _arm("completion-first-teacher").episode

    with pytest.raises(PairedBoundedPlayerError, match="authority identity"):
        PairedBoundedPlayerArm(
            arm_id="learned-goal-manager",
            starting_state_sha256="7" * 64,
            starting_semantic_state_sha256="8" * 64,
            starting_collection=episode.steps[0].collection_before,
            trajectory_manifest_sha256="9" * 64,
            episode=episode,
        )


def test_arm_rejects_a_broken_collection_chain() -> None:
    initial = _collection()
    arm = _arm("learned-goal-manager")
    first = arm.episode.steps[0]
    second = BoundedPlayerStep(
        decision_ordinal=2,
        selected_kind=GoalKind.RESTORE_TEAM,
        status=GoalDecisionOutcome.SUCCEEDED,
        failure_reason=None,
        recovery_attempt=False,
        available_goal_count=3,
        actions_executed=1,
        frames_executed=10,
        semantic_state_changed=True,
        policy_context_sha256="a" * 64,
        available_menu_sha256="b" * 64,
        collection_before=_collection(storage=3),
        collection_after=_collection(storage=3),
    )

    with pytest.raises(PairedBoundedPlayerError, match="collection chain"):
        PairedBoundedPlayerArm(
            arm_id=arm.arm_id,
            starting_state_sha256=arm.starting_state_sha256,
            starting_semantic_state_sha256=arm.starting_semantic_state_sha256,
            starting_collection=initial,
            trajectory_manifest_sha256=arm.trajectory_manifest_sha256,
            episode=BoundedPlayerResult(
                authority_id=arm.arm_id,
                stop_reason=BoundedPlayerStopReason.DECISION_LIMIT,
                steps=(first, second),
                completion_satisfied=False,
            ),
        )


def test_arm_rejects_negative_cost_and_inconsistent_terminal() -> None:
    arm = _arm("learned-goal-manager")
    step = arm.episode.steps[0]
    negative = BoundedPlayerStep(
        decision_ordinal=step.decision_ordinal,
        selected_kind=step.selected_kind,
        status=step.status,
        failure_reason=step.failure_reason,
        recovery_attempt=step.recovery_attempt,
        available_goal_count=step.available_goal_count,
        actions_executed=-1,
        frames_executed=step.frames_executed,
        semantic_state_changed=step.semantic_state_changed,
        policy_context_sha256=step.policy_context_sha256,
        available_menu_sha256=step.available_menu_sha256,
        collection_before=step.collection_before,
        collection_after=step.collection_after,
    )
    with pytest.raises(PairedBoundedPlayerError, match="cost counters"):
        PairedBoundedPlayerArm(
            arm_id=arm.arm_id,
            starting_state_sha256=arm.starting_state_sha256,
            starting_semantic_state_sha256=arm.starting_semantic_state_sha256,
            starting_collection=arm.starting_collection,
            trajectory_manifest_sha256=arm.trajectory_manifest_sha256,
            episode=BoundedPlayerResult(
                authority_id=arm.arm_id,
                stop_reason=BoundedPlayerStopReason.DECISION_LIMIT,
                steps=(negative,),
                completion_satisfied=False,
            ),
        )

    with pytest.raises(PairedBoundedPlayerError, match="terminal state"):
        PairedBoundedPlayerArm(
            arm_id=arm.arm_id,
            starting_state_sha256=arm.starting_state_sha256,
            starting_semantic_state_sha256=arm.starting_semantic_state_sha256,
            starting_collection=arm.starting_collection,
            trajectory_manifest_sha256=arm.trajectory_manifest_sha256,
            episode=BoundedPlayerResult(
                authority_id=arm.arm_id,
                stop_reason=BoundedPlayerStopReason.COMPLETION_REACHED,
                steps=arm.episode.steps,
                completion_satisfied=False,
            ),
        )


def test_public_result_is_path_free_and_preserves_both_episode_results() -> None:
    learned = _arm("learned-goal-manager", manifest="c")
    baseline = _arm("completion-first-teacher", manifest="d")
    result = compare_paired_bounded_player_arms(
        pair_id="red-pair-005",
        learned=learned,
        baseline=baseline,
    )

    encoded = json.dumps(result.public_dict(), sort_keys=True)
    assert result.verdict is PairedBoundedPlayerVerdict.EQUIVALENT
    assert '"private_path_fields": 0' in encoded
    assert "/private/" not in encoded
    assert '"authority_id": "learned-goal-manager"' in encoded
    assert '"authority_id": "completion-first-teacher"' in encoded
