from dataclasses import replace

from test_battle_runtime import MeasuredTurnRuntime, _raw

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import BattleRuntimeTiming, _await_next_battle_decision
from pokemon_red_completion.observation import BattleMenuPhase, BattleMenuState, MapId


def test_post_turn_text_cannot_open_fight_or_spend_another_pp():
    initial = _raw()
    after = replace(initial, first_party_pp=(34, 30, 30, 11), enemy_hp=11)
    runtime = MeasuredTurnRuntime(raw=after)
    runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
    inputs = []

    def advance(action):
        inputs.append(action.kind)
        if action.kind is MacroActionKind.CANCEL:
            runtime.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
        if action.kind is MacroActionKind.CONFIRM:
            raise AssertionError('unowned FIGHT confirmation')

    runtime.on_action = advance
    _await_next_battle_decision(runtime, runtime, expected_map=MapId.CERULEAN_CITY,
        expected_battle_state=initial.battle_state, initial_raw=initial, slot=1,
        move_executed=True, timing=BattleRuntimeTiming(), label='owned turn')
    assert inputs[0] is MacroActionKind.CANCEL
    assert runtime.raw == after
