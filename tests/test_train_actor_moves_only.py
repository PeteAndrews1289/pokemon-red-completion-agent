from dataclasses import replace, fields
from types import SimpleNamespace as S
import pytest
from test_battle_practice_factory import FakeReader
from pokemon_red_completion import red_battle_practice_factory as f
from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec, AssistedDevelopmentPracticeSpec, PracticeReserve, PracticeMove
from pokemon_red_completion.observation import RamAddress, PARTY_STRUCT_STRIDE, PARTY_MOVES_OFFSET, PARTY_PP_OFFSET, BattleMenuPhase
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref, pokemon_red_species_ref

class Memory(dict):
    def __init__(self):super().__init__();self.writes=[];self.corrupt=False
    def __getitem__(self,key):return self.get(key,0)
    def __setitem__(self,key,value):
        self.writes.append(key)
        if not self.corrupt:super().__setitem__(key,value)

class Reader(FakeReader):
    battle_state=2
    def read(self):
        raw=super().read();raw.battle_state=self.battle_state;raw.enemy_party_count=3
        raw.battler_moves=tuple(self.memory[f._BATTLE_MOVES+i]for i in range(4))
        raw.battler_pp=tuple(self.memory[f._BATTLE_PP+i]for i in range(4))
        return raw

def setup(monkeypatch):
    memory=Memory();base=int(RamAddress.PARTY_MON_1)+PARTY_STRUCT_STRIDE
    for address,values in [(f._BATTLE_MOVES,(44,39,61,55)),(f._BATTLE_PP,(25,30,20,25)),
       (base+PARTY_MOVES_OFFSET,(44,39,61,55)),(base+PARTY_PP_OFFSET,(25,30,20,25)),
       (int(RamAddress.ENEMY_MOVES),(64,28,15,31))]:
        for i,value in enumerate(values):memory[address+i]=value
    memory.writes.clear();reader=Reader(memory)
    monkeypatch.setattr(f.PokemonRedObservationEncoder,'from_state_reader',lambda _reader:object())
    monkeypatch.setattr(f,'prepare_red_battle_scenario',lambda *_:S(supported_candidate_mask=(True,True,True,False),initial_observation_sha256='b'*64))
    spec=BattlePracticeSpec.from_dict(dict(source_state_sha256='a'*64,root_lineage_id='red-train-move-test',partition='train',battle_kind='trainer',
        actor_moves=[dict(move_ref=pokemon_red_move_ref(move),pp=pp)for move,pp in [(44,25),(39,30),(61,20),(58,10)]],
        opponent_hp=80,opponent_species_ref=pokemon_red_species_ref(55),opponent_level=30,
        opponent_party_count=3,opponent_moves=[dict(move_ref=pokemon_red_move_ref(move),pp=pp)for move,pp in [(64,35),(28,15),(15,30),(31,20)]]))
    cartridge=S(species=lambda _species:S(tmhm_moves=(58,)))
    return reader,memory,spec,cartridge

def test_only_sixteen_active_move_and_pp_mirror_bytes_can_be_written(monkeypatch):
    reader,memory,spec,cartridge=setup(monkeypatch);before=dict(memory)
    receipt=f.materialize_red_train_actor_moves(reader,memory,spec,cartridge=cartridge)
    base=int(RamAddress.PARTY_MON_1)+PARTY_STRUCT_STRIDE
    allowed={address+i for address in [f._BATTLE_MOVES,f._BATTLE_PP,base+PARTY_MOVES_OFFSET,base+PARTY_PP_OFFSET]for i in range(4)}
    assert len(memory.writes)==16 and set(memory.writes)==allowed
    assert all(memory[key]==value for key,value in before.items()if key not in allowed)
    assert receipt.actor_move_ids==(44,39,61,58) and receipt.actor_pp==(25,30,20,10)
    assert receipt.public_dict()['final_player_action'] is False
    assert receipt.public_dict()['new_independent_upstream_roots']==0

@pytest.mark.parametrize('changes',[dict(actor_level=40),dict(actor_hp=50),dict(opponent_level=31),dict(opponent_hp=79),dict(opponent_species_ref=pokemon_red_species_ref(190)),dict(opponent_party_count=2)])
def test_requested_nonmove_changes_rejected_before_writes(monkeypatch,changes):
    reader,memory,spec,cartridge=setup(monkeypatch)
    with pytest.raises(f.BattlePracticeError):f.materialize_red_train_actor_moves(reader,memory,replace(spec,**changes),cartridge=cartridge)
    assert memory.writes==[]

def test_development_spec_cannot_enter_train_only_teacher(monkeypatch):
    reader,memory,spec,cartridge=setup(monkeypatch)
    from pokemon_red_completion.scenario_lab import ScenarioPartition
    values={field.name:getattr(spec,field.name)for field in fields(spec)}
    values['partition']=ScenarioPartition.DEVELOPMENT
    values['party_reserves']=tuple(PracticeReserve(slot,pokemon_red_species_ref(28),30,(PracticeMove(pokemon_red_move_ref(44),25),))for slot in (2,3,4))
    development=AssistedDevelopmentPracticeSpec(**values)
    with pytest.raises(f.BattlePracticeError,match='TRAIN'):f.materialize_red_train_actor_moves(reader,memory,development,cartridge=cartridge)
    assert memory.writes==[]

@pytest.mark.parametrize('bad_source',['not_main','battle','mirror','opponent','incompatible'])
def test_source_and_compatibility_fail_closed_before_writes(monkeypatch,bad_source):
    reader,memory,spec,cartridge=setup(monkeypatch)
    if bad_source=='not_main':reader.phase=BattleMenuPhase.UNKNOWN
    elif bad_source=='battle':reader.battle_state=0
    elif bad_source=='mirror':memory[f._BATTLE_MOVES]=33
    elif bad_source=='opponent':memory[int(RamAddress.ENEMY_MOVES)]=33
    else:cartridge=S(species=lambda _species:S(tmhm_moves=()))
    memory.writes.clear()
    with pytest.raises(f.BattlePracticeError):f.materialize_red_train_actor_moves(reader,memory,spec,cartridge=cartridge)
    assert memory.writes==[]

def test_mirror_write_failure_cannot_issue_a_success_receipt(monkeypatch):
    reader,memory,spec,cartridge=setup(monkeypatch);memory.corrupt=True
    with pytest.raises(f.BattlePracticeError,match='read back'):f.materialize_red_train_actor_moves(reader,memory,spec,cartridge=cartridge)
