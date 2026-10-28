"""Exact scoped TRAIN story registry; default observer inventory unchanged."""
import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace as N

import pytest
from test_production_train_pool import components
from test_red_live_option_menu import _binding
from test_train_gym_preinput_binding import hooks

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.player_option_challenge import OptionChallenge
from pokemon_red_completion.red_gym_reward import MISTY_REWARD
from pokemon_red_completion.red_player_story_menu import registered_story_branches


@pytest.mark.parametrize("training",[True,False])
def test_actual_registry_observes_only_admitted_train_target_and_preserves_development(components,monkeypatch,training):
    c=components;ns,runtime,holder=hooks(c,monkeypatch,training=training)
    helper=Path(__file__).resolve().parents[1]/"runtime_helpers/red_whole_player_inventory_20261006.py"
    tree=ast.parse(helper.read_text())
    assembly=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="assembly")
    branches=next(n for n in assembly.body if isinstance(n,ast.FunctionDef) and n.name=="branches")
    legal=("defeat_misty","help_bill","reach_vermilion")
    runtime.adapter.graph=N(available_objectives=lambda state:[N(id=o) for o in legal],objective=lambda key:N(id=key))
    ns["d"].observe_preparation_members=lambda *args:()
    ns["c"].MapId=N(BILLS_HOUSE=88)
    ns.update(REWARDS=(MISTY_REWARD,),ARRIVAL_OBJECTIVES=("reach_vermilion",),
        LEAGUE_PLAYER_TARGETS=(),CHAMPION_PLAYER_TARGET=N(objective_id="become_champion"),
        include_silph_continuation=False,registered_story_branches=registered_story_branches,
        OptionChallenge=OptionChallenge)
    observed=[]
    def row(objective):
        observed.append(objective)
        binding=replace(_binding(GoalKind.ADVANCE_STORY,binding_ref="observed-"+objective,calls=[]),
            story_objective_ref=objective)
        return binding,OptionChallenge(False,False,0.,0.,0.)
    def gym(rt,actions,*,reward,observe_leader_binding=None,**kwargs):
        result=row(reward.objective_id)
        if observe_leader_binding:observe_leader_binding(c.contract,result[0])
        return result
    ns["gym_story_option"]=gym
    ns["bill_story_option"]=lambda *args,**kwargs:row("help_bill")
    ns["story_travel_binding"]=lambda *args,objective_id,**kwargs:row(objective_id)[0]
    exec(compile(ast.Module(body=[branches],type_ignores=[]),str(helper),"exec"),ns)
    result=ns["branches"](runtime,object(),runtime.adapter.observe())
    expected={"defeat_misty"} if training else set(legal)
    assert {binding.story_objective_ref for binding,_ in result}==expected
    assert set(observed)==expected
    # DEV still invokes both existing gym passes; TRAIN binds its actor once.
    assert observed.count("defeat_misty")== (1 if training else 2)
    assert set(holder["configured_native_capabilities"])==expected if training else expected.issubset(holder["configured_native_capabilities"])
    assert holder["legal_native_objectives"]==sorted(legal)
    assert holder["missing_native_capabilities"]==(["help_bill","reach_vermilion"] if training else [])
    assert c.delegate.frame_count==0 and not c.delegate.pressed_buttons
