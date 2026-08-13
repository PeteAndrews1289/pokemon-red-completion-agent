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


def test_a_connection_rejects_unusable_destination_coordinates_and_modes() -> None:
    """Route 21 must arrive on Cinnabar water, not collision or dry land."""

    absent = MacroTransition((0, 1), (0, 8), "down")
    wrong_mode = MacroTransition((0, 2), (0, 10), "down")
    usable_water = MacroTransition((0, 3), (0, 3), "down")
    edge = MacroEdge(
        2,
        coordinate_transitions=(absent, wrong_mode, usable_water),
        heading="south",
    )
    target = LocalGraph(
        {
            (0, 10): (LocalEdge((1, 10), action="down", required_mode="land"),),
            (1, 10): (),
            (0, 3): (
                LocalEdge(
                    (1, 3),
                    action="down",
                    kind="water_travel",
                    required_mode="water",
                ),
            ),
            (1, 3): (),
        }
    )

    plan = compose_route(
        MacroGraph({1: (edge,), 2: ()}),
        MacroPath((1, 2), (edge,)),
        {1: line((0, 0), (0, 1), (0, 2), (0, 3)), 2: target},
        (0, 0),
        start_mode="water",
    )

    assert plan.segments[0].transition == usable_water
    assert plan.terminal_at == (0, 3)
    assert plan.terminal_mode == "water"


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


def test_pass_through_gate_warp_uses_a_second_inward_action() -> None:
    edge = MacroEdge(
        2,
        kind="warp",
        at=(4, 1),
        arrival_at=(3, 0),
        exit_action="right",
    )

    plan = compose_route(
        MacroGraph({1: (edge,)}),
        MacroPath((1, 2), (edge,)),
        {1: line((4, 0), (4, 1))},
        (4, 0),
    )

    assert plan.actions == ("right", "right")
    assert not plan.segments[0].transition_action_in_approach
    assert plan.steps[0].expected_map == 1
    assert plan.steps[0].expected_at == (4, 1)
    assert plan.steps[1].source_at == (4, 1)
    assert plan.steps[1].expected_map == 2
    assert plan.steps[1].expected_at == (3, 0)


def test_south_facing_ordinary_warp_lands_beyond_the_destination_door() -> None:
    """Route 2 -> Viridian Forest north gate is a directional ordinary warp."""

    edge = MacroEdge(
        47,
        kind="warp",
        at=(11, 3),
        arrival_at=(0, 5),
        exit_action="down",
        destination_warp_index=1,
    )
    automatic_return = MacroEdge(
        None,
        kind="return",
        at=(0, 5),
        destination_warp_index=1,
    )

    plan = compose_route(
        MacroGraph({13: (edge,), 47: (automatic_return,)}),
        MacroPath((13, 47), (edge,)),
        {13: line((11, 3))},
        (11, 3),
    )

    assert plan.actions == ("down",)
    assert plan.terminal_at == (1, 5)
    assert not plan.segments[0].transition_action_in_approach
    assert plan.steps[-1].source_map == 13
    assert plan.steps[-1].source_at == (11, 3)
    assert plan.steps[-1].expected_map == 47
    assert plan.steps[-1].expected_at == (1, 5)


def test_south_facing_ordinary_warp_stays_on_directional_destination() -> None:
    """Route 6 -> Underground Path lands on a return that still needs Up."""

    edge = MacroEdge(
        73,
        kind="warp",
        at=(1, 9),
        arrival_at=(0, 3),
        exit_action="down",
        destination_warp_index=2,
    )
    directional_return = MacroEdge(
        None,
        kind="return",
        at=(0, 3),
        exit_action="up",
        destination_warp_index=1,
    )

    plan = compose_route(
        MacroGraph({17: (edge,), 73: (directional_return,)}),
        MacroPath((17, 73), (edge,)),
        {17: line((1, 9))},
        (1, 9),
    )

    assert plan.actions == ("down",)
    assert plan.terminal_at == (0, 3)
    assert not plan.segments[0].transition_action_in_approach
    assert plan.steps[-1].expected_at == (0, 3)


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


def test_a_boundary_return_walks_out_and_lands_beyond_the_destination_door() -> None:
    edge = MacroEdge(
        None,
        kind="return",
        at=(7, 3),
        exit_action="down",
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
        {2: line((6, 3), (7, 3))},
        (7, 3),
    )

    assert plan.actions == ("down",)
    assert plan.terminal_at == (10, 4)
    assert not plan.segments[0].transition_action_in_approach
    assert plan.steps[-1].source_at == (7, 3)
    assert plan.steps[-1].expected_at == (10, 4)


def test_an_automatic_top_boundary_return_triggers_on_entry() -> None:
    edge = MacroEdge(
        None,
        kind="return",
        at=(0, 3),
        destination_warp_index=1,
    )
    path = MacroPath((62, 3), (edge,))
    graph = MacroGraph(
        {62: (edge,)},
        warp_locations={3: ((11, 27), (9, 27))},
    )

    plan = compose_route(
        graph,
        path,
        {62: line((2, 3), (1, 3), (0, 3))},
        (2, 3),
    )

    assert plan.actions == ("up", "up")
    assert plan.terminal_at == (9, 27)
    assert plan.segments[0].transition_action_in_approach
    assert plan.steps[-1].source_map == 62
    assert plan.steps[-1].source_at == (1, 3)
    assert plan.steps[-1].expected_map == 3
    assert plan.steps[-1].expected_at == (9, 27)


def test_a_directional_top_boundary_return_needs_outward_input() -> None:
    edge = MacroEdge(
        None,
        kind="return",
        at=(0, 3),
        exit_action="up",
        destination_warp_index=1,
    )
    path = MacroPath((73, 17), (edge,))
    graph = MacroGraph(
        {73: (edge,)},
        warp_locations={17: ((1, 9), (1, 10))},
    )

    plan = compose_route(
        graph,
        path,
        {73: line((2, 3), (1, 3), (0, 3))},
        (2, 3),
    )

    assert plan.actions == ("up", "up", "up")
    assert plan.terminal_at == (1, 10)
    assert not plan.segments[0].transition_action_in_approach
    assert plan.steps[-1].source_map == 73
    assert plan.steps[-1].source_at == (0, 3)
    assert plan.steps[-1].expected_map == 17
    assert plan.steps[-1].expected_at == (1, 10)


def test_an_internally_approached_bottom_boundary_return_needs_outward_input() -> None:
    edge = MacroEdge(
        None,
        kind="return",
        at=(7, 4),
        exit_action="down",
        destination_warp_index=1,
    )
    path = MacroPath((74, 17), (edge,))
    graph = MacroGraph(
        {74: (edge,)},
        warp_locations={17: ((12, 17), (13, 17))},
    )

    plan = compose_route(
        graph,
        path,
        {74: line((4, 4), (5, 4), (6, 4), (7, 4))},
        (4, 4),
    )

    assert plan.actions == ("down", "down", "down", "down")
    assert plan.terminal_at == (14, 17)
    assert not plan.segments[0].transition_action_in_approach
    assert plan.steps[-1].source_map == 74
    assert plan.steps[-1].source_at == (7, 4)
    assert plan.steps[-1].expected_map == 17
    assert plan.steps[-1].expected_at == (14, 17)


def test_a_horizontal_boundary_return_settles_on_the_outside_warp() -> None:
    """Gen I pass-through gates do not play the vertical door walk-out."""

    edge = MacroEdge(
        None,
        kind="return",
        at=(4, 5),
        exit_action="right",
        destination_warp_index=1,
    )
    path = MacroPath((76, 18), (edge,))
    graph = MacroGraph(
        {76: (edge,)},
        warp_locations={18: ((9, 18), (10, 18))},
    )

    plan = compose_route(
        graph,
        path,
        {76: line((4, 4), (4, 5))},
        (4, 5),
    )

    assert plan.actions == ("right",)
    assert plan.terminal_at == (10, 18)
    assert not plan.segments[0].transition_action_in_approach
    assert plan.steps[-1].expected_at == (10, 18)


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


def test_joint_search_prefers_more_maps_when_the_real_local_route_is_cheaper() -> None:
    direct = MacroEdge(
        2,
        coordinate_transitions=(MacroTransition((0, 5), (4, 0), "right"),),
    )
    detour = MacroEdge(
        3,
        coordinate_transitions=(MacroTransition((0, 1), (0, 0), "right"),),
    )
    finish = MacroEdge(
        2,
        coordinate_transitions=(MacroTransition((0, 1), (4, 0), "right"),),
    )

    plan = plan_route(
        MacroGraph({1: (direct, detour), 3: (finish,)}),
        {
            1: line(*((0, x) for x in range(6))),
            3: line((0, 0), (0, 1)),
        },
        1,
        (0, 0),
        2,
    )

    assert plan.macro_path.maps == (1, 3, 2)
    assert plan.actions == ("right", "right", "right", "right")
    assert plan.cost == 4


def test_joint_search_skips_a_topological_edge_with_no_local_approach() -> None:
    unreachable_direct = MacroEdge(2, kind="warp", at=(9, 9), arrival_at=(4, 0))
    detour = MacroEdge(
        3,
        coordinate_transitions=(MacroTransition((0, 1), (0, 0), "right"),),
    )
    finish = MacroEdge(
        2,
        coordinate_transitions=(MacroTransition((0, 1), (4, 0), "right"),),
    )

    plan = plan_route(
        MacroGraph({1: (unreachable_direct, detour), 3: (finish,)}),
        {
            1: line((0, 0), (0, 1)),
            3: line((0, 0), (0, 1)),
        },
        1,
        (0, 0),
        2,
    )

    assert plan.macro_path.maps == (1, 3, 2)
    assert unreachable_direct not in plan.macro_path.edges


def test_terminal_local_cost_is_part_of_the_cross_map_choice() -> None:
    expensive_arrival = MacroEdge(
        2,
        coordinate_transitions=(MacroTransition((0, 1), (0, 0), "right"),),
    )
    detour = MacroEdge(
        3,
        coordinate_transitions=(MacroTransition((0, 2), (0, 0), "right"),),
    )
    cheap_arrival = MacroEdge(
        2,
        coordinate_transitions=(MacroTransition((0, 1), (0, 9), "right"),),
    )

    plan = plan_route(
        MacroGraph({1: (expensive_arrival, detour), 3: (cheap_arrival,)}),
        {
            1: line((0, 0), (0, 1), (0, 2)),
            2: line(*((0, x) for x in range(11))),
            3: line((0, 0), (0, 1)),
        },
        1,
        (0, 0),
        2,
        goal_at=(0, 10),
    )

    assert plan.macro_path.maps == (1, 3, 2)
    assert plan.segments[-1].transition.arrival_at == (0, 9)
    assert plan.terminal_approach is not None
    assert plan.terminal_approach.coordinates == ((0, 9), (0, 10))
    assert plan.cost == 6


def test_joint_search_keeps_connection_endpoints_open_for_downstream_cost() -> None:
    first_connection = MacroEdge(
        2,
        coordinate_transitions=(
            MacroTransition((0, 1), (0, 0), "right"),
            MacroTransition((0, 2), (0, 9), "right"),
        ),
    )
    finish = MacroEdge(
        3,
        coordinate_transitions=(MacroTransition((0, 10), (0, 0), "right"),),
    )

    plan = plan_route(
        MacroGraph({1: (first_connection,), 2: (finish,)}),
        {
            1: line((0, 0), (0, 1), (0, 2)),
            2: line(*((0, x) for x in range(11))),
        },
        1,
        (0, 0),
        3,
    )

    assert plan.macro_path.maps == (1, 2, 3)
    assert plan.segments[0].transition.exit_at == (0, 2)
    assert plan.segments[0].transition.arrival_at == (0, 9)
    assert plan.cost == 5


def test_joint_search_can_leave_and_return_to_another_local_component() -> None:
    enter = MacroEdge(2, kind="warp", at=(0, 1), arrival_at=(0, 0))
    nested = MacroEdge(3, kind="warp", at=(0, 1), arrival_at=(0, 0))
    return_outside = MacroEdge(
        None,
        kind="return",
        at=(0, 1),
        destination_warp_index=0,
    )
    outside_local = line((0, 0), (0, 1))
    outside_local = LocalGraph({**outside_local.edges, (9, 9): ()})

    plan = plan_route(
        MacroGraph(
            {1: (enter,), 2: (nested,), 3: (return_outside,)},
            outside_nodes=frozenset({1}),
            warp_locations={1: ((9, 9),)},
        ),
        {
            1: outside_local,
            2: line((0, 0), (0, 1)),
            3: line((0, 0), (0, 1)),
        },
        1,
        (0, 0),
        1,
        goal_at=(9, 9),
    )

    assert plan.macro_path.maps == (1, 2, 3, 1)
    assert plan.terminal_at == (9, 9)
    assert plan.cost == 6
