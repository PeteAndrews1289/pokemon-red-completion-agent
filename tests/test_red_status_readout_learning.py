from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from test_red_status_retention_fit import inputs

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES
from pokemon_red_completion.red_status_readout_learning import (
    fit_readout,
    prepare_readout,
    representation_check,
)


def problem_inputs():
    frozen, initial, negative = inputs()
    w = np.zeros_like(initial.move.weights1)
    w[BALANCED_STATUS_NAMES.index("choice.status"), 0] = 1.
    w[BALANCED_STATUS_NAMES.index("choice.player_hp"), 1] = 1.
    initial = replace(initial, move=replace(initial.move, weights1=w,
                                            weights2=np.asarray([-.2, 0.])))
    positive = deepcopy(negative)
    positive["capture_id"] = "positive"
    positive["vectors"][1][BALANCED_STATUS_NAMES.index("choice.player_hp")] = 1.
    positive["returns"] = [0., 2.]
    positive["timing_returns"]["2"] = [2., 2., 2.]
    return frozen, initial, [[negative], [positive]]


def test_output_update_learns_without_touching_hidden_or_frozen_heads():
    frozen, initial, groups = problem_inputs()
    p = prepare_readout(groups, initial, frozen)
    diagnostic = representation_check(p)
    assert diagnostic["individually_correctable_errors"] == 1
    assert not diagnostic["joint_learnability_claim"]
    candidate, report = fit_readout(groups, initial, frozen)
    assert report["solver_result"]["success"]
    assert report["solver_result"]["stationarity_residual"] < 1e-5
    assert report["retention_regressions"] == 0
    assert candidate.move.predict_index(groups[0][0]["vectors"]) == 0
    assert candidate.move.predict_index(groups[1][0]["vectors"]) == 1
    assert np.array_equal(candidate.move.weights1, initial.move.weights1)
    assert np.array_equal(candidate.move.bias1, initial.move.bias1)
    assert candidate.damage_reference.to_dict() == frozen.move.to_dict()
    assert candidate.control.to_dict() == frozen.control.to_dict()
    assert candidate.switch.to_dict() == frozen.switch.to_dict()


def test_convex_objective_has_correct_gradient_and_curvature():
    frozen, initial, groups = problem_inputs()
    p = prepare_readout(groups, initial, frozen)
    theta = np.asarray([.3, -.4])
    _, g = p.objective(theta)
    eps = 1e-6
    numerical = [(p.objective(theta + eps * e)[0] - p.objective(theta - eps * e)[0]) /
                 (2 * eps) for e in np.eye(2)]
    assert g == pytest.approx(numerical, abs=1e-8)
    a, b = theta + .5, theta - 1.
    assert p.objective((a+b)/2)[0] < (p.objective(a)[0] + p.objective(b)[0]) / 2


def test_representability_does_not_hide_conflicting_identical_inputs():
    frozen, initial, groups = problem_inputs()
    groups[1][0]["vectors"] = deepcopy(groups[0][0]["vectors"])
    d = representation_check(prepare_readout(groups, initial, frozen))
    assert d["high_cost_initial_errors"] == 1
    assert d["individually_correctable_errors"] == 0
    assert d["individual_feasibility"][0]["solver_status"] == 2


def test_distinct_basis_preserves_original_retention_and_comparison():
    frozen, initial, groups = problem_inputs()
    original = prepare_readout(groups, initial, frozen)
    basis = replace(initial, move=replace(initial.move,
        weights1=initial.move.weights1 * 2., weights2=np.asarray([.1, -.3])))
    p = prepare_readout(groups, initial, frozen, basis=basis)
    assert p.protected == original.protected
    assert p.minimum == pytest.approx(original.minimum)
    assert p.initial_regrets == pytest.approx(original.initial_regrets)
    assert p.anchor == pytest.approx(basis.move.weights2)
    assert not np.allclose(p.contrast, original.contrast)
    # Selecting the new anchor's preferences instead would drop this protection.
    assert prepare_readout(groups, basis, frozen).protected != p.protected
    candidate, report = fit_readout(groups, initial, frozen, basis=basis)
    assert report["solver_result"]["success"]
    assert report["retention_regressions"] == 0
    assert np.array_equal(candidate.move.weights1, basis.move.weights1)
    assert np.array_equal(candidate.move.bias1, basis.move.bias1)
    assert report["groups"][1]["initial"]["regret"] == 2.
    assert candidate.damage_reference.to_dict() == frozen.move.to_dict()


def test_basis_train_ancestry_must_match():
    frozen, initial, groups = problem_inputs()
    with pytest.raises(ValueError):
        prepare_readout(groups, initial, frozen,
                        basis=replace(initial, train_root_ids=("unseen",)))


def test_reward_view_cannot_change_original_protected_preferences():
    from pokemon_red_completion.red_status_win_conditioned_returns import RETURN_SCHEMA
    frozen, initial, groups = problem_inputs()
    revised = deepcopy(groups)
    for group in revised:
        for row in group:
            row["return_schema"] = RETURN_SCHEMA
            row["returns"] = [0., 5.]
            row["timing_returns"] = {"1": [0.] * 3, "2": [5.] * 3}
    old = prepare_readout(groups, initial, frozen)
    new = prepare_readout(revised, initial, frozen, retention_groups=groups)
    assert new.protected == old.protected
    assert new.minimum == pytest.approx(old.minimum)
    candidate, fit = fit_readout(revised, initial, frozen, retention_groups=groups)
    assert fit["retention_regressions"] == 0
    assert candidate.move.predict_index(groups[0][0]["vectors"]) == 0
    assert "original_return_groups" in fit
    with pytest.raises(ValueError):
        prepare_readout(revised, initial, frozen)
    revised[0][0]["capture_id"] = "changed"
    with pytest.raises(ValueError, match="ordered contexts"):
        prepare_readout(revised, initial, frozen, retention_groups=groups)


@pytest.mark.parametrize("kind", ["holdout", "root", "sleep", "nonfinite", "mean", "timing"])
def test_readout_rejects_unqualified_targets(kind):
    frozen, initial, groups = problem_inputs()
    row = groups[0][0]
    if kind == "holdout":
        row["role"] = "holdout"
    elif kind == "root":
        row["root"] = "different"
    elif kind == "sleep":
        row["vectors"][1][BALANCED_STATUS_NAMES.index("choice.player_asleep")] = 1.
    elif kind == "nonfinite":
        row["returns"][0] = float("nan")
    elif kind == "mean":
        row["returns"][0] = 3.
    else:
        row["timing_returns"]["1"] = [0.]
    with pytest.raises(ValueError):
        prepare_readout(groups, initial, frozen)
