"""Observed PC loan eligibility, not strategy or native capture qualification."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_player_party_guard import (
    BIRD_CAPTURE_LOAN_POLICY,
    SNORLAX_CAPTURE_LOAN_POLICY,
    RedPlayerPartyGuard,
    observed_transport_safe_bird_guard,
    observed_transport_safe_snorlax_guard,
    validate_bird_capture_loan_declaration,
    validate_snorlax_capture_loan_declaration,
)


def setup(moves=None):
    moves = moves or ((57, 15, 70, 0), (148, 0, 0, 0), *((0, 0, 0, 0),) * 4)
    members = tuple(
        PartyMemberObservation(i + 1, i + 1, 17, 40, 40, experience=5000) for i in range(len(moves))
    )
    refs = tuple(f"original-{i}" for i in range(len(moves)))
    observed = N(refs=refs, moves=moves, members=members)
    reader = N(
        preparation_specimen_refs=lambda: observed.refs,
        read=lambda: PartyObservation(observed.members),
    )
    storage = N(read_box_specimen_identities=lambda: (), read=lambda: N(party_moves=observed.moves))
    guard = RedPlayerPartyGuard(
        reader, PartyObservation(members), refs, frozenset(), storage, frozenset({refs[0]})
    )
    runtime = N(adapter=N(party_guard=guard), reader=storage)
    return runtime, guard, observed


def bind(runtime, **kwargs):
    return observed_transport_safe_bird_guard(
        runtime,
        dict(BIRD_CAPTURE_LOAN_POLICY),
        helper_moves=kwargs.get("helper_moves", (105, 86, 94, 129)),
    )


def test_loan_keeps_sole_surf_cut_strength_and_flash_and_exact_original_return():
    runtime, original, _ = setup()
    scoped = bind(runtime)
    assert scoped.refs == original.refs and scoped.before == original.before
    assert scoped.loanable_refs == frozenset({"original-2"})
    assert original.loanable_refs == frozenset({"original-0"})
    assert runtime.adapter.party_guard is original


def test_duplicate_transport_capability_can_make_first_original_eligible():
    runtime, original, _ = setup(((57, 0, 0, 0), (57, 0, 0, 0)))
    assert bind(runtime).loanable_refs == frozenset({original.refs[0]})


@pytest.mark.parametrize("move", [91, 100, 135])
def test_non_hm_field_capabilities_are_preserved_too(move):
    runtime, _, _ = setup(((57, 15, 70, 0), (move, 0, 0, 0), *((0, 0, 0, 0),) * 4))
    assert bind(runtime).loanable_refs == frozenset({"original-2"})


def test_helper_can_preserve_observed_capability_but_no_species_shortcut():
    runtime, original, _ = setup(((57, 0, 0, 0), (15, 0, 0, 0)))
    assert bind(runtime) is None
    scoped = bind(runtime, helper_moves=(57, 105, 86, 94))
    assert scoped.loanable_refs == frozenset({original.refs[0]})


def test_party_reorder_binds_current_exact_identity_not_an_old_slot():
    runtime, _, observed = setup()
    permutation = (0, 1, 4, 2, 3, 5)
    observed.refs = tuple(observed.refs[i] for i in permutation)
    observed.moves = tuple(observed.moves[i] for i in permutation)
    observed.members = tuple(
        replace(observed.members[i], slot=j + 1) for j, i in enumerate(permutation)
    )
    assert bind(runtime).loanable_refs == frozenset({"original-4"})


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "unknown_moves",
        "short_moves",
        "boolean_move",
        "progress_lost",
        "duplicate",
        "helper_unknown",
    ],
)
def test_loan_rejects_missing_identity_unknown_moves_and_lost_progress(fault):
    runtime, _, observed = setup()
    helper = (105, 86, 94, 129)
    if fault == "missing":
        observed.refs = observed.refs[:-1]
        observed.members = observed.members[:-1]
    elif fault == "unknown_moves":
        observed.moves = None
    elif fault == "short_moves":
        observed.moves = ((57,), *observed.moves[1:])
    elif fault == "boolean_move":
        observed.moves = ((True, 15, 70, 0), *observed.moves[1:])
    elif fault == "progress_lost":
        observed.members = (replace(observed.members[0], experience=4999), *observed.members[1:])
    elif fault == "duplicate":
        observed.refs = (observed.refs[1], *observed.refs[1:])
    elif fault == "helper_unknown":
        helper = (105, 86, 94, 166)
    with pytest.raises(ValueError):
        bind(runtime, helper_moves=helper)


@pytest.mark.parametrize("fault", ["eligibility", "selection", "purpose", "schema", "extra"])
def test_frozen_semantic_policy_cannot_be_weakened(fault):
    policy = dict(BIRD_CAPTURE_LOAN_POLICY)
    policy[fault] = "ignore_identity"
    with pytest.raises(ValueError):
        validate_bird_capture_loan_declaration(policy)


def test_old_explicit_approval_is_still_exact_and_not_inferred_for_new_specimens():
    refs = [f"original-{i}" for i in range(6)]
    old = dict(
        schema="pokemon.red.bird-capture-loan.v1",
        user_authorized=True,
        purpose="bird_capture_only",
        species_id=166,
        original_refs=refs,
        specimen_ref=refs[1],
    )
    validate_bird_capture_loan_declaration(old)
    old["specimen_ref"] = "new-raticate"
    with pytest.raises(ValueError):
        validate_bird_capture_loan_declaration(old)


def test_snorlax_has_separate_source_scope_and_identical_exact_transport_protection():
    runtime, original, _ = setup()
    policy = dict(SNORLAX_CAPTURE_LOAN_POLICY)
    scoped = observed_transport_safe_snorlax_guard(
        runtime, policy, helper_moves=(105, 86, 94, 129)
    )
    assert scoped.refs == original.refs and scoped.before == original.before
    assert scoped.loanable_refs == frozenset({"original-2"})
    assert runtime.adapter.party_guard is original
    with pytest.raises(ValueError):
        validate_bird_capture_loan_declaration(policy)
    with pytest.raises(ValueError):
        validate_snorlax_capture_loan_declaration(dict(BIRD_CAPTURE_LOAN_POLICY))


@pytest.mark.parametrize("fault", ["eligibility", "selection", "purpose", "schema", "extra"])
def test_snorlax_scope_cannot_weaken_transport_identity_or_target(fault):
    policy = dict(SNORLAX_CAPTURE_LOAN_POLICY)
    policy[fault] = "ignore_identity"
    with pytest.raises(ValueError):
        validate_snorlax_capture_loan_declaration(policy)


def test_missing_snorlax_permission_cannot_bind_a_loan():
    runtime, _, _ = setup()
    validate_snorlax_capture_loan_declaration(None)
    with pytest.raises(ValueError, match="explicit policy"):
        observed_transport_safe_snorlax_guard(runtime, None, helper_moves=(105, 86, 94, 129))
