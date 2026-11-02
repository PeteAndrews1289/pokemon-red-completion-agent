"""An exhausted venue can end productive work without declaring evolution."""
from types import SimpleNamespace

import pytest

from pokemon_red_completion.goal_manager import GoalFailureReason, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
from pokemon_red_completion.red_integrated_play import ordinary_player_setback
from pokemon_red_completion.routed_semantic_goal import _evolution_progress, RoutedSemanticGoalError


def boundary_and_report():
    facts = dict(actions=0, completed_actions=0, frames=0, cash=100,
                 owned_species=['source'], completed_objectives=['story'],
                 specimen_counts={'source': 1}, battle_state=0,
                 input_ready=True, buttons_released=True)
    evidence = dict(schema='pokemon.red.native-evolution-partial.v1', bounded=True,
                    source_species_ref='pokemon:national:077', target_species_ref='pokemon:national:078',
                    evolution_partial=True, retained_active_roster_restored=True,
                    settlement_reserve_reached=False, wall_limit_reached=False,
                    completed_training_battles=4, healing_trips=13,
                    training_venue_exhausted=True, no_verified_win_in_quantum=True,
                    no_verified_win=False)
    terminal = dict(facts, actions=2, completed_actions=2, frames=20)
    return facts, terminal, evidence


def ordinary(facts, terminal, evidence, error=None):
    verdict = GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
    result = ordinary_player_setback(
        SimpleNamespace(kind=GoalKind.EVOLVE_SPECIES),
        AutonomousSnapshot(b'before', facts, True), AutonomousSnapshot(b'after', terminal, True),
        GoalExecutionReport(2, 20, evidence), verdict, error)
    assert verdict.status.value == 'failed'
    return result


@pytest.mark.parametrize('fault', [None, 'zero_battles', 'bool_battles', 'no_wins',
                                  'missing_no_wins', 'missing_quantum_stop', 'not_exhausted',
                                  'bool_exhausted', 'no_roster', 'unknown_schema', 'negative_heals',
                                  'unknown_helper_stop', 'exception', 'cost_mismatch',
                                  'lost_specimen', 'lost_story', 'lost_registration',
                                  'unsettled', 'battle_open'])
def test_productive_exhaustion_requires_native_custody_cost_and_positive_work(fault):
    before, after, evidence = boundary_and_report()
    mutations = {
        'zero_battles': dict(completed_training_battles=0),
        'bool_battles': dict(completed_training_battles=True),
        'no_wins': dict(no_verified_win=True),
        'not_exhausted': dict(training_venue_exhausted=False),
        'bool_exhausted': dict(training_venue_exhausted=1),
        'no_roster': dict(retained_active_roster_restored=False),
        'unknown_schema': dict(schema='unknown'),
        'negative_heals': dict(healing_trips=-1),
        'unknown_helper_stop': dict(training_venue_exhausted=False, helper_xp_headroom_exhausted=True),
    }
    evidence.update(mutations.get(fault, {}))
    if fault == 'missing_no_wins':
        evidence.pop('no_verified_win')
    if fault == 'missing_quantum_stop':
        evidence.pop('no_verified_win_in_quantum')
    if fault == 'cost_mismatch':
        after['actions'] = 3
    if fault == 'lost_specimen':
        after['specimen_counts'] = {'other': 1}
    if fault == 'lost_story':
        after['completed_objectives'] = []
    if fault == 'lost_registration':
        after['owned_species'] = []
    if fault == 'unsettled':
        after['input_ready'] = False
    if fault == 'battle_open':
        after['battle_state'] = 1
    assert ordinary(before, after, evidence, RuntimeError('native failure') if fault == 'exception' else None) is (fault is None)


@pytest.mark.parametrize('bad_flag', [None, 'budget_reconciled', 'destination_bound',
                                    'destination_executed', 'route_verified', 'within_budget'])
def test_routed_partial_preserves_exact_venue_stop_and_all_route_proofs(bad_flag):
    before, after, evidence = boundary_and_report()
    routed = dict(_evolution_progress(evidence), schema='pokemon.core.routed-semantic-goal-report.v1',
                  destination_kind=GoalKind.EVOLVE_SPECIES.value, budget_reconciled=True,
                  destination_bound=True, destination_executed=True, route_verified=True,
                  within_budget=True)
    if bad_flag:
        routed[bad_flag] = False
    assert ordinary(before, after, routed) is (bad_flag is None)


@pytest.mark.parametrize('field', ['training_venue_exhausted', 'no_verified_win_in_quantum', 'no_verified_win'])
def test_routed_stop_flags_reject_integer_booleans(field):
    with pytest.raises(RoutedSemanticGoalError, match='invalid typed costs'):
        _evolution_progress({field: 1})
