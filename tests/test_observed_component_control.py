from copy import deepcopy
from dataclasses import replace
import numpy as np
from test_red_trainer_proposed_control import setup_case
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_trainer_practice_features import *
from pokemon_red_completion.red_trainer_proposed_control import *
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel

def test_pp_fact_counts_owned_nonstatus_pp_without_changing_inventory():
    target,_,_=setup_case();obs=deepcopy(target['observation']);moves=[dict(move_ref='pokemon.red.gb.us.rev0:move:106',pp=30,slot_index=0),dict(move_ref='pokemon.red.gb.us.rev0:move:033',pp=0,slot_index=1)]
    obs['features']['party']['members'][1]['moves']=moves;catalog=PokemonRedBattleCatalog();before=deepcopy(obs)
    assert no_nonstatus_pp(obs,catalog,2)==1.;assert obs==before
    moves[1]['pp']=1;assert no_nonstatus_pp(obs,catalog,2)==0.
    moves[0]['pp']=0;moves[1]['pp']=0;assert no_nonstatus_pp(obs,catalog,2)==1.

def test_zero_extensions_preserve_both_components_and_round_trip():
    target,_,model=setup_case();effect=expand_observed_effect_control(model.control);control=expand_observed_component_control(effect);switch=expand_observed_pp_switch(model.switch);candidate=replace(model,control=control,switch=switch)
    assert TrainerPracticeThreeHeadModel.from_dict(candidate.to_dict()).to_dict()==candidate.to_dict()
    for old,new in [(effect,control),(model.switch,switch)]:
        indices={n:i for i,n in enumerate(new.feature_names)}
        for i,n in enumerate(old.feature_names):assert np.array_equal(old.weights1[i].view(np.uint64),new.weights1[indices[n]].view(np.uint64))
        assert np.array_equal(old.bias1,new.bias1)and np.array_equal(old.weights2,new.weights2)
        rng=np.random.default_rng(32);rows=rng.uniform(-1,1,size=(4,len(old.feature_names)));padded=np.zeros((4,len(new.feature_names)))
        for i,n in enumerate(old.feature_names):padded[:,indices[n]]=rows[:,i]
        assert np.allclose(old.probabilities(rows),new.probabilities(padded),rtol=0,atol=1e-12)
        assert old.predict_index(rows)==new.predict_index(padded)
    legacy=project_trainer_switch_features(target['observation'],PokemonRedBattleCatalog());new=project_switch_for_head(target['observation'],PokemonRedBattleCatalog(),switch)
    assert legacy.candidate_slots==new.candidate_slots
    assert [row[:-1]for row in new.candidate_vectors]==list(legacy.candidate_vectors)
