"""A catch before training is legal;roster changes during training are not."""

from dataclasses import dataclass, replace
from types import SimpleNamespace as NS

import pytest
from test_no_loan_evolution_settlement import retained_guard

from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_native_boxed_evolution import (
    bind_no_loan_evolution_roster,
    settle_native_evolution,
)


@dataclass
class Runtime:
    adapter: object
    evolution_settlement: object = None
    evolution_active_roster_refs: tuple[str, ...] | None = None


def fixture():
    guard = retained_guard()
    original = guard.before.members[0]
    caught = PartyMemberObservation(2, 21, 3, 14, 14, experience=27)
    state = [PartyObservation((original, caught)), ("a", "earned-catch")]
    guard.reader.read = lambda: state[0]
    guard.reader.preparation_specimen_refs = lambda: state[1]
    runtime = Runtime(
        NS(
            party_guard=guard,
            observe=lambda: NS(raw=NS(battle_state=0), input_ready=True, party=state[0]),
        )
    )
    return runtime, state


def test_earned_addition_before_training_is_preserved_with_original_guard():
    runtime, state = fixture()
    bound = bind_no_loan_evolution_roster(runtime)
    assert bound.evolution_active_roster_refs == ("a", "earned-catch")
    assert runtime.evolution_active_roster_refs is None
    assert bound.adapter.party_guard.refs == ("a",)
    old, caught = state[0].members
    state[0] = PartyObservation((replace(old, experience=28000, level=31), caught))
    assert settle_native_evolution(bound, object()) == {"retained_active_roster_restored": True}


@pytest.mark.parametrize(
    "change", ["addition", "remove_catch", "substitute_catch", "remove_retained"]
)
def test_exact_training_boundary_rejects_roster_changes(change):
    runtime, state = fixture()
    bound = bind_no_loan_evolution_roster(runtime)
    if change == "addition":
        state[0] = PartyObservation((*state[0].members, replace(state[0].members[1], slot=3)))
        state[1] = (*state[1], "third")
    elif change == "remove_catch":
        state[0] = PartyObservation(state[0].members[:1])
        state[1] = ("a",)
    elif change == "substitute_catch":
        state[1] = ("a", "substitute")
    else:
        state[0] = PartyObservation((replace(state[0].members[1], slot=1),))
        state[1] = ("earned-catch",)
    with pytest.raises((ValueError, RuntimeError), match="roster|lost|duplicated|restored"):
        settle_native_evolution(bound, object())


def test_legacy_settlement_still_rejects_unbound_extra_member():
    runtime, _ = fixture()
    with pytest.raises(RuntimeError, match="exact active roster"):
        settle_native_evolution(runtime, object())


def test_named_loan_keeps_original_callback_and_authority():
    runtime, _ = fixture()
    runtime.evolution_settlement = lambda actions: None
    assert bind_no_loan_evolution_roster(runtime) is runtime
