from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroTransition
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import (
    InterruptionReceipt,
    ReplanRequest,
    ResourceRenewalReceipt,
    RouteExecutionError,
    RouteExecutionFailureReason,
    RouteExecutionLimits,
    TraversalHazard,
    TraversalResource,
    TraversalSnapshot,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, RoutePlanningError, plan_route


@dataclass
class FakeWorld:
    map_id: int = 1
    at: tuple[int, int] = (0, 0)
    ready: bool = True
    interruption: str | None = None
    occupied: frozenset[tuple[int, int]] = frozenset()
    hazards: tuple[TraversalHazard, ...] = ()
    resources: tuple[TraversalResource, ...] = ()
    last_outside_map: int | None = None
    transitions: dict[tuple[int, tuple[int, int], str], tuple[int, tuple[int, int]]] = field(
        default_factory=dict
    )
    swallowed: dict[tuple[int, tuple[int, int], str], int] = field(default_factory=dict)
    interrupt_on: dict[tuple[int, tuple[int, int], str], str] = field(default_factory=dict)
    staged_transitions: dict[
        tuple[int, tuple[int, int], str], tuple[int, tuple[int, int], tuple[int, int]]
    ] = field(default_factory=dict)
    pending_arrival: tuple[int, tuple[int, int]] | None = None
    delayed_transitions: dict[tuple[int, tuple[int, int], str], tuple[int, tuple[int, int]]] = (
        field(default_factory=dict)
    )
    actions: list[MacroAction] = field(default_factory=list)
    occupancy_after_waits: dict[int, frozenset[tuple[int, int]]] = field(default_factory=dict)
    hazards_after_waits: dict[int, tuple[TraversalHazard, ...]] = field(default_factory=dict)
    interruptions_after_waits: dict[int, str] = field(default_factory=dict)
    wait_count: int = 0

    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        if action.kind is MacroActionKind.WAIT:
            self.wait_count += 1
            if self.wait_count in self.occupancy_after_waits:
                self.occupied = self.occupancy_after_waits[self.wait_count]
            if self.wait_count in self.hazards_after_waits:
                self.hazards = self.hazards_after_waits[self.wait_count]
            if self.wait_count in self.interruptions_after_waits:
                self.interruption = self.interruptions_after_waits[self.wait_count]
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
        if key in self.delayed_transitions:
            self.pending_arrival = self.delayed_transitions[key]
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
            occupied=self.occupied,
            hazards=self.hazards,
            resources=self.resources,
            last_outside_map=self.last_outside_map,
        )


@dataclass
class FakeResourceManager:
    world: FakeWorld
    calls: int = 0

    def renew_if_needed(
        self,
        current: TraversalSnapshot,
    ) -> ResourceRenewalReceipt | None:
        self.calls += 1
        (resource,) = current.resources
        if resource.remaining is None:
            raise RouteExecutionError("resource state is unknown")
        if resource.remaining > 0:
            return None
        if not resource.carried_units:
            raise RouteExecutionError("resource is depleted without a carried renewal")
        self.world.resources = (TraversalResource(resource.kind, 250, resource.carried_units - 1),)
        self.world.ready = True
        return ResourceRenewalReceipt(
            kind=resource.kind,
            map_id=current.map_id,
            at=current.at,
            before_remaining=0,
            after_remaining=250,
            units_consumed=1,
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


@dataclass
class TrainerClearingHandler(ClearingHandler):
    handled_hazard_kinds: frozenset[str] = frozenset({"trainer_sight"})


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


def test_a_depleted_route_resource_is_renewed_before_the_next_input() -> None:
    local = {
        1: LocalGraph(
            {
                (0, 0): (LocalEdge((0, 1), action="right"),),
                (0, 1): (),
            }
        )
    }
    plan = plan_route(MacroGraph({1: ()}), local, 1, (0, 0), 1, goal_at=(0, 1))
    world = FakeWorld(
        ready=False,
        resources=(TraversalResource("encounter_suppression", 0, 1),),
        transitions={(1, (0, 0), "right"): (1, (0, 1))},
    )
    manager = FakeResourceManager(world)

    report = execute_route(plan, world, world, resource_manager=manager)

    assert report.passed
    assert report.movement_requests == 1
    assert report.resource_renewals == (
        ResourceRenewalReceipt(
            kind="encounter_suppression",
            map_id=1,
            at=(0, 0),
            before_remaining=0,
            after_remaining=250,
            units_consumed=1,
        ),
    )
    assert world.actions == [MacroAction(MacroActionKind.MOVE, "right")]


def test_a_depleted_resource_without_inventory_fails_before_movement() -> None:
    plan, _, _ = connection_plan()
    world = FakeWorld(
        resources=(TraversalResource("encounter_suppression", 0, 0),),
    )

    with pytest.raises(RouteExecutionError, match="without a carried renewal") as caught:
        execute_route(
            plan,
            world,
            world,
            resource_manager=FakeResourceManager(world),
        )

    assert world.actions == []
    assert caught.value.reason is RouteExecutionFailureReason.RESOURCE_UNAVAILABLE
    assert caught.value.failure is not None
    assert caught.value.failure.movement_requests == 0
    assert caught.value.failure.executed_steps == ()


def test_a_resource_expiring_on_the_terminal_step_is_settled_before_handoff() -> None:
    local = {
        1: LocalGraph(
            {
                (0, 0): (LocalEdge((0, 1), action="right"),),
                (0, 1): (),
            }
        )
    }
    plan = plan_route(MacroGraph({1: ()}), local, 1, (0, 0), 1, goal_at=(0, 1))

    @dataclass
    class TerminalExpiryWorld(FakeWorld):
        def execute(self, action: MacroAction) -> object:
            result = super().execute(action)
            if action == MacroAction(MacroActionKind.MOVE, "right"):
                self.resources = (TraversalResource("encounter_suppression", 0, 1),)
                self.ready = False
            return result

    world = TerminalExpiryWorld(
        resources=(TraversalResource("encounter_suppression", 1, 1),),
        transitions={(1, (0, 0), "right"): (1, (0, 1))},
    )

    report = execute_route(
        plan,
        world,
        world,
        resource_manager=FakeResourceManager(world),
    )

    assert report.passed
    assert len(report.resource_renewals) == 1
    assert report.terminal.ready


def test_a_same_map_coordinate_goal_executes_its_terminal_approach() -> None:
    local = {
        1: LocalGraph(
            {
                (0, 0): (LocalEdge((0, 1), action="right"),),
                (0, 1): (LocalEdge((0, 2), action="right"),),
                (0, 2): (),
            }
        )
    }
    plan = plan_route(
        MacroGraph({1: ()}),
        local,
        1,
        (0, 0),
        1,
        goal_at=(0, 2),
    )
    world = FakeWorld(
        transitions={
            (1, (0, 0), "right"): (1, (0, 1)),
            (1, (0, 1), "right"): (1, (0, 2)),
        }
    )

    report = execute_route(plan, world, world)

    assert report.passed
    assert report.movement_requests == 2
    assert report.terminal.at == (0, 2)


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


def test_a_face_then_walk_step_accepts_its_delayed_acknowledgement() -> None:
    local = {
        1: LocalGraph(
            {
                (0, 0): (LocalEdge((1, 0), action="down"),),
                (1, 0): (),
            }
        )
    }
    plan = plan_route(
        MacroGraph({1: ()}),
        local,
        1,
        (0, 0),
        1,
        goal_at=(1, 0),
    )
    key = (1, (0, 0), "down")
    world = FakeWorld(
        swallowed={key: 1},
        delayed_transitions={key: (1, (1, 0))},
    )
    replan_requests: list[ReplanRequest] = []

    def reject_false_blocker(request: ReplanRequest) -> RoutePlan:
        replan_requests.append(request)
        raise AssertionError("an in-flight walk must settle before blocker discovery")

    report = execute_route(plan, world, world, replanner=reject_false_blocker)

    assert report.passed
    assert report.movement_requests == 2
    assert report.wait_actions == 2
    assert report.executed_steps[0].movement_requests == 2
    assert replan_requests == []


def test_field_actions_and_mode_changes_need_exact_live_acknowledgement() -> None:
    transition = MacroTransition((0, 3), (5, 0), "right")
    macro = MacroGraph({1: (MacroEdge(2, coordinate_transitions=(transition,)),)})
    local = LocalGraph(
        {
            (0, 0): (
                LocalEdge(
                    (0, 1),
                    action="surf:right",
                    kind="water_entry",
                    action_kind=MacroActionKind.FIELD_MOVE,
                    required_mode="land",
                    result_mode="water",
                ),
            ),
            (0, 1): (
                LocalEdge(
                    (0, 2),
                    action="right",
                    kind="water_travel",
                    required_mode="water",
                ),
            ),
            (0, 2): (
                LocalEdge(
                    (0, 3),
                    action="right",
                    kind="water_exit",
                    required_mode="water",
                    result_mode="land",
                ),
            ),
            (0, 3): (),
        }
    )
    plan = plan_route(macro, {1: local}, 1, (0, 0), 2, start_mode="land")

    @dataclass
    class ModeWorld:
        map_id: int = 1
        at: tuple[int, int] = (0, 0)
        mode: str = "land"
        actions: list[MacroAction] = field(default_factory=list)

        def execute(self, action: MacroAction) -> object:
            self.actions.append(action)
            if action.kind is MacroActionKind.WAIT:
                return action
            if action == MacroAction(MacroActionKind.FIELD_MOVE, "surf:right"):
                self.at = (0, 1)
                self.mode = "water"
            elif action == MacroAction(MacroActionKind.MOVE, "right"):
                if self.at == (0, 1):
                    self.at = (0, 2)
                elif self.at == (0, 2):
                    self.at = (0, 3)
                    self.mode = "land"
                else:
                    self.map_id, self.at = 2, (5, 0)
            return action

        def observe(self) -> TraversalSnapshot:
            return TraversalSnapshot(self.map_id, self.at, True, mode=self.mode)

    world = ModeWorld()
    report = execute_route(plan, world, world)

    assert report.passed
    assert [action.kind for action in world.actions if action.kind is not MacroActionKind.WAIT] == [
        MacroActionKind.FIELD_MOVE,
        MacroActionKind.MOVE,
        MacroActionKind.MOVE,
        MacroActionKind.MOVE,
    ]
    assert report.terminal.mode == "land"


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


def test_one_ledge_input_waits_for_its_declared_intermediate_coordinate() -> None:
    transition = MacroTransition((2, 0), (5, 0), "down")
    local = LocalGraph(
        {
            (0, 0): (
                LocalEdge(
                    (2, 0),
                    action="down",
                    kind="ledge",
                    transient=(1, 0),
                ),
            ),
            (2, 0): (),
        }
    )
    plan = plan_route(
        MacroGraph({1: (MacroEdge(2, coordinate_transitions=(transition,)),)}),
        {1: local},
        1,
        (0, 0),
        2,
    )
    world = FakeWorld(
        staged_transitions={
            (1, (0, 0), "down"): (1, (1, 0), (2, 0)),
        },
        transitions={(1, (2, 0), "down"): (2, (5, 0))},
    )

    report = execute_route(plan, world, world)

    assert plan.steps[0].transient_at == (1, 0)
    assert report.passed
    assert report.movement_requests == 2
    assert report.wait_actions == 2
    assert (report.terminal.map_id, report.terminal.at) == (2, (5, 0))


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
        last_outside_map=9,
        transitions={
            (1, (0, 0), "down"): (1, (1, 0)),
            (1, (1, 0), "right"): (1, (1, 1)),
            (1, (1, 1), "right"): (1, (1, 2)),
            (1, (1, 2), "up"): (1, (0, 2)),
            (1, (0, 2), "up"): (2, (7, 2)),
        },
    )

    def replan(request: ReplanRequest) -> RoutePlan:
        assert request.current.last_outside_map == 9
        return plan_route(
            macro,
            local,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            blocked=request.blocked,
            last_outside=request.current.last_outside_map,
        )

    report = execute_route(initial, world, world, replanner=replan)

    assert report.passed
    assert len(report.replans) == 1
    assert report.replans[0].newly_blocked == (0, 1)
    assert report.replans[0].reason == "settled_failed_step"
    assert report.movement_requests == 7, "two blocked requests plus five replacement steps"
    assert [step.step.action for step in report.executed_steps] == [
        "down",
        "right",
        "right",
        "up",
        "up",
    ]


def _visible_blocker_fixture() -> tuple[RoutePlan, MacroGraph, dict[int, LocalGraph]]:
    macro = MacroGraph({1: ()})
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
    return (
        plan_route(macro, local, 1, (0, 0), 1, goal_at=(0, 2)),
        macro,
        local,
    )


def _visible_blocker_world(**kwargs: object) -> FakeWorld:
    return FakeWorld(
        transitions={
            (1, (0, 0), "down"): (1, (1, 0)),
            (1, (1, 0), "right"): (1, (1, 1)),
            (1, (1, 1), "right"): (1, (1, 2)),
            (1, (1, 2), "up"): (1, (0, 2)),
        },
        **kwargs,  # type: ignore[arg-type]
    )


def test_a_visible_object_replans_before_requesting_its_square() -> None:
    initial, macro, local = _visible_blocker_fixture()
    world = _visible_blocker_world(occupied=frozenset({(0, 1)}))
    requests: list[ReplanRequest] = []

    def replan(request: ReplanRequest) -> RoutePlan:
        requests.append(request)
        world.occupied = frozenset()
        return plan_route(
            macro,
            local,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            goal_at=request.goal_at,
            blocked=request.blocked,
        )

    report = execute_route(initial, world, world, replanner=replan)

    assert report.passed
    assert requests[0].blocked == {1: frozenset({(0, 1)})}
    assert report.movement_requests == 4
    assert report.replans[0].reason == "visible_object"
    assert report.replans[0].newly_blocked == (0, 1)
    assert world.actions[0] == MacroAction(MacroActionKind.MOVE, "down")


def test_a_semantic_hazard_replans_without_becoming_visible_occupancy() -> None:
    initial, macro, local = _visible_blocker_fixture()
    world = _visible_blocker_world(
        hazards=(TraversalHazard((0, 1), "trainer_sight"),),
    )
    requests: list[ReplanRequest] = []

    def replan(request: ReplanRequest) -> RoutePlan:
        requests.append(request)
        world.hazards = ()
        return plan_route(
            macro,
            local,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            goal_at=request.goal_at,
            blocked=request.blocked,
        )

    report = execute_route(initial, world, world, replanner=replan)

    assert requests[0].blocked == {1: frozenset({(0, 1)})}
    assert report.replans[0].reason == "trainer_sight"
    assert report.movement_requests == 4
    assert world.actions[0] == MacroAction(MacroActionKind.MOVE, "down")


def test_an_explicit_handler_can_cross_and_settle_a_semantic_hazard() -> None:
    local = {
        1: LocalGraph(
            {
                (0, 0): (LocalEdge((0, 1), action="right"),),
                (0, 1): (LocalEdge((0, 2), action="right"),),
                (0, 2): (),
            }
        )
    }
    plan = plan_route(MacroGraph({1: ()}), local, 1, (0, 0), 1, goal_at=(0, 2))
    world = FakeWorld(
        hazards=(TraversalHazard((0, 1), "trainer_sight"),),
        transitions={
            (1, (0, 0), "right"): (1, (0, 1)),
            (1, (0, 1), "right"): (1, (0, 2)),
        },
        interruptions_after_waits={1: "trainer_engagement"},
    )

    report = execute_route(
        plan,
        world,
        world,
        interruption_handler=TrainerClearingHandler(world),
    )

    assert report.passed
    assert not report.replans
    assert [receipt.kind for receipt in report.interruptions] == ["trainer_engagement"]
    assert report.wait_actions == 1
    assert report.movement_requests == 2


def test_an_object_seen_during_settle_replans_before_a_retry() -> None:
    initial, macro, local = _visible_blocker_fixture()
    world = _visible_blocker_world(
        occupancy_after_waits={1: frozenset({(0, 1)})},
    )
    requests: list[ReplanRequest] = []

    def replan(request: ReplanRequest) -> RoutePlan:
        requests.append(request)
        world.occupied = frozenset()
        return plan_route(
            macro,
            local,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            goal_at=request.goal_at,
            blocked=request.blocked,
        )

    report = execute_route(initial, world, world, replanner=replan)

    assert report.passed
    assert requests[0].blocked == {1: frozenset({(0, 1)})}
    assert report.movement_requests == 5, "one failed request plus the four-step detour"
    assert report.replans[0].reason == "visible_object"
    moves = [action for action in world.actions if action.kind is MacroActionKind.MOVE]
    assert moves[:2] == [
        MacroAction(MacroActionKind.MOVE, "right"),
        MacroAction(MacroActionKind.MOVE, "down"),
    ]


def test_a_hazard_seen_during_settle_is_not_inferred_as_a_blocked_edge() -> None:
    initial, macro, local = _visible_blocker_fixture()
    world = _visible_blocker_world(
        hazards_after_waits={1: (TraversalHazard((0, 1), "trainer_sight"),)},
    )

    def replan(request: ReplanRequest) -> RoutePlan:
        world.hazards = ()
        return plan_route(
            macro,
            local,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            goal_at=request.goal_at,
            blocked=request.blocked,
        )

    report = execute_route(initial, world, world, replanner=replan)

    assert report.replans[0].reason == "trainer_sight"
    assert report.movement_requests == 5, "one request preceded the observed semantic hazard"


def test_a_departed_visible_object_does_not_become_a_durable_blocker() -> None:
    initial, macro, local = _visible_blocker_fixture()
    world = FakeWorld(
        occupied=frozenset({(0, 1)}),
        transitions={
            (1, (0, 0), "right"): (1, (0, 1)),
            (1, (0, 1), "right"): (1, (0, 2)),
        },
    )
    requests: list[ReplanRequest] = []

    def replan(request: ReplanRequest) -> RoutePlan:
        requests.append(request)
        world.occupied = frozenset()
        return plan_route(
            macro,
            local,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            goal_at=request.goal_at,
            blocked=request.blocked,
        )

    report = execute_route(initial, world, world, replanner=replan)

    assert report.passed
    assert [request.blocked for request in requests] == [
        {1: frozenset({(0, 1)})},
        {1: frozenset({(1, 0)})},
    ]
    assert [receipt.reason for receipt in report.replans] == [
        "visible_object",
        "settled_failed_step",
    ]
    assert report.movement_requests == 4


def test_route_drift_fails_instead_of_becoming_a_replan() -> None:
    plan, _, _ = connection_plan()
    world = FakeWorld(transitions={(1, (0, 0), "right"): (1, (9, 9))})

    with pytest.raises(RouteExecutionError, match="route drifted") as caught:
        execute_route(plan, world, world)

    assert caught.value.reason is RouteExecutionFailureReason.WORLD_STATE_DIVERGED
    assert caught.value.failure is not None
    assert caught.value.failure.movement_requests == 1
    assert caught.value.failure.last_observation is not None
    assert caught.value.failure.last_observation.at == (9, 9)


def test_replanner_failure_retains_the_acknowledged_prefix() -> None:
    local = {
        1: LocalGraph(
            {
                (0, 0): (LocalEdge((0, 1), action="right"),),
                (0, 1): (LocalEdge((0, 2), action="right"),),
                (0, 2): (),
            }
        )
    }
    plan = plan_route(MacroGraph({1: ()}), local, 1, (0, 0), 1, goal_at=(0, 2))
    world = FakeWorld(
        transitions={(1, (0, 0), "right"): (1, (0, 1))},
    )

    def no_route(_request: ReplanRequest) -> RoutePlan:
        raise RoutePlanningError("no replacement route")

    with pytest.raises(RouteExecutionError, match="replanning found no") as caught:
        execute_route(
            plan,
            world,
            world,
            replanner=no_route,
            limits=RouteExecutionLimits(replan_after_unchanged=1),
        )

    assert caught.value.reason is RouteExecutionFailureReason.PLANNER_NO_ROUTE
    assert caught.value.failure is not None
    assert len(caught.value.failure.executed_steps) == 1
    assert caught.value.failure.movement_requests == 2
    assert caught.value.failure.wait_actions == 1
    assert caught.value.failure.last_observation is not None
    assert caught.value.failure.last_observation.at == (0, 1)


def test_readiness_is_bounded_and_observed_before_movement() -> None:
    plan, _, _ = connection_plan()
    world = FakeWorld(ready=False)

    with pytest.raises(RouteExecutionError, match="step .* exceeded") as caught:
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
    assert caught.value.reason is (
        RouteExecutionFailureReason.STEP_ACKNOWLEDGEMENT_EXHAUSTED
    )
    assert caught.value.failure is not None
    assert caught.value.failure.movement_requests == 1
    assert caught.value.failure.executed_steps == ()
