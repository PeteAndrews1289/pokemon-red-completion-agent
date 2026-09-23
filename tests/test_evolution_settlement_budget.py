import hashlib
import json

import pytest
from run_red_evolution_battle_settlement import validate_source

from pokemon_red_completion.executor import WindowedFrameBudgetController
from pokemon_red_completion.goal_manager_composition_qualification import (
    HardCompositionActionLimiter,
)
from pokemon_red_completion.red_team_training import evolution_reserve_requested


class Delegate:
    frame_count = 0

    def tick(self, frames):
        self.frame_count += frames

    def execute(self, action):
        if action == "fail":
            raise RuntimeError("partial dispatch")


def test_remaining_actions_counts_failed_attempt_and_both_caps():
    limit = HardCompositionActionLimiter(
        Delegate(), maximum_actions_per_decision=2, maximum_episode_actions=3
    )
    assert limit.remaining_actions == 2
    with pytest.raises(RuntimeError):
        limit.execute("fail")
    assert limit.remaining_actions == 1
    limit.begin_decision_window()
    assert limit.remaining_actions == 2
    limit.execute("ok")
    limit.execute("ok")
    limit.begin_decision_window()
    assert limit.remaining_actions == 0
    with pytest.raises(RuntimeError):
        limit.execute("ok")


def test_remaining_frames_honors_total_window_and_nested_limits():
    control = WindowedFrameBudgetController(
        Delegate(), maximum_frames_per_window=10, maximum_total_frames=12
    )
    control.tick(6)
    assert control.remaining_frames == 4
    with control.limit_additional_frames(2):
        control.begin_window()
        assert control.remaining_frames == 2
        control.tick(2)
        assert control.remaining_frames == 0
        with pytest.raises(RuntimeError):
            control.tick(1)
    assert control.remaining_frames == 4
    control.tick(4)
    control.begin_window()
    assert control.remaining_frames == 0


@pytest.mark.parametrize("value", [None, 0, 1, "yes"])
def test_non_boolean_reserve_fails_closed(value):
    with pytest.raises(TypeError):
        evolution_reserve_requested(lambda: value)


def settlement_source():
    decision = {
        "schema": "pokemon.red.live-mixed-option-choice.v1",
        "mode": "model_exploration",
        "selected_option_kind": "evolve",
        "model_sha256": "a" * 64,
        "menu_sha256": "b" * 64,
    }
    outcome = {
        "selected_kind": "evolve_species",
        "safe_terminal": False,
        "error_type": "CompositionActionBudgetExhausted",
        "after": {"battle_state": 1},
        "terminal_state_sha256": hashlib.sha256(b"terminal").hexdigest(),
        "before_state_sha256": "c" * 64,
        "choice": decision,
    }
    result = {
        "schema": "pokemon.red.autonomous-option-result.v1",
        "stop_reason": "execution_failed",
        "outcomes": [outcome],
        "model_sha256": "a" * 64,
    }
    started = {
        "selected_kind": "evolve_species",
        "state_sha256": "c" * 64,
        "menu_sha256": "b" * 64,
        "selected_binding_ref": "retained-goal",
    }
    return dict(
        result=result, outcome=outcome, decision=decision, started=started, state=b"terminal"
    )


def test_exact_settlement_source_is_admitted_without_replay():
    validate_source(**settlement_source())


@pytest.mark.parametrize("mutation", ["state", "latest", "menu", "goal", "error", "model"])
def test_settlement_rejects_changed_source(mutation):
    source = settlement_source()
    if mutation == "state":
        source["state"] = b"earlier"
    elif mutation == "latest":
        source["result"]["outcomes"].append({})
    elif mutation == "menu":
        source["started"]["menu_sha256"] = "d" * 64
    elif mutation == "goal":
        source["started"]["selected_kind"] = "acquire_species"
    elif mutation == "error":
        source["outcome"]["error_type"] = "unexpected"
    else:
        source["result"]["model_sha256"] = "d" * 64
    with pytest.raises(ValueError):
        validate_source(**source)


@pytest.mark.parametrize("mutation", [None, "state", "cash", "cost", "identity", "unsafe", "model"])
def test_settled_goal_continuation_preserves_original_choice_and_resources(mutation):
    from run_red_autonomous_collection import _verify_goal_continuation

    source = settlement_source()
    original = source["outcome"]
    original["learning_eligible"] = True
    original["after"].update(
        owned_species=["owned"],
        specimen_counts={"owned": 1},
        cash=1000,
        bag_items=[[3, 1]],
        map_id=22,
    )
    origin = original["before_state_sha256"]
    settled_hash = "e" * 64
    plan = {
        "mode": "continue_selected_goal",
        "reserve_origin": {"sha256": origin},
        "state": {"sha256": settled_hash},
        "settlement_plan": {},
        "settlement_outcome": {},
    }
    parent = {
        "schema": "pokemon.red.autonomous-option-run.v1",
        "model_sha256": "a" * 64,
        "provenance": {"parent_state_sha256": origin},
    }
    settled_plan = {
        "schema": "pokemon.red.evolution-battle-settlement.v1",
        "parent_state_sha256": original["terminal_state_sha256"],
        "prior_binding_ref": source["started"]["selected_binding_ref"],
        "prior_outcome_sha256": hashlib.sha256(json.dumps(original).encode()).hexdigest(),
        "maximum_actions": 1000,
        "maximum_frames": 120000,
    }
    settled = {
        "before_state_sha256": original["terminal_state_sha256"],
        "terminal_state_sha256": settled_hash,
        "safe_terminal": True,
        "verification": "defensive_escape",
        "error": None,
        "model_queries": 0,
        "learning_eligible": False,
        "actions": 25,
        "frames": 500,
        "before": original["after"].copy(),
        "after": {**original["after"], "battle_state": 0, "input_ready": True},
    }
    if mutation == "state":
        plan["state"]["sha256"] = "f" * 64
    elif mutation == "cash":
        settled["after"]["cash"] = 1001
    elif mutation == "cost":
        settled["actions"] = 1001
    elif mutation == "identity":
        settled_plan["prior_binding_ref"] = "different"
    elif mutation == "unsafe":
        settled["safe_terminal"] = False
    elif mutation == "model":
        source["result"]["model_sha256"] = "f" * 64
    payloads = {
        key: json.dumps(value).encode()
        for key, value in {
            "prior_plan": parent,
            "prior_outcome": original,
            "prior_result": source["result"],
            "prior_execution_started": source["started"],
            "settlement_plan": settled_plan,
            "settlement_outcome": settled,
        }.items()
    }
    if mutation is None:
        assert _verify_goal_continuation(plan, payloads) == "retained-goal"
    else:
        with pytest.raises(ValueError):
            _verify_goal_continuation(plan, payloads)
