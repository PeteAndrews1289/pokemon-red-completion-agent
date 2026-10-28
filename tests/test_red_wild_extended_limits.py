"""Explicit 8/32 TRAIN windows preserve genuine collector/log/admission composition.

All episodes here are synthetic ROM-free unit fixtures, never native evidence.
"""
from copy import deepcopy
from types import SimpleNamespace
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
REFS=('pokemon.core:battle:move:1','pokemon.core:battle:switch:2')
def observation(resources,active,rich=True):
 data=dict(features=dict(battle=dict(active=True,kind='wild',opponent_hp=20,opponent_max_hp=20),party=dict(active_index=active,lead=dict(moves=[dict(slot_index=0,pp=resources['party_pp'][active][0])]),members=[dict(hp=hp,max_hp=cap) for hp,cap in zip(resources['party_hp'],resources['party_max_hp'],strict=True)])))
 if rich:data['features']['battle']['status_context']=deepcopy(CONTEXT)
 return data
def capture(tmp_path):
 resources=dict(party_hp=[40,35],party_max_hp=[50,50],party_pp=[[20,0,0,0],[20,0,0,0]])
 state=b'synthetic-unit-only-never-native';p=tmp_path/'unit.state';m=tmp_path/'unit.state.json';p.write_bytes(state)
 m.write_bytes(build_battle_scenario_capture_payload(capture_id='extended-window-unit',root_lineage_id='synthetic-unit-only',partition=ScenarioPartition.TRAIN,state_bytes=state,initial_observation_sha256=canonical_sha256(observation(resources,0,False)),source_commit='c'*40,expected_map=15,expected_battle_state=1,observation_schema=OBSERVATION_SCHEMA_V2))
 return open_battle_scenario_capture(p,m)
class Continuation:
 policy_id='unit-common-continuation'
 def choose_main(self,*a):return BattleAction.move(1)
 def choose_switch(self,_obs,legal,**kwargs):return legal[0]

def composed(tmp_path,monkeypatch,limits=(8,32)):
 cap=capture(tmp_path);horizon,budget=(2,8) if limits is None else limits;logs={};policies=[]
 def factory():
  obj=Continuation();policies.append(obj);return obj
 def fake_run(cap,*,policy,max_decisions,max_player_turns,event_sink,session_factory,opening_idle_frames=0,**kwargs):
  assert max_decisions==budget and max_player_turns==horizon and kwargs['wild_training'] is True and kwargs['train_wild_diagnostic'] is True
  event_sink(dict(event='episode_started',manifest_sha256=cap.manifest_sha256,policy_id=policy.policy_id,max_decisions=budget,max_player_turns=horizon,opening_idle_frames=0,wild_training=True,train_wild_diagnostic=True,allow_status_moves=True));resources=dict(party_hp=[40,35],party_max_hp=[50,50],party_pp=[[20,0,0,0],[20,0,0,0]]);active=0;decisions=[]
  for number in range(1,horizon+1):
   before=deepcopy(resources);obs=observation(before,active);action=policy.choose_main(obs,object());kind='voluntary_switch' if action.party_slot else 'attack';legal_party=[i+1 for i in range(2) if i!=active]
   if kind=='attack':resources['party_pp'][active][0]-=1
   else:active=action.party_slot-1
   resources['party_hp'][active]-=1;after=deepcopy(resources);after_obs=observation(after,active)
   decision=dict(decision_index=number,kind=kind,move_slot=1 if kind=='attack' else None,party_slot=action.party_slot,observation=obs,observation_sha256=canonical_sha256(obs),after_observation_sha256=canonical_sha256(after_obs),legal_move_slots=[1],legal_party_slots=legal_party,model_input=dict(candidate_move_slots=[1],legal_mask=[True],supported_candidate_mask=[True]),frames_executed=10,opponent_hp_before=20,opponent_hp_after=20,state_before=before,state_after=after)
   event_sink(dict(event='decision_started'));event_sink(dict(event='choice_recorded',decision_index=number,selected_action=action.public_dict()));event_sink(dict(event='decision_completed',decision=decision));decisions.append(decision)
  return RedTrainerPracticeEpisode(capture_id=cap.manifest.capture_id,manifest_sha256=cap.manifest_sha256,policy_id=policy.policy_id,decisions=tuple(decisions),battle_won=False,final_battle_state=1,stop_reason='player_turn_budget',final_observation=after_obs)
 monkeypatch.setattr(cf,'run_red_trainer_practice_episode',fake_run)
 def logger(index,choice):
  directory=tmp_path/f'branch-{index}';logs[choice.semantic_ref]=directory
  return TrainerPracticeEventLog(directory,run_identity=dict(capture_id=cap.manifest.capture_id,root_lineage_id=cap.manifest.root_lineage_id,capture_manifest_sha256=cap.manifest_sha256,source_commit=cap.manifest.source_commit,partition='train',policy_id=Continuation.policy_id,first_choice_ref=choice.semantic_ref,player_turn_horizon=horizon,plan_sha256='a'*64,model_sha256='b'*64,max_decisions=budget,opening_idle_frames=0,wild_training=True,train_wild_diagnostic=True,allow_status_moves=True,native_status_context=CONTEXT))
 result=cf.collect_trainer_practice_counterfactuals(cap,session_factory=lambda:None,continuation_policy_factory=factory,first_choices=(cf.TrainerPracticeFirstChoice(BattleAction.move(1)),cf.TrainerPracticeFirstChoice(BattleAction.switch(2))),max_decisions=budget,player_turn_horizon=horizon,branch_event_log_factory=logger,allow_status_moves=True,train_wild_diagnostic=True,train_wild_limits=limits)
 assert len(policies)==2 and policies[0] is not policies[1]
 kwargs=dict(expected_choice_refs=REFS,continuation_policy_id=Continuation.policy_id,branch_event_logs=logs,plan_sha256='a'*64,model_sha256='b'*64,max_decisions=budget,expected_status_context=CONTEXT,train_wild_diagnostic=True,train_wild_limits=limits)
 document=result.public_dict();proof=admission.inspect_trainer_practice_choices(cap,document,**kwargs)
 return cap,document,proof,kwargs

def test_extended_real_collector_logs_admission_and_targets_compose(tmp_path,monkeypatch):
 cap,doc,proof,kwargs=composed(tmp_path,monkeypatch)
 assert proof['execution_proof_complete'] and proof['return_proof_complete'];assert doc['player_turn_horizon']==8
 target=targets.extract_trainer_practice_targets(proof,doc,train_wild_diagnostic=True,train_wild_limits=(8,32))
 assert target['train_wild_limits']==proof['train_wild_limits']==doc['train_wild_limits']==dict(player_turn_horizon=8,max_decisions=32)
 assert target['heads']['control']['returns']==[r['whole_party_return']['value'] for r in proof['measured_choices']]
 assert set(target['heads'])=={'control'} and target['new_independent_upstream_roots']==0
def test_legacy_none_keeps_two_turn_contract_and_omits_metadata(tmp_path,monkeypatch):
 cap,doc,proof,kwargs=composed(tmp_path,monkeypatch,None);target=targets.extract_trainer_practice_targets(proof,doc,train_wild_diagnostic=True)
 assert doc['player_turn_horizon']==2 and all('train_wild_limits' not in x for x in (doc,proof,target))
@pytest.mark.parametrize('limits',[True,False,8,[8,32],(),(8,),(8,32,1),(True,32),(8,True),(8.,32),(2,8),(8,64),(80,160),(8,32000)])
def test_unsupported_limits_reject_before_policy_or_log(tmp_path,limits):
 cap=capture(tmp_path);calls=[]
 def forbidden(*a,**kwargs):calls.append(True);raise AssertionError('must reject before branch')
 with pytest.raises(cf.TrainerPracticeCounterfactualError):cf.collect_trainer_practice_counterfactuals(cap,session_factory=forbidden,continuation_policy_factory=forbidden,first_choices=(cf.TrainerPracticeFirstChoice(BattleAction.move(1)),cf.TrainerPracticeFirstChoice(BattleAction.switch(2))),max_decisions=32,player_turn_horizon=8,branch_event_log_factory=forbidden,train_wild_diagnostic=True,train_wild_limits=limits)
 assert calls==[]
@pytest.mark.parametrize('budget,horizon,limits',[(32,8,None),(8,8,(8,32)),(31,8,(8,32)),(64,8,(8,32)),(32,7,(8,32))])
def test_declared_window_must_match_actual_collection(tmp_path,budget,horizon,limits):
 cap=capture(tmp_path)
 with pytest.raises(cf.TrainerPracticeCounterfactualError):cf.collect_trainer_practice_counterfactuals(cap,session_factory=lambda:pytest.fail('branch'),continuation_policy_factory=lambda:pytest.fail('policy'),first_choices=(cf.TrainerPracticeFirstChoice(BattleAction.move(1)),cf.TrainerPracticeFirstChoice(BattleAction.switch(2))),max_decisions=budget,player_turn_horizon=horizon,train_wild_diagnostic=True,train_wild_limits=limits)
@pytest.mark.parametrize('fault',['missing','horizon','max_decisions','float','legacy_optout','wrong_argument','boolean_argument'])
def test_extended_admission_metadata_cannot_be_forged(tmp_path,monkeypatch,fault):
 cap,doc,proof,kwargs=composed(tmp_path,monkeypatch);doc=deepcopy(doc)
 if fault=='missing':doc.pop('train_wild_limits')
 if fault=='horizon':doc['player_turn_horizon']=2
 if fault=='max_decisions':doc['train_wild_limits']['max_decisions']=64
 if fault=='float':doc['train_wild_limits']['max_decisions']=32.
 if fault=='legacy_optout':kwargs['train_wild_limits']=None
 if fault=='wrong_argument':kwargs['max_decisions']=64
 if fault=='boolean_argument':kwargs['train_wild_limits']=True
 with pytest.raises(admission.TrainerPracticeAdmissionError):admission.inspect_trainer_practice_choices(cap,doc,**kwargs)
@pytest.mark.parametrize('fault',['missing_admission','missing_document','wrong_limits','wrong_horizon','float_horizon','default_optout','proof_false'])
def test_extended_typed_target_requires_matching_proved_window(tmp_path,monkeypatch,fault):
 cap,doc,proof,kwargs=composed(tmp_path,monkeypatch);opt=(8,32)
 if fault=='missing_admission':proof.pop('train_wild_limits')
 if fault=='missing_document':doc.pop('train_wild_limits')
 if fault=='wrong_limits':proof['train_wild_limits']['max_decisions']=64
 if fault=='wrong_horizon':proof['player_turn_horizon']=2
 if fault=='float_horizon':proof['player_turn_horizon']=8.
 if fault=='default_optout':opt=None
 if fault=='proof_false':proof['execution_proof_complete']=False
 with pytest.raises(targets.TrainerPracticeTargetError):targets.extract_trainer_practice_targets(proof,doc,train_wild_diagnostic=True,train_wild_limits=opt)

def test_explicit_window_producer_rejects_float_horizon():
 result=cf.TrainerPracticeCounterfactualSet(capture_id='unit',manifest_sha256='a'*64,root_lineage_id='synthetic',player_turn_horizon=8.,branches=(),train_wild_diagnostic=True,train_wild_limits=(8,32))
 with pytest.raises(cf.TrainerPracticeCounterfactualError,match='metadata'):result.public_dict()
