"""A declared exchange changes custody; it does not permit arbitrary substitution."""
from dataclasses import dataclass, replace
from types import SimpleNamespace as NS

import pytest
from test_no_loan_evolution_settlement import retained_guard

from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.red_goal_context import RedBoxedLevelEvolutionGoalRequest
from pokemon_red_completion.red_native_boxed_evolution import (
    bind_boxed_evolution_roster,
    settle_native_evolution,
)


@dataclass
class Runtime:
    adapter: object
    reader: object
    evolution_settlement: object = None
    evolution_active_roster_refs: tuple[str, ...] | None = None
    evolution_deposited_ref: str | None = None


def fixture():
    guard = retained_guard()
    original = guard.before.members[0]
    deposit = PartyMemberObservation(2, 21, 5, 19, 19, experience=178)
    trainee = PartyMemberObservation(2, 17, 13, 37, 37, experience=2324)
    state = [PartyObservation((original, deposit)), ('a', 'earned-deposit'),
             (NS(box_index=0, box_slot=1, species_id=17, preparation_ref='trainee'),)]
    guard.reader.read = lambda: state[0]
    guard.reader.preparation_specimen_refs = lambda: state[1]
    runtime = Runtime(NS(party_guard=guard, observe=lambda: NS(
        raw=NS(battle_state=0), input_ready=True, party=state[0])),
        NS(read_box_specimen_identities=lambda: state[2]))
    request = RedBoxedLevelEvolutionGoalRequest(17, 18, 0, 1, 2, 21)
    return runtime, request, state, trainee


def exchange(state, trainee):
    state[0] = PartyObservation((state[0].members[0], trainee))
    state[1] = ('a', 'trainee')
    state[2] = (NS(box_index=0, box_slot=1, species_id=21,
                   preparation_ref='earned-deposit'),)


@pytest.mark.parametrize('evolved', [False, True])
def test_declared_box_exchange_settles_with_exact_active_and_stored_identities(evolved):
    runtime, request, state, trainee = fixture()
    bound = bind_boxed_evolution_roster(runtime, request)
    assert runtime.evolution_active_roster_refs is None
    assert bound.evolution_active_roster_refs == ('a', 'trainee')
    assert bound.evolution_deposited_ref == 'earned-deposit'
    exchange(state, replace(trainee, species_id=18) if evolved else trainee)
    assert settle_native_evolution(bound, object()) == {'retained_active_roster_restored': True}


@pytest.mark.parametrize('fault', ['wrong_species', 'wrong_box', 'protected_deposit',
                                 'duplicate_source', 'active_collision'])
def test_exchange_binding_rejects_unobserved_or_protected_changes(fault):
    runtime, request, state, _ = fixture()
    if fault == 'wrong_species':
        request = replace(request, deposit_internal_species_id=22)
    elif fault == 'wrong_box':
        request = replace(request, current_box_index=1)
    elif fault == 'protected_deposit':
        request = replace(request, deposit_party_slot=1, deposit_internal_species_id=59)
    elif fault == 'duplicate_source':
        state[2] = state[2] * 2
    else:
        state[2][0].preparation_ref = 'a'
    with pytest.raises(RuntimeError, match='exchange|identity'):
        bind_boxed_evolution_roster(runtime, request)


@pytest.mark.parametrize('fault', ['missing_deposit', 'duplicate_deposit', 'active_substitute'])
def test_settlement_still_rejects_lost_or_substituted_custody(fault):
    runtime, request, state, trainee = fixture()
    bound = bind_boxed_evolution_roster(runtime, request)
    exchange(state, trainee)
    if fault == 'missing_deposit':
        state[2] = ()
    elif fault == 'duplicate_deposit':
        state[2] *= 2
    else:
        state[1] = ('a', 'substitute')
    with pytest.raises(RuntimeError, match='deposited|active roster'):
        settle_native_evolution(bound, object())


def test_named_loan_preserves_original_settlement_path():
    runtime, request, _, _ = fixture()
    runtime.evolution_settlement = lambda actions: None
    assert bind_boxed_evolution_roster(runtime, request) is runtime
