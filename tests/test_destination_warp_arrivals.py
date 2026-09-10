"""Destination semantics, not a source-direction guess, determine warp landing."""

from dataclasses import replace

import pytest
from test_route_plan import line

from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_maps import (
    MapNode,
    Passage,
    PassageKind,
    _with_warp_arrivals,
    macro_graph_from_nodes,
)
from pokemon_red_completion.global_router import MacroPath
from pokemon_red_completion.route_plan import RoutePlanningError, compose_route


def qualified_nodes(*, returning: bool = False, door: bool = True):
    # Two destinations deliberately differ: using the wrong warp index cannot pass.
    source = MapNode(
        10,
        2,
        2,
        (
            Passage(
                None if returning else 20,
                PassageKind.RETURN if returning else PassageKind.WARP,
                at=(1, 1),
                arrival_at=None if returning else (2, 1),
                destination_warp_index=1,
            ),
        ),
        tileset=7,
    )
    target = MapNode(20, 2, 2, (), tileset=9, warp_locations=((0, 0), (2, 1)))
    grids = {
        10: ((0, 0, 0, 0),) * 4,
        20: ((0, 0, 0, 0), (0, 0, 0, 0), (0, 0x58, 0, 0), (0, 0, 0, 0)),
    }
    return _with_warp_arrivals(
        {10: source, 20: target}, grids, {7: frozenset(), 9: frozenset({0x58} if door else {})}
    )


@pytest.mark.parametrize("returning", [False, True])
@pytest.mark.parametrize("door, expected", [(True, (3, 1)), (False, (2, 1))])
def test_destination_tile_controls_left_entered_ordinary_and_return_warps(
    returning,
    door,
    expected,
):
    nodes = qualified_nodes(returning=returning, door=door)
    graph = macro_graph_from_nodes(nodes)
    edge = graph.neighbors(10)[0]
    plan = compose_route(graph, MacroPath((10, 20), (edge,)), {10: line((1, 2), (1, 1))}, (1, 2))
    assert plan.actions == ("left",)
    assert plan.terminal_at == expected
    assert plan.steps[-1].expected_at == expected
    assert graph.warp_locations[20] == ((0, 0), (2, 1))
    assert graph.warp_arrivals[20][0] == (0, 0)


def test_explicit_nondoor_arrival_does_not_inherit_legacy_south_exit_guess():
    nodes = qualified_nodes(returning=True, door=False)
    graph = macro_graph_from_nodes(nodes)
    edge = replace(graph.neighbors(10)[0], exit_action="down")
    graph = replace(graph, edges={10: (edge,), 20: ()})
    plan = compose_route(graph, MacroPath((10, 20), (edge,)), {10: line((1, 1))}, (1, 1))
    assert plan.actions == ("down",)
    assert plan.terminal_at == (2, 1)


@pytest.mark.parametrize("arrivals", [{}, {20: ((0, 0),)}])
def test_incomplete_explicit_arrivals_cannot_fall_back_to_geometry(arrivals):
    graph = replace(macro_graph_from_nodes(qualified_nodes()), warp_arrivals=arrivals)
    edge = graph.neighbors(10)[0]
    with pytest.raises(RoutePlanningError, match="declared destination arrivals"):
        compose_route(graph, MacroPath((10, 20), (edge,)), {10: line((1, 2), (1, 1))}, (1, 2))


def test_inconsistent_raw_arrival_and_destination_index_fail_closed():
    graph = macro_graph_from_nodes(qualified_nodes())
    edge = replace(graph.neighbors(10)[0], arrival_at=(0, 0))
    with pytest.raises(RoutePlanningError, match="declared destination arrivals"):
        compose_route(graph, MacroPath((10, 20), (edge,)), {10: line((1, 2), (1, 1))}, (1, 2))


def test_projection_rejects_mixed_arrival_qualification():
    nodes = qualified_nodes()
    nodes[10] = replace(nodes[10], warp_arrivals=None)
    with pytest.raises(CartridgeReadError, match="qualification is incomplete"):
        macro_graph_from_nodes(nodes)


@pytest.mark.parametrize("at, tile", [((4, 0), 0), ((3, 1), 0x58)])
def test_arrival_cannot_escape_destination_terrain(at, tile):
    node = MapNode(20, 2, 2, (), tileset=9, warp_locations=(at,))
    with pytest.raises(CartridgeReadError, match="destination terrain"):
        _with_warp_arrivals({20: node}, {20: ((tile,) * 4,) * 4}, {9: frozenset({0x58})})
