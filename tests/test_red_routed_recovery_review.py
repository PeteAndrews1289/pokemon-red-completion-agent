"""Codex falsifiers for Flash's recovery draft; no private saved states."""

from dataclasses import replace

import pytest
from test_red_routed_recovery import make_fixture

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.red_routed_recovery import (
    RedRoutedRecoveryError,
    bind_routed_center_recovery,
)


def offer(monkeypatch, prepare=None):
    router, bindings, observe, state, collection, calls = make_fixture(monkeypatch)
    def prep():
        calls.append("prep")
        if prepare:
            prepare(state)
    result = bind_routed_center_recovery(router, bindings, observe(), prepare_escort=prep)
    binding = next(b for b in result.bindings if b.kind is GoalKind.RESTORE_TEAM)
    return binding, state, calls


@pytest.mark.parametrize("update", [
    {"party_max_hp": (31, 30)}, {"party_levels": (11, 12)},
    {"party_pp": ((9, 10), (10, 10))}, {"party_count": 1},
])
def test_stale_complete_member_state_rejects_before_prep(monkeypatch, update):
    binding, state, calls = offer(monkeypatch)
    state["raw"] = replace(state["raw"], **update)
    with pytest.raises(RedRoutedRecoveryError):
        binding.execute()
    assert not calls


@pytest.mark.parametrize("update", [
    {"party_pp": ((99, 10), (10, 10))}, {"party_levels": (11, 12)},
    {"party_moves": ((5, 2), (3, 4))}, {"player_x": 99},
])
def test_escort_cannot_mutate_moves_levels_pp_or_position(monkeypatch, update):
    def prepare(state):
        state["raw"] = replace(state["raw"], **update)
    binding, state, calls = offer(monkeypatch, prepare)
    with pytest.raises(RedRoutedRecoveryError):
        binding.execute()
    assert calls == ["prep"]


@pytest.mark.parametrize("update", [
    {"player_x": 99}, {"map_id": 22}, {"player_money": 999},
    {"bag_items": ((4, 1),)}, {"party_hp": (30, 0)},
])
def test_fresh_final_damage_cannot_be_hidden_by_heal_report(monkeypatch, update):
    binding, state, _calls = offer(monkeypatch)
    report = binding.execute()
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    state["raw"] = replace(state["raw"], **update)
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED
