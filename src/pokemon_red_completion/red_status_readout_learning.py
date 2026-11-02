"""Convex TRAIN-only output-layer learning with fixed learned hidden features."""

from dataclasses import dataclass, replace
from time import monotonic

import numpy as np
from scipy.optimize import linprog, minimize, nnls
from scipy.special import expit

from .red_balanced_status_features import BALANCED_STATUS_NAMES, BALANCED_STATUS_SCHEMA
from .red_status_battle_features import STATUS_MOVE_NAMES
from .red_status_closed_loop_returns import RETURN_SCHEMA
from .red_status_execution_learning import eligible_target
from .red_status_retention_fit import group_metrics
from .red_status_win_conditioned_returns import RETURN_SCHEMA as WIN_RETURN_SCHEMA


@dataclass(frozen=True)
class ReadoutProblem:
    contrast: np.ndarray
    desired: np.ndarray
    weights: np.ndarray
    anchor: np.ndarray
    constraints: np.ndarray
    minimum: np.ndarray
    protected: tuple[int, ...]
    status_indices: tuple[int, ...]
    initial_regrets: np.ndarray
    anchor_l2: float = .001

    def objective(self, theta):
        logits = self.contrast @ theta
        distance = theta - self.anchor
        loss = np.sum(self.weights * (np.logaddexp(0., logits) - self.desired * logits))
        loss += self.anchor_l2 * np.mean(distance ** 2)
        gradient = self.contrast.T @ (self.weights * (expit(logits) - self.desired))
        gradient += 2 * self.anchor_l2 * distance / len(theta)
        return float(loss), gradient


def prepare_readout(groups, initial, frozen, *, basis=None, retention_groups=None):
    basis = initial if basis is None else basis
    if (not groups or any(not g for g in groups)
            or initial.move.schema_id != BALANCED_STATUS_SCHEMA
            or basis.move.schema_id != BALANCED_STATUS_SCHEMA
            or np.count_nonzero(initial.move.weights1[:len(STATUS_MOVE_NAMES)])
            or np.count_nonzero(basis.move.weights1[:len(STATUS_MOVE_NAMES)])
            or set(basis.train_root_ids) != set(frozen.train_root_ids)):
        raise ValueError("readout requires compact initial features and nonempty TRAIN groups")
    targets = [t for g in groups for t in g]
    expected_schema = WIN_RETURN_SCHEMA if retention_groups is not None else RETURN_SCHEMA
    for t in targets:
        if (t["role"] != "train" or t["root"] not in frozen.train_root_ids
                or t["return_schema"] != expected_schema or len(t["slots"]) != 2
                or len(set(t["slots"])) != 2 or not eligible_target(t)):
            raise ValueError("readout requires awake two-choice TRAIN outcomes")
        if any(len(t["timing_returns"][str(slot)]) != 3 for slot in t["slots"]):
            raise ValueError("three retained timing branches required")
    x = np.asarray([t["vectors"] for t in targets], dtype=float)
    returns = np.asarray([t["returns"] for t in targets], dtype=float)
    timing = np.asarray([[t["timing_returns"][str(s)] for s in t["slots"]] for t in targets])
    if (x.shape != (len(targets), 2, len(BALANCED_STATUS_NAMES))
            or returns.shape != (len(targets), 2)
            or not all(np.all(np.isfinite(a)) for a in (x, returns, timing))):
        raise ValueError("invalid finite target dimensions")
    if not np.allclose(returns, timing.mean(axis=2), atol=1e-10, rtol=0):
        raise ValueError("target means differ from measured timings")
    statuses = np.asarray([next(i for i, v in enumerate(t["vectors"])
                                if v[BALANCED_STATUS_NAMES.index("choice.status")])
                           for t in targets])
    indices = np.arange(len(targets))
    hidden = np.tanh(x @ basis.move.weights1 + basis.move.bias1)
    contrast = hidden[indices, statuses] - hidden[indices, 1-statuses]
    anchor = basis.move.weights2.copy()
    gap = returns[indices, statuses] - returns[indices, 1-statuses]
    robust_negative = np.all(timing[indices, 1-statuses] - timing[indices, statuses] > .05, axis=1)
    reference_hidden = np.tanh(x @ initial.move.weights1 + initial.move.bias1)
    reference_contrast = reference_hidden[indices, statuses] - reference_hidden[indices, 1-statuses]
    initial_margin = -(reference_contrast @ initial.move.weights2)
    protected = np.flatnonzero(robust_negative & (initial_margin > 0))
    weights = np.concatenate([np.full(len(g), 1 / (len(groups) * len(g))) for g in groups])
    weights *= np.clip(np.abs(gap), .1, 4.)
    regrets = np.asarray([max(t["returns"]) - t["returns"][initial.move.predict_index(t["vectors"])]
                          for t in targets])
    minimum = np.minimum(initial_margin[protected], .05)
    if retention_groups is not None:
        original_targets = [t for g in retention_groups for t in g]
        if ([len(g) for g in retention_groups] != [len(g) for g in groups]
                or any(any(old[k] != new[k] for k in ("capture_id", "root", "slots", "vectors"))
                       for old, new in zip(original_targets, targets, strict=True))):
            raise ValueError("v2 reward view must preserve original ordered contexts")
        reference = prepare_readout(retention_groups, initial, frozen, basis=basis)
        protected, minimum = np.asarray(reference.protected, dtype=int), reference.minimum
    return ReadoutProblem(contrast, expit(3 * gap), weights, anchor,
                          -contrast[protected], minimum,
                          tuple(map(int, protected)), tuple(map(int, statuses)), regrets)


def representation_check(problem):
    """Individual feasibility is not joint fit quality; witnesses are discarded."""
    rows = []
    for i in np.flatnonzero(problem.initial_regrets >= 1.):
        sign = 1. if problem.desired[i] > .5 else -1.
        a = np.vstack((problem.constraints, sign * problem.contrast[i]))
        b = np.append(problem.minimum, .05)
        result = linprog(np.zeros(len(problem.anchor)), A_ub=-a, b_ub=-b,
                         bounds=[(None, None)] * len(problem.anchor), method="highs",
                         options={"time_limit": 1.})
        feasible = bool(result.success and np.min(a @ result.x - b) >= -1e-7)
        rows.append({"target_index": int(i), "feasible": feasible,
                     "solver_status": int(result.status)})
    return {"hidden_width": len(problem.anchor),
            "contrast_rank": int(np.linalg.matrix_rank(problem.contrast)),
            "high_cost_initial_errors": len(rows),
            "individually_correctable_errors": sum(r["feasible"] for r in rows),
            "individual_feasibility": rows, "joint_learnability_claim": False}


def fit_readout(groups, initial, frozen, *, basis=None, retention_groups=None, max_iterations=500):
    if type(max_iterations) is not int or not 1 <= max_iterations <= 500:
        raise ValueError("readout iteration budget must be1-500")
    basis = initial if basis is None else basis
    problem = prepare_readout(groups, initial, frozen, basis=basis,
                              retention_groups=retention_groups)
    began = monotonic()

    def deadline(_):
        if monotonic() - began > 60:
            raise TimeoutError("readout solver60second limit")

    a, b = problem.constraints, problem.minimum
    solution = minimize(problem.objective, problem.anchor, method="SLSQP", jac=True,
                        constraints=({"type": "ineq", "fun": lambda w: a @ w - b,
                                      "jac": lambda w: a},) if len(b) else (),
                        callback=deadline, options={"maxiter": max_iterations, "ftol": 1e-9})
    if not np.all(np.isfinite(solution.x)):
        raise ValueError("readout solver produced nonfinite weights")
    head = replace(basis.move, weights2=solution.x.copy())
    targets = [t for g in groups for t in g]
    candidate = replace(frozen, move=head, damage_reference=frozen.move,
        train_capture_ids=tuple(dict.fromkeys((*frozen.train_capture_ids,
                                              *(t["capture_id"] for t in targets)))))
    slack = a @ solution.x - b
    loss, gradient = problem.objective(solution.x)
    active = a[slack <= 1e-6]
    residual = float(np.linalg.norm(gradient))
    if len(active):
        _, residual = nnls(active.T, gradient, maxiter=10000)
    regressions = sum(candidate.move.predict_index(targets[i]["vectors"]) ==
                      problem.status_indices[i] for i in problem.protected)
    return candidate, {
        "groups": [{"initial": group_metrics(g, initial), "candidate": group_metrics(g, candidate)}
                   for g in groups],
        **({"original_return_groups": [
            {"initial": group_metrics(g, initial), "candidate": group_metrics(g, candidate)}
            for g in retention_groups]} if retention_groups is not None else {}),
        "protected_preferences": len(problem.protected), "retention_regressions": int(regressions),
        "solver_result": {"success": bool(solution.success), "iterations": int(solution.nit),
            "message": str(solution.message), "loss": loss, "anchor_l2": problem.anchor_l2,
            "minimum_constraint_slack": float(np.min(slack)) if len(slack) else 0.,
            "stationarity_residual": float(residual),
            "parameter_distance": float(np.linalg.norm(solution.x - problem.anchor)),
            "seconds": monotonic() - began},
        "hidden_parameters_unchanged": True}
