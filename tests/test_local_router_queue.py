"""Path contracts across unit/weighted movement and queue promotion."""
from pokemon_red_completion.local_router import LocalEdge, LocalGraph, find_local_paths

S, A, B, G, X = (0, 0), (0, 1), (1, 0), (1, 1), (2, 0)


def test_unit_paths_keep_first_equal_cost_route():
    graph = LocalGraph({S: (LocalEdge(A, "a"), LocalEdge(B, "b")),
                        A: (LocalEdge(G, "a-goal"),), B: (LocalEdge(G, "b-goal"),)})
    path = find_local_paths(graph, S, {(G, None)})[(G, None)]
    assert path.coordinates == (S, A, G)
    assert tuple(e.action for e in path.edges) == ("a", "a-goal")


def test_late_weighted_edge_preserves_cheaper_pending_route():
    graph = LocalGraph({S: (LocalEdge(A, "a"), LocalEdge(B, "b")),
                        A: (LocalEdge(G, "costly", cost=3),),
                        B: (LocalEdge(G, "cheap"),)})
    assert find_local_paths(graph, S, {(G, None)})[(G, None)].coordinates == (S, B, G)


def test_fractional_weight_promotes_before_using_a_longer_unit_path():
    graph = LocalGraph({S: (LocalEdge(A, "a"), LocalEdge(B, "b")),
                        A: (LocalEdge(X, "fraction", cost=.25),),
                        X: (LocalEdge(G, "fraction-goal", cost=.25),),
                        B: (LocalEdge(G, "unit-goal"),)})
    path = find_local_paths(graph, S, {(G, None)})[(G, None)]
    assert path.coordinates == (S, A, X, G)
    assert sum(e.cost for e in path.edges) == 1.5


def test_promotion_retains_original_equal_priority_order():
    graph = LocalGraph({S: (LocalEdge(A, "a"), LocalEdge(B, "b"),
                            LocalEdge(X, "weighted-dead-end", cost=5)),
                        A: (LocalEdge(G, "first"),), B: (LocalEdge(G, "second"),)})
    assert find_local_paths(graph, S, {(G, None)})[(G, None)].coordinates == (S, A, G)


def test_exact_and_wildcard_goals_preserve_movement_modes():
    graph = LocalGraph({S: (LocalEdge(A, "surf", requirements=frozenset({"surf"}),
                                    result_mode="surf"),
                            LocalEdge(B, "walk", result_mode="walk")),
                        A: (LocalEdge(G, "water", required_mode="surf"),),
                        B: (LocalEdge(G, "land", required_mode="walk", cost=2),)})
    goals = {(G, None), (G, "surf"), (G, "walk"), (X, None)}
    found = find_local_paths(graph, S, goals, capabilities=frozenset({"surf"}))
    assert found[(G, None)] is found[(G, "surf")]
    assert found[(G, "surf")].modes == (None, "surf", "surf")
    assert found[(G, "walk")].coordinates == (S, B, G)
    assert (X, None) not in found


def test_unavailable_requirements_do_not_create_a_route():
    graph = LocalGraph({S: (LocalEdge(G, "blocked", requirements=frozenset({"cut"}),
                                    cost=.25), LocalEdge(A, "open")),
                        A: (LocalEdge(G, "open-goal"),)})
    assert find_local_paths(graph, S, {(G, None)})[(G, None)].coordinates == (S, A, G)


def test_weighted_search_replaces_a_stale_expensive_entry():
    graph = LocalGraph({S: (LocalEdge(G, "expensive", cost=10), LocalEdge(A, "a"),
                            LocalEdge(B, "b", cost=2)),
                        A: (LocalEdge(G, "medium", cost=4),),
                        B: (LocalEdge(G, "best", cost=.5),)})
    assert find_local_paths(graph, S, {(G, None)})[(G, None)].coordinates == (S, B, G)


def test_empty_and_current_position_goals():
    graph = LocalGraph({S: ()})
    assert find_local_paths(graph, S, set()) == {}
    found = find_local_paths(graph, S, {(S, None), (S, "surf")}, start_mode="surf")
    assert found[(S, None)] is found[(S, "surf")]
    assert found[(S, None)].coordinates == (S,)
    assert found[(S, None)].edges == ()


def test_new_query_observes_graph_changes():
    edges = {S: (LocalEdge(A, "a"),), A: (LocalEdge(G, "goal"),)}
    graph = LocalGraph(edges)
    assert (G, None) in find_local_paths(graph, S, {(G, None)})
    edges[A] = ()
    assert (G, None) not in find_local_paths(graph, S, {(G, None)})
