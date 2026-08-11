from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import (
    ExecutedRouteStep,
    RouteExecutionFailureReason,
    RouteExecutionFailureReport,
    RouteExecutionReport,
    TraversalSnapshot,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route
from pokemon_red_completion.strategic_navigation import (
    StrategicNavigationError,
    StrategicNavigationTag,
)
from pokemon_red_completion.strategic_navigation_binding import (
    BoundStrategicNavigationDecision,
    DestinationRouteBinding,
)
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    StrategicNavigationProtocolError,
    parse_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_trajectory import (
    StrategicNavigationTrajectoryObserver,
    _assignment_ordered_bindings,
)
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _SnapshotProvider:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id="pokemon.red",
            mode="overworld",
            facts=("need:advance_story",),
            features={"candidate_count": 2},
        )


class _Executor:
    def execute(self, action: dict[str, object]) -> dict[str, object]:
        return action


def _plans() -> tuple[RoutePlan, RoutePlan]:
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), action="right"),),
            (0, 1): (LocalEdge((0, 2), action="right"),),
            (0, 2): (),
        }
    )
    macro = MacroGraph({1: ()})
    return (
        plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 1)),
        plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 2)),
    )


def _bindings() -> tuple[DestinationRouteBinding, ...]:
    short, long = _plans()
    return (
        DestinationRouteBinding.available(
            "pokemon.test:destination:safe",
            (StrategicNavigationTag.HEALING, StrategicNavigationTag.SAFE_HUB),
            short,
        ),
        DestinationRouteBinding.available(
            "pokemon.test:destination:progress",
            (StrategicNavigationTag.CHALLENGE, StrategicNavigationTag.STORY_PROGRESS),
            long,
        ),
    )


def test_assignment_ordering_is_deterministic_and_breaks_fixed_answer_position() -> None:
    bindings = _bindings()

    first = _assignment_ordered_bindings("a" * 64, 0, bindings)
    repeated = _assignment_ordered_bindings("a" * 64, 0, bindings)
    second_root = _assignment_ordered_bindings("b" * 64, 0, bindings)

    assert first == repeated
    assert {item.destination_ref for item in first} == {
        item.destination_ref for item in bindings
    }
    assert tuple(item.destination_ref for item in first) != tuple(
        item.destination_ref for item in second_root
    )


def _report(plan: RoutePlan) -> RouteExecutionReport:
    return RouteExecutionReport(
        initial_plan=plan,
        terminal=TraversalSnapshot(
            map_id=plan.terminal_map,
            at=plan.terminal_at,
            ready=True,
            mode=plan.terminal_mode,
        ),
        executed_steps=tuple(
            ExecutedRouteStep(step, movement_requests=1, interruption_count=0)
            for step in plan.steps
        ),
        interruptions=(),
        replans=(),
        movement_requests=len(plan.steps),
        wait_actions=0,
    )


def _observer() -> tuple[
    StrategicNavigationTrajectoryObserver,
    RecordingExecutor[dict[str, object], dict[str, object]],
    InMemoryTrajectorySink,
]:
    registry = parse_strategic_navigation_registry(
        (PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    assignment = replace(registry.rehearsal_assignment(), source_commit="a" * 40)
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_SnapshotProvider(),
        sink=sink,
        episode_id=assignment.episode_id,
    )
    return (
        StrategicNavigationTrajectoryObserver(
            assignment=assignment,
            snapshot_provider=_SnapshotProvider(),
            recorder=recorder,
            sink=sink,
        ),
        recorder,
        sink,
    )


def _bind(
    observer: StrategicNavigationTrajectoryObserver,
) -> BoundStrategicNavigationDecision:
    return observer.bind_decision(
        semantic_need_tags=(StrategicNavigationTag.ADVANCE_STORY,),
        origin_semantic_tags=(StrategicNavigationTag.OVERWORLD,),
        origin_region_ref="pokemon.test:region:origin",
        bindings=_bindings(),
        selected_destination_ref="pokemon.test:destination:progress",
    )


def test_observer_records_choice_before_execution_and_one_consumed_outcome() -> None:
    observer, recorder, sink = _observer()

    bound = _bind(observer)

    assert len(sink.decisions) == 1
    assert len(sink.events) == 0
    assert observer.pending_decision == bound.decision
    with pytest.raises(StrategicNavigationError, match="no consumed outcome"):
        observer.require_settled()
    with pytest.raises(StrategicNavigationError, match="still awaits"):
        _bind(observer)

    recorder.execute({"kind": "move", "direction": "right"})
    assert observer.record_outcome(bound.successful_record(_report(bound.selected_plan)))
    observer.require_settled()

    assert len(sink.events) == 1
    assert sink.decisions[0].step_index == 0
    assert sink.events[0].step_index == 1
    assert sink.events[0].payload["decision_id"] == sink.decisions[0].decision_id
    with pytest.raises(StrategicNavigationError, match="no pending"):
        observer.record_outcome(bound.successful_record(_report(bound.selected_plan)))


def test_observer_rejects_uncommitted_or_wrong_episode_assignment() -> None:
    registry = parse_strategic_navigation_registry(
        (PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    assignment = registry.rehearsal_assignment()
    sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_SnapshotProvider(),
        sink=sink,
        episode_id=assignment.episode_id,
    )
    with pytest.raises(StrategicNavigationProtocolError, match="committed"):
        StrategicNavigationTrajectoryObserver(
            assignment=assignment,
            snapshot_provider=_SnapshotProvider(),
            recorder=recorder,
            sink=sink,
        )

    committed = replace(assignment, source_commit="a" * 40)
    wrong_recorder = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_SnapshotProvider(),
        sink=sink,
        episode_id="wrong-episode",
    )
    with pytest.raises(StrategicNavigationProtocolError, match="episode differs"):
        StrategicNavigationTrajectoryObserver(
            assignment=committed,
            snapshot_provider=_SnapshotProvider(),
            recorder=wrong_recorder,
            sink=sink,
        )

    test_assignment = replace(
        registry.assignment("red-strategic-v1-08-test"),
        source_commit="b" * 40,
    )
    test_recorder = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_SnapshotProvider(),
        sink=sink,
        episode_id=test_assignment.episode_id,
    )
    with pytest.raises(StrategicNavigationProtocolError, match="must remain unopened"):
        StrategicNavigationTrajectoryObserver(
            assignment=test_assignment,
            snapshot_provider=_SnapshotProvider(),
            recorder=test_recorder,
            sink=sink,
        )


def test_observer_rejects_split_decision_and_outcome_sinks() -> None:
    registry = parse_strategic_navigation_registry(
        (PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    assignment = replace(registry.rehearsal_assignment(), source_commit="a" * 40)
    decision_sink = InMemoryTrajectorySink()
    recorder = RecordingExecutor(
        delegate=_Executor(),
        snapshot_provider=_SnapshotProvider(),
        sink=decision_sink,
        episode_id=assignment.episode_id,
    )

    with pytest.raises(StrategicNavigationProtocolError, match="sinks differ"):
        StrategicNavigationTrajectoryObserver(
            assignment=assignment,
            snapshot_provider=_SnapshotProvider(),
            recorder=recorder,
            sink=InMemoryTrajectorySink(),
        )


def test_observer_does_not_write_orphan_outcome_after_decision_sink_failure() -> None:
    observer, recorder, sink = _observer()
    sink.finalize()

    bound = _bind(observer)

    assert recorder.recording_failures == 1
    assert observer.record_outcome(bound.successful_record(_report(bound.selected_plan))) is False
    assert sink.decisions == ()
    assert sink.events == ()
    assert recorder.recording_failures == 1
    observer.require_settled()


def test_observer_marks_sink_failure_without_changing_control() -> None:
    observer, recorder, sink = _observer()
    bound = _bind(observer)
    sink.finalize()

    recorded = observer.record_outcome(
        bound.successful_record(_report(bound.selected_plan))
    )

    assert recorded is False
    assert recorder.recording_failures == 1
    observer.require_settled()


def test_observer_consumes_measured_route_failure_as_negative_outcome() -> None:
    observer, _, sink = _observer()
    bound = _bind(observer)
    failure = RouteExecutionFailureReport(
        initial_plan=bound.selected_plan,
        reason=RouteExecutionFailureReason.PLANNER_NO_ROUTE,
        last_observation=TraversalSnapshot(map_id=1, at=(0, 1), ready=True),
        executed_steps=(
            ExecutedRouteStep(
                bound.selected_plan.steps[0],
                movement_requests=1,
                interruption_count=0,
            ),
        ),
        interruptions=(),
        replans=(),
        movement_requests=2,
        wait_actions=1,
    )

    assert observer.record_outcome(bound.failed_route_record(failure))

    payload = sink.events[0].payload
    assert payload["status"] == "failed"
    assert payload["failure_reason"] == "planner_no_route"
    assert payload["movement_requests"] == 2
    assert payload["acknowledged_steps"] == 1
    assert "last_observation" not in payload
