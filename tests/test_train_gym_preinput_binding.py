"""Actual nested leader/gym hooks and eager controller identity; zero inputs."""
import ast
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace as N

import pytest
from test_production_train_pool import components
from test_red_live_option_menu import _binding

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_development_story_scope import DevelopmentStoryScope
from pokemon_red_completion.red_gym_reward import GymReward,MISTY_REWARD,SURGE_REWARD
from pokemon_red_completion.red_learned_trainer import TrainerPracticeThreeHeadModel,FROZEN_K_SHA256,K_QUALIFICATION_SHA256
from pokemon_red_completion.red_player_battle_history import NativeBattlerHistory
from pokemon_red_completion.red_story_battle import FrozenStoryBattleController
from pokemon_red_completion.scenario_lab import ScenarioPartition


def hooks(c,monkeypatch,*,training=True):
    helper=Path(__file__).resolve().parents[1]/"runtime_helpers/red_whole_player_inventory_20261006.py"
    tree=ast.parse(helper.read_text());assembly=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="assembly")
    selected=[next(n for n in assembly.body if isinstance(n,ast.FunctionDef) and n.name==name)
        for name in ("leader_actor","ensure_training_pool")]
    branches=next(n for n in assembly.body if isinstance(n,ast.FunctionDef) and n.name=="branches")
    selected.append(next(n for n in branches.body if isinstance(n,ast.FunctionDef) and n.name=="gym"))
    raw=N(map_id=65,battle_state=0,bag_items=(),player_money=3000)
    c.reader.read=lambda:raw
    c.delegate.pressed_buttons=()
    state=object();runtime=N(emulator=c.port,reader=c.reader,adapter=N(
        observe=lambda:N(game_state=state),graph=N(available_objectives=lambda _: [N(id="defeat_misty")])))
    base=replace(c.wild,model_sha256=FROZEN_K_SHA256,qualification_sha256=K_QUALIFICATION_SHA256,
        development_preparation_scope=None,source_partition=ScenarioPartition.TRAIN if training else ScenarioPartition.DEVELOPMENT,
        pp_depleted_switch_screen=True)
    holder=dict(actor=base,runtime=runtime,training_reader=c.reader,initial_battle=None,latest_battle=None,
        scoped_actors={},last_calls={"wild":0},plan=object(),current_matchup_witnesses=[])
    paths={k:Path(v) for k,v in json.loads(os.environ["POKEMON_PRODUCTION_TRAIN_COMPONENTS"]).items()}
    declared=c.tmp/"PLAN.json";declared.write_bytes(c.plan)
    engine=N(digest=lambda path:sha256(Path(path).read_bytes()).hexdigest(),canonical_sha256=canonical_sha256)
    monkeypatch.setattr(GymReward,"contract",lambda reward,rom,observed:c.contract)
    namespace=dict(training_admission=c.admission if training else None,holder=holder,
        include_rewards=True,include_matchup_observation=True,continuous_travel=True,
        d=N(ROOT=paths["story"].parent.parent,prior=N(doc=lambda path:json.loads(Path(path).read_bytes()))),
        c=engine,source=c.source,declared=declared,output=c.tmp,rom=b"synthetic immutable cartridge",
        route=N(rom=b"synthetic immutable cartridge",allow_surf=True),puzzle_history=[],record=lambda *a:None,
        TrainerPracticeThreeHeadModel=TrainerPracticeThreeHeadModel,DevelopmentStoryScope=DevelopmentStoryScope,
        NativeBattlerHistory=NativeBattlerHistory,replace=replace,MISTY_REWARD=MISTY_REWARD,
        preparation_actor=lambda map_id,**kwargs:c.wild,
        gym_trainer_actor=lambda _:pytest.fail("unexpected obstruction in exact Misty fixture"))
    exec(compile(ast.Module(body=selected,type_ignores=[]),str(helper),"exec"),namespace)
    return namespace,runtime,holder


def test_actual_gym_option_reaches_real_eager_controller_with_prebound_train_actor(components,monkeypatch):
    from pokemon_red_completion import red_player_gym as actual
    c=components;ns,runtime,holder=hooks(c,monkeypatch)
    seen=[]
    class AdmittedController(RuntimeError):pass
    def binding(rt,actions,*,contract,route,battler,reward):
        # Actual constructor executes exact source/model/TRAIN contract guards.
        controller=FrozenStoryBattleController(battler,(contract,),evolution_rom=route.rom)
        seen.append(controller)
        raise AdmittedController("zero-input stop after real eager controller admission")
    monkeypatch.setattr(actual,"_field_ready",lambda _:True)
    monkeypatch.setattr(actual,"story_battle_binding",binding)
    ns["gym_story_option"]=actual.gym_story_option
    with pytest.raises(AdmittedController):ns["gym"](MISTY_REWARD,runtime,object(),None)
    actor=seen[0].battler
    assert actor.model_sha256==c.story.model_sha256 and actor.train_story_contract==c.contract
    assert actor.source_partition is ScenarioPartition.TRAIN
    assert holder["actor"].model_sha256==FROZEN_K_SHA256 and holder["actor"].calls==0
    assert c.delegate.frame_count==0 and not c.delegate.pressed_buttons


@pytest.mark.parametrize("training",[True,False])
def test_train_uses_one_admitted_probe_and_default_development_retains_two_passes(components,monkeypatch,training):
    c=components;ns,runtime,holder=hooks(c,monkeypatch,training=training);seen=[]
    def probe(rt,actions,*,reward,route,battler,observe_leader_binding=None,observe_matchup_binding=None,**kwargs):
        FrozenStoryBattleController(battler,(c.contract,),evolution_rom=route.rom)
        seen.append(battler)
        binding=replace(_binding(GoalKind.ADVANCE_STORY,binding_ref="probe-"+str(len(seen)),calls=[]),
            story_objective_ref="defeat_misty")
        if observe_leader_binding:observe_leader_binding(c.contract,binding)
        if observe_matchup_binding:observe_matchup_binding(N(source="actual-current-probe"))
        return binding,OptionChallenge.from_levels(combat_levels=(19,),opponent_levels=(18,21))
    ns["gym_story_option"]=probe
    row=ns["gym"](MISTY_REWARD,runtime,object(),None)
    assert len(seen)==(1 if training else 2)
    assert [actor.model_sha256 for actor in seen]==([c.story.model_sha256] if training else [FROZEN_K_SHA256,c.story.model_sha256])
    assert row[0].story_objective_ref=="defeat_misty" and len(holder["current_matchup_witnesses"])==1
    assert c.delegate.frame_count==0


def test_foreign_train_target_rejects_before_probe_or_controller(components,monkeypatch):
    c=components;ns,runtime,holder=hooks(c,monkeypatch)
    ns["gym_story_option"]=lambda *a,**k:pytest.fail("foreign target reached probe")
    with pytest.raises(ValueError,match="declared Misty target"):
        ns["gym"](SURGE_REWARD,runtime,object(),None)
    assert not holder["scoped_actors"] and c.delegate.frame_count==0


def test_changed_native_misty_contract_is_not_guessed_or_relaxed(components,monkeypatch):
    c=components;ns,runtime,holder=hooks(c,monkeypatch)
    monkeypatch.setattr(GymReward,"contract",lambda *args:replace(c.contract,trainer_identity=(235,35,2)))
    ns["gym_story_option"]=lambda *a,**k:pytest.fail("changed contract reached probe")
    with pytest.raises(ValueError):ns["gym"](MISTY_REWARD,runtime,object(),None)
    assert c.delegate.frame_count==0
