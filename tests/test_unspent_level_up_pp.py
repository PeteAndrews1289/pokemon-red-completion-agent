"""Automatic empty-slot PP during an unsubmitted trapping finish is not a spend."""
from dataclasses import replace

import pytest
from test_battle_runtime import MeasuredTurnRuntime, _raw

from pokemon_red_completion import battle_runtime as runtime
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.observation import BattleMenuPhase,BattleMenuState,MapId


def states():
    before=replace(_raw(battle_state=1,moves=(35,43,0,0),pp=(15,30,0,0),enemy_hp=2),
                   active_party_index=0,active_party_species_id=108,active_party_level=9)
    after=replace(before,enemy_hp=0,active_party_level=10,
                  first_party_moves=(35,43,40,0),first_party_pp=(15,30,35,0))
    return before,after


class LearningFinish(MeasuredTurnRuntime):
    def __init__(self,after):
        self.initial,_=states()
        super().__init__(raw=after,menu=BattleMenuState(BattleMenuPhase.UNKNOWN))
    def execute(self,action):
        assert action.kind is not MacroActionKind.MOVE
        if action.kind is MacroActionKind.WAIT:self.raw=replace(self.raw,battle_state=0)
        return super().execute(action)


def settle(after):
    port=LearningFinish(after);token=runtime._ACTIVE_BATTLE_STATE.set(1)
    try:
        result=runtime._await_next_battle_decision(port,port,expected_map=MapId.CERULEAN_CITY,
            expected_battle_state=1,initial_raw=port.initial,slot=1,move_executed=False,
            allow_delayed_selected_spend=False,
            timing=runtime.BattleRuntimeTiming(max_post_attack_transition_pulses=6),label='unspent learning')
    finally:runtime._ACTIVE_BATTLE_STATE.reset(token)
    return port,result


def test_automatic_empty_slot_learning_settles_without_inventing_move_execution():
    _,after=states();port,result=settle(after)
    assert result is False and port.raw.battle_state==0
    assert port.raw.battler_pp==(15,30,35,0)


@pytest.mark.parametrize('changes',[
    {'enemy_hp':1},{'active_party_level':9},{'active_party_species_id':1},
    {'active_party_index':1},{'first_party_pp':(14,30,35,0)},
    {'first_party_pp':(15,29,35,0)},{'first_party_pp':(16,30,35,0)},
    {'first_party_pp':(15,30,34,0)},{'first_party_pp':(15,30,99,0)},
    {'first_party_moves':(40,43,35,0)},{'first_party_moves':(35,43,255,0)},
    {'first_party_moves':(35,44,40,0)},
])
def test_level_up_never_excuses_old_spending_healing_identity_or_invalid_allocation(changes):
    _,after=states()
    with pytest.raises(runtime.BattleRuntimeError,match='unspent turn|active party changed'):
        settle(replace(after,**changes))
