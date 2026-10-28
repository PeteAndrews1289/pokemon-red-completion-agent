"""Ordinary fixed-catalog tests: hashes only, no private raw datasets."""
import pytest
from pokemon_red_completion import red_production_train_admission as a
LOWER_DEFICIT='2d2eb758146be68e49bdbe08fa63177eb4852899e52ae9650aee17c423a51ef8'
NEW='7da092393b618c187ef1f2ffadef50dd492be4944f96a6133aed1fe57c417755'
NEW_PROVENANCE=('260f72f640dbc24ad1d83be13c318fd399a23da45c8fa08c7cdbebc119bf9b4d','61eb52658ea246af77697af4867ebdbf9060bc6556fc993fb6bfbfb287a4c172')
OLD={
 '0e691fe7b9c2624cc496ff07170c925c51fab3726245cc1547c887a69724575d':('066f81b50ee76e61c50a21daf7a5a6a0ba2ea0d912c26943006f3b4894a71c64','86eae3aba87c463a3335b940cd5638dfb6518bea5fc6f4978cdfee91a77f6039'),
 'e0ec6ba4eeb3dab69c37b29093c3b182ec42278a1962122f46365c32cac9544e':('0d679bd7e32a5b6cfec2486ce2977924285a2fb376cb11ecae6d30914a7b83ae','0132306ba8cb849391408de4856f5ce228346dbf9f42bbdeb1c096f0e16daf57'),
 'cdaef04a24f6bb0670c33fa532749e8bd5894cc51d7030c316d48298d22287ec':('f6f7c876335191e66eea0f49d6edb0ee5cb073213cf20d56d7efaefe4953227f','cedda9c05430b3f484fc02dd1651137f1066941e2ec58808f8d744230e6a9a59')}
def create(state,envelope,progress,origin=a.SOURCE_ORIGIN):return a.ProductionTrainAdmission(state,origin,'a'*40,'b'*64,envelope,progress)
def mutate(value):return('0'if value[0]!='0'else'1')+value[1:]
def test_three_original_and_two_finite_supplied_fixtures():
 assert len(a.SOURCE_STATES)==len(a.SOURCE_PROVENANCE)==5
 assert all(a.SOURCE_PROVENANCE[k]==v for k,v in OLD.items())
 assert set(a.SOURCE_STATES)-set(OLD)=={NEW,LOWER_DEFICIT}
 assert a.SOURCE_PROVENANCE[NEW]==NEW_PROVENANCE
@pytest.mark.parametrize('state',sorted(OLD))
def test_three_prior_admissions_remain_valid(state):
 e,p=OLD[state];assert create(state,e,p).source_state_sha256==state
def test_new_exact_catalog_triple_is_accepted():
 new=NEW;e,p=a.SOURCE_PROVENANCE[new];assert create(new,e,p).source_state_sha256==new
@pytest.mark.parametrize('which',['state','envelope','progress','origin'])
def test_new_fixture_mismatches_cannot_borrow_admission(which):
 new=NEW;e,p=a.SOURCE_PROVENANCE[new];values=dict(state=new,envelope=e,progress=p,origin=a.SOURCE_ORIGIN);values[which]=mutate(values[which])
 with pytest.raises(ValueError,match='source or identity'):create(**values)
def test_new_and_original_provenance_cannot_cross_pair():
 new=NEW;ne,np=a.SOURCE_PROVENANCE[new];old=next(iter(OLD));oe,op=OLD[old]
 for state,e,p in((new,oe,np),(new,ne,op),(old,ne,np)):
  with pytest.raises(ValueError,match='source or identity'):create(state,e,p)
