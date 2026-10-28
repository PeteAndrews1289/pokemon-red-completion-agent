"""ROM-free numerical fixtures; never fit the optional private native records."""
from dataclasses import replace
from pathlib import Path
import importlib.util
import json
import sys

import numpy as np
import pytest

import pokemon_red_completion.player_challenge_consequence as h
from pokemon_red_completion.player_preparation_party_context import PreparationPartyWitness
from pokemon_red_completion.player_consequence_projection import project_consequence_features,consequence_feature_names
from pokemon_red_completion.living_dex_option_value import option_feature_names
from pokemon_red_completion.provenance import canonical_sha256

PROJECTION='prospective_preparation_party_context_v1'
RECIPE=dict(ridge=1.,feedback_version=2,feature_version=15,context_projection=PROJECTION)
NAMES=option_feature_names(15)

def view(label,*,effort=0.,resource=0.,risk=0.,actions=100,censored=False,feedback=2):
    features=[0.]*len(NAMES)
    for name,value in [('kind.unlock_access',1.),('execution_effort',effort),('resource_cost',resource),('irreversibility_risk',risk)]:
        features[NAMES.index(name)]=value
    outcome=None if censored else h.ChallengeConsequence(
        True,True,actions,actions*60,0,100+actions,0,feedback,
        None if feedback==1 else False,None if feedback==1 else 1.)
    row=h.ConsequenceExample(canonical_sha256(dict(unit_fixture=label)),'a'*64,tuple(features),outcome,
        'unit_fixture_censored' if censored else None,'synthetic',feedback,15)
    witness=PreparationPartyWitness('b'*64,(('unit-member-1','combat'),('unit-member-2','combat')))
    return h.ConsequencePartyView(row,witness,'c'*64,'d'*64,'work_order_context_pin')

def matrix(views):
    return np.asarray([project_consequence_features(v.row.features,feature_version=15,
        context_projection=PROJECTION,party_context=v.party_witness.counts) for v in views])

def predictions(head,views):
    return np.asarray([head.predict(v.row.features,party_context=v.party_witness.counts) for v in views])

def bits(array):return np.asarray(array,dtype=np.float64).view(np.uint64)

@pytest.fixture
def fixture():
    old=(view('old0',effort=0.,actions=100),view('old1',effort=1.,actions=200))
    new=(view('new0',resource=1.,actions=1000),view('new1',risk=1.,actions=2000))
    reference=h.fit_challenge_consequence(old,**RECIPE)
    return old,new,reference

def test_reference_residual_retains_old_bits_and_improves_new_synthetic_targets(fixture):
    old,new,reference=fixture
    candidate=h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,**RECIPE)
    X=matrix(old+new);Z=(X-reference.feature_mean)/reference.feature_scale
    eligible=np.all(X[:2]==reference.feature_mean,axis=0)&np.all(Z[:2]==0.,axis=0)&np.any(Z[2:]!=0.,axis=0)
    assert eligible.sum()==2
    for field in ('feature_mean','feature_scale','intercept'):
        assert np.array_equal(bits(getattr(candidate,field)),bits(getattr(reference,field)))
    assert np.array_equal(bits(candidate.coefficients[~eligible]),bits(reference.coefficients[~eligible]))
    assert np.array_equal(bits(predictions(candidate,old)),bits(predictions(reference,old)))
    assert np.array_equal(bits(Z[:2]@candidate.coefficients+candidate.intercept),
                          bits(Z[:2]@reference.coefficients+reference.intercept))
    targets=np.asarray([v.row.outcome.vector() for v in new])
    assert np.square(predictions(candidate,new)-targets).sum()<np.square(predictions(reference,new)-targets).sum()
    assert candidate.examples==4 and candidate.provenance=='synthetic'
    expected=canonical_sha256([v.document() for v in sorted(old+new,key=lambda v:v.row.declaration_sha256)])
    assert candidate.evidence_sha256==expected
    restored=h.ChallengeConsequenceHead.from_document(candidate.document(),expected_sha256=candidate.model_sha256)
    assert restored.document()==candidate.document()

def test_residual_is_unclipped_and_uncentered(fixture):
    old,new,reference=fixture
    intercept=reference.intercept.copy();intercept[2]=-1.
    reference=replace(reference,intercept=intercept)
    candidate=h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,**RECIPE)
    X=matrix(old+new);Z=(X-reference.feature_mean)/reference.feature_scale
    eligible=np.all(X[:2]==reference.feature_mean,axis=0)&np.all(Z[:2]==0.,axis=0)&np.any(Z[2:]!=0.,axis=0)
    selected=Z[:,eligible]
    y=np.asarray([v.row.outcome.vector() for v in old+new])
    # Fit ordering is canonical, so compute the same ridge objective independent
    # of input order using the closed-form primal solution on the two columns.
    residual=y[:,2]-(Z@reference.coefficients[:,2]+reference.intercept[2])
    expected=np.linalg.solve(selected.T@selected+np.eye(eligible.sum()),selected.T@residual)
    assert np.allclose(candidate.coefficients[eligible,2]-reference.coefficients[eligible,2],expected,rtol=0,atol=1e-14)
    assert np.array_equal(bits(candidate.intercept),bits(reference.intercept))

@pytest.mark.parametrize('change',[dict(ridge=2.),dict(feedback_version=1),dict(feature_version=10),
    dict(cash_prediction='certified_single_trainer_v1'),dict(include_recovery_purchases=True),dict(context_projection='identity')])
def test_changed_reference_contract_rejected(fixture,change):
    old,new,reference=fixture;recipe=dict(RECIPE,**change)
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,**recipe)

def test_missing_forged_and_non_subset_retained_evidence_rejected(fixture):
    old,new,reference=fixture
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,retained_rows=old,**RECIPE)
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_head=reference,**RECIPE)
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_head=object(),retained_rows=old,**RECIPE)
    forged=(replace(old[0],source_context_sha256='e'*64),old[1])
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=forged,**RECIPE)
    with pytest.raises(ValueError):h.fit_challenge_consequence((old[0],)+new,reference_head=reference,retained_rows=old,**RECIPE)
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=(old[0],old[0]),**RECIPE)
    with pytest.raises(ValueError):h.fit_challenge_consequence(old+new,reference_head=replace(reference,examples=3),retained_rows=old,**RECIPE)

def test_censored_retained_features_participate_in_zero_basis_and_example_count():
    old=(view('c-old0',actions=100),view('c-old1',effort=1.,actions=200),view('censored',resource=1.,censored=True))
    reference=h.fit_challenge_consequence(old,**RECIPE)
    assert reference.examples==2
    new=(view('c-new0',resource=1.,risk=1.,actions=1000),view('c-new1',risk=2.,actions=2000))
    candidate=h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,**RECIPE)
    resource_index=consequence_feature_names(15,PROJECTION).index('resource_cost')
    assert np.array_equal(bits(candidate.coefficients[resource_index]),bits(reference.coefficients[resource_index]))
    assert np.array_equal(bits(predictions(candidate,old)),bits(predictions(reference,old)))
    old_z=(matrix(old)-reference.feature_mean)/reference.feature_scale
    assert np.array_equal(bits(old_z@candidate.coefficients+candidate.intercept),
                          bits(old_z@reference.coefficients+reference.intercept))
    assert candidate.examples==4
    # An active feature on a censored retained row cannot be treated as absent.
    only_resource=(view('blocked-new0',resource=1.,actions=1000),view('blocked-new1',resource=2.,actions=2000))
    with pytest.raises(ValueError,match='zero-basis'):h.fit_challenge_consequence(old+only_resource,reference_head=reference,retained_rows=old,**RECIPE)

def test_legacy_new_rows_do_not_invent_missing_v2_labels(fixture):
    old,_,reference=fixture
    new=(view('legacy-new0',resource=1.,actions=1000,feedback=1),view('legacy-new1',risk=1.,actions=2000,feedback=1))
    candidate=h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,**RECIPE)
    assert np.array_equal(bits(candidate.coefficients[:,7:]),bits(reference.coefficients[:,7:]))
    assert np.array_equal(bits(candidate.intercept[7:]),bits(reference.intercept[7:]))
    assert np.isfinite(candidate.coefficients).all()

def test_new_censored_rows_are_not_active_fitting_support(fixture):
    old,_,reference=fixture
    new=(view('new-censored',resource=1.,censored=True),)
    with pytest.raises(ValueError,match='zero-basis'):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,**RECIPE)

def test_near_zero_and_underflow_do_not_create_eligible_support(fixture):
    old,_,reference=fixture
    ix=consequence_feature_names(15,PROJECTION).index('resource_cost')
    mean=reference.feature_mean.copy();scale=reference.feature_scale.copy()
    mean[ix]=np.nextafter(0.,1.);scale[ix]=1e308
    reference=replace(reference,feature_mean=mean,feature_scale=scale)
    new=(view('underflow-new0',resource=1.,actions=1000),view('underflow-new1',resource=2.,actions=2000))
    with np.errstate(under='ignore'):
        assert ((matrix(old)[:,ix]-mean[ix])/scale[ix]==0.).all()
    with pytest.raises(ValueError,match='zero-basis'):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,**RECIPE)

def test_nonfinite_normalized_input_and_solution_rejected(fixture,monkeypatch):
    old,new,reference=fixture
    ix=consequence_feature_names(15,PROJECTION).index('resource_cost')
    scale=reference.feature_scale.copy();scale[ix]=np.nextafter(0.,1.)
    with pytest.raises(ValueError,match='nonfinite'):h.fit_challenge_consequence(old+new,reference_head=replace(reference,feature_scale=scale),retained_rows=old,**RECIPE)
    # z is finite here, but its Gram matrix overflows. A finite zero returned
    # by a solver on an inf diagonal must not be admitted as a valid solution.
    scale[ix]=1e-200
    with pytest.raises(ValueError,match='nonfinite'):h.fit_challenge_consequence(old+new,reference_head=replace(reference,feature_scale=scale),retained_rows=old,**RECIPE)
    monkeypatch.setattr(np.linalg,'solve',lambda a,b:np.full_like(b,np.nan))
    with pytest.raises(ValueError,match='nonfinite'):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,**RECIPE)

def test_nonfinite_affine_residual_rejected(fixture):
    old,_,reference=fixture
    ix=consequence_feature_names(15,PROJECTION).index('resource_cost')
    coefficients=reference.coefficients.copy();coefficients[ix,2]=1e308
    reference=replace(reference,coefficients=coefficients)
    new=(view('overflow-affine0',resource=2.,actions=1000),view('overflow-affine1',risk=1.,actions=2000))
    with pytest.raises(ValueError,match='nonfinite'):h.fit_challenge_consequence(old+new,reference_head=reference,retained_rows=old,**RECIPE)

def private_root():
    # Optional source-evidence checks use local archived bytes only. No real
    # native TRAIN view is ever passed to a fitting function in this test file.
    root=Path(__file__).resolve().parents[2]/'windows-seven-goal-implementation-20261017'
    if not root.exists():pytest.skip('private migrated evidence unavailable')
    return root

def test_default_synthetic_documents_and_model_sha_match_frozen_p17():
    root=private_root();path=root/'blaine-direct-move-20261027-0054/native-candidate17/frozen-runtime/checkout/src/pokemon_red_completion/player_challenge_consequence.py'
    if not path.exists():pytest.skip('private frozen P17 source unavailable')
    name='pokemon_red_completion._reference_fitter_frozen_p17'
    spec=importlib.util.spec_from_file_location(name,path);frozen=importlib.util.module_from_spec(spec);sys.modules[name]=frozen;spec.loader.exec_module(frozen)
    fixtures=(view('default0',effort=0.,actions=100),view('default1',effort=1.,actions=200),view('default2',resource=1.,actions=400))
    old_fixtures=tuple(frozen.ConsequencePartyView(frozen.ConsequenceExample.from_document(v.row.document()),v.party_witness,v.source_context_sha256,v.source_work_order_sha256,v.role_evidence) for v in fixtures)
    expected=frozen.fit_challenge_consequence(old_fixtures,**RECIPE)
    actual=h.fit_challenge_consequence(fixtures,**RECIPE)
    assert actual.document()==expected.document() and actual.model_sha256==expected.model_sha256

def test_private_original_native_party_views_and_evidence_digest_only():
    root=private_root();path=root/'blaine-direct-move-20261027-0054/fit14-inputs-v1/FOURTEEN-ROW-PROPOSED-MANIFEST.json'
    if not path.exists():pytest.skip('private exact fourteen-row views unavailable')
    manifest=json.loads(path.read_bytes());views=tuple(h.ConsequencePartyView.from_document(json.loads(Path(e['view']).read_bytes())) for e in manifest['rows'])
    head=json.loads((root/'stopping-switching-20261025-2240/stopping-fit12-v1/CONSEQUENCE-HEAD.json').read_bytes())
    assert len(views)==14 and all(v.row.provenance=='native_train' for v in views)
    assert matrix(views).shape==(14,321)
    assert canonical_sha256([v.document() for v in sorted(views[:12],key=lambda v:v.row.declaration_sha256)])==head['evidence_sha256']
    # No fitter, head.predict, head.scores or parameter change on native inputs.
