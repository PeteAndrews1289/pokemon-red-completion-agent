"""Delayed submitted spend after Disable; strict whole-vector accounting, no game."""
from dataclasses import replace

import pytest
from test_battle_runtime import MeasuredTurnRuntime, _raw
from pokemon_red_completion.actions import MacroActionKind
import pokemon_red_completion.battle_runtime as runtime
from pokemon_red_completion.observation import BattleMenuPhase, BattleMenuState, MapId


class DelayedDisableSettlement(MeasuredTurnRuntime):
    def __init__(self, *, bad=None, second=False):
        initial = replace(_raw(battle_state=1, hp=23, enemy_hp=36,
            moves=(40, 81, 0, 0), pp=(32, 40, 0, 0)), active_party_index=0,
            player_disabled_move_slot=1, player_disable_turns=1)
        super().__init__(raw=initial, menu=BattleMenuState(BattleMenuPhase.UNKNOWN))
        self.initial = initial
        clear = replace(initial, player_disabled_move_slot=0, player_disable_turns=0)
        spent = replace(clear, first_party_pp=(31, 40, 0, 0), enemy_hp=34)
        if bad == "offslot": spent = replace(spent, first_party_pp=(32, 39, 0, 0))
        if bad == "two": spent = replace(spent, first_party_pp=(30, 40, 0, 0))
        if bad == "moves": spent = replace(spent, first_party_moves=(41, 81, 0, 0))
        self.steps = [clear, spent]
        if second: self.steps.append(replace(spent, first_party_pp=(30, 40, 0, 0)))
        self.waits = 0; self.second = second

    def execute(self, action):
        if action.kind is MacroActionKind.CONFIRM:
            pytest.fail("Settlement must not select/confirm another player attack")
        if action.kind is MacroActionKind.WAIT:
            self.raw = self.steps[min(self.waits, len(self.steps) - 1)]
            self.waits += 1
            self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0) if (
                self.waits >= (3 if self.second else 2)) else BattleMenuState(BattleMenuPhase.UNKNOWN)
        return super().execute(action)


def settle(port, *, submitted=True):
    token = runtime._ACTIVE_BATTLE_STATE.set(1)
    try:
        return runtime._await_next_battle_decision(port, port, expected_map=MapId.CERULEAN_CITY,
            expected_battle_state=1, initial_raw=port.initial, slot=1, move_executed=False,
            allow_delayed_selected_spend=submitted,
            timing=runtime.BattleRuntimeTiming(max_post_attack_transition_pulses=6), label="submitted Disable")
    finally: runtime._ACTIVE_BATTLE_STATE.reset(token)


def test_delayed_disable_spend_is_reported_true_with_no_second_confirm():
    port = DelayedDisableSettlement()
    assert settle(port) is True
    assert port.raw.battler_pp == (31, 40, 0, 0)
    assert all(a.kind is not MacroActionKind.CONFIRM for a in port.actions)


@pytest.mark.parametrize("bad", ["offslot", "two", "moves"])
def test_delayed_spend_cannot_hide_other_slot_second_spend_or_move_identity(bad):
    with pytest.raises(runtime.BattleRuntimeError): settle(DelayedDisableSettlement(bad=bad))


def test_second_selected_decrement_after_promotion_is_rejected():
    with pytest.raises(runtime.BattleRuntimeError, match="selected-turn PP accounting"):
        settle(DelayedDisableSettlement(second=True))


def test_unsubmitted_and_double_ko_style_settlement_stays_strict_zero_spend():
    with pytest.raises(runtime.BattleRuntimeError, match="unspent turn"):
        settle(DelayedDisableSettlement(), submitted=False)


def test_whole_turn_propagates_spend_only_after_existing_move_cursor_callback(monkeypatch):
    port = DelayedDisableSettlement()
    port.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
    port.raw = replace(port.raw, player_disabled_move_slot=0, player_disable_turns=0)
    def selected(reader, executor, **kwargs):
        kwargs["before_attack"]()  # Existing callback after requested cursor proof.
        port.raw = port.initial  # Faster opponent applies Disable after submission.
        port.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        return False
    monkeypatch.setattr(runtime, "_execute_policy_turn", selected)
    result = runtime.execute_bounded_battle_move_turn(port, port,
        expected_map=MapId.CERULEAN_CITY, expected_battle_state=1, selected_slot=1,
        settle_to_next_decision=True,
        timing=runtime.BattleRuntimeTiming(max_post_attack_transition_pulses=6))
    assert result.move_executed is True
    assert result.final_state.battler_pp == (31, 40, 0, 0)


def test_whole_early_unspent_transition_cannot_gain_submission_authority(monkeypatch):
    port = DelayedDisableSettlement();port.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
    port.raw = replace(port.raw, player_disabled_move_slot=0, player_disable_turns=0)
    def unsubmitted(*args, **kwargs):
        port.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
        return False
    monkeypatch.setattr(runtime, "_execute_policy_turn", unsubmitted)
    with pytest.raises(runtime.BattleRuntimeError, match="unspent turn"):
        runtime.execute_bounded_battle_move_turn(port, port,
            expected_map=MapId.CERULEAN_CITY, expected_battle_state=1, selected_slot=1,
            settle_to_next_decision=True,
            timing=runtime.BattleRuntimeTiming(max_post_attack_transition_pulses=6))



@pytest.mark.parametrize("index", [None, True, 6])
def test_delayed_spend_requires_known_original_party_identity(index):
    port = DelayedDisableSettlement()
    port.initial = replace(port.initial, active_party_index=index)
    port.raw = port.initial
    port.steps = [replace(row, active_party_index=index) for row in port.steps]
    with pytest.raises(runtime.BattleRuntimeError, match="unspent turn"):
        settle(port)


def test_delayed_spend_cannot_change_active_party_identity():
    port = DelayedDisableSettlement()
    port.steps[-1] = replace(port.steps[-1], active_party_index=1)
    with pytest.raises(runtime.BattleRuntimeError):
        settle(port)
