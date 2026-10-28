"""Do not spend a finite return reserve starting another selected trip."""
from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace as NS

import pytest
from test_red_native_player import setup
from test_red_player_budget_stop import session

from pokemon_red_completion import red_native_player as native
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.red_player_support import PlayerBudgetStop
from run_configured_red_player import chunk_continuation_reason


def actor_at_reserve(tmp_path, monkeypatch, *, support=None, partition="development"):
    args, executed = setup(tmp_path, monkeypatch, support=support)
    args["source"] = {**args["source"], "partition": partition}
    args["limits"] = replace(args["limits"], actions=400, frames=4000, seconds=120)
    if partition == "development":
        args["allow_collection_restoration"] = True
    actor = session(args)
    actor.wall = NS(check_wall_time_budget=lambda: None, elapsed_seconds=90)
    actor.decisions = 1  # Renewal tests represent a chunk with a prior decision.
    return actor, executed


@pytest.mark.parametrize("axis", ["seconds", "actions", "frames"])
def test_settled_budget_boundary_has_no_new_goal_input_or_counter_reset(tmp_path, monkeypatch, axis):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch)
    if axis != "seconds":
        actor.wall.elapsed_seconds = 1
    if axis == "actions":
        actor.recorder.trace.extend([None] * 300)
    if axis == "frames":
        monkeypatch.setattr(type(actor.controller), "frames_executed", property(lambda self: 3000))
    before = actor.snapshot()
    counters = (len(actor.recorder.trace), actor.controller.frames_executed, actor.heals)
    stop = actor.observe(0)
    assert isinstance(stop, PlayerBudgetStop) and stop.reason == "settlement_budget"
    assert stop.state_sha256 == before.sha256 == sha256(before.state).hexdigest()
    assert actor.snapshot() == before and not executed
    assert counters == (len(actor.recorder.trace), actor.controller.frames_executed, actor.heals)
    assert stop.public_dict()["model_queries"] == 0
    assert not stop.public_dict()["full_game_completion"]


def test_menu_time_crossing_reserve_is_caught_before_choice(tmp_path, monkeypatch):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch)
    actor.wall.elapsed_seconds = 1
    original = native.observe_native_player_options

    def slow_observation(*args, **kwargs):
        value = original(*args, **kwargs)
        actor.wall.elapsed_seconds = 90
        return value

    monkeypatch.setattr(native, "observe_native_player_options", slow_observation)
    stop = actor.observe(0)
    assert isinstance(stop, PlayerBudgetStop) and not executed
    assert actor.controller.frames_executed == 0


def test_reserve_never_hides_unsettled_compulsory_recovery(tmp_path, monkeypatch):
    actor, executed = actor_at_reserve(tmp_path, monkeypatch, support="control")
    options = actor.observe(0)
    assert options.binding.kind is GoalKind.RECOVER_CONTROL
    assert not executed and actor.controller.frames_executed == 0


@pytest.mark.parametrize("scope", ["ample", "train", "restoration_disabled"])
def test_unaffected_ordinary_menus_remain_available(tmp_path, monkeypatch, scope):
    actor, executed = actor_at_reserve(
        tmp_path, monkeypatch, partition="train" if scope == "train" else "development"
    )
    if scope == "ample":
        actor.wall.elapsed_seconds = 1
    if scope == "restoration_disabled":
        actor.allow_collection_restoration = False
    options = actor.observe(0)
    assert not isinstance(options, PlayerBudgetStop) and len(options.bindings) == 2
    assert not executed and actor.controller.frames_executed == 0


@pytest.mark.parametrize("progress", [False, True])
def test_driver_renews_settlement_stop_only_after_real_progress(progress):
    result = dict(released=True, state_sha256="b" * 64 if progress else "a" * 64,
        chunk_costs=dict(actions_attempted=10 if progress else 0, frames=240 if progress else 0),
        episode=dict(stop_reason="settlement_budget", outcomes=[]))
    assert chunk_continuation_reason(result, source_sha256="a" * 64) == (
        "automatic_chunk_renewal" if progress else "no_executable_progress"
    )
