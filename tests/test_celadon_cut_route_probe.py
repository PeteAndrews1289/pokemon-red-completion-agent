from __future__ import annotations

import json
import os
from pathlib import Path

from pokemon_red_completion.observation import MapId

RECORD = Path("docs/evidence/celadon-staged-cut-route-probe-2026-08-10.json")
SOURCE_COMMIT = "8a0b794a11c5b5e9a93878c341cd6152f9af6864"
SOURCE_BUNDLE = "f47d70ec7158bb2ec69b19cf24a153c4d9feb6e4bf90774a7f63b89891373926"


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_cut_record_is_bound_to_clean_authenticated_source() -> None:
    payload = record()

    assert payload["schema"] == "celadon-staged-cut-route-probe-v1"
    assert payload["status"] == "ok"
    assert payload["source"] == {
        "git_commit": SOURCE_COMMIT,
        "worktree_dirty": False,
    }
    assert payload["executable_source_bundle_sha256"] == SOURCE_BUNDLE
    assert payload["private_capture_precondition"] == {
        "authenticated": True,
        "checkpoint_id": "celadon_stable",
        "checkpoint_label": "Healed safely in Celadon",
        "required_verified_objectives": ["defeat_misty", "obtain_cut"],
    }


def test_cut_was_staged_around_one_exact_observed_mutation() -> None:
    payload = record()

    assert payload["selection"] == {
        "city_start_yx": [10, 41],
        "source_yx": [20, 46],
        "target_yx": [20, 47],
        "direction": "right",
        "block_yx": [10, 23],
        "predicted_approach_steps": 23,
        "predicted_continuation_steps": 1,
        "prediction_used_as_execution_authority": False,
    }
    assert payload["mutation"] == {
        "block_before": 0x35,
        "block_after": 0x4C,
        "target_tile_before": 0x3D,
        "target_tile_after": 0x2C,
        "changed_block_count": 1,
        "player_stayed_at_source": True,
        "input_ready_after_mutation": True,
        "target_standable_before": False,
        "target_standable_after": True,
        "observed_post_cut_path_yx": [[20, 46], [20, 47]],
    }
    assert payload["cut_receipt"] == {
        "party_index": 1,
        "submenu_row": 0,
        "confirmation_count": 2,
    }


def test_crossing_was_planned_after_mutation_and_the_round_trip_closed() -> None:
    payload = record()
    crossing = payload["plans"]["observed_crossing"]
    execution = payload["execution"]

    assert crossing["start_yx"] == [20, 46]
    assert crossing["terminal_yx"] == [20, 48]
    assert crossing["steps"][0] == {
        "source_map_id": MapId.CELADON_CITY,
        "source_yx": [20, 46],
        "action_kind": "move",
        "action": "right",
        "expected_map_id": MapId.CELADON_CITY,
        "expected_yx": [20, 47],
        "kind": "walk",
    }
    assert all(stage["passed"] is True for stage in execution.values())
    assert sum(stage["movement_requests"] for stage in execution.values()) == 60
    assert sum(stage["acknowledged_steps"] for stage in execution.values()) == 60
    assert payload["final"] == {
        "map_id": MapId.CELADON_POKECENTER,
        "yx": [3, 3],
        "ready": True,
    }


def test_cut_probe_released_control_and_published_no_private_path() -> None:
    payload = record()
    encoded = json.dumps(payload)

    assert payload["actions_executed"] == 80
    assert payload["frames_executed"] == 3576
    assert payload["controller_released"] is True
    assert payload["rom_adjacent_artifacts_unchanged"] is True
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    rom_path = os.environ.get("POKEMON_RED_ROM")
    assert rom_path is None or rom_path not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
