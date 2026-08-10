from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from pokemon_red_completion.gen1_route_runtime import (
    Gen1TraversalObserver,
    Gen1WildFleeHandler,
)
from pokemon_red_completion.observation import (
    InputReadiness,
    MapId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.route_1_wild import Route1WildFleeEvidence
from pokemon_red_completion.route_executor import RouteExecutionError, TraversalSnapshot


@dataclass
class FakeReader:
    raw: RawGameState
    ready: bool = True

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(joy_ignore=0 if self.ready else 1, simulated_joypad_index=0)


@dataclass
class FakeExecutor:
    def execute(self, action: object) -> object:
        return action


def raw(*, battle_state: int = 0) -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.ROUTE_1,
        player_x=7,
        player_y=8,
        party_count=1,
        battle_state=battle_state,
    )


def reader_as_real(fake: FakeReader) -> PokemonRedStateReader:
    return cast(PokemonRedStateReader, fake)


def test_observer_keeps_coordinates_game_neutral_and_marks_wild_battle() -> None:
    fake = FakeReader(raw(battle_state=1))

    observed = Gen1TraversalObserver(reader_as_real(fake)).observe()

    assert observed == TraversalSnapshot(
        map_id=MapId.ROUTE_1,
        at=(8, 7),
        ready=False,
        interruption="wild_battle",
    )


def test_observer_requires_a_started_coordinate_state() -> None:
    fake = FakeReader(
        RawGameState(False, None, None, None, None, None),
    )

    with pytest.raises(RouteExecutionError, match="state is unavailable"):
        Gen1TraversalObserver(reader_as_real(fake)).observe()


def test_nonwild_battles_are_typed_but_not_dismissed() -> None:
    fake = FakeReader(raw(battle_state=2))
    observer = Gen1TraversalObserver(reader_as_real(fake))
    interruption = observer.observe()
    handler = Gen1WildFleeHandler(
        cast(object, FakeExecutor()),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        stabilization_frames=24,
    )

    assert interruption.interruption == "battle:2"
    with pytest.raises(RouteExecutionError, match="cannot dismiss"):
        handler.handle(interruption)


def test_wild_handler_publishes_the_existing_authenticated_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeReader(raw(battle_state=1))
    evidence = Route1WildFleeEvidence(
        initial_battle_state=1,
        final_battle_state=0,
        battle_result=2,
        expected_map_id=MapId.ROUTE_1,
        map_id=MapId.ROUTE_1,
        player_x=7,
        player_y=8,
        enemy_species_id=16,
        enemy_level=3,
        initial_hp=20,
        final_hp=20,
        maximum_hp_preserved=True,
        party_preserved=True,
        level_preserved=True,
        pp_preserved=True,
        status_preserved=True,
        control_ready=True,
        run_attempts=1,
        stabilization_frames=24,
    )

    def fake_flee(*args: object, **kwargs: object) -> Route1WildFleeEvidence:
        return evidence

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_route_runtime.flee_wild",
        fake_flee,
    )
    handler = Gen1WildFleeHandler(
        cast(object, FakeExecutor()),  # type: ignore[arg-type]
        reader_as_real(fake),
        maximum_flees=1,
        stabilization_frames=24,
    )

    receipt = handler.handle(
        TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "wild_battle")
    )

    assert receipt.kind == "wild_battle"
    assert receipt.resumed_at == (8, 7)
    assert receipt.details["verified"] is True
    assert handler.evidence == [evidence]
    with pytest.raises(RouteExecutionError, match="flee budget"):
        handler.handle(
            TraversalSnapshot(MapId.ROUTE_1, (8, 7), False, "wild_battle")
        )
