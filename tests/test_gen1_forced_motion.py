from dataclasses import dataclass, field, replace

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_forced_motion import apply_forced_motion, spinner_sequences
from pokemon_red_completion.gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import (
    LocalEdge,
    LocalGraph,
    LocalRouterError,
    find_local_path,
    without_coordinates,
)
from pokemon_red_completion.route_executor import (
    RouteExecutionError,
    RouteExecutionLimits,
    TraversalHazard,
    TraversalSnapshot,
    execute_route,
)
from pokemon_red_completion.route_plan import plan_route


def cartridge(map_id=45):
    rom = bytearray(0x10000)
    rom[MAP_HEADER_BANKS + map_id] = 1
    rom[MAP_HEADER_POINTERS + 2 * map_id:MAP_HEADER_POINTERS + 2 * map_id + 2] = b"\x00\x41"
    rom[0x4107:0x4109] = b"\x00\x42"
    script = bytes.fromhex("fa61d347fa62d34f210043cd4234feffca1932")
    rom[0x4200:0x4200 + len(script)] = script
    # Trigger (1,1), reverse-ordered program: right2 THEN down1.
    rom[0x4300:0x4305] = bytes([1, 1, 0, 0x44, 0xFF])
    rom[0x4400:0x4405] = bytes([0x80, 1, 0x10, 2, 0xFF])
    return rom


@pytest.mark.parametrize("map_id", [45, 200, 201])
def test_cartridge_reference_and_reverse_rle(map_id):
    assert spinner_sequences(bytes(cartridge(map_id)), map_id) == {
        (1, 1): ((1, 2), (1, 3), (2, 3)),
    }


def test_non_spinner_map_does_not_read_script():
    assert spinner_sequences(b"", 1) == {}


@pytest.mark.parametrize("at,payload", [
    (0x4200, b"\x00"), (0x420B, b"\x00"), (0x4209, b"\x00\x80"),
    (0x4302, b"\xff\x7f"), (0x4400, b"\x11"), (0x4401, b"\x00"),
    (0x4400, b"\xff"), (0x4400, bytes([0x10, 255, 0x10, 2, 0xFF])),
    (0x4304, bytes([1, 1, 0, 0x44, 0xFF])),
])
def test_bad_cartridge_data_fails_closed(at, payload):
    rom = cartridge()
    rom[at:at + len(payload)] = payload
    with pytest.raises(CartridgeReadError):
        spinner_sequences(bytes(rom), 45)


def test_truncated_cartridge_fails_with_typed_error():
    with pytest.raises(CartridgeReadError, match="truncated"):
        spinner_sequences(bytes(cartridge()[:100]), 45)


def grid(height=5, width=7):
    return LocalGraph({
        (y, x): tuple(LocalEdge((y + dy, x + dx), action)
                      for action, dy, dx in (("up", -1, 0), ("down", 1, 0),
                                             ("left", 0, -1), ("right", 0, 1))
                      if 0 <= y + dy < height and 0 <= x + dx < width)
        for y in range(height) for x in range(width)
    })


def edge_from(graph, start=(1, 0), action="right"):
    return next((e for e in graph.neighbors(start) if e.action == action), None)


def test_forced_endpoint_retains_every_visited_tile_and_single_input():
    graph = apply_forced_motion(grid(), {(1, 1): ((1, 2), (1, 3), (2, 3))})
    edge = edge_from(graph)
    assert edge.kind == "forced_motion" and edge.target == (2, 3)
    assert edge.via == ((1, 1), (1, 2), (1, 3)) and edge.cost == 4
    assert edge.action == "right" and (1, 1) not in graph.edges
    with pytest.raises(LocalRouterError):
        find_local_path(graph, (1, 0), (1, 1))


def test_chain_follows_only_script_endpoints_not_intermediate_arrows():
    graph = apply_forced_motion(grid(), {
        (1, 1): ((1, 2), (1, 3)), (1, 3): ((2, 3),),
        (1, 2): ((0, 2),),  # Passing this coordinate does not restart the script.
    })
    assert edge_from(graph).target == (2, 3)


@pytest.mark.parametrize("sequences", [
    {(1, 1): ()}, {(1, 1): ((1, 2),), (1, 2): ((1, 1),)},
    {(1, 1): ((1, 0),)}, {(1, 1): ((1, 4),)},
    {(1, 1): ((-1, 1),)},
])
def test_invalid_or_cyclic_motion_is_not_a_walkable_shortcut(sequences):
    assert edge_from(apply_forced_motion(grid(), sequences)) is None


def test_static_live_and_warp_blockers_include_intermediate_coordinates():
    sequence = {(1, 1): ((1, 2), (1, 3))}
    assert edge_from(apply_forced_motion(without_coordinates(grid(), {(1, 2)}), sequence)) is None
    assert edge_from(apply_forced_motion(grid(), sequence, forbidden={(1, 2)})) is None
    compiled = apply_forced_motion(grid(), sequence)
    assert edge_from(without_coordinates(compiled, {(1, 2)})) is None


def test_intermediate_requirements_are_not_lost():
    original = grid()
    edges = dict(original.edges)
    edges[(1, 2)] = tuple(replace(e, requirements=frozenset({"gate"}))
                          if e.target == (1, 3) else e for e in edges[(1, 2)])
    graph = apply_forced_motion(LocalGraph(edges), {(1, 1): ((1, 2), (1, 3))})
    assert edge_from(graph).requirements == frozenset({"gate"})


def motion_plan():
    graph = LocalGraph({(1, 0): (LocalEdge((1, 3), "right", kind="forced_motion",
                                          via=((1, 1), (1, 2))),), (1, 3): ()})
    return plan_route(MacroGraph({1: ()}), {1: graph}, 1, (1, 0), 1, goal_at=(1, 3))


@dataclass
class MotionWorld:
    at: tuple[int, int] = (1, 0)
    ready: bool = True
    stages: list = field(default_factory=lambda: [((1, 2), False), ((1, 3), False),
                                                 ((1, 3), True)])
    actions: list = field(default_factory=list)
    occupied: frozenset = frozenset()
    hazards: tuple = ()
    interruption: str | None = None

    def observe(self):
        return TraversalSnapshot(1, self.at, self.ready, interruption=self.interruption,
                                 occupied=self.occupied, hazards=self.hazards)

    def execute(self, action):
        self.actions.append(action)
        if action.kind == MacroActionKind.MOVE:
            assert self.at == (1, 0), "directional input inside a spinner"
            self.at, self.ready = (1, 1), True  # script dispatch is delayed
        elif self.stages:
            self.at, self.ready = self.stages.pop(0)


def test_execution_waits_for_exact_ready_endpoint_not_first_tile_or_early_endpoint():
    world = MotionWorld()
    plan = motion_plan()
    assert plan.steps[0].via == ((1, 1), (1, 2))
    report = execute_route(plan, world, world)
    assert report.passed and world.at == (1, 3) and world.ready
    assert report.movement_requests == 1 and report.wait_actions == 3


@pytest.mark.parametrize("stages", [[((2, 1), True)], [((1, 2), True)]])
def test_unexpected_or_stuck_endpoint_fails_without_reissuing_move(stages):
    world = MotionWorld(stages=stages)
    with pytest.raises(RouteExecutionError, match="forced motion") as error:
        execute_route(motion_plan(), world, world,
                      limits=RouteExecutionLimits(max_readiness_waits=2))
    assert error.value.failure is not None
    assert sum(a.kind == MacroActionKind.MOVE for a in world.actions) == 1


@pytest.mark.parametrize("hazard", [False, True])
def test_known_intermediate_object_or_trainer_stops_before_input(hazard):
    world = MotionWorld(
        occupied=frozenset() if hazard else frozenset({(1, 2)}),
        hazards=(TraversalHazard((1, 2), "trainer_sight"),) if hazard else (),
    )
    with pytest.raises(RouteExecutionError, match="live obstruction"):
        execute_route(motion_plan(), world, world)
    assert not world.actions


def test_known_intermediate_hazard_is_passed_to_replanner():
    world = MotionWorld(hazards=(TraversalHazard((1, 2), "trainer_sight"),))
    requests = []
    def replan(request):
        requests.append(request)
        from pokemon_red_completion.route_plan import RoutePlanningError
        raise RoutePlanningError("blocked path")
    with pytest.raises(RouteExecutionError):
        execute_route(motion_plan(), world, world, replanner=replan)
    assert requests[0].blocked[1] == frozenset({(1, 2)})
    assert not world.actions


def test_unexpected_battle_during_motion_is_retained_not_hidden_by_handler():
    class Encounter(MotionWorld):
        def execute(self, action):
            super().execute(action)
            if action.kind == MacroActionKind.WAIT:
                self.interruption = "trainer_battle"
    world = Encounter()
    with pytest.raises(RouteExecutionError, match="unexpected interruption"):
        execute_route(motion_plan(), world, world)
    assert sum(a.kind == MacroActionKind.MOVE for a in world.actions) == 1


def test_new_hazard_after_swallowed_input_prevents_a_second_move():
    class Swallowed(MotionWorld):
        def execute(self, action):
            self.actions.append(action)
            if action.kind == MacroActionKind.WAIT:
                self.hazards = (TraversalHazard((1, 2), "trainer_sight"),)
    world = Swallowed()
    with pytest.raises(RouteExecutionError, match="acquired a live obstruction"):
        execute_route(motion_plan(), world, world)
    assert sum(a.kind == MacroActionKind.MOVE for a in world.actions) == 1


def test_live_terrain_rebuild_keeps_motion_and_checks_changed_blocks():
    from pokemon_red_completion.gen1_terrain import Terrain
    from pokemon_red_completion.gen1_traversal import TraversalRules, surf_local_graph
    from pokemon_red_completion.strategic_navigation_scenario_runtime import (
        StrategicScenarioRouteWorld,
    )
    floor = tuple(tuple(True for _ in range(4)) for _ in range(4))
    empty = tuple(tuple(False for _ in range(4)) for _ in range(4))
    tiles = tuple(tuple(1 for _ in range(4)) for _ in range(4))
    terrain = Terrain(45, 7, floor, empty, empty, tiles)
    rules = TraversalRules((), (), (), (), ())
    sequence = {(1, 1): ((1, 2), (1, 3))}
    world = StrategicScenarioRouteWorld(MacroGraph({45: ()}),
        {45: surf_local_graph(terrain, rules)}, b"x", {45: terrain}, rules, {},
        frozenset(), {45: frozenset()}, forced_movements={45: sequence})
    assert edge_from(world._graph_for_terrain(terrain)).kind == "forced_motion"
    changed = replace(terrain, walkable=tuple(
        tuple(False if (y, x) == (1, 2) else value for x, value in enumerate(row))
        for y, row in enumerate(floor)))
    assert edge_from(world._graph_for_terrain(changed)) is None


def test_feasible_quote_cannot_cross_an_intermediate_trainer_lane():
    from pokemon_red_completion.gen1_traversal import TraversalRules
    from pokemon_red_completion.strategic_navigation_scenario_runtime import (
        StrategicScenarioRouteWorld,
    )
    world = StrategicScenarioRouteWorld(MacroGraph({1: ()}), {1: grid()}, b"x", {},
        TraversalRules((), (), (), (), ()), {}, frozenset(), {})
    start = TraversalSnapshot(1, (1, 0), True,
                              hazards=(TraversalHazard((1, 2), "trainer_sight"),))
    plan = world.plan_feasible_to_map(start, 1, goal_at=(1, 4))
    assert (1, 2) not in plan.terminal_approach.coordinates
    assert len(plan.steps) > 4


def test_feasible_cut_fallback_preserves_trainer_constraints(monkeypatch):
    from pokemon_red_completion.gen1_traversal import TraversalRules
    from pokemon_red_completion.route_plan import RoutePlanningError
    from pokemon_red_completion.strategic_navigation_scenario_runtime import (
        StrategicScenarioRouteWorld,
    )
    graph = LocalGraph({(1, 0): (LocalEdge((1, 1), "right"),),
                        (1, 1): (LocalEdge((1, 2), "right"),), (1, 2): ()})
    world = StrategicScenarioRouteWorld(MacroGraph({1: ()}), {1: graph}, b"x", {},
        TraversalRules((), (), (), (), ()), {}, frozenset(), {})
    seen = []
    def cut(self, start, goal_map, **kwargs):
        seen.append(kwargs["blocked"])
        raise RoutePlanningError("no safe Cut")
    monkeypatch.setattr(StrategicScenarioRouteWorld, "_staged_cut_plan", cut)
    start = TraversalSnapshot(1, (1, 0), True,
                              hazards=(TraversalHazard((1, 1), "trainer_sight"),))
    with pytest.raises(RoutePlanningError):
        world.plan_feasible_to_map(start, 1, goal_at=(1, 2))
    assert seen == [{1: frozenset({(1, 1)})}]
