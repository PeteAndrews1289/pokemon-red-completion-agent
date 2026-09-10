"""Concrete action-boundary probes, not a replay of a private game trajectory."""
from dataclasses import dataclass

import pytest
from test_route_executor import ClearingHandler, FakeWorld, connection_plan

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import (
    RouteExecutionError,
    RouteExecutionFailureReason,
    RouteExecutionLimits,
    execute_route,
)
from pokemon_red_completion.route_plan import plan_route


def _line(length):
    graph = LocalGraph({
        (0, i): (LocalEdge((0, i + 1), action="right"),) if i < length else ()
        for i in range(length + 1)
    })
    plan = plan_route(MacroGraph({1: ()}), {1: graph}, 1, (0, 0), 1, goal_at=(0, length))
    return plan, {(1, (0, i), "right"): (1, (0, i + 1)) for i in range(length)}


@dataclass
class EncounterOnArrival(FakeWorld):
    def execute(self, action):
        result = super().execute(action)
        if action.kind is MacroActionKind.MOVE:
            self.interruption = "wild_battle"
        return result


@pytest.mark.parametrize("limit", [1, 2, 8, 16])
def test_last_allowed_battle_stops_before_next_move_and_preserves_partial_route(limit):
    plan, transitions = _line(limit + 1)
    world = EncounterOnArrival(transitions=transitions)
    with pytest.raises(RouteExecutionError, match="before further input") as caught:
        execute_route(plan, world, world, interruption_handler=ClearingHandler(world),
                      limits=RouteExecutionLimits(max_interruptions=limit))
    failure = caught.value.failure
    assert caught.value.reason is RouteExecutionFailureReason.INTERRUPTION_BUDGET_EXHAUSTED
    assert failure.last_observation == world.observe()
    assert world.observe().ready and world.interruption is None
    assert world.at == (0, limit)
    assert len(world.actions) == failure.movement_requests == limit
    assert len(failure.executed_steps) == len(failure.interruptions) == limit
    assert failure.wait_actions == 0


@pytest.mark.parametrize("limit", [1, 2, 8, 16])
def test_exact_terminal_at_limit_still_completes_without_additional_input(limit):
    plan, transitions = _line(limit)
    world = EncounterOnArrival(transitions=transitions)
    result = execute_route(plan, world, world, interruption_handler=ClearingHandler(world),
                           limits=RouteExecutionLimits(max_interruptions=limit))
    assert result.passed and result.terminal.ready
    assert len(world.actions) == len(result.interruptions) == limit
    assert result.wait_actions == 0


@pytest.mark.parametrize("where", ["initial", "move", "retry_wait", "readiness_wait"])
def test_exhaustion_never_sends_retry_input_from_same_coordinate(where):
    plan, transitions = _line(2)
    world = FakeWorld(transitions=transitions)
    if where == "initial":
        world.interruption = "wild_battle"
    elif where == "move":
        world.interrupt_on[(1, (0, 0), "right")] = "wild_battle"
    elif where == "retry_wait":
        world.swallowed[(1, (0, 0), "right")] = 1
        world.interruptions_after_waits[1] = "wild_battle"
    else:
        world.ready = False
        world.interruptions_after_waits[1] = "wild_battle"
    with pytest.raises(RouteExecutionError) as caught:
        execute_route(plan, world, world, interruption_handler=ClearingHandler(world),
                      limits=RouteExecutionLimits(max_interruptions=1))
    assert caught.value.reason is RouteExecutionFailureReason.INTERRUPTION_BUDGET_EXHAUSTED
    assert len(world.actions) == {"initial": 0, "move": 1, "retry_wait": 2,
                                  "readiness_wait": 1}[where]
    assert world.at == (0, 0) and world.observe().ready
    assert len(caught.value.failure.interruptions) == 1


def test_delayed_transition_battle_at_terminal_is_resolved_then_completes():
    plan, _, _ = connection_plan()
    world = FakeWorld(
        transitions={(1, (0, 0), "right"): (1, (0, 1))},
        staged_transitions={(1, (0, 1), "up"): (2, (9, 9), (5, 0))},
        interruptions_after_waits={1: "wild_battle"},
    )
    result = execute_route(plan, world, world, interruption_handler=ClearingHandler(world),
                           limits=RouteExecutionLimits(max_interruptions=1))
    assert result.passed and result.terminal.at == (5, 0)
    assert len(result.interruptions) == 1 and result.wait_actions == 1


def test_failed_handler_is_not_misreported_as_safe_budget_exhaustion():
    plan, transitions = _line(2)
    world = EncounterOnArrival(transitions=transitions)
    class BadHandler(ClearingHandler):
        def handle(self, interrupted):
            receipt = super().handle(interrupted)
            self.world.interruption = "wild_battle"
            return receipt
    with pytest.raises(RouteExecutionError) as caught:
        execute_route(plan, world, world, interruption_handler=BadHandler(world),
                      limits=RouteExecutionLimits(max_interruptions=1))
    assert caught.value.reason is RouteExecutionFailureReason.INTERRUPTION_UNRECOVERED
    assert not caught.value.failure.last_observation.ready
    assert len(world.actions) == 1


def test_unready_handler_terminal_keeps_resolved_receipt_without_an_extra_wait():
    plan, transitions = _line(2)
    world = FakeWorld(transitions=transitions, interruption="wild_battle")
    class UnreadyHandler(ClearingHandler):
        def handle(self, interrupted):
            receipt = super().handle(interrupted)
            self.world.ready = False
            return receipt
    with pytest.raises(RouteExecutionError) as caught:
        execute_route(plan, world, world, interruption_handler=UnreadyHandler(world),
                      limits=RouteExecutionLimits(max_interruptions=1))
    assert len(caught.value.failure.interruptions) == 1
    assert not caught.value.failure.last_observation.ready
    assert world.actions == []


def test_budget_does_not_allow_a_transition_settle_to_trigger_another_battle():
    plan, _, _ = connection_plan()
    class ArrivalBattle(FakeWorld):
        def execute(self, action):
            old_map = self.map_id
            result = super().execute(action)
            if self.map_id != old_map:
                self.interruption = "wild_battle"
            return result
    world = ArrivalBattle(
        transitions={(1, (0, 0), "right"): (1, (0, 1))},
        staged_transitions={(1, (0, 1), "up"): (2, (9, 9), (5, 0))},
        interruptions_after_waits={1: "wild_battle"},
    )
    with pytest.raises(RouteExecutionError) as caught:
        execute_route(plan, world, world, interruption_handler=ClearingHandler(world),
                      limits=RouteExecutionLimits(max_interruptions=1))
    assert caught.value.reason is RouteExecutionFailureReason.INTERRUPTION_BUDGET_EXHAUSTED
    assert caught.value.failure.last_observation.at == (9, 9)
    assert len(world.actions) == 2 and world.wait_count == 0
    assert len(caught.value.failure.interruptions) == 1
    assert len(caught.value.failure.executed_steps) == 1  # Unsettled transition is not completion.
