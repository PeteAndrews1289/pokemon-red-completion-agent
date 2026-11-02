"""Exhausted restoration allowance is not a model failure or curriculum success."""

import json
from dataclasses import replace

import pytest
from test_red_native_player import setup

import pokemon_red_completion.red_native_player as native
from pokemon_red_completion.goal_manager import GoalAvailability, GoalKind
from pokemon_red_completion.goal_manager_runtime import GoalBindingSet
from pokemon_red_completion.red_player_support import PlayerBudgetStop


def session(args):
    args["execution"] = native.NativeExecutionIdentity(
        args.pop("run_id"), args.pop("arm_id"), args.pop("model").model_sha256,
        args.pop("seed"),
    )
    return native.NativePlayerSession(**args)


def test_spent_heal_stops_before_another_selection_or_input(tmp_path, monkeypatch):
    args, executed = setup(tmp_path, monkeypatch, support="restore")
    args["limits"] = replace(args["limits"], actions=5, heals=1)
    result = native.run_native_continuous_player(**args)
    assert executed == [2]
    assert result["stop_reason"] == "restoration_budget"
    assert result["executed_decisions"] == result["successful_decisions"] == 1
    assert result["support_decisions"] == 1 and result["model_decisions"] == 0
    step = args["output"] / "episode/step-001"
    stop = json.loads((step / "budget-stop.json").read_text())
    assert not stop["curriculum_complete"] and not stop["full_game_completion"]
    assert stop["model_queries"] == 0 and not (step / "intent.json").exists()
    assert (step / "terminal.state").read_bytes() == b"2"
    costs = json.loads((args["output"] / "native-costs.json").read_text())
    assert costs["restore_attempts"] == costs["goal_attempts"] == 1
    assert costs["actions_attempted"] == 1 and costs["frames"] == 2


def test_spent_heal_keeps_other_real_choices(tmp_path, monkeypatch):
    args, _ = setup(tmp_path, monkeypatch)
    from test_red_live_option_menu import _binding

    bindings = tuple(_binding(k, binding_ref=k.value, calls=[]) for k in (
        GoalKind.RESTORE_TEAM, GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM,
    ))
    args["enumerate_bindings"] = lambda *a: GoalBindingSet(
        tuple(b.opportunity for b in bindings), bindings,
    )
    actor = session(args)
    actor.heals = actor.limits.heals
    options = actor.observe(0)
    assert {b.kind for b in options.bindings} == {
        GoalKind.ADVANCE_STORY, GoalKind.DEVELOP_TEAM,
    }
    assert actor.controller.frames_executed == 0
    assert actor.snapshot().state == b"0"


def test_spent_heal_does_not_hide_mandatory_control_recovery(tmp_path, monkeypatch):
    args, _ = setup(tmp_path, monkeypatch, support="control")
    actor = session(args)
    actor.heals = actor.limits.heals
    options = actor.observe(0)
    assert options.binding.kind is GoalKind.RECOVER_CONTROL
    assert options.binding.opportunity.availability is GoalAvailability.AVAILABLE
    assert actor.controller.frames_executed == 0


@pytest.mark.parametrize("bad_hash", [None, "", "f" * 63, "F" * 64, "g" * 64])
def test_budget_stop_requires_canonical_state_hash(bad_hash):
    with pytest.raises(ValueError, match="authenticated exhaustion"):
        PlayerBudgetStop(bad_hash)


def test_budget_stop_cannot_claim_completion():
    with pytest.raises(ValueError):
        PlayerBudgetStop("a" * 64, "curriculum_complete")


@pytest.mark.parametrize("bad", ["hash", "mutate", "unsettled"])
def test_runner_rejects_untrusted_budget_boundary(tmp_path, monkeypatch, bad):
    from hashlib import sha256

    args, _ = setup(tmp_path, monkeypatch, support="control" if bad == "unsettled" else None)

    def observe(actor, ordinal):
        if bad == "mutate":
            actor.emulator.tick(1)
        return PlayerBudgetStop("0" * 64 if bad == "hash" else sha256(b"0").hexdigest())

    monkeypatch.setattr(native.NativePlayerSession, "observe", observe)
    result = native.run_native_continuous_player(**args)
    assert result["stop_reason"] == "menu_unavailable"
    assert result["executed_decisions"] == 0
    assert not (args["output"] / "episode/step-000/budget-stop.json").exists()
