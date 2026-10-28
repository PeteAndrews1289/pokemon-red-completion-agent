"""Persistent sleep yields to the actor before another recovery episode."""

from dataclasses import replace

import pytest
from test_battle_runtime import MeasuredTurnRuntime, ReappliedSleepSimulation, _raw

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import (
    _ACTIVE_BATTLE_STATE,
    BattleRuntimeError,
    BattleRuntimeTiming,
    _recover_sleep_transition,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.observation import BattleMenuPhase, BattleMenuState, MapId


class RepeatedSleepAtMain(MeasuredTurnRuntime):
    def __init__(self, *, nonlead=True, battle_state=1, fault=None, cap=2):
        pp = (35, 30, 30, 13)
        raw = replace(
            _raw(party_count=6, battle_state=battle_state, pp=pp),
            first_party_status=2,
        )
        if nonlead:
            raw = replace(
                raw,
                first_party_status=0,
                first_party_pp=(30, 20, 30, 29),
                active_party_index=3,
                active_party_hp=59,
                active_party_max_hp=71,
                active_party_status=2,
                active_party_moves=(33, 39, 98, 158),
                active_party_pp=pp,
                party_hp=(69, 96, 61, 59, 124, 121),
                party_pp=((30, 20, 30, 29), (30, 40, 20, 30),
                          (34, 40, 20, 30), pp,
                          (35, 15, 30, 20), (40, 30, 30, 25)),
            )
        super().__init__(raw=raw)
        self.nonlead = nonlead
        self.fault = fault
        self.cap = cap
        self.reapplications = 0
        self.sleeping_turns = 0

    def execute(self, action):
        if action.kind is MacroActionKind.CANCEL and self.menu.phase is BattleMenuPhase.UNKNOWN:
            self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=0)
        if action.kind is MacroActionKind.CONFIRM:
            if self.menu.phase is BattleMenuPhase.MAIN:
                count = self.raw.battler_status & 7
                assert count, "executor dispatched an extra waking attack"
                self.sleeping_turns += 1
                if count == 1:
                    self.reapplications += 1
                    count = 5
                else:
                    count -= 1
                key = "active_party_status" if self.nonlead else "first_party_status"
                self.raw = replace(self.raw, **{key: count})
                if self.reapplications == self.cap:
                    if self.fault in {"selected_pp", "offslot_pp", "unknown_pp"}:
                        pp = {
                            "selected_pp": (35, 30, 30, 12),
                            "offslot_pp": (35, 29, 30, 13),
                            "unknown_pp": None,
                        }[self.fault]
                        self.raw = replace(self.raw, active_party_pp=pp)
                    elif self.fault == "map":
                        self.raw = replace(self.raw, map_id=MapId.PALLET_TOWN)
                self.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
            elif self.menu.phase is BattleMenuPhase.UNKNOWN:
                command = 4 if self.fault == "menu" and self.reapplications == self.cap else 0
                self.menu = BattleMenuState(BattleMenuPhase.MAIN, selected_main_command=command)
            else:
                raise AssertionError("sleep recovery supplied another move selection")
        return super().execute(action)


def recover(runtime, *, cap):
    initial = runtime.raw
    token = _ACTIVE_BATTLE_STATE.set(initial.battle_state)
    try:
        return _recover_sleep_transition(
            runtime, runtime,
            expected_map=MapId.CERULEAN_CITY, slot=4,
            initial_pp=13, initial_pp_vector=initial.battler_pp,
            initial_raw=initial,
            timing=BattleRuntimeTiming(max_sleep_reapplications=cap),
            label="repeated sleep", allow_player_faint=True,
        )
    finally:
        _ACTIVE_BATTLE_STATE.reset(token)


@pytest.mark.parametrize("cap", [1, 2, 4])
@pytest.mark.parametrize("nonlead", [False, True])
def test_sleep_application_cap_returns_at_main_without_another_turn(cap, nonlead):
    runtime = RepeatedSleepAtMain(cap=cap, nonlead=nonlead)
    initial_pp = runtime.raw.battler_pp
    assert recover(runtime, cap=cap)
    assert runtime.menu.phase is BattleMenuPhase.MAIN
    assert runtime.reapplications == cap
    assert runtime.sleeping_turns == 2 + 5 * (cap - 1)
    assert runtime.raw.battler_status == 5
    assert runtime.raw.battler_pp == initial_pp


@pytest.mark.parametrize("battle_state", [1, 2])
@pytest.mark.parametrize("nonlead", [False, True])
def test_whole_sleeping_turn_returns_unspent_to_the_next_actor_boundary(battle_state, nonlead):
    runtime = RepeatedSleepAtMain(battle_state=battle_state, nonlead=nonlead)
    result = execute_bounded_battle_move_turn(
        runtime, runtime, expected_map=MapId.CERULEAN_CITY,
        selected_slot=4, expected_battle_state=battle_state,
        settle_to_next_decision=True,
        timing=BattleRuntimeTiming(max_move_menu_transition_pulses=1),
    )
    assert not result.move_executed
    assert runtime.menu.phase is BattleMenuPhase.MAIN
    assert runtime.reapplications == 0
    assert runtime.sleeping_turns == 1
    assert result.final_state.battler_pp == result.initial_state.battler_pp
    assert result.final_state.battler_status == 1
    assert result.final_state.battle_state == battle_state
    assert result.final_state.battler_hp > 0


@pytest.mark.parametrize("fault", ["selected_pp", "offslot_pp", "unknown_pp", "map", "menu"])
def test_sleep_handoff_cannot_hide_invalid_resource_or_boundary_proof(fault):
    runtime = RepeatedSleepAtMain(fault=fault)
    with pytest.raises(BattleRuntimeError):
        recover(runtime, cap=2)
    assert runtime.reapplications <= 2


def test_sleep_cap_still_rejects_reapplications_without_a_main_boundary():
    runtime = ReappliedSleepSimulation(reapplications=3)
    runtime.sleep_started = True
    runtime.raw = replace(runtime.raw, first_party_status=2)
    runtime.menu = BattleMenuState(BattleMenuPhase.UNKNOWN)
    with pytest.raises(BattleRuntimeError, match="bounded sleep reapplications"):
        _recover_sleep_transition(
            runtime, runtime, expected_map=MapId.CERULEAN_CITY,
            slot=1, initial_pp=35, initial_pp_vector=runtime.raw.battler_pp,
            timing=BattleRuntimeTiming(), label="unsafe sleep boundary",
            allow_player_faint=True,
        )
