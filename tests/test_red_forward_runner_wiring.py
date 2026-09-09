"""Actual arm-owner wiring with a real collector and the existing fake emulator."""

from inspect import getclosurevars
from types import SimpleNamespace

import pytest
from test_goal_resource_quote import _supply_model
from test_paired_red_bounded_player_script import _spent_arm_failure_harness
from test_red_forward_goal import champion_raw, choice, observation
from test_red_forward_runner import readiness as forward_readiness
from test_red_player_training import _plan

from pokemon_red_completion.forward_goal import ForwardGoalTerminal
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetCheckpoint
from pokemon_red_completion.living_dex_option_value import (
    upgrade_option_value_model_for_optional_recovery,
)
from pokemon_red_completion.red_forward_goal import RedForwardGoalCollector


def wired(monkeypatch, *, stage="verifier", complete=False, terminal_write_error=False):
    h = _spent_arm_failure_harness(monkeypatch, stage=stage)
    closure = getclosurevars(h.run).nonlocals
    ready, namespace = closure["readiness"], closure["run_arm"].__globals__
    model = upgrade_option_value_model_for_optional_recovery(_supply_model())
    ready.training_plan = _plan(model)
    ready.causal_record = SimpleNamespace(model=model)
    ready.decision_limit = 2
    ready.forward_story_objective = "defeat_champion"
    ready.forward_resource_budget = 2
    ready.profile = forward_readiness().profile
    ready.model_sha256 = model.model_sha256
    meter = namespace["CompositionIndependentBudgetMeter"]()
    meter.checkpoint = lambda: CompositionBudgetCheckpoint(
        h.emulator.inputs, h.emulator.frame_count
    )
    holder = [observation()]
    adapter = SimpleNamespace(observe=lambda: holder[0])
    monkeypatch.setitem(
        namespace, "build_red_goal_context_runtime", lambda **_: SimpleNamespace(adapter=adapter)
    )
    writer = ready.private_root.begin_episode("unused")
    original_append = writer.append
    forward_events, headers, collectors = [], [], []

    def append(stream, document, **kwargs):
        if stream == "forward_goal":
            assert not h.emulator.closed and kwargs == {"durable": True}
            if terminal_write_error and document.get("outcome") is not None:
                raise OSError("forward outcome append failed")
            h.order.append(document["kind"])
            forward_events.append(document)
            return
        return original_append(stream, document, **kwargs)

    writer.append = append
    sink = namespace["EpisodeTrajectorySink"]()
    sink.write_episode_header = lambda **kwargs: headers.append(kwargs["metadata"])

    def trajectory(**kwargs):
        collector = kwargs["forward"]
        assert isinstance(collector, RedForwardGoalCollector)
        assert kwargs["observe_training"] is adapter.observe
        assert kwargs["training_meter"] is meter
        assert kwargs["training_plan_sha256"] == ready.training_plan.plan_sha256
        assert h.emulator.inputs == 0
        assert [event["kind"] for event in forward_events] == ["forward_goal_declaration"]
        collectors.append(collector)
        return SimpleNamespace(forward=collector)

    monkeypatch.setitem(namespace, "RedForwardTrainingTrajectory", trajectory)
    original_player = namespace["run_bounded_player_episode"]

    def player(**kwargs):
        collector = kwargs["trajectory"].forward
        assert collector is collectors[0]
        assert kwargs["limits"].max_decisions == 2
        assert kwargs["completion_satisfied"](None) is False
        assert kwargs["stop_requested"](None) is False
        collector.anchor(choice(holder[0]))
        result = original_player(**kwargs)
        if complete:
            holder[0] = observation(champion_raw())
            collector.after_macro()
            assert kwargs["completion_satisfied"](None) is True
            assert kwargs["stop_requested"](None) is True
        return result

    monkeypatch.setitem(namespace, "run_bounded_player_episode", player)
    return h, ready, forward_events, headers, collectors


def test_run_arm_declares_before_input_and_censors_spent_failure_before_closing(monkeypatch):
    h, ready, events, headers, collectors = wired(monkeypatch)
    with pytest.raises(ValueError) as raised:
        h.run()
    assert raised.value is h.error
    assert h.order.index("forward_goal_declaration") < h.order.index("forward_goal_anchor")
    assert h.order.index("forward_goal_anchor") < h.order.index("input")
    assert h.order.index("forward_goal_observation") < h.order.index("capture_failure")
    assert h.order.index("failure_state") < h.order.index("close")
    assert events[-1]["outcome"]["target"] is None
    assert events[-1]["outcome"]["terminal"] == "interrupted"
    assert events[-1]["counters"] == {"actions": 1, "frames": 30, "resources": 0, "macros": 0}
    assert collectors[0].outcome.terminal is ForwardGoalTerminal.INTERRUPTED
    assert len(h.saved) == 1
    assert headers[0]["forward_goal_authority"] == "recording-only-existing-actor"
    assert headers[0]["player_training_plan"]["seed"] == 17
    assert headers[0]["player_training_plan_sha256"] == ready.training_plan.plan_sha256


def test_reporting_error_preserves_first_durable_completion_and_stop_callbacks(monkeypatch):
    h, _, events, _, collectors = wired(monkeypatch, stage="terminal_capture", complete=True)
    with pytest.raises(ValueError) as raised:
        h.run()
    assert raised.value is h.error
    outcome = collectors[0].outcome
    assert outcome.terminal is ForwardGoalTerminal.REACHED
    assert outcome.target[0] == 1.0
    assert len(events) == 3  # No replacement interrupted event after known completion.
    assert events[-1]["outcome"]["observed_goal"] is True
    assert h.order.index("forward_goal_observation") < h.order.index("terminal_capture")
    assert len(h.saved) == 1 and h.order[-2:] == ["close", "abort"]


def test_normal_episode_stop_finalizes_known_failure_before_terminal_capture(monkeypatch):
    h, _, events, _, collectors = wired(monkeypatch, stage="terminal_capture")
    with pytest.raises(ValueError) as raised:
        h.run()
    assert raised.value is h.error
    assert collectors[0].outcome.terminal is ForwardGoalTerminal.STOPPED
    assert events[-1]["outcome"]["target"][0] == 0.0
    assert events[-1]["outcome"]["observed_goal"] is False
    assert len(events) == 3 and len(h.saved) == 1


def test_forward_append_failure_does_not_mask_original_or_prevent_failure_state(monkeypatch):
    h, _, events, _, collectors = wired(monkeypatch, terminal_write_error=True)
    with pytest.raises(ValueError) as raised:
        h.run()
    assert raised.value is h.error
    assert raised.value.__notes__ == ["forward-goal terminal unavailable: OSError"]
    assert collectors[0].outcome is None
    assert len(events) == 2 and len(h.saved) == 1
    assert h.order.index("failure_state") < h.order.index("close")
