from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from pokemon_red_completion.constants import (
    POKEMON_RED_US_REV_0,
    SUPPORTED_ROMS,
    SupportedRom,
)

ROM_ENVIRONMENT_VARIABLE = "POKEMON_RED_ROM"

#: Where each title's private ROM path is supplied, keyed by title reference.
#:
#: A campaign runs more than one cartridge, so one variable cannot name them
#: all. Red keeps its original variable so every existing command and receipt
#: keeps working.
ROM_ENVIRONMENT_VARIABLES = {
    "red": ROM_ENVIRONMENT_VARIABLE,
    "blue": "POKEMON_BLUE_ROM",
}


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


def resolve_title_rom_path(title_ref: str, argument: str | Path | None = None) -> Path:
    """Find one title's private ROM, from its own environment variable.

    A campaign runs several cartridges at once, so a single variable cannot
    name them all. Red keeps ``POKEMON_RED_ROM`` so nothing that already works
    stops working.
    """

    if title_ref not in ROM_ENVIRONMENT_VARIABLES:
        known = ", ".join(sorted(ROM_ENVIRONMENT_VARIABLES))
        raise RomValidationError(f"unknown title {title_ref!r}; known titles are {known}")
    if argument is not None:
        return resolve_rom_path(argument)
    variable = ROM_ENVIRONMENT_VARIABLES[title_ref]
    raw_path = os.environ.get(variable)
    if not raw_path:
        raise RomValidationError(f"set {variable} to the private {title_ref} ROM path")
    return resolve_rom_path(raw_path)


def supported_rom_for(title_ref: str) -> SupportedRom:
    """The identity this repository will accept for a title."""

    try:
        return SUPPORTED_ROMS[title_ref]
    except KeyError:
        known = ", ".join(sorted(SUPPORTED_ROMS))
        raise RomValidationError(f"unknown title {title_ref!r}; known titles are {known}") from None


def fingerprint_rom(path: Path) -> RomFingerprint:
    return fingerprint_rom_bytes(path.read_bytes(), filename=path.name)


def fingerprint_rom_bytes(
    payload: bytes,
    *,
    filename: str = "<private>",
) -> RomFingerprint:
    """Fingerprint the exact immutable bytes that will be passed to an emulator."""
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")

    sha1 = hashlib.sha1(payload, usedforsecurity=False)
    sha256 = hashlib.sha256(payload)
    header = payload[:0x150]
    title_bytes = header[0x134:0x144]
    title = title_bytes.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
    return RomFingerprint(
        filename=filename,
        title=title,
        size_bytes=len(payload),
        sha1=sha1.hexdigest(),
        sha256=sha256.hexdigest(),
    )


def verify_rom_fingerprint(
    actual: RomFingerprint,
    expected: SupportedRom = POKEMON_RED_US_REV_0,
) -> RomFingerprint:
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


def verify_rom_bytes(
    payload: bytes,
    expected: SupportedRom = POKEMON_RED_US_REV_0,
    *,
    filename: str = "<private>",
) -> RomFingerprint:
    return verify_rom_fingerprint(
        fingerprint_rom_bytes(payload, filename=filename),
        expected,
    )


def verify_rom(
    path: Path,
    expected: SupportedRom = POKEMON_RED_US_REV_0,
) -> RomFingerprint:
    return verify_rom_bytes(path.read_bytes(), expected, filename=path.name)
