from __future__ import annotations

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.referee import (
    CHAMPION_DEFEATED_FACT,
    CompletionReferee,
)
from pokemon_red_completion.route import HALL_OF_FAME_FACT


def test_referee_requires_event_fact_and_hall_of_fame_mode_concurrently() -> None:
    referee = CompletionReferee()

    adjacent = referee.inspect(
        GameState(
            GameMode.OVERWORLD,
            facts=frozenset({CHAMPION_DEFEATED_FACT, HALL_OF_FAME_FACT}),
        )
    )
    mode_only = referee.inspect(GameState(GameMode.HALL_OF_FAME))
    complete = referee.inspect(
        GameState(
            GameMode.HALL_OF_FAME,
            facts=frozenset({CHAMPION_DEFEATED_FACT, HALL_OF_FAME_FACT}),
        )
    )

    assert not adjacent.complete
    assert adjacent.missing == ("Hall-of-Fame mode/map",)
    assert not mode_only.complete
    assert complete.complete
    assert complete.missing == ()
