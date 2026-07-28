from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from pokemon_red_completion.constants import POKEMON_RED_US_REV_0, SupportedRom

ROM_ENVIRONMENT_VARIABLE = "POKEMON_RED_ROM"


class RomValidationError(ValueError):
    """Raised when the private ROM is missing or has an unsupported identity."""


@dataclass(frozen=True, slots=True)
class RomFingerprint:
    filename: str
    title: str
    size_bytes: int
    sha1: str
    sha256: str

    def public_dict(self) -> dict[str, str | int]:
        """Return reproducibility fields without exposing a private path or filename."""
        public = asdict(self)
        del public["filename"]
        return public


def resolve_rom_path(argument: str | Path | None) -> Path:
    raw_path = str(argument) if argument is not None else os.environ.get(ROM_ENVIRONMENT_VARIABLE)
    if not raw_path:
        raise RomValidationError(
            f"Pass --rom or set {ROM_ENVIRONMENT_VARIABLE} to a private ROM path."
        )

    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise RomValidationError(f"ROM file does not exist: {path}")
    return path


def fingerprint_rom(path: Path) -> RomFingerprint:
    sha1 = hashlib.sha1(usedforsecurity=False)
    sha256 = hashlib.sha256()

    with path.open("rb") as rom_file:
        header = rom_file.read(0x150)
        rom_file.seek(0)
        for chunk in iter(lambda: rom_file.read(1024 * 1024), b""):
            sha1.update(chunk)
            sha256.update(chunk)

    title_bytes = header[0x134:0x144]
    title = title_bytes.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
    return RomFingerprint(
        filename=path.name,
        title=title,
        size_bytes=path.stat().st_size,
        sha1=sha1.hexdigest(),
        sha256=sha256.hexdigest(),
    )


def verify_rom(
    path: Path,
    expected: SupportedRom = POKEMON_RED_US_REV_0,
) -> RomFingerprint:
    actual = fingerprint_rom(path)
    mismatches: list[str] = []

    if actual.title != expected.title:
        mismatches.append(f"title {actual.title!r} != {expected.title!r}")
    if actual.size_bytes != expected.size_bytes:
        mismatches.append(f"size {actual.size_bytes} != {expected.size_bytes}")
    if actual.sha1 != expected.sha1:
        mismatches.append(f"SHA-1 {actual.sha1} != {expected.sha1}")
    if actual.sha256 != expected.sha256:
        mismatches.append(f"SHA-256 {actual.sha256} != {expected.sha256}")

    if mismatches:
        raise RomValidationError(
            "Unsupported ROM revision. Refusing to continue because memory addresses and save "
            f"states are revision-specific: {'; '.join(mismatches)}"
        )
    return actual
