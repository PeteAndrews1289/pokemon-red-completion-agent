"""Routing over a map graph, with no opinion about which game it came from.

This file used to search a hand-written five-node sketch of Kanto, and one of
its tests asserted that Saffron City was unreachable from Pallet Town. That was
true of the sketch and false of the game: the assertion had turned an absence of
data into a requirement, which is the failure mode the whole cartridge-reading
effort exists to remove.

So the graphs here are small and deliberately artificial. Whether Kanto is
joined correctly is a question about the cartridge, and it is asked in
``test_gen1_maps``.
"""

from __future__ import annotations

import pytest

from pokemon_red_completion.global_router import (
    GlobalRouterError,
    MacroEdge,
    MacroGraph,
    find_macro_path,
    find_macro_route,
)


def test_a_direct_edge_is_a_two_map_route() -> None:
    routed = find_macro_route(MacroGraph({1: (MacroEdge(2),)}), 1, 2)

    assert routed == (1, 2)


def test_a_route_to_where_you_already_are_is_a_single_map() -> None:
    assert find_macro_route(MacroGraph({}), 7, 7) == (7,)


def test_the_cheapest_path_wins_over_the_shortest() -> None:
    """The reason this is Dijkstra and not a breadth-first walk.

    Surfing is not free, and once traversal costs exist a route that takes an
    extra map to avoid an expensive edge is the right answer. A breadth-first
    search would return the two-hop path here.
    """

    routed = find_macro_route(
        MacroGraph(
            {
                1: (MacroEdge(2, cost=10), MacroEdge(3, cost=1)),
                3: (MacroEdge(4, cost=1),),
                4: (MacroEdge(2, cost=1),),
            }
        ),
        1,
        2,
    )

    assert routed == (1, 3, 4, 2)


def test_an_unreachable_goal_is_an_error_rather_than_an_empty_route() -> None:
    with pytest.raises(GlobalRouterError, match="no macro route"):
        find_macro_route(MacroGraph({1: (MacroEdge(2),)}), 1, 99)


def test_an_edge_carries_how_to_cross_it() -> None:
    """A warp needs a block to stand on; a connection does not.

    Collapsing the two would leave the caller knowing where to go and not how.
    """

    warp = MacroEdge(5, kind="warp", at=(7, 3))
    connection = MacroEdge(6, heading="north")

    assert warp.at == (7, 3)
    assert warp.kind == "warp"
    assert connection.at is None
    assert connection.kind == "connection"
    assert connection.heading == "north"


def test_an_actionable_path_keeps_the_exact_edges_selected() -> None:
    warp = MacroEdge(2, kind="warp", at=(7, 3))
    connection = MacroEdge(3, heading="east")

    path = find_macro_path(MacroGraph({1: (warp,), 2: (connection,)}), 1, 3)

    assert path.maps == (1, 2, 3)
    assert path.edges == (warp, connection)


def test_a_shared_interior_cannot_teleport_between_its_origins() -> None:
    """A return warp is legal only for the exterior that supplied its context."""

    graph = MacroGraph(
        {
            0: (MacroEdge(2, kind="warp"), MacroEdge(3)),
            1: (MacroEdge(2, kind="warp"),),
            2: (
                MacroEdge(0, kind="warp", return_origin=0),
                MacroEdge(1, kind="warp", return_origin=1),
            ),
            3: (MacroEdge(1),),
        }
    )

    assert find_macro_route(graph, 0, 1) == (0, 3, 1)
    assert find_macro_route(graph, 2, 0, entered_from=0) == (2, 0)
    with pytest.raises(GlobalRouterError):
        find_macro_route(MacroGraph({2: graph.edges[2]}), 2, 1, entered_from=0)


def test_an_edge_must_cost_something() -> None:
    """A free edge would let the search loop without ever settling."""

    with pytest.raises(ValueError, match="cost something"):
        MacroEdge(2, cost=0)
