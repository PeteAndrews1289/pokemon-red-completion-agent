"""Bounded TRAIN-only ridge selection; never accept heldout labels here."""

from dataclasses import replace

import numpy as np

from .living_dex_option_value import (
    evaluate_living_dex_option_value,
    fit_living_dex_option_value,
)

RIDGE_MULTIPLIERS = (0.25, 0.5, 1.0, 2.0, 4.0)


def curriculum_mse(model, rows):
    """Unit-weight prediction loss, with no invented observed-arm propensity."""
    features = np.asarray([row.features for row in rows], dtype=np.float64)
    targets = np.asarray([row.outcome.target_vector for row in rows], dtype=np.float64)
    prediction = np.clip(
        model.intercept
        + ((features - model.feature_mean) / model.feature_scale) @ model.coefficients,
        0.0,
        1.0,
    )
    return float(np.mean((prediction - targets) ** 2))


def fit_retaining_prior(prior, rows, curriculum, *, retained_curriculum=()):
    """Keep the 2% prior-loss limit fixed and select solely on new TRAIN loss.

    Caller authenticates the complete prior inventory. No mutable target weight,
    fabricated counterfactual, development metric or chosen destination is used.
    The economy head is unchanged: teacher demonstrations do not train that head.
    """
    if not curriculum or any(
        r.partition != "train" for r in (*rows, *curriculum, *retained_curriculum)
    ):
        raise ValueError("retention search requires TRAIN-only evidence")
    old = evaluate_living_dex_option_value(
        prior, rows, expected_partition="train", curriculum_examples=retained_curriculum
    )
    candidates, metrics = [], []
    for multiplier in RIDGE_MULTIPLIERS:
        fitted = fit_living_dex_option_value(
            rows,
            feature_version=prior.feature_version,
            ridge=prior.ridge * multiplier,
            maximum_importance_weight=prior.maximum_importance_weight,
            curriculum_examples=(*retained_curriculum, *curriculum),
        )
        model = replace(fitted.model, economy_head=prior.economy_head)
        fitted = replace(fitted, model=model)
        retained = evaluate_living_dex_option_value(
            model, rows, expected_partition="train", curriculum_examples=retained_curriculum
        )
        new = curriculum_mse(model, curriculum)
        passed = retained.weighted_mse <= 1.02 * old.weighted_mse
        metrics.append(
            dict(
                ridge=model.ridge,
                old_mse=retained.weighted_mse,
                new_train_mse=new,
                retained=passed,
                model_sha256=model.model_sha256,
            )
        )
        if passed:
            candidates.append((new, model.ridge, fitted))
    report = dict(
        schema="pokemon.core.train-only-retention-selection.v1",
        prior_mse=old.weighted_mse,
        maximum_old_error_ratio=1.02,
        candidates=metrics,
        heldout_queries=0,
        economy_head_changed=False,
    )
    if not candidates:
        return None, report
    chosen = min(candidates, key=lambda item: item[:2])[2]
    report["selected_model_sha256"] = chosen.model.model_sha256
    return chosen, report
