from dataclasses import replace

import pytest
from test_route_plan import line

from pokemon_red_completion import route_plan as routes
from pokemon_red_completion.global_router import MacroEdge, MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph


def world():
    graph = MacroGraph({
        1: (MacroEdge(2, kind="warp", at=(0, 1), arrival_at=(0, 0)),),
        2: (MacroEdge(3, kind="warp", at=(0, 1), arrival_at=(0, 0)),),
        3: (),
    })
    return graph, {i: line((0, 0), (0, 1), (0, 2)) for i in (1, 2, 3)}


def test_inventory_reuse_has_exact_route_parity_and_is_discarded(monkeypatch):
    graph, local = world()
    expected = [routes.plan_route(graph, local, 1, (0, 0), i) for i in (2, 3)]
    original, calls = routes.find_local_paths, []

    def measured(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(routes, "find_local_paths", measured)
    with routes.frozen_local_route_inventory() as cache:
        assert [routes.plan_route(graph, local, 1, (0, 0), i) for i in (2, 3)] == expected
        spent = len(calls)
        assert routes.plan_route(graph, local, 1, (0, 0), 3) == expected[1]
        assert len(calls) == spent and cache.hits >= 2
    assert cache.queries == cache.graphs == {}
    routes.plan_route(graph, local, 1, (0, 0), 3)
    assert len(calls) > spent


def test_inventory_keeps_goal_capability_blocker_and_warp_context_distinct():
    graph, local = world()
    local[1] = LocalGraph({
        (0, 0): (LocalEdge((0, 1), action="right", requirements=frozenset({"cut"})),),
        (0, 1): (LocalEdge((0, 2), action="right"),),
        (0, 2): (),
    })
    with routes.frozen_local_route_inventory():
        with pytest.raises(routes.RoutePlanningError):
            routes.plan_route(graph, local, 1, (0, 0), 2)
        assert routes.plan_route(graph, local, 1, (0, 0), 2,
                                 capabilities=frozenset({"cut"})).terminal_map == 2
        with pytest.raises(routes.RoutePlanningError):
            routes.plan_route(graph, local, 1, (0, 0), 2,
                              capabilities=frozenset({"cut"}), blocked={1: frozenset({(0, 1)})})
        assert routes.plan_route(graph, local, 1, (0, 0), 1, goal_at=(0, 1),
                                 capabilities=frozenset({"cut"})).terminal_at == (0, 1)
        assert routes.plan_route(graph, local, 1, (0, 0), 1, goal_at=(0, 2),
                                 capabilities=frozenset({"cut"})).terminal_at == (0, 2)
        inert = replace(graph, warp_locations={1: ((0, 1),)}, warp_triggers={1: ()})
        assert routes.plan_route(inert, local, 1, (0, 0), 1, goal_at=(0, 2),
                                 capabilities=frozenset({"cut"})).terminal_at == (0, 2)
        with pytest.raises(routes.RoutePlanningError):
            routes.plan_route(replace(inert, warp_triggers=None), local, 1, (0, 0), 1,
                              goal_at=(0, 2), capabilities=frozenset({"cut"}))


def test_in_place_edit_invalidates_inventory_even_if_inner_error_is_caught():
    graph, local = world()
    original = dict(local[1].edges)
    with (
        pytest.raises(routes.RoutePlanningError, match="changed a local graph"),
        routes.frozen_local_route_inventory(),
    ):
        routes.plan_route(graph, local, 1, (0, 0), 2)
        local[1].edges[(0, 0)] = ()
        with pytest.raises(routes.RoutePlanningError):
            routes.plan_route(graph, local, 1, (0, 0), 2)
        # Reverting an illicit edit does not restore cached authority.
        local[1].edges.clear()
        local[1].edges.update(original)
    assert routes._FROZEN_LOCAL_ROUTE_CACHE.get() is None


def test_nested_scope_reuses_parent_and_exception_restores_uncached_default():
    graph, local = world()
    with (
        pytest.raises(RuntimeError, match="observer failure"),
        routes.frozen_local_route_inventory() as outer,
    ):
        with routes.frozen_local_route_inventory() as inner:
            assert inner is outer
            routes.plan_route(graph, local, 1, (0, 0), 2)
        raise RuntimeError("observer failure")
    assert routes._FROZEN_LOCAL_ROUTE_CACHE.get() is None
    assert outer.queries == outer.graphs == {}


def test_mode_and_cached_path_mapping_are_not_shared_or_mutable():
    graph = LocalGraph({(0, 0): (LocalEdge((0, 1), action="right", required_mode="land"),),
                        (0, 1): ()})
    with routes.frozen_local_route_inventory() as cache:
        _, land = cache.paths(graph, (), (0, 0), {((0, 1), None)}, frozenset(), "land")
        _, water = cache.paths(graph, (), (0, 0), {((0, 1), None)}, frozenset(), "water")
        assert land and not water
        with pytest.raises(TypeError):
            land[((0, 1), None)] = None


def test_cache_bound_falls_back_to_normal_search_without_reusing_object_ids():
    graph, local = world()
    with routes.frozen_local_route_inventory() as cache:
        cache.graphs = {i: (LocalGraph({}), {}) for i in range(2048)}
        expected = routes.plan_route(graph, local, 1, (0, 0), 3)
        assert routes.plan_route(graph, local, 1, (0, 0), 3) == expected
        assert len(cache.graphs) == 2048 and not cache.queries
