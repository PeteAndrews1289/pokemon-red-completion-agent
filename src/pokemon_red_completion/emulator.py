from __future__ import annotations

import io
from collections.abc import Callable
from contextlib import suppress
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, runtime_checkable

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


@runtime_checkable
class EmulatorFrameObserver(Protocol):
    """Read-only rendered-frame sink; it has no controller methods."""

    def wants_frame(self, logical_frame: int) -> bool: ...

    def publish_frame(
        self,
        width: int,
        height: int,
        rgb: bytes,
        logical_frame: int,
    ) -> None: ...


PyBoyFactory = Callable[..., PyBoyBackend]
WindowEventPump = Callable[[], bool]


class CausallyMeteredEmulator:
    """Keep raw controller primitives inside the emulator trust boundary.

    Title adapters may wrap an already-open emulator and supply one durable
    frame-accounting callback.  Every attempted tick reconciles the delegate's
    actual frame counter in ``finally``, including a tick that advances and
    then raises.  Controller-action admission remains the executor's job.
    """

    __slots__ = ("_admit_frames", "_delegate", "_record_frames")

    def __init__(
        self,
        delegate: Any,
        *,
        record_frames: Callable[[int], None],
        admit_frames: Callable[[int], None] | None = None,
    ) -> None:
        if not callable(record_frames):
            raise TypeError("metered emulator needs a frame recorder")
        if admit_frames is not None and not callable(admit_frames):
            raise TypeError("metered emulator frame admission differs")
        self._admit_frames = admit_frames
        self._delegate = delegate
        self._record_frames = record_frames

    @property
    def frame_count(self) -> int:
        value = self._delegate.frame_count
        if type(value) is not int or value < 0:  # noqa: E721
            raise EmulatorError("metered emulator frame counter differs")
        return value

    @property
    def pressed_buttons(self) -> frozenset[str]:
        value = self._delegate.pressed_buttons
        if not isinstance(value, frozenset):
            raise EmulatorError("metered emulator button state differs")
        return value

    def tick(self, frames: int) -> None:
        if self._admit_frames is not None:
            self._admit_frames(frames)
        before = self.frame_count
        try:
            self._delegate.tick(frames)
        finally:
            after = self.frame_count
            if after < before:
                raise EmulatorError("metered emulator frame counter moved backwards")
            self._record_frames(after - before)

    def press(self, button: str) -> None:
        self._delegate.press(button)

    def release(self, button: str) -> None:
        self._delegate.release(button)

    def load_state_bytes(self, payload: bytes) -> None:
        self._delegate.load_state_bytes(payload)

    def save_state_bytes(self) -> bytes:
        return self._delegate.save_state_bytes()

    def read_u8(self, address: int) -> int:
        return self._delegate.read_u8(address)

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        return self._delegate.read_cartridge_ram_u8(bank, address)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


class OneWayEmulatorPort:
    """Keep raw frame, controller, and state-capture calls in this module.

    Higher-level one-shot runtimes may impose stricter ordering and accounting
    while this port preserves the repository rule that raw emulator primitives
    never spread into experiment or campaign modules.  It deliberately exposes
    no restore operation.

    This is a narrow capability surface, not a sandbox against deliberately
    introspective Python running in the same process.  A caller that supplies
    callbacks must bind their exact executable source; private-name syntax
    cannot replace that provenance boundary.  The independent counters below
    detect ordinary or accidental low-level bypasses inside authenticated code.
    """

    __slots__ = (
        "__advanced_frames",
        "__capture_token",
        "__controller_actions",
        "__controller_events",
        "__delegate",
        "__state_captures",
    )

    def __init__(self, delegate: Any, *, capture_token: object) -> None:
        self.__advanced_frames = 0
        self.__capture_token = capture_token
        self.__controller_actions = 0
        self.__controller_events = 0
        self.__delegate = delegate
        self.__state_captures = 0

    @property
    def advanced_frames(self) -> int:
        return self.__advanced_frames

    @property
    def controller_actions(self) -> int:
        return self.__controller_actions

    @property
    def controller_events(self) -> int:
        return self.__controller_events

    @property
    def state_captures(self) -> int:
        return self.__state_captures

    @property
    def frame_count(self) -> int:
        return self.__delegate.frame_count

    @property
    def pressed_buttons(self) -> frozenset[str]:
        return self.__delegate.pressed_buttons

    @property
    def fingerprint(self) -> RomFingerprint:
        return self.__delegate.fingerprint

    @property
    def window_name(self) -> str:
        return self.__delegate.window_name

    @property
    def speed(self) -> int:
        return self.__delegate.speed

    @property
    def pyboy_version(self) -> str:
        return self.__delegate.pyboy_version

    def advance(self, frames: int) -> None:
        before = self.frame_count
        try:
            self.__delegate.tick(frames)
        finally:
            after = self.frame_count
            if after < before:
                raise EmulatorError(
                    "one-way emulator frame counter moved backwards"
                )
            self.__advanced_frames += after - before

    def button_down(self, button: str) -> None:
        self.__delegate.press(button)
        self.__controller_actions += 1
        self.__controller_events += 1

    def button_up(self, button: str) -> None:
        self.__delegate.release(button)
        self.__controller_events += 1

    def capture_state_bytes(self, *, token: object) -> bytes:
        if token is not self.__capture_token:
            raise EmulatorError("one-way emulator capture authority differs")
        payload = self.__delegate.save_state_bytes()
        self.__state_captures += 1
        return payload

    def close(self) -> None:
        self.__delegate.close()

    def read_u8(self, address: int) -> int:
        return self.__delegate.read_u8(address)

    def read_wram(self, bank: int, address: int, length: int) -> bytes:
        return self.__delegate.read_wram(bank, address, length)

    def read_cartridge_ram_u8(self, bank: int, address: int) -> int:
        return self.__delegate.read_cartridge_ram_u8(bank, address)

    def read_cartridge_ram(
        self,
        bank: int,
        address: int,
        length: int,
    ) -> bytes:
        return self.__delegate.read_cartridge_ram(bank, address, length)


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
        frame_observer: EmulatorFrameObserver | None = None,
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
        if frame_observer is not None and not isinstance(frame_observer, EmulatorFrameObserver):
            raise TypeError("frame_observer must implement EmulatorFrameObserver")
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
        self._frame_observer = frame_observer
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

    def save_state_bytes(self) -> bytes:
        """Return an exact in-memory state for immediate restore readback.

        The payload never receives a path, which lets causal validators prove
        that the bytes they supplied were the bytes the emulator accepted
        without creating an extra private file.
        """

        with io.BytesIO() as handle:
            self._require_backend().save_state(handle)
            payload = handle.getvalue()
        if not payload:
            raise EmulatorError("saved state bytes are unavailable")
        return payload

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

    def load_state_bytes(self, payload: bytes) -> None:
        """Restore already-authenticated state bytes without reopening a path."""

        if not isinstance(payload, bytes) or not payload:
            raise EmulatorError("saved state bytes are unavailable")
        with io.BytesIO(payload) as handle:
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

    def read_wram(self, bank: int, address: int, length: int) -> bytes:
        """Read one exact fixed or switchable WRAM bank without changing it.

        PyBoy's bank-qualified memory view addresses CGB WRAM directly.  This
        avoids changing the live SVBK register merely to observe Crystal's
        bank-one campaign state.
        """

        if type(bank) is not int or not 0 <= bank <= 7:  # noqa: E721
            raise ValueError("WRAM bank must be between 0 and 7")
        if type(address) is not int or not 0xC000 <= address <= 0xDFFF:  # noqa: E721
            raise ValueError("WRAM address must be between 0xC000 and 0xDFFF")
        if type(length) is not int or length < 1:  # noqa: E721
            raise ValueError("WRAM read length must be positive")
        region_end = 0xCFFF if address < 0xD000 else 0xDFFF
        if address + length - 1 > region_end:
            raise ValueError("WRAM read must remain inside one banked region")
        if address < 0xD000 and bank != 0:
            raise ValueError("fixed WRAM must use bank 0")
        if address >= 0xD000 and bank == 0:
            raise ValueError("switchable WRAM must use bank 1 through 7")
        memory = self._require_backend().memory
        return bytes(int(memory[bank, address + offset]) for offset in range(length))

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

    def read_cartridge_ram(self, bank: int, address: int, length: int) -> bytes:
        """Read one exact MBC cartridge-RAM bank without changing emulator state.

        The shared port is intentionally read-only and restricted to the four
        SRAM banks used by the pinned Red and Crystal cartridges. Title
        adapters retain responsibility for allowlisting semantic regions.
        """

        if type(bank) is not int or not 0 <= bank <= 3:  # noqa: E721
            raise ValueError("Cartridge RAM bank must be between 0 and 3")
        if type(address) is not int or not 0xA000 <= address <= 0xBFFF:  # noqa: E721
            raise ValueError("Cartridge RAM address must be between 0xA000 and 0xBFFF")
        if type(length) is not int or length < 1:  # noqa: E721
            raise ValueError("Cartridge RAM read length must be positive")
        if address + length - 1 > 0xBFFF:
            raise ValueError("Cartridge RAM read must remain inside one bank")
        memory = self._require_backend().memory
        return bytes(int(memory[bank, address + offset]) for offset in range(length))

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
            self._tick_backend(backend, frames, render=self._frame_observer is not None)
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
        observer = self._frame_observer
        next_logical_frame = self._logical_frame + frames
        capture_frame = observer is not None and observer.wants_frame(next_logical_frame)
        render_frame = render if observer is None or self._watch else capture_frame
        alive = bool(backend.tick(frames, render=render_frame, sound=False))
        self._logical_frame += frames
        if not alive:
            raise EmulatorEndedError(
                f"Emulator ended before completing frame {self._logical_frame}."
            )
        if observer is not None and capture_frame:
            width, height, rgb = self._screen_rgb(backend)
            observer.publish_frame(width, height, rgb, self._logical_frame)

    @staticmethod
    def _screen_rgb(backend: PyBoyBackend) -> tuple[int, int, bytes]:
        """Copy PyBoy's rendered RGB/RGBA ndarray without exposing its backend."""

        screen = getattr(backend, "screen", None)
        pixels = getattr(screen, "ndarray", None)
        shape = getattr(pixels, "shape", None)
        tobytes = getattr(pixels, "tobytes", None)
        if (
            not isinstance(shape, tuple)
            or len(shape) != 3
            or any(type(value) is not int or value < 1 for value in shape)  # noqa: E721
            or not callable(tobytes)
        ):
            raise EmulatorError("Rendered emulator frame is unavailable.")
        height, width, channels = shape
        if channels not in (3, 4) or width > 1024 or height > 1024:
            raise EmulatorError("Rendered emulator frame dimensions are unsupported.")
        raw = tobytes()
        if not isinstance(raw, bytes) or len(raw) != width * height * channels:
            raise EmulatorError("Rendered emulator frame bytes are inconsistent.")
        if channels == 4:
            rgb = bytearray(width * height * 3)
            rgb[0::3] = raw[0::4]
            rgb[1::3] = raw[1::4]
            rgb[2::3] = raw[2::4]
            raw = bytes(rgb)
        return width, height, raw

    @staticmethod
    def _validated_button(button: str) -> str:
        if not isinstance(button, str):
            raise TypeError("button must be a string")
        normalized = button.lower()
        if normalized not in SUPPORTED_BUTTONS:
            raise ValueError(f"Unsupported button: {button}")
        return normalized
