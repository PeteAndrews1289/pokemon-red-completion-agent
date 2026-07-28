from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import suppress
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from pokemon_red_completion.rom import (
    RomFingerprint,
    resolve_rom_path,
    verify_rom_bytes,
)

SUPPORTED_BUTTONS = frozenset({"a", "b", "start", "select", "up", "right", "down", "left"})


class EmulatorError(RuntimeError):
    """Raised when the private emulator runtime cannot proceed safely."""


class EmulatorDependencyError(EmulatorError):
    """Raised when the optional emulator dependency is unavailable."""


class EmulatorEndedError(EmulatorError):
    """Raised when PyBoy stops before a requested bounded operation completes."""


class MemoryView(Protocol):
    def __getitem__(self, address: int) -> int: ...


class PyBoyBackend(Protocol):
    memory: MemoryView

    def set_emulation_speed(self, target_speed: int) -> None: ...

    def tick(self, count: int, *, render: bool, sound: bool) -> bool: ...

    def button_press(self, button: str) -> None: ...

    def button_release(self, button: str) -> None: ...

    def stop(self, save: bool = True, **kwargs: Any) -> None: ...


PyBoyFactory = Callable[..., PyBoyBackend]


def _load_pyboy_factory() -> PyBoyFactory:
    try:
        from pyboy import PyBoy
    except ImportError as error:
        raise EmulatorDependencyError(
            'PyBoy is optional. Install it with: python -m pip install -e ".[emulator]"'
        ) from error
    return PyBoy


class PyBoyAdapter:
    """No-save, headless PyBoy authority implementing memory and controller ports.

    The verified ROM is provided as an in-memory stream. PyBoy therefore cannot
    discover or create sibling RAM/RTC files beside the user's private ROM.
    """

    def __init__(
        self,
        rom_path: str | Path,
        *,
        window: str = "null",
        speed: int = 0,
    ) -> None:
        self._rom_path = Path(rom_path)
        self._window = window
        self._speed = speed
        self._backend: PyBoyBackend | None = None
        self._rom_stream: io.BytesIO | None = None
        self._fingerprint: RomFingerprint | None = None
        self._pressed_buttons: set[str] = set()
        self._logical_frame = 0

    def _require_backend(self) -> PyBoyBackend:
        if self._backend is None:
            raise EmulatorError("Emulator is not running.")
        return self._backend

    @property
    def fingerprint(self) -> RomFingerprint:
        if self._fingerprint is None:
            raise EmulatorError("Emulator ROM metadata is unavailable.")
        return self._fingerprint

    @property
    def frame_count(self) -> int:
        return self._logical_frame

    @property
    def pressed_buttons(self) -> frozenset[str]:
        return frozenset(self._pressed_buttons)

    @property
    def pyboy_version(self) -> str:
        try:
            return version("pyboy")
        except PackageNotFoundError:
            return "injected-test-backend"

    def start(self) -> PyBoyAdapter:
        if self._backend is not None:
            raise EmulatorError("Emulator is already running.")

        path = resolve_rom_path(self._rom_path)
        payload = path.read_bytes()
        fingerprint = verify_rom_bytes(payload)
        rom_stream = io.BytesIO(payload)
        factory = _load_pyboy_factory()

        backend: PyBoyBackend | None = None
        try:
            backend = factory(
                rom_stream,
                ram_file=None,
                rtc_file=None,
                window=self._window,
                no_input=True,
                sound_volume=0,
                sound_emulated=False,
                log_level="ERROR",
            )
            backend.set_emulation_speed(self._speed)
        except Exception:
            if backend is not None:
                with suppress(Exception):
                    backend.stop(save=False)
            rom_stream.close()
            raise

        self._backend = backend
        self._rom_stream = rom_stream
        self._fingerprint = fingerprint
        self._logical_frame = 0
        return self

    def close(self) -> None:
        backend = self._backend
        rom_stream = self._rom_stream
        self._backend = None
        self._rom_stream = None
        self._fingerprint = None

        try:
            if backend is not None:
                try:
                    for button in tuple(sorted(self._pressed_buttons)):
                        backend.button_release(button)
                finally:
                    self._pressed_buttons.clear()
                    backend.stop(save=False)
        finally:
            if rom_stream is not None:
                rom_stream.close()

    def __enter__(self) -> PyBoyAdapter:
        return self.start()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def read_u8(self, address: int) -> int:
        if (
            not isinstance(address, int)
            or isinstance(address, bool)
            or not 0xC000 <= address <= 0xDFFF
        ):
            raise ValueError("Address must be an integer in Work RAM (0xC000 to 0xDFFF)")
        return int(self._require_backend().memory[address])

    def press(self, button: str) -> None:
        normalized = self._validated_button(button)
        if normalized in self._pressed_buttons:
            raise EmulatorError(f"Button is already pressed: {normalized}")
        self._require_backend().button_press(normalized)
        self._pressed_buttons.add(normalized)

    def release(self, button: str) -> None:
        normalized = self._validated_button(button)
        if normalized not in self._pressed_buttons:
            raise EmulatorError(f"Button is not pressed: {normalized}")
        self._require_backend().button_release(normalized)
        self._pressed_buttons.remove(normalized)

    def tick(self, frames: int) -> None:
        if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
            raise ValueError("frames must be a positive integer")
        alive = bool(self._require_backend().tick(frames, render=False, sound=False))
        self._logical_frame += frames
        if not alive:
            raise EmulatorEndedError(
                f"Emulator ended before completing frame {self._logical_frame}."
            )

    @staticmethod
    def _validated_button(button: str) -> str:
        if not isinstance(button, str):
            raise TypeError("button must be a string")
        normalized = button.lower()
        if normalized not in SUPPORTED_BUTTONS:
            raise ValueError(f"Unsupported button: {button}")
        return normalized
