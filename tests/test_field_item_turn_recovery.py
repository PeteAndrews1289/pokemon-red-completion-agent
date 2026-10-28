from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from test_red_routed_recovery import make_test_raw
from pokemon_red_completion import red_player_field_item as module
from pokemon_red_completion.red_pc_storage import RedPCStorageError


def fixture(monkeypatch,*,fault=None,always=False):
    state={'raw':replace(make_test_raw(map_id=226,x=13,y=5,hp=(0,30)),
                         event_flags=bytes(320),badge_bits=255,
                         party_stats=((10,10,10,10,10),(10,10,10,10,10))),
           'faces':0,'escapes':0,'events':[]}
    runtime=NS(reader=NS(read=lambda:state['raw']),emulator=NS(pressed_buttons=()))
    def face(actions,reader,direction):
        state['faces']+=1
        if state['faces']>1 and not always:return
        state['raw']=replace(state['raw'],battle_state=1)
        if fault=='trainer':state['raw']=replace(state['raw'],battle_state=2)
        if fault=='location':state['raw']=replace(state['raw'],player_x=14)
        if fault=='money':state['raw']=replace(state['raw'],player_money=210)
        if fault=='items':state['raw']=replace(state['raw'],bag_items=((4,1),))
        if fault=='pp':state['raw']=replace(state['raw'],party_pp=((1,1),(1,1)))
        if fault=='species':state['raw']=replace(state['raw'],party_species_ids=(99,25))
        if fault=='held':runtime.emulator.pressed_buttons=('right',)
        if fault=='other':raise RedPCStorageError('unrelated facing error')
        raise RedPCStorageError('PC facing did not preserve its bound position')
    def settle(rt,actions):
        assert rt is runtime
        state['escapes']+=1
        if fault=='failed_escape':raise RuntimeError('native escape refused')
        state['raw']=replace(state['raw'],battle_state=0)
        return None if fault=='missing_evidence'else{'verified_native_escape':True}
    monkeypatch.setattr(module,'face_pc_boundary',face)
    monkeypatch.setattr(module,'settle_story_interaction',settle)
    actions=NS(record_diagnostic_event=lambda kind,payload:state['events'].append((kind,payload)))
    return runtime,actions,state


def test_turn_triggered_wild_encounter_settles_then_rechecks_orientation(monkeypatch):
    runtime,actions,state=fixture(monkeypatch)
    module.face_field_item_boundary(runtime,actions,'right')
    assert state['faces']==2 and state['escapes']==1
    assert state['raw'].battle_state==0 and state['raw'].party_hp==(0,30)
    assert len(state['events'])==1
    assert state['events'][0][1]['item_interaction_executed'] is False
    assert state['events'][0][1]['model_queries']==0


@pytest.mark.parametrize('fault',['trainer','location','money','items','pp','species','held','other'])
def test_facing_error_does_not_authorize_unrelated_escape_or_pickup(monkeypatch,fault):
    runtime,actions,state=fixture(monkeypatch,fault=fault)
    with pytest.raises(RedPCStorageError):module.face_field_item_boundary(runtime,actions,'right')
    assert state['escapes']==0 and not state['events']


@pytest.mark.parametrize('fault',['failed_escape','missing_evidence'])
def test_unverified_escape_never_retries_or_interacts(monkeypatch,fault):
    runtime,actions,state=fixture(monkeypatch,fault=fault)
    with pytest.raises(RuntimeError):module.face_field_item_boundary(runtime,actions,'right')
    assert state['faces']==state['escapes']==1 and not state['events']


def test_repeated_wild_turns_have_finite_native_bound(monkeypatch):
    runtime,actions,state=fixture(monkeypatch,always=True)
    with pytest.raises(RedPCStorageError):module.face_field_item_boundary(runtime,actions,'right')
    assert state['faces']==3 and state['escapes']==2


@pytest.mark.parametrize('bound',[True,-1,3,None])
def test_invalid_facing_bound_rejects_before_any_input(monkeypatch,bound):
    runtime,actions,state=fixture(monkeypatch)
    with pytest.raises(ValueError):module.face_field_item_boundary(runtime,actions,'right',maximum_wild_exits=bound)
    assert state['faces']==state['escapes']==0
