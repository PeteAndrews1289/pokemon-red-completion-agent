"""Synthetic-only semantics, constrained math, retention and codec checks."""
from dataclasses import replace
from types import SimpleNamespace
import hashlib

import numpy as np
import pytest
import pokemon_red_completion.living_dex_option_value as m
from test_living_dex_option_value import _settled
from test_success_head_retention import parent

SUCCESS = m.LIVING_DEX_OPTION_OUTCOME_NAMES.index('verified_success')
OTHER = [i for i in range(9) if i != SUCCESS]


def vector(kind='unlock_access', **updates):
    names=m.option_feature_names(9); x=np.zeros(len(names))
    x[names.index('kind.'+kind)]=1.
    x[names.index('execution_effort')]=.1
    x[names.index('execution_effort_x_kind.'+kind)]=.1
    for key,value in updates.items():x[names.index(key)]=value
    return x


def evidence():
    names=m.option_feature_names(9)
    vectors=[vector(),vector(**{'execution_effort':.2,'execution_effort_x_kind.unlock_access':.2}),
        vector(**{'readiness.unlock_access_x_observed':1.,'readiness.unlock_access_x_current.hp_fraction':.5}),
        vector(**{'challenge.unlock_access_x_present':1.,'challenge.unlock_access_x_combat_required':1.,'challenge.unlock_access_x_opposition_known':1.,'challenge.unlock_access_x_opponent_fraction':.5}),
        vector(**{'readiness.unlock_access_x_observed':1.,'readiness.unlock_access_x_current.pp_known':1.,'readiness.unlock_access_x_current.pp_fraction':1.}),
        vector(**{'readiness.unlock_access_x_observed':1.,'readiness.unlock_access_x_current.pp_known':1.,'readiness.unlock_access_x_current.pp_fraction':.5}),
        vector(**{'challenge.unlock_access_x_present':1.,'challenge.unlock_access_x_combat_required':1.,'challenge.unlock_access_x_opposition_known':1.,'challenge.unlock_access_x_opponent_fraction':.5,'challenge.unlock_access_x_median_level_deficit':.2}),
        vector('evolve'),vector('restore')]
    examples=tuple(m.LivingDexCurriculumOutcomeExample(hashlib.sha256(f'synthetic-story-{i}'.encode()).hexdigest(),'train',9,tuple(map(float,x)),_settled(success=bool(i%2),completion=.1,unlock=.2,action_cost=.1))for i,x in enumerate(vectors))
    return parent(),examples,tuple(r.decision_sha256 for r in examples[:4])


def fit(base,rows,ids,**kwargs):
    return m.fit_living_dex_option_value((),curriculum_examples=rows,feature_version=9,
        frozen_success_base=base,story_success_retention_decision_sha256s=ids,**kwargs)


def test_fixed_complete36_retains_anchors_nonstory_and_every_other_quantity():
    base,rows,ids=evidence();old=base.to_dict();documents=[r.public_dict()for r in rows]
    result=fit(base,rows,ids);model=result.model;x=np.asarray([r.features for r in rows]);a=base.raw_predictions(x);b=model.raw_predictions(x)
    np.testing.assert_allclose(b[:4,SUCCESS],a[:4,SUCCESS],atol=1e-10,rtol=0)
    np.testing.assert_allclose(b[7:,SUCCESS],a[7:,SUCCESS],atol=1e-10,rtol=0)
    np.testing.assert_array_equal(b[:,OTHER],a[:,OTHER])
    np.testing.assert_array_equal(model.coefficients[:,OTHER],base.coefficients[:,OTHER])
    np.testing.assert_array_equal(model.intercept[OTHER],base.intercept[OTHER])
    np.testing.assert_array_equal(model.feature_mean,base.feature_mean)
    np.testing.assert_array_equal(model.feature_scale,base.feature_scale)
    assert model.economy_head is base.economy_head
    columns=m._story_success_feature_columns(x,9);assert len(columns)==36
    outside=[i for i in range(len(x[0]))if i not in columns]
    np.testing.assert_array_equal(model.coefficients[outside],base.coefficients[outside])
    delta=model.coefficients[list(columns),SUCCESS]-base.coefficients[list(columns),SUCCESS]
    assert model.intercept[SUCCESS]-base.intercept[SUCCESS]==pytest.approx((base.feature_mean[list(columns)]/base.feature_scale[list(columns)])@delta,abs=1e-12)
    assert any(abs(b[i,SUCCESS]-a[i,SUCCESS])>.01 for i in (4,5,6))
    assert model.objective==m.LIVING_DEX_STORY_SUCCESS_RETAINED_OBJECTIVE
    report=result.report.public_dict();ret=report['story_success_retention']
    assert ret['protected_count']==4 and ret['feature_group']=='complete-story-context-v1'
    assert ret['trainable_feature_indices']==list(columns)
    assert ret['independent_global_intercept']is False and ret['nonstory_rows']==2
    assert ret['maximum_nonstory_raw_output_error']<=1e-10
    assert report['fitted_outcome_names']==['verified_success']and report['outcome_balance_required']
    assert 'party_cost_retention'not in report
    assert model.train_dataset_sha256==m.living_dex_option_train_dataset_sha256((),curriculum_examples=rows)
    assert base.to_dict()==old and [r.public_dict()for r in rows]==documents


def test_codec_and_v10_zero_extension_preserve_all_forecasts():
    base,rows,ids=evidence();model=fit(base,rows,ids).model
    restored=m.LivingDexOptionValueModel.from_dict(model.to_dict())
    assert restored.model_sha256==model.model_sha256
    extended=m.upgrade_option_value_model_for_move_change(restored)
    assert extended.feature_version==10 and extended.objective==model.objective
    assert m.LivingDexOptionValueModel.from_dict(extended.to_dict()).model_sha256==extended.model_sha256
    x=np.asarray([r.features for r in rows]);y=np.pad(x,((0,0),(0,len(extended.feature_mean)-x.shape[1])))
    np.testing.assert_allclose(extended.raw_predictions(y),model.raw_predictions(x),atol=1e-12,rtol=0)
    for row,extra in zip(x,y,strict=True):np.testing.assert_allclose(extended.raw_predictions(extra),model.raw_predictions(row),atol=1e-12,rtol=0)
    with pytest.raises(m.LivingDexOptionValueError):
        m.fit_living_dex_option_value((),curriculum_examples=rows,feature_version=10,frozen_success_base=extended,story_success_retention_decision_sha256s=ids)


def test_input_order_and_protected_order_do_not_change_model_or_report():
    base,rows,ids=evidence();a=fit(base,rows,ids);b=fit(base,tuple(reversed(rows)),tuple(reversed(ids)))
    assert a.model.model_sha256==b.model.model_sha256
    assert a.report.public_dict()==b.report.public_dict()


def test_synthetic_compensated_solver_matches_independent_kkt():
    x=np.asarray([[1.,0.],[0.,1.],[1.,2.],[0.,0.]])
    mean=np.array([.3,-.2]);scale=np.array([.7,1.3]);coef=np.zeros((2,9));coef[:,SUCCESS]=[.1,-.2];inter=np.zeros(9);inter[SUCCESS]=.4
    base=SimpleNamespace(coefficients=coef,intercept=inter,feature_mean=mean,feature_scale=scale,feature_version=9)
    targets=np.zeros((4,9));targets[:,SUCCESS]=[1.,1.,0.,0.];weights=np.array([1.,2.,.5,3.]);B=x/scale
    old=inter+(x-mean)/scale@coef;H=B.T@(weights[:,None]*B)+.25*np.eye(2);rhs=B.T@(weights*(targets[:,SUCCESS]-old[:,SUCCESS]));A=B[[0]]
    system=np.block([[H,A.T],[A,np.zeros((1,1))]])
    expected=np.linalg.solve(system,np.r_[rhs,0.])[:2]
    result=m._fit_outcome_with_retained_outputs(x,targets,weights,base,.25,(0,),('a'*64,),outcome_name='verified_success',feature_columns=(0,1))
    np.testing.assert_allclose(result[3][:,SUCCESS]-coef[:,SUCCESS],expected,atol=1e-12,rtol=0)
    assert result[2][SUCCESS]-inter[SUCCESS]==pytest.approx((mean/scale)@expected,abs=1e-12)
    assert result[6]['maximum_raw_output_error']<=1e-12


@pytest.mark.parametrize('fault',['wrong_kind','two_kinds','no_kind','leaked_context','wrong_effort','invented_pp','invalid_pp_flag','out_of_range_pp'])
def test_malformed_curriculum_gate_rejected_before_svd(monkeypatch,fault):
    base,rows,ids=evidence();names=m.option_feature_names(9);x=list(rows[7].features)
    changes={'wrong_kind':{'kind.evolve':.5},'two_kinds':{'kind.acquire':1.},'no_kind':{'kind.evolve':0.},'leaked_context':{'readiness.unlock_access_x_observed':1.},'wrong_effort':{'execution_effort_x_kind.evolve':.2},'invented_pp':{'readiness.evolve_x_current.pp_fraction':1.},'invalid_pp_flag':{'readiness.evolve_x_current.pp_known':.5},'out_of_range_pp':{'readiness.evolve_x_current.pp_known':1.,'readiness.evolve_x_current.pp_fraction':2.}}[fault]
    for key,value in changes.items():x[names.index(key)]=value
    rows=(*rows[:7],replace(rows[7],features=tuple(x)),*rows[8:])
    monkeypatch.setattr(np.linalg,'svd',lambda *a,**k:pytest.fail('Invalid input reached SVD'))
    with pytest.raises(m.LivingDexOptionValueError):fit(base,rows,ids)


@pytest.mark.parametrize('fault',['empty','duplicate','missing','bad_digest','string','set','boolean','nonstory_anchor','development_anchor','censored_anchor','no_parent','wrong_version','party_mode','workload_mode','complete_paid'])
def test_invalid_mode_and_anchors_rejected_before_solver(monkeypatch,fault):
    base,rows,ids=evidence();kwargs=dict(feature_version=9,frozen_success_base=base)
    if fault=='empty':ids=[]
    elif fault=='duplicate':ids=(ids[0],ids[0])
    elif fault=='missing':ids=['f'*64]
    elif fault=='bad_digest':ids=['bad']
    elif fault=='string':ids=ids[0]
    elif fault=='set':ids=set(ids)
    elif fault=='boolean':ids=[True]
    elif fault=='nonstory_anchor':ids=[rows[-1].decision_sha256]
    elif fault=='development_anchor':
        with pytest.raises(m.LivingDexOptionValueError):replace(rows[0],partition='development')
        return
    elif fault=='censored_anchor':rows=(replace(rows[0],outcome=m.LivingDexObservedOutcome(m.LivingDexOutcomeStatus.CENSORED,censor_reason=m.LivingDexCensorReason.EXTERNAL_INTERRUPTION)),*rows[1:])
    elif fault=='no_parent':kwargs.pop('frozen_success_base')
    elif fault=='wrong_version':kwargs['feature_version']=10
    elif fault=='party_mode':kwargs['frozen_party_cost_base']=base
    elif fault=='workload_mode':kwargs['frozen_level_workload_base']=base
    elif fault=='complete_paid':kwargs['complete_paid_success_basis']=m.CompletePaidSuccessBasis.CONSTANT
    monkeypatch.setattr(np.linalg,'svd',lambda *a,**k:pytest.fail('Invalid declaration reached SVD'))
    with pytest.raises(m.LivingDexOptionValueError):
        m.fit_living_dex_option_value((),curriculum_examples=rows,story_success_retention_decision_sha256s=ids,**kwargs)


def test_only_story_label_balance_counts(monkeypatch):
    base,rows,ids=evidence();rows=tuple(replace(r,outcome=replace(r.outcome,verified_success=i<7))for i,r in enumerate(rows))
    monkeypatch.setattr(np.linalg,'svd',lambda *a,**k:pytest.fail('One story class reached SVD'))
    with pytest.raises(m.LivingDexOptionValueError,match='story successes and failures'):fit(base,rows,ids)


def test_non_success_targets_do_not_change_success_coefficients():
    base,rows,ids=evidence();a=fit(base,rows,ids)
    altered=tuple(replace(r,outcome=replace(r.outcome,party_cost=.8,action_cost=.9,frame_cost=.2))for r in rows)
    b=fit(base,altered,ids)
    np.testing.assert_array_equal(a.model.coefficients,b.model.coefficients)
    np.testing.assert_array_equal(a.model.intercept,b.model.intercept)
    assert a.model.train_dataset_sha256!=b.model.train_dataset_sha256


def test_default_success_mode_never_enters_story_solver(monkeypatch):
    from test_success_head_retention import samples
    base=parent();rows=samples()
    monkeypatch.setattr(m,'_fit_story_success_with_retained_outputs',lambda *a,**k:pytest.fail('Legacy mode entered new solver'))
    a=m.fit_living_dex_option_value(rows,feature_version=9,frozen_success_base=base)
    b=m.fit_living_dex_option_value(rows,feature_version=9,frozen_success_base=base,story_success_retention_decision_sha256s=None)
    assert a.model.model_sha256==b.model.model_sha256 and a.report.public_dict()==b.report.public_dict()
    assert 'story_success_retention'not in a.report.public_dict()
