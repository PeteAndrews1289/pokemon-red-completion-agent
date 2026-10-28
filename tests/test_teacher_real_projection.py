"""Actual status legality projection after the staged teacher materializer."""
from dataclasses import fields,replace
from types import SimpleNamespace
import pytest
from pokemon_red_completion import red_battle_practice_factory as red
from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec
from pokemon_red_completion.observation import RawGameState,RamAddress,PARTY_STRUCT_STRIDE,BattleMenuState,BattleMenuPhase,InputReadiness
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref,pokemon_red_species_ref
from pokemon_red_completion.red_battle_scenario import prepare_red_battle_scenario
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from test_battle_practice_factory import FakeReader,_reader,_spec
from test_red_battle_scenario import _raw

class ActualProjectionReader(FakeReader):
 def read(self):
  supplied=vars(super().read());names={f.name for f in fields(RawGameState)}
  return replace(_raw(),**{k:v for k,v in supplied.items() if k in names})
 def read_input_readiness(self):return InputReadiness(0,0,0,0,0,0)
 def read_battle_menu_state(self,raw):return BattleMenuState(BattleMenuPhase.MAIN,selected_main_command=0)

def reader_and_cartridge():
 reader=ActualProjectionReader(dict(_reader().memory));memory=reader.memory;base=int(RamAddress.PARTY_MON_1)
 memory[base]=28;memory[int(RamAddress.PARTY_SPECIES)]=28
 active=base+PARTY_STRUCT_STRIDE;memory[active+red._PARTY_OT_ID_OFFSET]=0xAB;memory[active+red._PARTY_OT_ID_OFFSET+1]=0x6C
 species=SimpleNamespace(types=(0,0),catch_rate=190,nickname_bytes=b"RESERVE\x50\x50\x50\x50",neutral_stats=lambda _:red.PracticeStats(70,55,40,80,45),experience_at_level=lambda _:12345)
 reserve=dict(party_slot=1,species_ref=pokemon_red_species_ref(84),level=35,moves=[dict(move_ref=pokemon_red_move_ref(33),pp=35)],hp=50)
 return reader,SimpleNamespace(species=lambda _:species),reserve

def test_status_only_teacher_runs_real_encoder_and_real_legality_projection():
 assert red.prepare_red_battle_scenario is prepare_red_battle_scenario
 assert red.PokemonRedObservationEncoder is PokemonRedObservationEncoder
 reader,cartridge,reserve=reader_and_cartridge()
 spec=_spec(actor_moves=[dict(move_ref=pokemon_red_move_ref(106),pp=30)],allow_status_only_wild_training=True,party_reserves=[reserve])
 receipt=red.materialize_red_train_practice(reader,reader.memory,spec,cartridge=cartridge)
 raw=reader.read();encoder=PokemonRedObservationEncoder.from_state_reader(reader)
 prepared=prepare_red_battle_scenario(encoder,raw,allow_no_attack=True,allow_status_moves=True)
 assert receipt.actor_move_ids==(106,0,0,0) and receipt.actor_pp==(30,0,0,0)
 assert prepared.features.slot_indices==(0,) and prepared.supported_candidate_mask==(True,)
 assert prepared.features.candidate_vectors[0][prepared.features.feature_names.index('move.category.status')]==1
 assert prepared.initial_observation_sha256==receipt.observation_sha256
 legacy=prepare_red_battle_scenario(encoder,raw,allow_no_attack=True)
 assert legacy.supported_candidate_mask==(False,)

def test_legacy_teacher_runs_same_real_projection_without_broadening():
 assert red.prepare_red_battle_scenario is prepare_red_battle_scenario
 reader,cartridge,reserve=reader_and_cartridge();spec=_spec(party_reserves=[reserve])
 receipt=red.materialize_red_train_practice(reader,reader.memory,spec,cartridge=cartridge)
 prepared=prepare_red_battle_scenario(PokemonRedObservationEncoder.from_state_reader(reader),reader.read())
 assert receipt.actor_move_ids==(33,70,0,0) and prepared.supported_candidate_mask==(True,True)
 assert receipt.observation_sha256==prepared.initial_observation_sha256 and not receipt.allow_status_only_wild_training
