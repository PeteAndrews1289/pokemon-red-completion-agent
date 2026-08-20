from __future__ import annotations

import json
import os
from pathlib import Path

from pokemon_red_completion.gen1_story_routing import SAFFRON_GUARDS_OPEN
from pokemon_red_completion.observation import MapId

RECORD = Path("docs/evidence/saffron-story-gate-route-probe-2026-08-10.json")
SOURCE_COMMIT = "40a05d160b66e5e8e00f4ca95bb76841752694eb"
SOURCE_BUNDLE = "1b884ee9539881d9d95465156627d309f1ef70c0cea3d60f139c4fa79b5e2020"


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_the_story_gate_receipt_is_bound_to_clean_source_and_capture() -> None:
    payload = record()

    assert payload["schema"] == "saffron-story-gate-route-probe-v1"
    assert payload["status"] == "ok"
    assert payload["source"] == {
        "git_commit": SOURCE_COMMIT,
        "source_bundle_sha256": SOURCE_BUNDLE,
    }
    assert payload["capture"] == {
        "checkpoint_id": "portable_loop_defeat_erika_terminal",
        "required_verified_objective": "defeat_erika",
    }


def test_closed_and_unknown_state_reject_the_statically_open_corridor() -> None:
    payload = record()
    passage = payload["passage"]
    closed = payload["closed_observation"]

    assert passage == {
        "map_id": MapId.ROUTE_7_GATE,
        "west_yx": [4, 0],
        "east_yx": [4, 5],
        "predicate": SAFFRON_GUARDS_OPEN,
        "static_topology_changed_between_observations": False,
    }
    assert closed["predicate_state"] == "unsatisfied"
    assert closed["status_flags_1"] == 0
    assert closed["capabilities"] == []
    assert closed["static_unfiltered_plan"]["actions"] == ["right"] * 5
    assert closed["semantic_plan_available"] is False
    assert closed["unknown_predicate_plan_available"] is False
    assert closed["generated_inputs_sent"] == 0
    assert closed["fresh_water_present"] is True


def test_the_observed_open_flag_admits_both_threshold_directions() -> None:
    payload = record()
    opened = payload["open_observation"]
    execution = payload["generated_execution"]

    assert opened == {
        "predicate_state": "satisfied",
        "status_flags_1": 0x40,
        "capabilities": [SAFFRON_GUARDS_OPEN],
        "fresh_water_present": False,
    }
    assert execution["semantic_threshold_crossed_westbound"] is True
    assert execution["semantic_threshold_crossed_eastbound"] is True
    assert execution["total_movement_requests"] == 11
    assert execution["total_acknowledged_steps"] == 11
    assert execution["gate_exit"]["terminal_yx"] == [10, 18]
    assert execution["terminal_map_id"] == MapId.SAFFRON_CITY
    assert execution["terminal_yx"] == [18, 0]
    for stage in (
        "open_backtrack",
        "open_forward_crossing",
        "gate_exit",
        "saffron_connection",
    ):
        assert execution[stage]["passed"] is True
        assert execution[stage]["interruptions"] == []
        assert execution[stage]["replans"] == 0


def test_the_public_receipt_contains_no_private_input_path() -> None:
    payload = record()
    encoded = json.dumps(payload)

    assert payload["controller_released"] is True
    assert payload["rom_adjacent_artifacts_unchanged"] is True
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    rom_path = os.environ.get("POKEMON_RED_ROM")
    assert rom_path is None or rom_path not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
