"""Compose two existing Cut quotes at a real interior exit, never erase obstacles."""
from dataclasses import replace
import pytest
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroPath, MacroTransition
from pokemon_red_completion.local_router import LocalEdge, LocalGraph, LocalPath
from pokemon_red_completion.route_plan import RoutePlan, RouteSegment, RoutePlanningError
from pokemon_red_completion.route_executor import TraversalSnapshot, TraversalHazard
from pokemon_red_completion.strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def piece(source, target, at, arrival, macro):
    approach = LocalPath((at, at),
        (LocalEdge(at, 'cut:down', kind='field_move', action_kind=MacroActionKind.FIELD_MOVE),),
        ('land', 'land'))
    segment = RouteSegment(source, target, approach, MacroTransition(at, arrival, 'down'),
                           'warp', False)
    return RoutePlan(MacroPath((source, target), (macro,)), at, 'land', (segment,),
                     None, arrival, 'land')


def setup(monkeypatch, fault=None):
    world = object.__new__(StrategicScenarioRouteWorld)
    exit_edge = MacroEdge(None, kind='return', at=(0, 0), exit_action='down')
    entry = MacroEdge(3, kind='warp', at=(1, 1), arrival_at=(3, 3))
    graph = MacroGraph({2: (exit_edge,), 1: (entry,), 3: ()}, outside_nodes=frozenset({1}))
    object.__setattr__(world, 'macro_graph', graph)
    object.__setattr__(world, 'local_graphs', {1: LocalGraph({})})
    start = TraversalSnapshot(2, (0, 0), True, mode='land', last_outside_map=1,
        capabilities=frozenset({'move:cut'}), occupied=frozenset({(0, 1)}),
        hazards=(TraversalHazard((1, 0), 'trainer_sight'),))
    first = piece(2, 1, start.at, (1, 1), exit_edge)
    second = piece(1, 3, (1, 1), (3, 3), entry)
    calls = []

    def bounded(self, seen, goal, *, goal_at=None):
        calls.append((seen, goal, goal_at))
        if seen.map_id == 2 and goal == 3:
            raise RoutePlanningError('no bounded feasible route: two distinct Cut passages')
        if goal == 1:
            assert seen.occupied == start.occupied and seen.hazards == start.hazards
            if fault == 'blocked_exit': raise RoutePlanningError('occupied or trainer hazard')
            return first
        assert seen.map_id == 1 and goal == 3 and goal_at == (3, 3)
        assert seen.capabilities == start.capabilities and seen.last_outside_map == 1
        assert not seen.occupied and not seen.hazards
        if fault == 'blocked_suffix': raise RoutePlanningError('blocked outside passage')
        if fault == 'cycle':
            return piece(1, 2, (1, 1), (3, 3), replace(entry, target_map=2))
        return second

    monkeypatch.setattr(StrategicScenarioRouteWorld, '_bounded_single_cut_plan', bounded)
    return world, start, first, second, calls


def test_two_cuts_preserve_exact_endpoint_cost_and_step_continuity(monkeypatch):
    world, start, first, second, calls = setup(monkeypatch)
    joined = world.plan_feasible_to_map(start, 3, goal_at=(3, 3))
    assert joined.macro_path.maps == (2, 1, 3)
    assert joined.start_at == first.start_at and joined.terminal_at == (3, 3)
    assert joined.actions == first.actions + second.actions
    assert joined.cost == first.cost + second.cost
    assert len(calls) == 3
    for previous, following in zip(joined.steps, joined.steps[1:]):
        assert (previous.expected_map, previous.expected_at) == (following.source_map, following.source_at)


@pytest.mark.parametrize('fault', ['no_cut', 'unknown_outside', 'already_outside',
    'no_return_edge', 'blocked_exit', 'blocked_suffix', 'cycle'])
def test_failed_or_unsupported_exit_never_relaxes_the_owned_route(monkeypatch, fault):
    world, start, _, _, calls = setup(monkeypatch, fault)
    if fault == 'no_cut': start = replace(start, capabilities=frozenset())
    if fault == 'unknown_outside': start = replace(start, last_outside_map=None)
    if fault == 'already_outside':
        object.__setattr__(world, 'macro_graph', replace(world.macro_graph, outside_nodes=frozenset({1, 2})))
    if fault == 'no_return_edge':
        object.__setattr__(world, 'macro_graph', replace(world.macro_graph, edges={1: (), 2: (), 3: ()}))
    with pytest.raises(RoutePlanningError): world.plan_feasible_to_map(start, 3, goal_at=(3, 3))
    assert len(calls) <= 3


def test_normal_bounded_route_remains_the_exact_first_candidate(monkeypatch):
    world, start, _, second, _ = setup(monkeypatch)
    monkeypatch.setattr(StrategicScenarioRouteWorld, '_bounded_single_cut_plan', lambda *a, **k: second)
    assert world.plan_feasible_to_map(start, 3, goal_at=(3, 3)) is second
