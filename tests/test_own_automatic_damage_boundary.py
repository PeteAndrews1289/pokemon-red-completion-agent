"""Own automatic damage stops at the first stable MAIN; no ROM/emulator."""
from dataclasses import replace
import pytest
from test_battle_runtime import MeasuredTurnRuntime,_raw
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import BattleMenuPhase,BattleMenuState,MapId
from pokemon_red_completion.battle_runtime import execute_bounded_battle_move_turn,BattleRuntimeError

def setup(fault=None,battle_state=1):
    runtime=MeasuredTurnRuntime(raw=replace(_raw(battle_state=battle_state,enemy_hp=24,moves=(35,43,40,0),pp=(19,30,35,0)),active_party_index=0,enemy_using_trapping_move=False))
    count={'confirm':0,'wait':0}
    def transition(action):
        if action.kind is MacroActionKind.CONFIRM:
            count['confirm']+=1
            if count['confirm']>1:
                runtime.menu=BattleMenuState(BattleMenuPhase.MOVE,selected_move_slot=1);return
            changes={'enemy_hp':24 if fault=='no_progress' else 20}
            if fault=='selected_pp':changes['first_party_pp']=(18,30,35,0)
            if fault=='other_pp':changes['first_party_pp']=(19,29,35,0)
            if fault=='active':changes['active_party_index']=1
            if fault=='roster':changes['party_species_ids']=(1,)
            if fault=='moves':changes['first_party_moves']=(43,35,40,0)
            if fault=='opponent':changes['enemy_species_id']=1
            if fault=='faint':changes['first_party_hp']=0
            if fault=='enemy_faint':changes['enemy_hp']=0
            runtime.raw=replace(runtime.raw,**changes);runtime.menu=BattleMenuState(BattleMenuPhase.UNKNOWN)
        elif action.kind is MacroActionKind.WAIT and count['confirm']:
            count['wait']+=1
            runtime.menu=(BattleMenuState(BattleMenuPhase.MOVE,selected_move_slot=1)
                if fault=='move_at_settlement' and count['wait']>=2
                else BattleMenuState(BattleMenuPhase.MAIN,selected_main_command=1 if fault=='wrong_main' else 0))
    runtime.on_action=transition
    return runtime,count

def execute(runtime):
    return execute_bounded_battle_move_turn(runtime,runtime,selected_slot=1,expected_map=MapId.CERULEAN_CITY,expected_battle_state=runtime.raw.battle_state,settle_to_next_decision=True)

@pytest.mark.parametrize('state',[1,2])
def test_own_automatic_damage_uses_one_confirm_and_preserves_full_pp(state):
    runtime,count=setup(battle_state=state);initial=runtime.raw;result=execute(runtime)
    assert not result.move_executed and result.final_state.enemy_hp==20
    assert result.final_state.battler_pp==initial.battler_pp and count['confirm']==1
    assert runtime.menu.phase is BattleMenuPhase.MAIN

@pytest.mark.parametrize('fault',['selected_pp','other_pp','active','roster','moves','opponent'])
def test_own_automatic_damage_rejects_pp_or_identity_changes_before_second_confirm(fault):
    runtime,count=setup(fault)
    with pytest.raises(BattleRuntimeError):execute(runtime)
    assert count['confirm']==1

@pytest.mark.parametrize('fault',['no_progress','wrong_main','move_at_settlement'])
def test_own_automatic_damage_does_not_accept_unproved_or_wrong_menu(fault):
    runtime,count=setup(fault)
    with pytest.raises(BattleRuntimeError):execute(runtime)
    if fault in ['wrong_main','move_at_settlement']:assert count['confirm']==1

def test_expected_player_faint_preserves_existing_unspent_handoff():
    runtime,count=setup('faint');result=execute(runtime)
    assert not result.move_executed and result.final_state.battler_hp==0 and count['confirm']==1

def test_enemy_faint_does_not_use_live_enemy_automatic_damage_shortcut():
    runtime,count=setup('enemy_faint');initial=runtime.raw;result=execute(runtime)
    assert not result.move_executed and result.final_state.enemy_hp==0
    assert result.final_state.battler_pp==initial.battler_pp and count['confirm']>1
