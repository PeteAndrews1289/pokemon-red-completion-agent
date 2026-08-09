from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import suppress
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from pokemon_red_completion.constants import POKEMON_RED_US_REV_0, SupportedRom
from pokemon_red_completion.rom import (
    RomFingerprint,
    resolve_rom_path,
    verify_rom_bytes,
)

SUPPORTED_BUTTONS = frozenset({"a", "b", "start", "select", "up", "right", "down", "left"})
WATCH_SPEEDS = frozenset({1, 2, 4})
DEFAULT_WATCH_SPEED = 2


class EmulatorError(RuntimeError):
    """Raised when the private emulator runtime cannot proceed safely."""


class EmulatorDependencyError(EmulatorError):
    """Raised when the optional emulator dependency is unavailable."""


class EmulatorEndedError(EmulatorError):
    """Raised when PyBoy stops before a requested bounded operation completes."""


class MemoryView(Protocol):
    def __getitem__(self, address: int | tuple[int, int]) -> int: ...


class PyBoyBackend(Protocol):
    memory: MemoryView

    def set_emulation_speed(self, target_speed: int) -> None: ...

    def tick(self, count: int, *, render: bool, sound: bool) -> bool: ...

    def button_press(self, button: str) -> None: ...

    def button_release(self, button: str) -> None: ...

    def stop(self, save: bool = True, **kwargs: Any) -> None: ...

    def save_state(self, file_like_object: Any) -> None: ...

    def load_state(self, file_like_object: Any) -> None: ...


PyBoyFactory = Callable[..., PyBoyBackend]
WindowEventPump = Callable[[], bool]


def _load_pyboy_factory() -> PyBoyFactory:
    try:
        from pyboy import PyBoy
    except ImportError as error:
        raise EmulatorDependencyError(
            'PyBoy is optional. Install it with: python -m pip install -e ".[emulator]"'
        ) from error
    return PyBoy


def _load_sdl2_window_pump() -> WindowEventPump:
    """Build a view-only SDL event pump for watched runs.

    PyBoy's ``no_input=True`` deliberately skips its window event loop along
    with controller input. macOS needs that event loop for a window to become
    visible and remain responsive, so watch mode drains SDL events itself
    while forwarding none of them to the emulated controller.
    """

    try:
        import sdl2
        from sdl2.ext import get_events
    except ImportError as error:
        raise EmulatorDependencyError(
            "SDL2 display support is unavailable. Reinstall with: "
            'python -m pip install -e ".[emulator]"'
        ) from error

    raised = False

    def pump() -> bool:
        nonlocal raised
        if not raised:
            # A watched process owns one SDL window. Showing and raising it once
            # makes the separate game view difficult to miss behind Terminal.
            for window_id in range(1, 33):
                window = sdl2.SDL_GetWindowFromID(window_id)
                if window:
                    sdl2.SDL_ShowWindow(window)
                    sdl2.SDL_RaiseWindow(window)
                    break
            raised = True

        for event in get_events():
            if event.type == sdl2.SDL_QUIT:
                return False
            if (
                event.type == sdl2.SDL_WINDOWEVENT
                and event.window.event == sdl2.SDL_WINDOWEVENT_CLOSE
            ):
                return False
            if event.type == sdl2.SDL_KEYUP and event.key.keysym.sym == sdl2.SDLK_ESCAPE:
                return False
        return True

    return pump


class PyBoyAdapter:
    """No-save PyBoy authority implementing memory and controller ports.

    The verified ROM is provided as an in-memory stream. PyBoy therefore cannot
    discover or create sibling RAM/RTC files beside the user's private ROM.
    Watch mode changes presentation only: human input remains disabled and the
    adapter still stops without saving.
    """

    def __init__(
        self,
        rom_path: str | Path,
        *,
        watch: bool = False,
        speed: int | None = None,
        expected_rom: SupportedRom = POKEMON_RED_US_REV_0,
    ) -> None:
        """``expected_rom`` names which cartridge this adapter will load.

        It defaults to Red so every existing caller is unchanged. It exists
        because a living Pokedex needs a second version -- ten species are
        exclusive to Blue -- and until now the fingerprint check here was
        hard-coded, so the repository could refuse a cartridge it had already
        been told to expect.
        """

        if not isinstance(watch, bool):
            raise TypeError("watch must be a boolean")
        if not isinstance(expected_rom, SupportedRom):
            raise TypeError("expected_rom must be a SupportedRom")
        if speed is not None and (not isinstance(speed, int) or isinstance(speed, bool)):
            raise TypeError("speed must be an integer or None")
        if watch:
            resolved_speed = DEFAULT_WATCH_SPEED if speed is None else speed
            if resolved_speed not in WATCH_SPEEDS:
                choices = ", ".join(str(choice) for choice in sorted(WATCH_SPEEDS))
                raise ValueError(f"watch speed must be one of: {choices}")
            window_name = "SDL2"
        else:
            if speed is not None:
                raise ValueError("speed is available only when watch=True")
            resolved_speed = 0
            window_name = "null"

        self._rom_path = Path(rom_path)
        self._expected_rom = expected_rom
        self._watch = watch
        self._window_name = window_name
        self._speed = resolved_speed
        self._backend: PyBoyBackend | None = None
        self._window_event_pump: WindowEventPump | None = None
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
    def window_name(self) -> str:
        return self._window_name

    @property
    def speed(self) -> int:
        return self._speed

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
        fingerprint = verify_rom_bytes(payload, self._expected_rom)
        rom_stream = io.BytesIO(payload)
        factory = _load_pyboy_factory()
        window_event_pump = _load_sdl2_window_pump() if self._watch else None

        backend: PyBoyBackend | None = None
        try:
            backend_options: dict[str, Any] = {
                "ram_file": None,
                "rtc_file": None,
                "window": self._window_name,
                "no_input": True,
                "sound_volume": 0,
                "sound_emulated": False,
                "log_level": "ERROR",
            }
            if self._watch:
                backend_options["scale"] = 4
            backend = factory(rom_stream, **backend_options)
            backend.set_emulation_speed(self._speed)
            if window_event_pump is not None and not window_event_pump():
                raise EmulatorEndedError("The watched game window was closed.")
        except Exception:
            if backend is not None:
                with suppress(Exception):
                    backend.stop(save=False)
            rom_stream.close()
            raise

        self._backend = backend
        self._window_event_pump = window_event_pump
        self._rom_stream = rom_stream
        self._fingerprint = fingerprint
        self._logical_frame = 0
        return self

    def save_state(self, destination: str | Path) -> None:
        """Write the emulator's exact state to a file we name.

        This does not weaken the no-save property above. That property is about
        never letting PyBoy discover or create RAM and RTC files beside the
        user's private ROM, which is why the ROM arrives as an in-memory
        stream. Here the destination is explicit and chosen by the caller, so
        nothing is written near the ROM.

        The written file is derived from the ROM and is private data in exactly
        the way the ROM is. It belongs outside the repository and must never be
        committed; ``trajectory`` already refuses ``savestate`` keys in public
        artifacts for the same reason.
        """

        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            self._require_backend().save_state(handle)

    def load_state(self, source: str | Path) -> None:
        """Restore a state written by :meth:`save_state`.

        A state captured mid-route is a faithful starting point rather than an
        approximation: it restores real memory, so code under test meets the
        same bytes it would have met at that moment in a full run. That is the
        difference between this and a fake -- the fake can only answer what we
        thought to teach it.
        """

        path = Path(source)
        if not path.exists():
            raise EmulatorError(f"no saved state at {path}")
        with path.open("rb") as handle:
            self._require_backend().load_state(handle)

    def close(self) -> None:
        backend = self._backend
        self._window_event_pump = None
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

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        """Read one byte from Red's two dedicated saved-box SRAM banks.

        This is intentionally narrower than a general cartridge-memory port:
        only banks 2 and 3, which the pinned Red source reserves for boxes
        1–12, are visible. There is no corresponding write operation.
        """

        if type(bank) is not int or bank not in (2, 3):
            raise ValueError("Collection SRAM bank must be 2 or 3")
        if type(address) is not int or not 0xA000 <= address <= 0xBFFF:
            raise ValueError("Collection SRAM address must be between 0xA000 and 0xBFFF")
        return int(self._require_backend().memory[bank, address])

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
        backend = self._require_backend()
        if not self._watch:
            self._tick_backend(backend, frames, render=False)
            return
        for _ in range(frames):
            if self._window_event_pump is None:
                raise EmulatorError("Watched window event pump is unavailable.")
            if not self._window_event_pump():
                raise EmulatorEndedError("The watched game window was closed.")
            self._tick_backend(backend, 1, render=True)

    def _tick_backend(
        self,
        backend: PyBoyBackend,
        frames: int,
        *,
        render: bool,
    ) -> None:
        alive = bool(backend.tick(frames, render=render, sound=False))
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
