"""Constraint-aware optimization tests use synthetic measured outcomes only."""

from dataclasses import replace

import numpy as np
import pytest
from test_red_trainer_budgeted_fit import case
from test_red_trainer_retention import unit_head

from pokemon_red_completion.red_trainer_budgeted_fit import (
    RegretBudget,
    fit_budgeted_head,
    selected_regret,
)
from pokemon_red_completion.red_trainer_constrained_fit import (
    project_displacement,
    worse_choice_halfspaces,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel


def fit(model, terminal, anchors, budgets, *, epochs=120, rate=0.005):
    return fit_budgeted_head(
        model,
        terminal,
        anchors,
        budgets,
        epochs=epochs,
        learning_rate=rate,
        objective="pairwise_regret",
        retention_replay="unique_budget_cases_v1",
        update_rule="projected_budget_v1",
    )


def test_compatible_improvement_preserves_separate_old_decision():
    model = TrainerHeadModel(
        "three", ("x", "y", "z"), np.eye(3) * 0.1, np.zeros(3), np.array([0.1, 0.2, 1.0]), 1
    )
    terminal = TrainerHeadExample(((1, 0, 0), (0, 1, 0)), (0,), mean_returns=(4, 0))
    old = TrainerHeadExample(((0, 0, 1), (0, 0, -1)), (0,), mean_returns=(2, 0))
    original = model.to_dict()
    child, receipt = fit(model, (terminal,), (old,), (RegretBudget("old", (old,), 0),))
    assert selected_regret(child, (terminal,)) == 0 and selected_regret(child, (old,)) == 0
    assert model.to_dict() == original and receipt["accepted_steps"] > 0
    assert all(h["feasible"] and h["budgets"]["old"] == 0 for h in receipt["history"])


def test_old_wrong_choice_may_improve_and_is_not_locked():
    row = case()
    model = unit_head()
    before = model.predict_index(row.candidate_vectors)
    child, receipt = fit(model, (row,), (row,), (RegretBudget("old", (row,), 2),))
    assert child.predict_index(row.candidate_vectors) != before
    assert selected_regret(child, (row,)) == 0 and receipt["accepted_steps"] > 0


def test_coupled_feasible_constraints_allow_learning_without_forgetting():
    model = TrainerHeadModel(
        "two", ("x", "y"), np.eye(2) * 0.1, np.zeros(2), np.array([-0.5, 0.01]), 1
    )
    terminal = TrainerHeadExample(((1, 0), (0, 0)), (0,), mean_returns=(100, 0))
    old = TrainerHeadExample(((0.99, 0.01), (1, 0)), (0,), mean_returns=(2, 0))
    child, receipt = fit(model, (terminal,), (old,), (RegretBudget("old", (old,), 0),), rate=0.2)
    assert selected_regret(child, (terminal,)) == 0 and selected_regret(child, (old,)) == 0
    assert receipt["accepted_steps"] > 0
    assert all(h["budgets"]["old"] == 0 for h in receipt["history"])


def test_initial_impossible_budget_stops_without_any_update():
    row = case()
    child, receipt = fit(unit_head(), (row,), (row,), (RegretBudget("bad", (row,), -1),))
    assert child is None and receipt["steps"] == []
    assert receipt["stop_reason"] == "initial_budget_infeasible"
    assert receipt["feasible_checkpoints"] == 0


def test_incompatible_new_choice_never_crosses_numeric_budget():
    row = case()
    old = replace(row, mean_returns=tuple(reversed(row.mean_returns)))
    child, receipt = fit(
        unit_head(), (row,), (old,), (RegretBudget("old", (old,), 0.3, 0.3),), rate=0.1
    )
    assert selected_regret(child, (old,)) == 0 and selected_regret(child, (row,)) == 2
    assert all(h["budgets"]["old"] <= 0.3 for h in receipt["history"])
    assert len(receipt["steps"]) <= 120
    assert all(len(s["attempts"]) <= 13 and s["projection_passes"] <= 10 for s in receipt["steps"])
    assert receipt["stop_reason"] in ("epoch_limit", "no_feasible_descent_step")


def test_actual_nonlinear_check_is_authoritative_when_projection_is_wrong(monkeypatch):
    from pokemon_red_completion import red_trainer_constrained_fit as module

    monkeypatch.setattr(module, "project_displacement", lambda step, matrix, lower: (step * 1e8, 1))
    row = case()
    row = replace(row, mean_returns=tuple(50 * v for v in row.mean_returns))
    old = replace(row, mean_returns=tuple(reversed(row.mean_returns)))
    old = replace(old, mean_returns=tuple(v / 50 for v in old.mean_returns))
    child, receipt = fit(unit_head(), (row,), (old,), (RegretBudget("old", (old,), 0),), rate=0.1)
    assert selected_regret(child, (old,)) == 0
    assert all(h["feasible"] for h in receipt["history"])
    assert any(s["projection_pairs"] for s in receipt["steps"])
    assert receipt["stop_reason"] == "no_feasible_descent_step"


def test_halfspace_jacobian_matches_score_margin_finite_difference():
    model = unit_head()
    row = case()
    chosen = model.predict_index(row.candidate_vectors)
    old = replace(row, mean_returns=tuple(2.0 if i == chosen else 0.0 for i in range(2)))
    jac, lower = worse_choice_halfspaces(model, (old,))
    assert len(lower) == 1
    packed = np.concatenate((model.weights1.ravel(), model.bias1, model.weights2))
    n = model.weights1.size
    w = model.bias1.size

    def margin(p):
        m = replace(
            model,
            weights1=p[:n].reshape(model.weights1.shape),
            bias1=p[n : n + w],
            weights2=p[n + w :],
        )
        scores = m.scores(row.candidate_vectors)
        return scores[chosen] - scores[1 - chosen]

    for i in range(len(packed)):
        step = np.zeros_like(packed)
        step[i] = 1e-6
        assert jac[0, i] == pytest.approx(
            (margin(packed + step) - margin(packed - step)) / 2e-6, abs=1e-8
        )


def test_ties_better_alternatives_and_padding_are_not_protected_as_worse():
    model = unit_head()
    row = case()
    chosen = model.predict_index(row.candidate_vectors)
    tied = replace(row, mean_returns=(2, 2))
    assert worse_choice_halfspaces(model, (tied,))[0].shape[0] == 0
    better = replace(row, mean_returns=tuple(0 if i == chosen else 2 for i in range(2)))
    assert worse_choice_halfspaces(model, (better,))[0].shape[0] == 0
    old = replace(row, mean_returns=tuple(2 if i == chosen else 0 for i in range(2)))
    triple = TrainerHeadExample(((0, 0), (0.1, 0.2), (0.3, 0.4)), (0, 1, 2), mean_returns=(0, 0, 0))
    jac, lower = worse_choice_halfspaces(model, (old, triple))
    assert jac.shape[0] == len(lower) == 1


def test_projection_is_bounded_and_does_not_modify_its_input():
    step = np.array([-1.0, -1.0])
    original = step.copy()
    projected, passes = project_displacement(step, np.eye(2), np.zeros(2))
    np.testing.assert_array_equal(step, original)
    assert np.all(projected >= 0) and passes <= 10


@pytest.mark.parametrize("rate", [float("nan"), float("inf"), 0, -1])
def test_nonfinite_or_invalid_rate_rejected(rate):
    with pytest.raises(ValueError, match="schedule"):
        fit(unit_head(), (case(),), (case(),), (RegretBudget("old", (case(),), 2),), rate=rate)


def test_default_and_explicit_adam_are_identical():
    args = (unit_head(), (case(),), (case(),), (RegretBudget("old", (case(),), 2),))
    a, ra = fit_budgeted_head(*args, epochs=3)
    b, rb = fit_budgeted_head(*args, epochs=3, update_rule="adam")
    assert a.to_dict() == b.to_dict() and ra == rb


def test_invalid_update_rule_is_not_silently_ignored():
    with pytest.raises(ValueError, match="update rule"):
        fit_budgeted_head(
            unit_head(),
            (case(),),
            (case(),),
            (RegretBudget("old", (case(),), 2),),
            update_rule="typo",
        )
