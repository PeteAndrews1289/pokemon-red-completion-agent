"""Small listwise ranker for transferable battle switch targets."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.battle_switch_target import (
    SWITCH_TARGET_FEATURE_NAMES,
    SWITCH_TARGET_FEATURE_SCHEMA_ID,
    BattleSwitchTargetExample,
    BattleSwitchTargetSet,
)

SWITCH_TARGET_MODEL_ID = "pokemon.core.battle.switch-target-ranker.mlp.v1"


class BattleSwitchTargetModelError(ValueError):
    """Raised when a switch-target model or training request is invalid."""


@dataclass(frozen=True, slots=True)
class BattleSwitchTargetMetrics:
    examples: int
    accuracy: float
    cross_entropy: float
    battle_plan_accuracy: tuple[tuple[str, float], ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "examples": self.examples,
            "accuracy": self.accuracy,
            "cross_entropy": self.cross_entropy,
            "battle_plan_accuracy": dict(self.battle_plan_accuracy),
        }


@dataclass(frozen=True, slots=True)
class BattleSwitchTargetMLP:
    """Score each reserve independently, then softmax over the current party."""

    weights1: NDArray[np.float64]
    bias1: NDArray[np.float64]
    weights2: NDArray[np.float64]
    feature_mean: NDArray[np.float64]
    feature_scale: NDArray[np.float64]
    training_seed: int
    model_id: str = SWITCH_TARGET_MODEL_ID
    feature_schema_id: str = SWITCH_TARGET_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        width = len(SWITCH_TARGET_FEATURE_NAMES)
        arrays = tuple(
            np.asarray(value, dtype=np.float64)
            for value in (
                self.weights1,
                self.bias1,
                self.weights2,
                self.feature_mean,
                self.feature_scale,
            )
        )
        weights1, bias1, weights2, mean, scale = arrays
        if self.model_id != SWITCH_TARGET_MODEL_ID:
            raise BattleSwitchTargetModelError("switch target model identity is unsupported")
        if self.feature_schema_id != SWITCH_TARGET_FEATURE_SCHEMA_ID:
            raise BattleSwitchTargetModelError("switch target feature schema is unsupported")
        if (
            weights1.ndim != 2
            or weights1.shape[0] != width
            or weights1.shape[1] < 1
            or bias1.shape != (weights1.shape[1],)
            or weights2.shape != (weights1.shape[1],)
            or mean.shape != (width,)
            or scale.shape != (width,)
        ):
            raise BattleSwitchTargetModelError("switch target model shapes are invalid")
        if not all(np.all(np.isfinite(value)) for value in arrays) or np.any(scale <= 0):
            raise BattleSwitchTargetModelError("switch target parameters are not finite")
        if type(self.training_seed) is not int or self.training_seed < 0:  # noqa: E721
            raise BattleSwitchTargetModelError("switch target training seed is invalid")
        for name, value in zip(
            ("weights1", "bias1", "weights2", "feature_mean", "feature_scale"),
            arrays,
            strict=True,
        ):
            detached = value.copy()
            detached.setflags(write=False)
            object.__setattr__(self, name, detached)

    def scores(self, observation: BattleSwitchTargetSet) -> NDArray[np.float64]:
        features = np.asarray(
            [candidate.features for candidate in observation.candidates],
            dtype=np.float64,
        )
        normalized = (features - self.feature_mean) / self.feature_scale
        hidden = np.tanh(normalized @ self.weights1 + self.bias1)
        scores = hidden @ self.weights2
        if scores.shape != (len(observation.candidates),) or not np.all(np.isfinite(scores)):
            raise BattleSwitchTargetModelError("switch target scores are invalid")
        return scores

    def probabilities(self, observation: BattleSwitchTargetSet) -> NDArray[np.float64]:
        scores = self.scores(observation)
        shifted = scores - np.max(scores)
        probabilities = np.exp(shifted)
        probabilities /= np.sum(probabilities)
        return probabilities

    def predict_candidate_index(self, observation: BattleSwitchTargetSet) -> int:
        return int(np.argmax(self.probabilities(observation)))

    def predict_party_slot(self, observation: BattleSwitchTargetSet) -> int:
        return observation.candidates[self.predict_candidate_index(observation)].party_slot

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "model_id": self.model_id,
            "feature_schema_id": self.feature_schema_id,
            "feature_names": list(SWITCH_TARGET_FEATURE_NAMES),
            "hidden_units": int(self.weights1.shape[1]),
            "training_seed": self.training_seed,
            "weights1": self.weights1.tolist(),
            "bias1": self.bias1.tolist(),
            "weights2": self.weights2.tolist(),
            "feature_mean": self.feature_mean.tolist(),
            "feature_scale": self.feature_scale.tolist(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> BattleSwitchTargetMLP:
        names = value.get("feature_names")
        seed = value.get("training_seed")
        if (
            value.get("format_version") != 1
            or value.get("model_id") != SWITCH_TARGET_MODEL_ID
            or value.get("feature_schema_id") != SWITCH_TARGET_FEATURE_SCHEMA_ID
            or not isinstance(names, list)
            or tuple(names) != SWITCH_TARGET_FEATURE_NAMES
            or type(seed) is not int  # noqa: E721
        ):
            raise BattleSwitchTargetModelError("switch target model record is incompatible")
        try:
            return cls(
                weights1=np.asarray(value["weights1"], dtype=np.float64),
                bias1=np.asarray(value["bias1"], dtype=np.float64),
                weights2=np.asarray(value["weights2"], dtype=np.float64),
                feature_mean=np.asarray(value["feature_mean"], dtype=np.float64),
                feature_scale=np.asarray(value["feature_scale"], dtype=np.float64),
                training_seed=seed,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise BattleSwitchTargetModelError("switch target model record is invalid") from error

    @classmethod
    def fit(
        cls,
        examples: Iterable[BattleSwitchTargetExample],
        *,
        hidden_units: int = 2,
        epochs: int = 1000,
        learning_rate: float = 0.01,
        l2: float = 0.03,
        seed: int = 0,
    ) -> BattleSwitchTargetMLP:
        rows = tuple(examples)
        if not rows or not any(len(row.observation.candidates) > 1 for row in rows):
            raise BattleSwitchTargetModelError("switch target fitting requires genuine choices")
        if type(hidden_units) is not int or hidden_units < 1:  # noqa: E721
            raise BattleSwitchTargetModelError("switch target hidden-unit count is invalid")
        if type(epochs) is not int or epochs < 1:  # noqa: E721
            raise BattleSwitchTargetModelError("switch target epoch count is invalid")
        if (
            not math.isfinite(learning_rate)
            or learning_rate <= 0
            or not math.isfinite(l2)
            or l2 < 0
            or type(seed) is not int  # noqa: E721
            or seed < 0
        ):
            raise BattleSwitchTargetModelError("switch target optimizer settings are invalid")
        all_features = np.concatenate(
            [
                np.asarray(
                    [candidate.features for candidate in row.observation.candidates],
                    dtype=np.float64,
                )
                for row in rows
            ],
            axis=0,
        )
        mean = np.mean(all_features, axis=0)
        scale = np.std(all_features, axis=0)
        scale[scale < 1e-8] = 1.0
        random = np.random.default_rng(seed)
        weights1 = random.normal(
            0.0,
            1.0 / math.sqrt(all_features.shape[1]),
            (all_features.shape[1], hidden_units),
        )
        bias1 = np.zeros(hidden_units, dtype=np.float64)
        weights2 = random.normal(0.0, 1.0 / math.sqrt(hidden_units), hidden_units)
        parameters = (weights1, bias1, weights2)
        first = [np.zeros_like(value) for value in parameters]
        second = [np.zeros_like(value) for value in parameters]
        for epoch in range(1, epochs + 1):
            gradients = [np.zeros_like(value) for value in parameters]
            for row in rows:
                features = np.asarray(
                    [candidate.features for candidate in row.observation.candidates],
                    dtype=np.float64,
                )
                normalized = (features - mean) / scale
                hidden = np.tanh(normalized @ weights1 + bias1)
                logits = hidden @ weights2
                probabilities = np.exp(logits - np.max(logits))
                probabilities /= np.sum(probabilities)
                probabilities[row.selected_candidate_index] -= 1.0
                gradients[2] += hidden.T @ probabilities
                hidden_gradient = probabilities[:, None] * weights2[None, :]
                hidden_gradient *= 1.0 - hidden * hidden
                gradients[0] += normalized.T @ hidden_gradient
                gradients[1] += np.sum(hidden_gradient, axis=0)
            gradients[0] = gradients[0] / len(rows) + l2 * weights1
            gradients[1] /= len(rows)
            gradients[2] = gradients[2] / len(rows) + l2 * weights2
            for index, (parameter, gradient) in enumerate(
                zip(parameters, gradients, strict=True)
            ):
                first[index] *= 0.9
                first[index] += 0.1 * gradient
                second[index] *= 0.999
                second[index] += 0.001 * gradient * gradient
                corrected_first = first[index] / (1.0 - math.pow(0.9, epoch))
                corrected_second = second[index] / (1.0 - math.pow(0.999, epoch))
                parameter -= learning_rate * corrected_first / (
                    np.sqrt(corrected_second) + 1e-8
                )
        return cls(weights1, bias1, weights2, mean, scale, seed)


def evaluate_switch_target_model(
    model: BattleSwitchTargetMLP,
    examples: Iterable[BattleSwitchTargetExample],
) -> BattleSwitchTargetMetrics:
    rows = tuple(examples)
    if not rows:
        raise BattleSwitchTargetModelError("switch target evaluation examples are empty")
    correct = 0
    loss = 0.0
    plans: dict[str, list[int]] = {}
    for row in rows:
        probabilities = model.probabilities(row.observation)
        prediction = int(np.argmax(probabilities))
        agreed = prediction == row.selected_candidate_index
        correct += int(agreed)
        loss -= math.log(max(float(probabilities[row.selected_candidate_index]), 1e-12))
        counts = plans.setdefault(row.battle_plan_id, [0, 0])
        counts[0] += int(agreed)
        counts[1] += 1
    return BattleSwitchTargetMetrics(
        examples=len(rows),
        accuracy=correct / len(rows),
        cross_entropy=loss / len(rows),
        battle_plan_accuracy=tuple(
            (plan_id, counts[0] / counts[1]) for plan_id, counts in sorted(plans.items())
        ),
    )
