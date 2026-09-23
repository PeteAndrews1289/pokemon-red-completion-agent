from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from math import isfinite
from time import monotonic
from typing import Any, Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.emulator import CausallyMeteredEmulator


class ControllerPort(Protocol):
    """Minimal emulator-control authority owned exclusively by the executor."""

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def tick(self, frames: int) -> None: ...


class BorrowedLiveController:
    """Forward controls without giving a nested skill reset or close authority."""

    def __init__(self, session: Any, *, error_type: type[Exception] = RuntimeError) -> None:
        self.session = session
        self.error_type = error_type
        self.initialized = False

    def load_state_bytes(self, payload: bytes) -> None:
        if self.initialized or self.session.save_state_bytes() != payload:
            raise self.error_type("live trainer state differs or reset attempted")
        self.initialized = True

    @property
    def frame_count(self) -> int:
        return self.session.frame_count

    def press(self, button: str) -> None:
        self.session.press(button)

    def release(self, button: str) -> None:
        self.session.release(button)

    def tick(self, frames: int) -> None:
        self.session.tick(frames)

    def read_u8(self, address: int) -> int:
        return self.session.read_u8(address)


class JournaledController(CausallyMeteredEmulator):
    """Keep primitive control here while a caller owns durable costs.

    Cleanup releases remain possible after journal failure. Tick callbacks
    distinguish partial errors from silent short ticks.
    """

    def __init__(
        self,
        session: Any,
        *,
        admit_input: Callable[[], None],
        admit_frames: Callable[[int], None],
        record_frames: Callable[[int], None],
        tick_failed: Callable[[], None],
        tick_completed: Callable[[int], None],
    ) -> None:
        super().__init__(session, admit_frames=admit_frames, record_frames=record_frames)
        self._admit_input = admit_input
        self._tick_failed = tick_failed
        self._tick_completed = tick_completed

    def press(self, button: str) -> None:
        self._admit_input()
        super().press(button)

    def tick(self, frames: int) -> None:
        try:
            super().tick(frames)
        except BaseException:
            self._tick_failed()
            raise
        self._tick_completed(frames)


class UnsupportedMacroActionError(ValueError):
    """Raised when a specialist requests an action without a qualified compiler."""


class ControllerFrameBudgetError(RuntimeError):
    """Raised before controller time can exceed a declared frame budget."""


class ControllerActionBudgetExhausted(RuntimeError):
    """Raised before a macro dispatch can exceed its declared action budget."""

    def __init__(self, *, maximum_actions: int, attempted_actions: int) -> None:
        self.maximum_actions = maximum_actions
        self.attempted_actions = attempted_actions
        super().__init__("controller exhausted its hard macro-action budget")


class ControllerWallTimeBudgetExhausted(RuntimeError):
    """Raised when cooperative admission reaches a monotonic elapsed-time limit."""

    def __init__(self, *, maximum_wall_seconds: int, elapsed_seconds: float) -> None:
        self.maximum_wall_seconds = maximum_wall_seconds
        self.elapsed_seconds = elapsed_seconds
        super().__init__("controller reached its hard monotonic wall-time admission deadline")


class GoalExecutionBudgetExhausted(RuntimeError):
    """Marker for an expected hard goal-execution budget terminal."""


class ControllerFrameBudgetExhausted(
    ControllerFrameBudgetError,
    GoalExecutionBudgetExhausted,
):
    """Raised before a goal's resettable or total frame window is exceeded."""


class ControllerInputForbiddenError(RuntimeError):
    """Raised before a read-only controller boundary can send any input or tick."""


class ReadOnlyController:
    """Expose read-only emulator state while refusing every controller primitive."""

    __slots__ = ("_delegate",)

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate

    def press(self, _button: str) -> None:
        raise ControllerInputForbiddenError("controller input is forbidden")

    def release(self, _button: str) -> None:
        raise ControllerInputForbiddenError("controller input is forbidden")

    def tick(self, _frames: int) -> None:
        raise ControllerInputForbiddenError("controller frames are forbidden")

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        """Expose the narrow banked-RAM read needed by complete collection state."""

        reader = getattr(self._delegate, "read_cartridge_ram_u8", None)
        if not callable(reader):
            raise TypeError("read-only controller lacks cartridge-RAM access")
        value = reader(bank, address)
        if type(value) is not int or not 0 <= value <= 0xFF:  # noqa: E721
            raise TypeError("cartridge-RAM reader returned an invalid byte")
        return value

    def __getattr__(self, name: str) -> Any:
        if name == "release_restored_inputs":
            raise RuntimeError("read-only controller forbids restored-input release")
        return getattr(self._delegate, name)


class FrameBudgetController:
    """Transparent controller proxy that refuses the first over-budget tick.

    Timing authority remains inside the executor layer even when a chapter
    needs a campaign-specific hard frame ceiling.  Read-only emulator
    attributes continue through the proxy so observation adapters can share
    the same coherent state.
    """

    __slots__ = (
        "_delegate",
        "_error_message",
        "_error_type",
        "_maximum_frames",
        "_start_frame",
    )

    def __init__(
        self,
        delegate: ControllerPort,
        *,
        maximum_frames: int,
        error_type: type[RuntimeError] = ControllerFrameBudgetError,
        error_message: str = "controller exhausted its hard frame budget",
    ) -> None:
        if type(maximum_frames) is not int or maximum_frames <= 0:  # noqa: E721
            raise ValueError("maximum_frames must be a positive integer")
        if not isinstance(error_type, type) or not issubclass(error_type, RuntimeError):
            raise TypeError("error_type must be a RuntimeError class")
        if not isinstance(error_message, str) or not error_message:
            raise ValueError("error_message must be non-empty")
        frame_count = getattr(delegate, "frame_count", None)
        if type(frame_count) is not int or frame_count < 0:  # noqa: E721
            raise TypeError("frame-budget controller needs an integer frame_count")
        self._delegate = delegate
        self._maximum_frames = maximum_frames
        self._start_frame = frame_count
        self._error_type = error_type
        self._error_message = error_message

    @property
    def frame_count(self) -> int:
        value = getattr(self._delegate, "frame_count", None)
        if type(value) is not int or value < self._start_frame:  # noqa: E721
            raise ControllerFrameBudgetError("controller frame_count is invalid")
        return value

    @property
    def frames_executed(self) -> int:
        return self.frame_count - self._start_frame

    def tick(self, frames: int) -> None:
        if (
            type(frames) is not int  # noqa: E721
            or frames < 0
            or self.frames_executed + frames > self._maximum_frames
        ):
            raise self._error_type(self._error_message)
        self._delegate.tick(frames)

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        """Preserve the delegate's bounded cartridge-RAM observation port."""

        reader = getattr(self._delegate, "read_cartridge_ram_u8", None)
        if not callable(reader):
            raise TypeError("frame-budget controller lacks cartridge-RAM access")
        value = reader(bank, address)
        if type(value) is not int or not 0 <= value <= 0xFF:  # noqa: E721
            raise TypeError("cartridge-RAM reader returned an invalid byte")
        return value

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class MonotonicWallTimeBudgetController:
    """Refuse new input or frames at a cooperative monotonic deadline.

    Release and read-only endpoint operations remain available after expiry. This
    is an admission boundary, not a preemptive watchdog for an already-entered
    native, policy, or filesystem call.
    """

    __slots__ = (
        "_delegate",
        "_last_reading",
        "_maximum_wall_seconds",
        "_monotonic_clock",
        "_started_at",
    )

    def __init__(
        self,
        delegate: ControllerPort,
        *,
        maximum_wall_seconds: int,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if type(maximum_wall_seconds) is not int or maximum_wall_seconds <= 0:  # noqa: E721
            raise ValueError("maximum_wall_seconds must be a positive integer")
        if not callable(monotonic_clock):
            raise TypeError("monotonic_clock must be callable")
        started_at = monotonic_clock()
        if not isinstance(started_at, (int, float)) or not isfinite(started_at):
            raise TypeError("monotonic_clock returned an invalid reading")
        self._delegate = delegate
        self._maximum_wall_seconds = maximum_wall_seconds
        self._monotonic_clock = monotonic_clock
        self._started_at = float(started_at)
        self._last_reading = float(started_at)

    @property
    def maximum_wall_seconds(self) -> int:
        return self._maximum_wall_seconds

    @property
    def elapsed_seconds(self) -> float:
        reading = self._monotonic_clock()
        if (
            not isinstance(reading, (int, float))
            or not isfinite(reading)
            or reading < self._last_reading
        ):
            raise RuntimeError("monotonic_clock returned an invalid reading")
        self._last_reading = float(reading)
        return self._last_reading - self._started_at

    def check_wall_time_budget(self) -> None:
        elapsed = self.elapsed_seconds
        if elapsed >= self._maximum_wall_seconds:
            raise ControllerWallTimeBudgetExhausted(
                maximum_wall_seconds=self._maximum_wall_seconds,
                elapsed_seconds=elapsed,
            )

    def press(self, button: str) -> None:
        self.check_wall_time_budget()
        self._delegate.press(button)

    def release(self, button: str) -> None:
        self._delegate.release(button)

    def tick(self, frames: int) -> None:
        self.check_wall_time_budget()
        self._delegate.tick(frames)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class WindowedFrameBudgetController:
    """Refuse a tick before it exceeds either a resettable window or total cap."""

    __slots__ = (
        "_delegate",
        "_initial_frame",
        "_maximum_frames_per_window",
        "_maximum_total_frames",
        "_window_start",
        "_nested_frame_deadlines",
    )

    def __init__(
        self,
        delegate: ControllerPort,
        *,
        maximum_frames_per_window: int,
        maximum_total_frames: int,
    ) -> None:
        for name, value in (
            ("maximum_frames_per_window", maximum_frames_per_window),
            ("maximum_total_frames", maximum_total_frames),
        ):
            if type(value) is not int or value <= 0:  # noqa: E721
                raise ValueError(f"{name} must be a positive integer")
        if maximum_frames_per_window > maximum_total_frames:
            raise ValueError("per-window frames cannot exceed the total cap")
        frame_count = getattr(delegate, "frame_count", None)
        if type(frame_count) is not int or frame_count < 0:  # noqa: E721
            raise TypeError("windowed frame budget needs an integer frame_count")
        self._delegate = delegate
        self._initial_frame = frame_count
        self._window_start = frame_count
        self._maximum_frames_per_window = maximum_frames_per_window
        self._maximum_total_frames = maximum_total_frames
        self._nested_frame_deadlines: list[int] = []

    @contextmanager
    def limit_additional_frames(self, maximum_frames: int) -> Iterator[None]:
        """Narrow the existing controller chain without resetting any budget.

        The absolute deadline survives begin_window; nested scopes cannot widen
        an outer cap. Exceptions restore the outer limits, never spent frames.
        """
        if type(maximum_frames) is not int or maximum_frames <= 0:
            raise ValueError("nested frame limit must be a positive integer")
        self._nested_frame_deadlines.append(self.frame_count + maximum_frames)
        try:
            yield
        finally:
            self._nested_frame_deadlines.pop()

    @property
    def frame_count(self) -> int:
        value = getattr(self._delegate, "frame_count", None)
        if type(value) is not int or value < self._initial_frame:  # noqa: E721
            raise ControllerFrameBudgetError("controller frame_count is invalid")
        return value

    @property
    def frames_executed(self) -> int:
        return self.frame_count - self._initial_frame

    @property
    def frames_this_window(self) -> int:
        return self.frame_count - self._window_start

    @property
    def remaining_frames(self) -> int:
        """Headroom under every live cap; a new window never refunds total use."""
        return min(
            self._maximum_total_frames - self.frames_executed,
            self._maximum_frames_per_window - self.frames_this_window,
            *(end - self.frame_count for end in self._nested_frame_deadlines),
        )

    def begin_window(self) -> None:
        self._window_start = self.frame_count

    def tick(self, frames: int) -> None:
        if (
            type(frames) is not int  # noqa: E721
            or frames < 0
            or self.frames_executed + frames > self._maximum_total_frames
            or self.frames_this_window + frames > self._maximum_frames_per_window
            or any(self.frame_count + frames > end for end in self._nested_frame_deadlines)
        ):
            raise ControllerFrameBudgetExhausted(
                "controller exhausted its hard windowed frame budget"
            )
        self._delegate.tick(frames)

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        """Preserve the delegate's bounded cartridge-RAM observation port."""

        reader = getattr(self._delegate, "read_cartridge_ram_u8", None)
        if not callable(reader):
            raise TypeError("windowed frame budget lacks cartridge-RAM access")
        value = reader(bank, address)
        if type(value) is not int or not 0 <= value <= 0xFF:  # noqa: E721
            raise TypeError("cartridge-RAM reader returned an invalid byte")
        return value

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


@dataclass(frozen=True, slots=True)
class ControllerTiming:
    press_frames: int = 1
    release_frames: int = 1
    wait_frames: int = 1

    def __post_init__(self) -> None:
        for name, value in (
            ("press_frames", self.press_frames),
            ("release_frames", self.release_frames),
            ("wait_frames", self.wait_frames),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class ExecutedAction:
    macro: MacroAction
    buttons: tuple[str, ...]
    frames: int


class FrameSafeExecutor:
    """Compile qualified macro-actions and guarantee every pressed button is released."""

    def __init__(
        self,
        controller: ControllerPort,
        timing: ControllerTiming | None = None,
    ) -> None:
        self._controller = controller
        self._timing = timing or ControllerTiming()

    @property
    def controller(self) -> ControllerPort:
        return self._controller

    @property
    def timing(self) -> ControllerTiming:
        return self._timing

    def execute(self, action: MacroAction) -> ExecutedAction:
        button = self._button_for(action)
        if button is None:
            frames = self._timing.wait_frames * action.repeat
            self._controller.tick(frames)
            return ExecutedAction(action, (), frames)

        frames = 0
        for _ in range(action.repeat):
            self._controller.press(button)
            try:
                self._controller.tick(self._timing.press_frames)
                frames += self._timing.press_frames
            finally:
                self._controller.release(button)
            self._controller.tick(self._timing.release_frames)
            frames += self._timing.release_frames
        return ExecutedAction(action, (button,) * action.repeat, frames)

    def release_restored_inputs(self) -> tuple[str, ...]:
        """Explicit key-up-only recovery; never synthesize a key press."""
        release = getattr(self._controller, "release_restored_inputs", None)
        if not callable(release):
            raise UnsupportedMacroActionError("controller lacks restored-input release")
        return release()

    @staticmethod
    def _button_for(action: MacroAction) -> str | None:
        if action.kind is MacroActionKind.WAIT:
            return None
        if action.kind is MacroActionKind.MOVE:
            if not isinstance(action.value, str) or action.value not in {
                "up",
                "right",
                "down",
                "left",
            }:
                raise UnsupportedMacroActionError(f"invalid movement direction: {action.value!r}")
            return action.value
        if action.kind in {MacroActionKind.INTERACT, MacroActionKind.CONFIRM}:
            return "a"
        if action.kind is MacroActionKind.CANCEL:
            return "b"
        if action.kind is MacroActionKind.OPEN_MENU:
            return "start"
        raise UnsupportedMacroActionError(
            f"{action.kind.value} requires a qualified specialist compiler"
        )


class ControllerActionLimiter:
    """Reserve admitted macro attempts before delegation across one episode."""

    __slots__ = (
        "_admit_action",
        "_completed_actions",
        "_delegate",
        "_maximum_actions",
        "attempted_actions",
    )

    def __init__(
        self,
        delegate: ChapterExecutor,
        *,
        maximum_actions: int,
        admit_action: Callable[[], None] | None = None,
    ) -> None:
        if type(maximum_actions) is not int or maximum_actions <= 0:  # noqa: E721
            raise ValueError("maximum_actions must be a positive integer")
        if admit_action is not None and not callable(admit_action):
            raise TypeError("admit_action must be callable")
        self._delegate = delegate
        self._maximum_actions = maximum_actions
        self._admit_action = admit_action
        self.attempted_actions = 0
        self._completed_actions = 0

    @property
    def completed_actions(self) -> int:
        return self._completed_actions

    @property
    def maximum_actions(self) -> int:
        return self._maximum_actions

    def execute(self, action: MacroAction) -> object:
        if self.attempted_actions >= self._maximum_actions:
            raise ControllerActionBudgetExhausted(
                maximum_actions=self._maximum_actions,
                attempted_actions=self.attempted_actions,
            )
        if self._admit_action is not None:
            self._admit_action()
        self.attempted_actions += 1
        result = self._delegate.execute(action)
        self._completed_actions += 1
        return result


class ChapterExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class CountingExecutor:
    def __init__(self, delegate: ChapterExecutor) -> None:
        self.delegate = delegate
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> object:
        result = self.delegate.execute(action)
        self.actions_executed += 1
        return result
