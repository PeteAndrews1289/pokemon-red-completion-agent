"""ROM-free carrier-return capability and exact never-started abort checks."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from types import SimpleNamespace as N

import pytest
from test_red_field_carrier import case, branches
from pokemon_red_completion import red_field_carrier as carrier
from pokemon_red_completion import red_player_party_loan as loan
from pokemon_red_completion import red_field_carrier_return_abort as abort
from pokemon_red_completion.goal_manager import GoalAvailability, GoalUnavailableReason


def active(monkeypatch):
    c = case(monkeypatch, known=True)
    branches(c)[0][0].execute()
    c.state.completed.add('defeat_surge')
    c.state.legal.clear()
    return c


def proof(c):
    guard = c.runtime.adapter.party_guard
    custody = replace(guard.field_carrier, phase='pending')
    c.runtime.adapter.party_guard = replace(guard, field_carrier=custody)
    data = c.runtime.emulator.save_state_bytes();state = sha256(data).hexdigest()
    spent=dict(decisions=7,actions=80,frames=600,seconds=2.5,heals=1,cash_debits=40)
    context=dict(state_sha256=state,field_carrier=custody.private_dict(),spent=spent,
                 fit_allowed=False,grants_new_budget=False)
    body=json.dumps(context,sort_keys=True).encode()
    facts=dict(actions=4,completed_actions=4,frames=20,cash=c.state.money,battle_state=0,buttons_released=True)
    chain=[dict(error_type='ValueError',error=abort.ERROR)]
    row=dict(ordinal=0,selected_kind='manage_storage',error_type='ValueError',error=abort.ERROR,
             error_chain=chain,failure_phase='execution',verification=None,ordinary_setback=False,
             safe_terminal=True,before_state_sha256=state,terminal_state_sha256=state,
             before=facts,after=deepcopy(facts),observed_cost=dict(actions=0,completed_actions=0,frames=0,cash_spent=0))
    result=dict(passed=True,episode=dict(outcomes=[row],stop_reason="execution_failed"),released=True,field_ready=True,paired_context_authenticated=True,
                state_sha256=state,context_sha256=sha256(body).hexdigest(),spent=spent,error_chain=chain)
    started=dict(selected_kind='manage_storage',state_sha256=state,
                 selected_binding_ref='pokemon.red:field-carrier-return:'+state)
    return result,body,started


def test_unexecutable_return_is_unavailable_and_preserves_active_custody(monkeypatch):
    c=active(monkeypatch);guard=c.runtime.adapter.party_guard;before=c.runtime.emulator.save_state_bytes();counts=(c.actions.actions_executed,c.runtime.emulator.frame_count);unavailable=[]
    monkeypatch.setattr(carrier,'party_loan_return_center',lambda *a,**k:None)
    assert carrier.field_carrier_return_binding(c.runtime,c.actions,route=c.route,on_unavailable=unavailable.append)is None
    assert len(unavailable)==1 and unavailable[0].availability is GoalAvailability.UNAVAILABLE
    assert unavailable[0].unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
    assert c.runtime.adapter.party_guard is guard and c.runtime.emulator.save_state_bytes()==before
    assert (c.actions.actions_executed,c.runtime.emulator.frame_count)==counts


def test_quote_revalidated_before_metadata_or_input(monkeypatch):
    c=active(monkeypatch);guard=c.runtime.adapter.party_guard;quotes=iter([89,None]);counts=(c.actions.actions_executed,c.runtime.emulator.frame_count)
    monkeypatch.setattr(carrier,'party_loan_return_center',lambda *a,**k:next(quotes))
    binding=carrier.field_carrier_return_binding(c.runtime,c.actions,route=c.route)
    with pytest.raises(ValueError,match='quote changed'):binding.execute()
    assert c.runtime.adapter.party_guard is guard
    assert (c.actions.actions_executed,c.runtime.emulator.frame_count)==counts


@pytest.mark.parametrize('fault',['none','actions','frames','state','buttons'])
def test_failed_return_rolls_metadata_back_only_with_exact_no_input_proof(monkeypatch,fault):
    c=active(monkeypatch);guard=c.runtime.adapter.party_guard
    monkeypatch.setattr(carrier,'party_loan_return_center',lambda *a,**k:89)
    def fail(*args):
        if fault=='actions':c.actions.execute(N(kind='wait'))
        if fault=='frames':c.runtime.emulator.frame_count+=1
        if fault=='state':c.state.epoch+=1
        if fault=='buttons':c.runtime.emulator.pressed_buttons=('a',)
        raise ValueError('retained original native error')
    monkeypatch.setattr(carrier,'settle_pending_field_carrier',fail)
    binding=carrier.field_carrier_return_binding(c.runtime,c.actions,route=c.route)
    with pytest.raises(ValueError,match='retained original'):binding.execute()
    if fault=='none':assert c.runtime.adapter.party_guard is guard
    else:assert c.runtime.adapter.party_guard.field_carrier.phase=='pending'
    assert c.runtime.adapter.party_guard.before==guard.before
    assert c.runtime.adapter.party_guard.refs==guard.refs
    assert c.runtime.adapter.party_guard.loanable_refs==guard.loanable_refs


def test_exact_saved_abort_proof_preserves_original_guard_without_writing(monkeypatch):
    c=active(monkeypatch);result,body,started=proof(c);guard=c.runtime.adapter.party_guard
    current=c.runtime.emulator.save_state_bytes();counts=(c.actions.actions_executed,c.runtime.emulator.frame_count)
    candidate=abort._qualified_return_abort_guard(c.runtime,result,body,started)
    assert candidate is not None and candidate.field_carrier.phase=='active'
    assert candidate.before==guard.before and candidate.refs==guard.refs and candidate.loanable_refs==guard.loanable_refs
    assert c.runtime.adapter.party_guard is guard and guard.field_carrier.phase=='pending'
    assert current==c.runtime.emulator.save_state_bytes() and counts==(c.actions.actions_executed,c.runtime.emulator.frame_count)


@pytest.mark.parametrize('fault',['wrapper_failed','wrong_stop','unpaired','unreleased','unready','state','context','spent','budget_grant','fit',
    'wrong_kind','wrong_error','extra_cause','prior_error','verification','setback','unsafe','before_hash',
    'terminal_hash','native_actions','native_frames','cash','bool_cost','facts_changed','started_ref','started_kind',
    'started_source','wrong_carrier','not_active_physical'])
def test_arbitrary_or_partly_executed_pending_scope_cannot_be_promoted(monkeypatch,fault):
    c=active(monkeypatch);result,body,started=proof(c);row=result['episode']['outcomes'][-1]
    if fault=='wrapper_failed':result['passed']=False
    elif fault=='wrong_stop':result['episode']['stop_reason']='operator_interrupt'
    elif fault=='unpaired':result['paired_context_authenticated']=False
    elif fault=='unreleased':result['released']=False
    elif fault=='unready':result['field_ready']=False
    elif fault=='state':result['state_sha256']='0'*64
    elif fault=='context':result['context_sha256']='0'*64
    elif fault=='spent':result['spent']={}
    elif fault in {'budget_grant','fit','wrong_carrier'}:
        ctx=json.loads(body)
        if fault=='budget_grant':ctx['grants_new_budget']=True
        elif fault=='fit':ctx['fit_allowed']=True
        else:ctx['field_carrier']['carrier_ref']='unrelated'
        body=json.dumps(ctx).encode();result['context_sha256']=sha256(body).hexdigest()
    elif fault=='wrong_kind':row['selected_kind']='advance_story'
    elif fault=='wrong_error':row['error']='unknown'
    elif fault=='extra_cause':row['error_chain'].append(dict(error_type='RuntimeError',error='unrelated'))
    elif fault=='prior_error':result['episode']['outcomes'].insert(0,dict(error_type='RuntimeError'))
    elif fault=='verification':row['verification']='failed'
    elif fault=='setback':row['ordinary_setback']=True
    elif fault=='unsafe':row['safe_terminal']=False
    elif fault=='before_hash':row['before_state_sha256']='0'*64
    elif fault=='terminal_hash':row['terminal_state_sha256']='0'*64
    elif fault=='native_actions':row['observed_cost']['actions']=1
    elif fault=='native_frames':row['observed_cost']['frames']=1
    elif fault=='cash':row['observed_cost']['cash_spent']=1
    elif fault=='bool_cost':row['observed_cost']['actions']=False
    elif fault=='facts_changed':row['after']['cash']-=1
    elif fault=='started_ref':started['selected_binding_ref']='unrelated'
    elif fault=='started_kind':started['selected_kind']='advance_story'
    elif fault=='started_source':started['state_sha256']='0'*64
    elif fault=='not_active_physical':c.state.active[-1]=c.runtime.adapter.party_guard.field_carrier.displaced_ref
    assert abort._qualified_return_abort_guard(c.runtime,result,body,started)is None
    assert c.runtime.adapter.party_guard.field_carrier.phase=='pending'


def test_authenticated_abort_binding_changes_only_runtime_metadata_once(monkeypatch,tmp_path):
    c=active(monkeypatch);result,body,started=proof(c);old=c.runtime.adapter.party_guard
    (tmp_path/'RESULT.json').write_text(json.dumps(result));(tmp_path/'CONTEXT.json').write_bytes(body)
    step=tmp_path/'native/episode/step-000';step.mkdir(parents=True);(step/'execution-started.json').write_text(json.dumps(started))
    before=c.runtime.emulator.save_state_bytes();counts=(c.actions.actions_executed,c.runtime.emulator.frame_count)
    b=abort.retained_field_carrier_return_abort_binding(c.runtime,c.actions,parent=tmp_path)
    assert b is not None and old.field_carrier.phase=='pending'
    report=b.execute();assert b.verify(report).status.value=='succeeded'
    assert report.actions_executed==report.frames_executed==0 and report.evidence['original_roster_restored']is False
    assert c.runtime.adapter.party_guard.field_carrier.phase=='active'
    assert c.runtime.adapter.party_guard.before==old.before and c.runtime.adapter.party_guard.refs==old.refs
    assert (tmp_path/'CONTEXT.json').read_bytes()==body
    assert c.runtime.emulator.save_state_bytes()==before and counts==(c.actions.actions_executed,c.runtime.emulator.frame_count)
    with pytest.raises(ValueError,match='stale or consumed'):b.execute()
    assert abort.retained_field_carrier_return_abort_binding(c.runtime,c.actions,parent=tmp_path)is None