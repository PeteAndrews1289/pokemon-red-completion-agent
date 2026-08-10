from __future__ import annotations

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.global_router import (
    MacroEdge,
    MacroGraph,
    MacroPath,
    MacroTransition,
)
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_plan import RoutePlanningError, compose_route, plan_route


def line(*coordinates: tuple[int, int]) -> LocalGraph:
    edges: dict[tuple[int, int], tuple[LocalEdge, ...]] = {}
    for source, target in zip(coordinates, coordinates[1:], strict=False):
        dy = target[0] - source[0]
        dx = target[1] - source[1]
        action = {(1, 0): "down", (-1, 0): "up", (0, 1): "right", (0, -1): "left"}[(dy, dx)]
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
    assert [(step.kind, step.expected_map, step.expected_at) for step in plan.steps] == [
        ("walk", 1, (1, 2)),
        ("walk", 1, (0, 2)),
        ("connection", 2, (7, 2)),
    ]


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
    assert plan.steps[-1].kind == "warp"
    assert plan.steps[-1].source_at == (0, 1)
    assert plan.steps[-1].expected_at == (7, 3)


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


def test_a_live_blocker_changes_the_composed_local_approach() -> None:
    transition = MacroTransition((0, 2), (7, 2), "up")
    macro = MacroGraph({1: (MacroEdge(2, coordinate_transitions=(transition,)),)})
    local = LocalGraph(
        {
            (0, 0): (
                LocalEdge((0, 1), action="right"),
                LocalEdge((1, 0), action="down"),
            ),
            (0, 1): (LocalEdge((0, 2), action="right"),),
            (1, 0): (LocalEdge((1, 1), action="right"),),
            (1, 1): (LocalEdge((1, 2), action="right"),),
            (1, 2): (LocalEdge((0, 2), action="up"),),
            (0, 2): (),
        }
    )

    original = plan_route(macro, {1: local}, 1, (0, 0), 2)
    replanned = plan_route(
        macro,
        {1: local},
        1,
        (0, 0),
        2,
        blocked={1: frozenset({(0, 1)})},
    )

    assert original.actions == ("right", "right", "up")
    assert replanned.actions == ("down", "right", "right", "up", "up")


def test_route_composition_preserves_field_actions_and_movement_modes() -> None:
    transition = MacroTransition((0, 2), (0, 0), "right")
    edge = MacroEdge(2, coordinate_transitions=(transition,), heading="east")
    graph = LocalGraph(
        {
            (0, 0): (
                LocalEdge(
                    (0, 1),
                    action="surf:right",
                    kind="water_entry",
                    action_kind=MacroActionKind.FIELD_MOVE,
                    required_mode="land",
                    result_mode="water",
                ),
            ),
            (0, 1): (
                LocalEdge(
                    (0, 2),
                    action="right",
                    kind="water_travel",
                    required_mode="water",
                ),
            ),
            (0, 2): (),
        }
    )

    plan = compose_route(
        MacroGraph({1: (edge,)}),
        MacroPath((1, 2), (edge,)),
        {1: graph},
        (0, 0),
        start_mode="land",
    )

    assert plan.macro_actions == (
        MacroAction(MacroActionKind.FIELD_MOVE, "surf:right"),
        MacroAction(MacroActionKind.MOVE, "right"),
        MacroAction(MacroActionKind.MOVE, "right"),
    )
    assert [(step.source_mode, step.expected_mode) for step in plan.steps] == [
        ("land", "water"),
        ("water", "water"),
        ("water", "water"),
    ]
    assert plan.terminal_mode == "water"


def test_a_same_map_goal_is_a_real_local_route_not_an_empty_macro_path() -> None:
    local = LocalGraph(
        {
            (0, 0): (
                LocalEdge(
                    (0, 1),
                    action="surf:right",
                    kind="water_entry",
                    action_kind=MacroActionKind.FIELD_MOVE,
                    required_mode="land",
                    result_mode="water",
                ),
            ),
            (0, 1): (LocalEdge((0, 2), action="right", required_mode="water"),),
            (0, 2): (),
        }
    )

    plan = plan_route(
        MacroGraph({1: ()}),
        {1: local},
        1,
        (0, 0),
        1,
        start_mode="land",
        goal_at=(0, 2),
        goal_mode="water",
    )

    assert plan.macro_path.maps == (1,)
    assert plan.segments == ()
    assert plan.terminal_approach is not None
    assert plan.actions == ("surf:right", "right")
    assert (plan.terminal_map, plan.terminal_at, plan.terminal_mode) == (
        1,
        (0, 2),
        "water",
    )


def test_a_terminal_local_goal_continues_from_the_exact_cross_map_arrival() -> None:
    transition = MacroTransition((0, 1), (4, 0), "right")
    edge = MacroEdge(2, coordinate_transitions=(transition,), heading="east")

    plan = compose_route(
        MacroGraph({1: (edge,), 2: ()}),
        MacroPath((1, 2), (edge,)),
        {
            1: line((0, 0), (0, 1)),
            2: line((4, 0), (4, 1), (4, 2)),
        },
        (0, 0),
        goal_at=(4, 2),
    )

    assert plan.actions == ("right", "right", "right", "right")
    assert plan.terminal_approach is not None
    assert plan.terminal_approach.coordinates == ((4, 0), (4, 1), (4, 2))
