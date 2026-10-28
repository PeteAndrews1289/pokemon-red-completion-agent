"""Fixed TRAIN-only trajectories with measured-regret checkpoint constraints.

Old mistakes are not frozen. Only checkpoints satisfying every declared numeric
budget can be returned; unconstrained intermediate iterates never reach actors.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from pokemon_red_completion.red_trainer_practice_head import TrainerHeadExample, TrainerHeadModel
from pokemon_red_completion.red_trainer_retention import _batch, _forward, batch_loss_gradient


@dataclass(frozen=True)
class RegretBudget:
    name: str
    cases: tuple[TrainerHeadExample, ...]
    maximum: float
    offset: float = 0.0


def selected_regret(model: TrainerHeadModel, cases: tuple[TrainerHeadExample, ...]) -> float:
    x, mask, regret = _batch(cases)
    scores = _forward(x, mask, model.weights1, model.bias1, model.weights2)[1]
    return float(regret[np.arange(len(cases)), scores.argmax(axis=1)].mean())


def unique_budget_replay(anchors, budgets):
    """One optimization vote per exact measured feature/return example.

    Group overlap must not change replay weight. Different measured returns are
    retained, not averaged or resolved by a preferred label. Constraint rows and
    their original multiplicities remain untouched. Only mean-return objectives
    use this pool; best-index/probability metadata do not alter those objectives.
    """
    unique = {}
    for cases in (anchors, *(budget.cases for budget in budgets)):
        _batch(cases)
        for case in cases:
            key = (tuple(tuple(v) for v in case.candidate_vectors), tuple(case.mean_returns))
            unique.setdefault(key, case)
    return tuple(unique[key] for key in sorted(unique))


def pairwise_loss_gradient(model: TrainerHeadModel, cases: tuple[TrainerHeadExample, ...]):
    """Measured-return-weighted ranking loss with a nonvanishing wrong-margin signal."""
    x, mask, regret = _batch(cases)
    hidden, scores, _ = _forward(x, mask, model.weights1, model.bias1, model.weights2)
    scores = np.where(mask, scores, 0.0)
    gap = regret[:, None, :] - regret[:, :, None]
    valid = mask[:, :, None] & mask[:, None, :] & (gap > 0)
    weights = np.where(valid, gap, 0.0) / np.maximum(1, valid.sum(axis=(1, 2)))[:, None, None]
    wrong_margin = scores[:, None, :] - scores[:, :, None]
    loss = (weights * np.logaddexp(0.0, wrong_margin)).sum(axis=(1, 2)).mean()
    pair_derivative = weights * np.exp(-np.logaddexp(0.0, -wrong_margin))
    residual = (pair_derivative.sum(axis=1) - pair_derivative.sum(axis=2)) / len(cases)
    dh = residual[..., None] * model.weights2 * (1.0 - hidden * hidden)
    g1 = np.einsum("ncf,nch->fh", x, dh)
    gb = dh.sum(axis=(0, 1))
    g2 = np.einsum("nch,nc->h", hidden, residual)
    return float(loss), np.concatenate((g1.ravel(), gb, g2))


def fit_budgeted_head(
    initial: TrainerHeadModel,
    terminal: tuple[TrainerHeadExample, ...],
    anchors: tuple[TrainerHeadExample, ...],
    budgets: tuple[RegretBudget, ...],
    *,
    epochs: int = 2400,
    learning_rate: float = 0.005,
    objective: str = "expected_regret",
    retention_replay: str = "anchors",
    update_rule: str = "adam",
    allow_initial_infeasibility: bool = False,
    trainable_input_rows: tuple[int, ...] | None = None,
):
    """One Adam trajectory; best feasible actual-regret checkpoint, no restart.

    The optimization loss gives old and terminal groups equal weight. Selection is
    lexicographic (terminal argmax regret, terminal expected regret, earliest epoch).
    All inputs and selection constraints must be TRAIN-only, fixed before fitting.
    """
    if (
        type(epochs) is not int
        or epochs < 1
        or not np.isfinite(learning_rate)
        or learning_rate <= 0
    ):
        raise ValueError("invalid budgeted schedule")
    if not budgets or len({b.name for b in budgets}) != len(budgets):
        raise ValueError("unique nonempty regret budgets required")
    if objective not in {"expected_regret", "pairwise_regret"}:
        raise ValueError("unknown budgeted objective")
    if retention_replay not in {"anchors", "unique_budget_cases_v1"}:
        raise ValueError("unknown retention replay mode")
    if update_rule not in {
        "adam",
        "projected_budget_v1",
        "joint_ranking_v1",
        "joint_ranking_curvature_v1",
    }:
        raise ValueError("unknown budgeted update rule")
    if type(allow_initial_infeasibility) is not bool or (
        allow_initial_infeasibility
        and update_rule not in {"joint_ranking_v1", "joint_ranking_curvature_v1"}
    ):
        raise ValueError("initial feasibility recovery requires an explicit joint-ranking flag")
    if trainable_input_rows is not None and (
        update_rule != "adam"
        or type(trainable_input_rows) is not tuple
        or not trainable_input_rows
        or any(type(row) is not int or not 0 <= row < len(initial.feature_names)
               for row in trainable_input_rows)
        or len(set(trainable_input_rows)) != len(trainable_input_rows)
    ):
        raise ValueError("input-row freezing requires unique valid integer rows and Adam")
    loss_gradient = (
        pairwise_loss_gradient if objective == "pairwise_regret" else batch_loss_gradient
    )
    for budget in budgets:
        if not np.isfinite(budget.maximum) or not np.isfinite(budget.offset):
            raise ValueError("finite regret budgets required")
        _batch(budget.cases)
    _batch(anchors)
    _batch(terminal)
    replay = (
        unique_budget_replay(anchors, budgets)
        if retention_replay == "unique_budget_cases_v1"
        else anchors
    )
    if update_rule in {"joint_ranking_v1", "joint_ranking_curvature_v1"}:
        from .red_trainer_joint_ranking import fit_joint_ranking

        return fit_joint_ranking(
            initial,
            terminal,
            anchors,
            budgets,
            curvature_correction=update_rule == "joint_ranking_curvature_v1",
            allow_initial_infeasibility=allow_initial_infeasibility,
            replay=replay,
            epochs=epochs,
            learning_rate=learning_rate,
            objective=objective,
            retention_replay=retention_replay,
        )
    if update_rule == "projected_budget_v1":
        from .red_trainer_constrained_fit import fit_projected_budget

        return fit_projected_budget(
            initial,
            terminal,
            anchors,
            budgets,
            replay=replay,
            epochs=epochs,
            learning_rate=learning_rate,
            objective=objective,
            retention_replay=retention_replay,
        )
    packed = np.concatenate((initial.weights1.ravel(), initial.bias1, initial.weights2))
    parameter_mask = None
    initial_packed = None
    if trainable_input_rows is not None:
        row_mask = np.zeros_like(initial.weights1, dtype=bool)
        row_mask[list(trainable_input_rows), :] = True
        parameter_mask = np.concatenate((row_mask.ravel(),
            np.zeros(initial.bias1.size + initial.weights2.size, dtype=bool)))
        initial_packed = packed.copy()
    first = np.zeros_like(packed)
    second = np.zeros_like(packed)
    size, width = initial.weights1.size, initial.bias1.size
    current = initial
    best = None
    best_key = (float("inf"), float("inf"))
    best_epoch = None
    history = []
    feasible = 0
    for epoch in range(epochs + 1):
        loss, gradient = loss_gradient(current, terminal)
        old_loss, old_gradient = loss_gradient(current, replay)
        expected_loss = (
            batch_loss_gradient(current, terminal)[0] if objective == "pairwise_regret" else loss
        )
        actual = selected_regret(current, terminal)
        measured = {
            budget.name: selected_regret(current, budget.cases) + budget.offset
            for budget in budgets
        }
        admitted = all(measured[b.name] <= b.maximum for b in budgets)
        key = (actual, expected_loss)
        improved = admitted and key < best_key
        if admitted:
            feasible += 1
        if improved:
            best, best_key, best_epoch = current, key, epoch
        if epoch % 25 == 0 or improved or epoch == epochs:
            history.append(
                {
                    "epoch": epoch,
                    "terminal_expected_regret": expected_loss,
                    "terminal_objective_loss": loss,
                    "terminal_selected_regret": actual,
                    "anchor_expected_regret": batch_loss_gradient(current, anchors)[0]
                    if objective == "pairwise_regret" or replay is not anchors
                    else old_loss,
                    "anchor_objective_loss": (
                        loss_gradient(current, anchors)[0] if replay is not anchors else old_loss
                    ),
                    "budgets": measured,
                    "feasible": admitted,
                    "selected": improved,
                }
            )
            if retention_replay != "anchors":
                history[-1]["replay_objective_loss"] = old_loss
        if epoch == epochs:
            break
        gradient = 0.5 * (gradient + old_gradient)
        if parameter_mask is not None:
            gradient[~parameter_mask] = 0.0
        first = 0.9 * first + 0.1 * gradient
        second = 0.999 * second + 0.001 * gradient**2
        packed = packed - learning_rate * (first / (1 - 0.9 ** (epoch + 1))) / (
            np.sqrt(second / (1 - 0.999 ** (epoch + 1))) + 1e-8
        )
        if parameter_mask is not None:
            packed[~parameter_mask] = initial_packed[~parameter_mask]
            if not np.array_equal(packed[~parameter_mask].view(np.uint64),
                                  initial_packed[~parameter_mask].view(np.uint64)):
                raise ValueError("frozen fitter coordinates changed")
        if not np.all(np.isfinite(packed)):
            raise ValueError("nonfinite budgeted training iterate")
        current = replace(
            initial,
            weights1=packed[:size].reshape(initial.weights1.shape).copy(),
            bias1=packed[size : size + width].copy(),
            weights2=packed[size + width :].copy(),
            training_objective=objective,
        )
    receipt = {
        "objective": objective,
        "epochs": epochs,
        "learning_rate": learning_rate,
        "feasible_checkpoints": feasible,
        "selected_epoch": best_epoch,
        "initial_selected_regret": selected_regret(initial, terminal),
        "final_selected_regret": None if best is None else best_key[0],
        "initial_expected_regret": batch_loss_gradient(initial, terminal)[0],
        "final_expected_regret": None if best is None else best_key[1],
        "history": history,
    }
    if parameter_mask is not None:
        receipt["parameter_update_scope"] = dict(
            mode="input_rows_v1", trainable_input_rows=list(trainable_input_rows),
            trainable_input_features=[initial.feature_names[row] for row in trainable_input_rows],
            trainable_coordinates=int(parameter_mask.sum()),
            bias1_frozen=True, weights2_frozen=True, other_input_rows_frozen=True,
            frozen_coordinates_bit_identical=True,
        )
    if retention_replay != "anchors":
        receipt["retention_replay"] = {
            "mode": retention_replay,
            "anchor_cases": len(anchors),
            "budget_cases": sum(len(b.cases) for b in budgets),
            "unique_replay_cases": len(replay),
            "fresh_weight": 0.5,
            "replay_weight": 0.5,
        }
    return best, receipt
