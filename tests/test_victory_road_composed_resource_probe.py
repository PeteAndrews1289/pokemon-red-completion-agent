from __future__ import annotations

import json
from pathlib import Path

from pokemon_red_completion.gen1_repel import ENCOUNTER_SUPPRESSION
from pokemon_red_completion.observation import ItemId, MapId

RECORD = Path(
    "docs/evidence/victory-road-composed-resource-chain-probe-2026-08-10.json"
)
SOURCE_COMMIT = "254b846ff11bcb31d0a4359278ea43c2795fbdbc"
SOURCE_BUNDLE = "2c31afaf232726ea7c4b7a50b6bbac7d03eed8fc019c0e799af205d3cce84e35"


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_composed_resource_chain_is_bound_to_clean_authenticated_source() -> None:
    payload = record()

    assert payload["schema"] == "victory-road-composed-resource-chain-probe-v1"
    assert payload["status"] == "ok"
    assert payload["source"] == {
        "git_commit": SOURCE_COMMIT,
        "source_bundle_sha256": SOURCE_BUNDLE,
    }
    assert payload["capture"] == {
        "checkpoint_id": "portable_loop_defeat_giovanni_terminal",
        "required_verified_objectives": ["defeat_giovanni", "obtain_strength"],
    }


def test_both_authored_room_routes_are_replaced_by_acknowledged_warp_plans() -> None:
    execution = record()["execution"]
    routes = execution["composed_inter_phase_routes"]

    assert execution["authored_inter_phase_route_steps"] == 0
    assert [route["map_ids"] for route in routes] == [
        [MapId.VICTORY_ROAD_1F, MapId.VICTORY_ROAD_2F],
        [MapId.VICTORY_ROAD_2F, MapId.VICTORY_ROAD_3F],
    ]
    assert [route["steps"] for route in routes] == [51, 56]
    assert [route["passages"] for route in routes] == [["warp"], ["warp"]]
    assert [route["execution"]["replans"] for route in routes] == [
        ["trainer_sight"],
        [],
    ]
    for route in routes:
        stage = route["execution"]
        assert stage["passed"] is True
        assert stage["movement_requests"] == stage["acknowledged_steps"]
        assert stage["interruptions"] == []


def test_repel_renews_at_observed_zero_inside_the_third_strength_search() -> None:
    payload = record()
    boundary = payload["resource_boundary"]
    phases = payload["planner"]["phases"]

    assert boundary["authored_direction_count"] == 0
    assert boundary["puzzle_search_resumed_after_observed_replenishment"] is True
    assert boundary["renewals"] == [
        {
            "kind": ENCOUNTER_SUPPRESSION,
            "map_id": MapId.VICTORY_ROAD_3F,
            "at_yx": [1, 9],
            "before_remaining": 0,
            "after_remaining": 250,
            "units_consumed": 1,
            "details": {
                "item_id": ItemId.MAX_REPEL,
                "prompt_confirmations": 1,
                "carried_before": 1,
                "carried_after": 0,
            },
        }
    ]
    assert [len(phase["execution"]["resource_renewals"]) for phase in phases] == [
        0,
        0,
        1,
        0,
        0,
    ]


def test_all_puzzles_still_settle_after_removing_the_authored_preamble() -> None:
    payload = record()
    phases = payload["planner"]["phases"]
    execution = payload["execution"]

    assert [phase["steps"] for phase in phases] == [58, 25, 67, 87, 30]
    assert [phase["explored_states"] for phase in phases] == [
        3_934,
        2_519,
        54_305,
        572,
        5_659,
    ]
    assert all(phase["event_set"] is True for phase in phases)
    assert all(phase["execution"]["passed"] is True for phase in phases)
    assert execution["passed"] is True
    assert execution["derived_phase_steps"] == 267
    assert execution["derived_phase_pushes"] == 65
    assert execution["all_switch_events_set"] is True
    assert execution["terminal_map_id"] == MapId.VICTORY_ROAD_2F
    assert execution["terminal_player_yx"] == [16, 11]


def test_composed_resource_receipt_is_private_input_safe() -> None:
    payload = record()
    encoded = json.dumps(payload)

    assert payload["execution"]["controller_released"] is True
    assert payload["rom_adjacent_artifacts_unchanged"] is True
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "PokemonRoms" not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
