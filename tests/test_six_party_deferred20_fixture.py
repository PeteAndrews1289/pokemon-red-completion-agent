"""Synthetic fixture guards only; zero ROM/native state or model work."""
from hashlib import sha256
from types import SimpleNamespace
import pytest
import pokemon_red_completion.red_player_story_training_setup as setup
from pokemon_red_completion.red_party import PokemonRedPartyReader, member_field_address, SPECIES_OFFSET, EXPERIENCE_OFFSET, DETERMINANT_VALUES_OFFSET, PP_OFFSET
from pokemon_red_completion.red_battle_practice_factory import _PARTY_BOX_LEVEL_OFFSET,_PARTY_STAT_EXP_OFFSET,PARTY_LEVEL_OFFSET,PARTY_HP_OFFSET,PARTY_MAX_HP_OFFSET,_stats
from pokemon_red_completion.observation import EventFlag,MapId,RamAddress
from test_six_party_train_fixture import six_party_inputs
PARENT=b'synthetic exact six-party Rattata19 TRAIN parent for deferred20 guard tests'
def fixture(monkeypatch):
 memory,args,species=six_party_inputs(monkeypatch)
 setup.prepare_misty_party_training_fixture(memory,**args)
 monkeypatch.setattr(setup,'_MISTY_DEFERRED20_PARENT_SHA256',sha256(PARENT).hexdigest())
 args.update(condition='healthy-six-party-rattata20-deferred',parent_state_bytes=PARENT)
 return memory,args,species
def reader(memory):return PokemonRedPartyReader(SimpleNamespace(read_u8=lambda a:int(memory[a])))
def test_deferred20_changes_only_declared_target_fields_with_canonical_stats(monkeypatch):
 memory,args,species=fixture(monkeypatch);before=bytes(memory);refs=reader(memory).preparation_specimen_refs();party=reader(memory).read()
 rows=setup.prepare_misty_party_training_fixture(memory,**args);after=reader(memory).read();base=member_field_address(1,SPECIES_OFFSET);stats=species(165).stats_with_dvs(20,(8,8,8,9))
 allowed={base+_PARTY_BOX_LEVEL_OFFSET,base+PARTY_LEVEL_OFFSET,*range(base+EXPERIENCE_OFFSET,base+EXPERIENCE_OFFSET+3),*range(base+PARTY_HP_OFFSET,base+PARTY_HP_OFFSET+2),*range(base+PARTY_MAX_HP_OFFSET,base+PARTY_MAX_HP_OFFSET+10)}
 assert len(rows)==len(allowed)==17 and {r['address']for r in rows}==allowed
 assert all(memory[i]==v for i,v in enumerate(before)if i not in allowed)
 assert all(before[r['address']]==r['before']and memory[r['address']]==r['after']for r in rows)
 assert reader(memory).preparation_specimen_refs()==refs and all(a==b for i,(a,b)in enumerate(zip(party.members,after.members))if i!=1)
 assert after.members[1].species_id==165 and after.members[1].level==20 and after.members[1].experience==species(165).experience_at_level(20)
 assert _stats(memory,base+PARTY_MAX_HP_OFFSET)==stats and after.members[1].hp==stats.max_hp and after.members[1].moves==party.members[1].moves
@pytest.mark.parametrize('fault',['partition','authority','released','battle','boolbattle','romtype','romsha','parentmissing','parenttype','parenthash','map','misty','reward','species','level','boxlevel','EV','DV','XP','stats','PP','other_injury'])
def test_deferred20_bad_source_or_authority_is_atomic(monkeypatch,fault):
 memory,args,_=fixture(monkeypatch);base=member_field_address(1,SPECIES_OFFSET)
 if fault=='partition':args['partition']='development'
 elif fault=='authority':args['isolated_training_setup']=False
 elif fault=='released':args['controller_released']=False
 elif fault=='battle':args['battle_state']=1
 elif fault=='boolbattle':args['battle_state']=False
 elif fault=='romtype':args['rom']=bytearray(args['rom'])
 elif fault=='romsha':args['rom_sha256']='0'*64
 elif fault=='parentmissing':args.pop('parent_state_bytes')
 elif fault=='parenttype':args['parent_state_bytes']=bytearray(PARENT)
 elif fault=='parenthash':args['parent_state_bytes']=PARENT+b'changed'
 elif fault=='map':memory[RamAddress.CURRENT_MAP]=MapId.CERULEAN_CITY
 elif fault in('misty','reward'):
  flag=int(EventFlag.BEAT_MISTY if fault=='misty'else EventFlag.GOT_TM11);memory[int(RamAddress.EVENT_FLAGS)+flag//8]|=1<<(flag%8)
 elif fault=='species':memory[base]=166
 elif fault=='level':memory[base+PARTY_LEVEL_OFFSET]=20
 elif fault=='boxlevel':memory[base+_PARTY_BOX_LEVEL_OFFSET]=20
 elif fault=='EV':memory[base+_PARTY_STAT_EXP_OFFSET]=1
 elif fault=='DV':memory[base+DETERMINANT_VALUES_OFFSET]=0x98
 elif fault=='XP':memory[base+EXPERIENCE_OFFSET+2]^=1
 elif fault=='stats':memory[base+PARTY_MAX_HP_OFFSET+3]^=1
 elif fault=='PP':memory[base+PP_OFFSET]-=1
 else:memory[int(RamAddress.PARTY_MON_1)+2]=0
 before=bytes(memory)
 with pytest.raises(ValueError):setup.prepare_misty_party_training_fixture(memory,**args)
 assert bytes(memory)==before
