from dataclasses import replace

import pytest
from test_route_plan_inventory_cache import world
from pokemon_red_completion import route_plan as routes
from pokemon_red_completion.global_router import MacroGraph


def _count_compositions(monkeypatch):
    original = routes._find_composed_route
    calls = []
    def measured(*a, **kw):
        calls.append((a, kw))
        return original(*a, **kw)
    monkeypatch.setattr(routes, '_find_composed_route', measured)
    return calls


def test_complete_query_reuse_has_exact_parity_and_ends_with_observation(monkeypatch):
    graph, local = world()
    expected = routes.plan_route(graph, local, 1, (0, 0), 3)
    calls = _count_compositions(monkeypatch)
    with routes.frozen_local_route_inventory() as cache:
        for _ in range(8):
            assert routes.plan_route(graph, local, 1, (0, 0), 3) == expected
        assert len(calls) == 1 and cache.route_hits == 7
        assert routes.plan_route(graph, dict(local), 1, (0, 0), 3) == expected
        assert len(calls) == 1
    assert cache.routes == cache.route_macro_graphs == cache.route_worlds == {}
    routes.plan_route(graph, local, 1, (0, 0), 3)
    assert len(calls) == 2


@pytest.mark.parametrize('change', [
    {'capabilities': frozenset({'cut'})}, {'blocked': {2: frozenset({(0, 1)})}},
    {'last_outside': 7}, {'start_mode': 'land'},
    {'goal_at': (0, 1)}, {'goal_at': (0, 1), 'goal_mode': 'water'},
])
def test_complete_query_keeps_every_semantic_input_distinct(monkeypatch, change):
    graph, local = world()
    try:
        expected = routes.plan_route(graph, local, 1, (0, 0), 3, **change)
    except routes.RoutePlanningError as error:
        expected = error.args
    calls = _count_compositions(monkeypatch)
    with routes.frozen_local_route_inventory():
        routes.plan_route(graph, local, 1, (0, 0), 3)
        try:
            observed = routes.plan_route(graph, local, 1, (0, 0), 3, **change)
        except routes.RoutePlanningError as error:
            observed = error.args
        assert observed == expected
        assert len(calls) == 2


@pytest.mark.parametrize('field', ['edges', 'warp_locations', 'retained_outside_overrides', 'warp_arrivals', 'warp_triggers', 'outside_nodes'])
def test_complete_cache_rejects_macro_mutation_even_if_reverted(field):
    graph, local = world()
    if field in ('warp_arrivals', 'warp_triggers'):
        graph = replace(graph, **{field: {}})
    with pytest.raises(routes.RoutePlanningError, match='changed.*graph'), routes.frozen_local_route_inventory():
        routes.plan_route(graph, local, 1, (0, 0), 1)
        old = getattr(graph, field)
        saved = dict(old) if isinstance(old, dict) else old
        if field == 'outside_nodes':
            object.__setattr__(graph, field, frozenset({99}))
        else:
            old[99] = 1 if field == 'retained_outside_overrides' else ()
        with pytest.raises(routes.RoutePlanningError):
            routes.plan_route(graph, local, 1, (0, 0), 1)
        if field == 'outside_nodes':
            object.__setattr__(graph, field, saved)
        else:
            old.clear(); old.update(saved)


def test_complete_cache_rejects_local_inventory_membership_change():
    graph, local = world()
    with pytest.raises(routes.RoutePlanningError, match='changed.*graph'), routes.frozen_local_route_inventory():
        routes.plan_route(graph, local, 1, (0, 0), 3)
        local[99] = local[1]
        with pytest.raises(routes.RoutePlanningError, match='local map inventory'):
            routes.plan_route(graph, local, 1, (0, 0), 3)
        del local[99]


def test_plain_failures_are_recreated_with_same_args_without_recomposing(monkeypatch):
    graph, local = world()
    calls = _count_compositions(monkeypatch)
    errors = []
    with routes.frozen_local_route_inventory():
        for _ in range(2):
            with pytest.raises(routes.RoutePlanningError) as caught:
                routes.plan_route(graph, local, 1, (0, 0), 99)
            errors.append(caught.value)
    assert len(calls) == 1 and errors[0] is not errors[1]
    assert errors[0].args == errors[1].args


def test_complex_failure_chain_is_never_flattened_or_cached(monkeypatch):
    graph, local = world()
    calls = []
    def failure(*a, **kw):
        calls.append(1)
        raise routes.RoutePlanningError('retained native error') from ValueError('inner cause')
    monkeypatch.setattr(routes, '_find_composed_route', failure)
    with routes.frozen_local_route_inventory() as cache:
        for _ in range(2):
            with pytest.raises(routes.RoutePlanningError) as caught:
                routes.plan_route(graph, local, 1, (0, 0), 3)
            assert isinstance(caught.value.__cause__, ValueError)
        assert not cache.routes
    assert len(calls) == 2


def test_complete_query_memory_bound_falls_back_to_existing_algorithm(monkeypatch):
    graph, local = world()
    calls = _count_compositions(monkeypatch)
    with routes.frozen_local_route_inventory() as cache:
        cache.routes = {('occupied', i): (False, ()) for i in range(1024)}
        a = routes.plan_route(graph, local, 1, (0, 0), 3)
        b = routes.plan_route(graph, local, 1, (0, 0), 3)
        assert a == b and len(cache.routes) == 1024
    assert len(calls) == 2


def test_dynamic_macro_subclass_bypasses_complete_query_cache(monkeypatch):
    graph, local = world()
    class DynamicGraph(MacroGraph):
        pass
    graph = DynamicGraph(graph.edges)
    calls = _count_compositions(monkeypatch)
    with routes.frozen_local_route_inventory() as cache:
        a = routes.plan_route(graph, local, 1, (0, 0), 3)
        b = routes.plan_route(graph, local, 1, (0, 0), 3)
        assert a == b and not cache.routes
    assert len(calls) == 2
