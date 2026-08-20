from __future__ import annotations

import json
import os
from pathlib import Path

from pokemon_red_completion.observation import MapId

RECORD = Path("docs/evidence/celadon-repeated-cut-route-probe-2026-08-11.json")
SOURCE_COMMIT = "b449caf37c74b6e39f0760f5907bc369ea0a1f42"
SOURCE_BUNDLE = "09e645809e84b736bec1fdafc6fd4dab42b088e0b4c184ec88eef93dd0eb4fc0"


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_repeated_cut_record_is_bound_to_clean_authenticated_source() -> None:
    payload = record()

    assert payload["schema"] == "celadon-repeated-cut-route-probe-v1"
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


def test_both_distinct_trees_required_a_fresh_observed_mutation() -> None:
    payload = record()
    stages = payload["cut_stages"]

    assert payload["initial"] == {"city_start_yx": [10, 41]}
    assert payload["repeated_cut"] == {
        "required_cut_count": 2,
        "observed_cut_count": 2,
        "distinct_mutated_block_count": 2,
        "remaining_cut_tiles_after": 0,
        "durable_cut_edges_added": 0,
    }
    assert [stage["selection"] for stage in stages] == [
        {
            "planning_grid": "initial_live_ram",
            "start_yx": [10, 41],
            "source_yx": [20, 46],
            "target_yx": [20, 47],
            "direction": "right",
            "block_yx": [10, 23],
            "predicted_approach_steps": 23,
            "predicted_continuation_steps": 1,
            "prediction_used_as_execution_authority": False,
        },
        {
            "planning_grid": "live_ram_after_previous_cut",
            "start_yx": [20, 48],
            "source_yx": [31, 35],
            "target_yx": [32, 35],
            "direction": "down",
            "block_yx": [16, 17],
            "predicted_approach_steps": 24,
            "predicted_continuation_steps": 1,
            "prediction_used_as_execution_authority": False,
        },
    ]
    assert [stage["mutation"] for stage in stages] == [
        {
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
        },
        {
            "block_before": 0x32,
            "block_after": 0x6D,
            "target_tile_before": 0x3D,
            "target_tile_after": 0x2C,
            "changed_block_count": 1,
            "player_stayed_at_source": True,
            "input_ready_after_mutation": True,
            "target_standable_before": False,
            "target_standable_after": True,
            "observed_post_cut_path_yx": [[31, 35], [32, 35]],
        },
    ]
    assert all(
        stage["cut_receipt"]
        == {"party_index": 1, "submenu_row": 0, "confirmation_count": 2}
        for stage in stages
    )


def test_each_crossing_used_only_the_observed_post_cut_graph() -> None:
    payload = record()
    stages = payload["cut_stages"]

    assert [stage["plans"]["observed_crossing"]["steps"][0] for stage in stages] == [
        {
            "source_map_id": MapId.CELADON_CITY,
            "source_yx": [20, 46],
            "action_kind": "move",
            "action": "right",
            "expected_map_id": MapId.CELADON_CITY,
            "expected_yx": [20, 47],
            "kind": "walk",
        },
        {
            "source_map_id": MapId.CELADON_CITY,
            "source_yx": [31, 35],
            "action_kind": "move",
            "action": "down",
            "expected_map_id": MapId.CELADON_CITY,
            "expected_yx": [32, 35],
            "kind": "walk",
        },
    ]
    reports = [
        payload["execution"]["center_exit"],
        *(
            report
            for stage in stages
            for report in (stage["execution"]["approach"], stage["execution"]["observed_crossing"])
        ),
        payload["execution"]["center_return"],
    ]
    assert all(report["passed"] is True for report in reports)
    assert payload["route_totals"] == {
        "movement_requests": 110,
        "acknowledged_steps": 110,
        "interruption_count": 0,
        "replan_count": 1,
    }
    assert payload["final"] == {
        "map_id": MapId.CELADON_POKECENTER,
        "yx": [3, 3],
        "ready": True,
    }


def test_repeated_cut_probe_released_control_and_published_no_private_path() -> None:
    payload = record()
    encoded = json.dumps(payload)

    assert payload["actions_executed"] == 144
    assert payload["frames_executed"] == 6144
    assert payload["controller_released"] is True
    assert payload["rom_adjacent_artifacts_unchanged"] is True
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    rom_path = os.environ.get("POKEMON_RED_ROM")
    assert rom_path is None or rom_path not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
