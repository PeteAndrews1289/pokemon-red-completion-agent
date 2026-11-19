"""Zero-progress recovery is a failed attempt, with independently observed custody."""
from copy import deepcopy
from types import SimpleNamespace as N
import pytest
from pokemon_red_completion.goal_manager import GoalKind, GoalFailureReason
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport, GoalVerification
from pokemon_red_completion.red_autonomous_player import AutonomousSnapshot
from pokemon_red_completion.red_integrated_play import (
    ordinary_player_setback, settled_evolution_partial, settled_evolution_zero_progress,
)
from pokemon_red_completion.routed_semantic_goal import _evolution_progress


def example(routed=False):
    proof=dict(schema='pokemon.red.retained-party-continuation.v1',native_identity_verified=True,
        guard_sha256='a'*64,individuals={'trainee':dict(species_ref='pokemon:national:050',level=44,experience=85184),
        'helper':dict(species_ref='pokemon:national:009',level=51,experience=125126)},other_specimen_counts={})
    before=dict(actions=0,completed_actions=0,frames=0,cash=500,owned_species=['pokemon:national:050','pokemon:national:009'],
        completed_objectives=['help_bill'],specimen_counts={'pokemon:national:050':1,'pokemon:national:009':1},
        battle_state=0,input_ready=True,buttons_released=True,retained_party_continuation=proof)
    after=deepcopy(before);after.update(actions=20,completed_actions=20,frames=200)
    after['retained_party_continuation']['individuals']['helper']['experience']+=20
    e=dict(schema='pokemon.red.native-evolution-partial.v1',bounded=True,
        source_species_ref='pokemon:national:050',target_species_ref='pokemon:national:051',
        zero_progress_evolution=True,zero_progress_trainee_ref='trainee',evolution_partial=True,
        retained_active_roster_restored=True,settlement_reserve_reached=True,wall_limit_reached=False,
        completed_training_battles=0,healing_trips=1,trainee_initial_xp=85184,trainee_terminal_xp=85184,trainee_xp_gained=0)
    if routed:
        e=_evolution_progress(e)
        e.update(schema='pokemon.core.routed-semantic-goal-report.v1',destination_kind='evolve_species',
            budget_reconciled=True,destination_bound=True,destination_executed=True,route_verified=True,within_budget=True)
    return before,after,e


@pytest.mark.parametrize('routed',[False,True])
@pytest.mark.parametrize('fault',[None,'flag','ref','xp_claim','actual_xp','wins','unknown_cause','return',
    'custody','stock','story','unsafe','unready','cost','exception','success','bool_count','unknown_guard'])
def test_zero_progress_attempt_is_failed_and_costed(routed,fault):
    before,after,e=example(routed); error=None; actions=20
    verdict=GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
    if fault=='flag':e.pop('zero_progress_evolution')
    elif fault=='ref':e['zero_progress_trainee_ref']='helper'
    elif fault=='xp_claim':e['trainee_xp_gained']=20
    elif fault=='actual_xp':after['retained_party_continuation']['individuals']['trainee']['experience']+=20
    elif fault=='wins':e['completed_training_battles']=1
    elif fault=='unknown_cause':e['settlement_reserve_reached']=False
    elif fault=='return':e['retained_active_roster_restored']=False
    elif fault=='custody':after['retained_party_continuation']['individuals'].pop('helper')
    elif fault=='stock':after['specimen_counts']['pokemon:national:009']=2
    elif fault=='story':after['completed_objectives']=[]
    elif fault=='unsafe':after['battle_state']=1
    elif fault=='unready':after['input_ready']=False
    elif fault=='cost':actions=19
    elif fault=='exception':error=RuntimeError('unknown control')
    elif fault=='success':verdict=GoalVerification.succeeded()
    elif fault=='bool_count':e['completed_training_battles']=False
    elif fault=='unknown_guard':after['retained_party_continuation']['guard_sha256']='b'*64
    report=GoalExecutionReport(actions,200,e);binding=N(kind=GoalKind.EVOLVE_SPECIES,binding_ref='evolve')
    assert not settled_evolution_partial(binding,report)
    assert ordinary_player_setback(binding,AutonomousSnapshot(b'first',before,True),
        AutonomousSnapshot(b'last',after,True),report,verdict,error) is (fault is None)
    assert e['trainee_xp_gained']==(20 if fault=='xp_claim'else 0)


def test_zero_win_legacy_and_trade_reports_are_not_new_failed_attempts():
    _,_,e=example();e.pop('zero_progress_evolution')
    assert not settled_evolution_zero_progress(N(kind=GoalKind.EVOLVE_SPECIES),GoalExecutionReport(20,200,e))
    _,_,e=example()
    assert not settled_evolution_zero_progress(N(kind=GoalKind.ACQUIRE_SPECIES),GoalExecutionReport(20,200,e))


@pytest.mark.parametrize('name,value',[('zero_progress_evolution',1),('zero_progress_trainee_ref',2)])
def test_routed_zero_attempt_requires_typed_evidence(name,value):
    from pokemon_red_completion.routed_semantic_goal import RoutedSemanticGoalError
    _,_,e=example();e[name]=value
    with pytest.raises(RoutedSemanticGoalError):_evolution_progress(e)
