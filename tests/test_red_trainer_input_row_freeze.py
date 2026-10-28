"""Synthetic optimizer coverage; no corpus, ROM, or private paths required."""
import numpy as np
import pytest
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadModel,TrainerHeadExample
from pokemon_red_completion import red_trainer_budgeted_fit as staged

def fixtures():
 model=TrainerHeadModel('synthetic-mask',('fresh','old-a','old-b'),np.array([[.3,-.2],[-.2,.1],[.2,.4]]),np.array([.07,-0.0]),np.array([1.,-.6]),17)
 fresh=TrainerHeadExample(((1.,0.,0.),(-1.,0.,0.)),(1,),mean_returns=(0.,3.))
 vectors=((0.,1.,0.),(0.,0.,1.));winner=model.predict_index(vectors)
 old=TrainerHeadExample(vectors,(winner,),mean_returns=tuple(2. if i==winner else 0. for i in range(2)))
 return model,fresh,old,(staged.RegretBudget('old',(old,),0.),)

def bits(array):return array.tobytes()

def test_actual_toy_learning_keeps_zero_support_history_and_frozen_bits():
 model,fresh,old,budgets=fixtures();before=model.to_dict();old_scores=model.scores(old.candidate_vectors)
 fitted,receipt=staged.fit_budgeted_head(model,(fresh,),(old,),budgets,epochs=180,learning_rate=.02,objective='pairwise_regret',trainable_input_rows=(0,))
 assert fitted is not None and staged.selected_regret(fitted,(fresh,))==0
 assert bits(fitted.weights1[0])!=bits(model.weights1[0])
 assert bits(fitted.weights1[1:])==bits(model.weights1[1:])
 assert bits(fitted.bias1)==bits(model.bias1) and bits(fitted.weights2)==bits(model.weights2)
 assert bits(fitted.scores(old.candidate_vectors))==bits(old_scores)
 assert all(h['budgets']['old']==0. and h['feasible'] for h in receipt['history'])
 assert model.to_dict()==before
 scope=receipt['parameter_update_scope'];assert scope['trainable_input_rows']==[0] and scope['trainable_coordinates']==2 and scope['bias1_frozen'] and scope['weights2_frozen']


@pytest.mark.parametrize('rows',[(),[0],(True,),(False,),(0.,),(-1,),(3,),(0,0),'0',0])
def test_invalid_rows_rejected_before_loss(monkeypatch,rows):
 model,fresh,old,budgets=fixtures()
 monkeypatch.setattr(staged,'pairwise_loss_gradient',lambda *a:pytest.fail('invalid mask reached optimizer work'))
 with pytest.raises(ValueError,match='input-row'):staged.fit_budgeted_head(model,(fresh,),(old,),budgets,epochs=1,objective='pairwise_regret',trainable_input_rows=rows)

@pytest.mark.parametrize('rule',['projected_budget_v1','joint_ranking_v1','joint_ranking_curvature_v1'])
def test_partial_freeze_rejects_unsupported_update_before_loss(monkeypatch,rule):
 model,fresh,old,budgets=fixtures();monkeypatch.setattr(staged,'pairwise_loss_gradient',lambda *a:pytest.fail('unsupported backend reached fit'))
 with pytest.raises(ValueError,match='input-row'):staged.fit_budgeted_head(model,(fresh,),(old,),budgets,epochs=1,objective='pairwise_regret',update_rule=rule,trainable_input_rows=(0,))

def test_mask_does_not_relax_incompatible_numeric_budget():
 model,fresh,old,_=fixtures()
 protected=TrainerHeadExample(fresh.candidate_vectors,(0,),mean_returns=(3.,0.))
 fitted,receipt=staged.fit_budgeted_head(model,(fresh,),(old,),(staged.RegretBudget('strict',(protected,),0.),),epochs=90,learning_rate=.02,objective='pairwise_regret',trainable_input_rows=(0,))
 assert fitted is not None and staged.selected_regret(fitted,(protected,))==0.
 assert staged.selected_regret(fitted,(fresh,))==3.
 assert receipt['feasible_checkpoints']>=1

def test_masked_head_codec_preserves_schema_scores_and_readonly_arrays():
 model,fresh,old,budgets=fixtures();fitted,_=staged.fit_budgeted_head(model,(fresh,),(old,),budgets,epochs=30,objective='pairwise_regret',trainable_input_rows=(0,2))
 restored=TrainerHeadModel.from_dict(fitted.to_dict(),schema_id=model.schema_id,feature_names=model.feature_names)
 assert restored.to_dict()==fitted.to_dict()
 assert bits(restored.scores(fresh.candidate_vectors))==bits(fitted.scores(fresh.candidate_vectors))
 assert not restored.weights1.flags.writeable and not restored.bias1.flags.writeable and not restored.weights2.flags.writeable
