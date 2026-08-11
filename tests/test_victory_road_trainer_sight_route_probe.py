from __future__ import annotations

import runpy
from pathlib import Path

from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import TraversalHazard
from pokemon_red_completion.route_plan import plan_route

SCRIPT = runpy.run_path(
    str(
        Path(__file__).parents[1]
        / "scripts"
        / "falsify_victory_road_trainer_sight_route.py"
    )
)
hazard_crossings = SCRIPT["hazard_crossings"]


def test_probe_selection_detects_semantic_lane_without_calling_it_occupancy() -> None:
    graph = LocalGraph(
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
    plan = plan_route(
        MacroGraph({1: ()}),
        {1: graph},
        1,
        (0, 0),
        1,
        goal_at=(0, 2),
    )

    assert hazard_crossings(
        plan,
        (
            TraversalHazard((0, 1), "trainer_sight"),
            TraversalHazard((1, 0), "lava"),
        ),
    ) == ((0, 1),)
