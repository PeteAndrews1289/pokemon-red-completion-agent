"""ROM-free composition of voluntary faint fallback and unchanged forced guard."""
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
import pokemon_red_completion.surge as surge
from pokemon_red_completion.observation import RawGameState,BattleMenuPhase,BattleMenuState
from pokemon_red_completion.actions import MacroActionKind

def scenario(monkeypatch,*,live_hp=23,fault=None,force_fault=None):
    initial=RawGameState(True,36,4,5,6,1,party_species_ids=(179,165,150,113,5,108),
        party_hp=(6,40,53,23,37,15),enemy_species_id=185,enemy_level=12,enemy_hp=20,
        enemy_max_hp=34,active_party_index=1,active_party_hp=40)
    fainted=replace(initial,party_hp=(0,40,53,23,37,15),active_party_index=0,active_party_hp=0,enemy_hp=live_hp)
    if fault=='species':fainted=replace(fainted,enemy_species_id=112)
    elif fault=='roster':fainted=replace(fainted,party_species_ids=(179,165,150,113,5,109))
    elif fault=='battle':fainted=replace(fainted,battle_state=0)
    elif fault=='all_fainted':fainted=replace(fainted,party_hp=(0,0,0,0,0,0))
    restored=replace(fainted,active_party_index=1,active_party_hp=28,party_hp=(0,28,53,23,37,15))
    if force_fault=='hp':restored=replace(restored,enemy_hp=live_hp+1)
    elif force_fault=='species':restored=replace(restored,enemy_species_id=112)
    elif force_fault=='slot':restored=replace(restored,active_party_index=2)
    elif force_fault=='faint':restored=replace(restored,active_party_hp=0)
    elif force_fault=='battle':restored=replace(restored,battle_state=0)
    reader=NS(state=initial);reader.read=lambda:reader.state
    reader.read_battle_menu_state=lambda raw:BattleMenuState(BattleMenuPhase.MOVE if force_fault=='menu'and raw is restored else BattleMenuPhase.MAIN)
    commands=[];shared=[]
    def pulse(executor,kind,*args,**kwargs):
        commands.append(kind)
        assert kind is MacroActionKind.CONFIRM and len(commands)<=3
        if len(commands)==3:reader.state=fainted
    def shared_switch(executor,r,emulator,index,**kwargs):
        shared.append(dict(index=index,state=r.read(),kwargs=kwargs))
        assert index==1 and kwargs['expected_battle_state']==1
        reader.state=restored
    monkeypatch.setattr(surge,'_navigate_main',lambda *a:None)
    monkeypatch.setattr(surge,'_pulse',pulse)
    monkeypatch.setattr(surge,'switch_active_battler',shared_switch)
    emulator=NS(read_u8=lambda _:0)
    return initial,restored,reader,emulator,commands,shared

@pytest.mark.parametrize('live_hp',[9,16,23])
def test_protected_catcher_faint_uses_live_opponent_hp_after_voluntary_turn(monkeypatch,live_hp):
    initial,restored,reader,emulator,commands,shared=scenario(monkeypatch,live_hp=live_hp)
    observed=surge._switch_wild_capture_party_slot(emulator,object(),reader,0,185,20,'corridor protected catcher')
    assert observed is restored and len(shared)==1
    assert shared[0]['state'].enemy_hp==live_hp
    assert commands==[MacroActionKind.CONFIRM]*3

@pytest.mark.parametrize('live_hp',[None,0,-1,False])
def test_protected_catcher_faint_unknown_or_dead_target_stops_before_forced_input(monkeypatch,live_hp):
    initial,restored,reader,emulator,commands,shared=scenario(monkeypatch,live_hp=live_hp)
    with pytest.raises(surge.SurgeChapterError,match='changed its protected target'):
        surge._switch_wild_capture_party_slot(emulator,object(),reader,0,185,20,'corridor protected catcher')
    assert shared==[] and commands==[MacroActionKind.CONFIRM]*3

@pytest.mark.parametrize('fault',['species','roster','battle','all_fainted'])
def test_protected_catcher_faint_changed_target_or_roster_is_not_relaxed(monkeypatch,fault):
    initial,restored,reader,emulator,commands,shared=scenario(monkeypatch,fault=fault)
    with pytest.raises(surge.SurgeChapterError):
        surge._switch_wild_capture_party_slot(emulator,object(),reader,0,185,20,'corridor protected catcher')
    assert shared==[] and commands==[MacroActionKind.CONFIRM]*3

@pytest.mark.parametrize('force_fault',['hp','species','slot','faint','battle','menu'])
def test_protected_catcher_forced_replacement_keeps_exact_post_switch_guards(monkeypatch,force_fault):
    initial,restored,reader,emulator,commands,shared=scenario(monkeypatch,force_fault=force_fault)
    with pytest.raises(surge.SurgeChapterError,match='shared forced switch changed its protected target'):
        surge._switch_wild_capture_party_slot(emulator,object(),reader,0,185,20,'corridor protected catcher')
    assert len(shared)==1 and commands==[MacroActionKind.CONFIRM]*3
