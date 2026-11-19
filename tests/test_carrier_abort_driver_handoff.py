"""Real configuration abort projection + exact metadata-only driver handoff."""
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
from types import SimpleNamespace as N

import pytest
import run_configured_red_player as driver
import test_red_player_configuration as legacy_config
from test_red_field_carrier import case, branches
from test_carrier_return_preflight_abort import proof
from test_red_live_option_menu import _binding, _situation
from pokemon_red_completion import red_player_configuration as configuration_module
from pokemon_red_completion import red_field_carrier_return_abort as abort_module
from pokemon_red_completion.red_field_carrier_custody import active_carrier_preparation
from pokemon_red_completion.red_player_story_menu import NativeStoryBranchInventory
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.provenance import canonical_sha256


def configured_pending(monkeypatch,tmp_path):
    c=case(monkeypatch,known=True);branches(c)[0][0].execute()
    c.state.completed.add('defeat_surge');c.state.legal.clear()
    custody=c.runtime.adapter.party_guard.field_carrier
    old_view=active_carrier_preparation(c.plan,c.runtime,custody)
    c.mons[c.target].level+=1;c.mons[c.target].xp+=1000  # Genuine fake-native observation refresh, no role edit.
    result,body,started=proof(c)
    old_context=json.loads(body)
    old_context.update(schema=driver.PLAYER_CONTINUATION_SCHEMA,preparation=asdict(old_view),
        lesson={'native_party':'same physical source'},cash=c.state.money,bag=[[196,1]],battle=None,search_memory=None)
    body=json.dumps(old_context,sort_keys=True).encode();result['context_sha256']=sha256(body).hexdigest()
    (tmp_path/'RESULT.json').write_text(json.dumps(result));(tmp_path/'CONTEXT.json').write_bytes(body)
    step=tmp_path/'native/episode/step-000';step.mkdir(parents=True);(step/'execution-started.json').write_text(json.dumps(started))
    ordinary=(_binding(GoalKind.ADVANCE_STORY,binding_ref='native-story',calls=[]),_binding(GoalKind.RESTORE_TEAM,binding_ref='native-heal',calls=[]))
    inventory=GoalBindingSet(tuple(b.opportunity for b in ordinary),ordinary)
    menu=NativeStoryBranchInventory(lambda *_:inventory,lambda *_:())
    holder={'runtime':c.runtime,'plan':c.plan,'configured_route':c.route}
    backend=N(assembly=lambda *a,**k:(c.runtime.emulator.save_state_bytes(),None,menu,holder,{'partition':'development'}))
    for name in ['_retained_field_faint_inventory','_retained_capture_inventory','_retained_wild_faint_inventory']:
        monkeypatch.setattr(configuration_module,name,lambda *a,**k:None)
    import pokemon_red_completion.red_indoor_departure_plan as departure
    monkeypatch.setattr(departure,'native_ship_departure_binding',lambda *a,**k:None)
    monkeypatch.setattr(configuration_module,'pending_gym_reward_binding',lambda *a,**k:None)
    (tmp_path/'plan.json').write_text(json.dumps(dict(owned_field_carrier_exchange=True)))
    _,_,configured,_,_=configuration_module.assemble_configured_player(backend,legacy_config.config(),tmp_path,tmp_path,
        plan_path=tmp_path/'plan.json')
    bindings=configured.enumerate_base(c.runtime,c.actions,c.runtime.adapter.observe())
    assert len(bindings.bindings)==1
    return N(c=c,holder=holder,menu=configured,binding=bindings.bindings[0],source_bytes=body,source_context=old_context,
             pending_guard=c.runtime.adapter.party_guard,parent=tmp_path)


def handoff_case(monkeypatch,tmp_path):
    x=configured_pending(monkeypatch,tmp_path)
    counts=(x.c.actions.actions_executed,x.c.runtime.emulator.frame_count)
    report=x.binding.execute();assert x.binding.verify(report).status.value=='succeeded'
    current=x.c.runtime.emulator.save_state_bytes();state=sha256(current).hexdigest()
    context=deepcopy(x.source_context);context['field_carrier']=x.c.runtime.adapter.party_guard.field_carrier.private_dict()
    context['preparation']=asdict(x.holder['plan']);context['spent']=dict(context['spent'],decisions=context['spent']['decisions']+1,seconds=context['spent']['seconds']+0.5)
    exported=json.dumps(context,sort_keys=True).encode()
    facts=dict(actions=counts[0],completed_actions=counts[0],frames=counts[1],cash=x.c.state.money)
    row=dict(selected_kind='recover_control',verification='succeeded',safe_terminal=True,ordinary_setback=False,
             evidence=dict(report.evidence),before_state_sha256=state,terminal_state_sha256=state,
             before=facts,after=deepcopy(facts),observed_cost=dict(actions=0,completed_actions=0,frames=0,cash_spent=0))
    result=dict(passed=True,released=True,field_ready=True,paired_context_authenticated=True,state_sha256=state,
                context_sha256=sha256(exported).hexdigest(),spent=context['spent'],episode=dict(stop_reason='no_state_progress',outcomes=[row]),
                chunk_costs=dict(goal_attempts=1,actions_attempted=0,actions_completed=0,frames=0,restore_attempts=0,
                                 nested_restore_attempts=0,training_healing_attempts=0,seconds=0.5))
    plan=dict(partition='development',automatic_runtime_renewal=dict(mode='live_chunks_v1',reason='bounded existing allowance'))
    def inspect():return x.menu.enumerate_base(x.c.runtime,x.c.actions,x.c.runtime.adapter.observe())
    kwargs=dict(plan=plan,runtime=x.c.runtime,inspect_bindings=inspect,source_context_bytes=x.source_bytes,
                exported_context_bytes=exported,expected_source_context_sha256=sha256(x.source_bytes).hexdigest())
    return N(x=x,result=result,kwargs=kwargs,after_context=context,row=row)


def test_real_configuration_callback_reprojects_pending_source_current_active_members(monkeypatch,tmp_path):
    x=configured_pending(monkeypatch,tmp_path);old=x.pending_guard;native=x.c.runtime.emulator.save_state_bytes();counts=(x.c.actions.actions_executed,x.c.runtime.emulator.frame_count)
    assert x.holder['plan'] is x.c.plan and old.field_carrier.phase=='pending'
    report=x.binding.execute();assert x.binding.verify(report).status.value=='succeeded'
    plan=x.holder['plan'];guard=x.c.runtime.adapter.party_guard
    refs=guard.reader.preparation_specimen_refs();members=dict(zip(refs,guard.reader.read().members,strict=True))
    assert {m.specimen_ref for m in plan.roster}==set(refs)
    assert old.field_carrier.displaced_ref not in refs and old.field_carrier.carrier_ref in refs
    for member in plan.roster:assert member.observation==members[member.specimen_ref]
    carrier=next(m for m in plan.roster if m.specimen_ref==old.field_carrier.carrier_ref)
    assert carrier.purpose.value=='field_utility'
    assert carrier.observation.level==x.c.mons[x.c.target].level
    assert guard.before==old.before and guard.refs==old.refs and guard.loanable_refs==old.loanable_refs
    assert guard.field_carrier.preparation_before==old.field_carrier.preparation_before
    assert report.evidence['active_preparation_projection_sha256']==canonical_sha256(asdict(plan))
    assert x.c.runtime.emulator.save_state_bytes()==native and counts==(x.c.actions.actions_executed,x.c.runtime.emulator.frame_count)
    assert (tmp_path/'CONTEXT.json').read_bytes()==x.source_bytes
    fresh=x.menu.enumerate_base(x.c.runtime,x.c.actions,x.c.runtime.adapter.observe())
    assert fresh.bindings and all(not b.binding_ref.startswith('pokemon.red:aborted-field-carrier-return:')for b in fresh.bindings)


def test_failed_projection_preserves_pending_guard_and_original_holder(monkeypatch,tmp_path):
    x=configured_pending(monkeypatch,tmp_path);old=x.holder['plan']
    import pokemon_red_completion.red_field_carrier_custody as custody_module
    monkeypatch.setattr(custody_module,'aborted_active_carrier_preparation',lambda *a:(_ for _ in()).throw(ValueError('projection refused')))
    with pytest.raises(ValueError,match='projection refused'):x.binding.execute()
    assert x.c.runtime.adapter.party_guard is x.pending_guard and x.holder['plan'] is old


def test_exact_metadata_handoff_keeps_raw_no_progress_and_debits_original_costs(monkeypatch,tmp_path):
    h=handoff_case(monkeypatch,tmp_path);before=deepcopy(h.result)
    certificate=driver._qualified_zero_input_carrier_abort_handoff(h.result,**h.kwargs)
    assert certificate is not None and certificate['pending_to_active']is True
    assert certificate['native_progress']is certificate['quest_progress']is False
    assert certificate['decision_debit']==1 and certificate['seconds_debit']==0.5
    assert h.result==before and h.result['episode']['stop_reason']=='no_state_progress'
    assert driver.chunk_continuation_reason(h.result,source_sha256=h.result['state_sha256'])=='no_executable_progress'


@pytest.mark.parametrize('fault',['manual','wrong_mode','wrong_stop','extra_row','failed_row','row_error','top_error','unpaired',
    'unreleased','unready','state','same_context','source_pin','wrong_support','objective','restored_roster','no_projection',
    'wrong_projection','actions','frames','cash','bool_cost','decision_reset','seconds_reset','seconds_mismatch','extra_heal',
    'new_phase_pending','old_phase_active','baseline_change','roles_change','carrier_combat','old_roles_change',
    'physical_observation_change','missing_ref','stale_slot','new_budget','fit','repeated_abort','inspection_state'])
def test_metadata_handoff_refuses_every_unproved_scope(monkeypatch,tmp_path,fault):
    h=handoff_case(monkeypatch,tmp_path);r=h.result;k=h.kwargs;old=json.loads(k['source_context_bytes']);new=deepcopy(h.after_context)
    if fault=='manual':k['plan'].pop('automatic_runtime_renewal')
    elif fault=='wrong_mode':k['plan']['automatic_runtime_renewal']['mode']='new-budget'
    elif fault=='wrong_stop':r['episode']['stop_reason']='decision_budget'
    elif fault=='extra_row':r['episode']['outcomes'].append(deepcopy(h.row))
    elif fault=='failed_row':h.row['verification']='failed'
    elif fault=='row_error':h.row['error']='unknown'
    elif fault=='top_error':r['error']='unknown'
    elif fault=='unpaired':r['paired_context_authenticated']=False
    elif fault=='unreleased':r['released']=False
    elif fault=='unready':r['field_ready']=False
    elif fault=='state':r['state_sha256']='0'*64
    elif fault=='same_context':new=deepcopy(old)
    elif fault=='source_pin':k['expected_source_context_sha256']='0'*64
    elif fault=='wrong_support':h.row['evidence']['support']='unrelated'
    elif fault=='objective':h.row['evidence']['objective_completed']=True
    elif fault=='restored_roster':h.row['evidence']['original_roster_restored']=True
    elif fault=='no_projection':h.row['evidence'].pop('active_preparation_projection_sha256')
    elif fault=='wrong_projection':h.row['evidence']['active_preparation_projection_sha256']='0'*64
    elif fault=='actions':h.row['observed_cost']['actions']=1
    elif fault=='frames':h.row['after']['frames']+=1
    elif fault=='cash':h.row['after']['cash']-=1
    elif fault=='bool_cost':h.row['observed_cost']['actions']=False
    elif fault=='decision_reset':new['spent']['decisions']=0
    elif fault=='seconds_reset':new['spent']['seconds']=0
    elif fault=='seconds_mismatch':r['chunk_costs']['seconds']=0.7
    elif fault=='extra_heal':new['spent']['heals']+=1
    elif fault=='new_phase_pending':new['field_carrier']['phase']='pending'
    elif fault=='old_phase_active':old['field_carrier']['phase']='active'
    elif fault=='baseline_change':new['field_carrier']['original_guard_sha256']='0'*64
    elif fault=='roles_change':next(m for m in new['preparation']['roster']if m['purpose']=='undecided')['purpose']='combat'
    elif fault=='carrier_combat':next(m for m in new['preparation']['roster']if m['specimen_ref']==new['field_carrier']['carrier_ref'])['purpose']='combat'
    elif fault=='old_roles_change':next(m for m in old['preparation']['roster']if m['purpose']=='undecided')['purpose']='combat'
    elif fault=='physical_observation_change':new['preparation']['roster'][0]['observation']['experience']+=1
    elif fault=='missing_ref':new['preparation']['roster']=new['preparation']['roster'][:-1]
    elif fault=='stale_slot':new['preparation']['roster'][0]['observation']['slot']=6
    elif fault=='new_budget':new['grants_new_budget']=True
    elif fault=='fit':new['fit_allowed']=True
    elif fault=='repeated_abort':
        binding=h.x.binding;fresh=k['inspect_bindings']()
        k['inspect_bindings']=lambda:GoalBindingSet(fresh.opportunities+(binding.opportunity,),fresh.bindings+(binding,))
    elif fault=='inspection_state':
        original=k['inspect_bindings']
        def changed():h.x.c.state.epoch+=1;return original()
        k['inspect_bindings']=changed
    k['source_context_bytes']=json.dumps(old,sort_keys=True).encode()
    if fault!='source_pin':k['expected_source_context_sha256']=sha256(k['source_context_bytes']).hexdigest()
    k['exported_context_bytes']=json.dumps(new,sort_keys=True).encode();r['context_sha256']=sha256(k['exported_context_bytes']).hexdigest();r['spent']=new['spent']
    if fault in {'roles_change','carrier_combat','physical_observation_change','missing_ref','stale_slot'}:
        h.row['evidence']['active_preparation_projection_sha256']=canonical_sha256(new['preparation'])
    assert driver._qualified_zero_input_carrier_abort_handoff(r,**k)is None