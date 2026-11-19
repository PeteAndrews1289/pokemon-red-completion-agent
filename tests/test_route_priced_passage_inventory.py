from dataclasses import replace

import pytest
from test_route_shared_approach_cost import fixture

from pokemon_red_completion import route_plan as routes


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('weighted', [False, True])
def test_sibling_destinations_reuse_passages_without_changing_any_plan(monkeypatch, reverse, weighted):
    graph, local, sink, branches = fixture(reverse=reverse, weighted=weighted)
    destinations = [*branches, sink]
    expected = [routes.plan_route(graph, local, 1, (0, 0), goal) for goal in destinations]
    original, calls = routes._compose_segment_candidates, []
    def measured(*a, **kw):
        calls.append(1)
        return original(*a, **kw)
    monkeypatch.setattr(routes, '_compose_segment_candidates', measured)
    for goal in destinations:
        routes.plan_route(graph, local, 1, (0, 0), goal)
    without_reuse = len(calls)
    calls.clear()
    with routes.frozen_local_route_inventory() as cache:
        observed = [routes.plan_route(graph, local, 1, (0, 0), goal) for goal in destinations]
        assert observed == expected
        assert cache.passage_hits > 0 and len(calls) < without_reuse
    assert not cache.priced_passages
    assert routes._FROZEN_LOCAL_ROUTE_CACHE.get() is None


@pytest.mark.parametrize('capacity', [0, 1, 3])
def test_bounded_memory_fallback_keeps_routes_and_errors(monkeypatch, capacity):
    graph, local, sink, branches = fixture()
    monkeypatch.setattr(routes, '_MAX_INVENTORY_PASSAGES', capacity)
    expected = [routes.plan_route(graph, local, 1, (0, 0), goal) for goal in [*branches, sink]]
    with routes.frozen_local_route_inventory() as cache:
        assert [routes.plan_route(graph, local, 1, (0, 0), goal) for goal in [*branches, sink]] == expected
        assert len(cache.priced_passages) <= capacity
        with pytest.raises(routes.RoutePlanningError, match='no locally composable route'):
            routes.plan_route(graph, local, 1, (0, 0), 999)


@pytest.mark.parametrize('change', ['blocker', 'mode', 'capability', 'target_graph'])
def test_sibling_query_never_reuses_changed_semantics(change):
    graph, local, sink, branches = fixture()
    kwargs = {}
    changed = dict(local)
    if change == 'blocker':
        kwargs['blocked'] = {branches[0]: frozenset({(0, 1)})}
    elif change == 'mode':
        kwargs['start_mode'] = 'water'
    elif change == 'capability':
        kwargs['capabilities'] = frozenset({'cut'})
    else:
        changed[branches[0]] = replace(local[branches[0]], edges={(0, 0): (), (0, 1): ()})
    expected = routes.plan_route(graph, changed, 1, (0, 0), sink, **kwargs)
    with routes.frozen_local_route_inventory():
        routes.plan_route(graph, local, 1, (0, 0), branches[0])
        assert routes.plan_route(graph, changed, 1, (0, 0), sink, **kwargs) == expected


def test_scope_exception_clears_retained_passages_before_next_observation():
    graph, local, sink, branches = fixture()
    with pytest.raises(RuntimeError, match='boundary failed'):
        with routes.frozen_local_route_inventory() as cache:
            routes.plan_route(graph, local, 1, (0, 0), branches[0])
            routes.plan_route(graph, local, 1, (0, 0), sink)
            assert cache.priced_passages
            raise RuntimeError('boundary failed')
    assert not cache.priced_passages and routes._FROZEN_LOCAL_ROUTE_CACHE.get() is None
    before = routes.plan_route(graph, local, 1, (0, 0), sink)
    old = local[1].edges[(0, 0)][0]
    local[1].edges[(0, 0)] = (replace(old, cost=old.cost+17),)
    assert routes.plan_route(graph, local, 1, (0, 0), sink).cost == before.cost+17
