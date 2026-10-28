import random

import pytest

from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion import route_plan
from route_inventory_dijkstra_reference import reference_paths


def test_differing_destinations_reuse_settled_local_search_work():
    calls = [0]
    class CountedGraph(LocalGraph):
        def neighbors(self, coordinate):
            calls[0] += 1
            return super().neighbors(coordinate)
    edges = {(0, n): (LocalEdge((0, n + 1), "right"),) for n in range(90)}
    graph, oracle = CountedGraph(edges), LocalGraph(edges)
    with route_plan.frozen_local_route_inventory() as cache:
        for target in range(10, 80):
            goals = {((0, target), None)}
            projected, got = cache.paths(graph, frozenset(), (0, 0), goals, frozenset(), None)
            expected = reference_paths(oracle, (0, 0), goals)
            assert list(got.items()) == list(expected.items())
            assert projected is graph
        assert calls[0] <= 90


@pytest.mark.parametrize("seed", range(16))
def test_sequential_questions_match_pinned_dijkstra_paths_and_order(seed):
    rng = random.Random(seed)
    nodes = [(0, n) for n in range(18)]
    edges = {}
    for source in nodes:
        outgoing = []
        for target in rng.sample(nodes, 5):
            outgoing.append(LocalEdge(target, "right", cost=rng.choice([1, 1, 2, 5]),
                requirements=rng.choice([frozenset(), frozenset({"cut"})]),
                required_mode=rng.choice([None, None, "walk", "surf"]),
                result_mode=rng.choice([None, "walk", "surf"])))
        edges[source] = tuple(outgoing)
    graph = LocalGraph(edges)
    for capabilities in [frozenset(), frozenset({"cut"})]:
        for mode in [None, "walk", "surf"]:
            with route_plan.frozen_local_route_inventory() as cache:
                questions = [set(), {((0, 0), None)}, {((0, 17), None)},
                    {((0, 0), "walk"), ((0, 0), "surf")}, {((99, 99), None)}]
                questions += [{(rng.choice(nodes), rng.choice([None, "walk", "surf"]))
                    for _ in range(5)} for _ in range(16)]
                for goals in questions:
                    _, got = cache.paths(graph, frozenset(), (0, 0), goals, capabilities, mode)
                    expected = reference_paths(graph, (0, 0), goals, capabilities=capabilities, start_mode=mode)
                    assert list(got.items()) == list(expected.items())
                    assert {goal: sum(edge.cost for edge in path.edges) for goal, path in got.items()} == {
                        goal: sum(edge.cost for edge in path.edges) for goal, path in expected.items()}


def test_last_matched_node_is_expanded_before_a_later_destination():
    graph = LocalGraph({(0, n): (LocalEdge((0, n + 1), "right"),) for n in range(5)})
    with route_plan.frozen_local_route_inventory() as cache:
        for n in [0, 1, 4, 2, 5, 9]:
            goals = {((0, n), None)}
            _, got = cache.paths(graph, (), (0, 0), goals, frozenset(), None)
            assert list(got.items()) == list(reference_paths(graph, (0, 0), goals).items())


def test_start_mode_capabilities_and_warp_projection_are_separate_questions():
    graph = LocalGraph({
        (0, 0): (LocalEdge((1, 0), "down"), LocalEdge((0, 1), "right", requirements=frozenset({"cut"}))),
        (1, 0): (LocalEdge((1, 1), "right", result_mode="surf"),),
        (0, 1): (LocalEdge((1, 1), "down", required_mode="walk"),),
        (1, 1): (LocalEdge((2, 1), "down", required_mode="surf"),),
    })
    with route_plan.frozen_local_route_inventory() as cache:
        for start in [(0, 0), (1, 0)]:
            for capabilities in [frozenset(), frozenset({"cut"})]:
                for mode in [None, "walk", "surf"]:
                    for warps in [frozenset(), frozenset({(1, 0)})]:
                        for goals in [{((1, 1), None)}, {((2, 1), "surf"), ((1, 1), "walk")}]:
                            projected, got = cache.paths(graph, warps, start, goals, capabilities, mode)
                            expected_graph = route_plan.without_warp_transit(graph, warps, start_at=start)
                            expected = reference_paths(expected_graph, start, goals, capabilities=capabilities, start_mode=mode)
                            assert projected.edges == expected_graph.edges
                            assert list(got.items()) == list(expected.items())


def test_mutation_cannot_hide_behind_a_reused_frontier():
    edges = {(0, 0): (LocalEdge((0, 1), "right"),), (0, 1): (LocalEdge((0, 2), "right"),)}
    graph = LocalGraph(edges)
    with pytest.raises(route_plan.RoutePlanningError, match="changed"):
        with route_plan.frozen_local_route_inventory() as cache:
            cache.paths(graph, (), (0, 0), {((0, 1), None)}, frozenset(), None)
            edges[(0, 1)] = ()
            with pytest.raises(route_plan.RoutePlanningError, match="changed"):
                cache.paths(graph, (), (0, 0), {((0, 2), None)}, frozenset(), None)


def test_projected_graph_mutation_is_also_refused():
    graph = LocalGraph({(0, 0): (LocalEdge((0, 1), "right"),), (0, 1): (LocalEdge((0, 2), "right"),)})
    with pytest.raises(route_plan.RoutePlanningError, match="changed"):
        with route_plan.frozen_local_route_inventory() as cache:
            projected, _ = cache.paths(graph, {(0, 1)}, (0, 0), {((0, 1), None)}, frozenset(), None)
            projected.edges[(0, 0)] = ()
            with pytest.raises(route_plan.RoutePlanningError, match="changed"):
                cache.paths(graph, {(0, 1)}, (0, 0), {((0, 2), None)}, frozenset(), None)


def test_bounded_search_pool_falls_back_without_changing_paths(monkeypatch):
    monkeypatch.setattr(route_plan, "_MAX_LOCAL_INVENTORY_SEARCHES", 2)
    graph = LocalGraph({(0, n): (LocalEdge((0, n + 1), "right"),) for n in range(8)})
    with route_plan.frozen_local_route_inventory() as cache:
        for start in [(0, 0), (0, 1), (0, 2), (0, 3)]:
            for target in [4, 6, 8]:
                goals = {((0, target), None)}
                _, got = cache.paths(graph, (), start, goals, frozenset(), None)
                assert list(got.items()) == list(reference_paths(graph, start, goals).items())
        assert len(cache.searches) == 2
    assert not cache.searches and not cache.queries and not cache.graphs


def test_nested_inventory_reuses_only_the_owning_observation():
    graph = LocalGraph({(0, 0): (LocalEdge((0, 1), "right"),)})
    with route_plan.frozen_local_route_inventory() as outer:
        with route_plan.frozen_local_route_inventory() as inner:
            assert inner is outer
            outer.paths(graph, (), (0, 0), {((0, 1), None)}, frozenset(), None)
            assert outer.searches
        assert outer.searches
    assert not outer.searches
    with route_plan.frozen_local_route_inventory() as renewed:
        assert renewed is not outer and not renewed.searches
