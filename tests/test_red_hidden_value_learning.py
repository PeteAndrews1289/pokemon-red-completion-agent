from dataclasses import replace

import numpy as np
import pytest
from audit_red_outcome_value_pilot import verify_frozen
from red_hidden_value_learning import HiddenProblem, fit_hidden
from red_outcome_value_learning import extend_problem
from test_red_outcome_value_learning import setup


def inputs():
    old, actor, targets, groups, initial = setup()
    problem = extend_problem(old, actor, targets)
    return problem, actor, [*groups, targets], initial


def test_nonlinear_objective_and_all_retention_jacobians():
    problem, actor, groups, _ = inputs()
    p = HiddenProblem(problem, actor, [t for g in groups for t in g])
    theta = p.anchor+np.random.default_rng(7).normal(0, .01, len(p.anchor))
    eps = 1e-6
    numeric = [(p.objective(theta+eps*v)[0]-p.objective(theta-eps*v)[0])/(2*eps)
               for v in np.eye(len(theta))]
    assert p.objective(theta)[1] == pytest.approx(numeric, abs=1e-8)
    jac = np.column_stack([(p.constraints(theta+eps*v)-p.constraints(theta-eps*v))/(2*eps)
                           for v in np.eye(len(theta))])
    assert p.constraint_jacobian(theta) == pytest.approx(jac, abs=1e-8)


def test_one_hidden_fit_retains_real_margin_and_learns_without_changing_K():
    problem, actor, groups, initial = inputs()
    candidate, report = fit_hidden(problem, actor, groups, initial)
    assert report["passed"] and report["retention_regressions"] == 0
    assert candidate.move.predict_index(groups[-1][0]["vectors"]) == 1
    targets = [t for g in groups for t in g]
    verify_frozen(candidate, actor, targets, allow_hidden=True)
    assert not np.array_equal(candidate.move.weights1, actor.move.weights1)
    with pytest.raises(ValueError, match="frozen"):
        verify_frozen(candidate, actor, targets)
    bad = replace(candidate, control=replace(candidate.control,
                                             weights2=candidate.control.weights2+.1))
    with pytest.raises(ValueError, match="frozen"):
        verify_frozen(bad, actor, targets, allow_hidden=True)


@pytest.mark.parametrize("invalid", [0, 5001, True, 500.])
def test_hidden_solver_budget_is_explicit_and_bounded(invalid):
    with pytest.raises(ValueError, match="bounded"):
        fit_hidden(None, None, None, None, max_iterations=invalid)
