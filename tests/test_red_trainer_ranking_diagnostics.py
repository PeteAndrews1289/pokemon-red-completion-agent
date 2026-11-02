"""Synthetic diagnostics only: no private inputs, fitting or native game."""

from dataclasses import replace

import numpy as np
import pytest

from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel
from pokemon_red_completion.red_trainer_ranking_diagnostics import (
    inspect_rankings,
    nullspace_component_ratio,
    score_jacobian,
)


def head():
    return TrainerHeadModel(
        "test", ("x", "y"), np.eye(2) * 0.2, np.zeros(2), np.array([1.0, 2.0]), 1
    )


def example(vectors=((1.0, 0.0), (0.0, 1.0)), values=(2.0, 0.0)):
    return TrainerHeadExample(vectors, (int(np.argmax(values)),), mean_returns=values)


def test_partial_inventory_pair_collision_is_not_missed():
    old = example(((0.0, 1.0), (1.0, 0.0), (-1.0, -1.0)), (3.0, 1.0, 0.0))
    report = inspect_rankings(head(), (example(),), {"old": (old,)})
    alias = report["cases"][0]["exact_pair_aliases"]
    assert len(alias) == 1 and alias[0]["old_return_advantage_for_new_best"] == -2
    assert alias[0]["old_selected_in_pair"]


def test_another_old_winner_does_not_assert_pair_is_binding():
    old = example(((0.0, 1.0), (1.0, 0.0), (1.0, 1.0)), (3.0, 1.0, 4.0))
    report = inspect_rankings(head(), (example(),), {"old": (old,)})
    assert not report["cases"][0]["exact_pair_aliases"][0]["old_selected_in_pair"]


def test_tied_measured_returns_are_not_reported_as_wrong_choice():
    row = example(values=(2.0, 2.0))
    report = inspect_rankings(head(), (row,), {"old": (row,)})
    cell = report["cases"][0]
    assert cell["chosen"] == cell["best"]
    assert cell["desired_margin"] == 0 and cell["exact_pair_aliases"] == []
    assert report["weakest_old_margins"] == []
    assert cell["old_margin_nullspace"]["ratio"] == 0


def test_diagnostics_do_not_modify_parameters_or_inputs():
    model, row = head(), example()
    before = model.to_dict()
    report = inspect_rankings(model, (row,), {"old": (row, row)})
    assert before == model.to_dict()
    assert report["parameter_updates"] == 0
    assert report["unique_replay_cases"] == 1
    assert report["retained_budgets"]["old"]["cases"] == 2


def test_score_jacobian_matches_finite_differences():
    model = head()
    packed = np.r_[model.weights1.ravel(), model.bias1, model.weights2]
    vector = (0.2, -0.3)
    analytic = score_jacobian(model, vector)
    for i in range(len(packed)):
        delta = np.zeros_like(packed)
        delta[i] = 1e-6
        scores = []
        for p in (packed + delta, packed - delta):
            trial = replace(model, weights1=p[:4].reshape(2, 2), bias1=p[4:6], weights2=p[6:])
            scores.append(trial.scores((vector,))[0])
        assert analytic[i] == pytest.approx((scores[0] - scores[1]) / 2e-6, abs=1e-9)


def test_tangent_freedom_is_a_linear_algebra_result_not_a_new_actor():
    row = np.array([[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    assert nullspace_component_ratio(row, np.array([0.0, 1.0, 0.0]))["ratio"] == 1
    assert nullspace_component_ratio(row, np.array([1.0, 0.0, 0.0]))["ratio"] < 1e-12
    assert nullspace_component_ratio(row, np.array([1.0, 1.0, 0.0]))["ratio"] == pytest.approx(
        2**-0.5
    )
    assert nullspace_component_ratio(row, np.zeros(3))["ratio"] == 0


@pytest.mark.parametrize(
    "matrix,vector",
    [
        (np.zeros((1, 3)), np.zeros(2)),
        (np.array([[np.nan, 0.0]]), np.zeros(2)),
        (np.zeros((1, 2)), np.array([np.inf, 0.0])),
    ],
)
def test_invalid_tangent_values_rejected(matrix, vector):
    with pytest.raises(ValueError, match="tangent"):
        nullspace_component_ratio(matrix, vector)


def test_missing_groups_rejected():
    with pytest.raises(ValueError, match="inventories"):
        inspect_rankings(head(), (example(),), {"empty": ()})


def test_shared_training_signal_can_oppose_one_useful_ranking():
    weak = example(values=(2.0, 0.0))
    strong_opposite = example(values=(0.0, 20.0))
    neutral = example(values=(0.0, 0.0))
    report = inspect_rankings(head(), (weak, strong_opposite), {"old": (neutral,)})
    rates = report["cases"][0]["desired_margin_derivatives"]
    assert rates["negative_individual_gradients"][0] > 0
    assert rates["negative_fresh_gradient"] < 0
