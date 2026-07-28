from __future__ import annotations

import json
import re
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.provenance import GIT_COMMIT, canonical_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUALIFIED_SOURCE_COMMIT = "0fb14ac7f287e92fe270b3811f1ef495cbc36194"
BOOTSTRAP_RECEIPT = PROJECT_ROOT / "docs" / "evidence" / "bootstrap-smoke-2026-07-28.json"


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
