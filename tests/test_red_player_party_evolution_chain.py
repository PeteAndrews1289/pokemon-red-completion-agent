"""Whole player segments admit earned chains, never weaker per-battle custody."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard
from pokemon_red_completion.red_trainer_evolution import RedTrainerEvolutionGuard

EDGES = frozenset({(112, 113, 7), (113, 114, 10), (177, 179, 16), (179, 180, 36)})


def guard_fixture(old=None, new=None, refs=("same",), *, boxes=(), loan=False, edges=EDGES):
    old = old or PartyMemberObservation(1, 112, 6, 21, 21, experience=253)
    new = new or replace(old, species_id=114, level=10, experience=1034)
    reader = N(read=lambda: PartyObservation((new,)), preparation_specimen_refs=lambda: refs)
    census = N(read_box_specimen_identities=lambda: boxes) if boxes else None
    return RedPlayerPartyGuard(
        reader,
        PartyObservation((old,)),
        ("same",),
        edges,
        census,
        frozenset({"same"}) if loan else frozenset(),
    )


@pytest.mark.parametrize(
    "old_species,old_level,new_species,new_level",
    [
        (112, 6, 114, 10),
        (177, 5, 180, 36),
        (112, 6, 113, 9),
    ],
)
def test_preserves_original_identity_and_observation_across_earned_level_chain(
    old_species, old_level, new_species, new_level
):
    old = PartyMemberObservation(1, old_species, old_level, 21, 21, experience=100)
    new = replace(old, species_id=new_species, level=new_level, experience=50000)
    guard = guard_fixture(old, new)
    guard.verify()
    guard.verify()
    assert guard.before.members == (old,) and guard.refs == ("same",)
    assert guard.reader.read().members == (new,)


@pytest.mark.parametrize(
    "fault",
    [
        "xp_none",
        "xp_regression",
        "xp_unchanged",
        "level_regression",
        "level_unchanged",
        "final_threshold",
        "intermediate_threshold",
        "missing_edge",
        "wrong_species",
        "wrong_ref",
        "missing_ref",
        "cycle",
    ],
)
def test_chain_does_not_relax_identity_progress_or_cartridge_thresholds(fault):
    old = PartyMemberObservation(1, 112, 6, 21, 21, experience=253)
    new = replace(old, species_id=114, level=10, experience=1034)
    edges, refs = EDGES, ("same",)
    if fault == "xp_none":
        new = replace(new, experience=None)
    elif fault == "xp_regression":
        new = replace(new, experience=252)
    elif fault == "xp_unchanged":
        new = replace(new, experience=253)
    elif fault == "level_regression":
        new = replace(new, level=5)
    elif fault == "level_unchanged":
        new = replace(new, level=6)
    elif fault == "final_threshold":
        new = replace(new, level=9)
    elif fault == "intermediate_threshold":
        edges = frozenset({(112, 113, 20), (113, 114, 10)})
    elif fault == "missing_edge":
        edges = frozenset({(113, 114, 10)})
    elif fault == "wrong_species":
        new = replace(new, species_id=15)
    elif fault == "wrong_ref":
        refs = ("other",)
    elif fault == "missing_ref":
        refs = ()
    else:
        edges = frozenset({(112, 113, 7), (113, 112, 8)})
    with pytest.raises(ValueError):
        guard_fixture(old, new, refs, edges=edges).verify()


@pytest.mark.parametrize("species,xp,level", [(114, 1034, 10), (114, 252, 10), (114, 1034, 9)])
def test_transitive_box_fingerprint_collision_is_not_silently_ignored(species, xp, level):
    box = N(preparation_ref="same", species_id=species, experience=xp, level=level)
    with pytest.raises(ValueError, match="lost or duplicated"):
        guard_fixture(boxes=(box,)).verify()


def test_unrelated_box_fingerprint_stays_unrelated():
    box = N(preparation_ref="same", species_id=15, experience=1034, level=10)
    guard_fixture(boxes=(box,)).verify()


@pytest.mark.parametrize("fault", [None, "xp", "threshold", "missing", "unapproved"])
def test_declared_box_loan_checks_transitive_progress_without_expanding_permission(fault):
    old = PartyMemberObservation(1, 112, 6, 21, 21, experience=253)
    box = N(preparation_ref="same", species_id=114, experience=1034, level=10)
    if fault == "xp":
        box.experience = 252
    if fault == "threshold":
        box.level = 9
    reader = N(read=lambda: PartyObservation(()), preparation_specimen_refs=lambda: ())
    storage = N(read_box_specimen_identities=lambda: () if fault == "missing" else (box,))
    guard = RedPlayerPartyGuard(
        reader,
        PartyObservation((old,)),
        ("same",),
        EDGES,
        storage,
        frozenset() if fault == "unapproved" else frozenset({"same"}),
    )
    if fault:
        with pytest.raises(ValueError):
            guard.verify()
    else:
        guard.verify()
        with pytest.raises(ValueError, match="not been restored"):
            guard.verify_active_roster_restored()


def test_one_battle_still_cannot_claim_two_evolutions():
    guard = guard_fixture()
    initial = N(party_count=1, party_species_ids=(112,), party_levels=(6,))
    current = N(battle_state=0, party_count=1, party_species_ids=(114,), party_levels=(10,))
    battle = RedTrainerEvolutionGuard(guard.reader, guard.before, guard.refs, EDGES)
    assert not battle.matches(initial, current)
    guard.verify()
