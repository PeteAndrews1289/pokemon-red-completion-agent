from dataclasses import replace
import pytest
from test_red_live_option_menu import _model
from test_story_unit_v16 import candidate,context
from pokemon_red_completion.living_dex_option_value import LivingDexOptionMenu,LivingDexOptionKind,upgrade_option_value_model_for_story_unit,option_feature_names
from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY as U
from pokemon_red_completion.player_option_preparation import OptionPreparation
from pokemon_red_completion.resource_economy_observation import EconomySnapshot,EconomyOffer,EconomyMode
from pokemon_red_completion.player_sequence_value import SequenceValueHead,sequence_feature_width
from pokemon_red_completion.player_sequence_policy import SequencePolicy,SequenceChoiceContext
from pokemon_red_completion.player_sequence_targets import RESOURCE_TASK_TARGET_CONTRACT,TASK_TERMINAL_TARGET_CONTRACT,sequence_target_names,sequence_targets
from pokemon_red_completion.player_short_sequence import MeasuredSequenceStep,SequenceEnd,measure_sequence
from pokemon_red_completion.recorded_branch_history import RecordedBranchHistory

def test_replacement_cost_is_explicit_and_never_relabeled_observed_cash_spent():
 step=MeasuredSequenceStep('a'*64,'b'*64,'c'*64,'d'*64,100,1000,1000,1,progress=('owned:16',),cash_credits=5639)
 m=measure_sequence((step,),horizon=4,end=SequenceEnd.TASK_TERMINAL)
 t=sequence_targets(m,covered=frozenset(sequence_target_names(RESOURCE_TASK_TARGET_CONTRACT)),target_contract=RESOURCE_TASK_TARGET_CONTRACT,priced_medicine_depletion=19500)
 assert t.raw[4]==20500 and m.cash_debits==1000 and t.raw[0]==1
 assert t.values[4]==20500/21500 and all(t.known)
 with pytest.raises(ValueError):sequence_targets(m,target_contract=RESOURCE_TASK_TARGET_CONTRACT)
 with pytest.raises(ValueError):sequence_targets(m,target_contract=TASK_TERMINAL_TARGET_CONTRACT,priced_medicine_depletion=19500)

def fixture():
 model=upgrade_option_value_model_for_story_unit(_model());base=candidate();prep=replace(base,binding_ref='p',features=replace(base.features,kind=LivingDexOptionKind.DEVELOP),preparation=OptionPreparation(50,51,7000,1.0,1.0,False,True,None))
 earn=replace(base,binding_ref='e',features=replace(base.features,kind=LivingDexOptionKind.RESUPPLY),economy_offer=EconomyOffer(EconomyMode.EARN,1000))
 buy=replace(earn,binding_ref='b',economy_offer=EconomyOffer(EconomyMode.PURCHASE,0,1000));other=replace(base,binding_ref='x',features=replace(base.features,kind=LivingDexOptionKind.EXPLORE))
 ctx=replace(context(),resource_pressure=1.0,economy_snapshot=EconomySnapshot(8,()),target_cash=1000);menu=LivingDexOptionMenu(ctx,(prep,earn,buy,other));zero=RecordedBranchHistory(0,0,0,0,0,0,0,0);choice=SequenceChoiceContext(menu.policy_sha256,'c'*64,(zero,)*4,feature_version=16)
 width=sequence_feature_width(16);params=[]
 for i,v in enumerate((.5,0.0,.2,.2,.8,.9,.5)):
  row=[v]+[0.0]*width
  if i in(2,3):row[1+option_feature_names(16).index('kind.develop')]=.3
  params.append(tuple(row))
 head=SequenceValueHead(tuple(params),(3,)*7,'a'*64,1.0,4,model.model_sha256,16,TASK_TERMINAL_TARGET_CONTRACT)
 prior=SequencePolicy(model.model_sha256,head,(0.,4.,-.2,-.1,-.5,.5,0.),1.,selection_mode='stable')
 new=replace(head,target_contract=RESOURCE_TASK_TARGET_CONTRACT);utility=(U.completion_gain_weight,U.success_weight,-U.action_cost_weight,-U.frame_cost_weight,-U.resource_cost_weight,U.resource_cost_weight,0.)
 policy=SequencePolicy(model.model_sha256,new,utility,1.,selection_mode='stable',retained_policy=prior,supported_kinds=('develop','resupply'),support_evidence_sha256='e'*64,task_return_scope='resource-pressure-one-with-earning-peer-v1')
 return model,menu,choice,prior,policy

def test_whole_task_return_replaces_unit_success_and_preserves_untrained_peers():
 model,menu,ctx,prior,p=fixture();a=p.scores(model,menu,ctx);old=prior.scores(model,menu,ctx);forecast=p.head.score_menu(menu,histories=ctx.histories,utility=p.sequence_utility)
 assert a[0]==forecast[0]and a[1]==forecast[1]and a[1]>a[0]
 assert a[2:]==old[2:]and menu.available_indices==(0,1,2,3)

@pytest.mark.parametrize('fault',['pressure','economy','earning'])
def test_public_support_gate_preserves_exact_prior_scores(fault):
 model,menu,ctx,prior,p=fixture()
 if fault=='pressure':menu=replace(menu,context=replace(menu.context,resource_pressure=.9))
 if fault=='economy':menu=replace(menu,context=replace(menu.context,economy_snapshot=None,target_cash=None),candidates=tuple(replace(c,economy_offer=None)for c in menu.candidates))
 if fault=='earning':menu=replace(menu,candidates=(menu.candidates[0],menu.candidates[2],menu.candidates[3]))
 ctx=replace(ctx,menu_sha256=menu.policy_sha256,histories=ctx.histories[:len(menu.candidates)])
 assert p.scores(model,menu,ctx)==prior.scores(model,menu,ctx)

def test_identity_roundtrip_and_private_renaming_parity():
 model,menu,ctx,prior,p=fixture();doc=p.document();q=SequencePolicy.from_document(doc,expected_sha256=p.model_sha256);assert q.document()==doc and q.scores(model,menu,ctx)==p.scores(model,menu,ctx)
 renamed=replace(menu,candidates=tuple(replace(c,binding_ref='new-'+str(i))for i,c in enumerate(reversed(menu.candidates))));other=replace(ctx,menu_sha256=renamed.policy_sha256,histories=tuple(reversed(ctx.histories)));assert p.scores(model,renamed,other)==tuple(reversed(p.scores(model,menu,ctx)))
 assert 'task_return_scope'not in prior.document()

def test_incompatible_utility_or_missing_mode_rejected():
 *_,p=fixture()
 with pytest.raises(ValueError):replace(p,sequence_utility=(0.,*p.sequence_utility[1:]))
 with pytest.raises(ValueError):replace(p,task_return_scope=None)

def test_one_existing_retention_layer_can_be_preserved_but_deeper_chains_reject():
 model,menu,ctx,prior,p=fixture();inner=replace(prior,retained_policy=prior,supported_kinds=('unlock_access',),support_evidence_sha256='d'*64);outer=replace(p,retained_policy=inner);assert outer.retained_policy.model_sha256==inner.model_sha256
 with pytest.raises(ValueError):replace(p,retained_policy=outer)
