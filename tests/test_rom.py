from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pokemon_red_completion.constants import SupportedRom
from pokemon_red_completion.rom import (
    RomValidationError,
    fingerprint_rom,
    resolve_rom_path,
    verify_rom,
)


def _synthetic_rom() -> bytearray:
    contents = bytearray(0x200)
    contents[0x134:0x13F] = b"POKEMON RED"
    return contents


def test_fingerprint_reports_identity_without_public_path(tmp_path: Path) -> None:
    contents = _synthetic_rom()
    rom_path = tmp_path / "private-fixture.bin"
    rom_path.write_bytes(contents)

    fingerprint = fingerprint_rom(rom_path)
    public = fingerprint.public_dict()

    assert fingerprint.title == "POKEMON RED"
    assert fingerprint.sha1 == hashlib.sha1(contents, usedforsecurity=False).hexdigest()
    assert fingerprint.sha256 == hashlib.sha256(contents).hexdigest()
    assert "filename" not in public
    assert str(tmp_path) not in str(public)


def test_verify_rom_requires_an_exact_identity(tmp_path: Path) -> None:
    contents = _synthetic_rom()
    rom_path = tmp_path / "fixture.bin"
    rom_path.write_bytes(contents)
    fingerprint = fingerprint_rom(rom_path)
    expected = SupportedRom(
        title=fingerprint.title,
        size_bytes=fingerprint.size_bytes,
        sha1=fingerprint.sha1,
        sha256=fingerprint.sha256,
    )

    assert verify_rom(rom_path, expected) == fingerprint

    with pytest.raises(RomValidationError, match="Unsupported ROM revision"):
        verify_rom(
            rom_path,
            SupportedRom(title="WRONG", size_bytes=1, sha1="a", sha256="b"),
        )


def test_resolve_rom_path_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("POKEMON_RED_ROM", raising=False)
    with pytest.raises(RomValidationError, match="Pass --rom"):
        resolve_rom_path(None)

    missing = tmp_path / "missing.gb"
    with pytest.raises(RomValidationError, match="does not exist"):
        resolve_rom_path(missing)
