from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroTransition
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import (
    InterruptionReceipt,
    ReplanRequest,
    RouteExecutionError,
    RouteExecutionLimits,
    TraversalSnapshot,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route


@dataclass
class FakeWorld:
    map_id: int = 1
    at: tuple[int, int] = (0, 0)
    ready: bool = True
    interruption: str | None = None
    transitions: dict[
        tuple[int, tuple[int, int], str], tuple[int, tuple[int, int]]
    ] = field(default_factory=dict)
    swallowed: dict[tuple[int, tuple[int, int], str], int] = field(default_factory=dict)
    interrupt_on: dict[tuple[int, tuple[int, int], str], str] = field(default_factory=dict)
    staged_transitions: dict[
        tuple[int, tuple[int, int], str], tuple[int, tuple[int, int], tuple[int, int]]
    ] = field(default_factory=dict)
    pending_arrival: tuple[int, tuple[int, int]] | None = None
    actions: list[MacroAction] = field(default_factory=list)

    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            if self.pending_arrival is not None:
                self.map_id, self.at = self.pending_arrival
                self.pending_arrival = None
            self.ready = True
            return action
        assert action.kind is MacroActionKind.MOVE
        assert isinstance(action.value, str)
        key = (self.map_id, self.at, action.value)
        remaining = self.swallowed.get(key, 0)
        if remaining:
            self.swallowed[key] = remaining - 1
            return action
        if key in self.interrupt_on:
            self.interruption = self.interrupt_on.pop(key)
            return action
        if key in self.staged_transitions:
            target_map, transient_at, final_at = self.staged_transitions[key]
            self.map_id, self.at = target_map, transient_at
            self.pending_arrival = target_map, final_at
            return action
        if key in self.transitions:
            self.map_id, self.at = self.transitions[key]
        return action

    def observe(self) -> TraversalSnapshot:
        return TraversalSnapshot(
            map_id=self.map_id,
            at=self.at,
            ready=self.ready and self.interruption is None,
            interruption=self.interruption,
        )


@dataclass
class ClearingHandler:
    world: FakeWorld

    def handle(self, interruption: TraversalSnapshot) -> InterruptionReceipt:
        assert interruption.interruption is not None
        self.world.interruption = None
        self.world.ready = True
        return InterruptionReceipt(
            kind=interruption.interruption,
            resumed_map=self.world.map_id,
            resumed_at=self.world.at,
        )


def connection_plan() -> tuple[RoutePlan, MacroGraph, dict[int, LocalGraph]]:
    transition = MacroTransition((0, 1), (5, 0), "up")
    macro = MacroGraph({1: (MacroEdge(2, coordinate_transitions=(transition,)),)})
    local = {1: LocalGraph({(0, 0): (LocalEdge((0, 1), action="right"),), (0, 1): ()})}
    return plan_route(macro, local, 1, (0, 0), 2), macro, local


def test_each_requested_movement_needs_live_acknowledgement() -> None:
    plan, _, _ = connection_plan()
    world = FakeWorld(
        transitions={
            (1, (0, 0), "right"): (1, (0, 1)),
            (1, (0, 1), "up"): (2, (5, 0)),
        }
    )

    report = execute_route(plan, world, world)

    assert report.passed
    assert report.movement_requests == 2
    assert report.wait_actions == 1, "the cross-map transition receives one settling wait"
    assert [receipt.movement_requests for receipt in report.executed_steps] == [1, 1]


def test_an_unchanged_input_is_retried_instead_of_counted() -> None:
    plan, _, _ = connection_plan()
    world = FakeWorld(
        transitions={
            (1, (0, 0), "right"): (1, (0, 1)),
            (1, (0, 1), "up"): (2, (5, 0)),
        },
        swallowed={(1, (0, 0), "right"): 1},
    )

    report = execute_route(plan, world, world)

    assert report.movement_requests == 3
    assert report.executed_steps[0].movement_requests == 2
    assert report.wait_actions == 2, "one retry wait and one transition wait"


def test_a_map_change_waits_for_staggered_destination_coordinates() -> None:
    plan, _, _ = connection_plan()
    world = FakeWorld(
        transitions={(1, (0, 0), "right"): (1, (0, 1))},
        staged_transitions={
            (1, (0, 1), "up"): (2, (99, 99), (5, 0)),
        },
    )

    report = execute_route(plan, world, world)

    assert report.passed
    assert report.terminal.at == (5, 0)
    assert report.wait_actions == 1


def test_an_interruption_does_not_consume_a_same_coordinate_step() -> None:
    plan, _, _ = connection_plan()
    world = FakeWorld(
        transitions={
            (1, (0, 0), "right"): (1, (0, 1)),
            (1, (0, 1), "up"): (2, (5, 0)),
        },
        interrupt_on={(1, (0, 0), "right"): "wild_battle"},
    )

    report = execute_route(
        plan,
        world,
        world,
        interruption_handler=ClearingHandler(world),
    )

    assert report.movement_requests == 3
    assert len(report.interruptions) == 1
    assert report.interruptions[0].kind == "wild_battle"
    assert report.executed_steps[0].interruption_count == 1


def test_repeated_live_blocking_replans_around_the_discovered_square() -> None:
    transition = MacroTransition((0, 2), (7, 2), "up")
    macro = MacroGraph({1: (MacroEdge(2, coordinate_transitions=(transition,)),)})
    local = {
        1: LocalGraph(
            {
                (0, 0): (
                    LocalEdge((0, 1), action="right"),
                    LocalEdge((1, 0), action="down"),
                ),
                (0, 1): (LocalEdge((0, 2), action="right"),),
                (1, 0): (LocalEdge((1, 1), action="right"),),
                (1, 1): (LocalEdge((1, 2), action="right"),),
                (1, 2): (LocalEdge((0, 2), action="up"),),
                (0, 2): (),
            }
        )
    }
    initial = plan_route(macro, local, 1, (0, 0), 2)
    world = FakeWorld(
        transitions={
            (1, (0, 0), "down"): (1, (1, 0)),
            (1, (1, 0), "right"): (1, (1, 1)),
            (1, (1, 1), "right"): (1, (1, 2)),
            (1, (1, 2), "up"): (1, (0, 2)),
            (1, (0, 2), "up"): (2, (7, 2)),
        }
    )

    def replan(request: ReplanRequest) -> RoutePlan:
        return plan_route(
            macro,
            local,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            blocked=request.blocked,
        )

    report = execute_route(initial, world, world, replanner=replan)

    assert report.passed
    assert len(report.replans) == 1
    assert report.replans[0].newly_blocked == (0, 1)
    assert report.movement_requests == 7, "two blocked requests plus five replacement steps"
    assert [step.step.action for step in report.executed_steps] == [
        "down",
        "right",
        "right",
        "up",
        "up",
    ]


def test_route_drift_fails_instead_of_becoming_a_replan() -> None:
    plan, _, _ = connection_plan()
    world = FakeWorld(transitions={(1, (0, 0), "right"): (1, (9, 9))})

    with pytest.raises(RouteExecutionError, match="route drifted"):
        execute_route(plan, world, world)


def test_readiness_is_bounded_and_observed_before_movement() -> None:
    plan, _, _ = connection_plan()
    world = FakeWorld(ready=False)

    with pytest.raises(RouteExecutionError, match="step .* exceeded"):
        execute_route(
            plan,
            world,
            world,
            limits=RouteExecutionLimits(
                max_step_attempts=1,
                replan_after_unchanged=1,
            ),
        )
    assert world.actions[0].kind is MacroActionKind.WAIT
