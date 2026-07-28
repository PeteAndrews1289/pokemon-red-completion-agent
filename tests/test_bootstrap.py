from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from pokemon_red_completion.bootstrap import (
    BootstrapSmokeReport,
    is_bedroom_input_ready,
    is_clean_bedroom_start,
    play_new_game_intro,
    run_bootstrap_smoke,
)
from pokemon_red_completion.executor import ControllerTiming, FrameSafeExecutor
from pokemon_red_completion.observation import (
    REDS_HOUSE_2F_NOOP_SCRIPT,
    BedroomInputState,
    RawGameState,
)
from pokemon_red_completion.rom import RomFingerprint


class RecordingController:
    def __init__(self) -> None:
        self.frame_count = 0
        self.events: list[tuple[str, str | int]] = []

    def press(self, button: str) -> None:
        self.events.append(("press", button))

    def release(self, button: str) -> None:
        self.events.append(("release", button))

    def tick(self, frames: int) -> None:
        self.frame_count += frames
        self.events.append(("tick", frames))


def _raw(*, y: int = 6) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=0x26,
        player_x=3,
        player_y=y,
        party_count=0,
        battle_state=0,
        badge_bits=0,
        bag_item_ids=(),
        event_flags=b"",
    )


def test_new_game_sequence_has_frozen_inputs_and_timing() -> None:
    controller = RecordingController()
    executor = FrameSafeExecutor(
        controller,
        ControllerTiming(press_frames=8, release_frames=16, wait_frames=1),
    )

    play_new_game_intro(executor)

    buttons = [value for kind, value in controller.events if kind == "press"]
    assert buttons == [
        "start",
        *(["a"] * 14),
        "down",
        "a",
        *(["a"] * 5),
        "down",
        "a",
        *(["a"] * 7),
    ]
    assert controller.frame_count == 9_804


def test_bedroom_gate_requires_clean_state_and_typed_input_readiness() -> None:
    bedroom = _raw()
    ready = BedroomInputState(
        joy_ignore=0,
        map_script=REDS_HOUSE_2F_NOOP_SCRIPT,
    )

    assert is_clean_bedroom_start(bedroom)
    assert is_bedroom_input_ready(bedroom, ready)
    assert not is_clean_bedroom_start(_raw(y=7))
    assert not is_bedroom_input_ready(
        bedroom,
        BedroomInputState(joy_ignore=0, map_script=0),
    )


def test_public_report_excludes_private_filename_and_raw_buffers() -> None:
    bedroom = _raw()
    report = BootstrapSmokeReport(
        rom=RomFingerprint(
            filename="/private/path/Pokemon Red.gb",
            title="POKEMON RED",
            size_bytes=1_048_576,
            sha1="1" * 40,
            sha256="2" * 64,
        ),
        pyboy_version="2.7.0",
        clean_power_on=True,
        initial=RawGameState(False, None, None, None, None, None),
        bedroom=bedroom,
        moved=_raw(y=7),
        input_ready=True,
        movement_verified=True,
        facts=frozenset({"system:clean_power_on", "story:adventure_begun"}),
        frames_executed=9_828,
        controller_released=True,
    )

    public = report.public_dict()
    rendered = str(public)

    assert report.passed
    assert public["status"] == "ok"
    assert public["bedroom"] == {
        "mode": "overworld",
        "map_id": 0x26,
        "location": "reds_house_2f",
        "player_x": 3,
        "player_y": 6,
        "party_count": 0,
        "battle_state": 0,
    }
    assert "Pokemon Red.gb" not in rendered
    assert "/private/path" not in rendered
    assert "event_flags" not in rendered


def _adjacent_artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.integration
def test_private_rom_reaches_bedroom_without_adjacent_artifacts() -> None:
    raw_path = os.environ.get("POKEMON_RED_ROM")
    if not raw_path:
        pytest.skip("Set POKEMON_RED_ROM to run the private integration test")

    rom_path = Path(raw_path).expanduser().resolve()
    adjacent = tuple(Path(f"{rom_path}{suffix}") for suffix in (".ram", ".rtc", ".state"))
    before = tuple(_adjacent_artifact_identity(path) for path in adjacent)

    report = run_bootstrap_smoke(rom_path)

    after = tuple(_adjacent_artifact_identity(path) for path in adjacent)
    assert report.passed
    assert report.bedroom.player_y == 6
    assert report.moved.player_y == 7
    assert report.frames_executed == 9_828
    assert before == after
