from dataclasses import replace

import pytest
from test_battle_runtime import FakeRuntime, _raw

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.battle_runtime import (
    _ACTIVE_BATTLE_STATE,
    BattleRuntimeTiming,
    _await_next_battle_decision,
)
from pokemon_red_completion.observation import BattleMenuPhase, BattleMenuState


@pytest.mark.parametrize(
    "battle,enemy_hp,expected",
    [
        (1, 0, MacroActionKind.CONFIRM),
        (1, 10, MacroActionKind.CANCEL),
        (2, 0, MacroActionKind.CANCEL),
    ],
)
def test_only_proven_wild_knockout_avoids_evolution_cancel(battle, enemy_hp, expected):
    runtime = FakeRuntime(
        raw=_raw(battle_state=battle, enemy_hp=enemy_hp),
        menu=BattleMenuState(BattleMenuPhase.UNKNOWN),
    )
    initial = runtime.raw

    def step(action):
        if action.kind is not MacroActionKind.WAIT:
            assert action.kind is expected
            runtime.raw = replace(runtime.raw, battle_state=0)

    runtime.on_action = step
    token = _ACTIVE_BATTLE_STATE.set(battle)
    try:
        run_settlement(runtime, initial, battle)
    finally:
        _ACTIVE_BATTLE_STATE.reset(token)
    assert runtime.raw.battle_state == 0


def run_settlement(runtime, initial, battle):
    _await_next_battle_decision(
        runtime,
        runtime,
        expected_map=initial.map_id,
        expected_battle_state=battle,
        initial_raw=initial,
        slot=1,
        move_executed=False,
        timing=BattleRuntimeTiming(),
        label="wild post-KO",
    )
