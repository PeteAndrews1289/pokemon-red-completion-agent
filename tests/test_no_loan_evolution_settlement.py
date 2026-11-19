"""No-loan evolution cannot install settlement that demands a PC loan."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_native_boxed_evolution import settle_native_evolution
from pokemon_red_completion.red_player_configuration import _optional_loan_settlement
from pokemon_red_completion.red_player_party_guard import RedPlayerPartyGuard


def retained_guard():
    member = PartyMemberObservation(1, 59, 30, 46, 46, experience=27000)
    party = PartyObservation((member,))
    reader = NS(read=lambda: party, preparation_specimen_refs=lambda: ("a",))
    return RedPlayerPartyGuard(reader, party, ("a",), frozenset())


def test_no_loan_evolution_settles_without_a_spurious_callback_or_input():
    guard = retained_guard()
    calls = []
    guard.verify_active_roster_restored()
    callback = _optional_loan_settlement(guard, lambda actions: calls.append(actions))
    runtime = NS(
        evolution_settlement=callback,
        adapter=NS(
            party_guard=guard,
            observe=lambda: NS(raw=NS(battle_state=0), input_ready=True, party=guard.reader.read()),
        ),
    )
    assert callback is None
    assert settle_native_evolution(runtime, object()) == {"retained_active_roster_restored": True}
    assert calls == [] and guard.loanable_refs == frozenset()
    guard.verify_active_roster_restored()


@pytest.mark.parametrize("custody", [False, True])
def test_existing_named_loan_or_custody_keeps_its_callback(custody):
    guard = retained_guard()
    guard = (
        replace(guard, field_carrier=object())
        if custody
        else replace(guard, loanable_refs=frozenset({"a"}))
    )

    def callback(actions):
        return actions

    assert _optional_loan_settlement(guard, callback) is callback


@pytest.mark.parametrize("guard,callback", [(None, lambda _: None), (retained_guard(), None)])
def test_invalid_guard_or_callback_rejects(guard, callback):
    with pytest.raises(TypeError):
        _optional_loan_settlement(guard, callback)
