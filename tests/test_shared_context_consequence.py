"""ROM-free projection/learning contracts; synthetic rows are not native evidence."""
from dataclasses import replace
import numpy as np
import pytest

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind, option_feature_names
from pokemon_red_completion.player_challenge_consequence import (
    ChallengeConsequence, ChallengeConsequenceHead, ConsequenceExample, fit_challenge_consequence,
    PROGRESS_UTILITY,
)
from pokemon_red_completion.player_consequence_projection import (
    SHARED_CONTEXT, consequence_feature_names, consequence_normalization_scale, project_consequence_features,
)
from pokemon_red_completion.provenance import canonical_sha256

NAMES=option_feature_names(10)

def raw(kind='unlock_access', hp=.5, budget=1.):
    values=np.zeros(len(NAMES))
    for name,value in [(f'kind.{kind}',1.),(f'readiness.{kind}_x_observed',1.),
                       (f'readiness.{kind}_x_current.hp_fraction',hp),
                       (f'readiness.{kind}_x_budget.seconds',budget),
                       (f'challenge.{kind}_x_present',1.),(f'challenge.{kind}_x_combat_required',1.),
                       (f'challenge.{kind}_x_opposition_known',1.),(f'challenge.{kind}_x_opponent_fraction',.5),
                       (f'challenge.{kind}_x_median_level_deficit',-.12)]:
        values[NAMES.index(name)]=value
    return tuple(float(value) for value in values)

def project(values):
    return project_consequence_features(values,feature_version=10,context_projection=SHARED_CONTEXT)

def head(coefficients=None):
    width=len(consequence_feature_names(10,SHARED_CONTEXT))
    co=np.zeros((width,9)) if coefficients is None else coefficients
    return ChallengeConsequenceHead(co,np.array([1.,.5,0.,0.,0.,0.,0.,0.,.5]),
        np.zeros(width),np.ones(width),'a'*64,2,1.,'synthetic',feedback_version=2,
        feature_version=10,cash_prediction='certified_single_trainer_v1',context_projection=SHARED_CONTEXT)

@pytest.mark.parametrize('kind',[kind.value for kind in LivingDexOptionKind])
def test_common_facts_survive_kind_projection_without_losing_original_interactions(kind):
    before=raw(kind);after=project(before);names=consequence_feature_names(10,SHARED_CONTEXT)
    assert after[:len(before)]==before
    assert len(after)==len(before)+34
    assert after[names.index('shared_challenge.median_level_deficit')]==-.12
    assert after[names.index('shared_readiness.current.hp_fraction')]==.5
    assert after[NAMES.index(f'readiness.{kind}_x_current.hp_fraction')]==.5
    assert after[len(before):]==project(raw())[len(before):]

def test_unknown_facts_remain_distinct_from_observed_zero_and_noncombat():
    unknown=project((0.,)*len(NAMES));known=list(raw())
    for name in NAMES:
        if name.startswith('challenge.unlock_access_x_') and not name.endswith('_present'):
            known[NAMES.index(name)]=0.
    observed=project(tuple(known));names=consequence_feature_names(10,SHARED_CONTEXT)
    assert unknown[names.index('shared_challenge.present')]==0.
    assert observed[names.index('shared_challenge.present')]==1.
    assert observed[names.index('shared_challenge.combat_required')]==0.

@pytest.mark.parametrize('fault',['short','augmented','mode','version'])
def test_projection_never_reinterprets_wrong_width_mode_or_version(fault):
    values=raw();version=10;mode=SHARED_CONTEXT
    if fault=='short':values=values[:-1]
    if fault=='augmented':values=project(values)
    if fault=='mode':mode='unknown'
    if fault=='version':version=9
    with pytest.raises(ValueError):project_consequence_features(values,feature_version=version,context_projection=mode)

def test_training_only_normalization_bounds_startup_jitter_and_preserves_noncontext_scales():
    rows=np.asarray([project(raw(kind,hp,budget)) for kind,hp,budget in
        [('develop',.5,.99992),('unlock_access',.5,.99985),('develop',.6,.99989),('unlock_access',.6,.9999)]])
    names=consequence_feature_names(10,SHARED_CONTEXT);mean=rows.mean(axis=0)
    scale=consequence_normalization_scale(rows,feature_version=10,context_projection=SHARED_CONTEXT)
    budget=names.index('shared_readiness.budget.seconds')
    assert scale[budget]==.1
    assert scale[names.index('shared_readiness.observed')]==1.
    assert scale[names.index('readiness.develop_x_observed')]==2.
    assert scale[names.index('kind.develop')]==.5
    before=scale.copy()
    for value in (1.,.9,.5,0.):
        z=(np.asarray(project(raw(budget=value)))-mean)/scale
        assert np.isfinite(z).all() and abs(z[budget])<=10.
    assert np.array_equal(scale,before)  # Held-out measurements cannot alter fit statistics.

def test_real_readiness_by_preparation_choice_reversal_remains_representable():
    names=consequence_feature_names(10,SHARED_CONTEXT);coefficients=np.zeros((len(names),9))
    # Shared HP improves success; preparation additionally helps only at low HP.
    coefficients[names.index('shared_readiness.current.hp_fraction'),1]=.3
    coefficients[names.index('kind.develop'),1]=.3
    coefficients[names.index('readiness.develop_x_current.hp_fraction'),1]=-.5
    model=head(coefficients)
    differences=[]
    for hp in (.1,.9):
        p=model.predict(raw('develop',hp))[1];d=model.predict(raw('unlock_access',hp))[1]
        differences.append(p-d)
    assert differences[0]>.2 and differences[1]<-.1
    assert model.predict(raw('develop',.1,.9999))==model.predict(raw('develop',.1,1.))

@pytest.mark.parametrize('version,expected',[
    (7,'0fc4e54df40053efc68ca7b55769a1d3e364e8e7b6558e5d3f43443bd1cd5eec'),
    (9,'525daac39a5fd6e55fb1ba24d8670f20230a927eb42c96b8f3719dd528f5a824'),
    (10,'9754e71de908b7e1367c17013698e448a369c09e35d3408035b4e3962bcbd53d'),
    (11,'7371c330b61691721f36da94d64bbfcf811bc4ecd5bd3f4bec1866c4f0e37bd9'),
])
def test_legacy_fit_document_and_prediction_identity_remain_exact(version,expected):
    raw_version=min(version,10);width=len(option_feature_names(raw_version))
    rows=tuple(ConsequenceExample(str(k+1)*64,'f'*64,
        tuple(float(k) if j==0 else 0. for j in range(width)),
        ChallengeConsequence(True,bool(k),100+20*k,1000+200*k,50*(1-k),0,0),None,
        feature_version=raw_version) for k in range(2))
    model=fit_challenge_consequence(rows,feature_version=version)
    assert model.model_sha256==expected
    assert 'context_projection' not in model.document()
    restored=ChallengeConsequenceHead.from_document(model.document(),expected_sha256=expected)
    features=rows[0].features+(0.,)*(len(option_feature_names(version))-width)
    assert restored.predict(features)==model.predict(features)

def test_shared_fit_predict_and_cash_projection_match_exported_coefficients():
    rows=[]
    for hp in (.1,.3,.7,.9):
        for kind in ('unlock_access','develop'):
            won=hp>.5
            rows.append(ConsequenceExample(f'{len(rows)+1:064x}','f'*64,raw(kind,hp),
                ChallengeConsequence(True,won,100,1000,0,0,0,feedback_version=2,
                    initial_goal_failed=False,challenge_progress=float(won)),None,
                feature_version=10,feedback_version=2))
    model=fit_challenge_consequence(rows,feature_version=10,feedback_version=2,
        context_projection=SHARED_CONTEXT,cash_prediction='certified_single_trainer_v1')
    restored=ChallengeConsequenceHead.from_document(model.document(),expected_sha256=model.model_sha256)
    assert model.provenance=='synthetic'
    for values in [row.features for row in rows]+[raw('develop',.6,.5)]:
        pred=model.predict(values,single_battle_loss_debit=407)
        linear=((np.asarray(project(values))-model.feature_mean)/model.feature_scale)@model.coefficients+model.intercept
        assert pred[1]==pytest.approx(min(np.clip(linear[0],0.,1.),np.clip(linear[1],0.,1.)))
        assert pred[4]*1500==pytest.approx(407*(pred[0]-pred[1]))
        assert pred==restored.predict(values,single_battle_loss_debit=407)
    assert model.predict(raw(hp=.9))[1]>model.predict(raw(hp=.1))[1]+.5

@pytest.mark.parametrize('field',['names','multiplier','floor','mode'])
def test_rehashed_projection_metadata_tampering_is_rejected(field):
    document=head().document()
    if field=='names':document['feature_names'][-1]='invented'
    if field=='multiplier':document['context_projection_parameters']['interaction_scale_multiplier']=2.
    if field=='floor':document['context_projection_parameters']['minimum_context_scale']=.01
    if field=='mode':document['context_projection']='identity'
    with pytest.raises(ValueError):ChallengeConsequenceHead.from_document(document,expected_sha256=canonical_sha256(document))

def test_live_menu_scores_use_same_shared_projection_without_input(tmp_path,monkeypatch):
    from test_cash_consequence_contract import certified_options
    options,runtime,inputs=certified_options(tmp_path,monkeypatch);model=head()
    exposures=(407,407,407)
    scores=model.scores(options.menu,challenge_refs=('same',)*3,single_battle_loss_debits=exposures)
    expected=tuple(sum(w*v for w,v in zip(PROGRESS_UTILITY,model.predict(
        options.menu.candidate_vector(i,feature_version=10),single_battle_loss_debit=407),strict=True)) for i in range(3))
    assert scores==expected and not inputs and runtime.emulator.state==b'source'
