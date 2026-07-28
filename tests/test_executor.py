from __future__ import annotations

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import (
    ControllerTiming,
    FrameSafeExecutor,
    UnsupportedMacroActionError,
)


class RecordingController:
    def __init__(self, fail_tick: bool = False) -> None:
        self.events: list[tuple[str, str | int]] = []
        self.fail_tick = fail_tick

    def press(self, button: str) -> None:
        self.events.append(("press", button))

    def release(self, button: str) -> None:
        self.events.append(("release", button))

    def tick(self, frames: int) -> None:
        self.events.append(("tick", frames))
        if self.fail_tick:
            raise RuntimeError("emulator failed")


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
