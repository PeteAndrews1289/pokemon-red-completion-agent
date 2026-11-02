"""Read-only diagnostics for a shared candidate scorer; never fit or change weights."""

import numpy as np

from .red_trainer_budgeted_fit import (
    RegretBudget,
    batch_loss_gradient,
    pairwise_loss_gradient,
    selected_regret,
    unique_budget_replay,
)


def score_jacobian(model, vector):
    """Derivative in weights1/bias1/weights2 order, with no parameter mutation."""
    x = np.asarray(vector, dtype=float)
    if x.shape != (len(model.feature_names),) or not np.all(np.isfinite(x)):
        raise ValueError("invalid score vector")
    hidden = np.tanh(x @ model.weights1 + model.bias1)
    derivative = model.weights2 * (1 - hidden**2)
    return np.concatenate((np.outer(x, derivative).ravel(), derivative, hidden))


def nullspace_component_ratio(rows, vector):
    """First-order freedom while freezing these margins, not nonlinear feasibility.

    Freezing every old margin is stricter than preserving numeric mean regret.
    A nonzero result establishes a local linear degree of freedom only.
    """
    matrix = np.asarray(rows, dtype=float)
    vector = np.asarray(vector, dtype=float)
    if (
        vector.ndim != 1
        or matrix.ndim != 2
        or matrix.shape[1] != len(vector)
        or not np.all(np.isfinite(matrix))
        or not np.all(np.isfinite(vector))
    ):
        raise ValueError("invalid tangent matrix")
    if not len(matrix):
        return {"rank": 0, "threshold": 0.0, "ratio": 1.0 if np.linalg.norm(vector) else 0.0}
    _, values, vh = np.linalg.svd(matrix, full_matrices=False)
    threshold = float(values[0] * 1e-10) if len(values) else 0.0
    rank = int(np.sum(values > threshold))
    residual = vector - vh[:rank].T @ (vh[:rank] @ vector)
    norm = float(np.linalg.norm(vector))
    return {
        "rank": rank,
        "threshold": threshold,
        "ratio": float(np.linalg.norm(residual) / norm) if norm else 0.0,
    }


def inspect_rankings(model, fresh, retained):
    """Return input collisions, frozen scores and analytic gradient interference.

    Directional derivatives are at the parent only. They are not executed steps,
    trained choices, global infeasibility proofs or transfer measurements.
    """
    if not fresh or not retained or any(not cases for cases in retained.values()):
        raise ValueError("nonempty measured inventories required")
    budgets = tuple(RegretBudget(name, tuple(cases), 0) for name, cases in retained.items())
    replay = unique_budget_replay(budgets[0].cases, budgets)
    _, gradient = pairwise_loss_gradient(model, tuple(fresh))
    _, replay_gradient = pairwise_loss_gradient(model, replay)
    _, expected_gradient = batch_loss_gradient(model, tuple(fresh))
    combined = 0.5 * (gradient + replay_gradient)
    adam_direction = -0.005 * combined / (abs(combined) + 1e-8)
    individual = [pairwise_loss_gradient(model, (case,))[1] for case in fresh]
    old_rows, margin_rows = [], []
    for group, cases in retained.items():
        for index, case in enumerate(cases):
            scores = model.scores(case.candidate_vectors)
            chosen = int(scores.argmax())
            old_rows.append((group, index, case, chosen))
            for other, value in enumerate(case.mean_returns):
                if value < case.mean_returns[chosen]:
                    margin_rows.append(
                        {
                            "group": group,
                            "case": index,
                            "chosen": chosen,
                            "other": other,
                            "margin": float(scores[chosen] - scores[other]),
                            "return_gap": float(case.mean_returns[chosen] - value),
                            "jacobian": score_jacobian(model, case.candidate_vectors[chosen])
                            - score_jacobian(model, case.candidate_vectors[other]),
                        }
                    )
    # Remove duplicate derivatives only for linear algebra, not group accounting.
    width = model.weights1.size + model.bias1.size + model.weights2.size
    matrix = np.asarray(sorted({tuple(row["jacobian"]) for row in margin_rows})).reshape(-1, width)
    cases = []
    for index, case in enumerate(fresh):
        x = np.asarray(case.candidate_vectors)
        hidden = np.tanh(x @ model.weights1 + model.bias1)
        scores = hidden @ model.weights2
        chosen = int(scores.argmax())
        bests = [i for i, value in enumerate(case.mean_returns) if value == max(case.mean_returns)]
        best = max(bests, key=lambda i: scores[i])
        jac = score_jacobian(model, x[best]) - score_jacobian(model, x[chosen])
        aliases = []
        if chosen != best:
            for group, old_index, old, old_chosen in old_rows:
                vectors = list(old.candidate_vectors)
                if tuple(x[chosen]) not in vectors or tuple(x[best]) not in vectors:
                    continue
                a, b = vectors.index(tuple(x[chosen])), vectors.index(tuple(x[best]))
                aliases.append(
                    {
                        "group": group,
                        "case": old_index,
                        "old_selected_in_pair": old_chosen in (a, b),
                        "old_return_advantage_for_new_best": float(
                            old.mean_returns[b] - old.mean_returns[a]
                        ),
                    }
                )
        jac_norm = float(np.linalg.norm(jac))
        opposition = []
        for row in margin_rows:
            denom = jac_norm * float(np.linalg.norm(row["jacobian"]))
            if denom:
                opposition.append(
                    {
                        **{
                            k: row[k]
                            for k in ("group", "case", "chosen", "other", "margin", "return_gap")
                        },
                        "cosine": float(jac @ row["jacobian"] / denom),
                        "initial_adam_margin_derivative": float(row["jacobian"] @ adam_direction),
                    }
                )
        cases.append(
            {
                "case": index,
                "chosen": chosen,
                "best": best,
                "returns": list(case.mean_returns),
                "scores": scores.tolist(),
                "chosen_probability": float(model.probabilities(case.candidate_vectors)[chosen]),
                "desired_margin": float(scores[best] - scores[chosen]),
                "exact_pair_aliases": aliases,
                "saturated_fraction_abs_tanh_gt_0999": float(np.mean(abs(hidden) > 0.999)),
                "desired_margin_derivatives": {
                    "negative_fresh_gradient": float(jac @ -gradient),
                    "negative_replay_gradient": float(jac @ -replay_gradient),
                    "negative_combined_gradient": float(jac @ -combined),
                    "initial_adam": float(jac @ adam_direction),
                    "negative_individual_gradients": [float(jac @ -g) for g in individual],
                },
                "old_margin_nullspace": nullspace_component_ratio(matrix, jac),
                "strongest_opposition": sorted(opposition, key=lambda r: r["cosine"])[:3],
            }
        )
    weakest = sorted(margin_rows, key=lambda row: row["margin"])[:5]
    return {
        "fresh_cases": len(fresh),
        "unique_replay_cases": len(replay),
        "retained_budgets": {
            name: {"cases": len(rows), "parent_regret": selected_regret(model, tuple(rows))}
            for name, rows in retained.items()
        },
        "fresh_expected_regret_directional_derivatives": {
            "negative_combined_gradient": float(expected_gradient @ -combined),
            "initial_adam": float(expected_gradient @ adam_direction),
        },
        "gradient_norms": {
            "fresh": float(np.linalg.norm(gradient)),
            "replay": float(np.linalg.norm(replay_gradient)),
        },
        "weakest_old_margins": [
            {
                **{k: row[k] for k in ("group", "case", "chosen", "other", "margin", "return_gap")},
                "initial_adam_margin_derivative": float(row["jacobian"] @ adam_direction),
            }
            for row in weakest
        ],
        "cases": cases,
        "parameter_updates": 0,
        "limitations": [
            "Local analytic derivatives, not actual update outcomes or a feasible trained model.",
            "No exact pair collision does not establish sufficient state information.",
            "Tangent freedom freezes old margins, a stronger condition than mean-budget retention.",
            "Sampled return disagreements may reflect variation, not a proven state alias.",
        ],
    }
