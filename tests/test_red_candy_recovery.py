from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import red_candy_recovery as module
from pokemon_red_completion.collection import (
    CollectionLocation,
    CollectionObservation,
    LivingSpecimen,
)
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.red_candy_recovery import RedCandyRecoveryError, verify_candy_collection
from pokemon_red_completion.red_candy_recovery import verify_candy_effect as verify_candy
from pokemon_red_completion.red_party import party_observation_from_raw


def pair():
    before = RawGameState(
        True,
        245,
        5,
        3,
        2,
        0,
        player_money=19217,
        event_flags=bytes(319),
        badge_bits=255,
        bag_items=((40, 1), (19, 7)),
        bag_item_ids=(40, 19),
        party_species_ids=(28, 64),
        party_levels=(54, 45),
        party_hp=(38, 0),
        party_max_hp=(169, 118),
        party_stats=((122, 135, 113, 128), (85, 69, 72, 71)),
        party_status=(0, 0),
        party_moves=((44, 70, 58, 57), (64, 28, 15, 19)),
        party_pp=((25, 13, 10, 0), (35, 15, 30, 15)),
        first_party_level=54,
        first_party_hp=38,
        first_party_max_hp=169,
        first_party_status=0,
        first_party_moves=(44, 70, 58, 57),
        first_party_pp=(25, 13, 10, 0),
    )
    after = replace(
        before,
        bag_items=((19, 7),),
        bag_item_ids=(19,),
        party_levels=(54, 46),
        party_hp=(38, 2),
        party_max_hp=(169, 120),
        party_stats=((122, 135, 113, 128), (87, 70, 74, 72)),
    )
    return before, after


def test_exact_effect():
    before, after = pair()
    verify_candy(before, after, 1)


@pytest.mark.parametrize(
    "change",
    [
        {"party_hp": (38, 120)},
        {"party_levels": (54, 47)},
        {"party_hp": (39, 2)},
        {"player_money": 1},
        {"bag_items": ((19, 6),)},
        {"party_species_ids": (28, 104)},
        {"party_pp": ((25, 13, 10, 1), (35, 15, 30, 15))},
        {"event_flags": bytes(318) + b"\x01"},
    ],
)
def test_wrong_effect(change):
    before, after = pair()
    with pytest.raises(RedCandyRecoveryError):
        verify_candy(before, replace(after, **change), 1)


def collection():
    return CollectionObservation(
        frozenset({"pokemon:national:009", "pokemon:national:083"}),
        (
            LivingSpecimen("pokemon:national:009", 54, CollectionLocation.PARTY, slot_index=0),
            LivingSpecimen("pokemon:national:083", 45, CollectionLocation.PARTY, slot_index=1),
            LivingSpecimen("pokemon:national:025", 3, CollectionLocation.BOX),
        ),
        2,
        6,
        (1,),
        0,
        20,
    )


def test_intended_level_up_preserves_collection_except_target_level():
    before = collection()
    after = replace(
        before,
        specimens=(
            before.specimens[0],
            replace(before.specimens[1], level=46),
            before.specimens[2],
        ),
    )
    verify_candy_collection(before, after, 1)
    with pytest.raises(RedCandyRecoveryError):
        verify_candy_collection(before, before, 1)
    with pytest.raises(RedCandyRecoveryError):
        verify_candy_collection(before, after, 0)
    for altered in (
        replace(after, owned_species=after.owned_species | {"pokemon:national:025"}),
        replace(after, specimens=(replace(after.specimens[0], level=55), *after.specimens[1:])),
        replace(after, specimens=(*after.specimens[:2], replace(after.specimens[2], level=4))),
        replace(
            after,
            specimens=(
                after.specimens[0],
                replace(after.specimens[1], level=47),
                after.specimens[2],
            ),
        ),
    ):
        with pytest.raises(RedCandyRecoveryError):
            verify_candy_collection(before, altered, 1)


def runtime(monkeypatch, fault=None):
    before, after = pair()
    initial_collection = collection()
    final_collection = replace(
        initial_collection,
        specimens=(
            initial_collection.specimens[0],
            replace(initial_collection.specimens[1], level=46),
            initial_collection.specimens[2],
        ),
    )
    state = NS(raw=before)
    emulator = NS(pressed_buttons=(), frame_count=0)
    actions = NS(actions_executed=0)
    calls = []
    species = NS(national_number=83, level_up_moves=(), experience_at_level=lambda level: 97336)
    monkeypatch.setattr(
        module, "RedPracticeCartridge", lambda rom: NS(species=lambda index: species)
    )
    monkeypatch.setattr(module, "evolution_graph", lambda rom: {})
    reader = NS(read=lambda: state.raw, read_bottom_dialogue_box_visible=lambda: False)

    def observe():
        updated = state.raw is not before
        coll = final_collection if updated else initial_collection
        if updated and fault == "collection":
            coll = initial_collection
        return NS(raw=state.raw, input_ready=True, collection_observation=coll, game_state="same")

    adapter = NS(observe=observe, graph=NS(completed_ids=lambda state: ("same",)))

    def party():
        members = party_observation_from_raw(state.raw).members
        return NS(
            members=tuple(
                replace(
                    m,
                    experience=(97336 if state.raw is not before else 95814) if i == 1 else 150000,
                )
                for i, m in enumerate(members)
            )
        )

    monkeypatch.setattr(
        module,
        "PokemonRedPartyReader",
        lambda em: NS(read=party, preparation_specimen_refs=lambda: ("one", "two")),
    )
    monkeypatch.setattr(module, "_open_bag", lambda *args: calls.append("bag"))
    monkeypatch.setattr(
        module, "_select_bag_item", lambda a, e, item, t: calls.append(("item", item))
    )
    monkeypatch.setattr(
        module, "_select_cursor", lambda a, e, index, t: calls.append(("target", index))
    )
    monkeypatch.setattr(module, "_close_menus", lambda *args: calls.append("close"))

    def pulse(*args, **kwargs):
        assert state.raw is before, "confirmation after item consumption"
        calls.append("confirm")
        actions.actions_executed += 1
        emulator.frame_count += 24
        if ("target", 1) in calls and fault != "no_consumption":
            state.raw = replace(after, bag_items=((19, 6),)) if fault == "inventory" else after

    monkeypatch.setattr(module, "_pulse", pulse)
    return state, species, calls, (actions, reader, emulator, adapter, b"fake", 1)


def test_native_sequence_checks_level_and_stops_confirming_after_consumption(monkeypatch):
    state, _, calls, args = runtime(monkeypatch)
    receipt = module.use_candy_revival(*args)
    assert receipt["after_level"] == 46 and receipt["experience"] == 97336
    assert calls == ["bag", ("item", 40), "confirm", "confirm", ("target", 1), "confirm", "close"]
    # Recalling the skill on an already-used target must fail before input.
    prior = list(calls)
    with pytest.raises(RedCandyRecoveryError):
        module.use_candy_revival(*args)
    assert calls == prior


@pytest.mark.parametrize("fault", ["inventory", "collection", "no_consumption"])
def test_native_failure_is_not_hidden_or_retried(monkeypatch, fault):
    _, _, calls, args = runtime(monkeypatch, fault)
    with pytest.raises(RedCandyRecoveryError):
        module.use_candy_revival(*args)
    assert calls.count("confirm") <= 27


@pytest.mark.parametrize("fault", ["move", "evolution", "held", "not_fainted", "no_item"])
def test_unsupported_candy_boundary_rejects_before_inputs(monkeypatch, fault):
    state, species, calls, args = runtime(monkeypatch)
    if fault == "move":
        species.level_up_moves = ((46, 1),)
    elif fault == "evolution":
        monkeypatch.setattr(module, "evolution_graph", lambda rom: {83: ("evolution",)})
    elif fault == "held":
        args[2].pressed_buttons = ("a",)
    elif fault == "not_fainted":
        state.raw = replace(state.raw, party_hp=(38, 1))
    else:
        state.raw = replace(state.raw, bag_items=((19, 7),))
    with pytest.raises(RedCandyRecoveryError):
        module.use_candy_revival(*args)
    assert not calls
