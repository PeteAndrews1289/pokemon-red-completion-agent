from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind


class ControllerPort(Protocol):
    """Minimal emulator-control authority owned exclusively by the executor."""

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def tick(self, frames: int) -> None: ...


class UnsupportedMacroActionError(ValueError):
    """Raised when a specialist requests an action without a qualified compiler."""


class ControllerFrameBudgetError(RuntimeError):
    """Raised before controller time can exceed a declared frame budget."""


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

    def __getattr__(self, name: str) -> Any:
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

    def begin_window(self) -> None:
        self._window_start = self.frame_count

    def tick(self, frames: int) -> None:
        if (
            type(frames) is not int  # noqa: E721
            or frames < 0
            or self.frames_executed + frames > self._maximum_total_frames
            or self.frames_this_window + frames > self._maximum_frames_per_window
        ):
            raise ControllerFrameBudgetError(
                "controller exhausted its hard windowed frame budget"
            )
        self._delegate.tick(frames)

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
                raise UnsupportedMacroActionError(
                    f"invalid movement direction: {action.value!r}"
                )
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
