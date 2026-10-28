"""Synthetic ROM-free nullspace contracts; no native TRAIN fit or dataset load."""
from dataclasses import replace
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pytest

import pokemon_red_completion.player_challenge_consequence as h
from pokemon_red_completion.player_consequence_projection import project_consequence_features
from pokemon_red_completion.player_preparation_party_context import PreparationPartyWitness
from pokemon_red_completion.living_dex_option_value import option_feature_names
from pokemon_red_completion.provenance import canonical_sha256

PROJECTION='prospective_preparation_party_context_v1'
RECIPE=dict(ridge=1.,feedback_version=2,feature_version=15,context_projection=PROJECTION)
NAMES=option_feature_names(15)

def view(label,a,b,*,actions=100,resource=0.,censored=False,feedback=2):
    values=[0.]*len(NAMES)
    for name,value in [('kind.unlock_access',1.),('execution_effort',a),('party_risk',b),('resource_cost',resource)]:values[NAMES.index(name)]=value
    outcome=None if censored else h.ChallengeConsequence(True,True,actions,actions*60,0,100+actions,0,feedback,None if feedback==1 else False,None if feedback==1 else 1.)
    row=h.ConsequenceExample(canonical_sha256(dict(synthetic_fixture=label)),'a'*64,tuple(values),outcome,'synthetic_censor'if censored else None,'synthetic',feedback,15)
    return h.ConsequencePartyView(row,PreparationPartyWitness('b'*64,(('fixture1','combat'),('fixture2','combat'))),'c'*64,'d'*64,'work_order_context_pin')

def matrix(views):return np.asarray([project_consequence_features(v.row.features,feature_version=15,context_projection=PROJECTION,party_context=v.party_witness.counts)for v in views])
def public(head,views):return np.asarray([head.predict(v.row.features,party_context=v.party_witness.counts)for v in views])
def bits(values):return np.asarray(values,dtype=np.float64).view(np.uint64)
def nullfit(old,new,reference=None):
    if reference is None:reference=h.fit_challenge_consequence(old,**RECIPE)
    candidate=h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,reference_residual_mode='affine_nullspace',**RECIPE)
    return reference,candidate

@pytest.fixture
def fixture():
    old=(view('old0',0.,0.,actions=100),view('old1',1.,1.,actions=200))
    new=(view('new-offspan',1.,0.,actions=1200),)
    return old,new,h.fit_challenge_consequence(old,**RECIPE)

def assert_retained(reference,candidate,old):
    for field in ('feature_mean','feature_scale','intercept'):assert np.array_equal(bits(getattr(reference,field)),bits(getattr(candidate,field)))
    z=(matrix(old)-reference.feature_mean)/reference.feature_scale
    np.testing.assert_allclose(z@reference.coefficients+reference.intercept,z@candidate.coefficients+candidate.intercept,atol=1e-10,rtol=0.)
    before,after=public(reference,old),public(candidate,old)
    np.testing.assert_allclose(before,after,atol=1e-10,rtol=0.)
    utility=np.asarray(h.consequence_contract(2)[3]);np.testing.assert_allclose(before@utility,after@utility,atol=1e-6,rtol=0.)

def test_offspan_correction_without_new_zero_coordinate_preserves_old_outputs_and_order(fixture):
    old,new,reference=fixture
    with pytest.raises(ValueError,match='zero-basis'):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,**RECIPE)
    reference,candidate=nullfit(old,new,reference);assert_retained(reference,candidate,old)
    target=np.asarray([v.row.outcome.vector()for v in new])
    assert np.square(public(candidate,new)-target).sum()<np.square(public(reference,new)-target).sum()
    utility=np.asarray(h.consequence_contract(2)[3]);before=public(reference,old)@utility;after=public(candidate,old)@utility
    assert abs(before[1]-before[0])>1e-6 and np.sign(before[1]-before[0])==np.sign(after[1]-after[0])
    assert candidate.examples==3 and candidate.provenance=='synthetic'
    restored=h.ChallengeConsequenceHead.from_document(candidate.document(),expected_sha256=candidate.model_sha256)
    assert restored.document()==candidate.document()

def test_exact_tied_retained_inputs_keep_their_forecast_tie():
    old=(view('tie0',0.,0.,actions=100),view('tie1',1.,1.,actions=200),view('tie2',0.,0.,actions=100))
    reference,candidate=nullfit(old,(view('tie-new',1.,0.,actions=1200),));assert_retained(reference,candidate,old)
    assert np.array_equal(public(candidate,(old[0],)),public(candidate,(old[2],)))

def test_censored_retained_geometry_is_not_dropped():
    old=(view('c0',0.,0.),view('c1',1.,1.,actions=200),view('c2',.25,.25,censored=True))
    reference,candidate=nullfit(old,(view('c-new',1.,0.,actions=1200),));assert reference.examples==2;assert_retained(reference,candidate,old)
    # This censored input spans the previously missing direction. It must block
    # a correction which would otherwise change its forecast despite no label.
    blocked=old[:2]+(view('c-offspan',1.,0.,censored=True),)
    ref=h.fit_challenge_consequence(blocked,**RECIPE)
    with pytest.raises(ValueError,match='identifiable new direction'):nullfit(blocked,(view('c-in-fullspan',0.,1.,actions=1200),),ref)

def test_no_new_offspan_support_or_settled_row_rejected(fixture):
    old,_,reference=fixture
    with pytest.raises(ValueError,match='identifiable new direction'):nullfit(old,(view('same-span',.5,.5,actions=1200),),reference)
    with pytest.raises(ValueError,match='new settled'):nullfit(old,(view('no-new-label',1.,0.,censored=True),),reference)

def test_missing_legacy_channels_are_not_fabricated(fixture):
    old,_,reference=fixture
    _,candidate=nullfit(old,(view('legacy-new',1.,0.,actions=1200,feedback=1),),reference)
    assert_retained(reference,candidate,old)
    assert np.isfinite(candidate.coefficients).all()
    np.testing.assert_allclose(candidate.coefficients[:,7:],reference.coefficients[:,7:],atol=1e-10,rtol=0.)

@pytest.mark.parametrize('mode',[None,False,'nullspace','AFFINE_NULLSPACE'])
def test_mode_is_explicit_and_rejects_unknown_values(fixture,mode):
    old,new,reference=fixture
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,reference_residual_mode=mode,**RECIPE)

def test_reference_and_fixed_recipe_are_required(fixture):
    old,new,reference=fixture
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_residual_mode='affine_nullspace',**RECIPE)
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_head=reference,reference_residual_mode='affine_nullspace',**RECIPE)
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=(replace(old[0],source_context_sha256='e'*64),old[1]),reference_residual_mode='affine_nullspace',**RECIPE)
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,reference_residual_mode='affine_nullspace',**dict(RECIPE,ridge=2.))

def test_unstable_rank_rejected_without_residual_solve(fixture,monkeypatch):
    old,new,reference=fixture;called=[]
    monkeypatch.setattr(np.linalg,'svd',lambda z,full_matrices:(np.eye(len(z)),np.asarray([1.,1e-10]),np.eye(z.shape[1])))
    monkeypatch.setattr(np.linalg,'solve',lambda *a:called.append(1))
    with pytest.raises(ValueError,match='rank is numerically unstable'):nullfit(old,new,reference)
    assert called==[]

def test_nonfinite_svd_and_retained_basis_leak_rejected(fixture,monkeypatch):
    old,new,reference=fixture;original=np.linalg.svd
    def bad_svd(z,full_matrices):
        u,s,v=original(z,full_matrices=full_matrices);v[1]=v[0];return u,s,v
    monkeypatch.setattr(np.linalg,'svd',bad_svd)
    with pytest.raises(ValueError,match='retained basis leakage'):nullfit(old,new,reference)
    def nan_svd(z,full_matrices):
        u,s,v=original(z,full_matrices=full_matrices);v[1,0]=np.nan;return u,s,v
    monkeypatch.setattr(np.linalg,'svd',nan_svd)
    with pytest.raises(ValueError,match='nonfinite'):nullfit(old,new,reference)

def test_nonfinite_residual_solution_and_amplified_rounding_leak_rejected(fixture,monkeypatch):
    old,new,reference=fixture
    monkeypatch.setattr(np.linalg,'solve',lambda a,b:np.full_like(b,np.nan))
    with pytest.raises(ValueError,match='nonfinite'):nullfit(old,new,reference)
    monkeypatch.setattr(np.linalg,'solve',lambda a,b:np.full_like(b,1e20))
    with pytest.raises(ValueError,match='retained affine output leakage'):nullfit(old,new,reference)

def test_public_prediction_calls_are_explicit_two_per_retained_input(fixture,monkeypatch):
    old,new,reference=fixture;calls=[];predict=h.ChallengeConsequenceHead.predict
    def counted(self,*args,**kwargs):calls.append(self);return predict(self,*args,**kwargs)
    monkeypatch.setattr(h.ChallengeConsequenceHead,'predict',counted)
    nullfit(old,new,reference)
    assert len(calls)==2*len(old)

def test_default_and_coordinate_mode_documents_match_frozen_p18():
    root=Path(__file__).resolve().parents[2]/'windows-seven-goal-implementation-20261017'
    path=root/'blaine-direct-move-20261027-0054/native-candidate18/frozen-runtime/checkout/src/pokemon_red_completion/player_challenge_consequence.py'
    if not path.exists():pytest.skip('private frozen P18 source unavailable')
    name='pokemon_red_completion._frozen_p18_nullspace_compatibility';spec=importlib.util.spec_from_file_location(name,path);frozen=importlib.util.module_from_spec(spec);sys.modules[name]=frozen;spec.loader.exec_module(frozen)
    old=(view('compat0',0.,0.),view('compat1',1.,1.,actions=200));new=(view('compat-resource',.5,.5,resource=1.,actions=800),)
    convert=lambda rows:tuple(frozen.ConsequencePartyView(frozen.ConsequenceExample.from_document(v.row.document()),v.party_witness,v.source_context_sha256,v.source_work_order_sha256,v.role_evidence)for v in rows)
    old_f,new_f=convert(old),convert(new);ref_f=frozen.fit_challenge_consequence(old_f,**RECIPE);ref=h.fit_challenge_consequence(old,**RECIPE)
    assert ref.document()==ref_f.document() and ref.model_sha256==ref_f.model_sha256
    expected=frozen.fit_challenge_consequence(old_f+new_f,reference_head=ref_f,retained_rows=old_f,**RECIPE)
    actual=h.fit_challenge_consequence(old+new,reference_head=ref,retained_rows=old,**RECIPE)
    explicit=h.fit_challenge_consequence(old+new,reference_head=ref,retained_rows=old,reference_residual_mode='coordinate_zero',**RECIPE)
    assert actual.document()==expected.document()==explicit.document()
    assert actual.model_sha256==expected.model_sha256==explicit.model_sha256
