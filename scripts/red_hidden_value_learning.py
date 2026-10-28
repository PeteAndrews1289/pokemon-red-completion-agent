"""Constrained learning of existing compact status features; K remains frozen."""

from dataclasses import replace
from time import monotonic

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES as N
from pokemon_red_completion.red_effect_selector_head import effect_values
from pokemon_red_completion.red_status_battle_features import STATUS_MOVE_NAMES
from pokemon_red_completion.red_status_retention_fit import group_metrics


class HiddenProblem:
    def __init__(self, problem, actor, targets):
        self.problem = problem
        self.prefix = len(STATUS_MOVE_NAMES)
        self.shape = actor.move.weights1[self.prefix:].shape
        self.length = int(np.prod(self.shape))
        if (np.count_nonzero(actor.move.weights1[:self.prefix]) or
                len(targets) != len(problem.desired) or
                any(t["role"] != "train" or t["root"] not in actor.train_root_ids
                    for t in targets)):
            raise ValueError("compact TRAIN representation or ordered inventory differs")
        statuses = [next(i for i, v in enumerate(t["vectors"]) if v[N.index("choice.status")])
                    for t in targets]
        x = np.asarray([t["vectors"] for t in targets], float)
        indices = np.arange(len(targets))
        self.xs = x[indices, statuses, self.prefix:]
        self.xd = x[indices, 1-np.asarray(statuses), self.prefix:]
        extra = np.asarray([effect_values(t["vectors"], actor.move.effect_weights)
                            for t in targets])
        self.extra = extra[indices, statuses]-extra[indices, 1-np.asarray(statuses)]
        self.anchor = np.concatenate((actor.move.weights1[self.prefix:].ravel(),
                                      actor.move.bias1, actor.move.weights2,
                                      np.asarray(actor.move.effect_readout)))

    def unpack(self, theta):
        h = self.shape[1]
        return (theta[:self.length].reshape(self.shape), theta[self.length:self.length+h],
                theta[self.length+h:self.length+2*h], theta[-2:])

    def contrast(self, theta, *, jacobian=False):
        a, b, c, aux = self.unpack(theta)
        hs, hd = np.tanh(self.xs@a+b), np.tanh(self.xd@a+b)
        scores = (hs-hd)@c+self.extra@aux
        if not jacobian:
            return scores
        ds, dd = (1-hs*hs)*c, (1-hd*hd)*c
        dw = self.xs[:, :, None]*ds[:, None, :]-self.xd[:, :, None]*dd[:, None, :]
        jac = np.column_stack((dw.reshape(len(scores), self.length), ds-dd, hs-hd, self.extra))
        return scores, jac

    def objective(self, theta):
        scores, jac = self.contrast(theta, jacobian=True)
        p = self.problem
        distance = theta-self.anchor
        loss = np.sum(p.weights*(np.logaddexp(0., scores)-p.desired*scores))
        loss += p.anchor_l2*np.mean(distance**2)
        gradient = jac.T@(p.weights*(expit(scores)-p.desired))
        gradient += 2*p.anchor_l2*distance/len(theta)
        return float(loss), gradient

    def constraints(self, theta):
        return -self.contrast(theta)[list(self.problem.protected)]-self.problem.minimum

    def constraint_jacobian(self, theta):
        return -self.contrast(theta, jacobian=True)[1][list(self.problem.protected)]


def fit_hidden(problem, actor, groups, initial, *, max_iterations=500):
    if type(max_iterations) is not int or not 1 <= max_iterations <= 5000:
        raise ValueError("hidden solver requires a bounded1-5000iteration budget")
    targets = [t for g in groups for t in g]
    hidden = HiddenProblem(problem, actor, targets)
    if np.min(hidden.constraints(hidden.anchor)) < -1e-8:
        raise ValueError("nonlinear fit must start inside original retained margins")
    started = monotonic()

    def deadline(_):
        if monotonic()-started > 900:
            raise TimeoutError("hidden solver15minute cap")

    fitted = minimize(hidden.objective, hidden.anchor, jac=True, method="SLSQP",
        constraints=({"type": "ineq", "fun": hidden.constraints,
                      "jac": hidden.constraint_jacobian},), callback=deadline,
        options={"maxiter": max_iterations, "ftol": 1e-9})
    if not np.isfinite(fitted.x).all():
        raise ValueError("nonfinite status representation")
    w, b, v, aux = hidden.unpack(fitted.x)
    expanded = np.zeros_like(actor.move.weights1)
    expanded[hidden.prefix:] = w
    candidate = replace(actor, train_capture_ids=tuple(dict.fromkeys(
        (*actor.train_capture_ids, *(t["capture_id"] for t in targets)))),
        move=replace(actor.move, weights1=expanded,
        bias1=b.copy(), weights2=v.copy(), effect_readout=tuple(aux)))
    statuses = [next(i for i, row in enumerate(t["vectors"]) if row[N.index("choice.status")])
                for t in targets]
    regressions = sum(candidate.move.predict_index(targets[i]["vectors"]) == statuses[i]
                      for i in problem.protected)
    old = [{"initial": group_metrics(g, initial), "candidate": group_metrics(g, candidate)}
           for g in groups[:-1]]
    new = {"actor": group_metrics(groups[-1], actor),
           "candidate": group_metrics(groups[-1], candidate)}
    slack = float(np.min(hidden.constraints(fitted.x)))
    passed = bool(fitted.success and slack >= -1e-8 and regressions == 0 and
        old[0]["candidate"]["regret"] <= old[0]["initial"]["regret"] and
        new["candidate"]["regret"] <= .75*new["actor"]["regret"])
    return candidate, {"passed": passed, "fits": 1, "solver_success": bool(fitted.success),
        "iterations": int(fitted.nit), "solver_message": str(fitted.message),
        "minimum_slack": slack, "retention_regressions": regressions,
        "protected_preferences": len(problem.protected), "old_groups": old,
        "new_group": new, "hidden_changed": True, "effect_refitted": False,
        "parameters": len(fitted.x), "seconds": monotonic()-started}
