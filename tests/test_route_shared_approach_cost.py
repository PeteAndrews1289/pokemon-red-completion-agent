from __future__ import annotations
from dataclasses import replace
import pytest
from pokemon_red_completion import route_plan as routes
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroTransition
from pokemon_red_completion.local_router import LocalEdge, LocalGraph


def fixture(fanout=8, length=16, *, reverse=False, weighted=True):
    sink = fanout + 2
    order = list(range(2, sink))
    if reverse:
        order.reverse()
    source_edges = {
        (0, x): (LocalEdge((0, x + 1), action="right", cost=(1 + x % 3 if weighted else 1)),)
        for x in range(length)
    }
    source_edges[(0, length)] = ()
    local = {1: LocalGraph(source_edges), sink: LocalGraph({(0, 0): ()})}
    edges = {1: tuple(MacroEdge(m, coordinate_transitions=(MacroTransition((0, length), (0, 0), "down"),)) for m in order), sink: ()}
    for m in order:
        local[m] = LocalGraph({(0, 0): (LocalEdge((0, 1), action="right", cost=2),), (0, 1): ()})
        edges[m] = (MacroEdge(sink, kind="warp", at=(0, 1), arrival_at=(0, 0)),)
    return MacroGraph(edges), local, sink, order


@pytest.mark.parametrize("fanout", [1, 2, 8])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("weighted", [False, True])
def test_shared_approach_exact_cost_tie_and_actions(fanout, reverse, weighted):
    graph, local, sink, order = fixture(fanout, 16, reverse=reverse, weighted=weighted)
    result = routes.plan_route(graph, local, 1, (0, 0), sink)
    prefix_cost = sum(1 + x % 3 if weighted else 1 for x in range(16))
    assert result.macro_path.maps == (1, order[0], sink)
    assert result.cost == prefix_cost + 4
    assert result.actions == ("right",) * 16 + ("down", "right")
    assert result.terminal_at == (0, 0)
    assert result.terminal_mode is None
    assert result.steps[16].expected_map == order[0]
    if fanout > 1:
        blocked = routes.plan_route(graph, local, 1, (0, 0), sink,
                                    blocked={order[0]: frozenset({(0, 1)})})
        assert blocked.macro_path.maps == (1, order[1], sink)
        assert blocked.cost == result.cost


def test_price_lifetime_does_not_survive_new_observation():
    graph, local, sink, _ = fixture()
    before = routes.plan_route(graph, local, 1, (0, 0), sink)
    original = local[1].edges[(0, 0)][0]
    local[1].edges[(0, 0)] = (replace(original, cost=original.cost + 37),)
    after = routes.plan_route(graph, local, 1, (0, 0), sink)
    assert after.cost == before.cost + 37
    assert after.actions == before.actions
    assert after.macro_path == before.macro_path


def test_in_inventory_graph_mutation_still_refused():
    graph, local, sink, _ = fixture()
    with pytest.raises(routes.RoutePlanningError):
        with routes.frozen_local_route_inventory():
            routes.plan_route(graph, local, 1, (0, 0), sink)
            original = local[1].edges[(0, 0)][0]
            local[1].edges[(0, 0)] = (replace(original, cost=19),)
            routes.plan_route(graph, local, 1, (0, 0), sink)
    assert routes._FROZEN_LOCAL_ROUTE_CACHE.get() is None
