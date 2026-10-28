from types import SimpleNamespace
import pytest
from pokemon_red_completion import red_battle_practice_factory as red
from pokemon_red_completion.battle_practice_factory import BattlePracticeSpec,BattlePracticeError,PracticeStats,AssistedDevelopmentPracticeSpec
from pokemon_red_completion.red_battle_catalog import pokemon_red_move_ref,pokemon_red_species_ref
from pokemon_red_completion.observation import RamAddress,PARTY_STRUCT_STRIDE
from test_battle_practice_factory import _spec,_reader

def status_spec(**changes):
    return _spec(actor_moves=[{"move_ref":pokemon_red_move_ref(106),"pp":30}],allow_status_only_wild_training=True,**changes)

def test_default_single_move_remains_rejected():
    with pytest.raises(BattlePracticeError):_spec(actor_moves=[{"move_ref":pokemon_red_move_ref(106),"pp":30}])

def test_exact_boolean_optin_and_legacy_hash():
    assert _spec().allow_status_only_wild_training is False
    assert _spec().configuration_sha256==_spec(allow_status_only_wild_training=False).configuration_sha256
    assert status_spec().actor_moves[0].move_ref==pokemon_red_move_ref(106)
    for invalid in [1,None,"true"]:
        with pytest.raises(BattlePracticeError,match="boolean"):_spec(allow_status_only_wild_training=invalid)

def test_optin_trainer_and_development_rejected():
    with pytest.raises(BattlePracticeError,match="TRAIN wild"):status_spec(battle_kind="trainer",opponent_party_count=1)
    with pytest.raises(BattlePracticeError):status_spec(partition="development")

def test_supported_status_required_before_writes():
    reader=_reader();before=dict(reader.memory)
    unsupported=_spec(actor_moves=[{"move_ref":pokemon_red_move_ref(150),"pp":40}],allow_status_only_wild_training=True)
    with pytest.raises(BattlePracticeError,match="supported status"):red.materialize_red_train_practice(reader,reader.memory,unsupported)
    assert reader.memory==before

def test_attack_and_missing_reserve_rejected_before_writes():
    reader=_reader();before=dict(reader.memory)
    damaging=_spec(actor_moves=[{"move_ref":pokemon_red_move_ref(33),"pp":20}],allow_status_only_wild_training=True)
    with pytest.raises(BattlePracticeError,match="damaging move"):red.materialize_red_train_practice(reader,reader.memory,damaging)
    with pytest.raises(BattlePracticeError,match="declared living attacking reserve"):red.materialize_red_train_practice(reader,reader.memory,status_spec())
    assert reader.memory==before

def reserve_case(monkeypatch,reserve_move=33,pp=35):
    reader=_reader();memory=reader.memory;base=int(RamAddress.PARTY_MON_1)
    memory[base]=28;memory[int(RamAddress.PARTY_SPECIES)]=28
    active=base+PARTY_STRUCT_STRIDE
    memory[active+red._PARTY_OT_ID_OFFSET]=0xAB;memory[active+red._PARTY_OT_ID_OFFSET+1]=0x6C
    species=SimpleNamespace(types=(0,0),catch_rate=190,nickname_bytes=b"RESERVE\x50\x50\x50\x50",neutral_stats=lambda _:PracticeStats(70,55,40,80,45),experience_at_level=lambda _:12345)
    reserve={"party_slot":1,"species_ref":pokemon_red_species_ref(84),"level":35,"moves":[{"move_ref":pokemon_red_move_ref(reserve_move),"pp":pp}],"hp":50}
    calls=[]
    monkeypatch.setattr(red.PokemonRedObservationEncoder,"from_state_reader",lambda _:object())
    def prepared(_encoder,raw,**kwargs):
        calls.append(kwargs)
        assert kwargs=={"allow_no_attack":True,"allow_status_moves":True}
        assert raw.battler_moves==(106,0,0,0) and raw.battler_pp==(30,0,0,0)
        return SimpleNamespace(supported_candidate_mask=(True,),initial_observation_sha256="b"*64)
    monkeypatch.setattr(red,"prepare_red_battle_scenario",prepared)
    return reader,species,reserve,calls

def test_status_only_full_materializer_mirrors_and_capture_envelope(monkeypatch):
    from pokemon_red_completion.battle_scenario_capture import build_battle_scenario_capture_payload,parse_battle_scenario_capture_manifest
    from pokemon_red_completion.scenario_lab import ScenarioPartition
    reader,species,reserve,calls=reserve_case(monkeypatch)
    receipt=red.materialize_red_train_practice(reader,reader.memory,status_spec(party_reserves=[reserve]),cartridge=SimpleNamespace(species=lambda _:species))
    assert receipt.actor_move_ids==(106,0,0,0) and receipt.legal_move_count==1 and receipt.allow_status_only_wild_training
    assert receipt.public_dict()["allow_status_only_wild_training"] is True and receipt.public_dict()["final_player_action"] is False
    manifest=parse_battle_scenario_capture_manifest(build_battle_scenario_capture_payload(capture_id="status-optin-fakeport",root_lineage_id=receipt.root_lineage_id,partition=ScenarioPartition.TRAIN,state_bytes=b"fakeport-state-only",initial_observation_sha256=receipt.observation_sha256,source_commit="a"*40,expected_map=165,expected_battle_state=1,source_state_sha256=receipt.source_state_sha256))
    assert manifest.partition is ScenarioPartition.TRAIN and manifest.expected_battle_state==1
    assert calls==[{"allow_no_attack":True,"allow_status_moves":True}]

@pytest.mark.parametrize('move,pp',[(106,30),(33,0)])
def test_nonattacking_reserve_rejected_before_writes(monkeypatch,move,pp):
    reader,species,reserve,_=reserve_case(monkeypatch,move,pp);before=dict(reader.memory)
    with pytest.raises(BattlePracticeError,match="declared living attacking reserve"):red.materialize_red_train_practice(reader,reader.memory,status_spec(party_reserves=[reserve]),cartridge=SimpleNamespace(species=lambda _:species))
    assert reader.memory==before
