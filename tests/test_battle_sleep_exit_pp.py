"""A sleeping nonlead's PP remains its own when wild battle fields disappear."""

from dataclasses import replace

import pytest
from test_battle_runtime import MeasuredTurnRuntime, _raw

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import (
    _ACTIVE_BATTLE_STATE,
    BattleRuntimeError,
    BattleRuntimeTiming,
    _recover_sleep_transition,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.observation import BattleMenuPhase, BattleMenuState, MapId


class NonleadSleepExit(MeasuredTurnRuntime):
    def __init__(self, *, changed_pp=None, missing_pp=False, hp=49, wrong_map=False):
        super().__init__(raw=replace(
            _raw(party_count=3, battle_state=1, hp=55, pp=(30, 20, 30, 21)),
            first_party_max_hp=61,
            active_party_index=2,
            active_party_hp=49,
            active_party_max_hp=58,
            active_party_status=3,
            active_party_pp=(33, 40, 18, 30),
            party_hp=(55, 96, 49),
            party_pp=((30, 20, 30, 21), (30, 40, 20, 30), (33, 40, 18, 30)),
        ))
        self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        self.confirmations = 0
        self.changed_pp = changed_pp
        self.missing_pp = missing_pp
        self.final_hp = hp
        self.wrong_map = wrong_map

    def execute(self, action):
        if action.kind is MacroActionKind.CONFIRM:
            self.confirmations += 1
            assert self.confirmations == 1, "executor supplied another sleeping turn"
            party_pp = list(self.raw.party_pp)
            if self.changed_pp is not None:
                party_pp[2] = self.changed_pp
            self.raw = replace(
                self.raw,
                battle_state=0,
                enemy_hp=0,
                active_party_index=None,
                active_party_hp=None,
                active_party_max_hp=None,
                active_party_status=None,
                active_party_pp=None,
                party_hp=(55, 96, self.final_hp),
                party_pp=None if self.missing_pp else tuple(party_pp),
                map_id=MapId.PALLET_TOWN if self.wrong_map else MapId.CERULEAN_CITY,
            )
        return super().execute(action)


def recover(runtime):
    token = _ACTIVE_BATTLE_STATE.set(1)
    try:
        return _recover_sleep_transition(
            runtime, runtime,
            expected_map=MapId.CERULEAN_CITY,
            slot=1,
            initial_pp=33,
            initial_pp_vector=(33, 40, 18, 30),
            timing=BattleRuntimeTiming(max_sleep_recovery_pulses=1),
            label="nonlead sleep",
            allow_player_faint=True,
        )
    finally:
        _ACTIVE_BATTLE_STATE.reset(token)


def test_nonlead_wild_sleep_exit_preserves_original_full_pp_vector():
    runtime = NonleadSleepExit()
    assert recover(runtime)
    assert runtime.raw.battle_state == 0
    assert runtime.raw.battler_pp == (30, 20, 30, 21)  # field leader, not selected actor
    assert runtime.raw.party_pp[2] == (33, 40, 18, 30)
    assert runtime.confirmations == 1


@pytest.mark.parametrize("pp", [(32, 40, 18, 30), (33, 39, 18, 30)])
def test_nonlead_wild_sleep_exit_rejects_actual_pp_spending(pp):
    with pytest.raises(BattleRuntimeError, match="changed PP"):
        recover(NonleadSleepExit(changed_pp=pp))


def test_nonlead_wild_sleep_exit_rejects_unknown_original_pp():
    with pytest.raises(BattleRuntimeError, match="cannot prove selected-move PP"):
        recover(NonleadSleepExit(missing_pp=True))


def test_nonlead_wild_sleep_exit_cannot_hide_original_battler_faint():
    with pytest.raises(BattleRuntimeError, match="fainted"):
        recover(NonleadSleepExit(hp=0))


def test_nonlead_wild_sleep_exit_keeps_map_guard():
    with pytest.raises(BattleRuntimeError, match="expected map"):
        recover(NonleadSleepExit(wrong_map=True))


class WholeTurnNonleadSleepExit(NonleadSleepExit):
    def __init__(self, **options):
        super().__init__(**options)
        self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
        self.entered_sleep_dialogue = False

    def execute(self, action):
        if action.kind is MacroActionKind.CONFIRM and not self.entered_sleep_dialogue:
            self.entered_sleep_dialogue = True
            self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            return MeasuredTurnRuntime.execute(self, action)
        return super().execute(action)


def test_whole_selected_turn_keeps_original_nonlead_pp_after_sleep_exit():
    runtime = WholeTurnNonleadSleepExit()
    result = execute_bounded_battle_move_turn(
        runtime, runtime, expected_map=MapId.CERULEAN_CITY,
        selected_slot=1, expected_battle_state=1, settle_to_next_decision=True,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )
    assert not result.move_executed
    assert result.initial_state.active_party_index == 2
    assert result.final_state.active_party_index is None
    assert result.final_state.battle_state == 0
    assert result.final_state.party_pp[2] == result.initial_state.battler_pp
    assert result.final_state.battler_pp != result.initial_state.battler_pp
    assert runtime.confirmations == 1
