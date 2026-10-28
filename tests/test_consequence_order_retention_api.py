"""Synthetic ROM-free public API checks; no actual TRAIN data/native/model queries."""
from dataclasses import replace
import copy,json
import numpy as np
import pytest
import pokemon_red_completion.player_challenge_consequence as h
from pokemon_red_completion.living_dex_option_value import option_feature_names
from pokemon_red_completion.player_preparation_party_context import PreparationPartyWitness
from pokemon_red_completion.provenance import canonical_sha256
PROJECTION='prospective_preparation_party_context_v1'
RECIPE=dict(ridge=1.0,feedback_version=2,feature_version=15,context_projection=PROJECTION)
NAMES=option_feature_names(15)
def view(label,effort,actions,*,feedback=2,censored=False):
 x=[0.0]*len(NAMES);x[NAMES.index('kind.unlock_access')]=1.0;x[NAMES.index('execution_effort')]=effort
 out=None if censored else h.ChallengeConsequence(True,True,actions,actions*60,0,100+actions,0,feedback,None if feedback==1 else False,None if feedback==1 else 1.0)
 row=h.ConsequenceExample(canonical_sha256(dict(retention_api_unit_fixture=label)),'a'*64,tuple(x),out,'synthetic_censor'if censored else None,'synthetic',feedback,15)
 return h.ConsequencePartyView(row,PreparationPartyWitness('b'*64,(('fixture-1','combat'),('fixture-2','combat'))),'c'*64,'d'*64,'work_order_context_pin')
@pytest.fixture
def rows():return(view('winner',0.0,100),view('loser',0.5,1000),view('outlier',1.0,0))
def ids(rows):return rows[0].row.declaration_sha256,rows[1].row.declaration_sha256
def fit(rows,pairs,**change):return h.fit_challenge_consequence(rows,retention_pairs=pairs,**dict(RECIPE,**change))
def fail_solver(monkeypatch):
 calls=[]
 def forbidden(*a,**k):calls.append(1);raise AssertionError('numeric solver entered for invalid pair contract')
 monkeypatch.setattr(h,'_fit_order_retained',forbidden);return calls
def utility(value):return float(np.asarray(value)@np.asarray(h.consequence_contract(2)[3]))
def public(head,rows):return np.asarray([head.predict(v.row.features,party_context=v.party_witness.counts)for v in rows])
def test_empty_tuple_default_preserves_legacy_head_document():
 names=option_feature_names(7);features=[0.0]*len(names);features[names.index('kind.unlock_access')]=1.0
 a=h.ConsequenceExample('1'*64,'a'*64,tuple(features),h.ChallengeConsequence(True,False,100,6000,0,0,0),None)
 x=list(features);x[names.index('execution_effort')]=1.0
 b=replace(a,declaration_sha256='2'*64,features=tuple(x),outcome=h.ChallengeConsequence(True,True,200,12000,0,0,0))
 before=h.fit_challenge_consequence((a,b));explicit=h.fit_challenge_consequence((a,b),retention_pairs=())
 assert explicit.document()==before.document()and explicit.model_sha256==before.model_sha256
 for field in('coefficients','intercept','feature_mean','feature_scale'):assert np.array_equal(np.asarray(getattr(before,field)).view(np.uint64),np.asarray(getattr(explicit,field)).view(np.uint64))
@pytest.mark.parametrize('bad',[[],None,'bad'])
def test_outer_pair_container_must_be_tuple(rows,monkeypatch,bad):
 calls=fail_solver(monkeypatch)
 with pytest.raises(ValueError):fit(rows,bad)
 assert not calls
@pytest.mark.parametrize('kind',['inner_list','short','long','short_digest','invalid_digest','self','missing','duplicate','reverse_duplicate'])
def test_pair_id_and_unordered_uniqueness_contract(rows,monkeypatch,kind):
 a,b=ids(rows);pairs={'inner_list':([a,b],),'short':((a,),),'long':((a,b,'f'*64),),'short_digest':((a,'f'*63),),'invalid_digest':((a,'z'*64),),'self':((a,a),),'missing':((a,'f'*64),),'duplicate':((a,b),(a,b)),'reverse_duplicate':((a,b),(b,a))}[kind]
 calls=fail_solver(monkeypatch)
 with pytest.raises(ValueError):fit(rows,pairs)
 assert not calls
@pytest.mark.parametrize('kind',['origin','context','party_source','party_member_same_counts','provenance','censored','legacy_feedback'])
def test_pairs_require_same_original_boundary_and_complete_feedback(rows,monkeypatch,kind):
 values=list(rows);b=values[1]
 if kind=='origin':b=replace(b,row=replace(b.row,source_origin_sha256='e'*64))
 elif kind=='context':b=replace(b,source_context_sha256='e'*64)
 elif kind=='party_source':b=replace(b,party_witness=replace(b.party_witness,source_state_sha256='e'*64))
 elif kind=='party_member_same_counts':b=replace(b,party_witness=PreparationPartyWitness('b'*64,(('different-1','combat'),('different-2','combat'))))
 elif kind=='provenance':b=replace(b,row=replace(b.row,provenance='native_train'))
 elif kind=='censored':b=replace(b,row=replace(b.row,outcome=None,censor_reason='synthetic_censor'))
 else:b=view('legacy',0.5,1000,feedback=1)
 values[1]=b;calls=fail_solver(monkeypatch)
 with pytest.raises(ValueError):fit(tuple(values),(ids(values),))
 assert not calls
@pytest.mark.parametrize('change',[dict(ridge=2.0),dict(feedback_version=1),dict(feature_version=10),dict(context_projection='identity'),dict(cash_prediction='certified_single_trainer_v1'),dict(include_recovery_purchases=True),dict(reference_head=object()),dict(reference_residual_mode='affine_nullspace'),dict(retained_rows=(object(),))])
def test_pair_mode_is_narrow_and_never_enters_solver(rows,monkeypatch,change):
 calls=fail_solver(monkeypatch)
 with pytest.raises(ValueError):fit(rows,(ids(rows),),**change)
 assert not calls
@pytest.mark.parametrize('epsilon',[0.0,2e-8])
def test_native_utility_tie_or_tiny_gap_rejected(rows,monkeypatch,epsilon):
 out=h.ChallengeConsequence(True,False,100,6000,0,0,0,2,False,0.5)
 a=replace(rows[0],row=replace(rows[0].row,outcome=out));b=replace(rows[1],row=replace(rows[1].row,outcome=replace(out,challenge_progress=0.5+epsilon)))
 values=(a,b,rows[2]);calls=fail_solver(monkeypatch)
 with pytest.raises(ValueError):fit(values,(ids(values),))
 assert not calls
@pytest.mark.parametrize('reversed_ids',[False,True])
def test_orientation_is_derived_from_actual_nine_targets_not_pair_position(rows,monkeypatch,reversed_ids):
 seen=[]
 def stub(z,y,pair_indices,utility,*,ridge):
  assert ridge==1.0 and len(pair_indices)==1
  i,j=pair_indices[0];assert float((y[i]-y[j])@utility)>1e-8;seen.append((i,j));return np.zeros((z.shape[1],9)),np.mean(y,axis=0)
 monkeypatch.setattr(h,'_fit_order_retained',stub)
 pair=ids(rows);pair=pair[::-1]if reversed_ids else pair
 head=fit(rows,(pair,));assert len(seen)==1 and head.provenance=='synthetic'
def test_distinct_work_orders_are_legal_pair_arms(rows,monkeypatch):
 values=list(rows);values[1]=replace(values[1],source_work_order_sha256='e'*64);seen=[]
 def stub(z,y,pair_indices,utility,*,ridge):seen.append(pair_indices);return np.zeros((z.shape[1],9)),np.mean(y,axis=0)
 monkeypatch.setattr(h,'_fit_order_retained',stub);fit(tuple(values),(ids(values),));assert len(seen)==1
@pytest.mark.parametrize('reversed_ids',[False,True])
def test_real_synthetic_fit_retains_public_clipped_order_and_codec(rows,reversed_ids):
 before=copy.deepcopy([v.document()for v in rows]);pair=ids(rows);pair=pair[::-1]if reversed_ids else pair
 baseline=h.fit_challenge_consequence(rows,**RECIPE);baseline_values=public(baseline,rows)
 # The outlier makes ordinary ridge reverse this real observed pair; opt-in must correct it.
 assert utility(baseline_values[0])-utility(baseline_values[1])<0
 head=fit(rows,(pair,));doc=json.loads(json.dumps(head.document()));restored=h.ChallengeConsequenceHead.from_document(doc,expected_sha256=head.model_sha256)
 values=public(restored,rows);assert np.array_equal(values,public(head,rows));assert np.isfinite(values).all()and np.all(values>=0)
 assert np.all(values[:,:2]<=1)and np.all(values[:,1]<=values[:,0])and np.all(values[:,7:]<=1)
 actual_gap=utility(rows[0].row.outcome.vector())-utility(rows[1].row.outcome.vector());required=min(0.01,0.1*actual_gap)
 assert utility(values[0])-utility(values[1])>=required-1e-7
 assert [v.document()for v in rows]==before and head.feature_version==15 and head.feedback_version==2 and head.provenance=='synthetic'
