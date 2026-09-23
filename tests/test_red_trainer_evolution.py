from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_trainer_evolution import RedTrainerEvolutionGuard
from pokemon_red_completion.red_trainer_funding_battle import (
    TrainerFundingBattleError,
    _check_postbattle_fatal,
)


def member(species=59, level=25, xp=15000):
    return PartyMemberObservation(1, species, level, 30, 50, experience=xp)


@pytest.mark.parametrize("old_species,new_species,threshold", [(59, 118, 26), (177, 178, 16)])
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "xp",
        "level",
        "early",
        "wrong_species",
        "identity",
        "reorder",
        "raw_mismatch",
        "during_battle",
        "wrong_origin",
    ],
)
def test_only_observed_same_specimen_level_evolution_passes(
    old_species, new_species, threshold, fault
):
    old = member(old_species, threshold - 1)
    new = member(
        999 if fault == "wrong_species" else new_species,
        threshold - 1 if fault in {"level", "early"} else threshold,
        15000 if fault == "xp" else 16000,
    )
    before = PartyObservation((old,))
    after = PartyObservation((new,))
    reader = NS(
        read=lambda: after,
        preparation_specimen_refs=lambda: (
            "other" if fault in {"identity", "reorder"} else "same",
        ),
    )
    guard = RedTrainerEvolutionGuard(
        reader, before, ("same",), frozenset({(old_species, new_species, threshold)})
    )
    initial = NS(
        party_count=1,
        party_species_ids=(0 if fault == "wrong_origin" else old_species,),
        party_levels=before.levels,
    )
    current = NS(
        party_count=1,
        party_species_ids=(0,) if fault == "raw_mismatch" else after.species_ids(),
        party_levels=after.levels,
        battle_state=2 if fault == "during_battle" else 0,
    )
    assert guard.matches(initial, current) is (fault is None)


def test_unchanged_species_allowed_but_xp_regression_is_not():
    before = PartyObservation((member(),))
    after = [before]
    reader = NS(read=lambda: after[0], preparation_specimen_refs=lambda: ("same",))
    guard = RedTrainerEvolutionGuard(reader, before, ("same",), frozenset())
    raw = NS(
        party_count=1,
        party_species_ids=before.species_ids(),
        party_levels=before.levels,
        battle_state=0,
    )
    assert guard.matches(raw, raw)
    after[0] = PartyObservation((replace(member(), experience=1),))
    assert not guard.matches(raw, raw)


def test_cartridge_projection_excludes_stone_and_trade(monkeypatch):
    import pokemon_red_completion.red_trainer_evolution as module
    from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod

    before = PartyObservation((member(),))
    reader = NS(read=lambda: before, preparation_specimen_refs=lambda: ("same",))
    monkeypatch.setattr(module, "PokemonRedPartyReader", lambda _: reader)
    monkeypatch.setattr(module, "internal_to_dex", lambda _: {59: 50, 118: 51, 100: 52, 101: 53})
    monkeypatch.setattr(
        module,
        "evolution_graph",
        lambda _: {
            50: (
                Evolution(50, 51, EvolutionMethod.LEVEL, 26),
                Evolution(50, 52, EvolutionMethod.STONE, 10),
                Evolution(50, 53, EvolutionMethod.TRADE, None),
            )
        },
    )
    guard = RedTrainerEvolutionGuard.from_rom(b"", None)
    assert guard.level_edges == frozenset({(59, 118, 26)})


def test_default_funding_still_rejects_evolution(monkeypatch):
    import pokemon_red_completion.red_trainer_funding_battle as funding

    before = PartyObservation((member(),))
    after = PartyObservation((member(118, 26, 16000),))
    guard = RedTrainerEvolutionGuard(
        NS(read=lambda: after, preparation_specimen_refs=lambda: ("same",)),
        before,
        ("same",),
        frozenset({(59, 118, 26)}),
    )
    initial = NS(party_count=1, party_species_ids=(59,), party_levels=(25,))
    current = NS(
        party_count=1,
        party_species_ids=(118,),
        party_levels=(26,),
        battle_state=0,
        battle_result=0,
        map_id=17,
        player_y=3,
        player_x=4,
        party_hp=(30,),
    )
    target = NS(trainer=NS(map_id=17), approach=NS(terminal_at=(3, 4)))
    monkeypatch.setattr(funding, "trainer_bag_within_budget", lambda *a: True)
    with pytest.raises(TrainerFundingBattleError, match="species changed"):
        _check_postbattle_fatal(current, initial, target)
    _check_postbattle_fatal(current, initial, target, evolution_guard=guard)
