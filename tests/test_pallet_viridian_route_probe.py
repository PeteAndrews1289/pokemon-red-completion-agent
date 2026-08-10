from __future__ import annotations

import json
from pathlib import Path

from pokemon_red_completion.observation import MapId

RECORD = Path("docs/evidence/pallet-viridian-composed-route-probe-2026-08-10.json")


def test_the_live_probe_executes_one_continuous_composed_route() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    plan = record["plan"]

    assert record["schema"] == "pallet-viridian-composed-route-probe-v1"
    assert record["status"] == "ok"
    assert record["source"]["worktree_dirty"] is False
    assert plan["map_ids"] == [
        MapId.PALLET_TOWN,
        MapId.ROUTE_1,
        MapId.VIRIDIAN_CITY,
        MapId.VIRIDIAN_POKECENTER,
    ]
    assert plan["start_yx"] == [12, 12]
    assert plan["terminal_yx"] == record["final_yx"] == [7, 3]
    assert record["final_map"] == {
        "id": MapId.VIRIDIAN_POKECENTER,
        "name": "VIRIDIAN_POKECENTER",
    }
    assert record["planned_actions"] == len(plan["actions"]) == 86
    # Three transition-settling waits plus one Route 1 seed wait are runtime
    # control actions, not generated movements.
    assert record["actions_executed_during_plan"] == 86 + 4


def test_every_live_arrival_matches_cartridge_geometry() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    segments = record["plan"]["segments"]

    assert [segment["transition"] for segment in segments] == [
        {
            "exit_yx": [0, 10],
            "arrival_yx": [35, 10],
            "action": "up",
            "action_in_approach": False,
        },
        {
            "exit_yx": [0, 11],
            "arrival_yx": [35, 21],
            "action": "up",
            "action_in_approach": False,
        },
        {
            "exit_yx": [25, 23],
            "arrival_yx": [7, 3],
            "action": "up",
            "action_in_approach": True,
        },
    ]
    assert [arrival["yx"] for arrival in record["live_arrivals"]] == [
        transition["arrival_yx"] for transition in (s["transition"] for s in segments)
    ]
    assert record["wild_flees"] == []
    assert record["movement_retries"] == 0
    assert record["controller_released"] is True
    assert record["rom_adjacent_artifacts_unchanged"] is True
