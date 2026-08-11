from __future__ import annotations

import hashlib

from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_evidence import (
    public_route_execution,
    public_route_plan,
    rom_adjacent_artifacts,
)
from pokemon_red_completion.route_executor import (
    ExecutedRouteStep,
    RouteExecutionReport,
    TraversalSnapshot,
)
from pokemon_red_completion.route_plan import plan_route


def test_public_route_projection_preserves_plan_and_acknowledgement_contract() -> None:
    graph = LocalGraph(
        {
            (0, 0): (LocalEdge((0, 1), action="right"),),
            (0, 1): (),
        }
    )
    plan = plan_route(
        MacroGraph({7: ()}),
        {7: graph},
        7,
        (0, 0),
        7,
        goal_at=(0, 1),
    )
    report = RouteExecutionReport(
        initial_plan=plan,
        terminal=TraversalSnapshot(7, (0, 1), True),
        executed_steps=(ExecutedRouteStep(plan.steps[0], 1, 0),),
        interruptions=(),
        replans=(),
        movement_requests=1,
        wait_actions=2,
    )

    assert public_route_plan(plan, map_name=lambda value: f"map-{value}") == {
        "maps": ["map-7"],
        "map_ids": [7],
        "start_yx": [0, 0],
        "terminal_yx": [0, 1],
        "actions": ["right"],
        "segments": [],
    }
    assert public_route_execution(report) == {
        "passed": True,
        "movement_requests": 1,
        "wait_actions": 2,
        "acknowledged_steps": 1,
        "steps": [
            {
                "source_map_id": 7,
                "source_yx": [0, 0],
                "action": "right",
                "expected_map_id": 7,
                "expected_yx": [0, 1],
                "kind": "walk",
                "movement_requests": 1,
                "interruption_count": 0,
            }
        ],
        "interruptions": [],
        "replans": [],
        "terminal_map_id": 7,
        "terminal_yx": [0, 1],
        "terminal_ready": True,
    }


def test_sidecar_projection_exposes_only_presence_and_digest(tmp_path) -> None:
    rom = tmp_path / "game.gb"
    ram = tmp_path / "game.gb.ram"
    ram.write_bytes(b"private emulator state")

    assert rom_adjacent_artifacts(rom) == (
        (True, hashlib.sha256(b"private emulator state").hexdigest()),
        (False, None),
        (False, None),
    )
