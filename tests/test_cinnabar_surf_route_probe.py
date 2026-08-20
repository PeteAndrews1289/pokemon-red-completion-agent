from __future__ import annotations

import json
import os
from pathlib import Path

from pokemon_red_completion.observation import MapId

RECORD = Path("docs/evidence/cinnabar-cartridge-surf-route-probe-2026-08-10.json")
SOURCE_COMMIT = "0d1fc43187fa0bed8d88fdfb16a1b2e9a0813a82"
SOURCE_BUNDLE = "2bffd5f51822255afdd9b49b655dd5859434ad187f05d73eae5ec34eb619bcc1"


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_the_surf_round_trip_is_bound_to_clean_authenticated_source() -> None:
    payload = record()

    assert payload["schema"] == "cinnabar-cartridge-surf-route-probe-v1"
    assert payload["status"] == "ok"
    assert payload["source"] == {
        "git_commit": SOURCE_COMMIT,
        "worktree_dirty": False,
    }
    assert payload["executable_source_bundle_sha256"] == SOURCE_BUNDLE
    assert payload["private_capture_precondition"] == {
        "authenticated": True,
        "checkpoint_id": "portable_loop_defeat_blaine_terminal",
        "checkpoint_label": "Portable loop completed defeat_blaine",
        "required_verified_objective": "defeat_blaine",
    }


def test_the_center_return_and_every_surf_mode_change_were_acknowledged() -> None:
    payload = record()
    plans = payload["plans"]
    execution = payload["execution"]

    assert plans["center_exit"]["map_ids"] == [
        MapId.CINNABAR_POKECENTER,
        MapId.CINNABAR_ISLAND,
    ]
    assert plans["center_exit"]["steps"][-1] == {
        "source_map_id": MapId.CINNABAR_POKECENTER,
        "source_yx": [7, 3],
        "source_mode": "land",
        "action_kind": "move",
        "action": "down",
        "expected_map_id": MapId.CINNABAR_ISLAND,
        "expected_yx": [12, 11],
        "expected_mode": "land",
        "transition_kind": "return",
    }
    assert [step["transition_kind"] for step in plans["outbound"]["steps"]] == [
        "walk",
        "water_entry",
        "water_travel",
        "water_travel",
    ]
    assert [step["transition_kind"] for step in plans["return"]["steps"]] == [
        "water_travel",
        "water_travel",
        "water_exit",
        "walk",
    ]
    assert all(stage["passed"] is True for stage in execution.values())
    assert sum(stage["acknowledged_steps"] for stage in execution.values()) == 13
    assert payload["final"] == {
        "map_id": MapId.CINNABAR_ISLAND,
        "yx": [12, 11],
        "mode": "land",
        "ready": True,
    }


def test_the_field_move_used_a_living_holder_and_published_no_private_path() -> None:
    payload = record()
    encoded = json.dumps(payload)

    assert payload["surf_receipts"] == [
        {
            "source_map_id": MapId.CINNABAR_ISLAND,
            "source_yx": [13, 11],
            "target_yx": [14, 11],
            "direction": "down",
            "party_index": 0,
            "submenu_row": 1,
            "confirmation_count": 1,
            "permission_reason": "no_observed_title_restriction",
        }
    ]
    assert payload["controller_released"] is True
    assert payload["rom_adjacent_artifacts_unchanged"] is True
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    rom_path = os.environ.get("POKEMON_RED_ROM")
    assert rom_path is None or rom_path not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
