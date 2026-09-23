"""One constrained output fit; whole-battle outcomes, not effect labels, choose moves."""

from dataclasses import replace
from time import monotonic

import numpy as np
from scipy.optimize import minimize

from .red_effect_selector_head import augment_head, effect_values
from .red_status_readout_learning import prepare_readout
from .red_status_retention_fit import group_metrics


def prepare_combination(groups, initial, frozen, basis, originals, effect):
    old = prepare_readout(groups, initial, frozen, basis=basis, retention_groups=originals)
    targets = [t for g in groups for t in g]
    extras = np.array([effect_values(t["vectors"], effect["weights"]) for t in targets])
    indices, status = np.arange(len(targets)), np.array(old.status_indices)
    delta = extras[indices, status] - extras[indices, 1-status]
    contrast = np.column_stack((old.contrast, delta))
    return replace(old, contrast=contrast, anchor=np.append(old.anchor, [0., 0.]),
                   constraints=-contrast[list(old.protected)])


def fit_combination(groups, initial, frozen, basis, originals, effect, effect_sha):
    problem = prepare_combination(groups, initial, frozen, basis, originals, effect)
    a, b = problem.constraints, problem.minimum
    if len(b) and np.min(a @ problem.anchor-b) < -1e-8:
        raise ValueError("combination anchor violates retained preferences")
    started = monotonic()

    def deadline(_):
        if monotonic() - started > 60:
            raise TimeoutError("combination solver60second cap")

    fit = minimize(problem.objective, problem.anchor, jac=True, method="SLSQP",
        constraints=({"type": "ineq", "fun": lambda w: a @ w-b, "jac": lambda w: a},)
        if len(b) else (), callback=deadline, options={"maxiter": 500, "ftol": 1e-9})
    if not np.isfinite(fit.x).all():
        raise ValueError("nonfinite combination weights")
    base_head = replace(basis.move, weights2=fit.x[:-2].copy())
    head = augment_head(base_head, effect["weights"], effect_sha, tuple(fit.x[-2:]))
    candidate = replace(basis, move=head)
    targets = [t for g in groups for t in g]
    report = {"fits": 1, "solver_success": bool(fit.success), "iterations": int(fit.nit),
        "seconds": monotonic()-started,
        "minimum_slack": float(np.min(a @ fit.x-b)) if len(b) else 0.,
        "message": str(fit.message), "loss": float(fit.fun),
        "protected_preferences": len(problem.protected),
        "retention_regressions": sum(candidate.move.predict_index(targets[i]["vectors"]) ==
                                     problem.status_indices[i] for i in problem.protected),
        "auxiliary_readout": list(head.effect_readout),
        "groups": [{"initial": group_metrics(g, initial), "prior": group_metrics(g, basis),
                    "candidate": group_metrics(g, candidate)} for g in groups],
        "original_groups": [group_metrics(g, candidate) for g in originals],
        "effect_predictor_refitted": False, "hidden_parameters_changed": False}
    return candidate, report
