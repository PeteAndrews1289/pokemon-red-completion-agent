from __future__ import annotations

import pytest

from pokemon_red_completion.local_router import (
    LocalEdge,
    LocalGraph,
    LocalRouterError,
    find_local_path,
    find_nearest_transition,
    without_coordinates,
)


def test_a_local_path_retains_the_exact_actions_selected() -> None:
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), action="right"),),
            (0, 1): (LocalEdge((0, 3), action="down", kind="ledge"),),
        }
    )

    path = find_local_path(graph, (0, 0), (0, 3))

    assert path.coordinates == ((0, 0), (0, 1), (0, 3))
    assert tuple(edge.action for edge in path.edges) == ("right", "down")
    assert tuple(edge.kind for edge in path.edges) == ("walk", "ledge")


def test_a_live_blocker_removes_both_entry_and_exit_edges() -> None:
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), action="right"),),
            (0, 1): (LocalEdge((0, 0), action="left"), LocalEdge((0, 2), action="right")),
            (0, 2): (LocalEdge((0, 1), action="left"),),
        }
    )

    filtered = without_coordinates(graph, {(0, 1)})

    assert (0, 1) not in filtered.edges
    assert filtered.neighbors((0, 0)) == ()
    assert filtered.neighbors((0, 2)) == ()


def test_missing_capability_closes_an_edge_instead_of_becoming_a_fallback() -> None:
    graph = LocalGraph(
        {
            (0, 0): (
                LocalEdge((0, 1), action="surf", requirements=frozenset({"surf"})),
            )
        }
    )

    with pytest.raises(LocalRouterError, match="no permitted local route"):
        find_local_path(graph, (0, 0), (0, 1))

    path = find_local_path(graph, (0, 0), (0, 1), capabilities=frozenset({"surf"}))
    assert path.edges[0].action == "surf"


def test_cost_selects_a_longer_looking_but_cheaper_route() -> None:
    graph = LocalGraph(
        {
            (0, 0): (
                LocalEdge((0, 2), action="expensive", cost=5),
                LocalEdge((0, 1), action="right", cost=1),
            ),
            (0, 1): (LocalEdge((0, 2), action="right", cost=1),),
        }
    )

    assert find_local_path(graph, (0, 0), (0, 2)).coordinates == (
        (0, 0),
        (0, 1),
        (0, 2),
    )


def test_a_zero_length_path_needs_no_edges() -> None:
    assert find_local_path(LocalGraph({}), (3, 4), (3, 4)).coordinates == ((3, 4),)


def test_the_nearest_transition_retains_its_approach_and_final_input() -> None:
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), action="right"),),
            (0, 1): (
                LocalEdge((0, 3), action="down", kind="ledge"),
                LocalEdge((0, 2), action="right"),
            ),
            (0, 2): (LocalEdge((0, 4), action="down", kind="ledge"),),
        }
    )

    planned = find_nearest_transition(graph, (0, 0), "ledge")

    assert planned.approach.coordinates == ((0, 0), (0, 1))
    assert planned.transition == LocalEdge((0, 3), action="down", kind="ledge")


def test_an_unavailable_transition_capability_does_not_count_as_nearest() -> None:
    graph = LocalGraph(
        {
            (0, 0): (
                LocalEdge(
                    (0, 1),
                    action="surf",
                    kind="water_entry",
                    requirements=frozenset({"surf"}),
                ),
            )
        }
    )

    with pytest.raises(LocalRouterError, match="no permitted water_entry"):
        find_nearest_transition(graph, (0, 0), "water_entry")

    assert find_nearest_transition(
        graph,
        (0, 0),
        "water_entry",
        capabilities=frozenset({"surf"}),
    ).transition.action == "surf"


def test_a_transition_query_needs_a_kind() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        find_nearest_transition(LocalGraph({}), (0, 0), "")


def test_local_edges_require_an_action_and_positive_cost() -> None:
    assert LocalEdge((0, 1), action="right").cost == 1
    with pytest.raises(ValueError, match="needs an action"):
        LocalEdge((0, 1), action="")
    with pytest.raises(ValueError, match="transition kind"):
        LocalEdge((0, 1), action="right", kind="")
    with pytest.raises(ValueError, match="must cost"):
        LocalEdge((0, 1), action="right", cost=0)
