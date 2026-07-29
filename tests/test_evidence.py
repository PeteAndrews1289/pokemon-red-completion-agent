from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.cerulean import DEFAULT_CERULEAN_TIMING
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
from pokemon_red_completion.vermilion import DEFAULT_VERMILION_TIMING

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUALIFIED_SOURCE_COMMIT = "0fb14ac7f287e92fe270b3811f1ef495cbc36194"
OPENING_SOURCE_COMMIT = "898f015e297aae4f5d1ae3d200285e58f182d306"
POKEDEX_SOURCE_COMMIT = "f6feaab2e4864b27efacfe319eb7ac53b50707a4"
BROCK_SOURCE_COMMIT = "4af043f400754d473f8e9cf3779065afff4dff67"
CERULEAN_SOURCE_COMMIT = "30c58d555a5031cf50775943c21ad31c2239eb1a"
MISTY_RUNTIME_SNAPSHOT_SHA256 = "4b7490b5d7cb4e3cc020306da54e9fe85819ebf0209b2277068a7dc4f0a854d3"
MISTY_CONFIGURATION_SHA256 = "126faded5ef92cb564a22a500d5b2c1ceb808bfeba28a69673c1c449e9932ebb"
VERMILION_RUNTIME_SNAPSHOT_SHA256 = (
    "9dd1a77cfb83097d16dbf5406ee8a79340aa47e0d3907283b12aa2c0015894c8"
)
VERMILION_CONFIGURATION_SHA256 = "f00e1754db9da55d2ed7cab85ffa991da648b6209d9ba36d77a182e047632006"
BOOTSTRAP_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "bootstrap-smoke-2026-07-28.json"
OPENING_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "opening-squirtle-2026-07-28.json"
POKEDEX_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-pokedex-2026-07-28.json"
BROCK_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-brock-2026-07-28.json"
CERULEAN_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-cerulean-2026-07-28.json"
MISTY_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-misty-2026-07-28.json"
VERMILION_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-vermilion-2026-07-28.json"
SURGE_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-surge-2026-07-29.json"
LAVENDER_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-lavender-2026-07-29.json"
FUJI_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-fuji-2026-07-29.json"
FUCHSIA_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-fuchsia-2026-07-29.json"
SURF_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-surf-2026-07-29.json"
KOGA_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-koga-2026-07-29.json"


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
        "opening_timing": {name: getattr(opening, name) for name in opening.__dataclass_fields__},
        "pret_pokered_commit": PRET_POKERED_COMMIT,
        "qualified_play_timing": {name: getattr(play, name) for name in play.__dataclass_fields__},
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
        "opening_timing": {name: getattr(opening, name) for name in opening.__dataclass_fields__},
        "pewter_timing": {name: getattr(pewter, name) for name in pewter.__dataclass_fields__},
        "pret_pokered_commit": PRET_POKERED_COMMIT,
        "qualified_play_timing": {name: getattr(play, name) for name in play.__dataclass_fields__},
        "route_encounter_policy": ("fail_closed_except_three_verified_kakuna_and_one_bug_catcher"),
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
        "overworld_control_verified": True,
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
    assert receipt["frames_executed"] == 122_999
    assert receipt["actions_executed"] == 1_573
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_cerulean_receipt_is_source_bound_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(CERULEAN_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v3"
    assert receipt["schema"] == "qualified-play-v3"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["assistance"] == {
        "class": "deterministic_teacher",
        "human_controller_input": False,
        "save_state_restore": False,
    }
    assert receipt["source"] == {
        "git_commit": CERULEAN_SOURCE_COMMIT,
        "worktree_dirty": False,
    }
    assert GIT_COMMIT.fullmatch(receipt["source"]["git_commit"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", receipt["python_version"])
    assert receipt["recorded_on"] == "2026-07-28"

    intro = DEFAULT_NEW_GAME_TIMING
    opening = DEFAULT_OPENING_TIMING
    play = DEFAULT_QUALIFIED_PLAY_TIMING
    pewter = DEFAULT_PEWTER_TIMING
    cerulean = DEFAULT_CERULEAN_TIMING
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
        "opening_timing": {name: getattr(opening, name) for name in opening.__dataclass_fields__},
        "pewter_timing": {name: getattr(pewter, name) for name in pewter.__dataclass_fields__},
        "cerulean_timing": {
            name: getattr(cerulean, name) for name in cerulean.__dataclass_fields__
        },
        "pret_pokered_commit": PRET_POKERED_COMMIT,
        "qualified_play_timing": {name: getattr(play, name) for name in play.__dataclass_fields__},
        "route_encounter_policy": (
            "fail_closed_except_three_verified_kakuna_and_required_trainers"
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
    assert receipt["checkpoints"]["verified"] == 36
    assert receipt["checkpoints"]["all_verified"] is True
    assert receipt["checkpoints"]["ids"][-15:] == [
        "route_3_reached",
        "route_3_trainer_0",
        "route_3_trainer_1",
        "route_3_trainer_3",
        "route_3_trainer_6",
        "route_4_reached",
        "mt_moon_entered",
        "mt_moon_b1f",
        "mt_moon_b2f",
        "required_rocket",
        "super_nerd",
        "helix_fossil",
        "mt_moon_b1f_ascent",
        "mt_moon_exited",
        "cerulean_reached",
    ]
    assert receipt["cerulean_chapter"] == {
        "route": {
            "ordered_boundaries_total": 8,
            "ordered_boundaries_verified": 8,
            "required_route_3_trainers": [0, 1, 3, 6],
        },
        "mt_moon": {
            "helix_fossil_verified": True,
            "required_rocket_battle_observed": True,
            "super_nerd_battle_observed": True,
        },
        "cerulean": {
            "arrival_verified": True,
            "map_id": 3,
            "player_x": 0,
            "player_y": 18,
            "wartortle_hp": 26,
            "wartortle_level": 17,
            "wartortle_max_hp": 49,
            "wartortle_status": 0,
        },
        "frames_executed": 129_990,
        "actions_executed": 2_031,
        "controller_released": True,
    }
    assert receipt["objective_progress"] == {
        "next": "help_bill",
        "total": 36,
        "verified": 7,
        "verified_ids": [
            "power_on",
            "begin_adventure",
            "choose_starter",
            "receive_pokedex",
            "reach_pewter",
            "defeat_brock",
            "reach_cerulean",
        ],
    }
    assert receipt["repeatability"] == {
        "identical_action_count": True,
        "identical_final_state": True,
        "identical_frame_count": True,
    }
    assert receipt["qualified_through"] == "reach_cerulean"
    assert receipt["game_complete"] is False
    assert receipt["frames_executed"] == 252_989
    assert receipt["actions_executed"] == 3_604
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_misty_receipt_is_source_bound_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(MISTY_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v4"
    assert receipt["schema"] == "qualified-play-v4"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["assistance"] == {
        "class": "deterministic_teacher",
        "human_controller_input": False,
        "save_state_restore": False,
        "learned_policy": False,
    }
    assert receipt["source"]["git_commit"] == "9137f20b2459128fee89c1fb47d468bd86059a6e"
    assert GIT_COMMIT.fullmatch(receipt["source"]["git_commit"])
    assert receipt["source"]["worktree_dirty"] is True

    recorded_runtime_digest = receipt["source"]["runtime_snapshot_sha256"]
    assert re.fullmatch(r"[0-9a-f]{64}", recorded_runtime_digest)
    assert recorded_runtime_digest == MISTY_RUNTIME_SNAPSHOT_SHA256

    configuration = receipt["configuration"]
    assert canonical_sha256(configuration) == MISTY_CONFIGURATION_SHA256
    assert configuration["pret_pokered_commit"] == PRET_POKERED_COMMIT
    assert configuration["starter"] == "squirtle"
    assert configuration["emulator"]["human_input"] is False
    assert configuration["emulator"]["save_on_exit"] is False
    assert receipt["configuration_sha256"] == canonical_sha256(configuration)
    assert receipt["rom"] == {
        "sha1": POKEMON_RED_US_REV_0.sha1,
        "sha256": POKEMON_RED_US_REV_0.sha256,
        "size_bytes": POKEMON_RED_US_REV_0.size_bytes,
        "title": POKEMON_RED_US_REV_0.title,
    }
    assert receipt["checkpoints"]["verified"] == 58
    assert receipt["checkpoints"]["all_verified"] is True
    assert len(receipt["checkpoints"]["ids"]) == 58
    assert receipt["checkpoints"]["ids"][-4:] == [
        "cerulean_gym_trainer_battle",
        "cerulean_gym_trainer_defeated",
        "misty_battle",
        "misty_defeated",
    ]
    assert receipt["cascade_chapter"]["cascade"] == {
        "victory_verified": True,
        "badge_verified": True,
        "tm11_verified": True,
        "ss_ticket_verified": True,
        "wartortle_level": 24,
        "wartortle_hp": 4,
        "wartortle_max_hp": 66,
        "wartortle_status": 0,
    }
    assert receipt["cascade_chapter"]["frames_executed"] == 181_521
    assert receipt["cascade_chapter"]["actions_executed"] == 2_332
    assert receipt["objective_progress"] == {
        "next": "reach_vermilion",
        "total": 36,
        "verified": 9,
        "verified_ids": [
            "power_on",
            "begin_adventure",
            "choose_starter",
            "receive_pokedex",
            "reach_pewter",
            "defeat_brock",
            "reach_cerulean",
            "help_bill",
            "defeat_misty",
        ],
    }
    assert receipt["repeatability"] == {
        "identical_action_count": True,
        "identical_final_state": True,
        "identical_frame_count": True,
    }
    assert receipt["scope"] == {
        "claim": "exact deterministic teacher repeat",
        "timing_or_rng_generalization": False,
        "learned_policy_generalization": False,
        "game_complete": False,
    }
    assert receipt["qualified_through"] == "defeat_misty"
    assert receipt["game_complete"] is False
    assert receipt["frames_executed"] == 434_510
    assert receipt["actions_executed"] == 5_936
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_vermilion_receipt_is_source_bound_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(VERMILION_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v5"
    assert receipt["schema"] == "qualified-play-v5"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["assistance"] == {
        "class": "deterministic_teacher",
        "human_controller_input": False,
        "save_state_restore": False,
        "learned_policy": False,
    }
    assert receipt["source"] == {
        "git_commit": "4b2beb4c36a2228e2e922c31285883a174e4b446",
        "worktree_dirty": True,
        "runtime_snapshot_sha256": VERMILION_RUNTIME_SNAPSHOT_SHA256,
    }
    assert GIT_COMMIT.fullmatch(receipt["source"]["git_commit"])

    controller = DEFAULT_NEW_GAME_TIMING
    expected_configuration = {
        "battle_policy": ("adaptive_rocket_and_fixed_route6_trainers_with_bounded_sleep_recovery"),
        "controller_timing": {
            "press_frames": controller.press_frames,
            "release_frames": controller.release_frames,
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
        "pret_pokered_commit": PRET_POKERED_COMMIT,
        "route_encounter_policy": (
            "three_exact_route6_pidgey_encounters_with_semantic_run_and_pp_event_gates"
        ),
        "starter": "squirtle",
        "vermilion_timing": asdict(DEFAULT_VERMILION_TIMING),
    }
    assert receipt["configuration"] == expected_configuration
    assert canonical_sha256(expected_configuration) == VERMILION_CONFIGURATION_SHA256
    assert receipt["configuration_sha256"] == VERMILION_CONFIGURATION_SHA256
    assert receipt["rom"] == {
        "sha1": POKEMON_RED_US_REV_0.sha1,
        "sha256": POKEMON_RED_US_REV_0.sha256,
        "size_bytes": POKEMON_RED_US_REV_0.size_bytes,
        "title": POKEMON_RED_US_REV_0.title,
    }

    checkpoints = receipt["checkpoints"]
    assert checkpoints["all_verified"] is True
    assert checkpoints["verified"] == len(checkpoints["ids"]) == 73
    assert checkpoints["ids"][-5:] == [
        "route_6_trainer_f_battle",
        "route_6_trainer_f_defeated",
        "route_6_trainer_m_battle",
        "route_6_trainer_m_defeated",
        "vermilion_reached",
    ]
    chapter = receipt["vermilion_chapter"]
    assert chapter["frames_executed"] == 67_412
    assert chapter["actions_executed"] == 1_306
    assert chapter["controller_released"] is True
    assert chapter["route"]["route_6_trainer_events"] == [
        False,
        False,
        False,
        True,
        True,
        False,
    ]
    assert [
        (item["x"], item["y"], item["species_id"]) for item in chapter["route"]["wild_flees"]
    ] == [(15, 19, 0x24), (15, 22, 0x24), (15, 26, 0x24)]
    assert all(
        item["battle_state_before"] == 1
        and item["battle_state_after"] == 0
        and item["pp_unchanged"]
        and item["control_ready"]
        for item in chapter["route"]["wild_flees"]
    )
    assert chapter["trainer_f"] == {
        "start_hp": 53,
        "start_max_hp": 66,
        "start_pp": [24, 30, 30, 22],
        "final_hp": 27,
        "final_pp": [18, 30, 30, 22],
        "status": 0,
    }
    assert chapter["trainer_m"] == {
        "start_hp": 66,
        "start_max_hp": 66,
        "start_pp": [25, 30, 30, 25],
        "final_hp": 42,
        "final_max_hp": 69,
        "final_pp": [20, 30, 30, 25],
        "status": 0,
    }
    assert receipt["objective_progress"]["verified"] == 10
    assert receipt["objective_progress"]["total"] == 36
    assert receipt["objective_progress"]["next"] == "obtain_cut"
    assert receipt["repeatability"] == {
        "identical_action_count": True,
        "identical_final_state": True,
        "identical_frame_count": True,
        "identical_semantic_digest": True,
        "semantic_digest_sha256": (
            "84b6ee9dc46d56359ad7feafc2e9ce48f7c17d0667c7d67f2254e4af9808773e"
        ),
    }
    assert receipt["qualified_through"] == "reach_vermilion"
    assert receipt["game_complete"] is False
    assert receipt["frames_executed"] == 501_922
    assert receipt["actions_executed"] == 7_242
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_surge_receipt_is_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(SURGE_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v7"
    assert receipt["schema"] == "qualified-play-v7"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["checkpoints"]["all_verified"] is True
    assert receipt["checkpoints"]["verified"] == 97
    assert len(receipt["checkpoints"]["surge_ids"]) == 15
    assert receipt["surge_chapter"]["battle"] == {
        "dig_attacks": 5,
        "wrong_move_count": 0,
    }
    assert receipt["surge_chapter"]["reward"] == {
        "beat_lt_surge": True,
        "got_tm24": True,
        "tm24_in_bag": True,
        "thunder_badge": True,
        "thunder_badge_mirror": True,
    }
    assert receipt["surge_chapter"]["recovery"] == {
        "super_potion_used": False,
        "lead_hp": 71,
        "lead_max_hp": 71,
        "status": 0,
    }
    assert receipt["objective_progress"]["verified"] == 12
    assert receipt["objective_progress"]["next"] == "reach_lavender"
    assert receipt["qualified_through"] == "defeat_surge"
    assert receipt["game_complete"] is False
    assert receipt["frames_executed"] == 635_637
    assert receipt["actions_executed"] == 9_311
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_lavender_receipt_is_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(LAVENDER_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v8"
    assert receipt["schema"] == "qualified-play-v8"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["checkpoints"]["all_verified"] is True
    assert receipt["checkpoints"]["verified"] == 112
    assert len(receipt["checkpoints"]["lavender_ids"]) == 15
    assert len(receipt["lavender_chapter"]["trainer_battles"]) == 11
    assert receipt["lavender_chapter"]["wild_flees"] == 8
    assert receipt["lavender_chapter"]["inventory"] == {
        "money_remaining": 14_301,
        "purchase_cost": 7_000,
        "repels_purchased": 4,
        "repels_used": 4,
        "super_potions_purchased": 8,
        "super_potions_remaining": 4,
        "super_potions_used": 5,
    }
    assert receipt["lavender_chapter"]["party"] == {
        "hp": [79, 52, 37],
        "max_hp": [79, 52, 37],
        "species": [179, 64, 59],
        "status": [0, 0, 0],
    }
    assert receipt["lavender_chapter"]["route_10_trainer_2_bypassed"] is True
    assert receipt["objective_progress"]["verified"] == 13
    assert receipt["objective_progress"]["next"] == "reach_celadon"
    assert receipt["qualified_through"] == "reach_lavender"
    assert receipt["game_complete"] is False
    assert receipt["frames_executed"] == 858_008
    assert receipt["actions_executed"] == 12_713
    assert receipt["controller_released"] is True
    assert receipt["repeatability"]["full_report_sha256"] == (
        "2b6ed8dce8d913b89e6d4226ece3f73e0e7919f656476e19acea475b06949b89"
    )

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_fuji_receipt_is_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(FUJI_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v11"
    assert receipt["schema"] == "qualified-play-v11"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["checkpoints"] == {"all_verified": True, "verified": 170}
    tower = receipt["tower_chapter"]
    assert tower["trainer_sets"] == [5, 10, 14, 19, 21, 20, None, 19, 20, 21]
    assert tower["selected_pp_spent"] == [11, 4, 2, 5, 2, 2, 1, 4, 5, 4]
    assert tower["optional_trainers_bypassed"] == 8
    assert tower["required_events_verified"] == 13
    assert tower["purified_zone"] == {"event_observed": True, "full_party_heals": 3}
    assert tower["evolution"] == {
        "before_species": [179, 64, 59],
        "after_species": [28, 64, 59],
        "party_order_preserved": True,
        "lead_moves_preserved": True,
    }
    assert tower["inventory"]["super_potion_inventory_path"] == [2, 1, 0]
    assert tower["party"] == {
        "species": [28, 64, 59],
        "hp": [111, 52, 37],
        "max_hp": [111, 52, 37],
        "status": [0, 0, 0],
    }
    assert receipt["objective_progress"]["verified"] == 17
    assert receipt["objective_progress"]["next"] == "reach_fuchsia"
    assert receipt["repeatability"]["full_report_sha256"] == (
        "5322994a19cf54a7dc17c109f26af2b4ec34db3e838b403830d6c9e1d18ae045"
    )
    assert receipt["qualified_through"] == "rescue_fuji"
    assert receipt["frames_executed"] == 1_142_003
    assert receipt["actions_executed"] == 16_797
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_fuchsia_receipt_is_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(FUCHSIA_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v12"
    assert receipt["schema"] == "qualified-play-v12"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["checkpoints"] == {"all_verified": True, "verified": 184}
    chapter = receipt["fuchsia_chapter"]
    assert chapter["trainer_sets"] == [3, None, 2, 1, 12]
    assert chapter["selected_pp_spent"] == [5, 4, 2, 4, 5]
    assert chapter["required_events_verified"] == 5
    assert chapter["optional_events_false"] == 35
    assert chapter["optional_items_untouched"] == 5
    assert chapter["wild_flees"] == 4
    assert chapter["snorlax"] == {
        "species": 132,
        "level": 30,
        "fight_event_before": False,
        "fight_event_after": False,
        "beat_event": True,
        "object_tile_crossed": True,
        "poke_flute_retained": True,
    }
    assert chapter["recovery"]["consumable_items_used"] == 0
    assert chapter["recovery"]["bag_preserved"] is True
    assert chapter["party"] == {
        "species": [28, 64, 59],
        "hp": [114, 52, 37],
        "max_hp": [114, 52, 37],
        "status": [0, 0, 0],
    }
    assert receipt["objective_progress"]["verified"] == 18
    assert receipt["objective_progress"]["next"] == "obtain_surf"
    assert receipt["repeatability"]["full_report_sha256"] == (
        "2e6db96e0308777af8b34a8fec4f5d9405636d300e4f5918f55732e0ed40862b"
    )
    assert receipt["qualified_through"] == "reach_fuchsia"
    assert receipt["frames_executed"] == 1_419_928
    assert receipt["actions_executed"] == 19_073
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_surf_receipt_is_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(SURF_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v13"
    assert receipt["schema"] == "qualified-play-v13"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["checkpoints"] == {"all_verified": True, "verified": 196}
    chapter = receipt["safari_chapter"]
    assert chapter["admission_fee"] == 500
    assert chapter["initial_internal_steps"] == 502
    assert chapter["center_entry_steps"] == 500
    assert chapter["step_milestones"] == [500, 472, 376, 238, 228, 201, 0]
    assert chapter["balls_milestones"] == [30] * 7
    assert chapter["safari_encounters_run"] == 6
    assert chapter["safari_balls_thrown"] == 0
    assert chapter["pokemon_caught"] == 0
    assert chapter["optional_items_collected"] == 0
    assert chapter["gold_teeth_collected"] is True
    assert chapter["got_hm03_event"] is True
    assert chapter["hm03_reusable_and_retained"] is True
    assert chapter["surf"] == {
        "move_id": 57,
        "replaced_move_id": 55,
        "slot": 4,
        "moves_before": [44, 39, 61, 55],
        "moves_after": [44, 39, 61, 57],
        "pp_after": [25, 30, 20, 15],
    }
    assert chapter["cleanup"] == {
        "mechanism": "times_up",
        "safari_steps": 0,
        "safari_balls": 0,
        "in_safari_zone": False,
    }
    assert receipt["objective_progress"]["verified"] == 19
    assert receipt["objective_progress"]["next"] == "defeat_erika"
    assert receipt["repeatability"]["full_report_sha256"] == (
        "47b107378496fc42a9d68ef5c1cb404617bfbe47d310d743439bc0ece6344978"
    )
    assert receipt["qualified_through"] == "obtain_surf"
    assert receipt["frames_executed"] == 1_630_696
    assert receipt["actions_executed"] == 20_737
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_koga_receipt_is_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(KOGA_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v14"
    assert receipt["schema"] == "qualified-play-v14"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["checkpoints"] == {"all_verified": True, "verified": 207}
    chapter = receipt["koga_chapter"]
    assert [item["trainer_number"] for item in chapter["mandatory_trainers"]] == [3, 2, 4]
    assert [item["surf_pp_spent"] for item in chapter["mandatory_trainers"]] == [6, 5, 5]
    assert chapter["trainer_events_before_koga"] == [
        False,
        True,
        False,
        False,
        True,
        True,
    ]
    assert chapter["optional_trainers_undefeated_before_koga"] == 3
    assert chapter["recoveries_before_koga"] == 2
    assert chapter["koga"]["surf_pp_spent"] == 8
    assert chapter["koga"]["no_faint"] is True
    assert chapter["rewards"] == {
        "beat_koga_event": True,
        "soul_badge": True,
        "soul_badge_mirror": True,
        "got_tm06_event": True,
        "tm06_toxic_retained": True,
        "all_six_regular_trainers_deactivated": True,
    }
    assert chapter["terminal"]["party_hp"] == chapter["terminal"]["party_max_hp"] == [
        124,
        52,
        37,
    ]
    assert receipt["objective_progress"]["verified"] == 20
    assert receipt["objective_progress"]["next"] == "defeat_erika"
    assert receipt["repeatability"]["full_report_sha256"] == (
        "4d5c1589f9e31a8fec5b1d3a5a9af58951c9250763fea5a386d77dc4cb7ae226"
    )
    assert receipt["qualified_through"] == "defeat_koga"
    assert receipt["frames_executed"] == 1_782_032
    assert receipt["actions_executed"] == 22_053
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized
