from copy import deepcopy
from dataclasses import replace
import numpy as np
import pytest
from test_red_trainer_proposed_control import setup_case
from test_red_capped_stat_screen import observed
from pokemon_red_completion.red_battle_mechanics_boundary import capped_stat_slots,capped_stat_choices
from pokemon_red_completion.red_trainer_proposed_control import *
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel,TrainerPracticeFitError,control_schema

@pytest.mark.parametrize('move,index,direction',[(106,1,1),(104,5,1),(14,0,1),(39,1,-1),(28,4,-1)])
def test_cap_fact_does_not_apply_action_screen(move,index,direction):
    stages=[0]*6;stages[index]=6*direction
    obs,cat=observed((move,),**({'player':stages}if direction==1 else {'foe':stages}))
    assert capped_stat_slots(obs,cat,(1,))==(1,)
    assert capped_stat_choices(obs,cat,(1,))==((1,),())
    stages[index]-=direction
    assert capped_stat_slots(obs,cat,(1,))==()

def test_zero_extension_is_old_parameters_and_inactive_scores():
    _,_,model=setup_case();old=model.control;new=expand_observed_effect_control(old)
    mapping={n:i for i,n in enumerate(new.feature_names)}
    for i,n in enumerate(old.feature_names):assert np.array_equal(old.weights1[i],new.weights1[mapping[n]])
    assert np.array_equal(new.bias1,old.bias1)and np.array_equal(new.weights2,old.weights2)
    rng=np.random.default_rng(11);rows=rng.uniform(-1,1,size=(6,len(old.feature_names)))
    padded=np.zeros((6,len(new.feature_names)))
    for i,n in enumerate(old.feature_names):padded[:,mapping[n]]=rows[:,i]
    assert np.allclose(old.probabilities(rows),new.probabilities(padded),rtol=0,atol=1e-12)
    assert old.predict_index(rows)==new.predict_index(padded)
    candidate=replace(model,control=new)
    assert TrainerPracticeThreeHeadModel.from_dict(candidate.to_dict()).to_dict()==candidate.to_dict()
    with pytest.raises(TrainerPracticeFitError,match='fitted-component'):replace(candidate,control_target_mode='best_component')

def test_original_schema_and_default_are_unchanged():
    assert control_schema(PROPOSED_CONTROL_SCHEMA)==(PROPOSED_CONTROL_SCHEMA,PROPOSED_CONTROL_NAMES)
    assert control_schema(OBSERVED_EFFECT_CONTROL_SCHEMA)==(OBSERVED_EFFECT_CONTROL_SCHEMA,OBSERVED_EFFECT_CONTROL_NAMES)
    assert proposed_control.__kwdefaults__['control_schema']==PROPOSED_CONTROL_SCHEMA
