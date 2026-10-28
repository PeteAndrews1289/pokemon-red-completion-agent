"""Passage reuse must preserve return destinations and ordinary failure behavior."""
from dataclasses import replace

import pytest

from pokemon_red_completion import route_plan as routes
from pokemon_red_completion.global_router import MacroEdge, MacroGraph, MacroTransition
from pokemon_red_completion.local_router import LocalEdge, LocalGraph


def return_world():
    local = LocalGraph({
        (0, x): tuple(
            LocalEdge((0, target), action=action)
            for target, action in ((x - 1, "left"), (x + 1, "right"))
            if 0 <= target <= 3
        )
        for x in range(4)
    })
    graph = MacroGraph(
        edges={
            **{i: (MacroEdge(10, kind="warp", at=(0, 3), arrival_at=(0, 0)),)
               for i in (1, 2, 3)},
            10: (
                MacroEdge(None, kind="return", at=(0, 3), exit_action="down",
                          destination_warp_index=0),
                MacroEdge(2, coordinate_transitions=(MacroTransition((0, 1), (0, 0), "up"),)),
                MacroEdge(3, coordinate_transitions=(MacroTransition((0, 1), (0, 0), "up"),)),
            ),
            99: (),
        },
        outside_nodes=frozenset({1, 2, 3}),
        warp_locations={**{i: ((0, 0), (0, 3)) for i in (1, 2, 3)}, 10: ((0, 3),)},
        warp_triggers={i: ((0, 3),) for i in (1, 2, 3, 10)},
    )
    return graph, {i: local for i in (1, 2, 3, 10, 99)}


def counted_compositions(monkeypatch):
    original = routes._compose_segment_candidates
    calls = []

    def counted(*args, **kwargs):
        graph, local, state, target, edge = args
        calls.append((state.map_id, state.at, state.mode, target, edge.kind, state.last_outside))
        return original(*args, **kwargs)

    monkeypatch.setattr(routes, "_compose_segment_candidates", counted)
    return calls


def test_outside_variants_share_passages_but_keep_return_targets(monkeypatch):
    graph, local = return_world()
    calls = counted_compositions(monkeypatch)
    with pytest.raises(routes.RoutePlanningError, match="no locally composable route"):
        routes.plan_route(graph, local, 1, (0, 0), 99)
    for target in (2, 3):
        assert sum(source == 10 and to == target and kind == "connection"
                   for source, at, mode, to, kind, outside in calls) == 1
    assert {to for source, at, mode, to, kind, outside in calls
            if source == 10 and kind == "return"} == {1, 2, 3}


def test_passage_results_do_not_survive_another_search(monkeypatch):
    graph, local = return_world()
    calls = counted_compositions(monkeypatch)
    for _ in range(2):
        with pytest.raises(routes.RoutePlanningError):
            routes.plan_route(graph, local, 1, (0, 0), 99)
    assert sum(source == 10 and to == 2 and kind == "connection"
               for source, at, mode, to, kind, outside in calls) == 2


def test_successful_route_keeps_cheapest_exact_passages():
    graph, local = return_world()
    plan = routes.plan_route(graph, local, 1, (0, 0), 3)
    assert plan.macro_path.maps == (1, 10, 3)
    assert plan.actions == ("right", "right", "right", "right", "up")
    assert plan.terminal_at == (0, 0)
    assert plan.cost == 6


def test_new_weights_are_priced_in_the_new_search():
    graph, local = return_world()
    first = routes.plan_route(graph, local, 1, (0, 0), 3)
    weighted = replace(graph, edges={**graph.edges, 10: (
        graph.edges[10][0], graph.edges[10][1], replace(graph.edges[10][2], cost=17),
    )})
    second = routes.plan_route(weighted, local, 1, (0, 0), 3)
    assert second.macro_path.maps == first.macro_path.maps
    assert second.cost == first.cost + 16


def test_infeasible_passage_is_not_recomputed_for_other_outside_contexts(monkeypatch):
    graph, local = return_world()
    original = routes._compose_segment_candidates
    rejected = []

    def no_three(graph, local, state, target, edge, **kwargs):
        if state.map_id == 10 and edge.kind == "connection" and target == 3:
            rejected.append(state.last_outside)
            raise routes.RoutePlanningError("declared infeasible passage")
        return original(graph, local, state, target, edge, **kwargs)

    monkeypatch.setattr(routes, "_compose_segment_candidates", no_three)
    with pytest.raises(routes.RoutePlanningError, match="no locally composable route"):
        routes.plan_route(graph, local, 1, (0, 0), 99)
    assert len(rejected) == 1


def test_unexpected_composition_error_is_preserved(monkeypatch):
    graph, local = return_world()

    def broken(*args, **kwargs):
        raise RuntimeError("unexpected composition fault")

    monkeypatch.setattr(routes, "_compose_segment_candidates", broken)
    with pytest.raises(RuntimeError, match="unexpected composition fault"):
        routes.plan_route(graph, local, 1, (0, 0), 99)
