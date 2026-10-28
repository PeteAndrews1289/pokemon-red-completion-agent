"""Codex falsifiers for Flash's recovery draft; no private saved states."""

from dataclasses import replace

import pytest
from test_red_routed_recovery import make_fixture

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.red_routed_recovery import (
    RedRoutedRecoveryError,
    bind_routed_center_recovery,
)
from pokemon_red_completion.route_executor import InterruptionReceipt, TraversalSnapshot
import pokemon_red_completion.red_routed_recovery as recovery


@pytest.mark.parametrize("income,verified,battle_started,accepted", (
    (725, True, True, True), (725, False, True, False),
    (725, True, False, False), (-10, True, True, False),
))
def test_only_verified_trainer_income_can_change_recovery_money(
    monkeypatch, income, verified, battle_started, accepted
):
    router, bindings, observe, state, _collection, _calls = make_fixture(monkeypatch)
    def route(_plan, _actions, _observer, *, interruption_handler, **_kwargs):
        snapshot = TraversalSnapshot(
            map_id=state["raw"].map_id,
            at=(state["raw"].player_y, state["raw"].player_x),
            ready=False, interruption="battle:2",
        )
        class Trainer:
            def handle(self, interruption):
                state["raw"] = replace(state["raw"], player_money=209 + income)
                return InterruptionReceipt(
                    kind="trainer_engagement", resumed_map=interruption.map_id,
                    resumed_at=interruption.at,
                    details={"verified": verified, "battle_started": battle_started},
                )
        interruption_handler.inner = Trainer()
        interruption_handler.handle(snapshot)
        state["raw"] = replace(state["raw"], map_id=64, player_x=3, player_y=7)
        return type("Result", (), {"passed": True})()
    monkeypatch.setattr(recovery, "execute_route", route)
    offered = bind_routed_center_recovery(router, bindings, observe(), prepare_escort=lambda: None)
    binding = next(b for b in offered.bindings if b.kind is GoalKind.RESTORE_TEAM)
    if not accepted:
        with pytest.raises(RedRoutedRecoveryError, match="unverified money"):
            binding.execute()
        return
    report = binding.execute()
    assert report.evidence["routed_recovery"]["verified_trainer_income"] == income
    assert binding.verify(report).status is GoalDecisionOutcome.SUCCEEDED
    state["raw"] = replace(state["raw"], player_money=state["raw"].player_money + 1)
    assert binding.verify(report).status is GoalDecisionOutcome.FAILED


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
