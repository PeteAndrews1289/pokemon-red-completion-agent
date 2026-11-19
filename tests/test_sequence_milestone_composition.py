from pathlib import Path
from dataclasses import replace
from hashlib import sha256
import json,sys
import pytest
from test_story_branch_value import _options,_story
from test_recurrence_parent_exploration import observed_menu
from test_story_kind_commitment import readiness
from test_red_continuous_player import facts
from pokemon_red_completion.goal_manager_runtime import GoalExecutionReport
from pokemon_red_completion.player_sequence_collector import SequenceTraceCollector
from pokemon_red_completion.player_sequence_policy import SequencePolicy
from pokemon_red_completion.player_sequence_value import SequenceValueHead,sequence_feature_width
import pokemon_red_completion.red_autonomous_player as runner

@pytest.mark.parametrize("candidate",[False,True])
@pytest.mark.parametrize("seed",[1,2,3,4])
def test_milestone_keeps_branch_without_forcing_kind_and_charges_support(tmp_path,monkeypatch,candidate,seed):
 model,_=observed_menu(seen=False)
 options=_options([_story("s-a","objective-a"),_story("s-b","objective-b")],restore=False)
 options=replace(options,menu=replace(options.menu,candidates=tuple(replace(c,readiness=readiness(),features=replace(c.features,travel_effort=.1+.1*i))for i,c in enumerate(options.menu.candidates))))
 row=(.1,)+(0.,)*sequence_feature_width(16)
 head=SequenceValueHead((None,row,None,None,None,None,None),(0,2,0,0,0,0,0),"d"*64,1.,2,"b"*64,16)
 policy=SequencePolicy(model.model_sha256,head,(0.,4.,0.,0.,0.,0.,0.),1.,kind_balanced_exploration=True,continuation_behavior_sha256="b"*64)if candidate else None
 state={"n":0};calls=[]
 def execute(ref):
  calls.append(ref);state["n"]+=1;return GoalExecutionReport(1,10,{})
 def observe(_):return replace(options,bindings=tuple(replace(b,execute=lambda ref=b.binding_ref:execute(ref))for b in options.bindings))
 def snapshot():
  f=dict(facts(state["n"]),cash=5000)
  if state["n"]>=2:f["completed_objectives"]=list(f["completed_objectives"])+["objective-a"if calls[0]=="s-a"else"objective-b"]
  return runner.AutonomousSnapshot(str(state["n"]).encode(),f,True)
 collector=SequenceTraceCollector(source_sha256=sha256(b"0").hexdigest(),partition="development",horizon=2,window_stride=1,feature_version=16)
 result=runner.run_autonomous_options(model=model,output=tmp_path/"run",seed=seed,maximum_decisions=3,snapshot=snapshot,observe=observe,provenance={"source":{"partition":"development"}},continuous_player=True,maximum_cash_spent=None,story_milestone_commitment=True,sequence_collector=collector,**({"sequence_policy":policy}if policy else{}))
 assert result["executed_decisions"]==3,(result.get("stop_reason"),result.get("admission_failure"))
 assert calls[0]==calls[1]
 plan=json.loads((tmp_path/"run/plan.json").read_bytes())
 assert plan["story_branch_policy"]["kind_level_authority"]==(policy.model_sha256 if policy else model.model_sha256)

 assert json.loads((tmp_path/"run/sequence/result.json").read_bytes())["projection_error"]is None
 for outcome in result["outcomes"]:
  if outcome["support_role"]is not None:assert not outcome["learning_eligible"]
 assert sum(x["observed_cost"]["actions"]for x in result["outcomes"])==3
