"""Bounded terminal learning with hard retention of earlier learned decisions.

No replay or lookup table is used at inference. Constraints apply only during
training; deployment uses the unchanged schema-bound neural heads.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from pokemon_red_completion.red_trainer_practice_features import CONTROL_FEATURE_NAMES_V2
from pokemon_red_completion.red_trainer_practice_fit import (
    CONTROL_ACTION_SCHEMA_ID,
)
from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel
from pokemon_red_completion.red_trainer_proposed_control import (
    PROPOSED_CONTROL_NAMES,
    PROPOSED_CONTROL_SCHEMA,
)


def bridge_control(head: TrainerHeadModel) -> TrainerHeadModel:
    """Algebraic schema lift, preserving every old control score (not a fit)."""
    if head.schema_id != CONTROL_ACTION_SCHEMA_ID:
        raise ValueError("bridge requires legacy action-interaction control")
    weights = np.zeros((len(PROPOSED_CONTROL_NAMES), head.weights1.shape[1]))
    for index, name in enumerate(head.feature_names):
        if name in CONTROL_FEATURE_NAMES_V2:
            for prefix in ("attack_or_decline.", "switch."):
                weights[PROPOSED_CONTROL_NAMES.index(prefix + name)] += head.weights1[index]
        else:
            weights[PROPOSED_CONTROL_NAMES.index(name)] += head.weights1[index]
    return replace(
        head,
        schema_id=PROPOSED_CONTROL_SCHEMA,
        feature_names=PROPOSED_CONTROL_NAMES,
        weights1=weights,
    )


def _batch(cases):
    if not cases or any(case.mean_returns is None for case in cases):
        raise ValueError("measured retention training cases required")
    count = max(len(case.candidate_vectors) for case in cases)
    width = len(cases[0].candidate_vectors[0])
    x = np.zeros((len(cases), count, width))
    mask = np.zeros((len(cases), count), dtype=bool)
    regrets = np.zeros((len(cases), count))
    for i, case in enumerate(cases):
        n = len(case.candidate_vectors)
        x[i, :n] = case.candidate_vectors
        mask[i, :n] = True
        rewards = np.asarray(case.mean_returns)
        regrets[i, :n] = rewards.max() - rewards
    return x, mask, regrets


def _forward(x, mask, w1, b1, w2):
    hidden = np.tanh(x @ w1 + b1)
    scores = hidden @ w2
    scores = np.where(mask, scores, -np.inf)
    p = np.exp(scores - scores.max(axis=1, keepdims=True))
    p /= p.sum(axis=1, keepdims=True)
    return hidden, scores, p


def batch_loss_gradient(model: TrainerHeadModel, cases: tuple[TrainerHeadExample, ...]):
    """Vectorized measured expected-regret derivative in parameter-pack order."""
    x, mask, regret = _batch(cases)
    hidden, _, p = _forward(x, mask, model.weights1, model.bias1, model.weights2)
    loss = (p * regret).sum(axis=1, keepdims=True)
    residual = p * (regret - loss) / len(cases)
    dh = residual[..., None] * model.weights2 * (1.0 - hidden * hidden)
    g1 = np.einsum("ncf,nch->fh", x, dh)
    gb = dh.sum(axis=(0, 1))
    g2 = np.einsum("nch,nc->h", hidden, residual)
    return float(loss.mean()), np.concatenate((g1.ravel(), gb, g2))


def fit_retained_head(
    initial: TrainerHeadModel,
    terminal: tuple[TrainerHeadExample, ...],
    anchors: tuple[TrainerHeadExample, ...],
    *,
    epochs: int = 1200,
    learning_rate: float = 0.2,
):
    """One projected-gradient trajectory; hard checks precede every accepted step.

    Linearized anchor margins constrain each proposed step. Backtracking checks
    the actual nonlinear model, exact argmax retention and loss decrease. Failed
    search terminates this head, never restarts or relaxes the constraints.
    """
    if (
        type(epochs) is not int
        or epochs < 1
        or not np.isfinite(learning_rate)
        or learning_rate <= 0
    ):
        raise ValueError("invalid retention schedule")
    ax, amask, _ = _batch(anchors)
    _batch(terminal)
    initial_scores = _forward(ax, amask, initial.weights1, initial.bias1, initial.weights2)[1]
    chosen = initial_scores.argmax(axis=1)
    pairs = [
        (i, int(chosen[i]), j)
        for i, case in enumerate(anchors)
        for j in range(len(case.candidate_vectors))
        if j != chosen[i]
    ]
    floors = np.array(
        [
            min(1e-4, max(0.0, initial_scores[i, k] - initial_scores[i, j]) * 0.1)
            for i, k, j in pairs
        ]
    )
    size = initial.weights1.size
    width = initial.bias1.size

    def unpack(parameters):
        return replace(
            initial,
            weights1=parameters[:size].reshape(initial.weights1.shape),
            bias1=parameters[size : size + width],
            weights2=parameters[size + width :],
            training_objective="expected_regret",
        )

    current = initial
    history = []
    initial_loss = batch_loss_gradient(current, terminal)[0]
    reason = "epoch_limit"
    for epoch in range(epochs):
        loss, gradient = batch_loss_gradient(current, terminal)
        packed = np.concatenate((current.weights1.ravel(), current.bias1, current.weights2))
        step = -learning_rate * gradient
        h, scores, _ = _forward(ax, amask, current.weights1, current.bias1, current.weights2)
        margins = np.array([scores[i, k] - scores[i, j] for i, k, j in pairs])
        # First-order margin Jacobian. The final nonlinear acceptance test is
        # authoritative; a finite number of projection passes is not a proof.
        jac = []
        for i, k, j in pairs:
            dk = current.weights2 * (1 - h[i, k] ** 2)
            dj = current.weights2 * (1 - h[i, j] ** 2)
            jac.append(
                np.concatenate(
                    (
                        (np.outer(ax[i, k], dk) - np.outer(ax[i, j], dj)).ravel(),
                        dk - dj,
                        h[i, k] - h[i, j],
                    )
                )
            )
        matrix = np.asarray(jac)
        for _ in range(10):
            changed = False
            for index, row in enumerate(matrix):
                deficit = floors[index] - margins[index] - float(row @ step)
                norm = float(row @ row)
                if deficit > 0 and norm > 1e-20:
                    step += (deficit / norm) * row
                    changed = True
            if not changed:
                break
        accepted = False
        for backtrack in range(13):
            candidate = unpack(packed + step * (0.5**backtrack))
            cs = _forward(ax, amask, candidate.weights1, candidate.bias1, candidate.weights2)[1]
            cm = np.array([cs[i, k] - cs[i, j] for i, k, j in pairs])
            after = batch_loss_gradient(candidate, terminal)[0]
            if (
                np.array_equal(cs.argmax(axis=1), chosen)
                and np.all(cm >= floors - 1e-12)
                and after < loss - 1e-12
            ):
                current = candidate
                accepted = True
                history.append(
                    {
                        "epoch": epoch + 1,
                        "loss": after,
                        "backtracks": backtrack,
                        "minimum_margin": float(cm.min()),
                    }
                )
                break
        if not accepted:
            reason = "no_feasible_descent_step"
            break
    return current, {
        "initial_loss": initial_loss,
        "final_loss": batch_loss_gradient(current, terminal)[0],
        "accepted_steps": len(history),
        "stop_reason": reason,
        "protected_cases": len(anchors),
        "history": history,
    }
