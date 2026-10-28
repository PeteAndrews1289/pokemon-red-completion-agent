"""First-menu construction must not dispatch after using its wall reserve."""
from dataclasses import replace
import pytest
from test_native_settlement_admission import actor_at_reserve
from pokemon_red_completion import red_native_player as native
from pokemon_red_completion.red_player_support import PlayerBudgetStop
from pokemon_red_completion.goal_manager import GoalKind

@pytest.mark.parametrize("elapsed", [2, 3, 8.7])
def test_first_menu_consuming_wall_headroom_stops_without_input(tmp_path, monkeypatch, elapsed):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch)
    actor.decisions = 0
    actor.limits = replace(actor.limits, seconds=3)
    actor.wall.elapsed_seconds = 0
    before = actor.snapshot()
    observe = native.observe_native_player_options
    def expensive_menu(*a, **kw):
        options = observe(*a, **kw)
        actor.wall.elapsed_seconds = elapsed
        return options
    monkeypatch.setattr(native, "observe_native_player_options", expensive_menu)
    stop = actor.observe(0)
    assert isinstance(stop, PlayerBudgetStop) and stop.reason == "settlement_budget"
    assert actor.snapshot() == before and not executed
    assert actor.decisions == 0 and actor.controller.frames_executed == 0
    assert stop.public_dict()["model_queries"] == 0

@pytest.mark.parametrize("axis", ["actions", "frames", "ample"])
def test_first_decision_preserves_existing_input_caps_and_ample_menu(tmp_path, monkeypatch, axis):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch)
    actor.decisions = 0
    actor.wall.elapsed_seconds = 1
    if axis == "actions": actor.recorder.trace.extend([None] * 300)
    if axis == "frames": monkeypatch.setattr(type(actor.controller), "frames_executed", property(lambda self: 3000))
    assert not isinstance(actor.observe(0), PlayerBudgetStop)
    assert not executed

def test_first_decision_keeps_unsettled_compulsory_recovery(tmp_path, monkeypatch):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch, support="control")
    actor.decisions = 0
    assert actor.observe(0).binding.kind is GoalKind.RECOVER_CONTROL
    assert not executed
