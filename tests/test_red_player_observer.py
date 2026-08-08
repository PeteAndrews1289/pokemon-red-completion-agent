from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from pokemon_red_completion.captured_progress import CapturedProgressEnvelope
from pokemon_red_completion.observation import ItemId, MapId, RawGameState
from pokemon_red_completion.red_player_observer import (
    CapturedPokemonRedObserver,
    LivePokemonRedObserver,
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


def test_resumed_observer_does_not_latch_transient_inventory_affordances() -> None:
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
    reader = _Reader(
        replace(_celadon_raw(), bag_item_ids=(ItemId.GOLD_TEETH,))
    )
    observer = CapturedPokemonRedObserver(reader, COMPLETION_QUEST, _envelope(*prefix))

    assert "item:gold_teeth" in observer.observe().facts

    reader.raw = _celadon_raw()
    state = observer.observe()

    assert "item:gold_teeth" not in state.facts
    assert "location:celadon_city" in state.facts


def test_live_observer_latches_only_consistent_verified_quest_facts() -> None:
    reader = _Reader(replace(_celadon_raw(), game_started=False, map_id=None))
    observer = LivePokemonRedObserver(reader, COMPLETION_QUEST)

    assert observer.observe().facts == frozenset()
    with pytest.raises(ResumedStateError, match="prerequisites"):
        observer.latch_verified_facts(frozenset({"badge:boulder"}))
    with pytest.raises(ResumedStateError, match="outside the quest contract"):
        observer.latch_verified_facts(frozenset({"private:route_hint"}))

    early_ids = (
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
        "reach_celadon",
    )
    observer.latch_verified_facts(
        frozenset(
            fact
            for objective_id in early_ids
            for fact in COMPLETION_QUEST.objective(objective_id).completion_facts
        )
    )
    reader.raw = _celadon_raw()

    state = observer.observe()

    assert set(early_ids).issubset(COMPLETION_QUEST.completed_ids(state))
    assert observer.public_dict()["latched_fact_count"] == len(early_ids)
