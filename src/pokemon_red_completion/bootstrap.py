"""Verified clean-power-on bootstrap for the supported Pokémon Red revision.

The frozen input sequence is adapted from Peter Andrews Jr.'s concluded
``pokemon-red-ai`` project at commit
``0e2df37720eec7d148187eb1001bf2d9502aa4f6``. The successor executes it
through the stricter no-save adapter and sole frame-safe controller authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import ControllerTiming, FrameSafeExecutor
from pokemon_red_completion.observation import (
    BedroomInputState,
    MapId,
    PokemonRedStateReader,
    RawGameState,
    SemanticStateTracker,
    game_mode,
    location_label,
)
from pokemon_red_completion.rom import RomFingerprint

BEDROOM_START_Y = 6
BEDROOM_START_X = 3


class BootstrapError(RuntimeError):
    """Raised when the clean-start bootstrap misses a verified gate."""


@dataclass(frozen=True, slots=True)
class NewGameTiming:
    boot_frames: int = 1_800
    normal_wait_frames: int = 240
    menu_move_wait_frames: int = 120
    final_wait_frames: int = 300
    press_frames: int = 8
    release_frames: int = 16

    def __post_init__(self) -> None:
        for name, value in (
            ("boot_frames", self.boot_frames),
            ("normal_wait_frames", self.normal_wait_frames),
            ("menu_move_wait_frames", self.menu_move_wait_frames),
            ("final_wait_frames", self.final_wait_frames),
            ("press_frames", self.press_frames),
            ("release_frames", self.release_frames),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    def controller_timing(self) -> ControllerTiming:
        return ControllerTiming(
            press_frames=self.press_frames,
            release_frames=self.release_frames,
            wait_frames=1,
        )


DEFAULT_NEW_GAME_TIMING = NewGameTiming()


@dataclass(frozen=True, slots=True)
class BootstrapSmokeReport:
    rom: RomFingerprint
    pyboy_version: str
    clean_power_on: bool
    initial: RawGameState
    bedroom: RawGameState
    moved: RawGameState
    input_ready: bool
    movement_verified: bool
    facts: frozenset[str]
    frames_executed: int
    controller_released: bool

    @property
    def passed(self) -> bool:
        return (
            self.clean_power_on
            and is_clean_bedroom_start(self.bedroom)
            and self.input_ready
            and self.movement_verified
            and self.controller_released
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "bootstrap-smoke-v1",
            "status": "ok" if self.passed else "failed",
            "rom": self.rom.public_dict(),
            "emulator": {
                "name": "PyBoy",
                "version": self.pyboy_version,
                "window": "null",
                "human_input": False,
                "save_on_exit": False,
            },
            "clean_power_on": self.clean_power_on,
            "initial_mode": game_mode(self.initial).value,
            "bedroom": _public_state(self.bedroom),
            "input_ready": self.input_ready,
            "movement": {
                "verified": self.movement_verified,
                "from_y": self.bedroom.player_y,
                "to_y": self.moved.player_y,
            },
            "facts": sorted(self.facts),
            "frames_executed": self.frames_executed,
            "controller_released": self.controller_released,
        }


def is_clean_bedroom_start(state: RawGameState) -> bool:
    return (
        state.game_started
        and state.map_id == MapId.REDS_HOUSE_2F
        and state.player_y == BEDROOM_START_Y
        and state.player_x == BEDROOM_START_X
        and state.party_count == 0
        and state.battle_state == 0
    )


def is_bedroom_input_ready(
    state: RawGameState,
    input_state: BedroomInputState,
) -> bool:
    return is_clean_bedroom_start(state) and input_state.ready


def play_new_game_intro(
    executor: FrameSafeExecutor,
    *,
    timing: NewGameTiming = DEFAULT_NEW_GAME_TIMING,
) -> None:
    """Reach the bedroom from clean power-on using the built-in RED/BLUE names."""
    _wait(executor, timing.boot_frames)
    _act_and_wait(
        executor,
        MacroAction(MacroActionKind.OPEN_MENU),
        timing.normal_wait_frames,
    )

    for _ in range(14):
        _act_and_wait(
            executor,
            MacroAction(MacroActionKind.CONFIRM),
            timing.normal_wait_frames,
        )

    _act_and_wait(
        executor,
        MacroAction(MacroActionKind.MOVE, "down"),
        timing.menu_move_wait_frames,
    )
    _act_and_wait(
        executor,
        MacroAction(MacroActionKind.CONFIRM),
        timing.normal_wait_frames,
    )

    for _ in range(5):
        _act_and_wait(
            executor,
            MacroAction(MacroActionKind.CONFIRM),
            timing.normal_wait_frames,
        )

    _act_and_wait(
        executor,
        MacroAction(MacroActionKind.MOVE, "down"),
        timing.menu_move_wait_frames,
    )
    _act_and_wait(
        executor,
        MacroAction(MacroActionKind.CONFIRM),
        timing.normal_wait_frames,
    )

    for _ in range(6):
        _act_and_wait(
            executor,
            MacroAction(MacroActionKind.CONFIRM),
            timing.normal_wait_frames,
        )
    _act_and_wait(
        executor,
        MacroAction(MacroActionKind.CONFIRM),
        timing.final_wait_frames,
    )


def run_bootstrap_smoke(
    rom_path: str | Path,
    *,
    timing: NewGameTiming = DEFAULT_NEW_GAME_TIMING,
) -> BootstrapSmokeReport:
    with PyBoyAdapter(rom_path) as emulator:
        reader = PokemonRedStateReader(emulator)
        initial = reader.read()
        tracker = SemanticStateTracker(initial)
        executor = FrameSafeExecutor(emulator, timing.controller_timing())

        play_new_game_intro(executor, timing=timing)
        bedroom = reader.read()
        state = tracker.observe(bedroom)
        bedroom_input = reader.read_bedroom_input_state()
        input_ready = is_bedroom_input_ready(bedroom, bedroom_input)
        if not is_clean_bedroom_start(bedroom) or not input_ready:
            raise BootstrapError(
                "Clean-start bootstrap did not reach the verified input-ready bedroom gate."
            )

        executor.execute(MacroAction(MacroActionKind.MOVE, "down"))
        moved = reader.read()
        movement_verified = (
            moved.map_id == bedroom.map_id
            and bedroom.player_y is not None
            and moved.player_y == bedroom.player_y + 1
            and moved.player_x == bedroom.player_x
        )
        if not movement_verified:
            raise BootstrapError(
                "The agent reached the bedroom but failed its one-tile controller probe."
            )

        report = BootstrapSmokeReport(
            rom=emulator.fingerprint,
            pyboy_version=emulator.pyboy_version,
            clean_power_on="system:clean_power_on" in state.facts,
            initial=initial,
            bedroom=bedroom,
            moved=moved,
            input_ready=input_ready,
            movement_verified=movement_verified,
            facts=state.facts,
            frames_executed=emulator.frame_count,
            controller_released=not emulator.pressed_buttons,
        )
        if not report.passed:
            raise BootstrapError("Bootstrap evidence failed its public report contract.")
        return report


def _act_and_wait(
    executor: FrameSafeExecutor,
    action: MacroAction,
    wait_frames: int,
) -> None:
    executor.execute(action)
    _wait(executor, wait_frames)


def _wait(executor: FrameSafeExecutor, frames: int) -> None:
    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=frames))


def _public_state(state: RawGameState) -> dict[str, object]:
    return {
        "mode": game_mode(state).value,
        "map_id": state.map_id,
        "location": location_label(state.map_id),
        "player_x": state.player_x,
        "player_y": state.player_y,
        "party_count": state.party_count,
        "battle_state": state.battle_state,
    }
