"""Outcome-fitted damage ranking over observable mechanics interactions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .battle_semantics import MAX_EFFECTIVE_POWER
from .red_trainer_practice_features import MOVE_FEATURE_NAMES, MOVE_SCHEMA_ID

MODEL_ID = "pokemon.core.battle.damage-interaction-linear.v1"
PROJECTION_ID = "pokemon.core.battle.damage-interactions.v1"
FEATURE_NAMES = (
    "physical_pressure",
    "special_pressure",
    "accuracy_physical_pressure",
    "accuracy_special_pressure",
    "priority_speed_disadvantage",
    "pp_pressure",
    "opponent_hp_pressure",
    "player_hp_pressure",
)
RIDGE = 0.001
SEED = 23092321
_AT = {
    name: MOVE_FEATURE_NAMES.index(name)
    for name in (
        "move.category.physical",
        "move.category.special",
        "move.effective_power_fraction",
        "interaction.physical_attack_over_estimated_defense",
        "interaction.special_over_estimated_special",
        "state.player_attack_stage_fraction",
        "state.opponent_defense_stage_fraction",
        "observable.player.special_stage",
        "interaction.physical_x_player_burn",
        "state.player_accuracy_stage_fraction",
        "move.accuracy",
        "interaction.player_speed_over_estimated_speed",
        "move.priority",
        "move.pp_fraction",
        "state.opponent_hp_ratio",
        "state.player_hp_ratio",
    )
}


def _stage(value: float) -> float:
    scaled = value * 6.0
    rounded = round(scaled)
    if not -6 <= rounded <= 6 or not math.isclose(scaled, rounded, abs_tol=1e-8):
        raise ValueError("damage interaction requires a valid visible stat stage")
    return (2 + rounded) / 2 if rounded >= 0 else 2 / (2 - rounded)


def project_damage_interactions(vectors: Sequence[Sequence[float]]) -> NDArray[np.float64]:
    raw = np.asarray(vectors, dtype=np.float64)
    if (
        raw.ndim != 2
        or raw.shape[0] < 1
        or raw.shape[1] != len(MOVE_FEATURE_NAMES)
        or not np.isfinite(raw).all()
        or np.any(raw < -1)
        or np.any(raw > 1)
    ):
        raise ValueError("damage interaction input differs from the public move schema")
    rows = []
    for row in raw:

        def at(name: str, values: NDArray[np.float64] = row) -> float:
            return float(values[_AT[name]])

        physical, special = at("move.category.physical"), at("move.category.special")
        if (physical, special) not in ((1.0, 0.0), (0.0, 1.0)):
            raise ValueError("damage interaction requires one damaging move category")
        burn = at("interaction.physical_x_player_burn")
        if burn not in (0.0, physical):
            raise ValueError("damage interaction burn flag differs")
        effective = at("move.effective_power_fraction") * MAX_EFFECTIVE_POWER / 100.0
        rp = 4 * at("interaction.physical_attack_over_estimated_defense")
        rs = 4 * at("interaction.special_over_estimated_special")
        if (not physical and rp != 0) or (not special and rs != 0):
            raise ValueError("damage interaction stat ratio is not category gated")
        up = (
            effective
            * rp
            * _stage(at("state.player_attack_stage_fraction"))
            / _stage(at("state.opponent_defense_stage_fraction"))
            * (0.5 if burn else 1.0)
        )
        us = effective * rs * _stage(at("observable.player.special_stage"))
        if min(effective, rp, rs, up, us) < 0:
            raise ValueError("damage interaction pressure is negative")
        p, s = up / (1 + up), us / (1 + us)
        t = p + s
        accuracy = float(
            np.clip(at("move.accuracy") * _stage(at("state.player_accuracy_stage_fraction")), 0, 1)
        )
        speed_disadvantage = float(
            np.clip(1 - 4 * at("interaction.player_speed_over_estimated_speed"), 0, 1)
        )
        rows.append(
            (
                p,
                s,
                accuracy * p,
                accuracy * s,
                at("move.priority") * speed_disadvantage,
                at("move.pp_fraction") * t,
                at("state.opponent_hp_ratio") * t,
                at("state.player_hp_ratio") * t,
            )
        )
    features = np.asarray(rows, dtype=np.float64)
    if not np.isfinite(features).all() or np.any(features < 0) or np.any(features > 1):
        raise ValueError("damage interaction projection is outside its bounded domain")
    return features


@dataclass(frozen=True, slots=True)
class DamageInteractionHead:
    coefficients: NDArray[np.float64]
    train_dataset_sha256: str
    schema_id: str = MOVE_SCHEMA_ID
    feature_names: tuple[str, ...] = MOVE_FEATURE_NAMES
    training_seed: int = SEED

    def __post_init__(self) -> None:
        weights = np.asarray(self.coefficients, dtype=np.float64)
        if (
            weights.shape != (len(FEATURE_NAMES),)
            or not np.isfinite(weights).all()
            or self.schema_id != MOVE_SCHEMA_ID
            or self.feature_names != MOVE_FEATURE_NAMES
            or self.training_seed != SEED
            or len(self.train_dataset_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.train_dataset_sha256)
        ):
            raise ValueError("damage interaction checkpoint differs")
        weights = weights.copy()
        weights.setflags(write=False)
        object.__setattr__(self, "coefficients", weights)

    def scores(self, candidates: Sequence[Sequence[float]]) -> NDArray[np.float64]:
        return project_damage_interactions(candidates) @ self.coefficients

    def probabilities(self, candidates: Sequence[Sequence[float]]) -> NDArray[np.float64]:
        scores = self.scores(candidates)
        shifted = np.exp(scores - max(scores))
        return shifted / sum(shifted)

    def predict_index(self, candidates: Sequence[Sequence[float]]) -> int:
        return int(np.argmax(self.scores(candidates)))

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "model_id": MODEL_ID,
            "projection_id": PROJECTION_ID,
            "schema_id": self.schema_id,
            "feature_names": list(self.feature_names),
            "interaction_feature_names": list(FEATURE_NAMES),
            "coefficients": self.coefficients.tolist(),
            "ridge": RIDGE,
            "training_seed": self.training_seed,
            "train_dataset_sha256": self.train_dataset_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> DamageInteractionHead:
        coefficients = value.get("coefficients")
        dataset_sha256 = value.get("train_dataset_sha256")
        if (
            set(value)
            != {
                "format_version",
                "model_id",
                "projection_id",
                "schema_id",
                "feature_names",
                "interaction_feature_names",
                "coefficients",
                "ridge",
                "training_seed",
                "train_dataset_sha256",
            }
            or type(value.get("format_version")) is not int
            or value.get("format_version") != 1
            or value.get("model_id") != MODEL_ID
            or value.get("projection_id") != PROJECTION_ID
            or value.get("schema_id") != MOVE_SCHEMA_ID
            or value.get("feature_names") != list(MOVE_FEATURE_NAMES)
            or value.get("interaction_feature_names") != list(FEATURE_NAMES)
            or type(value.get("ridge")) is not float
            or value.get("ridge") != RIDGE
            or type(value.get("training_seed")) is not int
            or not isinstance(dataset_sha256, str)
            or not isinstance(coefficients, list)
            or any(type(weight) not in (int, float) for weight in coefficients)
        ):
            raise ValueError("damage interaction serialized schema differs")
        try:
            result = cls(
                np.asarray(coefficients, dtype=np.float64), dataset_sha256
            )
        except (TypeError, ValueError) as error:
            raise ValueError("damage interaction serialized coefficients differ") from error
        if result.to_dict() != dict(value):
            raise ValueError("damage interaction checkpoint round trip differs")
        return result


def fit_damage_interaction_head(
    examples: Sequence[tuple[Sequence[Sequence[float]], Sequence[float]]],
    *,
    train_dataset_sha256: str,
) -> DamageInteractionHead:
    if not examples:
        raise ValueError("damage interaction fit needs TRAIN targets")
    differences, targets = [], []
    for vectors, returns in examples:
        if (
            len(vectors) != 4
            or len(returns) != 4
            or not all(math.isfinite(x) and 0 <= x <= 1 for x in returns)
        ):
            raise ValueError("damage interaction fit needs four finite native returns")
        projected = project_damage_interactions(vectors)
        for first in range(4):
            for second in range(first + 1, 4):
                differences.append(projected[first] - projected[second])
                targets.append(returns[first] - returns[second])
    x, y = np.asarray(differences), np.asarray(targets)
    n = len(y)
    coefficients = np.linalg.solve(x.T @ x / n + RIDGE * np.eye(len(FEATURE_NAMES)), x.T @ y / n)
    return DamageInteractionHead(coefficients, train_dataset_sha256)
