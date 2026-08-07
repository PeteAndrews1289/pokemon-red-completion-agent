from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, MacroActionKind


class ControllerPort(Protocol):
    """Minimal emulator-control authority owned exclusively by the executor."""

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def tick(self, frames: int) -> None: ...


class UnsupportedMacroActionError(ValueError):
    """Raised when a specialist requests an action without a qualified compiler."""


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
