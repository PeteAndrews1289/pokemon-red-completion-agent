from __future__ import annotations

from dataclasses import dataclass

import pytest

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.observation import MapId, RawGameState
from pokemon_red_completion.red_player_observer import (
    CapturedPokemonRedObserver,
    ResumedStateError,
)
from pokemon_red_completion.route import COMPLETION_QUEST


def _envelope(*objective_ids: str) -> CapturedProgressEnvelope:
    return CapturedProgressEnvelope(
        state_sha256="a" * 64,
        checkpoint_id="celadon_stable",
        checkpoint_label="Healed safely in Celadon",
        checkpoints_completed=124,
        checkpoints_total=312,
        verified_objective_ids=objective_ids,
    )


@dataclass
class _Reader:
    raw: RawGameState

    def read(self) -> RawGameState:
        return self.raw


def _celadon_raw() -> RawGameState:
    return RawGameState(
        game_started=True,
        map_id=MapId.CELADON_POKECENTER,
        player_x=3,
        player_y=3,
        party_count=1,
        battle_state=0,
    )


def test_resumed_observer_preserves_transient_verified_location_facts() -> None:
    prefix = (
        "power_on",
        "begin_adventure",
        "choose_starter",
        "receive_pokedex",
        "reach_pewter",
        "defeat_brock",
        "reach_cerulean",
        "help_bill",
        "defeat_misty",
        "reach_vermilion",
        "obtain_cut",
        "defeat_surge",
        "reach_lavender",
    )
    observer = CapturedPokemonRedObserver(
        _Reader(_celadon_raw()), COMPLETION_QUEST, _envelope(*prefix)
    )

    state = observer.observe()

    assert "location:lavender_town" in state.facts
    assert "location:celadon_city" in state.facts
    assert [item.id for item in COMPLETION_QUEST.available_objectives(state)] == [
        "clear_rocket_hideout",
        "defeat_erika",
        "reach_saffron",
    ]


def test_resumed_observer_rejects_unknown_or_out_of_order_progress() -> None:
    reader = _Reader(_celadon_raw())
    with pytest.raises(ResumedStateError, match="unknown"):
        CapturedPokemonRedObserver(reader, COMPLETION_QUEST, _envelope("not_real"))
    with pytest.raises(ResumedStateError, match="prerequisites"):
        CapturedPokemonRedObserver(reader, COMPLETION_QUEST, _envelope("defeat_brock"))
