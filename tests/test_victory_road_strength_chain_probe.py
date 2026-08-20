from __future__ import annotations

import json
import os
from pathlib import Path

from pokemon_red_completion.observation import MapId

RECORD = Path("docs/evidence/victory-road-strength-chain-probe-2026-08-10.json")
SOURCE_COMMIT = "8dbee6f4235273eb2b04c45b457ac53ad2d260b0"
SOURCE_BUNDLE = "2a69d9ee762e3481e267db1bb9f2599e917f119b489d3bff71a5d2d4f6b0a036"


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_strength_chain_is_bound_to_authenticated_clean_source() -> None:
    payload = record()

    assert payload["schema"] == "victory-road-strength-chain-probe-v1"
    assert payload["status"] == "ok"
    assert payload["source"] == {
        "git_commit": SOURCE_COMMIT,
        "source_bundle_sha256": SOURCE_BUNDLE,
    }
    assert payload["capture"] == {
        "checkpoint_id": "portable_loop_defeat_giovanni_terminal",
        "required_verified_objectives": ["defeat_giovanni", "obtain_strength"],
    }
    assert payload["boundary"] == {
        "map_id": MapId.VICTORY_ROAD_1F,
        "player_yx": [17, 8],
        "ready": True,
    }


def test_strength_chain_searched_all_five_stateful_phases() -> None:
    payload = record()
    planner = payload["planner"]
    phases = planner["phases"]

    assert planner["algorithm"] == "bounded_dijkstra_player_and_toggle_present_boulders"
    assert planner["phase_count"] == 5
    assert [phase["phase_id"] for phase in phases] == [
        "victory_road_1f_switch",
        "victory_road_2f_switch_1",
        "victory_road_3f_switch",
        "victory_road_3f_hole",
        "victory_road_2f_switch_2",
    ]
    assert [phase["map_id"] for phase in phases] == [108, 194, 198, 198, 194]
    assert [phase["explored_states"] for phase in phases] == [
        3_934,
        2_519,
        31_841,
        572,
        5_659,
    ]
    assert [
        (phase["cost"], phase["steps"], phase["walks"], phase["pushes"], phase["drops"])
        for phase in phases
    ] == [
        (76, 58, 40, 18, 0),
        (30, 25, 20, 5, 0),
        (67, 47, 27, 20, 0),
        (87, 87, 86, 0, 1),
        (44, 30, 16, 14, 0),
    ]
    assert all(phase["event_set"] is True for phase in phases)
    assert all(phase["execution"]["passed"] is True for phase in phases)


def test_hidden_and_cross_floor_boulders_follow_toggle_state() -> None:
    phases = record()["planner"]["phases"]
    first_2f, hole, final_2f = phases[1], phases[3], phases[4]

    assert [item["sprite_index"] for item in first_2f["initial"]["boulders"]] == [
        11,
        12,
    ]
    assert hole["goal_removes_boulder"] is True
    assert [item["sprite_index"] for item in hole["terminal"]["boulders"]] == [
        7,
        8,
        9,
    ]
    assert final_2f["initial"]["boulders"][-1] == {
        "sprite_index": 13,
        "yx": [16, 23],
    }
    assert final_2f["terminal"]["boulders"][-1] == {
        "sprite_index": 13,
        "yx": [16, 9],
    }


def test_every_push_has_exact_engine_acknowledgement_and_privacy() -> None:
    payload = record()
    phases = payload["planner"]["phases"]
    receipts = [
        receipt
        for phase in phases
        for receipt in phase["execution"]["push_receipts"]
    ]
    encoded = json.dumps(payload)

    assert len(receipts) == 58
    assert all(receipt["engine_acknowledged"] is True for receipt in receipts)
    assert all(receipt["boulder_dust_observed"] is True for receipt in receipts)
    assert all(receipt["player_stationary"] is True for receipt in receipts)
    assert sum(receipt["boulder_removed"] for receipt in receipts) == 1
    assert payload["execution"]["derived_phase_steps"] == 247
    assert payload["execution"]["derived_phase_pushes"] == 58
    assert payload["execution"]["controller_released"] is True
    assert payload["execution"]["all_switch_events_set"] is True
    assert payload["rom_adjacent_artifacts_unchanged"] is True
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    rom_path = os.environ.get("POKEMON_RED_ROM")
    assert rom_path is None or rom_path not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
