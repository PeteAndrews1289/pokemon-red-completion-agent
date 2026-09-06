from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from pokemon_red_completion.bounded_player_episode import (
    BoundedPlayerError,
    BoundedPlayerLimits,
    BoundedPlayerStopReason,
    run_bounded_player_episode,
)
from pokemon_red_completion.executor import GoalExecutionBudgetExhausted
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalFailureReason,
    GoalKind,
    GoalOpportunity,
    GoalSelectionMode,
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
class _CountingAuthority:
    calls: int = 0

    def select(self, question):  # type: ignore[no-untyped-def]
        self.calls += 1
        return CompletionFirstGoalTeacher().select(question)


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
    exhaust_budget: bool = False,
    singleton_after_first: bool = False,
    binding_failure: bool = False,
):
    state = {"stage": 0, "actions": 0, "frames": 0, "observations": 0}

    def observe() -> GoalManagerCompositionObservation:
        state["observations"] += 1
        if observer_acts:
            state["actions"] += 1
        stage = state["stage"]
        policy_stage = 0 if same_failure_context and stage == 1 else stage
        if no_goals_after_first and stage >= 1:
            available = set()
        elif singleton_after_first and stage >= 1:
            available = {GoalKind.MANAGE_STORAGE}
        elif policy_stage == 0 or repeated_failure:
            available = {
                GoalKind.RESTORE_TEAM,
                GoalKind.MANAGE_STORAGE,
                GoalKind.ADVANCE_STORY,
            }
        else:
            available = {GoalKind.MANAGE_STORAGE, GoalKind.ADVANCE_STORY}
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
                if exhaust_budget:
                    state["stage"] += 1
                    raise GoalExecutionBudgetExhausted("private budget detail")
                if binding_failure and before == 0:
                    state["stage"] += 1
                    raise RuntimeError("private binding detail")
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


def test_single_available_followup_is_a_forced_bridge_not_model_authority() -> None:
    trajectory, sink = _trajectory()
    observe, meter, state = _observer(
        fail_first=False,
        singleton_after_first=True,
    )
    authority = _CountingAuthority()

    result = run_bounded_player_episode(
        observe=observe,
        authority=authority,
        authority_id="learned-goal-manager",
        trajectory=trajectory,
        budget_meter=meter,
        completion_satisfied=_complete,
    )

    assert result.stop_reason is BoundedPlayerStopReason.COMPLETION_REACHED
    assert authority.calls == 1
    assert result.authority_decisions == 1
    assert result.forced_singleton_steps == 1
    assert [step.selection_mode for step in result.steps] == [
        GoalSelectionMode.AUTHORITY,
        GoalSelectionMode.FORCED_SINGLETON,
    ]
    assert state["actions"] == 10
    assert len(sink.decisions) == len(sink.events) == 2
    assert [
        decision.context.metadata["selection_mode"]
        for decision in sink.decisions
    ] == ["authority", "forced_singleton"]


def test_recovery_cannot_repeat_the_failed_semantic_goal() -> None:
    trajectory, sink = _trajectory()
    observe, meter, state = _observer(repeated_failure=True)

    result = run_bounded_player_episode(
        observe=observe,
        authority=CompletionFirstGoalTeacher(),
        authority_id="completion-first-v1",
        trajectory=trajectory,
        budget_meter=meter,
        completion_satisfied=_complete,
    )
    assert result.stop_reason is BoundedPlayerStopReason.RECOVERY_GOAL_REPEATED
    assert not result.completion_satisfied
    assert len(result.steps) == len(sink.decisions) == len(sink.events) == 1
    assert result.steps[0].failure_reason is GoalFailureReason.OUTCOME_NOT_VERIFIED
    assert result.steps[0].semantic_state_changed
    assert result.steps[0].collection_after == observe().collection
    assert result.recovery_attempts == 0
    assert (state["actions"], state["frames"]) == (5, 50)
    trajectory.require_settled()


def test_rejected_recovery_must_not_hide_authority_side_effects() -> None:
    trajectory, _sink = _trajectory()
    observe, meter, state = _observer(repeated_failure=True)

    class ActingAuthority:
        def select(self, question):
            if state["stage"]:
                state["actions"] += 1
            return CompletionFirstGoalTeacher().select(question)

    with pytest.raises(BoundedPlayerError, match="rejected recovery selection changed state"):
        run_bounded_player_episode(
            observe=observe,
            authority=ActingAuthority(),
            authority_id="completion-first-v1",
            trajectory=trajectory,
            budget_meter=meter,
            completion_satisfied=_complete,
        )


def test_unrelated_authority_failure_is_not_a_safe_recovery_stop() -> None:
    trajectory, _sink = _trajectory()
    observe, meter, _state = _observer(repeated_failure=True)

    class BrokenAuthority:
        def select(self, question):
            raise BoundedPlayerError("unrelated selection defect")

    with pytest.raises(BoundedPlayerError, match="unrelated selection defect"):
        run_bounded_player_episode(
            observe=observe, authority=BrokenAuthority(), authority_id="broken",
            trajectory=trajectory, budget_meter=meter, completion_satisfied=_complete,
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


def test_budget_exhaustion_is_a_durable_verified_failure() -> None:
    trajectory, sink = _trajectory()
    observe, meter, state = _observer(exhaust_budget=True)
    failures: list[BaseException] = []

    result = run_bounded_player_episode(
        observe=observe,
        authority=CompletionFirstGoalTeacher(),
        authority_id="completion-first-v1",
        trajectory=trajectory,
        budget_meter=meter,
        completion_satisfied=_complete,
        limits=BoundedPlayerLimits(max_decisions=1, max_replans=0),
        failure_observer=failures.append,
    )

    assert result.stop_reason is BoundedPlayerStopReason.VERIFIED_FAILURE
    assert len(result.steps) == 1
    assert result.steps[0].failure_reason is (
        GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    )
    assert result.steps[0].actions_executed == 5
    assert result.steps[0].frames_executed == 50
    assert state["actions"] == 5
    assert len(sink.decisions) == len(sink.events) == 1
    trajectory.require_settled()
    assert len(failures) == 1
    assert isinstance(failures[0], GoalExecutionBudgetExhausted)
    assert str(failures[0]) == "private budget detail"


def test_binding_exception_is_retained_and_replanned_without_private_detail() -> None:
    trajectory, sink = _trajectory()
    observe, meter, state = _observer(binding_failure=True)
    failures: list[BaseException] = []

    result = run_bounded_player_episode(
        observe=observe,
        authority=CompletionFirstGoalTeacher(),
        authority_id="completion-first-v1",
        trajectory=trajectory,
        budget_meter=meter,
        completion_satisfied=_complete,
        failure_observer=failures.append,
    )

    assert result.stop_reason is BoundedPlayerStopReason.COMPLETION_REACHED
    assert [step.failure_reason for step in result.steps] == [
        GoalFailureReason.BINDING_FAILED,
        None,
    ]
    assert [step.recovery_attempt for step in result.steps] == [False, True]
    assert state["actions"] == 10
    assert len(sink.decisions) == len(sink.events) == 2
    assert "private binding detail" not in json.dumps(result.public_dict())
    assert len(failures) == 1
    assert isinstance(failures[0], RuntimeError)
    assert str(failures[0]) == "private binding detail"


@pytest.mark.parametrize("diagnostic_acts", (False, True))
def test_diagnostic_failure_or_hidden_action_stops_before_recovery(
    diagnostic_acts: bool,
) -> None:
    trajectory, sink = _trajectory()
    observe, meter, state = _observer(binding_failure=True)

    def retain(error: BaseException) -> None:
        assert str(error) == "private binding detail"
        if diagnostic_acts:
            state["actions"] += 1
        else:
            raise OSError("private journal unavailable")

    expected = BoundedPlayerError if diagnostic_acts else OSError
    with pytest.raises(expected):
        run_bounded_player_episode(
            observe=observe,
            authority=CompletionFirstGoalTeacher(),
            authority_id="completion-first-v1",
            trajectory=trajectory,
            budget_meter=meter,
            completion_satisfied=_complete,
            failure_observer=retain,
        )
    assert state["actions"] == 5 + int(diagnostic_acts)
    assert len(sink.decisions) == 1


def test_diagnostic_observer_must_be_callable_before_gameplay() -> None:
    trajectory, _ = _trajectory()
    observe, meter, state = _observer()
    with pytest.raises(TypeError, match="failure_observer"):
        run_bounded_player_episode(
            observe=observe,
            authority=CompletionFirstGoalTeacher(),
            authority_id="completion-first-v1",
            trajectory=trajectory,
            budget_meter=meter,
            completion_satisfied=_complete,
            failure_observer="not-callable",  # type: ignore[arg-type]
        )
    assert state["actions"] == 0


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
