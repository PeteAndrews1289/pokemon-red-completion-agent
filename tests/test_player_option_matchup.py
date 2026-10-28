from dataclasses import replace
from types import SimpleNamespace
import math
import pytest
from pokemon_red_completion.player_option_matchup import MATCHUP_NAMES,OptionMatchup,matchup_feature_names,matchup_vector
from pokemon_red_completion.red_player_matchup import ExactTrainerMatchupWitness,project_red_player_matchup
from pokemon_red_completion.party import PartyMemberObservation,MoveObservation,StatusCondition
from pokemon_red_completion.party_preparation import PreparationMember,PreparationPurpose
from pokemon_red_completion.gen1_trainer_parties import TrainerPartyQuote,TrainerPartyMember
from pokemon_red_completion.red_story_battle import StoryTrainerContract

SOURCE='a'*64
BINDING='private:current'

def fixture(count=2):
    raw=SimpleNamespace(party_count=count,battle_state=0,map_id=65,
        party_species_ids=(165,166)[:count],party_levels=(20,20)[:count],party_hp=(5,100)[:count],party_max_hp=(100,100)[:count],party_status=(0,0)[:count],party_moves=((33,39,98,158),)*count,party_pp=((35,30,30,15),)*count,party_stats=((30,25,40,20),(60,50,80,40))[:count])
    members=tuple(PreparationMember('private:specimen'+str(i),PartyMemberObservation(i+1,raw.party_species_ids[i],20,raw.party_hp[i],100,moves=tuple(MoveObservation(a,b) for a,b in zip(raw.party_moves[i],raw.party_pp[i]))),PreparationPurpose.COMBAT,'declared') for i in range(count))
    contract=StoryTrainerContract('defeat_misty','registered-leader',65,(235,35,1),191,200)
    quote=TrainerPartyQuote(235,1,(TrainerPartyMember(0x78,87,20),TrainerPartyMember(0x76,51,20)),10,200)
    witness=ExactTrainerMatchupWitness(SOURCE,BINDING,contract,quote)
    return raw,members,witness

def project(raw,members,witness):
    return project_red_player_matchup(raw=raw,members=members,witness=witness,source_sha256=SOURCE,binding_ref=BINDING)

def values(descriptor):return dict(zip(MATCHUP_NAMES,matchup_vector(descriptor)))

def test_none_and_strict_public_roundtrip():
    raw,members,w=fixture();d,_=project(raw,members,w)
    assert len(MATCHUP_NAMES)==28 and len(matchup_vector(None))==28 and not any(matchup_vector(None))
    assert matchup_feature_names()==tuple('matchup.'+n for n in MATCHUP_NAMES)
    assert OptionMatchup.from_public(d.public_dict())==d
    assert 'private:' not in str(d.public_dict()) and 'source' not in str(d.public_dict())
    bad=d.public_dict();bad['binding_ref']=BINDING
    with pytest.raises(ValueError):OptionMatchup.from_public(bad)

@pytest.mark.parametrize('bad',[True,float('nan'),float('inf'),'0',None,1.1])
def test_bad_values(bad):
    v=[0.]*27;v[0]=bad
    with pytest.raises(ValueError):OptionMatchup(tuple(v))

@pytest.mark.parametrize('name,value',[('own_stats_known',1),('own.attack.minimum',.1),('opponent_fraction',1/6),('declared_combat_fraction',.2),('living_combat_fraction',1/6),('own.usable_move_fraction.minimum',.1)])
def test_unknown_or_count_contradictions(name,value):
    v=[0.]*27;v[MATCHUP_NAMES.index(name)-1]=value
    with pytest.raises(ValueError):OptionMatchup(tuple(v))

def test_actual_stats_and_no_safety_filter():
    raw,members,w=fixture();d,p=project(raw,members,w);v=values(d)
    assert v['living_combat_fraction']==2/6 # first member only5%HP; no half-HP filter
    assert v['own.attack.minimum']==30/999
    assert v['own.attack.mean']==45/999
    assert len(p['per_opponent_profiles'][0])==2
    assert v['own.usable_move_fraction.minimum']==3/4
    assert v['own.usable_damaging_move_pp_fraction.mean']==1
    assert set(p['roles'][0])=={'specimen_ref','slot','purpose'}

def test_stats_change_is_observed_not_species_estimated():
    raw,members,w=fixture(1);a,_=project(raw,members,w)
    raw.party_species_ids=(166,);members=(replace(members[0],observation=replace(members[0].observation,species_id=166)),)
    b,_=project(raw,members,w)
    assert a==b # same actual stats and same types/moves; no inferred evolution improvement
    raw.party_stats=((60,50,80,40),);c,_=project(raw,members,w)
    assert values(c)['own.attack.mean']>values(b)['own.attack.mean']

def test_unknown_stats_only_masks_stats():
    raw,members,w=fixture();raw.party_stats=None;d,_=project(raw,members,w);v=values(d)
    assert v['own_stats_known']==0 and all(v[n]==0 for n in MATCHUP_NAMES[8:18])
    assert v['opposition_roster_known']==1 and v['moves_and_pp_known']==1

def test_unknown_opposition_does_not_erase_own_measures():
    raw,members,w=fixture();d,_=project(raw,members,None);v=values(d)
    assert v['opposition_roster_known']==0 and v['opponent_fraction']==0
    assert all(v[n]==0 for n in MATCHUP_NAMES[18:24])
    assert v['own.attack.mean']>0 and v['own.usable_move_fraction.mean']>0

def test_unknown_moves_keeps_type_defense_but_not_offense():
    raw,members,w=fixture();raw.party_moves=raw.party_pp=None;d,_=project(raw,members,w);v=values(d)
    assert not v['moves_and_pp_known']
    assert all(v[n]==0 for n in (*MATCHUP_NAMES[18:22],*MATCHUP_NAMES[24:]))
    assert v['opposition_roster_known']==1

def test_empty_living_and_noncombat_known_zero():
    raw,members,w=fixture();raw.party_hp=(0,0);members=tuple(replace(m,observation=replace(m.observation,hp=0)) for m in members)
    d,_=project(raw,members,w);v=values(d)
    assert v['declared_combat_fraction']==2/6 and v['living_combat_fraction']==0
    assert all(v[n]==0 for n in MATCHUP_NAMES[8:])
    members=tuple(replace(m,purpose=PreparationPurpose.COLLECTION,purpose_reason='collection') for m in members)
    d,_=project(raw,members,w);assert values(d)['declared_combat_fraction']==0

def test_permutation_invariance_of_party_and_opponent():
    raw,members,w=fixture();a,_=project(raw,members,w)
    for name in ('party_species_ids','party_levels','party_hp','party_max_hp','party_status','party_moves','party_pp','party_stats'):
        setattr(raw,name,tuple(reversed(getattr(raw,name))))
    members=tuple(replace(m,observation=replace(m.observation,slot=i+1)) for i,m in enumerate(reversed(members)))
    w=replace(w,quote=replace(w.quote,party=tuple(reversed(w.quote.party))))
    b,_=project(raw,members,w);assert a==b

def test_opponent_type_changes_mechanics_with_same_level():
    raw,members,w=fixture();a,_=project(raw,members,w)
    w=replace(w,quote=replace(w.quote,party=(TrainerPartyMember(0x93,93,20),)*2))
    b,_=project(raw,members,w)
    assert a!=b and values(a)['own.attack.mean']==values(b)['own.attack.mean']

@pytest.mark.parametrize('change',['source','binding','map','quote','partialstats','partialpp','roles','moves','battle'])
def test_exact_alignment_guards(change):
    raw,members,w=fixture()
    if change=='source':w=replace(w,source_sha256='b'*64)
    elif change=='binding':w=replace(w,binding_ref='other')
    elif change=='map':raw.map_id=66
    elif change=='quote':
        with pytest.raises(ValueError):replace(w,quote=replace(w.quote,trainer_set=2))
        return
    elif change=='partialstats':raw.party_stats=((30,25,40,20),)
    elif change=='partialpp':raw.party_pp=None
    elif change=='roles':members=(members[0],members[0])
    elif change=='moves':raw.party_pp=((34,30,30,15),raw.party_pp[1])
    elif change=='battle':raw.battle_state=2
    with pytest.raises((ValueError,TypeError)):project(raw,members,w)

@pytest.mark.parametrize('field,value',[('battle_state',False),('map_id',True),('party_status',(False,0)),('party_stats',((True,25,40,20),(60,50,80,40)))])
def test_raw_boolean_is_not_integer_measurement(field,value):
    raw,members,w=fixture();setattr(raw,field,value)
    with pytest.raises(ValueError):project(raw,members,w)

def test_private_receipt_is_complete_but_public_is_identity_free():
    import json
    raw,members,w=fixture();d,p=project(raw,members,w)
    assert p['observed_party'][0]['species_id']==165
    assert p['raw_party_moves']==raw.party_moves and p['packed_party_pp']==raw.party_pp
    assert 'private:specimen' in json.dumps(p)
    assert 'private:specimen' not in json.dumps(d.public_dict())

def test_pp_up_capacity_uses_actual_decoded_maximum_not_catalog_base():
    raw,members,w=fixture(1)
    # Tackle has base35PP; one PP Up gives actual42. Packed99 carries35 current.
    raw.party_pp=((64+35,30,30,15),)
    d,receipt=project(raw,members,w)
    v=values(d)
    expected=(35/42+30/30+15/15)/3
    assert v['moves_and_pp_known']==1
    assert v['own.usable_damaging_move_pp_fraction.minimum']==pytest.approx(expected)
    assert v['own.usable_damaging_move_pp_fraction.mean']==pytest.approx(expected)
    assert v['own.usable_damaging_move_pp_fraction.mean']<1
    assert receipt['packed_party_pp']==raw.party_pp
    # Existing mechanic power/type/resistance profiles are unchanged by capacity.
    ordinary_raw,ordinary_members,ordinary_w=fixture(1)
    full,_=project(ordinary_raw,ordinary_members,ordinary_w)
    assert d.values[17:23]==full.values[17:23]
