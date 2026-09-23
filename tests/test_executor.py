from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import (
    ControllerActionBudgetExhausted,
    ControllerActionLimiter,
    ControllerFrameBudgetError,
    ControllerFrameBudgetExhausted,
    ControllerInputForbiddenError,
    ControllerTiming,
    ControllerWallTimeBudgetExhausted,
    FrameBudgetController,
    FrameSafeExecutor,
    MonotonicWallTimeBudgetController,
    ReadOnlyController,
    UnsupportedMacroActionError,
    WindowedFrameBudgetController,
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


def test_nested_frame_deadlines_do_not_reset_or_widen_outer_limits():
    raw = RecordingController()
    controller = WindowedFrameBudgetController(
        raw, maximum_frames_per_window=100, maximum_total_frames=100,
    )
    controller.tick(7)
    with controller.limit_additional_frames(5):
        controller.tick(3)
        controller.begin_window()
        with controller.limit_additional_frames(50):
            controller.tick(2)
            with pytest.raises(ControllerFrameBudgetExhausted):
                controller.tick(1)
        assert raw.frame_count == 12
    controller.tick(1)
    assert raw.frame_count == 13
    assert controller.frames_executed == 13


def test_nested_frame_deadline_restores_scope_after_exception_without_refund():
    raw = RecordingController()
    controller = WindowedFrameBudgetController(
        raw, maximum_frames_per_window=6, maximum_total_frames=6,
    )
    with pytest.raises(RuntimeError, match="capture failed"), controller.limit_additional_frames(2):
        controller.tick(2)
        raise RuntimeError("capture failed")
    controller.tick(4)
    with pytest.raises(ControllerFrameBudgetExhausted), controller.limit_additional_frames(100):
        controller.tick(1)
    assert raw.frame_count == 6


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_nested_frame_deadline_rejects_invalid_limits(limit):
    raw = RecordingController()
    controller = WindowedFrameBudgetController(
        raw, maximum_frames_per_window=10, maximum_total_frames=10,
    )
    with pytest.raises(ValueError), controller.limit_additional_frames(limit):
        pytest.fail("invalid scope entered")
    assert raw.frame_count == 0


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


def test_controller_action_limiter_reserves_attempt_before_delegate() -> None:
    controller = RecordingController(fail_tick=True)
    limited = ControllerActionLimiter(FrameSafeExecutor(controller), maximum_actions=1)

    with pytest.raises(RuntimeError, match="emulator failed"):
        limited.execute(MacroAction(MacroActionKind.CONFIRM))
    with pytest.raises(ControllerActionBudgetExhausted):
        limited.execute(MacroAction(MacroActionKind.CONFIRM))

    assert limited.attempted_actions == 1
    assert limited.completed_actions == 0
    assert controller.events == [("press", "a"), ("tick", 1), ("release", "a")]


def test_controller_action_limiter_allows_n_and_blocks_n_plus_one() -> None:
    controller = RecordingController()
    limited = ControllerActionLimiter(FrameSafeExecutor(controller), maximum_actions=1)

    limited.execute(MacroAction(MacroActionKind.WAIT))
    with pytest.raises(ControllerActionBudgetExhausted):
        limited.execute(MacroAction(MacroActionKind.WAIT))

    assert limited.attempted_actions == limited.completed_actions == 1
    assert controller.events == [("tick", 1)]


def test_monotonic_deadline_between_press_and_tick_releases_without_tick() -> None:
    readings = iter((10.0, 14.999, 15.0, 16.0))
    controller = RecordingController()
    bounded = MonotonicWallTimeBudgetController(
        controller,
        maximum_wall_seconds=5,
        monotonic_clock=lambda: next(readings),
    )

    with pytest.raises(ControllerWallTimeBudgetExhausted) as caught:
        FrameSafeExecutor(bounded).execute(MacroAction(MacroActionKind.CONFIRM))

    assert caught.value.maximum_wall_seconds == 5
    assert caught.value.elapsed_seconds == 5.0
    assert controller.events == [("press", "a"), ("release", "a")]
    assert bounded.elapsed_seconds == 6.0


def test_monotonic_deadline_allows_before_and_rejects_at_deadline() -> None:
    readings = iter((100.0, 104.999, 105.0, 106.0))
    bounded = MonotonicWallTimeBudgetController(
        RecordingController(),
        maximum_wall_seconds=5,
        monotonic_clock=lambda: next(readings),
    )

    bounded.check_wall_time_budget()
    with pytest.raises(ControllerWallTimeBudgetExhausted) as caught:
        bounded.check_wall_time_budget()

    assert caught.value.elapsed_seconds == 5.0
    assert bounded.elapsed_seconds == 6.0


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
    assert isinstance(bounded, ReadOnlyCartridgeRam)
    assert bounded.read_cartridge_ram_u8(2, 0xA123) == 0xA5
    with pytest.raises(ControllerFrameBudgetError, match="frame budget"):
        bounded.tick(3)
    assert controller.events == [("tick", 3), ("cartridge_read", 0x2A123)]


def test_windowed_frame_budget_preserves_cartridge_reads_and_both_caps() -> None:
    controller = RecordingController()
    bounded = WindowedFrameBudgetController(
        controller,
        maximum_frames_per_window=4,
        maximum_total_frames=6,
    )

    assert isinstance(bounded, ReadOnlyCartridgeRam)
    assert bounded.read_cartridge_ram_u8(2, 0xA123) == 0xA5
    bounded.tick(4)
    with pytest.raises(ControllerFrameBudgetExhausted, match="windowed frame budget"):
        bounded.tick(1)
    bounded.begin_window()
    bounded.tick(2)
    with pytest.raises(ControllerFrameBudgetExhausted, match="windowed frame budget"):
        bounded.tick(1)

    assert bounded.frames_executed == 6
    assert controller.events == [
        ("cartridge_read", 0x2A123),
        ("tick", 4),
        ("tick", 2),
    ]


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
