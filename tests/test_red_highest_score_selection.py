"""The development setting preserves options, safety, ties and recorded authority."""

import copy
from dataclasses import replace

import pytest
from test_red_live_option_menu import _mixed, _model
from test_red_native_player import setup
from test_red_recorded_selection_authority import records

from pokemon_red_completion.living_dex_option_value import LivingDexOptionValueModel
from pokemon_red_completion.red_live_option_menu import select_red_live_option
from pokemon_red_completion.red_native_player import run_native_continuous_player
from pokemon_red_completion.red_recorded_selection_authority import (
    record_selection_authority,
    replay_selection_authority,
)


@pytest.mark.parametrize("seed", [0, 1, 2, 23, 999])
def test_selects_only_maximum_with_all_options_retained(monkeypatch, seed):
    options = _mixed([])
    scores = tuple(float(i) for i in range(len(options.bindings)))
    monkeypatch.setattr(LivingDexOptionValueModel, "scores", lambda *args: scores)
    choice = select_red_live_option(_model(), options, seed=seed, greedy_selection=True,
                                   allow_earning_exploration=True)
    assert choice.mode.value == "model_greedy"
    assert choice.selected_candidate_index == len(scores) - 1
    assert choice.options is options and choice.scores == scores
    assert choice.probabilities == (0.0,) * (len(scores) - 1) + (1.0,)


def test_exact_ties_are_seeded_and_not_first_option_preference(monkeypatch):
    options = _mixed([])
    scores = (0.0, 4.0, 4.0, 0.0)
    monkeypatch.setattr(LivingDexOptionValueModel, "scores", lambda *args: scores)
    choices = [select_red_live_option(_model(), options, seed=i, greedy_selection=True,
               allow_earning_exploration=True) for i in range(20)]
    assert {c.selected_candidate_index for c in choices} == {1, 2}
    assert all(c.probabilities == (0.0, 0.5, 0.5, 0.0) for c in choices)


@pytest.mark.parametrize("safety", [0.1, 0.99])
def test_recorded_highest_score_and_safety_replay_without_callbacks(safety):
    model, intent, old, calls = records(safety)
    options = old.options
    choice = select_red_live_option(model, options, seed=23, greedy_selection=True,
                                   allow_earning_exploration=True)
    intent["private_selection_authority"] = record_selection_authority(
        options, allow_earning_exploration=True, greedy_selection=True)
    selected = replay_selection_authority(model, intent, choice.public_dict(),
                                          allow_earning_exploration=True)
    assert selected == choice.selected_binding.binding_ref
    assert calls == []
    assert choice.mode.value == ("deterministic_safety" if safety > 0.9 else "model_greedy")
    if safety > 0.9:
        assert choice.public_dict() == old.public_dict()
    else:
        changed = copy.deepcopy(intent)
        del changed["private_selection_authority"]["greedy_selection"]
        with pytest.raises(ValueError):
            replay_selection_authority(model, changed, choice.public_dict(),
                                       allow_earning_exploration=True)


def test_default_omits_setting_and_old_receipt_remains_exact():
    model, intent, choice, _ = records()
    assert "greedy_selection" not in intent["private_selection_authority"]
    again = select_red_live_option(model, choice.options, seed=23,
        allow_earning_exploration=True, greedy_selection=False)
    assert again.public_dict() == choice.public_dict()


@pytest.mark.parametrize("bad", [1, None, "true"])
def test_nonboolean_rejected_before_query(bad):
    with pytest.raises(TypeError):
        select_red_live_option(_model(), _mixed([]), seed=1, greedy_selection=bad)


@pytest.mark.parametrize("partition", ["train", "benchmark", "sealed"])
def test_native_non_development_rejected_before_input(tmp_path, monkeypatch, partition):
    args, executed = setup(tmp_path, monkeypatch)
    args["source"] = dict(args["source"], partition=partition)
    with pytest.raises(ValueError, match="DEVELOPMENT"):
        run_native_continuous_player(**args, greedy_selection=True)
    assert executed == [] and not args["output"].exists()


def test_native_development_records_setting_before_choice(tmp_path, monkeypatch):
    import json
    args, executed = setup(tmp_path, monkeypatch)
    args["source"] = dict(args["source"], partition="development")
    args["limits"] = replace(args["limits"], decisions=1)
    result = run_native_continuous_player(**args, greedy_selection=True)
    root = args["output"] / "episode"
    assert json.loads((root / "plan.json").read_text())["greedy_selection"] is True
    intent = json.loads((root / "step-000/intent.json").read_text())
    assert intent["private_selection_authority"]["greedy_selection"] is True
    assert result["model_decisions"] == 1 and executed
