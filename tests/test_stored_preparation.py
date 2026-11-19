from dataclasses import replace
from types import SimpleNamespace as NS

import pytest
from test_no_loan_evolution_settlement import retained_guard

from pokemon_red_completion import red_player_continuation as continuation
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.party_preparation import (
    PreparationBudget,
    PreparationMember,
    PreparationPlan,
    PreparationPurpose,
)


def fixture(monkeypatch):
    guard = retained_guard()
    original = guard.before.members[0]
    caught = PartyMemberObservation(2, 21, 5, 19, 19, experience=178)
    guest = PartyMemberObservation(2, 17, 6, 20, 20, experience=216)
    plan = PreparationPlan((PreparationMember('a', original, PreparationPurpose.COMBAT,
                                              'original combat role'),
                            PreparationMember('caught', caught)),
                           35, 1, (('a', 31),), 'original intent', PreparationBudget())
    party = PartyObservation((replace(original, level=31, experience=29000), guest))
    state = [party, ('a', 'guest'),
             [NS(preparation_ref='caught', species_id=21, level=5, experience=178)]]
    guard.reader.read = lambda: state[0]
    guard.reader.preparation_specimen_refs = lambda: state[1]
    guard = replace(guard, storage_reader=NS(read_box_specimen_identities=lambda: state[2]))
    monkeypatch.setattr(continuation, 'PokemonRedPartyReader', lambda emulator: guard.reader)
    emulator = NS(save_state_bytes=lambda: b'unchanged native state')
    return plan, guard, state, emulator


def test_stored_capture_keeps_original_targets(monkeypatch):
    plan, guard, _, em = fixture(monkeypatch)
    result = continuation.refresh_preparation_roster(em, plan, party_guard=guard)
    assert [m.specimen_ref for m in result.roster] == ['a', 'guest']
    assert result.roster[0] == plan.roster[0]
    assert result.targets == (('a', 31),) and result.budget == plan.budget
    assert result.roster[1].purpose is PreparationPurpose.UNDECIDED
    assert len(plan.roster) == 2 and plan.roster[1].specimen_ref == 'caught'


def test_legacy_refresh_still_rejects_missing_member_without_guard(monkeypatch):
    plan, _, _, em = fixture(monkeypatch)
    with pytest.raises(ValueError, match='lost or duplicated'):
        continuation.refresh_preparation_roster(em, plan)


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'xp', 'species', 'protected',
                                 'assigned', 'loan', 'carrier', 'port'])
def test_storage_observation_does_not_authorize_lost_members_or_intent_changes(monkeypatch, fault):
    plan, guard, state, em = fixture(monkeypatch)
    if fault == 'missing':
        state[2] = []
    elif fault == 'duplicate':
        state[2] *= 2
    elif fault == 'xp':
        state[2][0].experience = 177
    elif fault == 'species':
        state[2][0].species_id = 22
    elif fault == 'protected':
        guard = replace(guard, refs=('a', 'caught'), before=PartyObservation(
            (guard.before.members[0], plan.roster[1].observation)))
    elif fault == 'assigned':
        plan = replace(plan, roster=(plan.roster[0], replace(
            plan.roster[1], purpose=PreparationPurpose.FIELD_UTILITY, purpose_reason='Cut')))
    elif fault == 'loan':
        guard = replace(guard, loanable_refs=frozenset({'a'}))
    elif fault == 'carrier':
        guard = replace(guard, field_carrier=object())
    else:
        guard = replace(guard, reader=NS(read=lambda: state[0],
            preparation_specimen_refs=lambda: ('a', 'different-reader')))
    with pytest.raises(ValueError):
        continuation.refresh_preparation_roster(em, plan, party_guard=guard)


def test_export_repairs_only_native_proven_unassigned_storage(monkeypatch):
    plan, guard, _, em = fixture(monkeypatch)
    runtime = NS(emulator=em, adapter=NS(party_guard=guard))
    monkeypatch.setattr(continuation, 'capture_player_lesson_snapshot', lambda runtime: (
        NS(raw=NS(player_money=100, bag_items=())), {'completed_objectives': []}))
    spent=dict(decisions=0, actions=0, frames=0, seconds=0, heals=0, cash_debits=0)
    result = continuation.capture_player_continuation(
        runtime, preparation=plan, battle=None, spent=spent)
    assert [m['specimen_ref'] for m in result['preparation']['roster']] == ['a', 'guest']
    assert result['preparation']['targets'] == (('a', 31),)
    assert not result['grants_new_budget'] and not result['fit_allowed']
