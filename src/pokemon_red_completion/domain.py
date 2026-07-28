"""ROM-independent semantic state shared by planners and specialists.

The completion agent should reason about game meaning rather than emulator
implementation details.  This module deliberately contains no ROM paths, memory
addresses, screenshots, save states, or controller timing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TypeAlias

Fact: TypeAlias = str


class GameMode(StrEnum):
    """Mutually exclusive interaction modes exposed to the high-level planner."""

    POWERED_OFF = "powered_off"
    BOOTING = "booting"
    OVERWORLD = "overworld"
    DIALOGUE = "dialogue"
    MENU = "menu"
    BATTLE = "battle"
    SCRIPTED_EVENT = "scripted_event"
    TRANSITION = "transition"
    HALL_OF_FAME = "hall_of_fame"


def _normalized_facts(facts: Iterable[Fact]) -> frozenset[Fact]:
    normalized = frozenset(facts)
    invalid = sorted(repr(fact) for fact in normalized if not isinstance(fact, str) or not fact)
    if invalid:
        raise ValueError(f"facts must be non-empty strings: {', '.join(invalid)}")
    return normalized


@dataclass(frozen=True, slots=True)
class GameState:
    """An immutable, public-safe snapshot of facts relevant to planning.

    ``facts`` are stable semantic assertions such as ``"badge:boulder"`` or
    ``"item:ss_ticket"``.  ``location`` is a public logical label such as
    ``"cerulean_city"``; it is not a filesystem path or a raw memory value.
    """

    mode: GameMode
    facts: frozenset[Fact] = field(default_factory=frozenset)
    location: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, GameMode):
            raise TypeError("mode must be a GameMode")
        object.__setattr__(self, "facts", _normalized_facts(self.facts))
        if self.location is not None and (
            not isinstance(self.location, str) or not self.location.strip()
        ):
            raise ValueError("location must be a non-empty semantic label or None")

    def has_all(self, required: Iterable[Fact]) -> bool:
        """Return whether every required semantic fact is currently true."""

        return _normalized_facts(required).issubset(self.facts)

    def with_facts(self, *facts: Fact) -> GameState:
        """Return a new state extended with facts, leaving this state unchanged."""

        return replace(self, facts=self.facts.union(_normalized_facts(facts)))

    def without_facts(self, *facts: Fact) -> GameState:
        """Return a new state with selected facts removed."""

        return replace(self, facts=self.facts.difference(_normalized_facts(facts)))
