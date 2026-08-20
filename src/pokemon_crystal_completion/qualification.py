"""Bounded clean-power qualification for Crystal's semantic observation path.

The setup transcript exists only to initialize a lawful fresh cartridge for
adapter qualification.  It never opens an experiment context, asks the
teacher, computes a prediction, or becomes an imitation target.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from pokemon_crystal_completion.observation import (
    CrystalObservationBundle,
    CrystalStorageMemoryReader,
)
from pokemon_crystal_completion.source_contract import CRYSTAL_OBSERVATION_SYMBOLS
from pokemon_red_completion.provenance import canonical_sha256

CRYSTAL_STARTING_MAP_GROUP = 24
CRYSTAL_STARTING_MAP_NUMBER = 7
CRYSTAL_STARTING_X = 3
CRYSTAL_STARTING_Y = 3
CRYSTAL_MAP_STATUS_HANDLE = 2
CRYSTAL_MAP_EVENTS_ON = 0
CRYSTAL_SCRIPT_OFF = 0
CRYSTAL_PLAYER_NORMAL = 0
CRYSTAL_BATTLE_MODE_NONE = 0
CRYSTAL_BUTTON_HOLD_FRAMES = 6
CRYSTAL_BOOT_FRAMES = 4_200
CRYSTAL_POST_SAVE_STABILITY_FRAMES = 600
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CrystalQualificationError(RuntimeError):
    """Raised when live qualification cannot prove every declared boundary."""


@dataclass(frozen=True, slots=True)
class CrystalQualificationStep:
    button: str
    repetitions: int
    settle_frames: int

    def __post_init__(self) -> None:
        if not isinstance(self.button, str) or self.button not in {
            "a",
            "b",
            "start",
            "select",
            "up",
            "right",
            "down",
            "left",
        }:
            raise CrystalQualificationError("Crystal qualification button is invalid")
        if type(self.repetitions) is not int or self.repetitions < 1:  # noqa: E721
            raise CrystalQualificationError("Crystal qualification repetitions are invalid")
        if type(self.settle_frames) is not int or self.settle_frames < 1:  # noqa: E721
            raise CrystalQualificationError("Crystal qualification wait is invalid")

    def public_dict(self) -> dict[str, object]:
        return {
            "button": self.button,
            "repetitions": self.repetitions,
            "settle_frames": self.settle_frames,
        }


CRYSTAL_NEW_GAME_QUALIFICATION_TRANSCRIPT = (
    CrystalQualificationStep("start", 1, 600),
    CrystalQualificationStep("a", 1, 600),
    CrystalQualificationStep("a", 1, 600),
    CrystalQualificationStep("a", 9, 600),
    CrystalQualificationStep("a", 15, 600),
    CrystalQualificationStep("a", 1, 1_200),
    CrystalQualificationStep("down", 1, 300),
    CrystalQualificationStep("a", 1, 1_200),
    CrystalQualificationStep("a", 10, 600),
)
CRYSTAL_IN_GAME_SAVE_QUALIFICATION_TRANSCRIPT = (
    CrystalQualificationStep("start", 1, 600),
    CrystalQualificationStep("down", 1, 300),
    CrystalQualificationStep("down", 1, 300),
    CrystalQualificationStep("a", 1, 600),
    CrystalQualificationStep("up", 1, 300),
    CrystalQualificationStep("a", 1, 1_200),
)


class CrystalQualificationController(CrystalStorageMemoryReader, Protocol):
    @property
    def frame_count(self) -> int: ...

    @property
    def pressed_buttons(self) -> frozenset[str]: ...

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def tick(self, frames: int) -> None: ...


@dataclass(frozen=True, slots=True)
class CrystalQualificationRuntimeState:
    johto_badges: int
    kanto_badges: int
    battle_mode: int
    map_status: int
    map_event_status: int
    script_mode: int
    script_running: int
    joypad_disable: int
    player_state: int
    map_group: int
    map_number: int
    x: int
    y: int

    def __post_init__(self) -> None:
        for name in (
            "johto_badges",
            "kanto_badges",
            "battle_mode",
            "map_status",
            "map_event_status",
            "script_mode",
            "script_running",
            "joypad_disable",
            "player_state",
            "map_group",
            "map_number",
            "x",
            "y",
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 0xFF:  # noqa: E721
                raise CrystalQualificationError(f"Crystal {name} byte is invalid")
        if self.map_status > 3 or self.map_event_status > 1 or self.script_mode > 3:
            raise CrystalQualificationError("Crystal runtime enum is invalid")
        if self.player_state not in {0, 1, 2, 4, 8}:
            raise CrystalQualificationError("Crystal player state is invalid")

    @property
    def badge_count(self) -> int:
        return self.johto_badges.bit_count() + self.kanto_badges.bit_count()

    @property
    def at_starting_bedroom(self) -> bool:
        return (
            self.map_group == CRYSTAL_STARTING_MAP_GROUP
            and self.map_number == CRYSTAL_STARTING_MAP_NUMBER
            and self.x == CRYSTAL_STARTING_X
            and self.y == CRYSTAL_STARTING_Y
        )

    @property
    def input_ready(self) -> bool:
        return (
            self.battle_mode == CRYSTAL_BATTLE_MODE_NONE
            and self.map_status == CRYSTAL_MAP_STATUS_HANDLE
            and self.map_event_status == CRYSTAL_MAP_EVENTS_ON
            and self.script_mode == CRYSTAL_SCRIPT_OFF
            and self.script_running == 0
            and self.joypad_disable == 0
            and self.player_state == CRYSTAL_PLAYER_NORMAL
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "badge_count": self.badge_count,
            "at_expected_start_location": self.at_starting_bedroom,
            "input_ready": self.input_ready,
            "private_location_identity_fields": 0,
            "raw_address_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class CrystalBankedObservationQualification:
    source_commit: str
    plan_sha256: str
    rom_sha1: str
    rom_sha256: str
    transcript_sha256: str
    actions: int
    frames: int
    runtime: CrystalQualificationRuntimeState
    observation: CrystalObservationBundle
    pre_save_storage_rejected: bool
    post_save_observations_identical: bool
    controller_released: bool
    rom_unchanged: bool

    def __post_init__(self) -> None:
        if _GIT_COMMIT.fullmatch(self.source_commit) is None:
            raise CrystalQualificationError("Crystal qualification source commit is invalid")
        for name in ("plan_sha256", "rom_sha256", "transcript_sha256"):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise CrystalQualificationError(f"Crystal qualification {name} is invalid")
        if not isinstance(self.rom_sha1, str) or _SHA1.fullmatch(self.rom_sha1) is None:
            raise CrystalQualificationError("Crystal qualification ROM SHA-1 is invalid")
        if type(self.actions) is not int or self.actions < 1:  # noqa: E721
            raise CrystalQualificationError("Crystal qualification action count is invalid")
        if type(self.frames) is not int or self.frames < 1:  # noqa: E721
            raise CrystalQualificationError("Crystal qualification frame count is invalid")
        if not isinstance(self.runtime, CrystalQualificationRuntimeState):
            raise TypeError("runtime must be CrystalQualificationRuntimeState")
        if not isinstance(self.observation, CrystalObservationBundle):
            raise TypeError("observation must be CrystalObservationBundle")
        if not all(
            (
                self.runtime.at_starting_bedroom,
                self.runtime.input_ready,
                self.pre_save_storage_rejected,
                self.post_save_observations_identical,
                self.controller_released,
                self.rom_unchanged,
            )
        ):
            raise CrystalQualificationError("Crystal banked observation did not qualify")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.crystal.banked-observation-qualification.v1",
            "status": "passed",
            "source_commit": self.source_commit,
            "plan_sha256": self.plan_sha256,
            "rom": {"sha1": self.rom_sha1, "sha256": self.rom_sha256},
            "setup": {
                "clean_power": True,
                "transcript_sha256": self.transcript_sha256,
                "actions": self.actions,
                "frames": self.frames,
                "actual_in_game_save": True,
            },
            "runtime": self.runtime.public_dict(),
            "observation": self.observation.public_dict(),
            "checks": {
                "pre_save_uninitialized_storage_rejected": self.pre_save_storage_rejected,
                "post_save_observations_identical": self.post_save_observations_identical,
                "controller_released": self.controller_released,
                "rom_unchanged": self.rom_unchanged,
            },
            "experiment": {
                "context_opened": False,
                "teacher_executed": False,
                "prediction_computed": False,
                "zero_shot_opened": 0,
                "adaptation_opened": 0,
                "sealed_test_opened": 0,
            },
            "qualification_only_transcript": True,
            "imitation_target_created": False,
            "private_path_fields": 0,
            "raw_address_fields": 0,
        }


def qualification_transcript_sha256() -> str:
    return canonical_sha256(
        {
            "boot_frames": CRYSTAL_BOOT_FRAMES,
            "new_game": [
                step.public_dict() for step in CRYSTAL_NEW_GAME_QUALIFICATION_TRANSCRIPT
            ],
            "in_game_save": [
                step.public_dict() for step in CRYSTAL_IN_GAME_SAVE_QUALIFICATION_TRANSCRIPT
            ],
            "post_save_stability_frames": CRYSTAL_POST_SAVE_STABILITY_FRAMES,
        }
    )


def execute_crystal_qualification_steps(
    emulator: CrystalQualificationController,
    steps: tuple[CrystalQualificationStep, ...],
) -> int:
    if emulator.pressed_buttons:
        raise CrystalQualificationError("Crystal controller was not released before setup")
    actions = 0
    for step in steps:
        if not isinstance(step, CrystalQualificationStep):
            raise TypeError("steps must contain CrystalQualificationStep entries")
        for _ in range(step.repetitions):
            emulator.press(step.button)
            try:
                emulator.tick(CRYSTAL_BUTTON_HOLD_FRAMES)
            finally:
                emulator.release(step.button)
            emulator.tick(step.settle_frames)
            actions += 1
    if emulator.pressed_buttons:
        raise CrystalQualificationError("Crystal controller remained pressed after setup")
    return actions


def read_crystal_qualification_runtime(
    memory: CrystalStorageMemoryReader,
    *,
    maximum_attempts: int = 3,
) -> CrystalQualificationRuntimeState:
    if type(maximum_attempts) is not int or maximum_attempts < 1:  # noqa: E721
        raise CrystalQualificationError("Crystal runtime read needs a positive attempt bound")
    last_error: CrystalQualificationError | None = None
    for _ in range(maximum_attempts):
        try:
            before = _read_runtime_bytes(memory)
            after = _read_runtime_bytes(memory)
        except CrystalQualificationError as error:
            last_error = error
            continue
        if before != after:
            last_error = CrystalQualificationError(
                "Crystal runtime changed during qualification observation"
            )
            continue
        try:
            return CrystalQualificationRuntimeState(*before)
        except CrystalQualificationError as error:
            last_error = error
    raise last_error or CrystalQualificationError("Crystal runtime observation failed")


def _read_runtime_bytes(memory: CrystalStorageMemoryReader) -> tuple[int, ...]:
    names = (
        "wJohtoBadges",
        "wKantoBadges",
        "wBattleMode",
        "wMapStatus",
        "wMapEventStatus",
        "wScriptMode",
        "wScriptRunning",
        "wJoypadDisable",
        "wPlayerState",
        "wMapGroup",
        "wMapNumber",
        "wXCoord",
        "wYCoord",
    )
    values: list[int] = []
    for name in names:
        symbol = CRYSTAL_OBSERVATION_SYMBOLS[name]
        try:
            payload = memory.read_wram(symbol.bank, symbol.address, 1)
        except Exception as error:
            raise CrystalQualificationError("Crystal runtime WRAM read failed") from error
        if not isinstance(payload, bytes) or len(payload) != 1:
            raise CrystalQualificationError("Crystal runtime WRAM read is malformed")
        values.append(payload[0])
    return tuple(values)


__all__ = [
    "CRYSTAL_BOOT_FRAMES",
    "CRYSTAL_IN_GAME_SAVE_QUALIFICATION_TRANSCRIPT",
    "CRYSTAL_NEW_GAME_QUALIFICATION_TRANSCRIPT",
    "CRYSTAL_POST_SAVE_STABILITY_FRAMES",
    "CrystalBankedObservationQualification",
    "CrystalQualificationController",
    "CrystalQualificationError",
    "CrystalQualificationRuntimeState",
    "CrystalQualificationStep",
    "execute_crystal_qualification_steps",
    "qualification_transcript_sha256",
    "read_crystal_qualification_runtime",
]
