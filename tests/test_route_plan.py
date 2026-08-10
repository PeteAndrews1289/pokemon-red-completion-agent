from __future__ import annotations

import pytest

from pokemon_red_completion.global_router import (
    MacroEdge,
    MacroGraph,
    MacroPath,
    MacroTransition,
)
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_plan import RoutePlanningError, compose_route


def line(*coordinates: tuple[int, int]) -> LocalGraph:
    edges: dict[tuple[int, int], tuple[LocalEdge, ...]] = {}
    for source, target in zip(coordinates, coordinates[1:], strict=False):
        dy = target[0] - source[0]
        dx = target[1] - source[1]
        action = {(1, 0): "down", (-1, 0): "up", (0, 1): "right", (0, -1): "left"}[
            (dy, dx)
        ]
        edges[source] = (LocalEdge(target, action=action),)
    edges.setdefault(coordinates[-1], ())
    return LocalGraph(edges)


def test_a_connection_selects_a_reachable_exact_endpoint() -> None:
    unreachable = MacroTransition((0, 9), (7, 9), "up")
    reachable = MacroTransition((0, 2), (7, 2), "up")
    edge = MacroEdge(
        2,
        coordinate_transitions=(unreachable, reachable),
        heading="north",
    )
    path = MacroPath((1, 2), (edge,))

    plan = compose_route(
        MacroGraph({1: (edge,)}),
        path,
        {1: line((2, 2), (1, 2), (0, 2))},
        (2, 2),
    )

    assert plan.actions == ("up", "up", "up")
    assert plan.segments[0].transition == reachable
    assert plan.terminal_at == (7, 2)
    assert plan.terminal_map == 2


def test_stepping_onto_a_warp_is_not_duplicated_as_an_extra_action() -> None:
    edge = MacroEdge(2, kind="warp", at=(0, 2), arrival_at=(7, 3))
    path = MacroPath((1, 2), (edge,))

    plan = compose_route(
        MacroGraph({1: (edge,)}),
        path,
        {1: line((0, 0), (0, 1), (0, 2))},
        (0, 0),
    )

    assert plan.actions == ("right", "right")
    assert plan.terminal_at == (7, 3)
    assert plan.segments[0].transition_action_in_approach


def test_a_return_resolves_its_arrival_after_its_map_target() -> None:
    edge = MacroEdge(
        None,
        kind="return",
        at=(1, 1),
        destination_warp_index=1,
    )
    path = MacroPath((2, 0), (edge,))
    graph = MacroGraph(
        {2: (edge,)},
        warp_locations={0: ((8, 8), (9, 4))},
    )

    plan = compose_route(
        graph,
        path,
        {2: line((1, 0), (1, 1))},
        (1, 0),
    )

    assert plan.terminal_at == (9, 4)
    assert plan.actions == ("right",)


def test_composition_refuses_to_invent_how_to_retrigger_a_warp() -> None:
    edge = MacroEdge(2, kind="warp", at=(0, 0), arrival_at=(1, 1))

    with pytest.raises(RoutePlanningError, match="begins on a warp trigger"):
        compose_route(
            MacroGraph({1: (edge,)}),
            MacroPath((1, 2), (edge,)),
            {1: line((0, 0), (0, 1))},
            (0, 0),
        )
