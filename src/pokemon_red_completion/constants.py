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

SUPPORTED_BUTTONS = frozenset({"up", "down", "left", "right", "a", "b", "start", "select"})
