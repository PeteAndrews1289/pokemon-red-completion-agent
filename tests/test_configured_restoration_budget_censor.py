"""ROM-free restoration finite-censor contracts against the actual shared driver."""
import argparse
import copy
from types import SimpleNamespace
import pytest
import run_configured_red_player as driver

def limits(**kwargs):
    return driver.NativePlayerLimits(**dict(dict(decisions=24, actions=24000,
        frames=2400000, seconds=600, heals=16, cash_debits=None), **kwargs))

def receipt():
    chain = [dict(error_type='RestorationBudgetExhausted', error='native player restoration budget exhausted')]
    before = dict(actions=10,completed_actions=10,frames=100,restoration_attempts=0,
        nested_restoration_attempts=0,training_healing_attempts=0,cash=3000)
    after = dict(actions=20,completed_actions=20,frames=300,restoration_attempts=16,
        nested_restoration_attempts=16,training_healing_attempts=0,cash=3000,
        battle_state=0,input_ready=True,buttons_released=True,party_guard_verified=True)
    row = dict(error_type=chain[0]['error_type'],error=chain[0]['error'],error_chain=chain,
        verification='failed',failure_reason='execution_budget_exhausted',failure_phase='execution',
        ordinary_setback=False,safe_terminal=True,terminal_state_sha256='a'*64,
        before=before,after=after,observed_cost=dict(actions=10,completed_actions=10,frames=200,cash_spent=0))
    meter = dict(schema="pokemon.red.native-player-costs.v1",automatic_fit=False,actions_attempted=20,actions_completed=20,frames=300,goal_attempts=1,
        restore_attempts=16,nested_restore_attempts=16,training_healing_attempts=0,
        observed_cash_debits=0,observed_cash_rewards=0,observed_cash_changes=0,
        control_recovery_cash_debits=0,seconds=3.5,buttons_released=True)
    return dict(worker_stopped=True,spent=dict(decisions=1,actions=20,frames=300,heals=16,cash_debits=0,seconds=3.5),passed=True,error=None,error_chain=copy.deepcopy(chain),released=True,
        field_ready=True,paired_context_authenticated=True,state_sha256='a'*64,
        context_sha256='b'*64,chunk_costs=meter,episode=dict(stop_reason='restoration_budget',
        executed_decisions=1,outcomes=[row]))

def test_exact_censor_retains_raw_failed_goal_error_and_input():
    value=receipt();before=copy.deepcopy(value)
    status=driver.native_result_status(value,limits=limits())
    assert status['status']=='restoration_budget_censor'
    assert status['native_outcome_error_count']==status['unrecovered_native_error_count']==1
    assert status['nonordinary_verification_failures']==1
    assert status['qualified_budget_censor_count']==1 and status['finite_censor']
    assert status['effective_unrecovered_native_error_count']==0
    assert status['effective_nonordinary_verification_failures']==0
    assert status['ordinary_setbacks']==0 and not status['independent_completion_verification']
    assert value==before

@pytest.mark.parametrize('cap',[None,{'heals':16},SimpleNamespace(heals=16)])
def test_missing_or_pasted_limits_never_qualify(cap):
    assert driver.native_result_status(receipt(),limits=cap)['status']=='execution_error'

MUTATIONS={
    'same_text_RuntimeError':lambda r:r['episode']['outcomes'][-1].update(error_type='RuntimeError'),
    'wrong_message':lambda r:r['episode']['outcomes'][-1].update(error='other'),
    'wrong_stop':lambda r:r['episode'].update(stop_reason='execution_failed'),
    'wrong_failure_reason':lambda r:r['episode']['outcomes'][-1].update(failure_reason='unknown'),
    'wrong_phase':lambda r:r['episode']['outcomes'][-1].update(failure_phase='verification'),
    'nonexact_chain':lambda r:r['episode']['outcomes'][-1]['error_chain'].append(dict(error_type='ValueError',error='secondary')),
    'extra_prior_error':lambda r:r['episode']['outcomes'].insert(0,dict(error_type='ValueError',error='first')),
    'prior_failed_goal':lambda r:r['episode']['outcomes'].insert(0,dict(verification='failed',ordinary_setback=False)),
    'root_error':lambda r:r.update(error_type='ValueError',error='export failed'),
    'export_error':lambda r:r.update(checkpoint_export_error=dict(error='failed')),
    'unsafe':lambda r:r['episode']['outcomes'][-1].update(safe_terminal=False),
    'unready':lambda r:r.update(field_ready=False),
    'held_controls':lambda r:r.update(released=False),
    'unpaired':lambda r:r.update(paired_context_authenticated=False),
    'wrong_terminal':lambda r:r['episode']['outcomes'][-1].update(terminal_state_sha256='c'*64),
    'missing_context_hash':lambda r:r.pop('context_sha256'),
    'missing_seconds':lambda r:r['chunk_costs'].pop('seconds'),
    'nan_seconds':lambda r:r['chunk_costs'].update(seconds=float('nan')),
    'boolean_cost':lambda r:r['chunk_costs'].update(restore_attempts=True),
    'missing_cash':lambda r:r['chunk_costs'].pop('observed_cash_debits'),
    'lower_bound':lambda r:r.update(cost_lower_bound=True),
    'unknown_cost':lambda r:r.update(unknown_cost_fields=['seconds']),
    'incomplete_context':lambda r:r.update(context_costs_complete=False),
    'counter_mismatch':lambda r:r['episode']['outcomes'][-1]['after'].update(actions=19),
    'paid_tail_omitted':lambda r:r['episode']['outcomes'][-1]['observed_cost'].update(actions=0),
    'cash_tail_omitted':lambda r:r['episode']['outcomes'][-1]['after'].update(cash=2900),
    'unsettled':lambda r:r['episode']['outcomes'][-1]['after'].update(battle_state=1),
    'unverified_guard':lambda r:r['episode']['outcomes'][-1]['after'].update(party_guard_verified=False),
}
@pytest.mark.parametrize('fault',MUTATIONS)
def test_unknown_errors_and_incomplete_paid_tail_stay_errors(fault):
    value=receipt();MUTATIONS[fault](value)
    status=driver.native_result_status(value,limits=limits())
    assert status['status']=='execution_error' and status['qualified_budget_censor_count']==0

@pytest.mark.parametrize('heals',[15,17])
def test_measured_heals_must_equal_actual_executing_limit(heals):
    assert not driver.qualified_restoration_budget_censor(receipt(),limits=limits(heals=heals))

@pytest.mark.parametrize('cap',[limits(actions=19),limits(frames=299),limits(seconds=3)])
def test_other_cap_breach_cannot_become_restoration_censor(cap):
    assert not driver.qualified_restoration_budget_censor(receipt(),limits=cap)

@pytest.mark.parametrize('cap,expected',[(0,False),(1,True),(None,True)])
def test_finite_cash_debit_limit_is_enforced_using_observed_debits(cap,expected):
    value=receipt();value['chunk_costs']['observed_cash_debits']=1
    value['chunk_costs']['observed_cash_rewards']=1 # Same final cash cannot erase the paid debit.
    value['chunk_costs']['observed_cash_changes']=2;value['spent']['cash_debits']=1
    assert driver.qualified_restoration_budget_censor(value,limits=limits(cash_debits=cap)) is expected

MISSING_FIELDS=[]
for field in ('state_sha256','context_sha256','spent','paired_context_authenticated','worker_stopped','released','field_ready','chunk_costs','episode'):
    MISSING_FIELDS.append(('result',field))
for field in receipt()['episode']:
    MISSING_FIELDS.append(('episode',field))
for field in receipt()['chunk_costs']:
    MISSING_FIELDS.append(('chunk_costs',field))
for field in receipt()['spent']:
    MISSING_FIELDS.append(('spent',field))
for field in receipt()['episode']['outcomes'][0]['before']:
    MISSING_FIELDS.append(('before',field))
for field in receipt()['episode']['outcomes'][0]['after']:
    MISSING_FIELDS.append(('after',field))
for field in receipt()['episode']['outcomes'][0]['observed_cost']:
    MISSING_FIELDS.append(('observed_cost',field))
for field in ('error_type','error','error_chain','verification','failure_reason','failure_phase','ordinary_setback','safe_terminal','terminal_state_sha256'):
    MISSING_FIELDS.append(('row',field))
@pytest.mark.parametrize('section,field',MISSING_FIELDS)
def test_every_mandatory_meter_state_and_export_field_is_required(section,field):
    value=receipt();row=value['episode']['outcomes'][0]
    target=value if section=='result' else row if section=='row' else row[section] if section in ('before','after','observed_cost') else value[section]
    del target[field]
    assert not driver.qualified_restoration_budget_censor(value,limits=limits())

@pytest.mark.parametrize('field',['decisions','actions','frames','seconds','heals','cash_debits'])
def test_exported_cumulative_cost_cannot_omit_the_paid_chunk(field):
    value=receipt();value['spent'][field]=-1
    assert not driver.qualified_restoration_budget_censor(value,limits=limits())

def test_qualified_reason_grants_no_new_original_budget():
    value=receipt()
    assert driver.chunk_continuation_reason(value,source_sha256='d'*64,limits=limits())=='automatic_budget_recovery'
    base=dict(decisions=0,actions=0,frames=0,seconds=0.,heals=0)
    allowance=dict(decisions=24,actions=24000,frames=2400000,seconds=600,heals=16)
    actual=driver.configured_execution_limits(argparse.Namespace(decisions=24,actions=24000,frames=2400000,seconds=600),driver.remaining_allowance(base,base,allowance),600)
    assert actual.heals==16
    inputs=[]
    with pytest.raises(ValueError,match='exhausted its allowance'):
        remaining=driver.remaining_allowance(dict(decisions=1,actions=20,frames=300,seconds=3.5,heals=16),base,allowance)
        inputs.append(remaining)
    assert inputs==[]
    value['episode']['outcomes'][-1]['error_type']='RuntimeError'
    assert driver.chunk_continuation_reason(value,source_sha256='d'*64,limits=limits())=='native_execution_error'
