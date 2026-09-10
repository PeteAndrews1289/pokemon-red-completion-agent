"""Projection semantics and the measured unnecessary edge-copying regression."""
from __future__ import annotations

import pytest

from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_plan import without_warp_transit


def grid():
    return {
        (y, x): tuple(
            LocalEdge((y + dy, x + dx), action)
            for dy, dx, action in ((-1, 0, "up"), (1, 0, "down"),
                                   (0, -1, "left"), (0, 1, "right"))
            if 0 <= y + dy < 5 and 0 <= x + dx < 5
        ) for y in range(5) for x in range(5)
    }


@pytest.mark.parametrize("start,allowed", [
    ((1, 2), {"left", "right", "down"}),
    ((3, 2), {"left", "right", "up"}),
    ((2, 1), {"up", "down", "right"}),
    ((2, 3), {"up", "down", "left"}),
    ((2, 2), {"up", "down", "left", "right"}),
])
def test_start_departure_preserves_all_four_border_rules(start, allowed):
    edges = grid()
    original = dict(edges)
    projected = without_warp_transit(LocalGraph(edges), (start, (4, 4)), start_at=start)
    assert {e.action for e in projected.edges[start]} == allowed
    assert projected.edges[(4, 4)] == ()
    assert edges == original
    assert projected.edges[(0, 0)] is edges[(0, 0)]


def test_projection_does_not_iterate_unaffected_exit_tuples():
    class UntouchedTuple(tuple):
        def __iter__(self):
            pytest.fail("projection iterated an unaffected tile's exits")

    edges = grid()
    edges[(2, 2)] = UntouchedTuple(edges[(2, 2)])
    projected = without_warp_transit(LocalGraph(edges), ((0, 0), (99, 99)), start_at=(1, 1))
    assert projected.edges[(2, 2)] is edges[(2, 2)]
    assert projected.edges[(0, 0)] == ()
    assert set(projected.edges) == set(edges)
    assert projected.edges is not edges


def test_new_call_observes_graph_and_start_changes_without_mutating_prior_projection():
    edges = grid()
    graph = LocalGraph(edges)
    first = without_warp_transit(graph, ((2, 2),), start_at=(1, 1))
    assert first.edges[(2, 2)] == ()
    edges[(2, 2)] = (LocalEdge((2, 3), "right"),)
    second = without_warp_transit(graph, ((2, 2),), start_at=(2, 2))
    assert second.edges[(2, 2)] == (LocalEdge((2, 3), "right"),)
    assert first.edges[(2, 2)] == ()
    assert without_warp_transit(graph, (), start_at=(1, 1)) is graph
