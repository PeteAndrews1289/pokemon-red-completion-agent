from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import (
    ControllerFrameBudgetError,
    ControllerInputForbiddenError,
    ControllerTiming,
    FrameBudgetController,
    FrameSafeExecutor,
    ReadOnlyController,
    UnsupportedMacroActionError,
)
from pokemon_red_completion.observation import ReadOnlyCartridgeRam


class RecordingController:
    def __init__(self, fail_tick: bool = False) -> None:
        self.events: list[tuple[str, str | int]] = []
        self.fail_tick = fail_tick
        self.frame_count = 0
        self.marker = "coherent-reader-state"

    def press(self, button: str) -> None:
        self.events.append(("press", button))

    def release(self, button: str) -> None:
        self.events.append(("release", button))

    def tick(self, frames: int) -> None:
        self.events.append(("tick", frames))
        if self.fail_tick:
            raise RuntimeError("emulator failed")
        self.frame_count += frames

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        self.events.append(("cartridge_read", bank * 0x10000 + address))
        return 0xA5


def test_executor_applies_declared_press_and_release_timing() -> None:
    controller = RecordingController()
    executor = FrameSafeExecutor(
        controller,
        ControllerTiming(press_frames=2, release_frames=3),
    )

    result = executor.execute(MacroAction(MacroActionKind.MOVE, "right", repeat=2))

    assert result.buttons == ("right", "right")
    assert result.frames == 10
    assert controller.events == [
        ("press", "right"),
        ("tick", 2),
        ("release", "right"),
        ("tick", 3),
        ("press", "right"),
        ("tick", 2),
        ("release", "right"),
        ("tick", 3),
    ]


def test_executor_releases_button_when_emulator_tick_fails() -> None:
    controller = RecordingController(fail_tick=True)

    with pytest.raises(RuntimeError, match="emulator failed"):
        FrameSafeExecutor(controller).execute(MacroAction(MacroActionKind.CONFIRM))

    assert controller.events[-1] == ("release", "a")


def test_wait_ticks_without_pressing_and_unqualified_macros_fail_closed() -> None:
    controller = RecordingController()
    executor = FrameSafeExecutor(controller, ControllerTiming(wait_frames=4))

    result = executor.execute(MacroAction(MacroActionKind.WAIT, repeat=3))

    assert result.frames == 12
    assert controller.events == [("tick", 12)]

    with pytest.raises(UnsupportedMacroActionError, match="qualified specialist"):
        executor.execute(MacroAction(MacroActionKind.BATTLE_MOVE, 1))


def test_invalid_direction_is_rejected_before_controller_input() -> None:
    controller = RecordingController()

    with pytest.raises(UnsupportedMacroActionError, match="invalid movement"):
        FrameSafeExecutor(controller).execute(MacroAction(MacroActionKind.MOVE, "north"))

    assert controller.events == []


def test_frame_budget_controller_refuses_before_overrun_and_delegates_reads() -> None:
    controller = RecordingController()
    bounded = FrameBudgetController(controller, maximum_frames=5)

    bounded.tick(3)

    assert bounded.frames_executed == 3
    assert bounded.marker == "coherent-reader-state"
    with pytest.raises(ControllerFrameBudgetError, match="frame budget"):
        bounded.tick(3)
    assert controller.events == [("tick", 3)]


def test_read_only_controller_exposes_bounded_cartridge_reads_but_no_time() -> None:
    controller = RecordingController()
    read_only = ReadOnlyController(controller)

    assert isinstance(read_only, ReadOnlyCartridgeRam)
    assert read_only.read_cartridge_ram_u8(2, 0xA123) == 0xA5
    with pytest.raises(ControllerInputForbiddenError, match="frames are forbidden"):
        read_only.tick(1)
    assert controller.events == [("cartridge_read", 0x2A123)]


def test_only_emulator_and_executor_modules_call_controller_primitives() -> None:
    package = Path(__file__).resolve().parents[1] / "src" / "pokemon_red_completion"
    allowed = {"emulator.py", "executor.py"}
    violations: list[str] = []

    for source_path in sorted(package.glob("*.py")):
        if source_path.name in allowed:
            continue
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"press", "release", "tick"}
            ):
                violations.append(f"{source_path.name}:{node.lineno}:{node.func.attr}")

    assert violations == []
