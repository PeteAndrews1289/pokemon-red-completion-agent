from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from pokemon_red_completion.bounded_player_episode import (
    BoundedPlayerError,
    BoundedPlayerStopReason,
    run_bounded_player_episode,
)
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetCheckpoint,
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_runtime import (
    CompletionFirstGoalTeacher,
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_trajectory import GoalManagerTrajectoryObserver
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
)


class _SnapshotProvider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id="pokemon.red",
            mode="overworld",
            location="pokemon.red:area:bounded-player-test",
            features={},
        )


class _Executor:
    def execute(self, action: object) -> object:
        return action


@dataclass
class _Meter:
    state: dict[str, int]

    def checkpoint(self) -> CompositionBudgetCheckpoint:
        return CompositionBudgetCheckpoint(
            controller_actions=self.state["actions"],
            emulator_frames=self.state["frames"],
        )


def _trajectory() -> tuple[GoalManagerTrajectoryObserver, InMemoryTrajectorySink]:
    sink = InMemoryTrajectorySink()
    recorder: RecordingExecutor[object, object] = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_SnapshotProvider(),
        sink=sink,
        episode_id="bounded-player-episode",
    )
    return (
        GoalManagerTrajectoryObserver(
            episode_id="bounded-player-episode",
            root_lineage_id="bounded-player-root",
            partition="development",
            environment_id="pokemon.red",
            actor="completion_first_teacher",
            policy_id="completion-first-v1",
            collection_id="bounded-player-v1",
            assignment_id="bounded-player-assignment",
            source_commit="1" * 40,
            snapshot_provider=_SnapshotProvider(),
            recorder=recorder,
            sink=sink,
        ),
        sink,
    )


def _situation(stage: int, *, repeated_failure: bool) -> GoalSituation:
    return GoalSituation(
        story_pressure=0.2,
        collection_pressure=0.2,
        team_pressure=0.2,
        evolution_pressure=0.2,
        safety_pressure=0.9 if stage == 0 or repeated_failure else 0.1,
        resource_pressure=0.1,
        storage_pressure=0.9 if stage >= 1 and not repeated_failure else 0.2,
        recovery_pressure=0.0,
        exploration_pressure=(0.1 + 0.1 * stage if repeated_failure else 0.1),
    )


def _observer(
    *,
    fail_first: bool = True,
    same_failure_context: bool = False,
    repeated_failure: bool = False,
    regress_collection: bool = False,
    unchanged_success: bool = False,
    mismatched_report: bool = False,
    interrupt: bool = False,
    observer_acts: bool = False,
    no_goals_after_first: bool = False,
):
    state = {"stage": 0, "actions": 0, "frames": 0, "observations": 0}

    def observe() -> GoalManagerCompositionObservation:
        state["observations"] += 1
        if observer_acts:
            state["actions"] += 1
        stage = state["stage"]
        policy_stage = 0 if same_failure_context and stage == 1 else stage
        available = (
            set()
            if no_goals_after_first and stage >= 1
            else
            {GoalKind.RESTORE_TEAM, GoalKind.MANAGE_STORAGE, GoalKind.ADVANCE_STORY}
            if policy_stage == 0 or repeated_failure
            else {GoalKind.MANAGE_STORAGE, GoalKind.ADVANCE_STORY}
        )
        opportunities = tuple(
            GoalOpportunity(
                binding_ref=f"private:red:{kind.value}",
                kind=kind,
                availability=(
                    GoalAvailability.AVAILABLE
                    if kind in available
                    else GoalAvailability.UNAVAILABLE
                ),
                estimated_effort=0.2 if kind in available else None,
                estimated_risk=0.1 if kind in available else None,
                unavailable_reason=(
                    None
                    if kind in available
                    else GoalUnavailableReason.NO_LEGAL_TARGET
                ),
            )
            for kind in GoalKind
        )

        def binding(kind: GoalKind) -> ExecutableGoalBinding:
            def execute() -> GoalExecutionReport:
                before = state["stage"]
                state["actions"] += 5
                state["frames"] += 50
                if interrupt:
                    raise KeyboardInterrupt
                if not unchanged_success:
                    state["stage"] += 1
                return GoalExecutionReport(
                    4 if mismatched_report else 5,
                    50,
                    {"fail": fail_first and before == 0},
                )

            def verify(report: GoalExecutionReport) -> GoalVerification:
                if report.evidence["fail"]:
                    return GoalVerification.failed(
                        GoalFailureReason.OUTCOME_NOT_VERIFIED
                    )
                return GoalVerification.succeeded()

            return ExecutableGoalBinding(
                binding_ref=f"private:red:{kind.value}",
                kind=kind,
                estimated_effort=0.2,
                estimated_risk=0.1,
                execute=execute,
                verify=verify,
            )

        living = 9 if regress_collection and stage >= 1 else 10
        return GoalManagerCompositionObservation(
            semantic_state_sha256=f"{stage + 1:064x}",
            situation=_situation(policy_stage, repeated_failure=repeated_failure),
            binding_set=GoalBindingSet(
                opportunities,
                tuple(binding(kind) for kind in GoalKind if kind in available),
            ),
            collection=LivingCollectionCheckpoint(
                registered_species=10,
                living_species=living,
                required_specimens_remaining=5,
                retained_captures=0,
                storage_headroom=9 if stage >= 2 else 1,
                undeclared_specimen_losses=0,
                completion_contract_sha256="1" * 64,
                specimen_ledger_sha256="2" * 64,
                required_specimens_sha256="3" * 64,
                specimen_counts=(("pokemon:red:living:starter", 10),),
            ),
        )

    return observe, _Meter(state), state


def _complete(observation: GoalManagerCompositionObservation) -> bool:
    return observation.collection.storage_headroom >= 9


def test_verified_failure_reobserves_and_replans_to_a_different_goal() -> None:
    trajectory, sink = _trajectory()
    observe, meter, state = _observer()

    result = run_bounded_player_episode(
        observe=observe,
        authority=CompletionFirstGoalTeacher(),
        authority_id="completion-first-v1",
        trajectory=trajectory,
        budget_meter=meter,
        completion_satisfied=_complete,
    )

    assert result.stop_reason is BoundedPlayerStopReason.COMPLETION_REACHED
    assert result.completion_satisfied is True
    assert [step.selected_kind for step in result.steps] == [
        GoalKind.RESTORE_TEAM,
        GoalKind.MANAGE_STORAGE,
    ]
    assert [step.status.value for step in result.steps] == ["failed", "succeeded"]
    assert [step.recovery_attempt for step in result.steps] == [False, True]
    assert state["observations"] == 3
    assert len(sink.decisions) == 2
    assert len(sink.events) == 2
    public = json.dumps(result.public_dict(), sort_keys=True)
    assert "private:red" not in public
    assert "bounded-player-root" not in public


def test_unchanged_failed_context_stops_without_repeating_input() -> None:
    trajectory, sink = _trajectory()
    observe, meter, state = _observer(same_failure_context=True)

    result = run_bounded_player_episode(
        observe=observe,
        authority=CompletionFirstGoalTeacher(),
        authority_id="completion-first-v1",
        trajectory=trajectory,
        budget_meter=meter,
        completion_satisfied=_complete,
    )

    assert result.stop_reason is BoundedPlayerStopReason.FAILURE_CONTEXT_UNCHANGED
    assert len(result.steps) == 1
    assert state["actions"] == 5
    assert len(sink.decisions) == len(sink.events) == 1


def test_successful_step_can_settle_before_an_unavailable_followup_menu() -> None:
    trajectory, sink = _trajectory()
    observe, meter, state = _observer(
        fail_first=False,
        no_goals_after_first=True,
    )

    result = run_bounded_player_episode(
        observe=observe,
        authority=CompletionFirstGoalTeacher(),
        authority_id="completion-first-v1",
        trajectory=trajectory,
        budget_meter=meter,
        completion_satisfied=_complete,
    )

    assert (
        result.stop_reason
        is BoundedPlayerStopReason.INSUFFICIENT_AVAILABLE_GOALS
    )
    assert len(result.steps) == 1
    assert result.steps[0].status.value == "succeeded"
    assert state["actions"] == 5
    assert len(sink.decisions) == len(sink.events) == 1
    trajectory.require_settled()


def test_recovery_cannot_repeat_the_failed_semantic_goal() -> None:
    trajectory, _sink = _trajectory()
    observe, meter, _state = _observer(repeated_failure=True)

    with pytest.raises(BoundedPlayerError, match="repeated the failed goal"):
        run_bounded_player_episode(
            observe=observe,
            authority=CompletionFirstGoalTeacher(),
            authority_id="completion-first-v1",
            trajectory=trajectory,
            budget_meter=meter,
            completion_satisfied=_complete,
        )


def test_collection_regression_is_rejected_after_fresh_observation() -> None:
    trajectory, _sink = _trajectory()
    observe, meter, _state = _observer(regress_collection=True)

    with pytest.raises(BoundedPlayerError, match="collection state regressed"):
        run_bounded_player_episode(
            observe=observe,
            authority=CompletionFirstGoalTeacher(),
            authority_id="completion-first-v1",
            trajectory=trajectory,
            budget_meter=meter,
            completion_satisfied=_complete,
        )


def test_success_requires_changed_semantic_state() -> None:
    trajectory, _sink = _trajectory()
    observe, meter, _state = _observer(fail_first=False, unchanged_success=True)

    with pytest.raises(BoundedPlayerError, match="did not change semantic state"):
        run_bounded_player_episode(
            observe=observe,
            authority=CompletionFirstGoalTeacher(),
            authority_id="completion-first-v1",
            trajectory=trajectory,
            budget_meter=meter,
            completion_satisfied=_complete,
        )


def test_self_report_must_match_independent_budget_meter() -> None:
    trajectory, _sink = _trajectory()
    observe, meter, _state = _observer(mismatched_report=True)

    with pytest.raises(BoundedPlayerError, match="independent budget"):
        run_bounded_player_episode(
            observe=observe,
            authority=CompletionFirstGoalTeacher(),
            authority_id="completion-first-v1",
            trajectory=trajectory,
            budget_meter=meter,
            completion_satisfied=_complete,
        )


def test_observation_may_not_hide_controller_input() -> None:
    trajectory, sink = _trajectory()
    observe, meter, _state = _observer(observer_acts=True)

    with pytest.raises(BoundedPlayerError, match="observation attempted emulator work"):
        run_bounded_player_episode(
            observe=observe,
            authority=CompletionFirstGoalTeacher(),
            authority_id="completion-first-v1",
            trajectory=trajectory,
            budget_meter=meter,
            completion_satisfied=_complete,
        )
    assert not sink.decisions


def test_external_interruption_is_recorded_then_propagated() -> None:
    trajectory, sink = _trajectory()
    observe, meter, _state = _observer(interrupt=True)

    with pytest.raises(KeyboardInterrupt):
        run_bounded_player_episode(
            observe=observe,
            authority=CompletionFirstGoalTeacher(),
            authority_id="completion-first-v1",
            trajectory=trajectory,
            budget_meter=meter,
            completion_satisfied=_complete,
        )

    assert len(sink.decisions) == len(sink.events) == 1
    assert sink.events[0].payload["status"] == "interrupted"
    assert sink.events[0].payload["failure_reason"] == "external_interruption"
    trajectory.require_settled()


def test_public_authority_identity_cannot_embed_a_path() -> None:
    trajectory, sink = _trajectory()
    observe, meter, _state = _observer()

    with pytest.raises(BoundedPlayerError, match="path-free"):
        run_bounded_player_episode(
            observe=observe,
            authority=CompletionFirstGoalTeacher(),
            authority_id="/private/model.bin",
            trajectory=trajectory,
            budget_meter=meter,
            completion_satisfied=_complete,
        )
    assert not sink.decisions
