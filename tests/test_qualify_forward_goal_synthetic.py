"""Independent transition and actor-boundary tests for the controlled toy task."""

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.forward_goal import ForwardGoalTerminal
from pokemon_red_completion.forward_goal_learning import ForwardGoalPrediction

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "qualify_forward_goal_synthetic.py"


@pytest.fixture
def module(monkeypatch):
    name = "_tested_forward_goal_synthetic"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, loaded)
    spec.loader.exec_module(loaded)
    return loaded


def test_optional_restore_really_has_positive_effect_but_extra_total_cost(module):
    task = module.ToyResourceTask(0.8)
    task.act(1)
    assert task.energy == 1.0
    assert task.completed is False
    assert task.counters().public_dict() == {
        "actions": 10,
        "frames": 200,
        "resources": 1,
        "macros": 1,
    }
    task.act(0)
    assert task.completed is True and task.energy == 0.5
    assert task.counters().public_dict() == {
        "actions": 40,
        "frames": 500,
        "resources": 1,
        "macros": 2,
    }
    direct, _ = module.collect_toy(episode=1, energy=0.8, selected=0, partition="development")
    restored, events = module.collect_toy(
        episode=2,
        energy=0.8,
        selected=1,
        partition="development",
    )
    assert direct.target == pytest.approx((1.0, 0.2))
    assert restored.target == pytest.approx((1.0, 0.3833333333333333))
    assert len(events) == 4  # Declaration, first anchor, two actual observations.
    assert [event["kind"] for event in events].count("forward_goal_anchor") == 1


def test_necessary_restore_changes_observed_failure_to_success(module):
    direct, _ = module.collect_toy(episode=3, energy=0.1, selected=0, partition="development")
    restored, _ = module.collect_toy(episode=4, energy=0.1, selected=1, partition="development")
    assert direct.terminal is ForwardGoalTerminal.STOPPED
    assert direct.target == pytest.approx((0.0, 0.2))
    assert restored.terminal is ForwardGoalTerminal.REACHED
    assert restored.target == pytest.approx((1.0, 0.3833333333333333))
    assert direct.counters.macros == 1 and restored.counters.macros == 2


def test_full_energy_allows_goal_but_not_another_restoration(module):
    task = module.ToyResourceTask(1.0)
    with pytest.raises(ValueError):
        task.act(1)
    assert task.counters().actions == 0
    task.act(0)
    assert task.completed is True and task.energy == 0.5
    with pytest.raises(ValueError):
        task.act(0)
    assert task.counters().actions == 30


@pytest.mark.parametrize("selected", [True, -1, 2, "0"])
def test_illegal_action_cannot_spend_resources(module, selected):
    task = module.ToyResourceTask(0.8)
    with pytest.raises(ValueError):
        task.act(selected)
    assert task.counters().public_dict() == {
        "actions": 0,
        "frames": 0,
        "resources": 0,
        "macros": 0,
    }


def test_declaration_and_single_anchor_complete_before_any_action(module, monkeypatch):
    order = []
    original_recorder = module.ForwardGoalRecorder
    original_task = module.ToyResourceTask

    class Recorder(original_recorder):
        def declare(self, **kwargs):
            assert kwargs == {"initial_goal": False}
            result = super().declare(**kwargs)
            order.append("declared")
            return result

        def anchor(self, choice):
            assert order == ["declared"]
            result = super().anchor(choice)
            order.append("anchored")
            return result

    class Task(original_task):
        def act(self, selected):
            assert order[:2] == ["declared", "anchored"]
            order.append(("act", selected))
            return super().act(selected)

    monkeypatch.setattr(module, "ForwardGoalRecorder", Recorder)
    monkeypatch.setattr(module, "ToyResourceTask", Task)
    outcome, events = module.collect_toy(
        episode=5,
        energy=0.8,
        selected=1,
        partition="development",
    )
    assert order == ["declared", "anchored", ("act", 1), ("act", 0)]
    assert events[1]["choice"]["context"] == [0.8]  # Not restored energy or future success.
    assert outcome.choice.context == (0.8,)
    assert outcome.choice.candidates == ((0.0,), (1.0,))


@pytest.mark.parametrize("selected,cost", [(0, 0.2), (1, 0.18333333333333335)])
def test_interruption_reads_no_post_action_goal_and_preserves_prefix_only(
    module,
    monkeypatch,
    selected,
    cost,
):
    original = module.ToyResourceTask

    class UnreadableAfterInput(original):
        def __getattribute__(self, name):
            if name == "completed" and object.__getattribute__(self, "actions") > 0:
                raise AssertionError("interrupted goal must not be inspected")
            return super().__getattribute__(name)

    monkeypatch.setattr(module, "ToyResourceTask", UnreadableAfterInput)
    outcome, events = module.collect_toy(
        episode=6,
        energy=0.8,
        selected=selected,
        partition="train",
        interrupt_after_first_action=True,
    )
    assert outcome.terminal is ForwardGoalTerminal.INTERRUPTED
    assert outcome.target is None and outcome.observed_goal is None
    assert outcome.counters.macros == 1
    assert outcome.public_dict()["prefix_cost"] == pytest.approx(cost)
    assert len(events) == 3 and events[-1]["goal"] is None


@pytest.mark.parametrize("selected,expected", [(0, (1.0, 0.0)), (1, (0.0, 1.0))])
def test_forced_development_probes_report_truthful_one_hot_behavior(module, selected, expected):
    outcome, _ = module.collect_toy(
        episode=7,
        energy=0.8,
        selected=selected,
        partition="development",
    )
    assert outcome.choice.probabilities == expected
    with pytest.raises(ValueError, match="train-only"):
        module.fit_forward_goal((outcome,))


def test_every_training_anchor_including_censored_one_uses_actual_declared_rng(module, monkeypatch):
    original_fit = module.fit_forward_goal
    seeds, calls, observed_rows = [], [], []

    class AlternatingRandom:
        def __init__(self, seed):
            seeds.append(seed)

        def randrange(self, n):
            assert n == 2
            result = len(calls) % 2
            calls.append(result)
            return result

    def fit(rows, **kwargs):
        observed_rows.extend(rows)
        return original_fit(rows, **kwargs)

    monkeypatch.setattr(module.random, "Random", AlternatingRandom)
    monkeypatch.setattr(module, "fit_forward_goal", fit)
    module.run_qualification()
    assert seeds == [2026090901]
    assert len(calls) == len(observed_rows) == 129
    assert [row.choice.selected_index for row in observed_rows] == calls
    assert all(row.choice.probabilities == (0.5, 0.5) for row in observed_rows)
    assert observed_rows[-1].choice.selected_index == 0  # Not forced restoration.
    assert observed_rows[-1].censored is True


def test_qualification_and_test_contexts_never_enter_fit_and_actor_sees_only_start_inputs(
    module,
    monkeypatch,
):
    original_fit = module.fit_forward_goal
    original_predict = module.ForwardGoalModel.predict
    fit_calls, prediction_calls, model_hashes = [], [], []

    def fit(rows, **kwargs):
        rows = tuple(rows)
        fit_calls.append(rows)
        result = original_fit(rows, **kwargs)
        model_hashes.append(result.model.sha256)
        return result

    def predict(self, **kwargs):
        assert set(kwargs) == {"plan", "context_names", "context", "candidate_names", "candidates"}
        assert kwargs["context_names"] == ("energy_fraction",)
        assert kwargs["candidate_names"] == ("restore",)
        assert kwargs["candidates"] == ((0.0,), (1.0,))
        assert len(kwargs["context"]) == 1
        prediction_calls.append(kwargs["context"][0])
        assert self.sha256 == model_hashes[0]
        return original_predict(self, **kwargs)

    monkeypatch.setattr(module, "fit_forward_goal", fit)
    monkeypatch.setattr(module.ForwardGoalModel, "predict", predict)
    report = module.run_qualification()
    assert len(fit_calls) == 1
    rows = fit_calls[0]
    assert len(rows) == 129
    assert {row.choice.context[0] for row in rows} == {0.1, 0.2, 0.8, 0.9}
    assert {row.choice.partition for row in rows} == {"train"}
    assert set(module.TRAIN_ENERGIES).isdisjoint(module.QUALIFICATION_ENERGIES)
    assert set(module.TRAIN_ENERGIES).isdisjoint(module.TEST_ENERGIES)
    assert set(module.QUALIFICATION_ENERGIES).isdisjoint(module.TEST_ENERGIES)
    assert prediction_calls == [
        *module.QUALIFICATION_ENERGIES,
        *module.TEST_ENERGIES,
        *module.UNSUPPORTED_ENERGIES,
    ]
    assert report["training"]["model_sha256"] == model_hashes[0]


def test_controlled_result_counts_and_literal_success_costs(module):
    report = module.run_qualification()
    assert report["scope"] == "controlled_synthetic_not_pokemon_or_real_calibration"
    assert report["qualification"]["passed"] is True
    training = report["training"]
    assert training["settled_examples"] == 128 and training["censored_examples"] == 1
    assert training["recorded_roots"] == training["settled_roots"] == 4
    assert training["distinct_selected_inputs"] == 8
    assert report["qualification"]["completion_max_error"] <= 0.08
    assert report["qualification"]["cost_max_error"] <= 0.015
    rows = report["tests"]
    assert len(rows) == 11
    assert [row["selected_option"] for row in rows] == [1, 1, 1, 1, 0, 0, 0, 0, None, None, None]
    assert [row["supported"] for row in rows] == [True] * 8 + [False] * 3
    for row in rows[:4]:
        assert row["observed_target"] == pytest.approx([1.0, 0.3833333333333333])
    for row in rows[4:8]:
        assert row["observed_target"] == pytest.approx([1.0, 0.2])
    assert all(row["regret_against_known_toy_optimum"] is False for row in rows[:8])
    assert all(row["observed_target"] is None for row in rows[8:])
    assert report["red_training_rows_created"] == report["red_authority_promotions"] == 0
    assert report["red_model_changed"] is False and report["no_red_inputs"] is True


def test_poisoned_test_predictions_control_actual_action_not_oracle(module, monkeypatch):
    original = module.predict

    def deliberately_wrong(model, energy, plan=module.PLAN):
        if energy in module.TEST_ENERGIES:
            return (ForwardGoalPrediction(1.0, 0.1), ForwardGoalPrediction(0.0, 0.5))
        return original(model, energy, plan)

    monkeypatch.setattr(module, "predict", deliberately_wrong)
    report = module.run_qualification()
    assert report["qualification"]["passed"] is True
    assert [row["selected_option"] for row in report["tests"][:8]] == [0] * 8
    for row in report["tests"][:4]:
        assert row["observed_target"] == pytest.approx([0.0, 0.2])
        assert row["regret_against_known_toy_optimum"] is True


def test_abstention_is_not_replaced_with_hindsight_action(module, monkeypatch):
    monkeypatch.setattr(module, "select_forward_goal", lambda *args, **kwargs: None)
    report = module.run_qualification()
    assert report["qualification"]["passed"] is True
    assert all(
        row["selected_option"] is None and row["observed_target"] is None for row in report["tests"]
    )


@pytest.mark.parametrize("failed_head", ["completion", "cost"])
def test_bad_error_bounds_disable_all_test_actions(module, monkeypatch, failed_head):
    original_collect = module.collect_toy
    original_predict = module.predict
    collected = []

    def collect(**kwargs):
        collected.append(kwargs["episode"])
        return original_collect(**kwargs)

    def inaccurate(model, energy, plan=module.PLAN):
        predictions = original_predict(model, energy, plan)
        return tuple(
            ForwardGoalPrediction(
                0.5 if failed_head == "completion" else prediction.completion,
                99.0 if failed_head == "cost" else prediction.cost,
            )
            for prediction in predictions
        )

    monkeypatch.setattr(module, "collect_toy", collect)
    monkeypatch.setattr(module, "predict", inaccurate)
    report = module.run_qualification()
    assert report["qualification"]["passed"] is False
    other_head = "cost" if failed_head == "completion" else "completion"
    bound = 0.015 if other_head == "cost" else 0.08
    assert report["qualification"][f"{other_head}_max_error"] <= bound
    assert all(
        row["selected_option"] is None and row["observed_target"] is None for row in report["tests"]
    )
    assert all(episode < 2000 for episode in collected)
    assert report["red_authority_promotions"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"max_actions": 101},
        {"max_frames": 999},
        {"max_resources": 0},
        {"max_macros": 3},
        {"continuation_sha256": "e" * 64},
    ],
)
def test_changed_budget_or_continuation_is_not_qualified_support(module, change):
    assert module.supported(0.1, replace(module.PLAN)) is True
    assert module.supported(0.1, replace(module.PLAN, **change)) is False


@pytest.mark.parametrize("energy", [-0.1, 0.35, 0.5, 0.65, 1.0, 1.1])
def test_unqualified_or_unavailable_contexts_have_no_support(module, energy):
    assert module.supported(energy) is False


def test_cli_emits_controlled_json_without_files_or_red_authority(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        check=True,
        text=True,
        capture_output=True,
    )
    report = json.loads(result.stdout)
    assert report["schema"] == "pokemon.synthetic.forward-goal-qualification.v1"
    assert report["red_authority_promotions"] == report["red_training_rows_created"] == 0
    assert report["qualification"]["passed"] is True
    assert list(tmp_path.iterdir()) == []
