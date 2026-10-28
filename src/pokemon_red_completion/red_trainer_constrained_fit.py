"""Bounded feasible updates; measured budgets remain the final authority."""

from dataclasses import replace

import numpy as np

from .red_trainer_budgeted_fit import (
    batch_loss_gradient,
    pairwise_loss_gradient,
    selected_regret,
    unique_budget_replay,
)
from .red_trainer_retention import _batch, _forward


def worse_choice_halfspaces(model, cases):
    """Local margins against worse measured actions, not fixed old argmaxes."""
    x, mask, regret = _batch(cases)
    hidden, scores, _ = _forward(x, mask, model.weights1, model.bias1, model.weights2)
    chosen = scores.argmax(axis=1)
    rows, lower = [], []
    for i, winner in enumerate(chosen):
        for other in range(len(cases[i].candidate_vectors)):
            if regret[i, other] <= regret[i, winner]:
                continue
            dk = model.weights2 * (1 - hidden[i, winner] ** 2)
            dj = model.weights2 * (1 - hidden[i, other] ** 2)
            rows.append(
                np.concatenate(
                    (
                        (np.outer(x[i, winner], dk) - np.outer(x[i, other], dj)).ravel(),
                        dk - dj,
                        hidden[i, winner] - hidden[i, other],
                    )
                )
            )
            margin = float(scores[i, winner] - scores[i, other])
            # A small margin floor avoids rounding through an existing boundary.
            lower.append(min(1e-6, max(0.0, margin) * 0.1) - margin)
    width = model.weights1.size + model.bias1.size + model.weights2.size
    return np.asarray(rows).reshape((-1, width)), np.asarray(lower)


def project_displacement(step, matrix, lower):
    """At most ten cyclic projection passes; no claim of exact feasibility."""
    result = step.copy()
    norms = np.einsum("ij,ij->i", matrix, matrix)
    passes = 0
    for _ in range(10):
        changed = False
        passes += 1
        for row, floor, norm in zip(matrix, lower, norms, strict=True):
            deficit = floor - float(row @ result)
            if deficit > 0 and norm > 1e-20:
                result += (deficit / norm) * row
                changed = True
        if not changed:
            break
    return result, passes


def fit_projected_budget(
    initial,
    terminal,
    anchors,
    budgets,
    *,
    replay,
    epochs,
    learning_rate,
    objective,
    retention_replay,
):
    """Called after shared validation. Rejected weights never become current."""
    loss_gradient = (
        pairwise_loss_gradient if objective == "pairwise_regret" else batch_loss_gradient
    )
    size, width = initial.weights1.size, initial.bias1.size

    def unpack(parameters):
        if not np.all(np.isfinite(parameters)):
            raise ValueError("nonfinite constrained update")
        return replace(
            initial,
            weights1=parameters[:size].reshape(initial.weights1.shape),
            bias1=parameters[size : size + width],
            weights2=parameters[size + width :],
            training_objective=objective,
        )

    def measured(model):
        return {b.name: selected_regret(model, b.cases) + b.offset for b in budgets}

    def feasible(values):
        return all(values[b.name] <= b.maximum for b in budgets)

    def objective_value(model):
        return 0.5 * (loss_gradient(model, terminal)[0] + loss_gradient(model, replay)[0])

    current = initial
    packed = np.concatenate((initial.weights1.ravel(), initial.bias1, initial.weights2))
    first = np.zeros_like(packed)
    second = np.zeros_like(packed)
    history, steps = [], []
    best, best_epoch = None, None
    best_key = (float("inf"), float("inf"))
    stop = "epoch_limit"
    values = measured(current)
    initial_feasible = feasible(values)
    for epoch in range(epochs + 1):
        loss, gradient = loss_gradient(current, terminal)
        old_loss, old_gradient = loss_gradient(current, replay)
        expected = batch_loss_gradient(current, terminal)[0]
        actual = selected_regret(current, terminal)
        admitted = feasible(values)
        key = (actual, expected)
        improved = admitted and key < best_key
        if improved:
            best, best_key, best_epoch = current, key, epoch
        history.append(
            dict(
                epoch=epoch,
                terminal_expected_regret=expected,
                terminal_objective_loss=loss,
                terminal_selected_regret=actual,
                anchor_expected_regret=batch_loss_gradient(current, anchors)[0],
                anchor_objective_loss=loss_gradient(current, anchors)[0],
                replay_objective_loss=old_loss,
                budgets=values,
                feasible=admitted,
                selected=improved,
            )
        )
        if not admitted:
            stop = "initial_budget_infeasible"
            break
        if epoch == epochs:
            break
        gradient = 0.5 * (gradient + old_gradient)
        next_first = 0.9 * first + 0.1 * gradient
        next_second = 0.999 * second + 0.001 * gradient**2
        step = (
            -learning_rate
            * (next_first / (1 - 0.9 ** (epoch + 1)))
            / (np.sqrt(next_second / (1 - 0.999 ** (epoch + 1))) + 1e-8)
        )
        fallback = float(step @ gradient) >= 0
        if fallback:
            norm = float(np.linalg.norm(gradient))
            step = -gradient * min(learning_rate, float(np.linalg.norm(step)) / max(norm, 1e-20))
        full = measured(unpack(packed + step))
        violated = [b for b in budgets if full[b.name] > b.maximum]
        pair_count = passes = 0
        if violated:
            # Deduplicate overlapping groups only for projection, not accounting.
            cases = unique_budget_replay(violated[0].cases, tuple(violated))
            matrix, lower = worse_choice_halfspaces(current, cases)
            pair_count = len(lower)
            step, passes = project_displacement(step, matrix, lower)
        accepted = False
        attempts = []
        for backtrack in range(13):
            candidate = unpack(packed + step * (0.5**backtrack))
            proposed = measured(candidate)
            next_loss = objective_value(candidate)
            accepted = feasible(proposed) and next_loss < 0.5 * (loss + old_loss) - 1e-12
            attempts.append(
                dict(
                    backtrack=backtrack,
                    objective=next_loss,
                    violated=[b.name for b in budgets if proposed[b.name] > b.maximum],
                    accepted=bool(accepted),
                )
            )
            if accepted:
                current = candidate
                packed = np.concatenate((current.weights1.ravel(), current.bias1, current.weights2))
                first, second, values = next_first, next_second, proposed
                break
        steps.append(
            dict(
                epoch=epoch + 1,
                accepted=bool(accepted),
                full_step_violations=[b.name for b in violated],
                projection_pairs=pair_count,
                projection_passes=passes,
                gradient_fallback=bool(fallback),
                attempts=attempts,
            )
        )
        if not accepted:
            stop = "no_feasible_descent_step"
            break
    receipt = dict(
        objective=objective,
        update_rule="projected_budget_v1",
        epochs=epochs,
        learning_rate=learning_rate,
        feasible_checkpoints=sum(h["feasible"] for h in history),
        selected_epoch=best_epoch,
        initial_selected_regret=selected_regret(initial, terminal),
        final_selected_regret=None if best is None else best_key[0],
        initial_expected_regret=batch_loss_gradient(initial, terminal)[0],
        final_expected_regret=None if best is None else best_key[1],
        initial_feasible=bool(initial_feasible),
        accepted_steps=sum(s["accepted"] for s in steps),
        stop_reason=stop,
        steps=steps,
        history=history,
    )
    if retention_replay != "anchors":
        receipt["retention_replay"] = dict(
            mode=retention_replay,
            anchor_cases=len(anchors),
            budget_cases=sum(len(b.cases) for b in budgets),
            unique_replay_cases=len(replay),
            fresh_weight=0.5,
            replay_weight=0.5,
        )
    return best, receipt
