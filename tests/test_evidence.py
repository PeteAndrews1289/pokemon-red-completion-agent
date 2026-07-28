from __future__ import annotations

import json
import re
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.navigation import path_to_directions
from pokemon_red_completion.opening import (
    BEDROOM_CORRIDOR,
    DEFAULT_OPENING_TIMING,
    HOUSE_1F_CORRIDOR,
    PALLET_CORRIDOR,
    PRET_POKERED_COMMIT,
    SQUIRTLE_APPROACH,
)
from pokemon_red_completion.provenance import GIT_COMMIT, canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUALIFIED_SOURCE_COMMIT = "0fb14ac7f287e92fe270b3811f1ef495cbc36194"
OPENING_SOURCE_COMMIT = "898f015e297aae4f5d1ae3d200285e58f182d306"
BOOTSTRAP_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "bootstrap-smoke-2026-07-28.json"
OPENING_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "opening-squirtle-2026-07-28.json"


def test_bootstrap_receipt_is_source_bound_and_privacy_safe() -> None:
    receipt = json.loads(BOOTSTRAP_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "bootstrap-evidence-v1"
    assert receipt["schema"] == "bootstrap-smoke-v1"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 1, "total": 1}
    assert receipt["assistance"] == {
        "class": "deterministic_teacher",
        "human_controller_input": False,
        "save_state_restore": False,
    }
    assert receipt["source"]["worktree_dirty"] is False
    assert GIT_COMMIT.fullmatch(receipt["source"]["git_commit"])
    assert receipt["source"]["git_commit"] == QUALIFIED_SOURCE_COMMIT
    assert re.fullmatch(r"\d+\.\d+\.\d+", receipt["python_version"])
    assert receipt["recorded_on"] == "2026-07-28"

    timing = DEFAULT_NEW_GAME_TIMING
    expected_configuration = {
        "controller_timing": {
            "press_frames": timing.press_frames,
            "release_frames": timing.release_frames,
            "wait_frames": 1,
        },
        "emulator": {
            "human_input": False,
            "ram_input": "none",
            "rtc_input": "none",
            "save_on_exit": False,
            "sound_emulated": False,
            "speed": 0,
            "window": "null",
        },
        "intro_timing": {
            "boot_frames": timing.boot_frames,
            "final_wait_frames": timing.final_wait_frames,
            "menu_move_wait_frames": timing.menu_move_wait_frames,
            "normal_wait_frames": timing.normal_wait_frames,
        },
        "movement_probe": {
            "direction": "down",
            "macro_action": "move",
        },
        "new_game_names": "built_in_red_blue",
    }
    assert receipt["configuration"] == expected_configuration
    assert receipt["configuration_sha256"] == canonical_sha256(expected_configuration)
    assert receipt["rom"] == {
        "sha1": POKEMON_RED_US_REV_0.sha1,
        "sha256": POKEMON_RED_US_REV_0.sha256,
        "size_bytes": POKEMON_RED_US_REV_0.size_bytes,
        "title": POKEMON_RED_US_REV_0.title,
    }
    assert receipt["clean_power_on"] is True
    assert receipt["input_ready"] is True
    assert receipt["frames_executed"] == 9_828
    assert receipt["movement"] == {
        "from_y": 6,
        "to_y": 7,
        "verified": True,
    }
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_opening_receipt_is_source_bound_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(OPENING_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "opening-evidence-v1"
    assert receipt["schema"] == "opening-chapter-v1"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["assistance"] == {
        "class": "deterministic_teacher",
        "human_controller_input": False,
        "save_state_restore": False,
    }
    assert receipt["source"] == {
        "git_commit": OPENING_SOURCE_COMMIT,
        "worktree_dirty": False,
    }
    assert GIT_COMMIT.fullmatch(receipt["source"]["git_commit"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", receipt["python_version"])
    assert receipt["recorded_on"] == "2026-07-28"

    intro = DEFAULT_NEW_GAME_TIMING
    timing = DEFAULT_OPENING_TIMING
    expected_configuration = {
        "controller_timing": {
            "press_frames": intro.press_frames,
            "release_frames": intro.release_frames,
            "wait_frames": 1,
        },
        "emulator": {
            "human_input": False,
            "ram_input": "none",
            "rtc_input": "none",
            "save_on_exit": False,
            "sound_emulated": False,
            "speed": 0,
            "window": "null",
        },
        "intro_timing": {
            "boot_frames": intro.boot_frames,
            "final_wait_frames": intro.final_wait_frames,
            "menu_move_wait_frames": intro.menu_move_wait_frames,
            "normal_wait_frames": intro.normal_wait_frames,
        },
        "new_game_names": "built_in_red_blue",
        "opening_timing": {
            "dialogue_wait_frames": timing.dialogue_wait_frames,
            "max_escort_pulses": timing.max_escort_pulses,
            "max_starter_cancel_pulses": timing.max_starter_cancel_pulses,
            "max_starter_confirm_pulses": timing.max_starter_confirm_pulses,
            "oak_trigger_wait_frames": timing.oak_trigger_wait_frames,
            "starter_text_wait_frames": timing.starter_text_wait_frames,
            "transition_wait_frames": timing.transition_wait_frames,
        },
        "pret_pokered_commit": PRET_POKERED_COMMIT,
        "qualified_actions": {
            "bedroom": [direction.value for direction in path_to_directions(BEDROOM_CORRIDOR)],
            "house_1f": [
                *(direction.value for direction in path_to_directions(HOUSE_1F_CORRIDOR)),
                "down",
            ],
            "pallet_town": [direction.value for direction in path_to_directions(PALLET_CORRIDOR)],
            "starter_approach": [
                *(direction.value for direction in path_to_directions(SQUIRTLE_APPROACH)),
                "face_up",
                "interact",
            ],
        },
        "starter": "squirtle",
    }
    assert receipt["configuration"] == expected_configuration
    assert receipt["configuration_sha256"] == canonical_sha256(expected_configuration)
    assert receipt["rom"] == {
        "sha1": POKEMON_RED_US_REV_0.sha1,
        "sha256": POKEMON_RED_US_REV_0.sha256,
        "size_bytes": POKEMON_RED_US_REV_0.size_bytes,
        "title": POKEMON_RED_US_REV_0.title,
    }
    assert receipt["checkpoints"] == {
        "all_verified": True,
        "ids": [
            "bedroom_ready",
            "downstairs",
            "outside",
            "oak_triggered",
            "selection_ready",
            "starter_obtained",
        ],
        "verified": 6,
    }
    assert receipt["starter"] == {
        "controls_ready": True,
        "event_verified": True,
        "map_id": 40,
        "party_count": 1,
        "player_x": 7,
        "player_y": 4,
        "species": "squirtle",
        "species_id": 177,
    }
    assert receipt["objective_progress"] == {
        "next": "receive_pokedex",
        "total": 36,
        "verified": 3,
        "verified_ids": ["power_on", "begin_adventure", "choose_starter"],
    }
    assert receipt["repeatability"] == {
        "identical_action_count": True,
        "identical_final_state": True,
        "identical_frame_count": True,
    }
    assert receipt["frames_executed"] == 21_216
    assert receipt["actions_executed"] == 178
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized
