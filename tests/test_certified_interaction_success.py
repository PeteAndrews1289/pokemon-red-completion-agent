"""PROPOSAL: synthetic ROM-free optional-interaction contract checks.
These synthetic fixtures are not project TRAIN evidence or a candidate fit.
Root must review/copy/run after applying the proposed optional-head source.
"""
from dataclasses import replace
from unittest.mock import patch
import numpy as np
import pytest
import pokemon_red_completion.living_dex_option_value as V
from pokemon_red_completion.player_option_story_unit import OptionStoryUnit
from pokemon_red_completion.player_option_challenge import OptionChallenge


def vector(unit=OptionStoryUnit('interaction',True),kind=V.LivingDexOptionKind.UNLOCK_ACCESS,challenge=OptionChallenge(False,False,0.,0.,0.),**context):
    c=V.LivingDexOptionContext(**(dict(collection_pressure=.3,dependency_pressure=.4,access_pressure=.5,resource_pressure=.2,storage_pressure=.1,party_pressure=.2,knowledge_pressure=.1)|context))
    p=V.LivingDexOptionCandidate('synthetic:optional-interaction',V.LivingDexOptionFeatures(kind,.2,.4,.1,.2,.1,0.,.1,0.,0.),V.LivingDexOptionAvailability.AVAILABLE,story_unit=unit,challenge=challenge)
    return np.asarray(p.vector(c,feature_version=16))


def base(intercept=-10.):
    names=V.option_feature_names(16);n=len(names);w=np.zeros((n,9));b=np.zeros(9);b[0]=intercept
    for name,coef in zip(V._MOVEMENT_STRATEGIC_FEATURE_NAMES,(2.,-3.,1.5),strict=True):w[names.index(name),0]=coef
    w[names.index('execution_effort'),0]=.1;w[names.index('execution_effort'),3]=.3
    plain=V.LivingDexOptionValueModel(w,b,np.zeros(n),np.ones(n),'a'*64,175,0,.25,10.,feature_version=16)
    mh=V.LivingDexMovementSuccessHead(.2,plain.model_sha256,'b'*64,'c'*64,('1'*64,'2'*64),2)
    return replace(plain,movement_success_head=mh)


def headed(parent,bias=.2):
    h=V.LivingDexInteractionSuccessHead(bias,parent.model_sha256,'d'*64,'e'*64,('3'*64,'4'*64),2)
    return replace(parent,interaction_success_head=h)


def row(identifier,x=None,y=True):
    o=V.LivingDexObservedOutcome(V.LivingDexOutcomeStatus.SETTLED,y,0.,0.,.01,.01,0.,0.,0.,0.)
    return V.LivingDexCurriculumOutcomeExample(identifier*64,'train',16,tuple(map(float,vector()if x is None else x)),o)


def fit(parent,rows,ids=None):
    return V.fit_certified_interaction_success_bias(rows,frozen_base=parent,attestation_sha256='d'*64,attested_decision_sha256s=[r.decision_sha256 for r in rows]if ids is None else ids)


def test_none_preserves_old_codec_hash_and_raw_numerics_exactly():
    p=base();doc=p.to_dict();assert 'interaction_success_head'not in doc
    restored=V.LivingDexOptionValueModel.from_dict(doc)
    assert restored.interaction_success_head is None and restored.to_dict()==doc and restored.model_sha256==p.model_sha256
    x=np.array([vector(),vector(None),vector(OptionStoryUnit('movement',True))])
    np.testing.assert_array_equal(restored.raw_predictions(x),p.raw_predictions(x))
    assert replace(p,interaction_success_head=None).to_dict()==doc


def test_new_parent_is_full_old_model_with_old_movement_document_unchanged():
    p=base();q=headed(p);doc=q.to_dict();head=doc.pop('interaction_success_head')
    assert doc==p.to_dict() and head['parent_model_sha256']==p.model_sha256
    assert q.movement_success_head.to_dict()==p.movement_success_head.to_dict()
    restored=V.LivingDexOptionValueModel.from_dict(q.to_dict());assert restored.model_sha256==q.model_sha256
    np.testing.assert_array_equal(restored.raw_predictions(vector()),q.raw_predictions(vector()))
    with pytest.raises(ValueError):replace(base(-9.),interaction_success_head=q.interaction_success_head)


def test_every_other_output_and_the_off_scope_domain_are_exactly_retained():
    p=base();q=headed(p)
    values=[vector(),vector(None),vector(OptionStoryUnit('movement',True)),vector(OptionStoryUnit('movement',False)),vector(OptionStoryUnit('interaction',False))]
    values += [vector(None,k)for k in V.LivingDexOptionKind if k is not V.LivingDexOptionKind.UNLOCK_ACCESS]
    x=np.array(values);before=p.raw_predictions(x);after=q.raw_predictions(x)
    np.testing.assert_array_equal(before[:,1:],after[:,1:]);np.testing.assert_array_equal(before[1:],after[1:])
    for field in ('coefficients','intercept','feature_mean','feature_scale'):np.testing.assert_array_equal(getattr(p,field),getattr(q,field))
    assert q.economy_head is p.economy_head
    assert q.train_dataset_sha256==p.train_dataset_sha256 and q.settled_examples==175


def test_strategic_pressure_does_not_change_certified_physical_override():
    p=base(-.2);q=headed(p)
    a=vector(collection_pressure=0.,dependency_pressure=0.,access_pressure=0.)
    b=vector(collection_pressure=1.,dependency_pressure=1.,access_pressure=1.)
    assert p.raw_predictions(a)[0]!=p.raw_predictions(b)[0]
    assert q.raw_predictions(a)[0]==q.raw_predictions(b)[0]
    assert q.interaction_success_head.to_dict()['excluded_features']==list(V._MOVEMENT_STRATEGIC_FEATURE_NAMES)


def test_physical_cost_feature_is_preserved():
    q=headed(base(-.02));a=vector();b=a.copy();b[V.option_feature_names(16).index('execution_effort')]+=.1
    assert q.interaction_success_components(a)['bounded_physical_prior']!=q.interaction_success_components(b)['bounded_physical_prior']


@pytest.mark.parametrize('intercept,expected',[(-20.,.2),(20.,1.2)])
def test_prior_clips_before_bias_while_raw_keeps_final_preclip(intercept,expected):
    q=headed(base(intercept));x=vector()
    assert float(q.raw_predictions(x)[0])==pytest.approx(expected)
    assert float(q.interaction_success_components(x)['final'])==pytest.approx(min(expected,1.))


@pytest.mark.parametrize('fault',['parent','bias_bool','ridge','gate','count','version','strategic_mask','schema','head_type'])
def test_strict_new_head_codec_rejects_corruption(fault):
    doc=headed(base()).to_dict();h=doc['interaction_success_head']
    if fault=='parent':h['parent_model_sha256']='f'*64
    elif fault=='bias_bool':h['bias']=True
    elif fault=='ridge':h['ridge']=0.
    elif fault=='gate':h['gate']='certified-movement-requires-further-selected-unit'
    elif fault=='count':h['successful_examples']=99
    elif fault=='version':h['feature_version']=15
    elif fault=='strategic_mask':h['excluded_features'].append('execution_effort')
    elif fault=='schema':h['schema']='pokemon.core.certified-movement-success-bias.v1'
    else:doc['interaction_success_head']=doc['movement_success_head']
    with pytest.raises(ValueError):V.LivingDexOptionValueModel.from_dict(doc)


@pytest.mark.parametrize('fault',['nonstory','two_kinds','malformed_unit'])
def test_gate_does_not_trust_a_descriptor_without_exact_kind(fault):
    q=headed(base());x=vector();names=V.option_feature_names(16)
    if fault=='nonstory':x[names.index('kind.unlock_access')]=0.;x[names.index('kind.acquire')]=1.
    elif fault=='two_kinds':x[names.index('kind.acquire')]=1.
    else:x[-1]=2.
    with pytest.raises(ValueError):q.raw_predictions(x)


def test_unknown_and_complete_scopes_have_no_interaction_override():
    p=base();q=headed(p)
    x=np.array([vector(None),vector(OptionStoryUnit('interaction',False)),vector(OptionStoryUnit('movement',True)),vector(OptionStoryUnit('movement',False))])
    np.testing.assert_array_equal(q.raw_predictions(x),p.raw_predictions(x))
    assert not q.interaction_success_components(x)['certified_interaction_mask'].any()


def test_fixed_ridge_fit_uses_four_actual_targets_but_does_not_relabel_core_count():
    p=base();rr=tuple(row(s)for s in '3456');q,report=fit(p,rr)
    assert report['fits']==1 and report['status']=='PROVISIONAL_NATIVE_FALSIFICATION_ONLY'
    assert q.interaction_success_head.bias==pytest.approx(4/4.25)
    assert report['physical_prior_mse']==pytest.approx(1.) and report['candidate_mse']<1.
    assert report['labels_are_one_class']is True and report['prediction_is_calibrated_probability']is False
    assert q.settled_examples==p.settled_examples==175
    assert q.movement_success_head.to_dict()==p.movement_success_head.to_dict()


def test_insufficient_and_uninformative_rows_do_not_manufacture_fits():
    p=base()
    with patch.object(V.LivingDexOptionValueModel,'interaction_success_components',side_effect=AssertionError('forward')):
        q,r=fit(p,(row('3'),));assert q is None and r['fits']==0
    q,r=fit(base(20.),(row('3'),row('4')));assert q is None and r['status']=='NO_INFORMATIVE_SCALAR_DIRECTION'and r['fits']==0


@pytest.mark.parametrize('fault',['unknown','movement','complete','old_version','duplicate','membership','nontrain','censored','raw_dict','quest_gain','dependency_gain','challenge_absent','combat_required','unknown_combat'])
def test_actual_input_filters_reject_unqualified_or_unattested_rows(fault):
    p=base();rr=[row('3'),row('4')];ids=None
    if fault=='unknown':rr[1]=row('4',vector(None))
    elif fault=='movement':rr[1]=row('4',vector(OptionStoryUnit('movement',True)))
    elif fault=='complete':rr[1]=row('4',vector(OptionStoryUnit('interaction',False)))
    elif fault=='old_version':rr[1]=replace(rr[1],feature_version=15,features=rr[1].features[:-4])
    elif fault=='duplicate':rr[1]=rr[0]
    elif fault=='membership':ids=['5'*64]
    elif fault=='nontrain':object.__setattr__(rr[1],'partition','development')
    elif fault=='censored':rr[1]=replace(rr[1],outcome=V.LivingDexObservedOutcome(V.LivingDexOutcomeStatus.CENSORED,censor_reason=V.LivingDexCensorReason.EXTERNAL_INTERRUPTION))
    elif fault=='quest_gain':rr[1]=replace(rr[1],outcome=replace(rr[1].outcome,completion_gain=.2))
    elif fault=='dependency_gain':rr[1]=replace(rr[1],outcome=replace(rr[1].outcome,dependency_unlock_gain=.2))
    elif fault=='challenge_absent':rr[1]=row('4',vector(challenge=None))
    elif fault=='combat_required':rr[1]=row('4',vector(challenge=OptionChallenge(True,True,1/6,0.,0.)))
    elif fault=='unknown_combat':rr[1]=row('4',vector(challenge=OptionChallenge(True,False,0.,0.,0.)))
    else:rr[1]=rr[1].public_dict();ids=['3'*64,'4'*64]
    with pytest.raises(ValueError):fit(p,rr,ids=ids)


def test_generic_fitter_requires_existing_movement_parent_and_refuses_repeat_heading():
    p=base();rr=(row('3'),row('4'))
    with pytest.raises(ValueError):fit(replace(p,movement_success_head=None),rr)
    with pytest.raises(ValueError):fit(headed(p),rr)
    with pytest.raises(ValueError):V.fit_living_dex_option_value((),feature_version=16,frozen_success_base=headed(p))
@pytest.mark.parametrize('challenge',[None,OptionChallenge(True,False,0.,0.,0.),OptionChallenge(True,True,1/6,0.,0.)])
def test_missing_unknown_or_required_combat_preserves_exact_parent(challenge):
    p=base();q=headed(p);x=vector(challenge=challenge)
    np.testing.assert_array_equal(q.raw_predictions(x),p.raw_predictions(x))
    assert not bool(q.interaction_success_components(x)['certified_interaction_mask'])


def test_valid_bounded_story_parent_cannot_enter_interaction_fitter():
    n=len(V.option_feature_names(9))
    p=V.LivingDexOptionValueModel(np.zeros((n,9)),np.zeros(9),np.zeros(n),np.ones(n),'a'*64,175,0,.25,10.,feature_version=9)
    h=V.LivingDexBoundedStorySuccessHead(np.zeros(n),.1,p.model_sha256)
    p=replace(p,objective=V.LIVING_DEX_BOUNDED_STORY_SUCCESS_OBJECTIVE,bounded_story_success_head=h)
    with pytest.raises(ValueError):fit(p,(row('3'),row('4')))
@pytest.mark.parametrize('name,value',[('challenge.unlock_access_x_present',0.),('challenge.unlock_access_x_combat_required',1.),('challenge.unlock_access_x_opposition_known',1.)])
def test_individual_unsupported_challenge_flags_keep_parent_and_are_not_fit_evidence(name,value):
    p=base();q=headed(p);x=vector();x[V.option_feature_names(16).index(name)]=value
    np.testing.assert_array_equal(q.raw_predictions(x),p.raw_predictions(x))
    assert not bool(q.interaction_success_components(x)['certified_interaction_mask'])
    with pytest.raises(ValueError):fit(p,(row('3'),row('4',x)))