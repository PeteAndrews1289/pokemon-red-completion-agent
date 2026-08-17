from __future__ import annotations

import json

import pytest

from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSituation,
)
from pokemon_red_completion.goal_manager_runtime import (
    CompletionFirstGoalTeacher,
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalExecutionReport,
    GoalManagerRuntimeError,
    GoalVerification,
    execute_goal_manager_decision,
)
from pokemon_red_completion.goal_manager_trajectory import (
    GoalManagerTrajectoryError,
    GoalManagerTrajectoryObserver,
)
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
            location="pokemon.red:area:test",
            features={},
        )


class _Executor:
    def execute(self, action: object) -> object:
        return action


class _SelectKind:
    def __init__(self, kind: GoalKind) -> None:
        self.kind = kind

    def select(self, question):  # type: ignore[no-untyped-def]
        return next(
            index
            for index, opportunity in enumerate(question.opportunities)
            if opportunity.kind is self.kind
        )


def _trajectory():  # type: ignore[no-untyped-def]
    sink = InMemoryTrajectorySink()
    recorder: RecordingExecutor[object, object] = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_SnapshotProvider(),
        sink=sink,
        episode_id="goal-runtime-episode",
    )
    observer = GoalManagerTrajectoryObserver(
        episode_id="goal-runtime-episode",
        root_lineage_id="goal-runtime-root",
        partition="train",
        environment_id="pokemon.red",
        actor="deterministic_teacher",
        policy_id="portable-goal-teacher-v1",
        collection_id="portable-goal-curriculum-v1",
        assignment_id="goal-runtime-assignment",
        source_commit="1" * 40,
        snapshot_provider=_SnapshotProvider(),
        recorder=recorder,
        sink=sink,
    )
    return observer, sink


def _situation(**overrides: float) -> GoalSituation:
    values = {
        "story_pressure": 0.60,
        "collection_pressure": 0.40,
        "team_pressure": 0.30,
        "evolution_pressure": 0.20,
        "safety_pressure": 0.10,
        "resource_pressure": 0.10,
        "storage_pressure": 0.10,
        "recovery_pressure": 0.0,
        "exploration_pressure": 0.20,
    }
    values.update(overrides)
    return GoalSituation(**values)


def _binding(
    kind: GoalKind,
    *,
    execute,
    verify,
    effort: float = 0.20,
    risk: float = 0.10,
) -> ExecutableGoalBinding:  # type: ignore[no-untyped-def]
    return ExecutableGoalBinding(
        binding_ref=f"private:red:{kind.value}",
        kind=kind,
        estimated_effort=effort,
        estimated_risk=risk,
        execute=execute,
        verify=verify,
    )


def test_runtime_records_before_action_and_verifies_after_action() -> None:
    trajectory, sink = _trajectory()
    order: list[str] = []

    def execute() -> GoalExecutionReport:
        assert len(sink.decisions) == 1
        assert not sink.events
        order.append("execute")
        return GoalExecutionReport(3, 120, {"bounded": True})

    def verify(report: GoalExecutionReport) -> GoalVerification:
        assert report.actions_executed == 3
        order.append("verify")
        return GoalVerification.succeeded()

    story = _binding(GoalKind.ADVANCE_STORY, execute=execute, verify=verify)
    restore = _binding(
        GoalKind.RESTORE_TEAM,
        execute=lambda: GoalExecutionReport(1, 1, {}),
        verify=lambda _report: GoalVerification.succeeded(),
    )

    result = execute_goal_manager_decision(
        situation=_situation(),
        binding_set=GoalBindingSet(
            (story.opportunity, restore.opportunity),
            (story, restore),
        ),
        authority=_SelectKind(GoalKind.ADVANCE_STORY),
        trajectory=trajectory,
    )

    assert order == ["execute", "verify"]
    assert result.passed
    assert result.decision_recorded
    assert result.outcome_recorded
    assert len(sink.events) == 1
    assert sink.events[0].payload["status"] == GoalDecisionOutcome.SUCCEEDED.value
    assert "private:red" not in json.dumps(result.public_dict(), sort_keys=True)


def test_runtime_records_a_failure_if_the_bound_executor_raises() -> None:
    trajectory, sink = _trajectory()

    def fail() -> GoalExecutionReport:
        raise RuntimeError("private implementation detail")

    selected = _binding(
        GoalKind.ADVANCE_STORY,
        execute=fail,
        verify=lambda _report: GoalVerification.succeeded(),
    )
    other = _binding(
        GoalKind.RESTORE_TEAM,
        execute=lambda: GoalExecutionReport(0, 0, {}),
        verify=lambda _report: GoalVerification.succeeded(),
    )

    with pytest.raises(RuntimeError, match="private implementation"):
        execute_goal_manager_decision(
            situation=_situation(),
            binding_set=GoalBindingSet(
                (selected.opportunity, other.opportunity),
                (selected, other),
            ),
            authority=_SelectKind(GoalKind.ADVANCE_STORY),
            trajectory=trajectory,
        )

    assert len(sink.decisions) == 1
    assert len(sink.events) == 1
    assert sink.events[0].payload == {
        "decision_id": "goal-runtime-episode:goal-manager:0",
        "failure_reason": "binding_failed",
        "selected_candidate_index": sink.decisions[0].action[
            "selected_candidate_index"
        ],
        "status": "failed",
    }
    assert "implementation detail" not in json.dumps(sink.events[0].to_dict())


def test_required_durable_decision_stops_before_controller_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory, sink = _trajectory()
    acted = False

    def execute() -> GoalExecutionReport:
        nonlocal acted
        acted = True
        return GoalExecutionReport(1, 1, {})

    monkeypatch.setattr(
        RecordingExecutor,
        "record_standalone_decision",
        lambda _self, _decision: False,
    )
    selected = _binding(
        GoalKind.ADVANCE_STORY,
        execute=execute,
        verify=lambda _report: GoalVerification.succeeded(),
    )
    other = _binding(
        GoalKind.RESTORE_TEAM,
        execute=lambda: GoalExecutionReport(0, 0, {}),
        verify=lambda _report: GoalVerification.succeeded(),
    )

    with pytest.raises(GoalManagerRuntimeError, match="not durably recorded"):
        execute_goal_manager_decision(
            situation=_situation(),
            binding_set=GoalBindingSet(
                (selected.opportunity, other.opportunity),
                (selected, other),
            ),
            authority=_SelectKind(GoalKind.ADVANCE_STORY),
            trajectory=trajectory,
            require_durable_decision=True,
        )

    assert acted is False
    assert trajectory.pending_decision is None
    assert not sink.decisions
    assert not sink.events


def test_failed_outcome_write_remains_unsettled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trajectory, sink = _trajectory()

    def reject_event(_self: InMemoryTrajectorySink, _event: object) -> None:
        raise OSError("simulated durable outcome failure")

    monkeypatch.setattr(InMemoryTrajectorySink, "record_event", reject_event)
    selected = _binding(
        GoalKind.ADVANCE_STORY,
        execute=lambda: GoalExecutionReport(1, 1, {}),
        verify=lambda _report: GoalVerification.succeeded(),
    )
    other = _binding(
        GoalKind.RESTORE_TEAM,
        execute=lambda: GoalExecutionReport(0, 0, {}),
        verify=lambda _report: GoalVerification.succeeded(),
    )

    with pytest.raises(GoalManagerTrajectoryError, match="no consumed outcome"):
        execute_goal_manager_decision(
            situation=_situation(),
            binding_set=GoalBindingSet(
                (selected.opportunity, other.opportunity),
                (selected, other),
            ),
            authority=_SelectKind(GoalKind.ADVANCE_STORY),
            trajectory=trajectory,
        )

    assert trajectory.pending_decision is not None
    assert len(sink.decisions) == 1
    assert not sink.events


def test_completion_first_teacher_changes_choice_with_same_menu() -> None:
    options = (
        GoalOpportunity(
            "story",
            GoalKind.ADVANCE_STORY,
            GoalAvailability.AVAILABLE,
            0.20,
            0.20,
        ),
        GoalOpportunity(
            "collect",
            GoalKind.ACQUIRE_SPECIES,
            GoalAvailability.AVAILABLE,
            0.30,
            0.10,
        ),
        GoalOpportunity(
            "restore",
            GoalKind.RESTORE_TEAM,
            GoalAvailability.AVAILABLE,
            0.05,
            0.01,
        ),
    )
    teacher = CompletionFirstGoalTeacher()
    story_question = GoalManagerQuestion(_situation(), options)
    safety_question = GoalManagerQuestion(
        _situation(story_pressure=0.20, safety_pressure=0.80),
        options,
    )

    assert teacher.select(story_question).kind is GoalKind.ADVANCE_STORY
    assert teacher.select(safety_question).kind is GoalKind.RESTORE_TEAM
    assert teacher.public_dict()["uses_candidate_position"] is False
