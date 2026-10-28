"""Synthetic bounded-parent correction checks; no game or archived TRAIN inputs."""
from dataclasses import replace
import numpy as np
import pytest
import pokemon_red_completion.living_dex_option_value as m
from test_story_success_output_retention import evidence, vector, SUCCESS, OTHER


def fit(base, rows, ids, **kwargs):
    return m.fit_living_dex_option_value((), curriculum_examples=rows, feature_version=9,
        frozen_success_base=base, bounded_story_success_retention_decision_sha256s=ids, **kwargs)


def test_full_context_fit_retains_base_and_actual_anchor_forecasts():
    base,rows,ids=evidence(); result=fit(base,rows,ids); model=result.model
    x=np.array([r.features for r in rows]);a=base.raw_predictions(x);b=model.raw_predictions(x)
    for field in ('coefficients','intercept','feature_mean','feature_scale'):
        np.testing.assert_array_equal(getattr(model,field),getattr(base,field))
    assert model.economy_head is base.economy_head
    np.testing.assert_array_equal(b[:,OTHER],a[:,OTHER]);np.testing.assert_array_equal(b[7:],a[7:])
    np.testing.assert_allclose(np.clip(b[:4,0],0,1),np.clip(a[:4,0],0,1),atol=1e-10,rtol=0)
    assert model.objective==m.LIVING_DEX_BOUNDED_STORY_SUCCESS_OBJECTIVE
    assert len(model.bounded_story_success_head.coefficients)==370
    assert model.bounded_story_success_head.parent_model_sha256==base.model_sha256
    d=model.story_success_components(x)
    np.testing.assert_array_equal(d['base_raw'],a[:,0]);np.testing.assert_array_equal(d['preclip'],b[:,0])
    np.testing.assert_array_equal(d['final'],np.clip(b[:,0],0,1))
    np.testing.assert_array_equal(d['learned_delta'][7:],np.zeros(2))
    np.testing.assert_allclose(d['learned_delta'],d['correction_intercept']+d['correction_feature_contributions'].sum(axis=-1),atol=1e-12,rtol=0)
    assert result.report.public_dict()['bounded_story_success_retention']['protected_count']==4
    assert model.train_dataset_sha256==m.living_dex_option_train_dataset_sha256((),curriculum_examples=rows)


def test_extreme_parent_is_bounded_before_correcting_and_nonstory_remains_raw():
    base,rows,ids=evidence();inter=base.intercept.copy();inter[0]=-20.
    base=replace(base,intercept=inter);head=m.LivingDexBoundedStorySuccessHead(np.zeros(370),.25,base.model_sha256)
    model=replace(base,objective=m.LIVING_DEX_BOUNDED_STORY_SUCCESS_OBJECTIVE,bounded_story_success_head=head)
    x=np.array([rows[0].features,rows[-1].features]);raw=model.raw_predictions(x)
    assert raw[0,0]==.25;assert raw[1,0]==base.raw_predictions(x)[1,0]
    d=model.story_success_components(x);assert d['bounded_base'][0]==0.
    inter[0]=20.;base=replace(base,intercept=inter);model=replace(model,intercept=inter)
    assert model.raw_predictions(x)[0,0]==1.25
    assert np.clip(model.raw_predictions(x),0,1)[0,0]==1.


def test_solution_matches_independent_equality_constrained_normal_equation():
    base,rows,ids=evidence();result=fit(base,rows,ids);head=result.model.bounded_story_success_head
    x=np.array([r.features for r in rows]);y=np.array([r.outcome.target_vector[0] for r in rows]);w=np.ones(len(x))
    B=np.column_stack((np.ones(len(x)),(x-base.feature_mean)/base.feature_scale));B[7:]=0
    A=B[:4];_,sv,vt=np.linalg.svd(A,full_matrices=True);rank=np.count_nonzero(sv>max(A.shape)*np.finfo(float).eps*sv[0]);Z=vt[rank:].T
    theta=np.r_[head.intercept,head.coefficients];r=y-np.clip(base.raw_predictions(x)[:,0],0,1)
    penalty=np.r_[0.,np.ones(370)]
    grad=Z.T@(B.T@(w*(B@theta-r))+.25*penalty*theta)
    assert max(abs(grad))<1e-10;assert max(abs(A@theta))<1e-10
    # Frozen parent normalizer is genuinely nonzero, so bias/centering matters.
    assert np.any(base.feature_mean!=0)


def test_codec_v10_prefix_and_unsupported_suffix():
    base,rows,ids=evidence();model=fit(base,rows,ids).model
    restored=m.LivingDexOptionValueModel.from_dict(model.to_dict());assert restored.model_sha256==model.model_sha256
    expanded=m.upgrade_option_value_model_for_move_change(model)
    assert expanded.bounded_story_success_head is model.bounded_story_success_head
    x=np.array([r.features for r in rows]);v10=np.pad(x,((0,0),(0,len(expanded.feature_mean)-370)))
    np.testing.assert_allclose(expanded.raw_predictions(v10),model.raw_predictions(x),atol=1e-12,rtol=0)
    assert m.LivingDexOptionValueModel.from_dict(expanded.to_dict()).model_sha256==expanded.model_sha256
    with pytest.raises(m.LivingDexOptionValueError):m.upgrade_option_value_model_for_move_context(expanded)
    for row in x:assert model.story_success_components(row)['preclip'].shape==()
    with pytest.raises(ValueError):model.bounded_story_success_head.coefficients[0]=0.


@pytest.mark.parametrize('fault',['missing_head','old_objective','bad_prefix','bad_kind','extra_key','bad_coefficients','bad_bias','bad_parent'])
def test_codec_and_typed_head_reject_invalid_documents(fault):
    base,rows,ids=evidence();doc=fit(base,rows,ids).model.to_dict()
    if fault=='missing_head':del doc['bounded_story_success_head']
    elif fault=='old_objective':doc['objective']=m.LIVING_DEX_OPTION_OBJECTIVE
    elif fault=='bad_prefix':doc['bounded_story_success_head']['feature_version']=10
    elif fault=='bad_kind':doc['bounded_story_success_head']['kind']='develop'
    elif fault=='extra_key':doc['bounded_story_success_head']['unknown']=1
    elif fault=='bad_coefficients':doc['bounded_story_success_head']['coefficients']=[float('nan')]*370
    elif fault=='bad_bias':doc['bounded_story_success_head']['intercept']=True
    else:doc['bounded_story_success_head']['parent_model_sha256']='bad'
    with pytest.raises((m.LivingDexOptionValueError,ValueError,TypeError)):m.LivingDexOptionValueModel.from_dict(doc)


@pytest.mark.parametrize('parent_kw',['frozen_success_base','frozen_party_cost_base','frozen_level_workload_base'])
def test_every_old_fit_mode_rejects_corrected_parent_before_data(parent_kw):
    base,rows,ids=evidence();model=fit(base,rows,ids).model
    with pytest.raises(m.LivingDexOptionValueError,match='already corrected'):
        m.fit_living_dex_option_value((),feature_version=9,**{parent_kw:model})
    with pytest.raises(m.LivingDexOptionValueError,match='already corrected'):fit(model,rows,ids)


@pytest.mark.parametrize('fault',['duplicate','missing','nonstory','ambiguous_kind','leaked_pp','mixed_mode','not_sequence'])
def test_invalid_anchors_and_context_fail_closed(fault):
    base,rows,ids=evidence()
    if fault=='duplicate':ids=(*ids,ids[0])
    elif fault=='missing':ids=('f'*64,)
    elif fault=='nonstory':ids=(rows[-1].decision_sha256,)
    elif fault in ('ambiguous_kind','leaked_pp'):
        x=list(rows[-1].features);names=m.option_feature_names(9)
        x[names.index('kind.evolve' if fault=='ambiguous_kind' else 'readiness.unlock_access_x_current.pp_fraction')]=1.
        rows=(*rows[:-1],replace(rows[-1],features=tuple(x)))
    elif fault=='not_sequence':ids=ids[0]
    with pytest.raises(m.LivingDexOptionValueError):
        fit(base,rows,ids,**({'story_success_retention_decision_sha256s':ids}if fault=='mixed_mode'else{}))


def test_curriculum_metric_uses_head_and_retention_search_rejects_it():
    from pokemon_red_completion.living_dex_retention_fit import curriculum_mse,fit_retaining_prior
    base,rows,ids=evidence();model=fit(base,rows,ids).model;x=np.array([r.features for r in rows]);y=np.array([r.outcome.target_vector for r in rows])
    assert curriculum_mse(model,rows)==pytest.approx(np.mean((np.clip(model.raw_predictions(x),0,1)-y)**2))
    with pytest.raises(ValueError,match='already corrected'):fit_retaining_prior(model,(),rows)


def test_legacy_serialization_omits_optional_head():
    base,rows,ids=evidence();assert 'bounded_story_success_head'not in base.to_dict()
    assert m.LivingDexOptionValueModel.from_dict(base.to_dict()).model_sha256==base.model_sha256


def test_actual_anchor_forecasts_retained_when_parent_raw_is_outside_probability_range():
    base,rows,ids=evidence();inter=base.intercept.copy();inter[0]=4.;base=replace(base,intercept=inter)
    model=fit(base,rows,ids).model;x=np.array([r.features for r in rows])
    np.testing.assert_allclose(model.raw_predictions(x)[:4,0],np.ones(4),atol=1e-10,rtol=0)
    assert np.all(base.raw_predictions(x)[:4,0]==4.)
    np.testing.assert_array_equal(model.raw_predictions(x)[7:],base.raw_predictions(x)[7:])


def test_weighted_normal_equation_and_full_shared_context_are_used():
    base,rows,ids=evidence();x=np.array([r.features for r in rows]);names=m.option_feature_names(9)
    # Public shared context lies outside the old story-only36; declaration keeps all370.
    col=names.index('completion_gain');x[4,col]=.8;x[5,col]=.3;x[6,col]=.9
    y=np.array([r.outcome.target_vector for r in rows]);w=np.array([1.,2.,.5,3.,4.,.2,2.,1.,1.])
    h,_,_,report=m._fit_bounded_story_success(x,y,w,base,.25,(0,1,2,3),ids)
    B=np.column_stack((np.ones(len(x)),(x-base.feature_mean)/base.feature_scale));B[7:]=0
    A=B[:4];_,sv,vt=np.linalg.svd(A,full_matrices=True);rank=np.count_nonzero(sv>max(A.shape)*np.finfo(float).eps*sv[0]);Z=vt[rank:].T
    theta=np.r_[h.intercept,h.coefficients];res=y[:,0]-np.clip(base.raw_predictions(x)[:,0],0,1)
    gradient=Z.T@(B.T@(w*(B@theta-res))+.25*np.r_[0.,theta[1:]])
    assert max(abs(gradient))<1e-10 and abs(h.coefficients[col])>1e-5
    assert report['bias_unpenalized']


def test_model_record_and_menu_diagnostics_rejoin_explicit_head():
    import json
    from test_living_dex_goal_model_record import _record
    from pokemon_red_completion.living_dex_goal_model_record import load_living_dex_goal_model_record_bytes
    from test_living_dex_option_value import _menu
    from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
    base,rows,ids=evidence();model=fit(base,rows,ids).model
    payload=json.dumps(_record(model),sort_keys=True).encode();restored=load_living_dex_goal_model_record_bytes(payload,expected_model_sha256=model.model_sha256)
    assert restored.model.to_dict()==model.to_dict()
    menu=_menu();first=menu.candidates[0];first=replace(first,features=replace(first.features,kind=m.LivingDexOptionKind.UNLOCK_ACCESS));menu=replace(menu,candidates=(first,*menu.candidates[1:]))
    d=model.diagnose_menu(menu,DEFAULT_LIVING_DEX_GOAL_UTILITY)
    assert d['weighted_feature_count_scope']=='base_linear_parameters_only'
    assert [r['score']for r in d['candidates']]==list(model.scores(menu,DEFAULT_LIVING_DEX_GOAL_UTILITY))
    for row in d['candidates']:
        if row['available']:
            c=row['bounded_story_success'];assert c['preclip']==row['raw_predictions']['verified_success']
            assert c['final']==row['bounded_predictions']['verified_success']
            assert row['raw_contribution_scope']=='base_linear_parameters_only'
    from test_success_head_retention import samples
    coverage=model.diagnose_training_coverage(samples(),curriculum_examples=rows)
    assert coverage['weighted_feature_scope']=='base_linear_parameters_only'
    assert all('bounded_story_head_weighted'in v for v in coverage['features'])


@pytest.mark.parametrize('bad',[True,'0.1',None])
def test_head_coefficients_reject_coercible_nonnumeric_or_boolean_values(bad):
    values=[0.]*370;values[4]=bad
    with pytest.raises((m.LivingDexOptionValueError,TypeError,ValueError)):
        m.LivingDexBoundedStorySuccessHead(values,0.,'a'*64)
