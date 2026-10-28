from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from test_red_trainer_budgeted_fit import case
from test_red_trainer_retention import unit_head

from pokemon_red_completion.red_trainer_budgeted_fit import (
    RegretBudget,
    fit_budgeted_head,
    pairwise_loss_gradient,
    selected_regret,
)
from pokemon_red_completion.red_trainer_joint_ranking import (
    ranking_guards,
    solve_curvature_direction,
    solve_direction,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel
from pokemon_red_completion.red_trainer_ranking_diagnostics import score_jacobian


def fit(model, fresh, old, budget=0, epochs=120, rate=0.05, offset=0):
    return fit_budgeted_head(
        model,
        fresh,
        old,
        (RegretBudget("old", old, budget, offset),),
        epochs=epochs,
        learning_rate=rate,
        objective="pairwise_regret",
        retention_replay="unique_budget_cases_v1",
        update_rule="joint_ranking_v1",
    )


def test_large_wrong_margin_and_tiny_old_margin_correct_actual_choice():
    model = TrainerHeadModel(
        "three", ("x", "y", "z"), np.eye(3), np.zeros(3), np.array([-10.0, 10.0, 0.0001]), 1
    )
    fresh = TrainerHeadExample(((1, 0, 0), (0, 1, 0)), (0,), mean_returns=(4, 0))
    old = TrainerHeadExample(((0, 0, 1), (0, 0, -1)), (0,), mean_returns=(2, 0))
    original = model.to_dict()
    child, r = fit(model, (fresh,), (old,))
    assert selected_regret(child, (fresh,)) == selected_regret(child, (old,)) == 0
    assert model.to_dict() == original and r["accepted_steps"] > 0
    assert len(r["checkpoints"]) == len(r["history"]) == r["accepted_steps"] + 1
    assert all(h["feasible"] for h in r["history"])


def test_shared_gradient_interference_is_not_the_update_direction():
    model = TrainerHeadModel(
        "two", ("x", "y"), np.eye(2) * 0.1, np.zeros(2), np.array([-0.5, 0.01]), 1
    )
    first = TrainerHeadExample(((1, 0), (0, 0)), (0,), mean_returns=(1, 0))
    second = TrainerHeadExample(((-1, 1), (0, 0)), (0,), mean_returns=(100, 0))
    # The second lesson is already right but its large loss gradient harms first.
    jac = score_jacobian(model, (1, 0)) - score_jacobian(model, (0, 0))
    assert jac @ -pairwise_loss_gradient(model, (first, second))[1] < 0
    child, r = fit(model, (first, second), (second,))
    assert selected_regret(child, (first, second)) == 0
    assert all(h["budgets"]["old"] == 0 for h in r["history"])


def test_old_wrong_choice_is_free_to_improve():
    row = case()
    child, r = fit(unit_head(), (row,), (row,), budget=2)
    assert selected_regret(child, (row,)) == 0 and r["accepted_steps"] > 0


def test_impossible_local_system_is_bounded_not_global_certificate():
    row = case()
    old = replace(row, mean_returns=tuple(reversed(row.mean_returns)))
    child, r = fit(unit_head(), (row,), (old,), budget=0.3, offset=0.3, epochs=20)
    assert selected_regret(child, (old,)) == 0 and selected_regret(child, (row,)) == 2
    assert len(r["steps"]) <= 20
    assert all(len(s["attempts"]) <= 8 for s in r["steps"])
    assert "not global" in r["guard_scope"]


def test_impossible_initial_offset_returns_no_candidate():
    child, r = fit(unit_head(), (case(),), (case(),), budget=1, offset=3)
    assert child is None and r["stop_reason"] == "initial_budget_infeasible"
    assert not r["steps"]


def test_solver_zero_derivative_and_infeasible_are_distinct():
    step, r = solve_direction(np.zeros(2), np.zeros((0, 2)), np.zeros(0), 0.1, 1)
    assert step is None and r["reason"] == "no_useful_local_direction"
    step, r = solve_direction(np.ones(2), np.zeros((1, 2)), np.ones(1), 0.1, 1)
    assert step is None and r["status"] == 2 and r["local_only"]


def test_solver_feasible_gain_and_bound_residuals():
    j = np.array([1.0, 1.0])
    a = np.array([[1.0, -1.0]])
    step, r = solve_direction(j, a, np.array([0.0]), 0.1, 1)
    assert np.max(np.abs(step)) <= 0.1 + 1e-9 and np.min(a @ step) >= -1e-9
    assert r["linear_violation"] <= 1e-7 and j @ step >= 0.18 - 1e-9


@pytest.mark.parametrize("seed", range(5))
def test_split_direction_matches_original_minimum_l1_problem(seed):
    from scipy.optimize import linprog

    rng = np.random.default_rng(seed)
    n = 12
    j, a = rng.normal(size=n), rng.normal(size=(8, n))
    b = -rng.uniform(0.01, 0.2, size=8)
    step, report = solve_direction(j, a, b, 0.1, 0.5)
    assert step is not None
    original = linprog(
        np.r_[np.zeros(n), np.ones(n)],
        A_ub=np.block(
            [
                [-a, np.zeros_like(a)],
                [-j[None, :], np.zeros((1, n))],
                [np.eye(n), -np.eye(n)],
                [-np.eye(n), -np.eye(n)],
            ]
        ),
        b_ub=np.r_[-b, -report["required_gain"], np.zeros(2 * n)],
        bounds=[(-0.1, 0.1)] * n + [(0, 0.1)] * n,
        method="highs",
    )
    assert original.success
    assert np.abs(step).sum() == pytest.approx(original.fun, abs=1e-8)
    assert report["linear_violation"] <= 1e-7


def test_control_width_solver_avoids_parameter_count_constraint_rows(monkeypatch):
    from pokemon_red_completion import red_trainer_joint_ranking as m

    actual = m.linprog
    shapes = []

    def capture(*args, **kwargs):
        shapes.append(kwargs["A_ub"].shape)
        return actual(*args, **kwargs)

    monkeypatch.setattr(m, "linprog", capture)
    n = 4576
    step, report = solve_direction(np.ones(n), np.ones((2, n)), np.zeros(2), 0.05, 1)
    assert step is not None and report["minimum_step_status"] == 0
    assert shapes == [(2, n), (3, 2 * n)]


def test_solver_failure_is_not_reported_as_infeasibility(monkeypatch):
    from pokemon_red_completion import red_trainer_joint_ranking as m

    monkeypatch.setattr(
        m,
        "linprog",
        lambda *a, **k: SimpleNamespace(status=1, message="time limit", nit=4, success=False),
    )
    step, r = solve_direction(np.ones(2), np.zeros((0, 2)), np.zeros(0), 0.1, 1)
    assert step is None and r["status"] == 1


def test_curvature_correction_resolves_safe_linear_but_unsafe_actual_direction():
    j, a, b = np.array([1.0, 0.0]), np.array([[0.0, 1.0]]), np.zeros(1)

    def actual(d):
        return np.array([d[1] - d[0] ** 2])

    plain, _ = solve_direction(j, a, b, 0.1, 1)
    assert actual(plain)[0] < 0 <= (a @ plain)[0]
    step, report = solve_curvature_direction(j, a, b, 0.1, 1, actual)
    assert actual(step)[0] >= 0 and j @ step >= 0.09 - 1e-9
    assert 1 < len(report["curvature_rounds"]) <= 4
    assert report["linear_violation"] <= 1e-7


def test_curvature_solver_is_bounded_and_does_not_admit_impossible_guard():
    calls = []

    def impossible(d):
        calls.append(d)
        return np.array([-1.0])

    step, report = solve_curvature_direction(
        np.ones(2), np.array([[0.0, 1.0]]), np.zeros(1), 0.1, 1, impossible
    )
    assert step is None and len(calls) <= 4 and report["status"] == 2


def test_curvature_mode_preserves_original_budget_with_neural_learning():
    row = case()
    child, report = fit_budgeted_head(
        unit_head(),
        (row,),
        (row,),
        (RegretBudget("old", (row,), 2),),
        epochs=60,
        learning_rate=0.05,
        update_rule="joint_ranking_curvature_v1",
    )
    assert selected_regret(child, (row,)) == 0
    assert report["update_rule"] == "joint_ranking_curvature_v1"
    assert all(h["feasible"] for h in report["history"])
    assert all(
        len(a["solver"]["curvature_rounds"]) <= 4 for s in report["steps"] for a in s["attempts"]
    )


def test_ties_have_no_worse_guard_and_already_optimal_stops():
    row = replace(case(), mean_returns=(2, 2))
    a, b, labels = ranking_guards(unit_head(), (row,))
    assert not len(a) and not len(b) and not labels
    child, r = fit(unit_head(), (row,), (row,))
    assert child is not None and not r["steps"] and r["stop_reason"] == "all_fresh_choices_optimal"


def test_exact_nonlinear_budget_rejects_bad_solver_step(monkeypatch):
    from pokemon_red_completion import red_trainer_joint_ranking as m

    row = case()
    old = replace(row, mean_returns=tuple(reversed(row.mean_returns)))
    monkeypatch.setattr(m, "solve_direction", lambda j, *args: (j * 1e6, {"status": 0}))
    child, r = fit(unit_head(), (row,), (old,))
    assert selected_regret(child, (old,)) == 0
    assert all(h["feasible"] for h in r["history"])


@pytest.mark.parametrize("radius", [0, -1, float("nan"), float("inf")])
def test_invalid_solver_radius_rejected(radius):
    with pytest.raises(ValueError):
        solve_direction(np.ones(2), np.zeros((0, 2)), np.zeros(0), radius, 1)


@pytest.mark.parametrize("mode", ["joint_ranking_v1", "joint_ranking_curvature_v1"])
def test_explicit_initial_recovery_withholds_infeasible_private_checkpoints(mode):
    model = TrainerHeadModel(
        "three", ("x", "y", "z"), np.eye(3), np.zeros(3), np.array([-10.0, 10.0, 0.0001]), 1
    )
    fresh = TrainerHeadExample(((1, 0, 0), (0, 1, 0)), (0,), mean_returns=(4, 0))
    old = TrainerHeadExample(((0, 0, 1), (0, 0, -1)), (0,), mean_returns=(2, 0))
    budgets = (RegretBudget("restore", (fresh,), 0), RegretBudget("stable", (old,), 0))
    original = model.to_dict()
    rejected, initial = fit_budgeted_head(model, (fresh,), (old,), budgets,
        epochs=120, learning_rate=0.05, update_rule=mode)
    assert rejected is None and initial["stop_reason"] == "initial_budget_infeasible"
    child, receipt = fit_budgeted_head(model, (fresh,), (old,), budgets,
        epochs=120, learning_rate=0.05, update_rule=mode, allow_initial_infeasibility=True)
    assert child is not None and model.to_dict() == original
    assert selected_regret(child, (fresh,)) == selected_regret(child, (old,)) == 0
    assert receipt["initial_feasible"] is False and receipt["private_infeasible_checkpoints"] > 1
    chosen = receipt["history"][receipt["selected_epoch"]]
    assert chosen["feasible"] and receipt["feasible_checkpoints"] > 0
    assert all(h["budgets"]["stable"] == 0 for h in receipt["history"])
    assert all(not h["selected"] for h in receipt["history"] if not h["feasible"])
    excess = [h["budgets"]["restore"] for h in receipt["history"]]
    assert all(b <= a for a, b in zip(excess, excess[1:]))


def test_initial_recovery_never_returns_impossible_offset():
    row = case()
    child, receipt = fit_budgeted_head(unit_head(), (row,), (row,),
        (RegretBudget("impossible", (row,), 1, offset=3),), epochs=20,
        learning_rate=0.05, update_rule="joint_ranking_v1", allow_initial_infeasibility=True)
    assert child is None and receipt["feasible_checkpoints"] == 0
    assert receipt["selected_epoch"] is None and len(receipt["steps"]) <= 20


def test_initial_recovery_rejects_a_new_budget_violation(monkeypatch):
    from pokemon_red_completion import red_trainer_joint_ranking as module
    model = TrainerHeadModel("three", ("x", "y", "z"), np.eye(3), np.zeros(3), np.array([-1., 1., .1]), 1)
    fresh = TrainerHeadExample(((1, 0, 0), (0, 1, 0)), (0,), mean_returns=(4, 0))
    old = TrainerHeadExample(((0, 0, 1), (0, 0, -1)), (0,), mean_returns=(2, 0))
    bad = np.zeros(model.weights1.size + model.bias1.size + model.weights2.size)
    bad[-3], bad[-1] = 5., -2.
    monkeypatch.setattr(module, "solve_direction", lambda *a, **k: (bad, {"forced_test_step": True}))
    child, receipt = fit_budgeted_head(model, (fresh,), (old,),
        (RegretBudget("restore", (fresh,), 0), RegretBudget("stable", (old,), 0)),
        epochs=2, learning_rate=.05, update_rule="joint_ranking_v1", allow_initial_infeasibility=True)
    assert child is None and not any(h["feasible"] for h in receipt["history"])
    assert all(not attempt["accepted"] for step in receipt["steps"] for attempt in step["attempts"])
    assert any("stable" in attempt["violated"] for step in receipt["steps"] for attempt in step["attempts"])


@pytest.mark.parametrize("flag,mode", [(1, "joint_ranking_v1"), (None, "joint_ranking_v1"), (True, "adam"), (True, "projected_budget_v1")])
def test_initial_recovery_flag_is_explicit_and_scoped(flag, mode):
    with pytest.raises(ValueError, match="feasibility recovery"):
        fit_budgeted_head(unit_head(), (case(),), (case(),), (RegretBudget("a", (case(),), 2),),
            epochs=1, update_rule=mode, allow_initial_infeasibility=flag)
