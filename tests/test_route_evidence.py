from __future__ import annotations

import hashlib

from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_evidence import (
    public_route_execution,
    public_route_execution_summary,
    public_route_plan,
    public_route_plan_summary,
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
                "transient_yx": None,
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
        "terminal_last_outside_map_id": None,
    }
    plan_summary = public_route_plan_summary(
        plan,
        map_name=lambda value: f"map-{value}",
    )
    assert plan_summary == {
        "schema": "route-plan-summary-v1",
        "maps": ["map-7"],
        "map_ids": [7],
        "start_yx": [0, 0],
        "terminal_yx": [0, 1],
        "route_cost": 1,
        "route_steps": 1,
        "map_transitions": 0,
        "full_projection_sha256": (
            "a410da5fe6cdb459022e1de5745c062e7efcbbffaaa7f360885b114c97534c9a"
        ),
    }
    execution_summary = public_route_execution_summary(report)
    assert execution_summary == {
        "schema": "route-execution-summary-v1",
        "passed": True,
        "movement_requests": 1,
        "wait_actions": 2,
        "acknowledged_steps": 1,
        "interruptions": [],
        "replans": [],
        "terminal_map_id": 7,
        "terminal_yx": [0, 1],
        "terminal_ready": True,
        "terminal_last_outside_map_id": None,
        "executed_steps_sha256": (
            "042a071cec14865806188995d98a335a103a0d88a0fc12ab881d562bb5dda76d"
        ),
        "full_projection_sha256": (
            "918c3b061d4911511849a2eb4f7cf95e3b8421b4e7eba6d55b2d30ad3057865a"
        ),
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
