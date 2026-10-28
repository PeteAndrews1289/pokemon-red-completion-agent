from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.collection import CollectionLocation, LivingSpecimen
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_player_party_guard import (
    RedPlayerPartyGuard,
    RetainedPartyGoalStateAdapter,
    retained_party_slot_is_depositable,
)


@pytest.mark.parametrize(
    "fault",
    [None, "missing", "duplicate", "swap", "xp", "level", "species", "threshold", "unearned"],
)
def test_retains_individuals_and_only_earned_evolution(fault):
    old = PartyMemberObservation(1, 177, 15, 30, 40, experience=3000)
    new = replace(old, species_id=179, level=16, experience=4000)
    ref = "a"
    if fault == "swap":
        ref = "b"
    if fault == "xp":
        new = replace(new, experience=2999)
    if fault == "level":
        new = replace(new, level=14)
    if fault == "species":
        new = replace(new, species_id=180)
    if fault == "threshold":
        new = replace(new, level=16)
    if fault == "unearned":
        new = replace(new, experience=3000)
    members, refs = (new,), (ref,)
    if fault == "missing":
        refs = ("other",)
    if fault == "duplicate":
        members, refs = (new, replace(new, slot=2)), (ref, ref)
    reader = N(read=lambda: PartyObservation(members), preparation_specimen_refs=lambda: refs)
    guard = RedPlayerPartyGuard(
        reader,
        PartyObservation((old,)),
        ("a",),
        frozenset({(177, 179, 17 if fault == "threshold" else 16)}),
    )
    if fault:
        with pytest.raises(ValueError):
            guard.verify()
    else:
        guard.verify()
        assert guard.before.members[0] == old


def test_reordering_and_new_capture_do_not_change_preserved_baseline():
    a = PartyMemberObservation(1, 177, 15, 30, 40, experience=3000)
    b = PartyMemberObservation(2, 165, 7, 20, 22, experience=350)
    reader = N(
        read=lambda: PartyObservation((replace(b, slot=1), replace(a, slot=2))),
        preparation_specimen_refs=lambda: ("new", "a"),
    )
    RedPlayerPartyGuard(reader, PartyObservation((a,)), ("a",), frozenset()).verify()


def test_continuation_evidence_is_native_guarded_and_does_not_grant_new_capture_coverage():
    old=PartyMemberObservation(1,177,15,30,40,experience=3000)
    current=PartyObservation((old,))
    refs=("retained",)
    reader=N(read=lambda:current,preparation_specimen_refs=lambda:refs)
    guard=RedPlayerPartyGuard(reader,current,refs,frozenset({(177,179,16)}))
    collection=N(specimens=(LivingSpecimen("pokemon:national:007",15,CollectionLocation.PARTY),))
    before=guard.continuation_evidence(collection)
    current=PartyObservation((replace(old,species_id=179,level=16,experience=4000),))
    collection=N(specimens=(LivingSpecimen("pokemon:national:008",16,CollectionLocation.PARTY),))
    after=guard.continuation_evidence(collection)
    assert before["guard_sha256"] == after["guard_sha256"]
    assert after["individuals"]["retained"] == dict(
        species_ref="pokemon:national:008", level=16, experience=4000)
    refs=("retained","new")
    current=PartyObservation((current.members[0],replace(old,slot=2)))
    assert guard.continuation_evidence(collection) is None
    current=PartyObservation((replace(current.members[0],species_id=180),current.members[1]))
    with pytest.raises(ValueError,match="earned progress"):
        guard.continuation_evidence(collection)


def test_opt_in_adapter_requires_guard_before_observation():
    with pytest.raises(ValueError, match="identity guard"):
        RetainedPartyGoalStateAdapter(None, None, None).observe()


def test_storage_admission_preserves_reserved_identity_after_reordering():
    old = PartyMemberObservation(1, 177, 15, 30, 40, experience=3000)
    new = PartyMemberObservation(2, 165, 7, 20, 22, experience=350)
    reader = N(
        read=lambda: PartyObservation((replace(new, slot=1), replace(old, slot=2))),
        preparation_specimen_refs=lambda: ("new", "old"),
    )
    guard = RedPlayerPartyGuard(reader, PartyObservation((old,)), ("old",), frozenset())
    adapter = N(party_guard=guard)
    assert retained_party_slot_is_depositable(adapter, 1)
    assert not retained_party_slot_is_depositable(adapter, 2)
    assert retained_party_slot_is_depositable(N(), 2)
    guard.verify()


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "missing",
        "duplicate",
        "active_collision",
        "xp",
        "level",
        "species",
        "unapproved",
        "no_census",
        "bad_contract",
    ],
)
def test_explicit_temporary_loan_preserves_original_identity_and_progress(fault):
    old = PartyMemberObservation(1, 177, 15, 30, 40, experience=3000)
    loan = replace(old, slot=2, species_id=165, level=7, experience=350)
    boxed = N(preparation_ref="loan", species_id=165, level=7, experience=350)
    members, refs = (old,), ("role",)
    boxes = [boxed]
    if fault == "missing":
        boxes = []
    if fault == "duplicate":
        boxes.append(boxed)
    if fault == "active_collision":
        members, refs = (old, loan), ("role", "loan")
    if fault == "xp":
        boxed.experience = 349
    if fault == "level":
        boxed.level = 6
    if fault == "species":
        boxed.species_id = 166
    reader = N(read=lambda: PartyObservation(members), preparation_specimen_refs=lambda: refs)
    census = N(read_box_specimen_identities=lambda: tuple(boxes))
    guard = RedPlayerPartyGuard(
        reader,
        PartyObservation((old, loan)),
        ("role", "loan"),
        frozenset(),
        None if fault == "no_census" else census,
        frozenset({"other" if fault == "bad_contract" else "loan"})
        if fault != "unapproved"
        else frozenset(),
    )
    if fault:
        with pytest.raises(ValueError):
            guard.verify()
    else:
        guard.verify()
        with pytest.raises(ValueError, match="not been restored"):
            guard.verify_active_roster_restored()
        members, refs, boxes = (old, loan), ("role", "loan"), []
        guard.verify_active_roster_restored()
        assert not retained_party_slot_is_depositable(N(party_guard=guard), 1)
        assert retained_party_slot_is_depositable(N(party_guard=guard), 2)


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("boxed_species", [13, 177, 179])
def test_box_fingerprint_collision_requires_the_retained_species_line(active, boxed_species):
    old = PartyMemberObservation(1, 177, 15, 30, 40, experience=3000)
    guest = replace(old, species_id=166)
    reader = N(
        read=lambda: PartyObservation((old if active else guest,)),
        preparation_specimen_refs=lambda: ("retained" if active else "guest",),
    )
    boxed = N(preparation_ref="retained", species_id=boxed_species, level=16, experience=4000)
    guard = RedPlayerPartyGuard(reader, PartyObservation((old,)), ("retained",),
        frozenset({(177, 179, 16)}), N(read_box_specimen_identities=lambda: (boxed,)),
        frozenset({"retained"}))
    valid = (active and boxed_species == 13) or (not active and boxed_species in {177, 179})
    if valid:
        guard.verify()
    else:
        with pytest.raises(ValueError, match="lost or duplicated"):
            guard.verify()


def test_box_collision_resolution_does_not_waive_earned_evolution():
    old = PartyMemberObservation(1, 177, 15, 30, 40, experience=3000)
    reader = N(read=lambda: PartyObservation((replace(old, species_id=166),)),
        preparation_specimen_refs=lambda: ("guest",))
    boxed = N(preparation_ref="retained", species_id=179, level=16, experience=2999)
    guard = RedPlayerPartyGuard(reader, PartyObservation((old,)), ("retained",),
        frozenset({(177, 179, 16)}), N(read_box_specimen_identities=lambda: (boxed,)),
        frozenset({"retained"}))
    with pytest.raises(ValueError, match="earned progress"):
        guard.verify()


def test_loan_does_not_allow_nonloanable_role_to_leave_party():
    role = PartyMemberObservation(1, 177, 15, 30, 40, experience=3000)
    loan = replace(role, slot=2, species_id=165, level=7, experience=350)
    reader = N(
        read=lambda: PartyObservation((replace(loan, slot=1),)),
        preparation_specimen_refs=lambda: ("loan",),
    )
    storage = N(
        read_box_specimen_identities=lambda: (
            N(preparation_ref="role", species_id=177, level=15, experience=3000),
        )
    )
    guard = RedPlayerPartyGuard(
        reader,
        PartyObservation((role, loan)),
        ("role", "loan"),
        frozenset(),
        storage,
        frozenset({"loan"}),
    )
    with pytest.raises(ValueError):
        guard.verify()
