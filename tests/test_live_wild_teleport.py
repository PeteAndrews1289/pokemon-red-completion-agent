from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import (
    BattleMenuPhase, NativeWildTeleportWitness, PokemonRedStateReader, RamAddress,
)
from pokemon_red_completion.wild_party_flee import flee_with_fainted_lead
from test_wild_party_flee import state


def sample():
    return replace(state(), enemy_species_id=148, enemy_level=10, enemy_hp=26, battle_result=0,
                   active_party_index=1, active_party_hp=140)


def real_reader(live, values=None):
    values = [100, 28, 0, 1] if values is None else values
    addresses = [int(RamAddress.ENEMY_SPECIES_2)-12, int(RamAddress.ENEMY_SPECIES_2)-11,
                 int(RamAddress.ENEMY_SPECIES_2)-6, int(RamAddress.PLAYER_DISABLED_MOVE)+11]
    reader = PokemonRedStateReader.__new__(PokemonRedStateReader)
    reader._memory = NS(read_u8=lambda at: values[addresses.index(at)])
    reader.read = lambda: live[0]
    return reader, values


def test_live_reader_requires_coherent_flag_before_cleanup():
    raw = sample(); live = [raw]; reader, values = real_reader(live)
    witness = reader.read_live_wild_teleport_witness(raw)
    assert type(witness) is NativeWildTeleportWitness
    assert witness.enemy_hp == 26
    values[3] = 0
    assert reader.read_live_wild_teleport_witness(raw) is None
    values[3] = 1
    live[0] = replace(raw, battle_state=0)
    assert reader.read_live_wild_teleport_witness(raw) is None
    assert reader.read_live_wild_teleport_witness(live[0]) is None


@pytest.mark.parametrize('index,wrong', [(0,40),(1,2),(2,100),(3,0),(3,2)])
def test_live_reader_rejects_other_effect_or_player_action(index,wrong):
    raw=sample(); reader,values=real_reader([raw]); values[index]=wrong
    assert reader.read_live_wild_teleport_witness(raw) is None


@pytest.mark.parametrize('change', [dict(enemy_species_id=185),dict(enemy_hp=0),
                                   dict(enemy_level=None),dict(battle_state=2)])
def test_live_reader_rejects_unqualified_enemy(change):
    raw=replace(sample(),**change);reader,_=real_reader([raw])
    assert reader.read_live_wild_teleport_witness(raw) is None


def run_escape(qualify=True, terminal_change=None):
    raw=sample();live=[raw]; reader,values=real_reader(live,[100,28,0,0]);actions=[]
    def execute(action):
        actions.append(action.kind)
        if action.kind is MacroActionKind.CONFIRM:
            values[3]=1 if qualify else 0
        elif action.kind is MacroActionKind.CANCEL:
            values[3]=0
            live[0]=replace(raw,battle_state=0,battle_result=0,**(terminal_change or {}))
    reader.read_input_readiness=lambda:NS(ready=True)
    reader.read_battle_menu_state=lambda _:NS(
        phase=BattleMenuPhase.MAIN if MacroActionKind.CONFIRM not in actions else BattleMenuPhase.UNKNOWN,
        selected_main_command=3)
    result=flee_with_fainted_lead(NS(execute=execute),reader,raw,expected_map_id=17,
        route_name='measured native Teleport',stabilization_frames=120,error_type=RuntimeError)
    return result,actions


def test_actual_flee_latches_live_flag_and_verifies_after_reset():
    result,actions=run_escape()
    assert result.verified and result.battle_result==0 and result.run_attempts==1
    assert type(result.native_opponent_teleport_exit) is NativeWildTeleportWitness
    assert not replace(result,native_opponent_teleport_exit=None).verified
    assert not replace(result,pp_preserved=False).verified
    assert not replace(result,status_preserved=False).verified
    assert not replace(result,hp_scope='first_party_member').verified
    assert not replace(result,enemy_species_id=185).verified
    assert not replace(result,player_x=13).verified
    assert set(actions)<={MacroActionKind.CONFIRM,MacroActionKind.CANCEL,MacroActionKind.WAIT}
    assert result.public_dict()['native_opponent_teleport_exit']['live_escaped_flag']==1


def test_last_move_without_observed_flag_does_not_qualify():
    with pytest.raises(RuntimeError,match='party escape terminal did not verify'):
        run_escape(False)


@pytest.mark.parametrize('change',[dict(enemy_hp=25),dict(player_money=4582),
    dict(party_pp=((19,20,20,20),)*4),dict(player_x=13)])
def test_witness_does_not_waive_terminal_or_resource_conservation(change):
    with pytest.raises(RuntimeError):
        run_escape(terminal_change=change)
