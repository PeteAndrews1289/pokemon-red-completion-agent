"""Synthetic ROM-free correction checks; fixtures are not project TRAIN evidence."""
from dataclasses import replace
import copy
import numpy as np
import pytest
import pokemon_red_completion.living_dex_option_value as V
from pokemon_red_completion.preparation_success import PreparationSuccessHead, PreparationSuccessExample, fit_preparation_success, preparation_mask
from pokemon_red_completion.player_option_preparation import OptionPreparation
from test_certified_interaction_success import base, headed, vector

def prep(level=24,target=27,xp=5155):
    context=V.LivingDexOptionContext(.3,.4,.5,.2,.1,.2,.1)
    candidate=V.LivingDexOptionCandidate('synthetic:preparation',V.LivingDexOptionFeatures(V.LivingDexOptionKind.DEVELOP,.0,.25,.0,1.,0.,0.,.2,0.,0.),V.LivingDexOptionAvailability.AVAILABLE,preparation=OptionPreparation(level,target,xp,1.,1.,True,False,26))
    return np.asarray(candidate.vector(context,feature_version=16))

def parent():return headed(base(1.5))
def head(p):
    return PreparationSuccessHead((-.3,)+(0.,)*12,(1.,)*13,p.model_sha256,'a'*64,'b'*64,('5'*64,'6'*64),1)
def example(h,y,x=None):return PreparationSuccessExample(h*64,'train',tuple(map(float,prep()if x is None else x)),y)
def fit(p,rows):
    return fit_preparation_success(rows,frozen_base=p,attestation_sha256='e'*64,attested_decision_sha256s=tuple(r.decision_sha256 for r in rows),protected_features=np.asarray([vector(),vector(None)]),protected_decision_sha256s=('c'*64,'d'*64))

def test_old_codec_hash_and_predictions_are_unchanged_when_absent():
    p=parent();doc=p.to_dict();assert 'preparation_success_head'not in doc
    restored=V.LivingDexOptionValueModel.from_dict(doc)
    assert restored.to_dict()==doc and restored.model_sha256==p.model_sha256
    np.testing.assert_array_equal(restored.raw_predictions(np.array([prep(),vector()])),p.raw_predictions(np.array([prep(),vector()])))

def test_child_keeps_exact_parent_and_old_head_documents():
    p=parent();q=replace(p,preparation_success_head=head(p));doc=q.to_dict();doc.pop('preparation_success_head');assert doc==p.to_dict()
    assert q.movement_success_head is p.movement_success_head and q.interaction_success_head is p.interaction_success_head
    restored=V.LivingDexOptionValueModel.from_dict(q.to_dict());assert restored.model_sha256==q.model_sha256
    np.testing.assert_array_equal(restored.raw_predictions(prep()),q.raw_predictions(prep()))

def test_retains_all_other_outcomes_and_off_scope_exactly():
    p=parent();q=replace(p,preparation_success_head=head(p));x=np.array([prep(),vector(),vector(None)])
    a=p.raw_predictions(x);b=q.raw_predictions(x)
    np.testing.assert_array_equal(a[:,1:],b[:,1:]);np.testing.assert_array_equal(a[1:],b[1:]);assert b[0,0]!=a[0,0]
    for k in ['coefficients','intercept','feature_mean','feature_scale']:np.testing.assert_array_equal(getattr(p,k),getattr(q,k))
    assert q.settled_examples==p.settled_examples and q.train_dataset_sha256==p.train_dataset_sha256

def test_preparation_prior_excludes_existing_strategic_products():
    p=parent();q=replace(p,preparation_success_head=head(p));a=prep();b=a.copy();names=V.option_feature_names(16)
    for name in V._MOVEMENT_STRATEGIC_FEATURE_NAMES:b[names.index(name)]=0.
    assert q.preparation_success_components(a)['preclip']==q.preparation_success_components(b)['preclip']

def test_strict_frozen_parent_is_still_enforced():
    p=parent();q=replace(p,preparation_success_head=head(p));doc=q.to_dict();doc['coefficients'][0][0]+=.1
    with pytest.raises(ValueError):V.LivingDexOptionValueModel.from_dict(doc)
    with pytest.raises(ValueError):replace(head(p),parent_model_sha256='f'*64);replace(p,preparation_success_head=replace(head(p),parent_model_sha256='f'*64))

@pytest.mark.parametrize('field,value',[('ridge',.5),('gate','all-options'),('base','raw'),('feature_version',15),('prediction_is_calibrated_probability',True),('live_policy_adopted',True),('feature_names',[]),('successful_examples',0),('feature_scales',[0.]*13),('coefficients',[float('nan')]*13)])
def test_codec_rejects_corrupt_semantics(field,value):
    p=parent();doc=replace(p,preparation_success_head=head(p)).to_dict();doc['preparation_success_head'][field]=value
    with pytest.raises(ValueError):V.LivingDexOptionValueModel.from_dict(doc)

def test_scope_rejects_fake_present_or_wrong_kind():
    x=prep();names=V.option_feature_names(16);x[names.index('kind.develop')]=0.;x[names.index('kind.acquire')]=1.
    with pytest.raises(ValueError):preparation_mask(x)
    x=prep();x[names.index('preparation.present')]=.5
    with pytest.raises(ValueError):preparation_mask(x)

def test_fit_reuses_retention_and_preserves_existing_corrections():
    p=parent();rows=(example('5',False),example('6',True,prep(5,6,100)));q,report=fit(p,rows)
    assert report['fits']==1 and report['candidate_MSE']<report['parent_MSE']
    assert report['retained_outputs_bitwise_equal']and report['other_outcomes_bitwise_equal']
    assert q.movement_success_head is p.movement_success_head and q.interaction_success_head is p.interaction_success_head
    assert q.to_dict()['preparation_success_head']['decision_sha256s']==['5'*64,'6'*64]

@pytest.mark.parametrize('bad',['development','unknown_target','nonprep','missing_member','duplicates','one_class','retention_prep','already_corrected'])
def test_fit_cannot_coerce_unsupported_or_unattested_data(bad):
    p=parent();rows=(example('5',False),example('6',True,prep(5,6,100)));kw=dict(frozen_base=p,attestation_sha256='e'*64,attested_decision_sha256s=('5'*64,'6'*64),protected_features=np.asarray([vector()]),protected_decision_sha256s=('c'*64,))
    with pytest.raises((ValueError,TypeError)):
        if bad=='development':rows=(replace(rows[0],partition='development'),rows[1])
        elif bad=='unknown_target':rows=(replace(rows[0],target_success=None),rows[1])
        elif bad=='nonprep':rows=(replace(rows[0],features=tuple(vector())),rows[1])
        elif bad=='missing_member':kw['attested_decision_sha256s']=('5'*64,)
        elif bad=='duplicates':rows=(rows[0],rows[0])
        elif bad=='one_class':rows=(rows[0],replace(rows[1],target_success=False))
        elif bad=='retention_prep':kw['protected_features']=np.asarray([prep()])
        else:kw['frozen_base']=replace(p,preparation_success_head=head(p))
        fit_preparation_success(rows,**kw)
