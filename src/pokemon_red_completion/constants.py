from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupportedRom:
    """Identity of one explicitly supported, user-supplied ROM revision."""

    title: str
    size_bytes: int
    sha1: str
    sha256: str


POKEMON_RED_US_REV_0 = SupportedRom(
    title="POKEMON RED",
    size_bytes=1_048_576,
    sha1="ea9bcae617fdf159b045185467ae58b2e4a48b9a",
    sha256="5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b",
)

#: Measured from the owner's cartridge on 2026-08-09, not transcribed from a
#: reference list. A living Pokedex needs a second version: ten species are
#: version-exclusive to Blue and no amount of Red planning reaches them.
#:
#: Red and Blue share one engine, so the RAM symbols the adapter uses are
#: expected to hold here unchanged. "Expected" is doing real work in that
#: sentence -- it is a hypothesis this repository can now test rather than a
#: fact it may assume.
POKEMON_BLUE_US_REV_0 = SupportedRom(
    title="POKEMON BLUE",
    size_bytes=1_048_576,
    sha1="d7037c83e1ae5b39bde3c30787637ba1d4c48ce2",
    sha256="2a951313c2640e8c2cb21f25d1db019ae6245d9c7121f754fa61afd7bee6452d",
)

#: Every cartridge this repository will knowingly load, keyed by title
#: reference. A campaign vessel names one of these.
SUPPORTED_ROMS = {
    "red": POKEMON_RED_US_REV_0,
    "blue": POKEMON_BLUE_US_REV_0,
}

SUPPORTED_BUTTONS = frozenset({"up", "down", "left", "right", "a", "b", "start", "select"})
