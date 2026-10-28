"""A cartridge trainer switch must not turn a suppressed sleeping turn into an error."""
from dataclasses import replace
import pytest
from test_battle_sleep_reapplication_handoff import RepeatedSleepAtMain
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleRuntimeError, BattleRuntimeTiming, _unspent_sleep_turn_progress,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.observation import BattleMenuPhase, MapId


class SleepingTrainerSwitch(RepeatedSleepAtMain):
    def __init__(self, *, nonlead=True):
        super().__init__(nonlead=nonlead, battle_state=2)
        key = 'active_party_status' if nonlead else 'first_party_status'
        self.raw = replace(self.raw, enemy_species_id=14, enemy_party_position=0,
                           enemy_hp=54, enemy_party_count=5, **{key:5})

    def execute(self, action):
        sleeping_turn = action.kind is MacroActionKind.CONFIRM and self.menu.phase is BattleMenuPhase.MAIN
        result = super().execute(action)
        if sleeping_turn:
            self.raw = replace(self.raw, enemy_species_id=130, enemy_party_position=1, enemy_hp=158)
        return result


@pytest.mark.parametrize('nonlead', [False, True])
def test_sleeping_turn_settles_opponent_switch_without_spending_another_move(nonlead):
    runtime = SleepingTrainerSwitch(nonlead=nonlead)
    result = execute_bounded_battle_move_turn(runtime, runtime,
        expected_map=MapId.CERULEAN_CITY, selected_slot=4, expected_battle_state=2,
        settle_to_next_decision=True,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1))
    assert not result.move_executed
    assert runtime.sleeping_turns == 1
    assert runtime.menu.phase is BattleMenuPhase.MAIN
    assert result.final_state.battler_status == 4
    assert result.final_state.battler_pp == result.initial_state.battler_pp
    assert result.final_state.active_party_index == result.initial_state.active_party_index
    assert result.final_state.enemy_party_position == 1


def test_opponent_switch_alone_does_not_prove_a_suppressed_turn():
    before = SleepingTrainerSwitch().raw
    after = replace(before, enemy_species_id=130, enemy_party_position=1, enemy_hp=158)
    assert not _unspent_sleep_turn_progress(before, after, label='pending trainer switch')


@pytest.mark.parametrize('fault', ['wild', 'unknown_position', 'invalid_position',
    'same_position_new_species', 'unknown_species', 'active_player', 'selected_pp', 'offslot_pp', 'sleep_increase'])
def test_sleep_switch_does_not_hide_invalid_identity_or_resource_proof(fault):
    before = SleepingTrainerSwitch().raw
    after = replace(before, enemy_species_id=130, enemy_party_position=1, enemy_hp=158, active_party_status=4)
    if fault == 'wild': before, after = replace(before,battle_state=1),replace(after,battle_state=1)
    if fault == 'unknown_position': after=replace(after,enemy_party_position=None)
    if fault == 'invalid_position': after=replace(after,enemy_party_position=6)
    if fault == 'same_position_new_species': after=replace(after,enemy_party_position=0)
    if fault == 'unknown_species': after=replace(after,enemy_species_id=None)
    if fault == 'active_player': after=replace(after,active_party_index=2)
    if fault == 'selected_pp': after=replace(after,active_party_pp=(35,30,30,12))
    if fault == 'offslot_pp': after=replace(after,active_party_pp=(35,29,30,13))
    if fault == 'sleep_increase': after=replace(after,active_party_status=6)
    with pytest.raises(BattleRuntimeError):
        _unspent_sleep_turn_progress(before,after,label='guarded trainer switch')


@pytest.mark.parametrize('before_slot,after_slot,same_species',[(0,1,False),(2,0,False),(0,1,True)])
@pytest.mark.parametrize('delayed',[False,True])
def test_trainer_switch_at_dialogue_or_neutral_settlement_keeps_one_actor_turn(before_slot,after_slot,same_species,delayed):
    from test_selected_sleep_turn_authority import SleepingTurn,execute
    runtime=SleepingTurn(before=3,after=2,nonlead=True,dialogue=True)
    runtime.raw=replace(runtime.raw,enemy_species_id=14,enemy_party_position=before_slot,enemy_party_count=5,enemy_hp=54)
    advance=runtime.on_action
    def transition(action):
        advance(action)
        if runtime.turn_finished and (not delayed or runtime.waits_after_turn>=2):
            runtime.raw=replace(runtime.raw,enemy_species_id=14 if same_species else 130,
                                enemy_party_position=after_slot,enemy_hp=158)
    runtime.on_action=transition
    result=execute(runtime)
    assert not result.move_executed and runtime.fights==1
    assert result.final_state.enemy_party_position==after_slot
    assert result.final_state.battler_pp==result.initial_state.battler_pp
    assert runtime.menu.phase is BattleMenuPhase.MAIN


@pytest.mark.parametrize('field,value',[('enemy_party_count',None),('enemy_party_count',True),
    ('enemy_party_count',4),('enemy_party_position',True),('enemy_party_position',-1),
    ('enemy_hp',0),('enemy_species_id',0),('active_party_moves',(1,2,3,4)),
    ('map_id',MapId.PALLET_TOWN)])
def test_sleep_roster_switch_requires_known_coherent_transition(field,value):
    before=SleepingTrainerSwitch().raw
    after=replace(before,enemy_species_id=130,enemy_party_position=1,enemy_hp=158,active_party_status=4)
    after=replace(after,**{field:value})
    with pytest.raises(BattleRuntimeError):
        _unspent_sleep_turn_progress(before,after,label='incoherent trainer switch')
