"""The teacher chapter's entry gate is narrower than its objective prerequisites."""
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.observation import OpeningPhase
from pokemon_red_completion.red_early_game_skill import (
    EarlyGameCompositeError,
    build_red_oaks_errand_skill,
)


def setup():
    raw = N(game_started=True, battle_state=0, party_hp=(20,))
    opening = N(phase=OpeningPhase.STARTER_OBTAINED, all_controls_allowed=True,
                first_party_species=177)
    errand = N(battled_rival=False, got_oaks_parcel=False, oak_got_parcel=False,
               got_pokedex=False, parcel_in_bag=False)
    ready = N(ready=True)
    ui = N(dialogue=False)
    em = N(pressed_buttons=())
    reader = N(read=lambda: raw, read_opening_control_state=lambda _: opening,
               read_oaks_errand_state=lambda _: errand, read_input_readiness=lambda: ready,
               read_bottom_dialogue_box_visible=lambda: ui.dialogue)
    skill = build_red_oaks_errand_skill(em, reader, object(), object())
    state = GameState(GameMode.OVERWORLD, location="oaks_lab", facts=skill.required_facts)
    return skill, state, dict(raw=raw, opening=opening, errand=errand,
                             ready=ready, ui=ui, em=em)


def test_exact_original_opening_remains_available():
    skill, state, _ = setup()
    assert skill.availability(state).executable


@pytest.mark.parametrize("owner,field,value", [
    ("raw", "game_started", False), ("raw", "battle_state", 2),
    ("raw", "party_hp", (0,)), ("raw", "party_hp", ()),
    ("opening", "phase", OpeningPhase.UNKNOWN),
    ("opening", "all_controls_allowed", False),
    ("opening", "first_party_species", 153),
    *(('errand', name, True) for name in (
        'battled_rival','got_oaks_parcel','oak_got_parcel','got_pokedex','parcel_in_bag')),
    ("ready", "ready", False), ("ui", "dialogue", True),
    ("em", "pressed_buttons", ("a",)),
])
def test_native_prerequisite_change_masks_and_prevents_stale_execution(owner, field, value):
    skill, state, objects = setup()
    assert skill.availability(state).executable
    setattr(objects[owner], field, value)
    assert not skill.availability(state).executable
    # Executor/observer are deliberately unusable: no input or progress latch is allowed.
    with pytest.raises(EarlyGameCompositeError, match="absent or stale"):
        skill.execute()


def test_missing_semantic_prerequisites_still_block_a_native_ready_entry():
    skill, _, _ = setup()
    assert not skill.availability(GameState(GameMode.OVERWORLD, location="oaks_lab")).executable
