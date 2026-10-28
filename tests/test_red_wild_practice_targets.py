"""TRAIN-only wild target extraction preserves native measured outcomes."""
import pytest
from pokemon_red_completion import red_trainer_practice_targets as w
from test_red_trainer_practice_targets import _contrast

def pair(tie=False):
 a,d=_contrast();indices=[0,2]
 a['measured_choices']=[a['measured_choices'][i] for i in indices];d['branches']=[d['branches'][i] for i in indices]
 a.update(schema='pokemon.red.wild-practice-admission.v1',train_wild_diagnostic=True,expected_battle_state=1)
 d.update(schema='pokemon.red.wild-practice-counterfactual-set.v1',wild_training=True,train_wild_diagnostic=True,expected_battle_state=1,player_turn_horizon=2,branch_count=2)
 if tie:a['measured_choices'][1]['whole_party_return']['value']=a['measured_choices'][0]['whole_party_return']['value']
 return a,d
def test_wild_default_rejects_and_explicit_target_preserves_actual_returns():
 a,d=pair()
 with pytest.raises(w.TrainerPracticeTargetError):w.extract_trainer_practice_targets(a,d)
 t=w.extract_trainer_practice_targets(a,d,train_wild_diagnostic=True)
 assert t['train_wild_diagnostic'] and t['heads']['control']['returns']==[1.0,0.9]
 assert set(t['heads'])=={'control'} and t['new_independent_upstream_roots']==0
def test_equal_return_pair_remains_tied_without_attack_label():
 a,d=pair(tie=True);t=w.extract_trainer_practice_targets(a,d,train_wild_diagnostic=True)
 assert t['heads']['control']['best_indices']==[0,1] and t['heads']['control']['returns']==[1.0,1.0]
@pytest.mark.parametrize('fault',['admission_flag','doc_flag','schema','state','partition','proof','count','horizon','inventory','optin_bool'])
def test_wild_semantic_negative(fault):
 a,d=pair();flag=True
 if fault=='admission_flag':a['train_wild_diagnostic']=False
 if fault=='doc_flag':d['wild_training']=False
 if fault=='schema':a['schema']='pokemon.red.trainer-practice-admission.v1'
 if fault=='state':a['expected_battle_state']=2
 if fault=='partition':a['partition']='development'
 if fault=='proof':a['execution_proof_complete']=False
 if fault=='count':d['branch_count']=3
 if fault=='horizon':d['player_turn_horizon']=3
 if fault=='inventory':d['branches'][1]['episode']['decisions'][0]['kind']='forced_switch'
 if fault=='optin_bool':flag=1
 with pytest.raises(w.TrainerPracticeTargetError):w.extract_trainer_practice_targets(a,d,train_wild_diagnostic=flag)
