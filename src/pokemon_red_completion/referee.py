from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.route import HALL_OF_FAME_FACT

CHAMPION_DEFEATED_FACT = "league:champion_defeated"


@dataclass(frozen=True, slots=True)
class CompletionEvidence:
    champion_event: bool
    hall_of_fame_fact: bool
    hall_of_fame_mode: bool

    @property
    def complete(self) -> bool:
        return self.champion_event and self.hall_of_fame_fact and self.hall_of_fame_mode

    @property
    def missing(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.champion_event:
            missing.append("Champion-defeated event")
        if not self.hall_of_fame_fact:
            missing.append("Hall-of-Fame semantic fact")
        if not self.hall_of_fame_mode:
            missing.append("Hall-of-Fame mode/map")
        return tuple(missing)


class CompletionReferee:
    """Independently verify completion without choosing or replacing actor actions."""

    def inspect(self, state: GameState) -> CompletionEvidence:
        return CompletionEvidence(
            champion_event=CHAMPION_DEFEATED_FACT in state.facts,
            hall_of_fame_fact=HALL_OF_FAME_FACT in state.facts,
            hall_of_fame_mode=state.mode is GameMode.HALL_OF_FAME,
        )
