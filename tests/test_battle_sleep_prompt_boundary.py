"""A trainer send-out prompt is an actor decision, even during sleep recovery."""

from dataclasses import replace

import pytest
from test_battle_runtime import MeasuredTurnRuntime, _raw

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import (
    _ACTIVE_BATTLE_STATE,
    BattleRuntimeError,
    BattleRuntimeTiming,
    _recover_sleep_transition,
    _unspent_trainer_prompt_boundary,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.observation import BattleMenuPhase, BattleMenuState, MapId


class SendOutDuringSleep(MeasuredTurnRuntime):
    def __init__(self, entry):
        super().__init__(raw=replace(_raw(party_count=3), first_party_status=2))
        self.entry = entry
        self.prompt_visible = entry == "prompt"
        self.menu = BattleMenuState(
            BattleMenuPhase.MAIN if entry == "fight" else BattleMenuPhase.UNKNOWN,
            selected_main_command=0 if entry == "fight" else None,
        )
        self.confirmations = 0

    def trainer_switch_prompt_visible(self, raw):
        return raw.battle_state == 2 and self.prompt_visible

    def execute(self, action):
        if action.kind is MacroActionKind.CONFIRM:
            assert not self.prompt_visible, "executor answered the model-owned prompt"
            self.confirmations += 1
            self.prompt_visible = True
            self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            self.raw = replace(self.raw, enemy_hp=66, enemy_party_position=2)
        return super().execute(action)


@pytest.mark.parametrize("entry", ["prompt", "fight", "dialogue"])
def test_sleep_recovery_yields_unspent_choice_at_each_prompt_boundary(entry):
    runtime = SendOutDuringSleep(entry)
    original_pp = runtime.raw.battler_pp
    assert _recover_sleep_transition(
        runtime, runtime, expected_map=MapId.CERULEAN_CITY, slot=2,
        initial_pp=30, initial_pp_vector=original_pp,
        timing=BattleRuntimeTiming(max_sleep_recovery_pulses=1),
        label="sleep prompt", allow_player_faint=True,
    )
    assert runtime.prompt_visible and runtime.raw.battler_status == 2
    assert runtime.raw.battler_pp == original_pp
    assert runtime.confirmations == (0 if entry == "prompt" else 1)


@pytest.mark.parametrize("asleep", [True, False])
def test_move_menu_transition_yields_before_confirming_send_out(asleep):
    runtime = SendOutDuringSleep("fight")
    if not asleep:
        runtime.raw = replace(runtime.raw, first_party_status=0)
    original_pp = runtime.raw.battler_pp
    result = execute_bounded_battle_move_turn(
        runtime, runtime, expected_map=MapId.CERULEAN_CITY, selected_slot=2,
        expected_battle_state=2, settle_to_next_decision=True,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )
    assert not result.move_executed
    assert runtime.confirmations == 1 and runtime.prompt_visible
    assert runtime.raw.battler_pp == original_pp


@pytest.mark.parametrize("pp", [(34, 30, 30, 11), (35, 29, 30, 11), None])
def test_prompt_handoff_cannot_hide_changed_or_unknown_pp(pp):
    runtime = SendOutDuringSleep("prompt")
    runtime.raw = replace(runtime.raw, first_party_pp=pp)
    with pytest.raises(BattleRuntimeError):
        _recover_sleep_transition(
            runtime, runtime, expected_map=MapId.CERULEAN_CITY, slot=2,
            initial_pp=30, initial_pp_vector=(35, 30, 30, 11),
            timing=BattleRuntimeTiming(max_sleep_recovery_pulses=1),
            label="sleep prompt", allow_player_faint=True,
        )
    assert runtime.confirmations == 0


def test_prompt_handoff_keeps_expected_map_guard():
    runtime = SendOutDuringSleep("prompt")
    with pytest.raises(BattleRuntimeError):
        _unspent_trainer_prompt_boundary(
            runtime, runtime.raw, expected_map=MapId.PALLET_TOWN,
            initial_pp_vector=runtime.raw.battler_pp, label="wrong map",
        )
    assert runtime.confirmations == 0


@pytest.mark.parametrize(
    "context,battle_state,visible",
    [(1, 2, True), (2, 1, True), (2, 0, True), (2, 2, False)],
)
def test_prompt_handoff_requires_native_trainer_prompt(context, battle_state, visible):
    runtime = SendOutDuringSleep("prompt")
    runtime.prompt_visible = visible
    raw = replace(runtime.raw, battle_state=battle_state)
    token = _ACTIVE_BATTLE_STATE.set(context)
    try:
        assert not _unspent_trainer_prompt_boundary(
            runtime, raw, expected_map=MapId.CERULEAN_CITY,
            initial_pp_vector=raw.battler_pp, label="not a trainer prompt",
        )
    finally:
        _ACTIVE_BATTLE_STATE.reset(token)
    assert runtime.confirmations == 0
