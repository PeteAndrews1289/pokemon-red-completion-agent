"""Disable can force one native move without broadening zero-PP or TRAIN scope."""
from dataclasses import replace

import pytest
from test_red_forced_struggle import Native, raw

from pokemon_red_completion import battle_runtime
from pokemon_red_completion import red_forced_struggle as s
from pokemon_red_completion.red_trainer_practice_admission import _valid_forced_struggle
from pokemon_red_completion.red_trainer_practice_episode import _resource_state


def disabled_raw():
    return replace(raw(), active_party_moves=(106, 0, 0, 0),
                   active_party_pp=(30, 0, 0, 0), player_disabled_move_slot=1,
                   player_disable_turns=4)


@pytest.mark.parametrize("changes", [None, {"party_hp": (100, 1)},
    {"player_disabled_move_slot": None}, {"player_disabled_move_slot": 0},
    {"player_disabled_move_slot": 2}, {"player_disabled_move_slot": True},
    {"player_disable_turns": None}, {"player_disable_turns": 0},
    {"player_disable_turns": 9}, {"player_disable_turns": True},
    {"active_party_pp": (30, 1, 0, 0)}, {"active_party_pp": (30, 64, 0, 0)},
    {"active_party_pp": (0, 0, 0, 0)}, {"active_party_pp": None},
    {"active_party_moves": None}, {"active_party_moves": (0, 0, 0, 0)},
    {"active_party_hp": 0}, {"party_hp": (99, 0)}, {"battle_state": 1},
    {"enemy_hp": 0}])
def test_disabled_singleton_is_separate_and_exact(changes):
    state = replace(disabled_raw(), **(changes or {}))
    assert s.disabled_forced_struggle_available(state) is (changes is None)
    if changes is None:
        assert not s.forced_struggle_available(state)
        assert not s.model_struggle_available(state)
    else:
        native = Native()
        native.raw = state
        with pytest.raises(battle_runtime.BattleRuntimeError):
            s.execute_disabled_forced_struggle_turn(native, native, expected_map=120)
        assert not native.actions


@pytest.mark.parametrize("options", [{}, {"own_hp": 0},
    {"stuck": True}, {"selected": False}, {"move_menu": True}])
def test_disabled_singleton_keeps_native_selection_and_bounded_executor(monkeypatch, options):
    monkeypatch.setattr(battle_runtime, "_preserve_moves_at_learning_prompt", lambda *a, **k: False)
    native = Native(**options)
    native.raw = disabled_raw()
    if any(options.get(key) for key in ("stuck", "move_menu")) or options.get("selected") is False:
        with pytest.raises(battle_runtime.BattleRuntimeError):
            s.execute_disabled_forced_struggle_turn(native, native, expected_map=120)
        assert len(native.actions) <= 15
        return
    result = s.execute_disabled_forced_struggle_turn(native, native, expected_map=120)
    assert result.final_state.battler_pp == (30, 0, 0, 0)
    assert result.public_dict()["availability_basis"] == "last_usable_move_disabled"
    assert result.public_dict()["cartridge_selection_observed"] is True
    decision = dict(authority="forced_mechanic", legal_party_slots=[], model_diagnostics={},
        policy_elapsed_ns=0, move_slot=None, state_before=_resource_state(result.initial_state),
        state_after=_resource_state(result.final_state), outcome=result.public_dict())
    assert not _valid_forced_struggle(decision)  # No broadened legacy TRAIN admission.
