from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.cerulean import DEFAULT_CERULEAN_TIMING
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.navigation import path_to_directions
from pokemon_red_completion.observation import ItemId, MapId
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
STRENGTH_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-strength-2026-07-29.json"
SAFFRON_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-saffron-2026-07-29.json"
SILPH_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-silph-2026-07-29.json"
SABRINA_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-sabrina-2026-07-29.json"
CINNABAR_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-cinnabar-2026-07-29.json"
BLAINE_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-blaine-2026-07-29.json"
GIOVANNI_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-giovanni-2026-07-29.json"
VICTORY_ROAD_RECEIPT = (
    PROJECT_ROOT / "docs" / "evidence" / "qualified-play-victory-road-2026-07-29.json"
)
LORELEI_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "qualified-play-lorelei-2026-07-29.json"
TRAJECTORY_FOUNDATION_RECEIPT = (
    PROJECT_ROOT / "docs" / "evidence" / "private-trajectory-foundation-2026-07-30.json"
)
BATTLE_DECISION_RECEIPT = (
    PROJECT_ROOT / "docs" / "evidence" / "private-battle-decisions-2026-07-30.json"
)
BATTLE_IMITATION_RECEIPT = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "private-battle-imitation-diagnostic-2026-07-30.json"
)
ROUTE1_ACQUISITION_RECEIPT = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "qualified-play-route1-acquisition-2026-08-02.json"
)
VIRIDIAN_FOREST_RECEIPT = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "qualified-play-viridian-forest-2026-08-02.json"
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
    assert (
        chapter["terminal"]["party_hp"]
        == chapter["terminal"]["party_max_hp"]
        == [
            124,
            52,
            37,
        ]
    )
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


def test_strength_receipt_is_repeatable_and_privacy_safe() -> None:
    receipt = json.loads(STRENGTH_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["receipt_schema"] == "qualified-play-evidence-v15"
    assert receipt["schema"] == "qualified-play-v15"
    assert receipt["status"] == "ok"
    assert receipt["attempts"] == {"failed": 0, "passed": 3, "total": 3}
    assert receipt["checkpoints"] == {"all_verified": True, "verified": 215}
    chapter = receipt["strength_chapter"]
    assert chapter["reward_sequence"] == [
        {
            "step": 1,
            "gave_gold_teeth_event": True,
            "got_hm04_event": False,
            "gold_teeth_removed": True,
            "hm04_present": False,
        },
        {
            "step": 2,
            "gave_gold_teeth_event": True,
            "got_hm04_event": True,
            "gold_teeth_removed": True,
            "hm04_present": True,
        },
    ]
    assert chapter["strength"] == {
        "move_id": 70,
        "replaced_move_id": 39,
        "slot": 2,
        "moves_before": [44, 39, 61, 57],
        "moves_after": [44, 70, 61, 57],
        "pp_after": [25, 15, 20, 15],
        "hm04_reusable_and_retained": True,
    }
    assert chapter["money_before"] == chapter["money_remaining"] == 37_489
    assert receipt["objective_progress"]["verified"] == 21
    assert receipt["objective_progress"]["next"] == "defeat_erika"
    assert receipt["repeatability"]["full_report_sha256"] == (
        "2234503e670b5a2740cf37e61d421b113166fb07595e8009e8e0f86801714c3e"
    )
    assert receipt["qualified_through"] == "obtain_strength"
    assert receipt["frames_executed"] == 1_875_968
    assert receipt["actions_executed"] == 22_779
    assert receipt["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_saffron_receipt_is_repeatable_ordered_and_privacy_safe() -> None:
    receipt = json.loads(SAFFRON_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "qualified-play-v17-receipt"
    assert receipt["status"] == "ok"
    assert receipt["evaluation"] == {
        "clean_power_on": True,
        "human_input": False,
        "save_state_restoration": False,
        "runs": 3,
        "identical_reports": True,
        "report_sha256": ("42f68a663ef3a6c078eccda0fc81b92bb91152009d953cc801377a921d93038c"),
        "frames_per_run": 2_284_226,
        "actions_per_run": 26_012,
    }
    assert receipt["progress"] == {
        "checkpoints_verified": 235,
        "checkpoints_total": 235,
        "objectives_verified": 23,
        "objectives_total": 36,
        "next_objective": "liberate_silph",
    }
    chapter = receipt["saffron_chapter"]
    assert chapter["vending_machine"] == {
        "floor": "celadon_mart_roof",
        "cursor": 0,
        "item_id": int(ItemId.FRESH_WATER),
        "price": 200,
        "money_before": 41_545,
        "money_after": 41_345,
    }
    assert chapter["guard_handoff"] == {
        "fresh_water_before": 0,
        "fresh_water_after_purchase": 1,
        "fresh_water_after_guard": 0,
        "flag_before": 0,
        "flag_after_consumption": 0,
        "flag_after_dialogue": 64,
        "consumed_before_global_access": True,
        "soda_pop_absent": True,
        "lemonade_absent": True,
    }
    assert chapter["battle_free"] is True
    assert chapter["terminal"]["map"] == int(MapId.SAFFRON_POKECENTER)
    assert chapter["terminal"]["party_hp"] == chapter["terminal"]["party_max_hp"]

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_silph_receipt_is_repeatable_complete_and_privacy_safe() -> None:
    receipt = json.loads(SILPH_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "qualified-play-v18-receipt"
    assert receipt["status"] == "ok"
    assert receipt["claim_scope"] == {
        "qualified_through": "liberate_silph",
        "game_complete": False,
        "learned_policy": False,
        "timing_or_rng_generalization": False,
    }
    assert receipt["evaluation"] == {
        "clean_power_on": True,
        "human_input": False,
        "save_state_restoration": False,
        "runs": 3,
        "identical_reports": True,
        "report_sha256": ("7ac303e831446a617b3c7b8eccca2fd7379749bf2e32216f0b42e91cd85ecde3"),
        "frames_per_run": 3_323_717,
        "actions_per_run": 29_473,
    }
    assert receipt["progress"] == {
        "checkpoints_verified": 247,
        "checkpoints_total": 247,
        "objectives_verified": 24,
        "objectives_total": 36,
        "next_objective": "defeat_sabrina",
    }
    chapter = receipt["silph_chapter"]
    assert chapter["ice_beam_upgrade"] == {
        "max_repel_bought": 1,
        "max_repel_remaining": 0,
        "fresh_water_remaining": 0,
        "tm13_event": True,
        "tm13_transfer_before_event": True,
        "other_roof_rewards_untouched": True,
        "tm13_remaining": 0,
        "moves": [130, 70, 58, 57],
        "pp": [15, 15, 10, 15],
    }
    assert chapter["supply"] == {
        "hyper_potions_bought": 6,
        "used_by_rival_policy": 0,
        "remaining": 6,
    }
    assert chapter["key_items"] == {"card_key": 1, "master_ball": 1}
    assert chapter["optional_lapras_untouched"] is True
    assert all(chapter["required_events"].values())
    assert chapter["terminal"]["map"] == int(MapId.SAFFRON_POKECENTER)
    assert chapter["terminal"]["controller_released"] is True

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_sabrina_receipt_is_repeatable_complete_and_privacy_safe() -> None:
    receipt = json.loads(SABRINA_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "qualified-play-v19-receipt"
    assert receipt["status"] == "ok"
    assert receipt["evaluation"]["runs"] == 3
    assert receipt["evaluation"]["identical_reports"] is True
    assert receipt["evaluation"]["report_sha256"] == (
        "e575b1411adab8a6ff9f80b533988f20e98c6a67a365fa7f1304be666a170655"
    )
    assert receipt["evaluation"]["frames_per_run"] == 3_497_826
    assert receipt["evaluation"]["actions_per_run"] == 30_048
    assert receipt["progress"] == {
        "checkpoints_verified": 253,
        "checkpoints_total": 253,
        "objectives_verified": 25,
        "objectives_total": 36,
        "next_objective": "reach_cinnabar",
    }
    chapter = receipt["sabrina_chapter"]
    assert chapter["trainer_free_warp_route"] is True
    assert chapter["regular_trainer_events_before"] == [False] * 7
    assert chapter["identity"] == [0xF0, 0xF0, 1]
    assert chapter["party"] == [[0x26, 38], [0x2A, 37], [0x77, 38], [0x95, 43]]
    assert chapter["move_slots"] == [2, 2, 3, 3, 3, 2]
    assert chapter["faints"] == chapter["persistent_status"] == chapter["hyper_potions_used"] == 0
    assert chapter["rewards"] == {
        "tm46_quantity": 1,
        "tm46_event": True,
        "sabrina_event": True,
        "marsh_badge": True,
        "marsh_badge_mirror": True,
        "regular_trainers_deactivated": True,
    }
    assert chapter["terminal"]["party_hp"] == chapter["terminal"]["party_max_hp"]
    assert chapter["terminal"]["lead_pp"] == [15, 15, 10, 15]
    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_cinnabar_receipt_is_repeatable_complete_and_privacy_safe() -> None:
    receipt = json.loads(CINNABAR_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "qualified-play-v20-receipt"
    assert receipt["status"] == "ok"
    assert receipt["claim_scope"]["qualified_through"] == "reach_cinnabar"
    assert receipt["evaluation"] == {
        "clean_power_on": True,
        "human_input": False,
        "save_state_restoration": False,
        "runs": 3,
        "identical_reports": True,
        "report_sha256": "77bb810300445c6e297352768e03e6cbec1bdc288e42bae055bd38fd2bb0d0f2",
        "frames_per_run": 3_648_870,
        "actions_per_run": 30_910,
    }
    assert receipt["progress"] == {
        "checkpoints_verified": 259,
        "checkpoints_total": 259,
        "objectives_verified": 26,
        "objectives_total": 36,
        "next_objective": "obtain_secret_key",
    }
    chapter = receipt["cinnabar_chapter"]
    assert chapter["bicycle_required"] is False
    assert chapter["route16_cut_lane"] is True
    assert chapter["hm02"]["item_and_event_same_pulse"] is True
    assert chapter["hm02"]["dux_moves_after"] == [0x40, 0x1C, 0x0F, 0x13]
    assert chapter["route21"]["trainer_events_before"] == [False] * 9
    assert chapter["route21"]["trainer_events_after"] == [False] * 9
    assert chapter["route21"]["trainer_battles"] == 0
    assert [
        (item["position"], item["species"], item["level"])
        for item in chapter["route21"]["wild_flees"]
    ] == [([4, 12], 0xA5, 21), ([3, 52], 0x18, 10), ([3, 77], 0x18, 10)]
    assert all(
        item["party_preserved"]
        and item["pp_preserved"]
        and item["hp_safe"]
        and item["inventory_preserved"]
        for item in chapter["route21"]["wild_flees"]
    )
    assert chapter["terminal"]["party_hp"] == chapter["terminal"]["party_max_hp"]
    assert chapter["terminal"]["controller_released"] is True
    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_blaine_receipt_is_repeatable_complete_and_privacy_safe() -> None:
    receipt = json.loads(BLAINE_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "qualified-play-v21-receipt"
    assert receipt["status"] == "ok"
    assert receipt["claim_scope"] == {
        "qualified_through": "defeat_blaine",
        "game_complete": False,
        "learned_policy": False,
        "timing_or_rng_generalization": False,
    }
    assert receipt["evaluation"] == {
        "clean_power_on": True,
        "human_input": False,
        "save_state_restoration": False,
        "runs": 3,
        "identical_reports": True,
        "report_sha256": "f26bcfbd2051fffcbd32eee6186acef215f22fb2c7aeec53139eae07d8749b3b",
        "frames_per_run": 3_869_179,
        "actions_per_run": 32_695,
    }
    assert receipt["progress"] == {
        "checkpoints_verified": 267,
        "checkpoints_total": 267,
        "objectives_verified": 28,
        "objectives_total": 36,
        "next_objective": "defeat_giovanni",
    }
    chapter = receipt["blaine_chapter"]
    assert chapter["frames"] == 220_309
    assert chapter["actions"] == 1_785
    assert chapter["mansion"]["switch_trace"] == [False, True, False, True]
    assert chapter["mansion"]["optional_trainers_before"] == [False] * 6
    assert chapter["mansion"]["optional_trainers_after"] == [False] * 6
    assert chapter["mansion"]["secret_key_quantity"] == 1
    assert chapter["mansion"]["wild_battles"] == 0
    assert chapter["quiz"]["answers"] == ["yes", "no", "no", "no", "yes", "no"]
    assert chapter["quiz"]["gate_events_after"] == [False] + [True] * 6
    assert chapter["quiz"]["trainer_events_before"] == [False] * 7
    assert chapter["battle"]["identity"] == [0xEF, 0xEF, 1]
    assert chapter["battle"]["party"] == [[0x21, 42], [0xA3, 40], [0xA4, 42], [0x14, 47]]
    assert chapter["battle"]["move_slots"] == [4] * 5
    assert chapter["rewards"] == {
        "tm38_quantity": 1,
        "tm38_event": True,
        "blaine_event": True,
        "volcano_badge": True,
        "volcano_badge_mirror": True,
    }
    assert chapter["terminal"]["party_hp"] == chapter["terminal"]["party_max_hp"]
    assert chapter["terminal"]["lead_pp"] == [15, 15, 10, 15]
    assert chapter["terminal"]["controller_released"] is True
    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_giovanni_receipt_is_repeatable_complete_and_privacy_safe() -> None:
    receipt = json.loads(GIOVANNI_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "qualified-play-v22-receipt"
    assert receipt["status"] == "ok"
    assert receipt["claim_scope"] == {
        "qualified_through": "defeat_giovanni",
        "game_complete": False,
        "learned_policy": False,
        "timing_or_rng_generalization": False,
    }
    assert receipt["evaluation"] == {
        "clean_power_on": True,
        "human_input": False,
        "save_state_restoration": False,
        "runs": 3,
        "identical_reports": True,
        "report_sha256": "5019471510435fdedaba50ba514dd72ed2fe19c73ad0401870f3459e59d735e5",
        "frames_per_run": 4_033_092,
        "actions_per_run": 34_178,
    }
    assert receipt["progress"] == {
        "checkpoints_verified": 275,
        "checkpoints_total": 275,
        "objectives_verified": 29,
        "objectives_total": 36,
        "next_objective": "cross_victory_road",
    }
    chapter = receipt["giovanni_chapter"]
    assert chapter["frames"] == 163_913
    assert chapter["actions"] == 1_483
    assert chapter["inventory"] == {
        "tm46_sold": True,
        "tm27_quantity": 1,
        "money_before": 50_579,
        "money_after": 65_434,
    }
    assert chapter["gym"]["trainer_events_before"] == [False] * 8
    assert chapter["gym"]["trainer_events_before_giovanni"] == [
        True,
        True,
        True,
        False,
        True,
        True,
        False,
        True,
    ]
    assert chapter["gym"]["trainer_events_after"] == [True] * 8
    assert [battle["identity"] for battle in chapter["gym"]["required_battles"]] == [
        [0xE0, 0xE0, 8],
        [0xE0, 0xE0, 6],
        [0xE7, 0xE7, 9],
        [0xDE, 0xDE, 3],
        [0xE7, 0xE7, 10],
        [0xE7, 0xE7, 1],
    ]
    assert chapter["giovanni"] == {
        "identity": [0xE5, 0xE5, 3],
        "party": [[0x12, 45], [0x76, 42], [0x10, 44], [0x07, 45], [0x01, 50]],
        "move_slots": [4] * 5,
    }
    assert all(chapter["rewards"].values())
    assert chapter["terminal"]["party_hp"] == chapter["terminal"]["party_max_hp"]
    assert chapter["terminal"]["lead_pp"] == [15, 15, 10, 15]
    assert chapter["terminal"]["controller_released"] is True
    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_victory_road_receipt_is_repeatable_complete_and_privacy_safe() -> None:
    receipt = json.loads(VICTORY_ROAD_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "qualified-play-v23-receipt"
    assert receipt["status"] == "ok"
    assert receipt["claim_scope"] == {
        "qualified_through": "cross_victory_road",
        "game_complete": False,
        "learned_policy": False,
        "timing_or_rng_generalization": False,
    }
    assert receipt["evaluation"] == {
        "clean_power_on": True,
        "human_input": False,
        "save_state_restoration": False,
        "runs": 3,
        "identical_reports": True,
        "frames_per_run": 4_427_245,
        "actions_per_run": 37_535,
        "rom_adjacent_artifacts_unchanged": True,
    }
    assert receipt["progress"] == {
        "checkpoints_verified": 284,
        "checkpoints_total": 284,
        "objectives_verified": 30,
        "objectives_total": 36,
        "next_objective": "defeat_lorelei",
    }
    chapter = receipt["victory_road_chapter"]
    assert chapter["frames"] == 394_153
    assert chapter["actions"] == 3_357
    assert chapter["route22_rival"]["party"] == [
        [0x97, 47],
        [0x12, 45],
        [0x16, 45],
        [0x21, 47],
        [0x95, 50],
        [0x9A, 53],
    ]
    assert chapter["route23"]["remaining_badge_checks"] == [True] * 7
    assert all(chapter["victory_road"].values())
    terminal = chapter["terminal"]
    assert terminal["party_hp"] == terminal["party_max_hp"] == [157, 52, 37]
    assert terminal["lead_moves"] == [0x5C, 0x46, 0x3A, 0x39]
    assert terminal["lead_pp"] == [10, 15, 10, 15]
    assert terminal["controller_released"] is True
    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_lorelei_receipt_is_repeatable_complete_and_privacy_safe() -> None:
    receipt = json.loads(LORELEI_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "qualified-play-v24-receipt"
    assert receipt["claim_scope"] == {
        "qualified_through": "defeat_lorelei",
        "game_complete": False,
        "learned_policy": False,
        "timing_or_rng_generalization": False,
    }
    assert receipt["evaluation"] == {
        "clean_power_on": True,
        "human_input": False,
        "save_state_restoration": False,
        "runs": 3,
        "identical_reports": True,
        "frames_per_run": 4_496_270,
        "actions_per_run": 38_258,
        "rom_adjacent_artifacts_unchanged": True,
    }
    assert receipt["progress"] == {
        "checkpoints_verified": 287,
        "checkpoints_total": 287,
        "objectives_verified": 31,
        "objectives_total": 36,
        "next_objective": "defeat_bruno",
    }
    chapter = receipt["lorelei_chapter"]
    assert chapter["frames"] == 69_025
    assert chapter["actions"] == 723
    assert chapter["party"] == [
        [0x78, 54],
        [0x8B, 53],
        [0x08, 54],
        [0x48, 56],
        [0x13, 56],
    ]
    assert chapter["recovery"]["hyper_potions_used"] == 3
    assert chapter["recovery"]["full_restores_used"] == 2
    terminal = chapter["terminal"]
    assert terminal["party_hp"] == terminal["party_max_hp"] == [160, 52, 37]
    assert terminal["party_status"] == [0, 0, 0]
    assert terminal["lead_moves"] == [0x5C, 0x46, 0x3A, 0x39]
    assert terminal["lead_pp"] == [7, 0, 10, 9]
    assert terminal["controller_released"] is True
    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_trajectory_foundation_receipt_is_integrity_scoped_and_privacy_safe() -> None:
    receipt = json.loads(TRAJECTORY_FOUNDATION_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "private-trajectory-foundation-receipt-v1"
    assert receipt["recorded_on"] == "2026-07-30"
    assert receipt["evidence_lane"] == "deterministic_teacher_control_trace"
    assert receipt["claim_scope"] == {
        "game_complete": True,
        "learned_policy": False,
        "transfer_result": False,
        "model_ready_dataset": False,
    }
    assert GIT_COMMIT.fullmatch(receipt["source"]["git_commit"])
    assert receipt["source"]["worktree_dirty"] is False
    assert receipt["rom"] == {
        "title": POKEMON_RED_US_REV_0.title,
        "size_bytes": POKEMON_RED_US_REV_0.size_bytes,
        "sha1": POKEMON_RED_US_REV_0.sha1,
        "sha256": POKEMON_RED_US_REV_0.sha256,
    }
    assert receipt["episode"]["status"] == "complete"
    assert receipt["episode"]["distributed"] is False
    assert receipt["episode"]["streams"] == {
        "episode": 1,
        "events": 300,
        "executions": 41_330,
        "snapshots": 14_760,
    }
    assert receipt["episode"]["total_records"] == 56_391
    assert receipt["gameplay"] == {
        "checkpoints_verified": 299,
        "checkpoints_total": 299,
        "objectives_verified": 36,
        "objectives_total": 36,
        "frames_executed": 4_796_436,
        "actions_executed": 41_330,
        "qualified_through": "enter_hall_of_fame",
        "controller_released": True,
    }
    assert receipt["integrity_audit"]["adjacent_state_hash_transitions_verified"] == 41_329
    assert all(
        value
        for key, value in receipt["integrity_audit"].items()
        if key != "adjacent_state_hash_transitions_verified"
    )
    assert all(receipt["privacy_audit"].values())
    assert receipt["limitations"]["decision_records"] == 0

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "/Volumes/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_battle_decision_receipt_is_linked_limited_and_privacy_safe() -> None:
    receipt = json.loads(BATTLE_DECISION_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "private-battle-decision-receipt-v1"
    assert receipt["recorded_on"] == "2026-07-30"
    assert receipt["evidence_lane"] == "deterministic_teacher_adaptive_battle_decisions"
    assert receipt["claim_scope"] == {
        "game_complete": True,
        "adaptive_battle_decision_labels": True,
        "all_battle_decisions_labeled": False,
        "model_ready_dataset": False,
        "learned_policy": False,
        "transfer_result": False,
    }
    assert receipt["source"] == {
        "git_commit": "fb6a7b9ab73daf202e8ca74e5537d449ce4b466e",
        "worktree_dirty": False,
    }
    assert receipt["rom"] == {
        "title": POKEMON_RED_US_REV_0.title,
        "size_bytes": POKEMON_RED_US_REV_0.size_bytes,
        "sha1": POKEMON_RED_US_REV_0.sha1,
        "sha256": POKEMON_RED_US_REV_0.sha256,
    }
    assert receipt["episode"]["status"] == "complete"
    assert receipt["episode"]["distributed"] is False
    assert receipt["episode"]["streams"] == {
        "episode": 1,
        "decisions": 422,
        "events": 300,
        "executions": 41_330,
        "snapshots": 14_760,
    }
    assert receipt["episode"]["total_records"] == 56_813
    assert receipt["episode"]["total_bytes"] == 39_291_235
    assert receipt["gameplay"] == {
        "checkpoints_verified": 299,
        "checkpoints_total": 299,
        "objectives_verified": 36,
        "objectives_total": 36,
        "frames_executed": 4_796_436,
        "actions_executed": 41_330,
        "qualified_through": "enter_hall_of_fame",
        "controller_released": True,
    }

    decision_audit = receipt["decision_audit"]
    assert decision_audit["decision_records"] == 422
    assert decision_audit["unique_decision_snapshots"] == 421
    assert decision_audit["battle_locations_observed"] == 32
    assert decision_audit["shared_runtime_call_sites_covered"] == 22
    assert sum(decision_audit["slot_counts"].values()) == 422
    assert (
        decision_audit["linked_execution_records"]
        + decision_audit["unlinked_execution_records"]
        == 41_330
    )
    assert decision_audit["conflicting_actions_for_duplicate_snapshots"] == 0
    assert all(
        decision_audit[key]
        for key in (
            "all_decisions_have_linked_executions",
            "first_execution_step_matches_decision",
            "first_execution_snapshot_matches_decision",
            "linked_execution_spans_are_contiguous",
        )
    )

    assert receipt["integrity_audit"]["adjacent_state_hash_transitions_verified"] == 41_329
    assert all(
        value
        for key, value in receipt["integrity_audit"].items()
        if key != "adjacent_state_hash_transitions_verified"
    )
    assert all(receipt["privacy_audit"].values())
    assert receipt["limitations"]["single_nominal_teacher_episode"] is True
    assert receipt["limitations"]["adaptive_runtime_only"] is True
    assert receipt["limitations"]["custom_battle_controllers_labeled"] is False
    assert receipt["limitations"]["perturbed_examples"] == 0
    assert receipt["limitations"]["held_out_evaluation_attempts"] == 0

    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "/Volumes/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_battle_imitation_receipt_is_diagnostic_aggregate_and_privacy_safe() -> None:
    receipt = json.loads(BATTLE_IMITATION_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "battle-imitation-diagnostic-v1"
    assert receipt["recorded_on"] == "2026-07-30"
    assert receipt["evidence_lane"] == "single_lineage_grouped_battle_imitation_diagnostic"
    assert receipt["status"] == "complete"
    assert receipt["claim_scope"] == {
        "battle_imitation_model_trained": True,
        "same_lineage_grouped_diagnostic": True,
        "held_out_evaluation": False,
        "learned_policy_rollout": False,
        "learned_full_game_completion": False,
        "promotion_eligible": False,
        "transfer_result": False,
    }
    assert receipt["scope"] == {
        "decisions": 422,
        "groups": 63,
        "source_episodes": 1,
        "source_root_lineages": 1,
    }
    assert receipt["dataset_manifest_sha256"] == (
        "3ed9e3f7cfccb9dcf2e1f0c11b6a53f687854e35bf1766f66c44e8ebfe07a750"
    )
    assert receipt["model"] == {
        "model_id": "pokemon.core.battle.masked-linear-ranker.v1",
        "feature_schema_id": "pokemon.core.battle.move-ranker.v1",
        "feature_count": 100,
        "sha256": "0051da799e6d95b64bde2a3c09ed46d34b43aaf61660217c77f7fd635ddf950a",
        "serialization": "canonical_json",
    }
    assert receipt["training"] == {
        "seed": 1289,
        "folds": 5,
        "epochs": 300,
        "learning_rate": 0.03,
        "l2": 0.0001,
        "split_unit": "diagnostic_battle_group",
    }

    metrics = receipt["metrics"]
    assert metrics["accuracy"] == 0.7251184834123223
    assert metrics["macro_f1"] == 0.6830197450601863
    assert metrics["per_slot_recall"] == [
        0.8605769230769231,
        0.74,
        0.4942528735632184,
        0.6103896103896104,
    ]
    assert metrics["cross_entropy"] == 0.7131798266065661
    assert metrics["majority_accuracy"] == 0.504739336492891
    assert metrics["training_accuracy"] == 0.8056872037914692
    assert metrics["legal_choice_rate"] == 1.0
    assert metrics["accuracy"] > metrics["majority_accuracy"]
    folds = metrics["folds"]
    assert [fold["fold_index"] for fold in folds] == list(range(5))
    assert [fold["accuracy"] for fold in folds] == [
        0.6588235294117647,
        0.8117647058823529,
        0.5833333333333334,
        0.9166666666666666,
        0.6547619047619048,
    ]
    assert [fold["cross_entropy"] for fold in folds] == [
        0.7859594101860107,
        0.677667240016898,
        0.8236010302364283,
        0.3596113660777685,
        0.9186164317896561,
    ]
    assert [fold["majority_accuracy"] for fold in folds] == [
        0.5882352941176471,
        0.6235294117647059,
        0.42857142857142855,
        0.5238095238095238,
        0.35714285714285715,
    ]
    assert sum(fold["test_decisions"] for fold in folds) == 422
    assert sum(fold["test_groups"] for fold in folds) == 63

    assert receipt["qualification"] == {
        "promotion_eligible": False,
        "held_out_evaluation": False,
        "learned_policy_rollout": False,
        "reasons": [
            "grouped_cross_validation_is_not_held_out",
            "inferred_battle_groups",
            "policy_goal_not_fully_observed",
            "single_recorded_root_lineage",
            "unassigned_root_lineage",
        ],
    }
    assert receipt["source"] == {
        "git_commit": "2d8f711092d6a279a9143b6f9db41a840461a4c3",
        "worktree_dirty": False,
    }
    artifact = receipt["private_artifact"]
    assert artifact == {
        "artifact_id": "red-battle-ranker-8e12f910fad2422c8d494771740d351d",
        "kind": "battle_model",
        "status": "complete",
        "schema": "private-json-artifact-summary-v1",
        "stream_records": {"metrics": 1, "model": 1, "training": 1},
        "total_records": 3,
        "total_bytes": 8251,
        "manifest_sha256": (
            "a9173fe9aa8139584e23c8abb5d7c912d1d2c3242204a48c3d67810870d0022c"
        ),
    }

    limitations = receipt["limitations"]
    assert limitations["single_nominal_teacher_episode"] is True
    assert limitations["unassigned_root_lineage"] is True
    assert limitations["inferred_battle_groups"] is True
    assert limitations["adaptive_runtime_decisions_only"] is True
    assert limitations["all_battle_decisions_labeled"] is False
    assert limitations["policy_goal_not_fully_observed"] is True
    assert limitations["held_out_root_lineages"] == 0
    assert limitations["learned_policy_rollouts"] == 0

    serialized = json.dumps(receipt)
    for forbidden in (
        "/Users/",
        "/Volumes/",
        "Downloads",
        ".gb",
        ".jsonl",
        '"weights"',
        "candidate_vectors",
        "decision_id",
        "snapshot_sha256",
    ):
        assert forbidden not in serialized


def test_route1_acquisition_receipt_is_narrow_complete_and_privacy_safe() -> None:
    receipt = json.loads(ROUTE1_ACQUISITION_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "pokemon-red-route1-acquisition-receipt-v1"
    assert receipt["status"] == "passed"
    assert receipt["evaluation"] == {
        "clean_power_on": True,
        "human_input": False,
        "save_state_restoration": False,
        "runs": 1,
    }
    assert receipt["route_1_acquisition"] == {
        "live_emulator_execution": True,
        "species_captured_in_order": [16, 19],
        "pokedex_owned_flags_verified": [16, 19],
        "exact_pc_deposit_transitions_verified": 2,
        "current_box_tail_verified": [16, 19],
        "party_restored_to_story_roster": True,
        "vermilion_gym_route_restored": True,
    }
    assert receipt["balanced_training"] == {
        "battle_budget": 7000,
        "healing_trip_budget": 1250,
        "faints": 0,
        "minimum_level_at_gate": 77,
        "maximum_level_at_gate": 82,
        "level_spread_at_gate": 5,
    }
    assert receipt["completion"] == {
        "checkpoints_verified": 312,
        "checkpoints_total": 312,
        "objectives_verified": 36,
        "objectives_total": 36,
        "champion_defeated": True,
        "hall_of_fame_entered": True,
        "actions_executed": 758430,
    }
    assert receipt["terminal_collection"] == {
        "all_boxes_verified": True,
        "storage_initialized": True,
        "pokedex_registered_targets": 14,
        "living_targets": 9,
        "level_100_targets": 0,
        "pokedex_target_complete": False,
        "living_collection_verified": False,
        "level_100_collection_verified": False,
    }
    assert not any(receipt["privacy"].values())
    serialized = json.dumps(receipt)
    assert "/Users/" not in serialized
    assert "/Volumes/" not in serialized
    assert "Downloads" not in serialized
    assert ".gb" not in serialized


def test_viridian_forest_receipt_is_source_bound_narrow_and_privacy_safe() -> None:
    receipt = json.loads(VIRIDIAN_FOREST_RECEIPT.read_text(encoding="utf-8"))

    assert receipt["schema"] == "pokemon-red-viridian-forest-receipt-v1"
    assert receipt["status"] == "passed"
    assert receipt["source_identity"] == {
        "collection_registry_sha256": (
            "a97026d9e25edb9b0baf0b4945b0aeb10c8f7e62a4d524ab4ceafd5792ce4c4b"
        ),
        "source_bundle_sha256": (
            "2045f27313a02d9ac3e44feaff886f1020d01408bd2a17a8b6e0df173f2ae9fa"
        ),
        "teacher_execution_sha256": (
            "82895df18df8d3e38902c7d25d6e27d8a08ba202e164c7f881c8b929f5694210"
        ),
    }
    assert receipt["evaluation"] == {
        "clean_power_on": True,
        "human_input": False,
        "save_state_restoration": False,
        "adjacent_private_artifacts_unchanged": True,
        "exact_source_teacher_executions": 2,
    }
    assert receipt["viridian_forest_acquisition"] == {
        "live_emulator_execution": True,
        "reusable_semantic_source_controller": True,
        "global_pokedex_observation": True,
        "global_party_observation": True,
        "all_twelve_boxes_observed": True,
        "species_quantities": {"10": 1, "11": 2, "14": 2, "25": 1},
        "physical_specimens_retained": 6,
        "distinct_species_retained": 4,
        "exact_party_deposit_transitions_verified": 3,
        "duplicate_specimens_sent_directly_to_storage": 3,
        "forest_and_gate_warps_normalized": True,
        "story_party_restored": True,
    }
    assert receipt["completion"] == {
        "checkpoints_verified": 312,
        "checkpoints_total": 312,
        "objectives_verified": 36,
        "objectives_total": 36,
        "champion_defeated": True,
        "hall_of_fame_entered": True,
        "frames_executed": 83_619_428,
        "actions_executed": 765_088,
    }
    assert receipt["terminal_collection"] == {
        "pokedex_registered_targets": 18,
        "distinct_living_target_species": 13,
        "level_100_targets": 0,
        "physical_specimens": 15,
        "party_count": 6,
        "box_counts": [9, *(0 for _ in range(11))],
        "all_boxes_verified": True,
        "storage_initialized": True,
    }
    assert receipt["learning_boundary"] == {
        "formal_train_validation_fitter_implemented": True,
        "candidate_model_fitted": False,
        "sealed_test_partition_opened": False,
        "learned_policy_rollout_completed": False,
    }
    assert receipt["validation"]["public_tests_passed"] == 1456
    assert receipt["validation"]["private_integration_tests_passed"] == 1
    assert not any(receipt["privacy"].values())

    serialized = json.dumps(receipt)
    for forbidden in ("/Users/", "/Volumes/", "Downloads", ".gb", ".jsonl"):
        assert forbidden not in serialized
