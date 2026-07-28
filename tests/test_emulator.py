from __future__ import annotations

import io
from pathlib import Path

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.emulator import (
    EmulatorEndedError,
    EmulatorError,
    PyBoyAdapter,
)
from pokemon_red_completion.executor import ControllerTiming, FrameSafeExecutor
from pokemon_red_completion.rom import RomFingerprint, RomValidationError


class FakeMemory:
    def __init__(self, values: dict[int, int] | None = None) -> None:
        self.values = values or {}

    def __getitem__(self, address: int) -> int:
        return self.values.get(address, 0)


class FakePyBoy:
    def __init__(
        self,
        rom_stream: io.BytesIO,
        kwargs: dict[str, object],
    ) -> None:
        self.rom_stream = rom_stream
        self.kwargs = kwargs
        self.memory = FakeMemory({0xD732: 0x12})
        self.events: list[tuple[str, str | int | bool]] = []
        self.tick_calls: list[tuple[int, bool, bool]] = []
        self.speed: int | None = None
        self.alive = True

    def set_emulation_speed(self, target_speed: int) -> None:
        self.speed = target_speed

    def tick(self, count: int, *, render: bool, sound: bool) -> bool:
        self.tick_calls.append((count, render, sound))
        self.events.append(("tick", count))
        return self.alive

    def button_press(self, button: str) -> None:
        self.events.append(("press", button))

    def button_release(self, button: str) -> None:
        self.events.append(("release", button))

    def stop(self, save: bool = True, **kwargs: object) -> None:
        assert not kwargs
        self.events.append(("stop", save))


class RecordingFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[io.BytesIO, dict[str, object]]] = []
        self.backend: FakePyBoy | None = None

    def __call__(self, rom_stream: io.BytesIO, **kwargs: object) -> FakePyBoy:
        self.calls.append((rom_stream, kwargs))
        self.backend = FakePyBoy(rom_stream, kwargs)
        return self.backend


def _fingerprint(payload: bytes) -> RomFingerprint:
    return RomFingerprint(
        filename="<private>",
        title="POKEMON RED",
        size_bytes=len(payload),
        sha1="1" * 40,
        sha256="2" * 64,
    )


@pytest.fixture
def accept_test_rom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pokemon_red_completion.emulator.verify_rom_bytes",
        _fingerprint,
    )


@pytest.fixture
def recording_factory(monkeypatch: pytest.MonkeyPatch) -> RecordingFactory:
    factory = RecordingFactory()
    monkeypatch.setattr(
        "pokemon_red_completion.emulator._load_pyboy_factory",
        lambda: factory,
    )
    return factory


def test_adapter_uses_verified_stream_and_safe_backend_flags(
    tmp_path: Path,
    accept_test_rom: None,
    recording_factory: RecordingFactory,
) -> None:
    payload = b"private fixture bytes"
    rom_path = tmp_path / "fixture.gb"
    rom_path.write_bytes(payload)

    with PyBoyAdapter(rom_path) as emulator:
        assert len(recording_factory.calls) == 1
        rom_stream, kwargs = recording_factory.calls[0]
        assert isinstance(rom_stream, io.BytesIO)
        assert rom_stream.getvalue() == payload
        assert kwargs == {
            "ram_file": None,
            "rtc_file": None,
            "window": "null",
            "no_input": True,
            "sound_volume": 0,
            "sound_emulated": False,
            "log_level": "ERROR",
        }
        assert emulator.read_u8(0xD732) == 0x12
        assert emulator.fingerprint.public_dict() == _fingerprint(payload).public_dict()
        assert emulator.window_name == "null"
        assert emulator.speed == 0
        assert recording_factory.backend is not None
        assert recording_factory.backend.speed == 0

    assert recording_factory.backend is not None
    assert recording_factory.backend.events[-1] == ("stop", False)
    assert rom_stream.closed


def test_adapter_satisfies_frame_safe_controller_contract(
    tmp_path: Path,
    accept_test_rom: None,
    recording_factory: RecordingFactory,
) -> None:
    rom_path = tmp_path / "fixture.gb"
    rom_path.write_bytes(b"fixture")

    with PyBoyAdapter(rom_path) as emulator:
        executor = FrameSafeExecutor(
            emulator,
            ControllerTiming(press_frames=2, release_frames=3),
        )
        result = executor.execute(MacroAction(MacroActionKind.MOVE, "right"))

        assert result.frames == 5
        assert emulator.frame_count == 5
        assert not emulator.pressed_buttons
        assert recording_factory.backend is not None
        assert recording_factory.backend.events == [
            ("press", "right"),
            ("tick", 2),
            ("release", "right"),
            ("tick", 3),
        ]
        assert recording_factory.backend.tick_calls == [
            (2, False, False),
            (3, False, False),
        ]


def test_watch_mode_uses_safe_visible_backend_and_renders_each_frame(
    tmp_path: Path,
    accept_test_rom: None,
    recording_factory: RecordingFactory,
) -> None:
    payload = b"private fixture bytes"
    rom_path = tmp_path / "fixture.gb"
    rom_path.write_bytes(payload)

    with PyBoyAdapter(rom_path, watch=True) as emulator:
        assert len(recording_factory.calls) == 1
        rom_stream, kwargs = recording_factory.calls[0]
        assert isinstance(rom_stream, io.BytesIO)
        assert rom_stream.getvalue() == payload
        assert kwargs == {
            "ram_file": None,
            "rtc_file": None,
            "window": "SDL2",
            "no_input": True,
            "sound_volume": 0,
            "sound_emulated": False,
            "log_level": "ERROR",
        }
        assert emulator.window_name == "SDL2"
        assert emulator.speed == 2
        assert recording_factory.backend is not None
        assert recording_factory.backend.speed == 2

        emulator.tick(3)

        assert emulator.frame_count == 3
        assert recording_factory.backend.tick_calls == [
            (1, True, False),
            (1, True, False),
            (1, True, False),
        ]

    assert recording_factory.backend is not None
    assert recording_factory.backend.events[-1] == ("stop", False)
    assert rom_stream.closed


@pytest.mark.parametrize("speed", [1, 2, 4])
def test_watch_mode_accepts_only_supported_speed_presets(
    speed: int,
    tmp_path: Path,
    accept_test_rom: None,
    recording_factory: RecordingFactory,
) -> None:
    rom_path = tmp_path / "fixture.gb"
    rom_path.write_bytes(b"fixture")

    with PyBoyAdapter(rom_path, watch=True, speed=speed) as emulator:
        assert emulator.speed == speed
        assert recording_factory.backend is not None
        assert recording_factory.backend.speed == speed


@pytest.mark.parametrize("speed", [0, -1, 3, 5])
def test_watch_mode_rejects_unsupported_speed_presets(speed: int) -> None:
    with pytest.raises(ValueError, match="watch speed must be one of: 1, 2, 4"):
        PyBoyAdapter("fixture.gb", watch=True, speed=speed)


@pytest.mark.parametrize("speed", [False, 1.5, "2"])
def test_adapter_rejects_non_integer_speed(speed: object) -> None:
    with pytest.raises(TypeError, match="speed must be an integer or None"):
        PyBoyAdapter("fixture.gb", watch=True, speed=speed)  # type: ignore[arg-type]


def test_headless_mode_rejects_speed_override() -> None:
    with pytest.raises(ValueError, match="speed is available only when watch=True"):
        PyBoyAdapter("fixture.gb", speed=1)


def test_adapter_rejects_non_boolean_watch_mode() -> None:
    with pytest.raises(TypeError, match="watch must be a boolean"):
        PyBoyAdapter("fixture.gb", watch=1)  # type: ignore[arg-type]


def test_adapter_fails_closed_on_invalid_operations(
    tmp_path: Path,
    accept_test_rom: None,
    recording_factory: RecordingFactory,
) -> None:
    rom_path = tmp_path / "fixture.gb"
    rom_path.write_bytes(b"fixture")

    with PyBoyAdapter(rom_path) as emulator:
        with pytest.raises(ValueError, match="positive integer"):
            emulator.tick(0)
        with pytest.raises(ValueError, match="Unsupported button"):
            emulator.press("turbo")
        for forbidden_address in (-1, False, 0x0000, 0x8000, 0xA000, 0xFF00, 0x10000):
            with pytest.raises(ValueError, match="Work RAM"):
                emulator.read_u8(forbidden_address)

        emulator.press("a")
        with pytest.raises(EmulatorError, match="already pressed"):
            emulator.press("a")
        emulator.release("a")
        with pytest.raises(EmulatorError, match="not pressed"):
            emulator.release("a")

        assert recording_factory.backend is not None
        recording_factory.backend.alive = False
        with pytest.raises(EmulatorEndedError, match="ended"):
            emulator.tick(1)


def test_invalid_rom_is_rejected_before_backend_construction(
    tmp_path: Path,
    recording_factory: RecordingFactory,
) -> None:
    rom_path = tmp_path / "wrong.gb"
    rom_path.write_bytes(b"not the supported ROM")

    with pytest.raises(RomValidationError, match="Unsupported ROM revision"):
        PyBoyAdapter(rom_path).start()

    assert recording_factory.calls == []
