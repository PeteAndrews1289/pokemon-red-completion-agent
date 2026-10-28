"""Public API/codec checks on synthetic rows only; no actual TRAIN/native data."""
from dataclasses import replace
import copy,json
import numpy as np
import pytest
import pokemon_red_completion.player_challenge_consequence as h
from pokemon_red_completion.living_dex_option_value import option_feature_names
from test_consequence_order_retention_api import view,ids,public,utility,RECIPE
@pytest.fixture
def rows():
 a=view('absolute-winner',0.0,100);b=view('absolute-loser',0.5,1000);c=view('absolute-other',0.0,0)
 names=option_feature_names(15);x=list(c.row.features);x[names.index('party_risk')]=1.0
 return a,b,replace(c,row=replace(c.row,features=tuple(x)))
def fit(rows,**change):return h.fit_challenge_consequence(rows,retention_pairs=(ids(rows),),**dict(RECIPE,**change))
def assert_bits_equal(a,b):
 assert a.document()==b.document()and a.model_sha256==b.model_sha256
 for field in('coefficients','intercept','feature_mean','feature_scale'):assert np.array_equal(np.asarray(getattr(a,field)).view(np.uint64),np.asarray(getattr(b,field)).view(np.uint64))
def forbidden_solver(monkeypatch):
 calls=[]
 def forbidden(*a,**k):calls.append(1);raise AssertionError('helper entered for invalid public flag contract')
 monkeypatch.setattr(h,'_fit_order_retained',forbidden);return calls
def test_false_default_keeps_legacy_unpaired_head_bits():
 names=option_feature_names(7);x=[0.0]*len(names);x[names.index('kind.unlock_access')]=1.0
 a=h.ConsequenceExample('1'*64,'a'*64,tuple(x),h.ChallengeConsequence(True,False,100,6000,0,0,0),None)
 x[names.index('execution_effort')]=1.0;b=replace(a,declaration_sha256='2'*64,features=tuple(x),outcome=h.ChallengeConsequence(True,True,200,12000,0,0,0))
 assert_bits_equal(h.fit_challenge_consequence((a,b)),h.fit_challenge_consequence((a,b),utility_absolute_loss=False))
def test_false_default_keeps_pair_fit_bits_and_public_codec(rows):
 assert_bits_equal(fit(rows),fit(rows,utility_absolute_loss=False))
def test_false_does_not_forward_a_new_keyword_into_existing_helper(rows,monkeypatch):
 calls=[]
 def legacy_signature(z,y,pair_indices,utility,*,ridge):calls.append(1);return np.zeros((z.shape[1],9)),np.mean(y,axis=0)
 monkeypatch.setattr(h,'_fit_order_retained',legacy_signature)
 assert_bits_equal(fit(rows),fit(rows,utility_absolute_loss=False));assert len(calls)==2
@pytest.mark.parametrize('bad',[None,0,1,np.bool_(True),'true',[]])
def test_flag_requires_exact_python_bool(rows,monkeypatch,bad):
 calls=forbidden_solver(monkeypatch)
 with pytest.raises(ValueError):fit(rows,utility_absolute_loss=bad)
 assert not calls
@pytest.mark.parametrize('pairs',[(),None,[]])
def test_true_requires_explicit_nonempty_retention_pairs(rows,monkeypatch,pairs):
 calls=forbidden_solver(monkeypatch)
 with pytest.raises(ValueError):h.fit_challenge_consequence(rows,retention_pairs=pairs,utility_absolute_loss=True,**RECIPE)
 assert not calls
@pytest.mark.parametrize('change',[dict(feedback_version=1),dict(feature_version=10),dict(context_projection='identity'),dict(ridge=2.0),dict(cash_prediction='certified_single_trainer_v1'),dict(reference_head=object()),dict(retained_rows=(object(),)),dict(include_recovery_purchases=True),dict(reference_residual_mode='affine_nullspace')])
def test_true_mode_remains_full_v15_party_progress_ridge1_independent(rows,monkeypatch,change):
 calls=forbidden_solver(monkeypatch)
 with pytest.raises(ValueError):fit(rows,utility_absolute_loss=True,**change)
 assert not calls
def test_true_rejects_unpaired_legacy_row_without_all_nine_targets(rows):
 legacy=view('absolute-legacy',0.0,0,feedback=1)
 with pytest.raises(ValueError):fit((rows[0],rows[1],legacy),utility_absolute_loss=True)
@pytest.mark.parametrize('reverse_pair',[False,True])
def test_true_aligns_rowwise_public_utility_and_retains_orders_bounds_codec(rows,reverse_pair):
 before=copy.deepcopy([v.document()for v in rows]);pair=ids(rows);pair=pair[::-1]if reverse_pair else pair
 default=h.fit_challenge_consequence(rows,retention_pairs=(pair,),**RECIPE)
 absolute=h.fit_challenge_consequence(rows,retention_pairs=(pair,),utility_absolute_loss=True,**RECIPE)
 document=json.loads(json.dumps(absolute.document()));restored=h.ChallengeConsequenceHead.from_document(document,expected_sha256=absolute.model_sha256)
 values=public(restored,rows);baseline=public(default,rows);actual=np.asarray([v.row.outcome.vector()for v in rows]);weights=np.asarray(h.consequence_contract(2)[3])
 assert np.array_equal(values,public(absolute,rows));assert np.isfinite(values).all()and np.all(values>=0)
 assert np.all(values[:,:2]<=1)and np.all(values[:,1]<=values[:,0])and np.all(values[:,7:]<=1)
 gap=float((actual[0]-actual[1])@weights);assert float((values[0]-values[1])@weights)>=min(0.01,0.1*gap)-1e-7
 old_mae=float(np.mean(np.abs((baseline-actual)@weights)));new_mae=float(np.mean(np.abs((values-actual)@weights)))
 assert new_mae<=old_mae+1e-9
 assert new_mae<old_mae-1e-10
 assert [v.document()for v in rows]==before and absolute.provenance=='synthetic'and absolute.feature_version==15 and absolute.feedback_version==2
