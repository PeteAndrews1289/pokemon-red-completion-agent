from __future__ import annotations

import json

from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.red_navigation_outcome_probe import (
    RED_LOCAL_NAVIGATION_ACTOR,
    RED_LOCAL_NAVIGATION_ORDER_RULE,
    build_same_destination_navigation_question,
)
from pokemon_red_completion.route_plan import plan_route
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    SameDestinationRoutePair,
)


def _route_pair() -> SameDestinationRoutePair:
    macro = MacroGraph({1: ()})
    shortest_graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), "right"),),
            (0, 1): (
                LocalEdge((0, 0), "left"),
                LocalEdge((0, 2), "right"),
            ),
            (0, 2): (LocalEdge((0, 1), "left"),),
        }
    )
    detour_graph = LocalGraph(
        {
            (0, 0): (LocalEdge((1, 0), "down"),),
            (1, 0): (
                LocalEdge((0, 0), "up"),
                LocalEdge((1, 1), "right"),
            ),
            (1, 1): (
                LocalEdge((1, 0), "left"),
                LocalEdge((1, 2), "right"),
            ),
            (1, 2): (
                LocalEdge((1, 1), "left"),
                LocalEdge((0, 2), "up"),
            ),
            (0, 2): (LocalEdge((1, 2), "down"),),
        }
    )
    shortest = plan_route(
        macro,
        {1: shortest_graph},
        1,
        (0, 0),
        1,
        goal_at=(0, 2),
    )
    detour = plan_route(
        macro,
        {1: detour_graph},
        1,
        (0, 0),
        1,
        goal_at=(0, 2),
    )
    return SameDestinationRoutePair(
        shortest=shortest,
        detour=detour,
        excluded_step_ordinal=1,
        excluded_map=1,
        excluded_at=(0, 1),
    )


def test_question_uses_state_bound_order_and_shared_decision_identity() -> None:
    question = build_same_destination_navigation_question(
        _route_pair(),
        initial_state_sha256="8" * 64,
    )

    assert question.shortest_candidate_index == 1
    assert question.plans[0] is question.route_pair.detour
    assert question.plans[1] is question.route_pair.shortest
    first = question.decision(
        0,
        episode_id="same-terminal-probe",
        root_lineage_id="same-terminal-root",
    )
    second = question.decision(
        1,
        episode_id="same-terminal-probe",
        root_lineage_id="same-terminal-root",
    )
    assert first.decision_id == second.decision_id
    assert first.policy_input() == second.policy_input()
    assert first.actor == second.actor == RED_LOCAL_NAVIGATION_ACTOR
    assert first.selected_index == 0
    assert second.selected_index == 1


def test_question_public_catalog_has_no_route_actions_or_binding_identity() -> None:
    question = build_same_destination_navigation_question(
        _route_pair(),
        initial_state_sha256="7" * 64,
    )

    catalog = question.public_catalog()
    encoded = json.dumps(catalog, sort_keys=True)
    assert question.shortest_candidate_index == 0
    assert catalog["candidate_order_rule"] == RED_LOCAL_NAVIGATION_ORDER_RULE
    assert catalog["same_terminal"] is True
    assert catalog["movement_action_labels"] == 0
    assert "route-option" not in encoded
    assert '"right"' not in encoded
    assert '"down"' not in encoded

