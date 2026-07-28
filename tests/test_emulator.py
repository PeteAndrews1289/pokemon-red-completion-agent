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
        self.speed: int | None = None
        self.alive = True

    def set_emulation_speed(self, target_speed: int) -> None:
        self.speed = target_speed

    def tick(self, count: int, *, render: bool, sound: bool) -> bool:
        assert not render
        assert not sound
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


def test_adapter_uses_verified_stream_and_safe_backend_flags(
    tmp_path: Path,
    accept_test_rom: None,
) -> None:
    payload = b"private fixture bytes"
    rom_path = tmp_path / "fixture.gb"
    rom_path.write_bytes(payload)
    factory = RecordingFactory()

    with PyBoyAdapter(
        rom_path,
        factory=factory,
    ) as emulator:
        assert len(factory.calls) == 1
        rom_stream, kwargs = factory.calls[0]
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
        assert factory.backend is not None
        assert factory.backend.speed == 0

    assert factory.backend is not None
    assert factory.backend.events[-1] == ("stop", False)
    assert rom_stream.closed


def test_adapter_satisfies_frame_safe_controller_contract(
    tmp_path: Path,
    accept_test_rom: None,
) -> None:
    rom_path = tmp_path / "fixture.gb"
    rom_path.write_bytes(b"fixture")
    factory = RecordingFactory()

    with PyBoyAdapter(rom_path, factory=factory) as emulator:
        executor = FrameSafeExecutor(
            emulator,
            ControllerTiming(press_frames=2, release_frames=3),
        )
        result = executor.execute(MacroAction(MacroActionKind.MOVE, "right"))

        assert result.frames == 5
        assert emulator.frame_count == 5
        assert not emulator.pressed_buttons
        assert factory.backend is not None
        assert factory.backend.events == [
            ("press", "right"),
            ("tick", 2),
            ("release", "right"),
            ("tick", 3),
        ]


def test_adapter_fails_closed_on_invalid_operations(
    tmp_path: Path,
    accept_test_rom: None,
) -> None:
    rom_path = tmp_path / "fixture.gb"
    rom_path.write_bytes(b"fixture")
    factory = RecordingFactory()

    with PyBoyAdapter(rom_path, factory=factory) as emulator:
        with pytest.raises(ValueError, match="positive integer"):
            emulator.tick(0)
        with pytest.raises(ValueError, match="Unsupported button"):
            emulator.press("turbo")
        with pytest.raises(ValueError, match="0x0000"):
            emulator.read_u8(0x10000)

        emulator.press("a")
        with pytest.raises(EmulatorError, match="already pressed"):
            emulator.press("a")
        emulator.release("a")
        with pytest.raises(EmulatorError, match="not pressed"):
            emulator.release("a")

        assert factory.backend is not None
        factory.backend.alive = False
        with pytest.raises(EmulatorEndedError, match="ended"):
            emulator.tick(1)


def test_invalid_rom_is_rejected_before_backend_construction(tmp_path: Path) -> None:
    rom_path = tmp_path / "wrong.gb"
    rom_path.write_bytes(b"not the supported ROM")
    factory = RecordingFactory()

    with pytest.raises(RomValidationError, match="Unsupported ROM revision"):
        PyBoyAdapter(rom_path, factory=factory).start()

    assert factory.calls == []
