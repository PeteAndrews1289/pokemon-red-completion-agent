"""Successful registration tasks may renew only through the declared live loop."""
from types import SimpleNamespace as N
from hashlib import sha256
from copy import deepcopy
import json
import pytest
import run_configured_red_player as driver
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.player_sequence_targets import registration_task_catalog
from pokemon_red_completion.red_collection import RED_SOLO_COLLECTION_CONTRACT
from pokemon_red_completion.provenance import canonical_sha256
from test_configured_sequence_policy import policy_plan

def fixture(tmp_path):
    _,_,plan=policy_plan(tmp_path)
    task=registration_task_catalog(POKEMON_RED_US_REV_0.sha256)
    path=tmp_path/'catalog.json';path.write_text(json.dumps(task))
    plan['sequence_policy'].update(task_sha256=task['task_sha256'],task_catalog=dict(path=str(path),content_sha256=sha256(path.read_bytes()).hexdigest()))
    plan.update(registration_task_continuation='live_next_registration_v1',automatic_runtime_renewal=dict(mode='live_chunks_v1',reason='finite useful task renewal'),required_species=list(RED_SOLO_COLLECTION_CONTRACT.target_species),objectives=['defeat_champion','enter_hall_of_fame'])
    output=tmp_path/'segment';root=output/'native/episode';(root/'sequence').mkdir(parents=True);(root/'step-000').mkdir();source=sha256(b'before').hexdigest();terminal=sha256(b'after').hexdigest();(output/'native/source.state').write_bytes(b'before')
    row=dict(before_state_sha256=source,terminal_state_sha256=terminal,before=dict(owned_species=['pokemon:national:007']),after=dict(owned_species=['pokemon:national:007','pokemon:national:016']),verification='succeeded',safe_terminal=True,error_type=None,error=None)
    episode=dict(stop_reason='declared_consequence_complete',outcomes=[row]);ap=dict(schema='pokemon.red.autonomous-option-run.v1',continuous_player=True,teacher_actions_allowed=False)
    claim=dict(schema='pokemon.player.task-terminal-claim.v1',task_sha256=task['task_sha256'],source_sha256=source,behavior_plan_sha256=canonical_sha256(ap),terminal_sha256=terminal,last_outcome_sha256=canonical_sha256(row),native_verification_required=True,training_eligible=False)
    for p,x in[(root/'plan.json',ap),(root/'result.json',episode),(root/'step-000/outcome.json',row),(root/'sequence/task-terminal.json',claim),(root/'sequence/receipt-000.json',dict(outcome_sha256=claim['last_outcome_sha256']))]:p.write_text(json.dumps(x))
    result=dict(passed=True,released=True,field_ready=True,paired_context_authenticated=True,state_sha256=terminal,episode=episode,chunk_costs=dict(actions_attempted=1,frames=1))
    em=N(frame_count=1,pressed_buttons=(),save_state_bytes=lambda:b'after');runtime=N(emulator=em,reader=N(read_pokedex_state=lambda:N(owned_species=frozenset([7,16]))))
    return plan,result,runtime,output,root

def test_absent_opt_in_preserves_existing_stop_without_touching_runtime():
    assert driver.declared_registration_task_continuation({})is False
    assert driver.qualified_registration_task_handoff({},plan={},runtime=None,output=None)is None

def test_real_progress_matching_receipt_renews_read_only_with_no_budget_grant(tmp_path):
    p,r,rt,o,_=fixture(tmp_path);before=deepcopy(r);proof=driver.qualified_registration_task_handoff(r,plan=p,runtime=rt,output=o)
    assert proof and proof['new_registrations']==['pokemon:national:016']and proof['aggregate_budget_reset']is False
    assert proof['inputs']==proof['frames']==proof['model_queries']==proof['fit_calls']==0 and r==before

@pytest.mark.parametrize('fault',['mode','no_live','subset','story_subset','catalog','task'])
def test_bad_opt_in_fails_before_any_runtime_read(tmp_path,fault):
    p,_,_,_,_=fixture(tmp_path)
    if fault=='mode':p['registration_task_continuation']='unchecked'
    elif fault=='no_live':p.pop('automatic_runtime_renewal')
    elif fault=='subset':p['required_species']=p['required_species'][:-1]
    elif fault=='story_subset':p['objectives']=['defeat_brock']
    elif fault=='catalog':p['sequence_policy']['task_catalog']['content_sha256']='0'*64
    else:p['sequence_policy']['task_sha256']='0'*64
    with pytest.raises(ValueError):driver.qualified_registration_task_handoff({},plan=p,runtime=None,output=None)

@pytest.mark.parametrize('fault',['passed','released','field_ready','paired_context_authenticated','error','export','admission','unknown_cost','zero_actions','claim','receipt','row','actual_state','actual_dex','buttons'])
def test_unknown_or_mismatched_task_cannot_renew(tmp_path,fault):
    p,r,rt,o,root=fixture(tmp_path)
    if fault in ['passed','released','field_ready','paired_context_authenticated']:r[fault]=False
    elif fault=='error':r['error_type']='KeyboardInterrupt'
    elif fault=='export':r['checkpoint_export_error']='missing'
    elif fault=='admission':r['episode']['admission_failure']=True
    elif fault=='unknown_cost':r['cost_lower_bound']=True
    elif fault=='zero_actions':r['chunk_costs']['actions_attempted']=0
    elif fault in ['claim','receipt','row']:(root/('sequence/task-terminal.json'if fault=='claim'else'sequence/receipt-000.json'if fault=='receipt'else'step-000/outcome.json')).write_text('{}')
    elif fault=='actual_state':rt.emulator.save_state_bytes=lambda:b'foreign'
    elif fault=='actual_dex':rt.reader.read_pokedex_state=lambda:N(owned_species=frozenset([7]))
    else:rt.emulator.pressed_buttons=('a',)
    assert driver.qualified_registration_task_handoff(r,plan=p,runtime=rt,output=o)is None

def test_opt_in_cannot_change_silently_across_own_continuation():
    with pytest.raises(ValueError,match='continuation'):driver.validate_continued_sequence_wiring(dict(registration_task_continuation='live_next_registration_v1'),{})


def loss_before_successful_registration(tmp_path):
    p,r,rt,o,root=fixture(tmp_path)
    row=r['episode']['outcomes'][0]
    loss=deepcopy(row)
    lost_state=sha256(b'after-loss').hexdigest()
    loss.update(terminal_state_sha256=lost_state,after=dict(owned_species=['pokemon:national:007']),verification='failed',ordinary_setback=True,evidence=dict(native_league_funding_loss=dict(completion=dict(episode=dict(decisions=[dict(state_before=dict(player_stat_stages=(7,7,7,7,7,7)),state_after=dict(player_stat_stages=(7,7,7,7,7,7)))])))))
    row['before_state_sha256']=lost_state
    r['episode']['outcomes']=[loss,row]
    r['chunk_costs']=dict(actions_attempted=2,frames=2)
    (root/'step-001').mkdir()
    claim=json.loads((root/'sequence/task-terminal.json').read_text())
    claim['last_outcome_sha256']=canonical_sha256(row)
    for path,value in [(root/'result.json',r['episode']),(root/'step-000/outcome.json',loss),(root/'step-001/outcome.json',row),(root/'sequence/task-terminal.json',claim),(root/'sequence/receipt-000.json',dict(outcome_sha256=canonical_sha256(loss))),(root/'sequence/receipt-001.json',dict(outcome_sha256=canonical_sha256(row)))]:path.write_text(json.dumps(value))
    return p,r,rt,o,root


def test_ordinary_loss_then_registration_accepts_canonical_persisted_evidence(tmp_path):
    p,r,rt,o,root=loss_before_successful_registration(tmp_path)
    before=deepcopy(r)
    persisted=json.loads((root/'result.json').read_text())
    assert persisted!=r['episode'] and canonical_sha256(persisted)==canonical_sha256(r['episode'])
    proof=driver.qualified_registration_task_handoff(r,plan=p,runtime=rt,output=o)
    assert proof and proof['new_registrations']==['pokemon:national:016']
    assert proof['aggregate_budget_reset']is False and r==before


@pytest.mark.parametrize('surface',['episode','row'])
def test_normalizing_loss_evidence_never_accepts_changed_battle_values(tmp_path,surface):
    p,r,rt,o,root=loss_before_successful_registration(tmp_path)
    path=root/('result.json'if surface=='episode'else'step-000/outcome.json')
    value=json.loads(path.read_text())
    loss=value['outcomes'][0]if surface=='episode'else value
    loss['evidence']['native_league_funding_loss']['completion']['episode']['decisions'][0]['state_after']['player_stat_stages'][0]=6
    path.write_text(json.dumps(value))
    assert driver.qualified_registration_task_handoff(r,plan=p,runtime=rt,output=o)is None
