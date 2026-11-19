"""Milestone support needs its own sealed opt-in, not kind forcing."""
import json
from dataclasses import replace
import pytest
from test_red_native_player import setup
from test_story_branch_value import _story
from test_recurrence_parent_exploration import observed_menu
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
from pokemon_red_completion.red_live_option_menu import supplemental_live_option
from pokemon_red_completion.red_native_player import run_native_continuous_player
from pokemon_red_completion.red_sequence_native_audit import audit_native_sequence_trace, _require_story_support_opt_in
from pokemon_red_completion.provenance import canonical_sha256


def read(p):return json.loads(p.read_bytes())


def test_milestone_only_native_trace_keeps_support_unaudited_and_costed(tmp_path,monkeypatch):
 args,executed=setup(tmp_path,monkeypatch)
 model,_=observed_menu(seen=False)
 args.update(model=model,sequence_horizon=2,story_milestone_commitment=True)
 args['limits']=replace(args['limits'],actions=6,decisions=6)
 def bindings(runtime,actions,observation):
  b=runtime.enumerator(actions).enumerate(observation);first=replace(b.bindings[0],story_objective_ref='objective-a',story_approach_only=True,story_unit=_story('a','objective-a').story_unit)
  return GoalBindingSet((first.opportunity,b.bindings[1].opportunity),(first,b.bindings[1]))
 def extra(runtime,actions,observation,b):
  first=replace(b.bindings[0],binding_ref='other-story',story_objective_ref='objective-b')
  q=GoalBindingSet((first.opportunity,b.bindings[1].opportunity),(first,b.bindings[1])).question(observation.situation)
  candidate=project_living_dex_goal_candidate(q,0,feature_version=16,binding_ref=first.binding_ref)
  return (supplemental_live_option(first,replace(candidate,story_unit=first.story_unit)),)
 args.update(enumerate_bindings=bindings,enumerate_supplements=extra)
 # Fixed numerical scorer;real sampler,executor,sealed records and audit remain active.
 monkeypatch.setattr(type(model),'scores',lambda self,menu,utility:tuple(-1000. if c.features.kind.value=='develop' else 0. for c in menu.candidates))
 result=run_native_continuous_player(**args);root=args['output']
 assert result['executed_decisions']==6 and result['support_decisions']>0
 audit=audit_native_sequence_trace(root,store=args['store'],model=model,expected_native_plan_sha256=canonical_sha256(read(root/'native-plan.json')),expected_actor_result_sha256=canonical_sha256(read(root/'episode/result.json')),source_sha256=args['source']['state_sha256'])
 assert audit.actions==6 and audit.support_requiring_authority_audit>0
 assert not audit.training_eligible and not audit.safety_and_executor_authority_verified
 assert executed==[2,4,6,8,10,12]


@pytest.mark.parametrize('kind_override,flags,accepted',[
 (False,{'story_milestone_commitment':True},True),
 (False,{'story_kind_commitment':True},False),
 (True,{'story_milestone_commitment':True},False),
 (True,{'story_kind_commitment':True},True),
 (False,{},False),
])
def test_wrong_support_flag_cannot_authorize_other_support(tmp_path,kind_override,flags,accepted):
 (tmp_path/'story-kind-commitment.json').write_text(json.dumps({'overridden':kind_override}))
 if accepted:_require_story_support_opt_in(tmp_path,flags)
 else:
  with pytest.raises(ValueError,match='story support opt-in'):_require_story_support_opt_in(tmp_path,flags)
