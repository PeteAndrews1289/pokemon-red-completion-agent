"""Outcome-weighted TRAIN fitting with retained measured preferences, not policy rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from time import monotonic
from typing import Any

import numpy as np

from .red_balanced_status_features import BALANCED_STATUS_NAMES, BALANCED_STATUS_SCHEMA
from .red_status_battle_features import STATUS_MOVE_NAMES
from .red_status_closed_loop_returns import RETURN_SCHEMA
from .red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from .red_trainer_practice_head import TrainerHeadModel


def group_metrics(targets: Sequence[Mapping[str, Any]], actor: TrainerPracticeThreeHeadModel
                  ) -> dict[str, float | int]:
    regrets = [max(t["returns"]) - t["returns"][actor.move.predict_index(t["vectors"])]
               for t in targets]
    return {"contexts": len(targets), "regret": float(np.mean(regrets)),
            "errors": sum(r > .05 for r in regrets),
            "high_cost_errors": sum(r >= 1 for r in regrets)}


def fit_retaining_negatives(groups, initial, frozen, *, epochs=6000, rate=.03, seed=2026092201,
                           solver="backtracking", continuation=None, max_solver_iterations=500,
                           anchor_l2=0.):
    if not np.isfinite(anchor_l2) or anchor_l2 < 0 or (anchor_l2 and solver != "slsqp"):
        raise ValueError("anchor regularization requires finite nonnegative SLSQP coefficient")
    if type(max_solver_iterations) is not int or not 1 <= max_solver_iterations <= 5000:
        raise ValueError("numeric iteration budget must be bounded")
    if (initial.move.schema_id != BALANCED_STATUS_SCHEMA
            or np.count_nonzero(initial.move.weights1[:len(STATUS_MOVE_NAMES)])
            or not groups or any(not g for g in groups)):
        raise ValueError("retention fit requires compact initial weights and nonempty TRAIN groups")
    targets = [t for group in groups for t in group]
    for t in targets:
        if (t["role"] != "train" or t["root"] not in frozen.train_root_ids
                or t["return_schema"] != RETURN_SCHEMA or len(t["slots"]) != 2):
            raise ValueError("retention fit requires actual two-choice TRAIN outcomes")
    x = np.asarray([[v[len(STATUS_MOVE_NAMES):] for v in t["vectors"]] for t in targets])
    rewards = np.asarray([t["returns"] for t in targets], dtype=float)
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(rewards)):
        raise ValueError("nonfinite training input")
    desired = np.exp(3 * (rewards - rewards.max(axis=1, keepdims=True)))
    desired /= desired.sum(axis=1, keepdims=True)
    weights = np.concatenate([np.full(len(g), 1 / (len(groups) * len(g))) for g in groups])
    weights *= np.clip(np.abs(rewards[:, 0] - rewards[:, 1]), .1, 4.)
    status = np.asarray([next(i for i, row in enumerate(t["vectors"])
                              if row[BALANCED_STATUS_NAMES.index("choice.status")])
                         for t in targets])
    damage = 1 - status
    w1, b1, w2 = (initial.move.weights1[len(STATUS_MOVE_NAMES):].copy(),
                   initial.move.bias1.copy(), initial.move.weights2.copy())
    anchor = np.concatenate((w1.ravel(), b1, w2))

    def scores(a, b, c):
        return np.tanh(x @ a + b) @ c

    before = scores(w1, b1, w2)
    margins = before[np.arange(len(targets)), damage] - before[np.arange(len(targets)), status]
    robust = []
    for i, t in enumerate(targets):
        timing = t["timing_returns"]
        neg = all(d - s > .05 for d, s in zip(timing[str(t["slots"][damage[i]])],
                   timing[str(t["slots"][status[i]])], strict=True))
        if neg and margins[i] > 0:
            robust.append(i)
    protected = np.asarray(robust, dtype=int)
    minimum = np.minimum(margins[protected], .05)
    if continuation is not None:
        if (solver != "slsqp" or continuation.move.schema_id != initial.move.schema_id
                or continuation.move.weights1.shape != initial.move.weights1.shape
                or np.count_nonzero(continuation.move.weights1[:len(STATUS_MOVE_NAMES)])):
            raise ValueError("numeric continuation must preserve compact parameterization")
        w1 = continuation.move.weights1[len(STATUS_MOVE_NAMES):].copy()
        b1, w2 = continuation.move.bias1.copy(), continuation.move.weights2.copy()
        retained = scores(w1, b1, w2)
        if np.any(retained[protected, damage[protected]]
                  - retained[protected, status[protected]] < minimum - 1e-8):
            raise ValueError("numeric continuation violates original retention constraints")
    accepted = rejected = shrunk = 0
    solver_report = {}
    if solver == "slsqp":
        from scipy.optimize import minimize
        width, hidden = w1.shape
        length = width * hidden

        def unpack(theta):
            return (theta[:length].reshape(width, hidden),
                    theta[length:length+hidden], theta[-hidden:])

        def objective(theta):
            a, b, c = unpack(theta)
            h = np.tanh(x @ a + b)
            logits = h @ c
            shifted = logits - logits.max(axis=1, keepdims=True)
            normalizer = np.exp(shifted).sum(axis=1, keepdims=True)
            p = np.exp(shifted) / normalizer
            loss = -np.sum(weights[:, None] * desired * (shifted - np.log(normalizer)))
            residual = (p - desired) * weights[:, None]
            dh = residual[:, :, None] * c * (1 - h * h)
            jac = np.concatenate((np.einsum("nkw,nkh->wh", x, dh).ravel(),
                                  dh.sum(axis=(0, 1)), np.einsum("nkh,nk->h", h, residual)))
            loss += anchor_l2 * np.mean((theta - anchor) ** 2)
            jac += (2 * anchor_l2 / len(theta)) * (theta - anchor)
            return float(loss), jac

        xd = x[protected, damage[protected]]
        xs = x[protected, status[protected]]

        def constraints(theta):
            a, b, c = unpack(theta)
            return (np.tanh(xd @ a + b) - np.tanh(xs @ a + b)) @ c - minimum

        def constraint_jacobian(theta):
            a, b, c = unpack(theta)
            hd, hs = np.tanh(xd @ a + b), np.tanh(xs @ a + b)
            dd, ds = (1 - hd * hd) * c, (1 - hs * hs) * c
            jac = np.einsum("nw,nh->nwh", xd, dd) - np.einsum("nw,nh->nwh", xs, ds)
            return np.concatenate((jac.reshape(len(protected), length), dd - ds, hd - hs), axis=1)

        started = monotonic()

        def check_deadline(_theta):
            if monotonic() - started > 900:
                raise TimeoutError("retention optimizer15minute limit")

        theta = np.concatenate((w1.ravel(), b1, w2))
        solution = minimize(objective, theta, method="SLSQP", jac=True,
                            constraints=({"type": "ineq", "fun": constraints,
                                          "jac": constraint_jacobian},) if len(protected) else (),
                            options={"maxiter": max_solver_iterations, "ftol": 1e-9},
                            callback=check_deadline)
        w1, b1, w2 = unpack(solution.x)
        solver_report = {"solver": "slsqp", "success": bool(solution.success),
                         "iterations": int(solution.nit), "message": str(solution.message),
                         "loss": float(solution.fun),
                         "minimum_constraint_slack": float(np.min(constraints(solution.x)))
                         if len(protected) else 0.}
        if anchor_l2:
            solver_report.update(anchor_l2=anchor_l2,
                                 parameter_distance=float(np.linalg.norm(solution.x - anchor)))
    elif solver != "backtracking":
        raise ValueError("unknown retention solver")
    for _ in range(epochs if solver == "backtracking" else 0):
        h = np.tanh(x @ w1 + b1)
        logits = h @ w2
        p = np.exp(logits - logits.max(axis=1, keepdims=True))
        p /= p.sum(axis=1, keepdims=True)
        residual = (p - desired) * weights[:, None]
        g2 = np.einsum("nkh,nk->h", h, residual)
        dh = residual[:, :, None] * w2 * (1 - h * h)
        g1 = np.einsum("nkw,nkh->wh", x, dh)
        gb = dh.sum(axis=(0, 1))
        for halving in range(13):
            step = rate / 2 ** halving
            a, b, c = w1 - step * g1, b1 - step * gb, w2 - step * g2
            proposal = scores(a, b, c)
            margin = (proposal[protected, damage[protected]]
                      - proposal[protected, status[protected]])
            if np.all(margin >= minimum):
                w1, b1, w2 = a, b, c
                accepted += 1
                shrunk += halving > 0
                break
        else:
            rejected += 1
    expanded = np.zeros_like(initial.move.weights1)
    expanded[len(STATUS_MOVE_NAMES):] = w1
    head = TrainerHeadModel(BALANCED_STATUS_SCHEMA, BALANCED_STATUS_NAMES, expanded, b1, w2, seed)
    candidate = replace(frozen, move=head, damage_reference=frozen.move,
                        train_capture_ids=tuple(dict.fromkeys(
                            (*frozen.train_capture_ids, *(t["capture_id"] for t in targets)))))
    reports = [{"initial": group_metrics(g, initial), "candidate": group_metrics(g, candidate)}
               for g in groups]
    regressions = sum(candidate.move.predict_index(targets[i]["vectors"]) != damage[i]
                      for i in protected)
    return candidate, {"groups": reports, "protected_preferences": len(protected),
                       "retention_regressions": int(regressions), "accepted_steps": accepted,
                       "backtracked_steps": shrunk, "rejected_steps": rejected,
                       **({"solver_result": solver_report} if solver_report else {})}
