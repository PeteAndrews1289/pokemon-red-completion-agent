"""Frozen conditional-effect knowledge with learned battle-value coefficients.

Unsupported actions have no auxiliary representation; no action is banned or
chosen here. Ordinary visible features remain available for all actions, including
sleep. Application probabilities are conditional on execution, never execution odds.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.special import expit

from .red_balanced_status_features import (
    BALANCED_STATUS_NAMES,
    BALANCED_STATUS_SCHEMA,
    COMPACT_STATUS_NAMES,
)
from .red_trainer_practice_head import TrainerHeadError, TrainerHeadModel

EFFECT_SCHEMA = "pokemon.core.battle.conditional-effect-augmentation.v1"
SUPPORTED = ("heal", "rest", "confusion")


def effect_values(candidates, weights):
    x = np.asarray(candidates, dtype=float)
    w = np.asarray(weights, dtype=float)
    if (x.ndim != 2 or x.shape[1] != len(BALANCED_STATUS_NAMES) or
            w.shape != (1 + len(COMPACT_STATUS_NAMES),) or
            not np.isfinite(x).all() or not np.isfinite(w).all()):
        raise TrainerHeadError("conditional-effect inputs differ")
    compact = x[:, -len(COMPACT_STATUS_NAMES):]
    flags = compact[:, [COMPACT_STATUS_NAMES.index("choice.effect." + f) for f in SUPPORTED]]
    if not np.isin(flags, [0., 1.]).all() or (flags.sum(axis=1) > 1).any():
        raise TrainerHeadError("conditional-effect family flags differ")
    supported = flags.sum(axis=1)
    p = expit(w[0] + compact @ w[1:])
    return np.column_stack((supported, supported * p))


@dataclass(frozen=True, slots=True)
class EffectSelectorHead(TrainerHeadModel):
    effect_weights: tuple[float, ...] = ()
    effect_sha256: str = ""
    effect_readout: tuple[float, float] = (0., 0.)

    def __post_init__(self):
        TrainerHeadModel.__post_init__(self)
        if (self.schema_id != BALANCED_STATUS_SCHEMA or
                self.feature_names != BALANCED_STATUS_NAMES or
                len(self.effect_weights) != 1 + len(COMPACT_STATUS_NAMES) or
                not np.isfinite(self.effect_weights).all() or
                len(self.effect_readout) != 2 or not np.isfinite(self.effect_readout).all() or
                len(self.effect_sha256) != 64 or
                any(c not in "0123456789abcdef" for c in self.effect_sha256)):
            raise TrainerHeadError("conditional-effect checkpoint differs")
        object.__setattr__(self, "effect_weights", tuple(self.effect_weights))
        object.__setattr__(self, "effect_readout", tuple(self.effect_readout))

    def scores(self, candidates):
        return (TrainerHeadModel.scores(self, candidates) +
                effect_values(candidates, self.effect_weights) @ np.asarray(self.effect_readout))

    def to_dict(self) -> dict[str, object]:
        return {**TrainerHeadModel.to_dict(self), "format_version": 2,
                "auxiliary_effect": {"schema": EFFECT_SCHEMA,
                    "source_fit_sha256": self.effect_sha256,
                    "feature_names": ["intercept", *COMPACT_STATUS_NAMES],
                    "families": list(SUPPORTED), "conditional_on_execution": True,
                    "weights": list(self.effect_weights), "readout": list(self.effect_readout)}}


def augment_head(head: TrainerHeadModel, weights, digest: str, readout=(0., 0.)):
    if isinstance(head, EffectSelectorHead):
        raise TrainerHeadError("cannot stack conditional-effect heads")
    return EffectSelectorHead(head.schema_id, head.feature_names, head.weights1, head.bias1,
        head.weights2, head.training_seed, head.training_objective,
        tuple(weights), digest, tuple(readout))


def restore_effect(head: TrainerHeadModel, value: Any) -> EffectSelectorHead:
    if (not isinstance(value, Mapping) or value.get("schema") != EFFECT_SCHEMA or
            value.get("feature_names") != ["intercept", *COMPACT_STATUS_NAMES] or
            value.get("families") != list(SUPPORTED) or
            value.get("conditional_on_execution") is not True):
        raise TrainerHeadError("conditional-effect semantics differ")
    return augment_head(head, value["weights"], value["source_fit_sha256"], value["readout"])
