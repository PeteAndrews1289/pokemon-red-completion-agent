"""One selected attack cannot keep choosing Fight through later sleeping turns."""
from dataclasses import replace

import pytest
from test_battle_runtime import MeasuredTurnRuntime, _raw
from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import (
    BattleRuntimeError, BattleRuntimeTiming, execute_bounded_battle_move_turn,
)
from pokemon_red_completion.observation import BattleMenuPhase, BattleMenuState, MapId


class SleepingTurn(MeasuredTurnRuntime):
    def __init__(self, *, before=6, after=5, damage=0, dialogue=False,
                 nonlead=False, battle_state=2, fault=None, selected=False):
        raw = replace(_raw(battle_state=battle_state), first_party_status=before)
        if nonlead:
            raw = replace(raw, party_count=2, active_party_index=1,
                          active_party_hp=26, active_party_max_hp=49,
                          active_party_status=before, active_party_pp=raw.first_party_pp,
                          active_party_moves=raw.first_party_moves,
                          first_party_status=0, party_hp=(49, 26),
                          party_pp=((10, 10, 10, 10), raw.first_party_pp))
        super().__init__(raw=raw)
        self.confirms = 0
        self.fights = 0
        self.turn_finished = False
        self.waits_after_turn = 0
        self.dialogue_done = False

        def advance(action):
            if action.kind is MacroActionKind.WAIT:
                if self.turn_finished:
                    self.waits_after_turn += 1
                    if fault == "delayed_pp" and self.waits_after_turn == 2:
                        key = "active_party_pp" if nonlead else "first_party_pp"
                        self.raw = replace(self.raw, **{key: (35, 29, 30, 11)})
                    if fault == "delayed_counter" and self.waits_after_turn == 2:
                        key = "active_party_status" if nonlead else "first_party_status"
                        self.raw = replace(self.raw, **{key: 7})
                return
            if action.kind is MacroActionKind.CANCEL and self.menu.phase is BattleMenuPhase.UNKNOWN:
                self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
                self.dialogue_done = True
                return
            if action.kind is not MacroActionKind.CONFIRM:
                raise AssertionError(f"unexpected input {action.kind}")
            self.confirms += 1
            if self.menu.phase is BattleMenuPhase.MAIN:
                self.fights += 1
                if self.fights > 1:
                    raise AssertionError("executor selected a second Fight without the actor")
                if selected:
                    self.menu = BattleMenuState(BattleMenuPhase.MOVE, selected_move_slot=1)
                    return
            elif self.menu.phase is BattleMenuPhase.UNKNOWN:
                self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
                self.dialogue_done = True
                return
            self.turn_finished = True
            status_key = "active_party_status" if nonlead else "first_party_status"
            hp_key = "active_party_hp" if nonlead else "first_party_hp"
            values = {status_key: after, hp_key: 26-damage}
            if fault in {"selected_pp", "offslot_pp", "unknown_pp"}:
                values["active_party_pp" if nonlead else "first_party_pp"] = {
                    "selected_pp": (34, 30, 30, 11),
                    "offslot_pp": (35, 29, 30, 11), "unknown_pp": None,
                }[fault]
            if fault == "unknown_pp":
                values.update(first_party_pp=None, active_party_pp=None, party_pp=None)
            if fault == "unknown_status":
                values.update(first_party_status=None, active_party_status=None)
            if fault == "active_identity":
                values["active_party_index"] = 0
            if fault == "opponent_identity":
                values["enemy_species_id"] = 1
            if fault == "map":
                values["map_id"] = MapId.PALLET_TOWN
            self.raw = replace(self.raw, **values)
            self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN) if dialogue else BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
        self.on_action = advance


def execute(runtime):
    return execute_bounded_battle_move_turn(
        runtime, runtime, expected_map=MapId.CERULEAN_CITY, selected_slot=1,
        expected_battle_state=runtime.raw.battle_state, settle_to_next_decision=True,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )


@pytest.mark.parametrize("before,after,damage,dialogue,selected", [
    (6, 5, 0, False, False), (1, 0, 0, False, False),
    (6, 6, 3, False, False), (6, 5, 0, True, False),
    (1, 0, 0, True, False), (0, 6, 0, True, True),
])
@pytest.mark.parametrize("nonlead,battle_state", [(False, 2), (True, 1)])
def test_selected_attack_returns_after_first_verified_sleep_turn(before, after, damage, dialogue, selected, nonlead, battle_state):
    runtime = SleepingTurn(before=before, after=after, damage=damage, dialogue=dialogue,
                           selected=selected, nonlead=nonlead, battle_state=battle_state)
    result = execute(runtime)
    assert not result.move_executed
    assert result.final_state.battler_status == after
    assert result.final_state.battler_hp == 26-damage
    assert result.final_state.battler_pp == result.initial_state.battler_pp
    assert runtime.fights == 1
    assert runtime.menu.phase is BattleMenuPhase.MAIN
    assert result.pre_attack_frames > 0 if selected else result.pre_attack_frames == 0


@pytest.mark.parametrize("fault", ["selected_pp", "offslot_pp", "unknown_pp", "delayed_pp", "map", "active_identity", "opponent_identity", "unknown_status", "delayed_counter"])
def test_sleep_turn_cannot_hide_resource_or_settlement_fault(fault):
    runtime = SleepingTurn(fault=fault, nonlead=True)
    with pytest.raises(BattleRuntimeError):
        execute(runtime)


def test_stale_main_without_turn_proof_is_not_reported_as_a_completed_turn():
    runtime = MeasuredTurnRuntime(raw=replace(_raw(), first_party_status=6))
    with pytest.raises(BattleRuntimeError):
        execute(runtime)


def test_sleep_counter_increase_without_wake_is_not_silent_progress():
    runtime = SleepingTurn(before=6, after=7)
    with pytest.raises(BattleRuntimeError, match="sleep counter increased"):
        execute(runtime)
