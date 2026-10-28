"""ROM-free switch-only TRAIN contrasts; no native, model predictions or optimization."""
from copy import deepcopy
import pytest
from pokemon_red_completion import red_trainer_practice_counterfactual as cf
from pokemon_red_completion import red_trainer_practice_admission as admission
from pokemon_red_completion import red_trainer_practice_targets as targets
from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_scenario_capture import OBSERVATION_SCHEMA_V2,build_battle_scenario_capture_payload,open_battle_scenario_capture
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_trainer_practice_episode import RedTrainerPracticeEpisode
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog
from pokemon_red_completion.scenario_lab import ScenarioPartition
CONTEXT=dict(schema='pokemon.core.battle.status-context.v1',player_confused=False,opponent_confused=False,player_stages=[0]*6,opponent_stages=[0]*6)
ROLE='switch_selection';REFS=('pokemon.core:battle:switch:2','pokemon.core:battle:switch:3')
def resources():return dict(party_hp=[40,35,30],party_max_hp=[50,50,50],party_pp=[[20,0,0,0],[20,0,0,0],[20,0,0,0]])
def observation(r,active,rich=True):
 o=dict(features=dict(battle=dict(active=True,kind='wild',opponent_hp=20,opponent_max_hp=20),party=dict(active_index=active,lead=dict(moves=[dict(slot_index=0,pp=r['party_pp'][active][0])]),members=[dict(hp=hp,max_hp=cap)for hp,cap in zip(r['party_hp'],r['party_max_hp'],strict=True)])))
 if rich:o['features']['battle']['status_context']=deepcopy(CONTEXT)
 return o
def capture(tmp_path):
 tmp_path.mkdir(exist_ok=True);state=b'switch-only-synthetic-unit-never-native';p=tmp_path/'unit.state';m=tmp_path/'unit.state.json';p.write_bytes(state)
 m.write_bytes(build_battle_scenario_capture_payload(capture_id='switch-window-unit',root_lineage_id='synthetic-unit-only',partition=ScenarioPartition.TRAIN,state_bytes=state,initial_observation_sha256=canonical_sha256(observation(resources(),0,False)),source_commit='c'*40,expected_map=15,expected_battle_state=1,observation_schema=OBSERVATION_SCHEMA_V2))
 return open_battle_scenario_capture(p,m)
class Continuation:
 policy_id='unit-common-continuation'
 def choose_main(self,*a):return BattleAction.move(1)
 def choose_switch(self,_obs,legal,**kwargs):return legal[0]
def composed(tmp_path,monkeypatch,*,limits=(8,32),scope=ROLE,first_slots=(2,3),log_scope=ROLE,modules=None,admit=True):
 cmod,amod,tmod=modules or (cf,admission,targets);cap=capture(tmp_path);horizon,budget=(2,8)if limits is None else limits;logs={};policies=[]
 def factory():obj=Continuation();policies.append(obj);return obj
 def fake_run(cap,*,policy,max_decisions,max_player_turns,event_sink,session_factory,opening_idle_frames=0,**kwargs):
  assert max_decisions==budget and max_player_turns==horizon and kwargs['wild_training'] is True and kwargs['train_wild_diagnostic'] is True
  event_sink(dict(event='episode_started',manifest_sha256=cap.manifest_sha256,policy_id=policy.policy_id,max_decisions=budget,max_player_turns=horizon,opening_idle_frames=0,wild_training=True,train_wild_diagnostic=True,allow_status_moves=True));r=resources();active=0;decisions=[]
  for number in range(1,horizon+1):
   before=deepcopy(r);obs=observation(before,active);action=policy.choose_main(obs,object());kind='voluntary_switch'if action.party_slot else'attack';legal=[i+1 for i in range(3)if i!=active and r['party_hp'][i]>0]
   if kind=='attack':r['party_pp'][active][0]-=1
   else:active=action.party_slot-1
   r['party_hp'][active]-=2 if active==2 else 1;after=deepcopy(r);after_obs=observation(after,active)
   step=dict(decision_index=number,kind=kind,move_slot=1 if kind=='attack'else None,party_slot=action.party_slot,observation=obs,observation_sha256=canonical_sha256(obs),after_observation_sha256=canonical_sha256(after_obs),legal_move_slots=[1],legal_party_slots=legal,model_input=dict(candidate_move_slots=[1],legal_mask=[True],supported_candidate_mask=[True]),frames_executed=10,opponent_hp_before=20,opponent_hp_after=20,state_before=before,state_after=after)
   event_sink(dict(event='decision_started'));event_sink(dict(event='choice_recorded',decision_index=number,selected_action=action.public_dict()));event_sink(dict(event='decision_completed',decision=step));decisions.append(step)
  return RedTrainerPracticeEpisode(capture_id=cap.manifest.capture_id,manifest_sha256=cap.manifest_sha256,policy_id=policy.policy_id,decisions=tuple(decisions),battle_won=False,final_battle_state=1,stop_reason='player_turn_budget',final_observation=after_obs)
 monkeypatch.setattr(cmod,'run_red_trainer_practice_episode',fake_run)
 def logger(index,choice):
  directory=tmp_path/f'branch-{index}';logs[choice.semantic_ref]=directory;identity=dict(capture_id=cap.manifest.capture_id,root_lineage_id=cap.manifest.root_lineage_id,capture_manifest_sha256=cap.manifest_sha256,source_commit=cap.manifest.source_commit,partition='train',policy_id=Continuation.policy_id,first_choice_ref=choice.semantic_ref,player_turn_horizon=horizon,plan_sha256='a'*64,model_sha256='b'*64,max_decisions=budget,opening_idle_frames=0,wild_training=True,train_wild_diagnostic=True,allow_status_moves=True,native_status_context=CONTEXT)
  if log_scope is not None:identity['train_wild_choice_scope']=log_scope
  return TrainerPracticeEventLog(directory,run_identity=identity)
 choices=tuple(cmod.TrainerPracticeFirstChoice(BattleAction.switch(s))for s in first_slots)if scope is not None else(cmod.TrainerPracticeFirstChoice(BattleAction.move(1)),cmod.TrainerPracticeFirstChoice(BattleAction.switch(2)))
 optional={}if scope is None else dict(train_wild_choice_scope=scope)
 result=cmod.collect_trainer_practice_counterfactuals(cap,session_factory=lambda:pytest.fail('no emulator sessions'),continuation_policy_factory=factory,first_choices=choices,max_decisions=budget,player_turn_horizon=horizon,branch_event_log_factory=logger,allow_status_moves=True,train_wild_diagnostic=True,train_wild_limits=limits,**optional)
 assert len(policies)==2 and policies[0]is not policies[1]
 kwargs=dict(expected_choice_refs=tuple(c.semantic_ref for c in choices),continuation_policy_id=Continuation.policy_id,branch_event_logs=logs,plan_sha256='a'*64,model_sha256='b'*64,max_decisions=budget,expected_status_context=CONTEXT,train_wild_diagnostic=True,train_wild_limits=limits,**optional)
 document=result.public_dict();proof=amod.inspect_trainer_practice_choices(cap,document,**kwargs)if admit else None
 return cap,document,proof,kwargs

def test_real_collector_log_admission_target_switch_only(tmp_path,monkeypatch):
 cap,doc,proof,kwargs=composed(tmp_path,monkeypatch);target=targets.extract_trainer_practice_targets(proof,doc,train_wild_diagnostic=True,train_wild_limits=(8,32),train_wild_choice_scope=ROLE)
 assert doc['train_wild_choice_scope']==proof['train_wild_choice_scope']==target['train_wild_choice_scope']==ROLE
 assert proof['execution_proof_complete']and proof['return_proof_complete']and doc['branch_count']==2
 assert set(target['heads'])=={'switch'}and target['heads']['switch']['choice_refs']==list(REFS)
 assert target['heads']['switch']['returns']==[r['whole_party_return']['value']for r in proof['measured_choices']]
 assert target['heads']['switch']['best_indices']==[0]and target['decision_context']=='main'and target['new_independent_upstream_roots']==0
 assert 'control'not in target['heads']and'move'not in target['heads']

@pytest.mark.parametrize('scope',[True,False,1,[],{},'control','switch','SWITCH_SELECTION','switch_selection '])
def test_invalid_role_rejects_before_policy_log_or_session(tmp_path,scope):
 cap=capture(tmp_path);calls=[]
 def forbidden(*a,**k):calls.append(True);raise AssertionError('must reject before branch')
 with pytest.raises(cf.TrainerPracticeCounterfactualError):cf.collect_trainer_practice_counterfactuals(cap,session_factory=forbidden,continuation_policy_factory=forbidden,first_choices=(cf.TrainerPracticeFirstChoice(BattleAction.switch(2)),cf.TrainerPracticeFirstChoice(BattleAction.switch(3))),max_decisions=32,player_turn_horizon=8,branch_event_log_factory=forbidden,train_wild_diagnostic=True,train_wild_limits=(8,32),train_wild_choice_scope=scope)
 assert calls==[]
@pytest.mark.parametrize('wild,limits',[(False,(8,32)),(True,None),(True,(2,8)),(True,[8,32]),(True,(8,True))])
def test_switch_role_requires_explicit_eight_turn_authority(tmp_path,wild,limits):
 cap=capture(tmp_path)
 with pytest.raises(cf.TrainerPracticeCounterfactualError):cf.collect_trainer_practice_counterfactuals(cap,session_factory=lambda:pytest.fail('session'),continuation_policy_factory=lambda:pytest.fail('policy'),first_choices=(cf.TrainerPracticeFirstChoice(BattleAction.switch(2)),cf.TrainerPracticeFirstChoice(BattleAction.switch(3))),max_decisions=32,player_turn_horizon=8,train_wild_diagnostic=wild,train_wild_limits=limits,train_wild_choice_scope=ROLE)
@pytest.mark.parametrize('choice_type',['mixed','duplicate','decline','three','default_consumer'])
def test_only_two_distinct_switches_collect(tmp_path,choice_type):
 choices={'mixed':(BattleAction.move(1),BattleAction.switch(2)),'duplicate':(BattleAction.switch(2),BattleAction.switch(2)),'decline':(None,BattleAction.switch(2)),'three':(BattleAction.switch(2),BattleAction.switch(3),BattleAction.switch(4)),'default_consumer':(BattleAction.switch(2),BattleAction.switch(3))}[choice_type];cap=capture(tmp_path)
 with pytest.raises(cf.TrainerPracticeCounterfactualError):cf.collect_trainer_practice_counterfactuals(cap,session_factory=lambda:pytest.fail('session'),continuation_policy_factory=lambda:pytest.fail('policy'),first_choices=tuple(cf.TrainerPracticeFirstChoice(x)for x in choices),max_decisions=32,player_turn_horizon=8,train_wild_diagnostic=True,train_wild_limits=(8,32),train_wild_choice_scope=None if choice_type=='default_consumer'else ROLE)
@pytest.mark.parametrize('fault',['missing_scope','forged_scope','default_consumer','missing_limits','false_argument','bad_ref'])
def test_admission_cannot_downgrade_or_forge_scope(tmp_path,monkeypatch,fault):
 cap,doc,proof,kwargs=composed(tmp_path,monkeypatch)
 if fault=='missing_scope':doc.pop('train_wild_choice_scope')
 if fault=='forged_scope':doc['train_wild_choice_scope']='control'
 if fault=='default_consumer':kwargs['train_wild_choice_scope']=None
 if fault=='missing_limits':kwargs['train_wild_limits']=None
 if fault=='false_argument':kwargs['train_wild_choice_scope']=False
 if fault=='bad_ref':kwargs['expected_choice_refs']=('pokemon.core:battle:switch:2','pokemon.core:battle:switch:True')
 with pytest.raises(admission.TrainerPracticeAdmissionError):admission.inspect_trainer_practice_choices(cap,doc,**kwargs)
def test_log_role_must_match_and_be_present(tmp_path,monkeypatch):
 with pytest.raises(admission.TrainerPracticeAdmissionError,match='scope|identity'):composed(tmp_path,monkeypatch,log_scope=None)
def test_native_initial_switch_must_be_legal(tmp_path,monkeypatch):
 with pytest.raises(admission.TrainerPracticeAdmissionError,match='illegal'):composed(tmp_path,monkeypatch,first_slots=(1,2))
@pytest.mark.parametrize('fault',['admission_missing','document_missing','default_consumer','false_argument','attack_forgery','illegal_switch','changed_model_input'])
def test_target_switch_scope_metadata_and_no_synthetic_control(tmp_path,monkeypatch,fault):
 cap,doc,proof,kwargs=composed(tmp_path,monkeypatch);scope=ROLE
 if fault=='admission_missing':proof.pop('train_wild_choice_scope')
 if fault=='document_missing':doc.pop('train_wild_choice_scope')
 if fault=='default_consumer':scope=None
 if fault=='false_argument':scope=False
 if fault=='attack_forgery':doc['branches'][0]['episode']['decisions'][0]['kind']='attack'
 if fault=='illegal_switch':doc['branches'][0]['episode']['decisions'][0]['legal_party_slots']=[]
 if fault=='changed_model_input':doc['branches'][1]['episode']['decisions'][0]['model_input']['supported_candidate_mask']=[False]
 with pytest.raises(targets.TrainerPracticeTargetError):targets.extract_trainer_practice_targets(proof,doc,train_wild_diagnostic=True,train_wild_limits=(8,32),train_wild_choice_scope=scope)
def test_default_timing_aggregator_cannot_strip_role(tmp_path,monkeypatch):
 _,doc,proof,_=composed(tmp_path,monkeypatch);t=targets.extract_trainer_practice_targets(proof,doc,train_wild_diagnostic=True,train_wild_limits=(8,32),train_wild_choice_scope=ROLE);samples=[]
 for i in range(5):item=deepcopy(t);item['timing_offset_frames']=i;samples.append(item)
 with pytest.raises(targets.TrainerPracticeTargetError,match='switch-selection'):targets.aggregate_trainer_timing_targets(tuple(samples),expected_offsets=(0,1,2,3,4))
@pytest.mark.parametrize('scope',[True,False,0,'unknown'])
def test_producer_role_metadata_checked(scope):
 result=cf.TrainerPracticeCounterfactualSet(capture_id='unit',manifest_sha256='a'*64,root_lineage_id='synthetic',player_turn_horizon=8,branches=(),train_wild_diagnostic=True,train_wild_limits=(8,32),train_wild_choice_scope=scope)
 with pytest.raises(cf.TrainerPracticeCounterfactualError):result.public_dict()