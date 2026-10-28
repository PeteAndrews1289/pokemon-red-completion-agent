"""Prospective conservative RNG preference learning, never rewriting native returns."""

from dataclasses import replace

import numpy as np
from audit_red_randomized_collection import validate_target
from scipy.special import expit

from pokemon_red_completion.red_balanced_status_features import (
    BALANCED_STATUS_NAMES as N,
)
from pokemon_red_completion.red_balanced_status_features import (
    COMPACT_STATUS_NAMES,
)
from pokemon_red_completion.red_effect_selector_head import effect_values


def additive_basis(actor):
    """Fixed per-feature transform, learned additive outputs; no action masks."""
    width = len(COMPACT_STATUS_NAMES)
    weights = np.zeros((len(N), width))
    weights[-width:] = np.eye(width)
    output = np.zeros(width)
    output[COMPACT_STATUS_NAMES.index("choice.status")] = -1/np.tanh(1.)
    return replace(actor, move=replace(actor.move, weights1=weights, bias1=np.zeros(width),
        weights2=output, effect_readout=(0., 0.)))


def extend_randomized(old, actor, targets, *, seeds, continuation_sha):
    if not targets or len({t["capture_id"] for t in targets}) != len(targets):
        raise ValueError("nonempty unique RNG contexts required")
    contrast, desired, weights, diagnostics, statuses = [], [], [], [], []
    for target in targets:
        x, y = validate_target(target, actor.train_root_ids, seeds, continuation_sha)
        status = next(i for i, v in enumerate(x) if v[N.index("choice.status")])
        gaps = y[status]-y[1-status]
        gap, se = float(gaps.mean()), float(gaps.std(ddof=1)/32**.5)
        probability = float(expit(gap-se-.05))
        hidden = np.tanh(x@actor.move.weights1+actor.move.bias1)
        extra = effect_values(x, actor.move.effect_weights)
        contrast.append(np.append(hidden[status]-hidden[1-status], extra[status]-extra[1-status]))
        desired.append(probability)
        weights.append(.75/len(targets)*np.clip(abs(gap), .1, 4.)/(1+se))
        statuses.append(status)
        diagnostics.append({"capture_id": target["capture_id"], "status_gap": gap,
            "descriptive_standard_error": se, "conservative_soft_target": probability})
    return replace(old, contrast=np.vstack((old.contrast, contrast)),
        desired=np.append(old.desired, desired), weights=np.append(.25*old.weights, weights),
        status_indices=(*old.status_indices, *statuses)), diagnostics
