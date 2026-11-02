"""A settled new decision needs useful work headroom above its return reserve."""

from dataclasses import replace

import pytest
from test_native_settlement_admission import actor_at_reserve

from pokemon_red_completion import red_native_player as native
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_player_support import PlayerBudgetStop


def set_remaining(actor, monkeypatch, axis, remaining):
    actor.wall.elapsed_seconds = 1
    if axis == "actions":
        actor.recorder.trace.extend([None] * (actor.limits.actions - remaining))
    elif axis == "frames":
        spent = actor.limits.frames - remaining
        monkeypatch.setattr(type(actor.controller), "frames_executed", property(lambda self: spent))
    else:
        actor.wall.elapsed_seconds = actor.limits.seconds - remaining


@pytest.mark.parametrize("axis,reserve", [("actions", 100), ("frames", 1000), ("seconds", 30)])
@pytest.mark.parametrize("extra,stops", [(0, True), (1, False)])
def test_new_goal_boundary_retains_work_and_return_allowances(
    tmp_path, monkeypatch, axis, reserve, extra, stops
):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch)
    set_remaining(actor, monkeypatch, axis, 2 * reserve + extra)
    before = actor.snapshot()
    counters = (
        len(actor.recorder.trace),
        actor.controller.frames_executed,
        actor.heals,
        actor.decisions,
    )
    # At this boundary the in-flight goal may still train, but a fresh goal waits.
    assert not actor.evolution_reserve_reached()
    value = actor.observe(1)
    assert isinstance(value, PlayerBudgetStop) is stops
    if stops:
        assert value.reason == "settlement_budget" and value.state_sha256 == before.sha256
        assert value.public_dict()["model_queries"] == 0
    else:
        assert {b.kind for b in value.bindings} == {GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM}
    assert actor.snapshot() == before and not executed
    assert counters == (
        len(actor.recorder.trace),
        actor.controller.frames_executed,
        actor.heals,
        actor.decisions,
    )


def test_mid_failed_evolution_frame_headroom_renews_before_choice(tmp_path, monkeypatch):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch)
    actor.limits = replace(actor.limits, decisions=24, actions=30000, frames=2500000, seconds=600)
    actor.decisions = 19
    set_remaining(actor, monkeypatch, "frames", 259948)
    assert not actor.evolution_reserve_reached()
    before = actor.snapshot()
    stop = actor.observe(19)
    assert isinstance(stop, PlayerBudgetStop) and stop.reason == "settlement_budget"
    assert stop.state_sha256 == before.sha256 and actor.snapshot() == before
    assert actor.decisions == 19 and not executed
    # The recorded routed attempt spent 23,796 frames before finding no work budget.
    assert 259948 - 23796 < 250000


def test_menu_construction_can_use_the_productive_allowance_without_dispatch(tmp_path, monkeypatch):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch)
    actor.wall.elapsed_seconds = 1
    original = native.observe_native_player_options

    def slow_menu(*args, **kwargs):
        value = original(*args, **kwargs)
        actor.wall.elapsed_seconds = 60
        return value

    monkeypatch.setattr(native, "observe_native_player_options", slow_menu)
    before = actor.snapshot()
    assert isinstance(actor.observe(1), PlayerBudgetStop)
    assert not actor.evolution_reserve_reached()
    assert actor.snapshot() == before and not executed


def test_compulsory_unsettled_recovery_bypasses_new_goal_margin(tmp_path, monkeypatch):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch, support="control")
    set_remaining(actor, monkeypatch, "seconds", 60)
    assert actor.decision_admission_reserve_reached() and not actor.evolution_reserve_reached()
    options = actor.observe(1)
    assert options.binding.kind is GoalKind.RECOVER_CONTROL
    assert not executed and actor.decisions == 1


def test_settled_restoration_support_can_renew_without_issuing_input(tmp_path, monkeypatch):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch, support="restore")
    set_remaining(actor, monkeypatch, "seconds", 60)
    stop = actor.observe(1)
    assert isinstance(stop, PlayerBudgetStop) and stop.reason == "settlement_budget"
    assert not executed and actor.heals == 0
