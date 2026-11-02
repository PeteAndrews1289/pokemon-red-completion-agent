"""Absorbing warp and safe departure contracts across graph projections."""
import pytest

from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_plan import without_warp_transit


def test_nonwarp_start_absorbs_every_warp_without_mutating_the_graph():
    edge = LocalEdge((0, 1), "right")
    graph = LocalGraph({(0, 0): (edge,), (0, 1): (), (1, 0): ()})
    projected = without_warp_transit(graph, ((0, 0), (0, 1)), start_at=(1, 0))
    assert projected.edges == {(0, 0): (), (0, 1): (), (1, 0): ()}
    assert graph.edges[(0, 0)] == (edge,)
    assert projected is not graph


def test_starting_warp_keeps_safe_inward_departures():
    inward = LocalEdge((1, 0), "down")
    outward = LocalEdge((-1, 0), "up")
    graph = LocalGraph({(0, 0): (outward, inward), (1, 0): (), (3, 3): ()})
    projected = without_warp_transit(graph, ((0, 0),), start_at=(0, 0))
    assert projected.edges[(0, 0)] == (inward,)
    assert graph.edges[(0, 0)] == (outward, inward)


def test_bottom_right_warp_keeps_only_inward_departures():
    up, left = LocalEdge((2, 3), "up"), LocalEdge((3, 2), "left")
    down, right = LocalEdge((4, 3), "down"), LocalEdge((3, 4), "right")
    edges = {(y, x): () for y in range(5) for x in range(5)}
    edges[3, 3] = (up, down, left, right)
    projected = without_warp_transit(LocalGraph(edges), ((3, 3),), start_at=(3, 3))
    assert projected.edges[3, 3] == (up, left)


def test_no_warps_preserve_graph_identity_including_empty_graphs():
    graph = LocalGraph({})
    assert without_warp_transit(graph, (), start_at=(0, 0)) is graph


def test_empty_graph_with_declared_warps_still_refuses():
    with pytest.raises(ValueError):
        without_warp_transit(LocalGraph({}), ((0, 0),), start_at=(1, 1))


def test_absent_warp_coordinates_are_never_invented():
    graph = LocalGraph({(0, 0): ()})
    projected = without_warp_transit(graph, ((1, 1),), start_at=(2, 2))
    assert projected.edges == {(0, 0): ()}


def test_unaffected_weighted_mode_edges_retain_identity_and_requirements():
    edge = LocalEdge((1, 2), "surf", cost=3, required_mode="surf",
                     requirements=frozenset({"surf"}))
    graph = LocalGraph({(1, 1): (edge,), (1, 2): (), (0, 0): ()})
    projected = without_warp_transit(graph, ((0, 0),), start_at=(1, 1))
    assert projected.edges[(1, 1)] is graph.edges[(1, 1)]
    assert projected.edges[(1, 1)][0] is edge


def test_projected_mapping_does_not_follow_later_source_mapping_changes():
    edge = LocalEdge((1, 2), "right")
    edges = {(1, 1): (edge,), (1, 2): (), (0, 0): ()}
    projected = without_warp_transit(LocalGraph(edges), ((0, 0),), start_at=(1, 1))
    edges[(1, 1)] = ()
    assert projected.edges[(1, 1)] == (edge,)
