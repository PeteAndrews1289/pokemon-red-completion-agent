"""Prospective output-only update and outcome gate; historical gates are untouched."""

from dataclasses import replace
from time import monotonic

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

from pokemon_red_completion.red_balanced_status_features import BALANCED_STATUS_NAMES as N
from pokemon_red_completion.red_effect_selector_head import effect_values
from pokemon_red_completion.red_status_execution_learning import eligible_target
from pokemon_red_completion.red_status_retention_fit import group_metrics
from pokemon_red_completion.red_status_win_conditioned_returns import RETURN_SCHEMA

OFFSETS = (0, 1, 2, 3, 5, 7, 11, 12)
GATE_SCHEMA = "pokemon.red.battler.outcome-readiness.v2"


def validate_offsets(offsets):
    # Match the existing episode executor bound; do not widen it for this pilot.
    if (len(offsets) != 8 or any(type(x) is not int or not 0 <= x <= 12 for x in offsets)
            or len(set(offsets)) != 8):
        raise ValueError("eight distinct opening offsets within0-12required")


def extend_problem(old, actor, targets):
    validate_offsets(OFFSETS)
    if not targets or len({t["capture_id"] for t in targets}) != len(targets):
        raise ValueError("nonempty distinct targets required")
    contrasts, desired, weights = [], [], []
    for t in targets:
        if (t["root"] not in actor.train_root_ids or not eligible_target(t) or
                t["return_schema"] != RETURN_SCHEMA or tuple(t["offsets"]) != OFFSETS or
                len(t["slots"]) != 2 or len(set(t["slots"])) != 2):
            raise ValueError("new TRAIN target scope differs")
        x = np.asarray(t["vectors"], float)
        y = np.asarray([t["timing_returns"][str(s)] for s in t["slots"]], float)
        if (x.shape != (2, len(N)) or y.shape != (2, 8) or not np.isfinite(x).all()
                or not np.isfinite(y).all() or
                not np.allclose(y.mean(axis=1), t["returns"], rtol=0, atol=1e-10)):
            raise ValueError("paired measured target dimensions or means differ")
        si = next(i for i, v in enumerate(x) if v[N.index("choice.status")])
        hidden = np.tanh(x @ actor.move.weights1 + actor.move.bias1)
        extras = effect_values(x, actor.move.effect_weights)
        contrasts.append(np.append(hidden[si]-hidden[1-si], extras[si]-extras[1-si]))
        gaps = y[si]-y[1-si]
        desired.append(expit(3 * gaps.mean()))
        weights.append(.5 / len(targets) * np.clip(abs(gaps.mean()), .1, 4.) /
                       (1 + np.std(gaps, ddof=1) / 20))
    anchor = np.append(actor.move.weights2, actor.move.effect_readout)
    if np.min(old.constraints @ anchor-old.minimum) < -1e-8:
        raise ValueError("current anchor violates retained preferences")
    return replace(old, contrast=np.vstack((old.contrast, contrasts)),
        desired=np.append(old.desired, desired), weights=np.append(.5*old.weights, weights),
        anchor=anchor)


def fit_once(problem, actor, targets, old_groups, initial, *, start=None, reference_actor=None):
    started = monotonic()

    def deadline(_):
        if monotonic()-started > 60:
            raise TimeoutError("output solver60second cap")

    a, b = problem.constraints, problem.minimum
    start = problem.anchor if start is None else np.asarray(start, float)
    if start.shape != problem.anchor.shape or not np.isfinite(start).all():
        raise ValueError("readout start differs from finite parameter space")
    fit = minimize(problem.objective, start, jac=True, method="SLSQP",
        constraints=({"type": "ineq", "fun": lambda w: a@w-b, "jac": lambda w: a},),
        callback=deadline, options={"maxiter": 500, "ftol": 1e-9})
    if not np.isfinite(fit.x).all():
        raise ValueError("nonfinite fitted readout")
    candidate = replace(actor,
        move=replace(actor.move, weights2=fit.x[:-2].copy(), effect_readout=tuple(fit.x[-2:])),
        train_capture_ids=tuple(dict.fromkeys((*actor.train_capture_ids,
                                             *(t["capture_id"] for t in targets)))))
    old_targets = [t for g in old_groups for t in g]
    regressions = sum(candidate.move.predict_index(old_targets[i]["vectors"]) ==
                      problem.status_indices[i] for i in problem.protected)
    old_metrics = [{"initial": group_metrics(g, initial),
                    "candidate": group_metrics(g, candidate)} for g in old_groups]
    reference = actor if reference_actor is None else reference_actor
    new_metrics = {"actor": group_metrics(targets, reference),
                   "candidate": group_metrics(targets, candidate)}
    slack = float(np.min(a@fit.x-b))
    passed = bool(fit.success and slack >= -1e-8 and regressions == 0 and
        old_metrics[0]["candidate"]["regret"] <= old_metrics[0]["initial"]["regret"] and
        new_metrics["candidate"]["regret"] <= .75*new_metrics["actor"]["regret"])
    return candidate, {"passed": passed, "fits": 1, "solver_success": bool(fit.success),
        "iterations": int(fit.nit), "minimum_slack": slack, "retention_regressions": regressions,
        "protected_preferences": len(problem.protected), "old_groups": old_metrics,
        "new_group": new_metrics, "hidden_changed": False, "effect_refitted": False}


def empirical_preferences(problem, targets):
    """Preserve empirical timing disagreement instead of saturating the sample mean.

    This is a prospective ranking objective, not a rewritten episode reward or
    estimated confidence interval. Retained expected-return metrics still gate fit.
    """
    if len(targets) != len(problem.contrast):
        raise ValueError("empirical objective requires the exact ordered target inventory")
    probabilities = []
    for target in targets:
        if target["role"] != "train":
            raise ValueError("empirical objective is TRAIN only")
        status = next(i for i, v in enumerate(target["vectors"]) if v[N.index("choice.status")])
        samples = np.asarray([target["timing_returns"][str(s)] for s in target["slots"]], float)
        if (samples.ndim != 2 or samples.shape[0] != 2 or samples.shape[1] not in (3, 8) or
                not np.isfinite(samples).all() or
                not np.allclose(samples.mean(axis=1), target["returns"], rtol=0, atol=1e-10)):
            raise ValueError("empirical timing samples or means differ")
        probabilities.append(float(expit(3*(samples[status]-samples[1-status])).mean()))
    return replace(problem, desired=np.asarray(probabilities))


def outcome_gate(candidate, baseline):
    from run_red_closed_loop_status import gate
    for arm in (candidate, baseline):
        if not arm or len({r["case"] for r in arm}) != len(arm):
            raise ValueError("nonempty unique battle cases required")
        if any(type(r["metrics"]["invalid_action_failures"]) is not int or
               r["metrics"]["invalid_action_failures"] < 0 for r in arm):
            raise ValueError("invalid-action counts must be nonnegative integers")
    original = gate(candidate, baseline)
    invalid = sum(r["metrics"]["invalid_action_failures"] for r in [*candidate, *baseline])
    return {**original, "schema": GATE_SCHEMA, "original_zero_flag_passed": original["passed"],
        "invalid_actions": invalid, "raw_flags_are_diagnostic": True,
        "passed": bool(original["wins"]["candidate"] >= original["wins"]["frozen"] and
            original["decisions"]["candidate"] <= 1.25*original["decisions"]["frozen"] and
            original["improved_won_status_cases"] > 0 and invalid == 0)}
