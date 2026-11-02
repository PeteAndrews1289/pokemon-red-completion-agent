from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import battle_runtime as b
from pokemon_red_completion.actions import MacroActionKind


@pytest.mark.parametrize("roster", [(0, 0), (0, 1), None, (), (False,), (-1,)])
def test_confirm_only_after_verified_final_trainer_ko(monkeypatch, roster):
    raw = N(battle_state=2, battler_hp=10, enemy_hp=0,
            active_party_index=0, battler_pp=(10, 10, 0, 0))
    reader = N(
        read=lambda: raw,
        read_enemy_party_roster_hp=lambda: roster,
        read_battle_menu_state=lambda _: N(phase=b.BattleMenuPhase.UNKNOWN),
    )
    actions = []

    def execute(action):
        actions.append(action)
        if action.kind in {MacroActionKind.CONFIRM, MacroActionKind.CANCEL}:
            raw.battle_state = 0

    monkeypatch.setattr(b, "_require_present_turn_state", lambda *a, **k: None)
    monkeypatch.setattr(b, "_preserve_moves_at_learning_prompt", lambda *a, **k: False)
    monkeypatch.setattr(b, "_trainer_switch_prompt_visible", lambda *a: False)
    monkeypatch.setattr(b, "_validated_menu", lambda menu, **k: menu)
    b._await_next_battle_decision(
        reader,
        N(execute=execute),
        expected_map=61,
        expected_battle_state=2,
        initial_raw=raw,
        slot=1,
        move_executed=False,
        timing=b.BattleRuntimeTiming(),
        label="test",
    )
    assert actions[0].kind is (
        MacroActionKind.CONFIRM if roster == (0, 0) else MacroActionKind.CANCEL
    )
