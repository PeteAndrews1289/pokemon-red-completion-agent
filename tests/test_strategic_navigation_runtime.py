from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import (
    DEFAULT_ROUTE_EXECUTION_LIMITS,
    RouteExecutionError,
    RouteExecutionFailureReason,
    RouteExecutionLimits,
    TraversalSnapshot,
)
from pokemon_red_completion.route_plan import plan_route
from pokemon_red_completion.strategic_navigation import StrategicNavigationTag
from pokemon_red_completion.strategic_navigation_binding import DestinationRouteBinding
from pokemon_red_completion.strategic_navigation_protocol import (
    STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH,
    parse_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_runtime import (
    execute_strategic_navigation_route,
)
from pokemon_red_completion.strategic_navigation_trajectory import (
    StrategicNavigationTrajectoryObserver,
)
from pokemon_red_completion.trajectory import (
    InMemoryTrajectorySink,
    RecordingExecutor,
    SemanticSnapshot,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _SemanticObserver:
    def snapshot(self) -> SemanticSnapshot:
        return SemanticSnapshot(
            game_id="pokemon.red",
            mode="overworld",
            facts=("need:advance_story",),
            features={"candidate_count": 2},
        )


class _World:
    def __init__(self, *, acknowledge: bool = True) -> None:
        self.at = (0, 0)
        self.acknowledge = acknowledge
        self.decision_count_at_first_action: int | None = None
        self.sink: InMemoryTrajectorySink | None = None

    def observe(self) -> TraversalSnapshot:
        return TraversalSnapshot(map_id=1, at=self.at, ready=True)

    def execute(self, action: MacroAction) -> object:
        if self.decision_count_at_first_action is None:
            assert self.sink is not None
            self.decision_count_at_first_action = len(self.sink.decisions)
        if action.kind is MacroActionKind.MOVE and self.acknowledge:
            self.at = (0, self.at[1] + 1)
        return action


def _fixture(
    *,
    acknowledge: bool = True,
) -> tuple[
    StrategicNavigationTrajectoryObserver,
    RecordingExecutor[MacroAction, object],
    InMemoryTrajectorySink,
    _World,
    tuple[DestinationRouteBinding, ...],
]:
    registry = parse_strategic_navigation_registry(
        (PROJECT_ROOT / STRATEGIC_NAVIGATION_REGISTRY_RELATIVE_PATH).read_bytes()
    )
    assignment = replace(registry.rehearsal_assignment(), source_commit="a" * 40)
    sink = InMemoryTrajectorySink()
    world = _World(acknowledge=acknowledge)
    world.sink = sink
    recorder = RecordingExecutor(
        delegate=world,
        snapshot_provider=_SemanticObserver(),
        sink=sink,
        episode_id=assignment.episode_id,
    )
    trajectory = StrategicNavigationTrajectoryObserver(
        assignment=assignment,
        snapshot_provider=_SemanticObserver(),
        recorder=recorder,
        sink=sink,
    )
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), action="right"),),
            (0, 1): (LocalEdge((0, 2), action="right"),),
            (0, 2): (),
        }
    )
    macro = MacroGraph({1: ()})
    bindings = (
        DestinationRouteBinding.available(
            "pokemon.test:destination:near",
            (StrategicNavigationTag.OPTIONAL_REWARD,),
            plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 1)),
        ),
        DestinationRouteBinding.available(
            "pokemon.test:destination:story",
            (StrategicNavigationTag.STORY_PROGRESS,),
            plan_route(macro, {1: graph}, 1, (0, 0), 1, goal_at=(0, 2)),
        ),
    )
    return trajectory, recorder, sink, world, bindings


def _execute(
    trajectory: StrategicNavigationTrajectoryObserver,
    recorder: RecordingExecutor[MacroAction, object],
    world: _World,
    bindings: tuple[DestinationRouteBinding, ...],
    *,
    limits: RouteExecutionLimits = DEFAULT_ROUTE_EXECUTION_LIMITS,
) -> object:
    return execute_strategic_navigation_route(
        trajectory,
        semantic_need_tags=(StrategicNavigationTag.ADVANCE_STORY,),
        origin_semantic_tags=(StrategicNavigationTag.OVERWORLD,),
        origin_region_ref="pokemon.test:region:origin",
        bindings=bindings,
        selected_destination_ref="pokemon.test:destination:story",
        actions=recorder,
        traversal_observer=world,
        limits=limits,
    )


def test_runtime_records_choice_before_action_and_consumes_success() -> None:
    trajectory, recorder, sink, world, bindings = _fixture()

    report = _execute(trajectory, recorder, world, bindings)

    assert report.passed
    assert world.decision_count_at_first_action == 1
    assert len(sink.decisions) == 1
    assert len(sink.events) == 1
    assert sink.events[0].payload["status"] == "succeeded"
    assert trajectory.pending_decision is None


def test_runtime_consumes_measured_failure_before_propagating_it() -> None:
    trajectory, recorder, sink, world, bindings = _fixture(acknowledge=False)

    with pytest.raises(RouteExecutionError) as raised:
        _execute(
            trajectory,
            recorder,
            world,
            bindings,
            limits=RouteExecutionLimits(
                max_step_attempts=1,
                replan_after_unchanged=1,
            ),
        )

    assert raised.value.reason is RouteExecutionFailureReason.STEP_ACKNOWLEDGEMENT_EXHAUSTED
    assert raised.value.failure is not None
    assert world.decision_count_at_first_action == 1
    assert len(sink.decisions) == 1
    assert len(sink.events) == 1
    assert sink.events[0].payload["status"] == "failed"
    assert sink.events[0].payload["movement_requests"] == 1
    assert sink.events[0].payload["failure_reason"] == "step_acknowledgement_exhausted"
    assert trajectory.pending_decision is None
