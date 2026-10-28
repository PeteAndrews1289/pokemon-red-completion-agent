"""Synthetic-only V15 bounded-head math, contracts and legacy compatibility."""
from dataclasses import replace
import json
import numpy as np
import pytest
import pokemon_red_completion.living_dex_option_value as m
from pokemon_red_completion.player_option_matchup import OptionMatchup,MATCHUP_NAMES
from test_story_success_output_retention import evidence as old_evidence


def evidence():
    base,rows,ids=old_evidence();base=m.upgrade_option_value_model_for_matchup(base)
    out=[];names=m.option_feature_names(15)
    for i,row in enumerate(rows):
        x=list(m.curriculum_features(row,15))
        if i in (4,5,6):
            for key,value in {'present':1.,'combat_required':1.,'opposition_known':1.,'opponent_fraction':1/6}.items():
                x[names.index('challenge.unlock_access_x_'+key)]=value
            d={name:0. for name in MATCHUP_NAMES[1:]}
            d.update(own_members_known=1.,own_stats_known=1.,opposition_roster_known=1.,moves_and_pp_known=1.,declared_combat_fraction=1/6,living_combat_fraction=1/6,opponent_fraction=1/6)
            for group in ('attack','defense','speed','special','max_hp'):
                d['own.'+group+'.minimum']=d['own.'+group+'.mean']=(i-3)*20/999
            d['own.usable_move_fraction.minimum']=d['own.usable_move_fraction.mean']=.5
            d['own.usable_damaging_move_pp_fraction.minimum']=d['own.usable_damaging_move_pp_fraction.mean']=.5
            desc=OptionMatchup(tuple(d[n] for n in MATCHUP_NAMES[1:]))
            x=list(m.project_matchup_features(x[:len(m.option_feature_names(14))],desc))
        out.append(replace(row,feature_version=15,features=tuple(x)))
    return base,tuple(out),ids


def fit(base,rows,ids,**kw):
    return m.fit_living_dex_option_value((),curriculum_examples=rows,feature_version=15,frozen_success_base=base,bounded_matchup_story_success_retention_decision_sha256s=ids,**kw)


def test_full_basis_normalizer_retention_components_and_input_order():
    base,rows,ids=evidence();result=fit(base,rows,ids);model=result.model;head=model.bounded_story_success_head
    assert isinstance(head,m.LivingDexBoundedMatchupStorySuccessHead)
    assert len(head.coefficients)==461 and len(m.bounded_matchup_story_feature_indices())==461
    assert not any('_x_budget.' in n for n in head.feature_names)
    x=np.array([r.features for r in rows]);before=base.raw_predictions(x);after=model.raw_predictions(x)
    for field in ('coefficients','intercept','feature_mean','feature_scale'):np.testing.assert_array_equal(getattr(model,field),getattr(base,field))
    np.testing.assert_array_equal(after[:,1:],before[:,1:]);np.testing.assert_array_equal(after[7:],before[7:])
    np.testing.assert_allclose(np.clip(after[:4,0],0,1),np.clip(before[:4,0],0,1),atol=1e-10,rtol=0)
    assert model.economy_head is base.economy_head
    d=model.story_success_components(x)
    assert d['correction_feature_contributions'].shape==(9,506)
    np.testing.assert_allclose(d['learned_delta'],d['correction_intercept']+d['correction_feature_contributions'].sum(axis=-1),atol=1e-12,rtol=0)
    np.testing.assert_array_equal(d['preclip'],after[:,0]);np.testing.assert_array_equal(d['learned_delta'][7:],np.zeros(2))
    np.testing.assert_array_equal(head.coefficients[head.constant_mask],np.zeros(head.constant_mask.sum()))
    h2=fit(base,tuple(reversed(rows)),tuple(reversed(ids)))
    assert h2.model.model_sha256==model.model_sha256 and h2.report.public_dict()==result.report.public_dict()
    assert result.report.bounded_story_success_retention['reduced_normal_equation_max_abs_residual']<1e-10


def test_weighted_normalizer_and_independent_reduced_kkt():
    base,rows,ids=evidence();rows=tuple(sorted(rows,key=lambda r:r.decision_sha256))
    x=np.array([r.features for r in rows]);y=np.array([r.outcome.target_vector for r in rows]);w=np.arange(1,len(rows)+1,dtype=float)
    anchors=tuple(i for i,r in enumerate(rows)if r.decision_sha256 in ids)
    head,_,_,report=m._fit_bounded_matchup_story_success(x,y,w,base,.25,anchors,ids,tuple(r.decision_sha256 for r in rows))
    story=m._bounded_story_mask(x);z=x[:,head.feature_indices];expected=np.average(z[story],axis=0,weights=w[story])
    np.testing.assert_array_equal(head.feature_mean,expected)
    std=np.sqrt(np.average((z[story]-expected)**2,axis=0,weights=w[story]))
    np.testing.assert_array_equal(head.feature_scale[~head.constant_mask],np.maximum(std[~head.constant_mask],1e-6))
    normalized=(z-head.feature_mean)/head.feature_scale;normalized[:,head.constant_mask]=0
    active=np.flatnonzero(~head.constant_mask);B=np.column_stack((np.ones(len(x)),normalized[:,active]));B[~story]=0
    A=B[list(anchors)];_,sv,vt=np.linalg.svd(A,full_matrices=True);rank=np.count_nonzero(sv>max(A.shape)*np.finfo(float).eps*sv[0]);Z=vt[rank:].T
    theta=np.r_[head.intercept,head.coefficients[active]];res=y[:,0]-np.clip(base.raw_predictions(x)[:,0],0,1)
    grad=Z.T@(B.T@(w*(B@theta-res))+.25*np.r_[0.,theta[1:]])
    assert np.max(abs(grad))<1e-10 and np.max(abs(A@theta))<1e-10
    w[~story]=1e8
    other,*_=m._fit_bounded_matchup_story_success(x,y,w,base,.25,anchors,ids,tuple(r.decision_sha256 for r in rows))
    np.testing.assert_array_equal(head.feature_mean,other.feature_mean);np.testing.assert_array_equal(head.feature_scale,other.feature_scale)


def test_stats_scale_cancels_units_and_floor_constant_policy():
    base,rows,ids=evidence();names=m.option_feature_names(15);changed=[]
    for i,r in enumerate(rows):
        x=list(r.features)
        if i<7:
            x[names.index('uncertainty')]=.4+i*1e-9
            x[names.index('storage_cost')]=.3+i*1e-16
        changed.append(replace(r,features=tuple(x)))
    head=fit(base,tuple(changed),ids).model.bounded_story_success_head
    col=head.feature_names.index('matchup.own.attack.mean')
    assert 1e-6<head.feature_scale[col]<.1
    assert head.feature_scale[head.feature_names.index('uncertainty')]==1e-6
    constant=head.feature_names.index('storage_cost')
    assert head.constant_mask[constant] and head.feature_scale[constant]==1 and head.coefficients[constant]==0


def test_budget_invariance_is_correction_only_and_nonstrory_zero():
    base,rows,ids=evidence();names=m.option_feature_names(15);col=names.index('readiness.unlock_access_x_budget.seconds')
    coef=base.coefficients.copy();coef[col,0]=.1;base=replace(base,coefficients=coef)
    model=fit(base,rows,ids).model;x=np.array(rows[4].features);y=x.copy();y[col]=.5
    a=model.story_success_components(x);b=model.story_success_components(y)
    np.testing.assert_array_equal(a['learned_delta'],b['learned_delta'])
    np.testing.assert_array_equal(a['correction_feature_contributions'],b['correction_feature_contributions'])
    assert a['base_raw']!=b['base_raw'] and a['preclip']!=b['preclip']
    assert a['correction_feature_contributions'][col]==0


def test_normalization_evidence_has_no_targets_and_unknown_stats_are_not_invented():
    base,rows,ids=evidence();first=fit(base,rows,ids).model.bounded_story_success_head
    flipped=tuple(replace(r,outcome=replace(r.outcome,verified_success=not r.outcome.verified_success))for r in rows)
    second=fit(base,flipped,ids).model.bounded_story_success_head
    assert first.normalization_evidence_sha256==second.normalization_evidence_sha256
    np.testing.assert_array_equal(first.feature_mean,second.feature_mean)
    assert all(not any(r.features[-28:]) for r in rows[:4])


def test_v2_model_and_outer_record_codec_and_array_immutability():
    from test_living_dex_goal_model_record import _record
    from pokemon_red_completion.living_dex_goal_model_record import load_living_dex_goal_model_record_bytes
    base,rows,ids=evidence();model=fit(base,rows,ids).model
    restored=m.LivingDexOptionValueModel.from_dict(model.to_dict());assert restored.model_sha256==model.model_sha256
    record=load_living_dex_goal_model_record_bytes(json.dumps(_record(model)).encode(),expected_model_sha256=model.model_sha256)
    assert record.model.to_dict()==model.to_dict()
    for name in ('coefficients','feature_mean','feature_scale','constant_mask'):
        with pytest.raises(ValueError):getattr(model.bounded_story_success_head,name)[0]=0
    assert model.story_success_components(np.array(rows[0].features))['preclip'].shape==()


@pytest.mark.parametrize('fault',['budget_index','index_order','bool_index','bad_floor','bad_constant_scale','constant_coefficient','missing_normalizer','bad_mean','bad_mask','wrong_schema','wrong_version','extra_key'])
def test_v2_codec_rejects_malformed_basis_and_normalizer(fault):
    base,rows,ids=evidence();doc=fit(base,rows,ids).model.to_dict();h=doc['bounded_story_success_head'];n=h['normalization']
    if fault=='budget_index':h['feature_indices'][0]=m.option_feature_names(15).index('readiness.unlock_access_x_budget.seconds')
    elif fault=='index_order':h['feature_indices'].reverse()
    elif fault=='bool_index':h['feature_indices'][0]=False
    elif fault=='bad_floor':n['scale_floor']=.1
    elif fault=='bad_constant_scale':n['feature_scale'][n['constant_mask'].index(True)]=.1
    elif fault=='constant_coefficient':h['coefficients'][n['constant_mask'].index(True)]=1.
    elif fault=='missing_normalizer':del h['normalization']
    elif fault=='bad_mean':n['feature_mean'][0]=True
    elif fault=='bad_mask':n['constant_mask'][0]=0
    elif fault=='wrong_schema':h['schema']='pokemon.core.bounded-story-success-head.v1'
    elif fault=='wrong_version':h['feature_version']=10
    else:h['surprise']=1
    with pytest.raises((ValueError,TypeError)):m.LivingDexOptionValueModel.from_dict(doc)


@pytest.mark.parametrize('fault',['empty','duplicate','missing','nonstory','wrong_version','nested','mixed_v1','wrong_kind'])
def test_v2_fit_rejects_bad_scope(fault):
    base,rows,ids=evidence();kw={}
    if fault=='empty':ids=()
    elif fault=='duplicate':ids=(*ids,ids[0])
    elif fault=='missing':ids=('f'*64,)
    elif fault=='nonstory':ids=(rows[-1].decision_sha256,)
    elif fault=='wrong_version':base=old_evidence()[0]
    elif fault=='nested':base=fit(base,rows,ids).model
    elif fault=='mixed_v1':kw['bounded_story_success_retention_decision_sha256s']=ids
    else:
        x=list(rows[-1].features);x[0]=1;rows=(*rows[:-1],replace(rows[-1],features=tuple(x)))
    with pytest.raises(ValueError):fit(base,rows,ids,**kw)


def test_v15_matchup_economy_and_diagnostics_use_same_real_gateway():
    from test_living_dex_option_value import _menu
    from pokemon_red_completion.player_option_challenge import OptionChallenge
    from pokemon_red_completion.living_dex_goal_policy import DEFAULT_LIVING_DEX_GOAL_UTILITY
    from pokemon_red_completion.resource_economy_observation import EconomySnapshot
    base,rows,ids=evidence();model=fit(base,rows,ids).model
    menu=_menu();first=menu.candidates[0]
    desc=OptionMatchup(tuple(rows[4].features[-27:]))
    first=replace(first,features=replace(first.features,kind=m.LivingDexOptionKind.UNLOCK_ACCESS),challenge=OptionChallenge(True,True,1/6,0.,0.),matchup=desc)
    menu=replace(menu,context=replace(menu.context,economy_snapshot=EconomySnapshot(1000,()),target_cash=2000),candidates=(first,*menu.candidates[1:]))
    scores=model.scores(menu,DEFAULT_LIVING_DEX_GOAL_UTILITY);diag=model.diagnose_menu(menu,DEFAULT_LIVING_DEX_GOAL_UTILITY)
    assert scores==tuple(r['score']for r in diag['candidates'])
    c=diag['candidates'][0]['bounded_story_success'];assert len(c['feature_names'])==506
    assert c['preclip']==diag['candidates'][0]['raw_predictions']['verified_success']
    assert model.predict_economy_candidate(menu.context,first)==base.predict_economy_candidate(menu.context,replace(first,matchup=None))
    from test_success_head_retention import samples
    coverage=model.diagnose_training_coverage(samples(),curriculum_examples=rows)
    for i in (i for i,n in enumerate(m.option_feature_names(15))if '_x_budget.'in n):
        assert coverage['features'][i]['bounded_story_head_weighted']is False

def test_v2_exact_version_upgrade_is_identity_and_v1_remains_rejected():
    base,rows,ids=evidence();model=fit(base,rows,ids).model
    assert m.upgrade_option_value_model_for_matchup(model)is model
    old,oldrows,oldids=old_evidence()
    prior=m.fit_living_dex_option_value((),curriculum_examples=oldrows,feature_version=9,frozen_success_base=old,bounded_story_success_retention_decision_sha256s=oldids).model
    with pytest.raises(ValueError):m.upgrade_option_value_model_for_matchup(prior)

