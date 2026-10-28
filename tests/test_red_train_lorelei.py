"""ROM-free strict TRAIN identity and existing real lifecycle composition."""
from dataclasses import replace
from types import SimpleNamespace as NS
import numpy as np
import pytest
import test_red_lorelei_story as lifecycle
from test_red_trainer_story import fixture as story_fixture
from pokemon_red_completion import red_train_lorelei as m
from pokemon_red_completion import red_player_league_options as options
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_learned_trainer import FrozenTrainerBattler,FROZEN_K_SHA256,K_QUALIFICATION_SHA256
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel, CONTROL_ACTION_SCHEMA_ID, CONTROL_ACTION_FEATURE_NAMES
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel
from pokemon_red_completion.red_trainer_practice_features import (
    MOVE_SCHEMA_ID,MOVE_FEATURE_NAMES,CONTROL_SCHEMA_ID,CONTROL_FEATURE_NAMES_V2,
    SWITCH_SCHEMA_ID,SWITCH_FEATURE_NAMES_V2)
from pokemon_red_completion.scenario_lab import ScenarioPartition

def controller(tmp_path,monkeypatch):
    # Synthetic actual model object for lifecycle tests; no fit or production pin weakening.
    def head(schema,names):
        return TrainerHeadModel(schema,names,np.zeros((len(names),2)),np.zeros(2),np.zeros(2),0)
    model=TrainerPracticeThreeHeadModel(head(MOVE_SCHEMA_ID,MOVE_FEATURE_NAMES),
        head(CONTROL_ACTION_SCHEMA_ID,CONTROL_ACTION_FEATURE_NAMES),
        head(SWITCH_SCHEMA_ID,SWITCH_FEATURE_NAMES_V2),('capture',),('root',))
    monkeypatch.setattr(m,'K_CONTENT_SHA256',canonical_sha256(model.to_dict()))
    c=lifecycle.contract()
    b=FrozenTrainerBattler(None,model,tmp_path,'a'*40,'original-train','b'*64,{},
        model_sha256=FROZEN_K_SHA256,qualification_sha256=K_QUALIFICATION_SHA256,
        source_partition=ScenarioPartition.TRAIN,train_story_contract=c)
    return m.FrozenTrainLoreleiStoryController(b,c,m.train_lorelei_admission(b,c,73),73)

@pytest.mark.parametrize('change',[
    ('source_partition',ScenarioPartition.DEVELOPMENT),('root_lineage_id','another'),
    ('source_state_sha256','c'*64),('model_sha256','d'*64),('qualification_sha256','e'*64),
    ('train_story_contract',replace(lifecycle.contract(),victory_money=1)),
    ('train_funding_diagnostic',True),('train_risk_story_scope',object()),
    ('evaluation_story_scope',object()),('development_story_scope',object()),
    ('development_preparation_scope',object()),('story_chain_scope',object()),
    ('pp_depleted_switch_screen',True),('mechanics_aware_tower_choices',True),
    ('diagnostic_tower_productive_stay',True)])
def test_changed_identity_refused_before_inputs(tmp_path,monkeypatch,change):
    ctl=controller(tmp_path,monkeypatch)
    setattr(ctl.battler,*change)
    with pytest.raises(ValueError):ctl.require_identity()
    assert not list(tmp_path.iterdir())

def test_actual_weight_mutation_cannot_keep_qualified_labels(tmp_path,monkeypatch):
    ctl=controller(tmp_path,monkeypatch)
    move=ctl.battler.model.move;weights=move.weights1.copy();weights[0,0]=.5
    ctl.battler.model=replace(ctl.battler.model,move=replace(move,weights1=weights))
    assert ctl.battler.model_sha256==FROZEN_K_SHA256
    with pytest.raises(ValueError,match='qualified K'):ctl.require_identity()
    assert not list(tmp_path.iterdir())

@pytest.mark.parametrize('mode',['won','lost','unresolved'])
def test_existing_lifecycle_retains_ordinary_loss_and_forbids_teacher(tmp_path,monkeypatch,mode):
    ctl=controller(tmp_path,monkeypatch)
    monkeypatch.setattr(lifecycle,'controller',lambda p:ctl)
    lifecycle.test_real_story_lifecycle_retains_outcome_and_never_calls_teacher(tmp_path,monkeypatch,mode)

def test_real_first_challenge_option_constructs_and_binds_train_owner(tmp_path,monkeypatch):
    skill,reader,inputs,observe,_=story_fixture.__wrapped__(monkeypatch)
    ctl=controller(tmp_path,monkeypatch);rt=skill.runtime
    rt.league_story_battle_controller=ctl
    rt.emulator.save_state_bytes=lambda:b'original-train'
    monkeypatch.setattr(options,'_field_ready',lambda r:True)
    monkeypatch.setattr(options,'trainer_party_quote',lambda *a:skill._quote(244,1))
    route=NS(route_world=skill.world,rom=skill.world.rom)
    result=options.league_story_option(rt,skill.actions,route=route,combat_levels=(63,55),history=lambda:None,rematch=False)
    assert result is not None and result[0].story_objective_ref=='defeat_lorelei'
    assert not inputs and ctl.battler.source_partition is ScenarioPartition.TRAIN
    assert lifecycle.bridge.story_league_controller(rt,'defeat_lorelei') is ctl
    # The legacy default remains rematch=True and is not silently admitted here.
    assert options.league_story_option(rt,skill.actions,route=route,combat_levels=(63,55),history=lambda:None) is None
    for kwargs in ({'rematch':False,'development_retry_reentry':True},{'rematch':1}):
        with pytest.raises(ValueError):
            options.league_story_option(rt,skill.actions,route=route,combat_levels=(63,55),history=lambda:None,**kwargs)
    skill.recovery_controller=ctl.controller_name
    skill.maximum_level_deficit=100
    assert not skill.availability(observe().game_state).executable
    assert not inputs

def test_bound_skill_rechecks_source_and_no_rematch(tmp_path,monkeypatch):
    skill,reader,inputs,observe,_=story_fixture.__wrapped__(monkeypatch)
    ctl=controller(tmp_path,monkeypatch)
    skill.runtime.league_story_battle_controller=ctl;skill.recovery_controller=ctl.controller_name
    assert skill.availability(observe().game_state).executable
    ctl.battler.root_lineage_id='changed'
    with pytest.raises(ValueError):skill.execute()
    assert not inputs


@pytest.mark.parametrize('location',[9,174])
def test_first_challenge_entry_uses_scripted_arrival_without_retry(tmp_path,monkeypatch,location):
    from dataclasses import dataclass
    from pokemon_red_completion import gen1_scripted_arrival as arrival
    skill,reader,inputs,observe,_=story_fixture.__wrapped__(monkeypatch)
    reader.raw=replace(reader.raw,map_id=location)
    ctl=controller(tmp_path,monkeypatch)
    skill.runtime.league_story_battle_controller=ctl;skill.recovery_controller=ctl.controller_name
    @dataclass
    class World:
        rom:bytes
        plan_feasible_to_map:object
        replanner:object
        macro_graph:object
    skill.world=World(skill.world.rom,skill.world.plan_feasible_to_map,skill.world.replanner,'graph')
    seen=[];declared=NS(steps=('settle',))
    def lookup(rom,target,events,**kwargs):
        assert target==245 and events==reader.raw.event_flags and not kwargs
        seen.append(target);return declared
    def bind(graph,value):
        assert graph=='graph' and value is declared
        return 'arrival-bound-graph'
    monkeypatch.setattr(arrival,'trainer_room_arrival',lookup)
    monkeypatch.setattr(arrival,'with_scripted_trainer_arrival',bind)
    assert skill.availability(observe().game_state).executable
    assert seen==[245] and skill._arrival is declared and not inputs
    assert skill._lobby_events is None and skill._lobby_reset_latch is None

def test_historical_completion_does_not_enable_train_rematch(tmp_path,monkeypatch):
    skill,reader,inputs,observe,_=story_fixture.__wrapped__(monkeypatch)
    ctl=controller(tmp_path,monkeypatch)
    skill.runtime.league_story_battle_controller=ctl;skill.recovery_controller=ctl.controller_name
    def historical():
        v=observe()
        return replace(v,game_state=replace(v.game_state,facts=v.game_state.facts|{'league:lorelei_defeated'}))
    skill.runtime.adapter.observe=historical
    assert not skill.availability(historical().game_state).executable
    skill.rematch=True
    assert not skill.availability(historical().game_state).executable
    assert not inputs
