"""Synthetic contract tests. Root must authorize execution; no ROM/native assets.

These test-only examples are not project TRAIN evidence or a candidate fit.
"""
from dataclasses import replace
from unittest.mock import patch
import numpy as np
import pytest
import pokemon_red_completion.living_dex_option_value as m
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit


def context(**kwargs):
    return m.LivingDexOptionContext(**dict(collection_pressure=.3, dependency_pressure=.4,
        access_pressure=.5, resource_pressure=.2, storage_pressure=.1,
        party_pressure=.2, knowledge_pressure=.1) | kwargs)


def candidate(kind=m.LivingDexOptionKind.UNLOCK_ACCESS, unit=None):
    return m.LivingDexOptionCandidate('synthetic:test',
        m.LivingDexOptionFeatures(kind,.2,.4,.1,.2,.1,.0,.1,.0,.0),
        m.LivingDexOptionAvailability.AVAILABLE,story_unit=unit)


def vector(unit=OptionStoryUnit('movement',True), *, kind=m.LivingDexOptionKind.UNLOCK_ACCESS, **kwargs):
    return np.array(candidate(kind,unit).vector(context(**kwargs),feature_version=16))


def parent(intercept=.25):
    names=m.option_feature_names(16);w=len(names)
    coefficients=np.zeros((w,9));bias=np.zeros(9);bias[0]=intercept
    for name,value in zip(m._MOVEMENT_STRATEGIC_FEATURE_NAMES,(2.,-3.,1.5)):
        coefficients[names.index(name),0]=value
    coefficients[names.index('execution_effort'),0]=.1
    coefficients[names.index('resource_pressure_x_resource_cost'),0]=.2
    coefficients[names.index('party_pressure_x_party_risk'),0]=-.2
    coefficients[names.index('readiness.unlock_access_x_budget.seconds'),0]=.1
    coefficients[names.index('execution_effort'),3]=.3
    mean=np.zeros(w);scale=np.ones(w)
    for name in m._MOVEMENT_STRATEGIC_FEATURE_NAMES:mean[names.index(name)]=.1
    return m.LivingDexOptionValueModel(coefficients,bias,mean,scale,'a'*64,10,0,.25,10.,feature_version=16)


def headed(base,bias=.05):
    head=m.LivingDexMovementSuccessHead(bias,base.model_sha256,'b'*64,'c'*64,('1'*64,'2'*64),2)
    return replace(base,movement_success_head=head)


def row(identifier,x,y=True):
    outcome=m.LivingDexObservedOutcome(m.LivingDexOutcomeStatus.SETTLED,y,0.,0.,.01,.01,0.,0.,0.,0.)
    return m.LivingDexCurriculumOutcomeExample(identifier*64,'train',16,tuple(map(float,x)),outcome)


def fit(base,rows):
    return m.fit_certified_movement_success_bias(rows,frozen_base=base,
        attestation_sha256='b'*64,attested_decision_sha256s=[r.decision_sha256 for r in rows])


def test_only_three_strategic_inputs_are_removed_from_certified_success():
    base=parent();model=headed(base)
    x=vector(collection_pressure=0.,dependency_pressure=0.,access_pressure=0.)
    y=vector(collection_pressure=1.,dependency_pressure=1.,access_pressure=1.)
    assert base.raw_predictions(x)[0]!=base.raw_predictions(y)[0]
    assert model.raw_predictions(x)[0]==model.raw_predictions(y)[0]
    assert model.movement_success_head.to_dict()['excluded_features']==list(m._MOVEMENT_STRATEGIC_FEATURE_NAMES)


@pytest.mark.parametrize('feature',[
    'execution_effort','resource_pressure_x_resource_cost','party_pressure_x_party_risk',
    'readiness.unlock_access_x_budget.seconds'])
def test_physical_cost_safety_and_budget_coordinates_still_affect_prior(feature):
    model=headed(parent());x=vector();y=x.copy();y[m.option_feature_names(16).index(feature)]+=.1
    assert model.raw_predictions(x)[0]!=model.raw_predictions(y)[0]


def test_other_heads_and_every_off_scope_row_are_bitwise_retained():
    base=parent();model=headed(base)
    rows=[vector(),vector(None),vector(OptionStoryUnit('interaction',True)),
          vector(OptionStoryUnit('movement',False))]
    rows.extend(vector(None,kind=kind) for kind in m.LivingDexOptionKind if kind is not m.LivingDexOptionKind.UNLOCK_ACCESS)
    x=np.array(rows);a=base.raw_predictions(x);b=model.raw_predictions(x)
    np.testing.assert_array_equal(a[:,1:],b[:,1:]);np.testing.assert_array_equal(a[1:],b[1:])
    for field in ('coefficients','intercept','feature_mean','feature_scale'):
        np.testing.assert_array_equal(getattr(base,field),getattr(model,field))
    assert model.economy_head is base.economy_head


def test_parent_is_bounded_before_bias_and_only_final_prediction_clips():
    model=headed(parent(-20.),.2);x=vector()
    assert model.raw_predictions(x)[0]==.2
    model=headed(parent(20.),.2)
    assert model.raw_predictions(x)[0]==1.2
    assert model.predict_candidate(context(),candidate(unit=OptionStoryUnit('movement',True))).verified_success==1.


def test_unknown_legacy_codec_has_no_new_field_and_exact_identity():
    base=parent();doc=base.to_dict();assert 'movement_success_head' not in doc
    restored=m.LivingDexOptionValueModel.from_dict(doc)
    assert restored.model_sha256==base.model_sha256
    model=headed(base);restored=m.LivingDexOptionValueModel.from_dict(model.to_dict())
    assert restored.model_sha256==model.model_sha256
    np.testing.assert_array_equal(restored.raw_predictions(vector()),model.raw_predictions(vector()))


@pytest.mark.parametrize('fault',['parent','bias_bool','mask','ridge','count','unversioned'])
def test_head_document_corruption_is_rejected(fault):
    doc=headed(parent()).to_dict();head=doc['movement_success_head']
    if fault=='parent':head['parent_model_sha256']='f'*64
    elif fault=='bias_bool':head['bias']=True
    elif fault=='mask':head['excluded_features'].append('resource_pressure_x_resource_cost')
    elif fault=='ridge':head['ridge']=0.
    elif fault=='count':head['successful_examples']=3
    else:head['feature_version']=15
    with pytest.raises(ValueError):m.LivingDexOptionValueModel.from_dict(doc)


def test_descriptor_does_not_grant_nonstory_gate_or_accept_malformed_bits():
    model=headed(parent());x=vector();names=m.option_feature_names(16)
    x[names.index('kind.unlock_access')]=0.;x[names.index('kind.acquire')]=1.
    with pytest.raises(ValueError):model.raw_predictions(x)
    x=vector();x[-1]=2.
    with pytest.raises(ValueError):model.raw_predictions(x)


def test_scalar_fit_uses_fixed_penalized_bias_not_unpenalized_always_one():
    base=parent();rows=(row('1',vector()),row('2',vector()))
    q=base.movement_success_components(np.array([r.features for r in rows]))['bounded_physical_prior']
    model,report=fit(base,rows)
    assert report['fits']==1 and report['status']=='PROVISIONAL_NATIVE_FALSIFICATION_ONLY'
    assert model.movement_success_head.bias==pytest.approx(float((2-q.sum())/2.25))
    assert model.raw_predictions(vector())[0]<1.
    assert report['labels_are_one_class'] is True
    assert report['prediction_is_calibrated_probability'] is False
    assert report['baseline_forward_calls']==report['candidate_forward_calls']==1


def test_insufficient_rows_exit_before_any_forward_or_fit():
    base=parent();rows=(row('1',vector()),)
    with patch.object(m.LivingDexOptionValueModel,'movement_success_components',side_effect=AssertionError('forward')):
        model,report=fit(base,rows)
    assert model is None and report['status']=='INSUFFICIENT_ATTESTED_TRAIN_ROWS'
    assert report['fits']==report['baseline_forward_calls']==report['candidate_forward_calls']==0


def test_no_residual_does_not_manufacture_a_fit():
    model,report=fit(parent(20.),(row('1',vector()),row('2',vector())))
    assert model is None and report['status']=='NO_INFORMATIVE_SCALAR_DIRECTION'
    assert report['fits']==0


@pytest.mark.parametrize('fault',['unknown','interaction','completing','duplicate','membership','old_version'])
def test_fit_does_not_coerce_phase_or_membership(fault):
    base=parent();rows=[row('1',vector()),row('2',vector())]
    if fault=='unknown':rows[1]=row('2',vector(None))
    elif fault=='interaction':rows[1]=row('2',vector(OptionStoryUnit('interaction',True)))
    elif fault=='completing':rows[1]=row('2',vector(OptionStoryUnit('movement',False)))
    elif fault=='duplicate':rows[1]=rows[0]
    elif fault=='old_version':rows[1]=replace(rows[1],feature_version=15,features=rows[1].features[:-4])
    with pytest.raises(ValueError):
        if fault=='membership':m.fit_certified_movement_success_bias(rows,frozen_base=base,attestation_sha256='b'*64,attested_decision_sha256s=['3'*64])
        else:fit(base,rows)


def test_existing_fitter_cannot_silently_discard_optional_head():
    with pytest.raises(ValueError,match='already corrected'):
        m.fit_living_dex_option_value((),feature_version=16,frozen_success_base=headed(parent()))


def test_existing_metric_observes_head_and_old_retention_search_refuses_it():
    from pokemon_red_completion.living_dex_retention_fit import curriculum_mse, fit_retaining_prior
    model=headed(parent());rows=(row('1',vector()),row('2',vector()))
    x=np.array([r.features for r in rows]);y=np.array([r.outcome.target_vector for r in rows])
    assert curriculum_mse(model,rows)==pytest.approx(np.mean((np.clip(model.raw_predictions(x),0,1)-y)**2))
    with pytest.raises(ValueError,match='already corrected'):
        fit_retaining_prior(model,(),rows)
