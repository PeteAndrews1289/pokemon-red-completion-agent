"""ROM-free strict typed retained-outcome handoff; no battle/action execution."""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace as N

import pytest
import run_configured_red_player as driver
from pokemon_red_completion.goal_manager import GoalKind, GoalAvailability, GoalOpportunity, GoalUnavailableReason
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet, GoalVerification

ERROR='RetainedTrainerBattleDecisionBudgetReached'
MESSAGE='retained trainer battle reached its bounded decision limit'
REASON='retained_trainer_battle_decision_budget'


def binding_set(*bindings):
    blocked=GoalOpportunity('blocked',GoalKind.EXPLORE,GoalAvailability.UNAVAILABLE,
        unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET)
    return GoalBindingSet(tuple(b.opportunity for b in bindings)+(blocked,),tuple(bindings))


def fixture(monkeypatch,*,preface=False):
    state=[b'exact-current-retained-native-trainer']
    current=sha256(state[0]).hexdigest()
    em=N(save_state_bytes=lambda:state[0],frame_count=80,pressed_buttons=set())
    raw=N(battle_state=2,party_hp=(0,140))
    rt=N(emulator=em,reader=N(read=lambda:raw))
    chain=[dict(error_type=ERROR,error=MESSAGE,reason_code=REASON)]
    result=dict(state_sha256=current,released=True,field_ready=False)
    if preface:
        result.update(error_type=ERROR,error=MESSAGE,error_chain=deepcopy(chain))
    else:
        row=dict(selected_kind=GoalKind.RECOVER_CONTROL.value,error_type=ERROR,error=MESSAGE,
            error_chain=deepcopy(chain),failure_phase='execution',verification=None,ordinary_setback=False,
            safe_terminal=True,before_state_sha256='a'*64,terminal_state_sha256=current,
            before=dict(actions=0,completed_actions=0,frames=0),after=dict(actions=1118,completed_actions=1118,frames=104088),
            observed_cost=dict(actions=1118,completed_actions=1118,frames=104088,cash_spent=0))
        result.update(passed=True,error=None,error_chain=deepcopy(chain),context_sha256='b'*64,paired_context_authenticated=True,
            episode=dict(stop_reason='execution_failed',outcomes=[row]),
            chunk_costs=dict(actions_attempted=1118,actions_completed=1118,frames=104088))
    monkeypatch.setattr(driver,'_field_ready',lambda _:False)
    calls=[]
    def inventory():
        calls.append('inspect')
        bind=ExecutableGoalBinding('pokemon.red:retained-engagement:'+current,GoalKind.RECOVER_CONTROL,0.,0.,
            lambda:pytest.fail('handoff must not execute a goal'),lambda _:GoalVerification.succeeded())
        return binding_set(bind)
    return N(result=result,rt=rt,raw=raw,state=state,em=em,inventory=inventory,calls=calls)


def run(s):return driver.qualified_native_control_handoff(s.result,runtime=s.rt,inspect_bindings=s.inventory)


def test_single_typed_compulsory_outcome_qualifies_without_rewriting_raw_failure(monkeypatch):
    s=fixture(monkeypatch);before=json.dumps(s.result,sort_keys=True)
    receipt=run(s)
    assert receipt['qualified'] and receipt['retained_outcome_censor'] and not receipt['compulsory_preface_censor']
    assert receipt['finite_in_battle_censor'] and receipt['original_terminal_safe'] is False
    assert receipt['local_decision_limit_unchanged'] and receipt['aggregate_budget_reset'] is False
    assert receipt['inputs']==receipt['frames']==receipt['model_queries']==0
    assert receipt['observed_actions']==1118 and receipt['observed_frames']==104088
    assert s.result['episode']['outcomes'][0]['safe_terminal'] is True
    assert json.dumps(s.result,sort_keys=True)==before and s.calls==['inspect']


def test_legacy_top_preface_shape_still_qualifies_without_rewriting_it(monkeypatch):
    s=fixture(monkeypatch,preface=True);before=json.dumps(s.result,sort_keys=True)
    receipt=run(s)
    assert receipt['compulsory_preface_censor'] and not receipt['retained_outcome_censor']
    assert json.dumps(s.result,sort_keys=True)==before


@pytest.mark.parametrize('fault',[
    'wrong_kind','wrong_type','wrong_message','missing_reason','unknown_row_cause','unknown_top_cause',
    'top_error','export_error','admission','unpaired','wrapper_not_returned','context_pin','source_pin','stationary',
    'terminal_mismatch','prior_success','prior_failure','zero_actions','zero_frames','incomplete_actions',
    'meter_mismatch','meter_boolean','row_delta','unknown_cost','lower_bound','cost_incomplete','missing_cost',
    'wrong_stop','verified_success','ordinary_setback','unreleased','field_ready','wild','party_defeated','stale',
])
def test_unqualified_or_zero_progress_shapes_refuse_before_inspection(monkeypatch,fault):
    s=fixture(monkeypatch);r=s.result;row=r['episode']['outcomes'][0]
    if fault=='wrong_kind':row['selected_kind']=GoalKind.ADVANCE_STORY.value
    elif fault=='wrong_type':row['error_type']='RuntimeError'
    elif fault=='wrong_message':row['error']='some other bounded failure'
    elif fault=='missing_reason':row['error_chain']=[]
    elif fault=='unknown_row_cause':row['error_chain'].append(dict(error_type='RuntimeError',reason_code='unknown'))
    elif fault=='unknown_top_cause':r['error_chain'].append(dict(error_type='RuntimeError',reason_code='unknown'))
    elif fault=='top_error':r['error_type']='RuntimeError';r['error']='unrelated runner error'
    elif fault=='export_error':r['checkpoint_export_error']='failed context export'
    elif fault=='admission':r['episode']['admission_failure']={'why':'unknown'}
    elif fault=='unpaired':r['paired_context_authenticated']=False
    elif fault=='wrapper_not_returned':r['passed']=False
    elif fault=='context_pin':r['context_sha256']='not-a-hash'
    elif fault=='source_pin':row['before_state_sha256']='not-a-hash'
    elif fault=='stationary':row['before_state_sha256']=r['state_sha256']
    elif fault=='terminal_mismatch':row['terminal_state_sha256']='c'*64
    elif fault in ('prior_success','prior_failure'):
        r['episode']['outcomes'].insert(0,dict(error_type=None if fault=='prior_success'else'RuntimeError'))
    elif fault=='zero_actions':row['observed_cost']['actions']=0
    elif fault=='zero_frames':row['observed_cost']['frames']=0
    elif fault=='incomplete_actions':row['observed_cost']['completed_actions']-=1
    elif fault=='meter_mismatch':r['chunk_costs']['frames']+=1
    elif fault=='meter_boolean':row['observed_cost']['actions']=1;row['after']['actions']=1;r['chunk_costs']['actions_attempted']=True
    elif fault=='row_delta':row['after']['frames']+=1
    elif fault=='unknown_cost':r['unknown_cost_fields']=['actions']
    elif fault=='lower_bound':r['cost_lower_bound']=True
    elif fault=='cost_incomplete':r['context_costs_complete']=False
    elif fault=='missing_cost':row.pop('observed_cost')
    elif fault=='wrong_stop':r['episode']['stop_reason']='wall_time_budget'
    elif fault=='verified_success':row['verification']='succeeded'
    elif fault=='ordinary_setback':row['ordinary_setback']=True
    elif fault=='unreleased':r['released']=False
    elif fault=='field_ready':r['field_ready']=True
    elif fault=='wild':s.raw.battle_state=1
    elif fault=='party_defeated':s.raw.party_hp=(0,0)
    else:s.state[0]=b'changed-native-source'
    before=json.dumps(r,sort_keys=True)
    assert run(s)is None
    assert json.dumps(r,sort_keys=True)==before and s.calls==[]


@pytest.mark.parametrize('fault',['extra_choice','wrong_ref','wrong_binding_kind'])
def test_only_one_exact_compulsory_successor_is_accepted(monkeypatch,fault):
    s=fixture(monkeypatch);original=s.inventory
    def inventory():
        bindings=original();old=bindings.bindings[0]
        if fault=='wrong_ref':
            new=ExecutableGoalBinding('other-source',old.kind,0.,0.,old.execute,old.verify);return binding_set(new)
        new=ExecutableGoalBinding('other-choice',GoalKind.EXPLORE,0.,0.,old.execute,old.verify)
        if fault=='wrong_binding_kind':return binding_set(new)
        return binding_set(old,new)
    s.inventory=inventory
    assert run(s)is None


@pytest.mark.parametrize('fault',['state','frames','pressed'])
def test_inspection_that_changes_native_boundary_is_a_fault(monkeypatch,fault):
    s=fixture(monkeypatch);original=s.inventory
    def inventory():
        result=original()
        if fault=='state':s.state[0]=b'changed'
        elif fault=='frames':s.em.frame_count+=1
        else:s.em.pressed_buttons.add('a')
        return result
    s.inventory=inventory
    with pytest.raises(ValueError,match='inspection changed state'):run(s)
