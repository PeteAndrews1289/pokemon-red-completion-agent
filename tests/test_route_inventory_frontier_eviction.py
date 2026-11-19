import random

import pytest
from route_inventory_dijkstra_reference import reference_paths
from pokemon_red_completion import route_plan
from pokemon_red_completion.local_router import LocalEdge, LocalGraph


def test_new_origins_after_capacity_still_share_incremental_search(monkeypatch):
    monkeypatch.setattr(route_plan, '_MAX_LOCAL_INVENTORY_SEARCHES', 2)
    calls = [0]
    class CountedGraph(LocalGraph):
        def neighbors(self, coordinate):
            calls[0] += 1
            return super().neighbors(coordinate)
    edges = {(0, n): (LocalEdge((0, n + 1), 'right'),) for n in range(20)}
    graph, oracle = CountedGraph(edges), LocalGraph(edges)
    with route_plan.frozen_local_route_inventory() as cache:
        for start in [(0, 0), (0, 1), (0, 2), (0, 3)]:
            for target in range(10, 16):
                goals = {((0, target), None)}
                _, got = cache.paths(graph, (), start, goals, frozenset(), None)
                assert list(got.items()) == list(reference_paths(oracle, start, goals).items())
                assert len(cache.searches) <= 2
        assert calls[0] <= 60
    assert not cache.searches and not cache.graphs


def test_exact_query_hit_keeps_its_frontier_recent(monkeypatch):
    monkeypatch.setattr(route_plan, '_MAX_LOCAL_INVENTORY_SEARCHES', 2)
    graph = LocalGraph({(0, n): (LocalEdge((0, n + 1), 'right'),) for n in range(9)})
    with route_plan.frozen_local_route_inventory() as cache:
        def ask(start, end):
            goals = {((0, end), None)}
            _, got = cache.paths(graph, (), (0, start), goals, frozenset(), None)
            assert list(got.items()) == list(reference_paths(graph, (0, start), goals).items())
        ask(0, 3); ask(1, 3)
        first = next(value[1] for key, value in cache.searches.items() if key[2] == (0, 0))
        ask(0, 3); ask(2, 4)
        assert any(value[1] is first for value in cache.searches.values())
        assert not any(key[2] == (0, 1) for key in cache.searches)
        ask(0, 7)


@pytest.mark.parametrize('seed', range(8))
def test_eviction_preserves_weighted_paths_modes_ties_and_unreachable_results(monkeypatch, seed):
    monkeypatch.setattr(route_plan, '_MAX_LOCAL_INVENTORY_SEARCHES', 2)
    rng = random.Random(seed)
    nodes = [(0, n) for n in range(15)]
    graph = LocalGraph({source: tuple(LocalEdge(
        target, 'right', cost=rng.choice([1, 1, 2, 5]),
        requirements=rng.choice([frozenset(), frozenset({'cut'})]),
        required_mode=rng.choice([None, 'walk', 'surf']),
        result_mode=rng.choice([None, 'walk', 'surf']))
        for target in rng.sample(nodes, 4)) for source in nodes})
    with route_plan.frozen_local_route_inventory() as cache:
        for turn in range(60):
            start = nodes[turn % 5]
            mode = [None, 'walk', 'surf'][turn % 3]
            capabilities = frozenset({'cut'}) if turn % 2 else frozenset()
            goals = {(rng.choice(nodes), rng.choice([None, 'walk', 'surf'])), ((99, 99), None)}
            _, got = cache.paths(graph, (), start, goals, capabilities, mode)
            expected = reference_paths(graph, start, goals, capabilities=capabilities, start_mode=mode)
            assert list(got.items()) == list(expected.items())
            assert len(cache.searches) <= 2


def test_zero_frontier_capacity_retains_stateless_fallback(monkeypatch):
    monkeypatch.setattr(route_plan, '_MAX_LOCAL_INVENTORY_SEARCHES', 0)
    graph = LocalGraph({(0, 0): (LocalEdge((0, 1), 'right'),)})
    goals = {((0, 1), None)}
    with route_plan.frozen_local_route_inventory() as cache:
        _, got = cache.paths(graph, (), (0, 0), goals, frozenset(), None)
        assert list(got.items()) == list(reference_paths(graph, (0, 0), goals).items())
        assert not cache.searches


def test_eviction_never_discards_mutation_evidence(monkeypatch):
    monkeypatch.setattr(route_plan, '_MAX_LOCAL_INVENTORY_SEARCHES', 1)
    edges = {(0, 0): (LocalEdge((0, 1), 'right'),)}
    first = LocalGraph(edges)
    second = LocalGraph({(1, 0): (LocalEdge((1, 1), 'right'),)})
    with pytest.raises(route_plan.RoutePlanningError, match='changed'), route_plan.frozen_local_route_inventory() as cache:
        cache.paths(first, (), (0, 0), {((0, 1), None)}, frozenset(), None)
        cache.paths(second, (), (1, 0), {((1, 1), None)}, frozenset(), None)
        assert len(cache.searches) == 1
        edges[(0, 0)] = ()
