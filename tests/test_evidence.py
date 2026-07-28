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
from pokemon_red_completion.pewter import DEFAULT_PEWTER_TIMING
from pokemon_red_completion.play import DEFAULT_QUALIFIED_PLAY_TIMING
from pokemon_red_completion.provenance import GIT_COMMIT, canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUALIFIED_SOURCE_COMMIT = "0fb14ac7f287e92fe270b3811f1ef495cbc36194"
OPENING_SOURCE_COMMIT = "898f015e297aae4f5d1ae3d200285e58f182d306"
POKEDEX_SOURCE_COMMIT = "f6feaab2e4864b27efacfe319eb7ac53b50707a4"
BROCK_SOURCE_COMMIT = "0021ef7a3d267a222e53d388928f0a5fa4221d01"
BOOTSTRAP_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "bootstrap-smoke-2026-07-28.json"
OPENING_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "opening-squirtle-2026-07-28.json"
POKEDEX_RECEIPT = (
    PROJECT_ROOT / "docs" / "evidence" / "qualified-play-pokedex-2026-07-28.json"
)
BROCK_RECEIPT = (
    PROJECT_ROOT / "docs" / "evidence" / "qualified-play-brock-2026-07-28.json"
)


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


def test_pokedex_receipt_is_source_bound_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(POKEDEX_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v1"
    assert receipt["schema"] == "qualified-play-v1"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["source"] == {
        "git_commit": POKEDEX_SOURCE_COMMIT,
        "worktree_dirty": False,
    }
    assert GIT_COMMIT.fullmatch(receipt["source"]["git_commit"])
    assert receipt["recorded_on"] == "2026-07-28"

    intro = DEFAULT_NEW_GAME_TIMING
    opening = DEFAULT_OPENING_TIMING
    play = DEFAULT_QUALIFIED_PLAY_TIMING
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
            name: getattr(opening, name)
            for name in opening.__dataclass_fields__
        },
        "pret_pokered_commit": PRET_POKERED_COMMIT,
        "qualified_play_timing": {
            name: getattr(play, name)
            for name in play.__dataclass_fields__
        },
        "route_encounter_policy": "fail_closed",
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
    assert receipt["checkpoints"]["verified"] == 11
    assert receipt["checkpoints"]["all_verified"] is True
    assert receipt["objective_progress"] == {
        "next": "reach_pewter",
        "total": 36,
        "verified": 4,
        "verified_ids": [
            "power_on",
            "begin_adventure",
            "choose_starter",
            "receive_pokedex",
        ],
    }
    assert receipt["rival"] == {
        "hp": 21,
        "level": 6,
        "max_hp": 21,
        "species": "squirtle",
        "species_id": 177,
        "trainer_battle_observed": True,
        "victory_verified": True,
    }
    assert receipt["parcel"] == {
        "delivered_verified": True,
        "present_after_delivery": False,
        "received_verified": True,
    }
    assert receipt["pokedex"] == {
        "controls_ready": True,
        "received_verified": True,
    }
    assert receipt["repeatability"] == {
        "identical_action_count": True,
        "identical_final_state": True,
        "identical_frame_count": True,
    }
    assert receipt["qualified_through"] == "receive_pokedex"
    assert receipt["game_complete"] is False
    assert receipt["frames_executed"] == 52_956
    assert receipt["actions_executed"] == 619
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_brock_receipt_is_source_bound_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(BROCK_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v2"
    assert receipt["schema"] == "qualified-play-v2"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["assistance"] == {
        "class": "deterministic_teacher",
        "human_controller_input": False,
        "save_state_restore": False,
    }
    assert receipt["source"] == {
        "git_commit": BROCK_SOURCE_COMMIT,
        "worktree_dirty": False,
    }
    assert GIT_COMMIT.fullmatch(receipt["source"]["git_commit"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", receipt["python_version"])
    assert receipt["recorded_on"] == "2026-07-28"

    intro = DEFAULT_NEW_GAME_TIMING
    opening = DEFAULT_OPENING_TIMING
    play = DEFAULT_QUALIFIED_PLAY_TIMING
    pewter = DEFAULT_PEWTER_TIMING
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
            name: getattr(opening, name)
            for name in opening.__dataclass_fields__
        },
        "pewter_timing": {
            name: getattr(pewter, name)
            for name in pewter.__dataclass_fields__
        },
        "pret_pokered_commit": PRET_POKERED_COMMIT,
        "qualified_play_timing": {
            name: getattr(play, name)
            for name in play.__dataclass_fields__
        },
        "route_encounter_policy": (
            "fail_closed_except_three_verified_kakuna_and_one_bug_catcher"
        ),
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
    assert receipt["checkpoints"]["verified"] == 21
    assert receipt["checkpoints"]["all_verified"] is True
    assert receipt["checkpoints"]["ids"][-2:] == [
        "brock_battle",
        "brock_defeated",
    ]
    assert receipt["northbound"] == {
        "brock_battle_observed": True,
        "ordered_boundaries_total": 9,
        "ordered_boundaries_verified": 9,
    }
    assert receipt["brock"] == {
        "boulder_badge_verified": True,
        "bubble_pp": 23,
        "squirtle_hp": 27,
        "squirtle_level": 12,
        "squirtle_max_hp": 33,
        "squirtle_status": 0,
        "tm34_verified": True,
        "victory_verified": True,
    }
    assert receipt["objective_progress"] == {
        "next": "reach_cerulean",
        "total": 36,
        "verified": 6,
        "verified_ids": [
            "power_on",
            "begin_adventure",
            "choose_starter",
            "receive_pokedex",
            "reach_pewter",
            "defeat_brock",
        ],
    }
    assert receipt["repeatability"] == {
        "identical_action_count": True,
        "identical_final_state": True,
        "identical_frame_count": True,
    }
    assert receipt["qualified_through"] == "defeat_brock"
    assert receipt["game_complete"] is False
    assert receipt["frames_executed"] == 121_247
    assert receipt["actions_executed"] == 1_554
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized
