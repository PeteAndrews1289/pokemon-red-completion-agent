from test_route_executor import FakeWorld
import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import execute_route, RouteExecutionError
from pokemon_red_completion.route_plan import plan_route, RoutePlanningError


def test_reobserve_after_replanner_wait_vacates_occupied_destination():
    macro = MacroGraph({1: ()})
    graphs = {1: LocalGraph({(0, 0): (LocalEdge((0, 1), 'right'),), (0, 1): ()})}
    plan = plan_route(macro, graphs, 1, (0, 0), 1, goal_at=(0, 1))
    world = FakeWorld(occupied=frozenset({(0, 1)}),
                      occupancy_after_waits={1: frozenset()},
                      transitions={(1, (0, 0), 'right'): (1, (0, 1))})
    calls = []

    def replan(request):
        if calls:
            raise RoutePlanningError('executor reused the pre-wait occupied snapshot')
        calls.append(request)
        world.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
        current = world.observe()
        return plan_route(macro, graphs, 1, current.at, 1, goal_at=(0, 1),
                          blocked={1: current.occupied})

    report = execute_route(plan, world, world, replanner=replan)
    assert report.passed and world.at == (0, 1)
    assert len(calls) == len(report.replans) == 1
    assert [a.kind for a in world.actions] == [MacroActionKind.WAIT, MacroActionKind.MOVE]


def test_replanner_cannot_hide_changed_player_position_before_next_input():
    macro = MacroGraph({1: ()})
    graphs = {1: LocalGraph({(0, 0): (LocalEdge((0, 1), 'right'),), (0, 1): ()})}
    plan = plan_route(macro, graphs, 1, (0, 0), 1, goal_at=(0, 1))
    world = FakeWorld(occupied=frozenset({(0, 1)}))

    def replan(request):
        world.occupied = frozenset()
        world.at = (2, 2)
        return plan

    with pytest.raises(RouteExecutionError, match='step source'):
        execute_route(plan, world, world, replanner=replan)
    assert not world.actions
