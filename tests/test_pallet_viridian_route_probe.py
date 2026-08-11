from __future__ import annotations

import json
from pathlib import Path

from pokemon_red_completion.observation import MapId

CENTER_RECORD = Path(
    "docs/evidence/pallet-viridian-composed-route-probe-2026-08-10.json"
)
MART_RECORD = Path(
    "docs/evidence/pallet-viridian-mart-closed-loop-replan-probe-2026-08-10.json"
)
STRATEGIC_RECORD = Path(
    "docs/evidence/pallet-strategic-safe-hub-route-probe-2026-08-11.json"
)


def load_record(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_control_route_acknowledges_every_step_and_three_wilds() -> None:
    record = load_record(CENTER_RECORD)
    plan = record["plan"]
    execution = record["execution"]

    assert record["schema"] == "pallet-viridian-closed-loop-route-probe-v2"
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
    assert execution["passed"] is True
    assert execution["acknowledged_steps"] == execution["movement_requests"] == 86
    assert execution["wait_actions"] == 3
    assert execution["replans"] == []
    assert len(execution["interruptions"]) == len(record["wild_flees"]) == 3
    assert all(
        interruption["kind"] == "wild_battle"
        and interruption["details"]["verified"] is True
        for interruption in execution["interruptions"]
    )
    assert record["fault_injection"]["enabled"] is False


def test_every_control_arrival_matches_cartridge_geometry() -> None:
    record = load_record(CENTER_RECORD)
    segments = record["plan"]["segments"]
    transitions = [
        step
        for step in record["execution"]["steps"]
        if step["source_map_id"] != step["expected_map_id"]
    ]

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
    assert [step["expected_yx"] for step in transitions] == [
        segment["transition"]["arrival_yx"] for segment in segments
    ]
    assert record["controller_released"] is True
    assert record["rom_adjacent_artifacts_unchanged"] is True


def test_the_fault_probe_replans_around_two_distinct_live_blockers() -> None:
    record = load_record(MART_RECORD)
    execution = record["execution"]
    replans = execution["replans"]
    fault = record["fault_injection"]

    assert record["source"]["git_commit"] == load_record(CENTER_RECORD)["source"][
        "git_commit"
    ]
    assert record["source"]["worktree_dirty"] is False
    assert record["plan"]["map_ids"] == [
        MapId.PALLET_TOWN,
        MapId.ROUTE_1,
        MapId.VIRIDIAN_CITY,
        MapId.VIRIDIAN_MART,
    ]
    assert record["planned_actions"] == 98
    assert fault == {
        "enabled": True,
        "kind": "suppressed movement requests",
        "source_map_id": MapId.PALLET_TOWN,
        "source_yx": [12, 12],
        "blocked_yx": [12, 11],
        "direction": "left",
        "suppressed_requests": 2,
        "disclosure": (
            "Artificial fault for causal recovery testing; not a naturally observed NPC."
        ),
    }
    assert replans == [
        {
            "ordinal": 1,
            "map_id": MapId.PALLET_TOWN,
            "at_yx": [12, 12],
            "newly_blocked_yx": [12, 11],
            "replacement_steps": 104,
        },
        {
            "ordinal": 2,
            "map_id": MapId.ROUTE_1,
            "at_yx": [14, 14],
            "newly_blocked_yx": [13, 14],
            "replacement_steps": 50,
        },
    ]
    assert execution["passed"] is True
    assert execution["movement_requests"] == 112
    assert execution["acknowledged_steps"] == 108
    assert len(execution["interruptions"]) == 1
    assert execution["interruptions"][0]["details"]["verified"] is True
    assert record["final_map"] == {
        "id": MapId.VIRIDIAN_MART,
        "name": "VIRIDIAN_MART",
    }
    assert record["final_yx"] == [7, 3]
    assert record["controller_released"] is True
    assert record["rom_adjacent_artifacts_unchanged"] is True


def test_fault_replanning_changes_the_executed_pallet_connection() -> None:
    record = load_record(MART_RECORD)
    initial_arrival = record["plan"]["segments"][0]["transition"]["arrival_yx"]
    executed_transitions = [
        step
        for step in record["execution"]["steps"]
        if step["source_map_id"] != step["expected_map_id"]
    ]

    assert initial_arrival == [35, 10]
    assert executed_transitions[0]["expected_yx"] == [35, 11]
    assert [step["expected_map_id"] for step in executed_transitions] == [
        MapId.ROUTE_1,
        MapId.VIRIDIAN_CITY,
        MapId.VIRIDIAN_MART,
    ]


def test_safe_hub_calibration_binds_two_real_routes_to_one_live_outcome() -> None:
    record = load_record(STRATEGIC_RECORD)
    strategic = record["strategic_navigation"]
    decision = strategic["record"]["decision"]
    outcome = strategic["record"]["outcome"]

    assert record["schema"] == "pallet-strategic-safe-hub-route-probe-v1"
    assert record["source"] == {
        "git_commit": "bf3fc76d8c571fd56acdb81da7aaed4fa97e5255",
        "worktree_dirty": False,
    }
    assert record["executable_source_bundle_sha256"] == (
        "098b7004f6bf822164cf66d8d15b353313f95cb6e49681e4e38762d64233fd0e"
    )
    assert record["destination"] == "home"
    assert record["plan"]["map_ids"] == [MapId.PALLET_TOWN, MapId.REDS_HOUSE_1F]
    assert record["planned_actions"] == 14
    assert record["execution"]["passed"] is True
    assert record["execution"]["acknowledged_steps"] == 14
    assert record["execution"]["movement_requests"] == 14
    assert record["final_yx"] == [7, 2]
    assert record["controller_released"] is True
    assert record["rom_adjacent_artifacts_unchanged"] is True
    assert strategic["scope"] == "unassigned calibration; excluded from model development"
    assert strategic["selection_rule"] == (
        "lowest route cost among two available safe hubs"
    )
    assert strategic["numeric_feature_schema_frozen"] is False
    assert strategic["promotion_eligible"] is False
    assert [candidate["route_cost"] for candidate in decision["candidates"]] == [15, 87]
    assert [candidate["route_steps"] for candidate in decision["candidates"]] == [14, 86]
    assert decision["selected_index"] == 0
    assert outcome["decision_id"] == decision["decision_id"]
    assert outcome["status"] == "succeeded"
    assert outcome["acknowledged_steps"] == decision["candidates"][0]["route_steps"]


def test_safe_hub_policy_projection_contains_no_route_identity_or_arrow_labels() -> None:
    record = load_record(STRATEGIC_RECORD)
    strategic = record["strategic_navigation"]
    decision = strategic["identity_free_trajectory_decision"]
    outcome = strategic["identity_free_trajectory_outcome"]
    encoded = json.dumps(
        {"context": decision["context"], "action": decision["action"], "outcome": outcome},
        sort_keys=True,
    )

    for forbidden in (
        "destination_ref",
        "origin_region_ref",
        "pokemon.red:destination",
        '"direction"',
        '"coordinate"',
        '"map_id"',
        '"left"',
        '"right"',
        '"up"',
        '"down"',
    ):
        assert forbidden not in encoded
    assert decision["action"] == {
        "kind": "select_destination",
        "selected_candidate_index": 0,
    }
    assert outcome["payload"]["decision_id"] == decision["decision_id"]
