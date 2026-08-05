"""Small game-neutral listwise ranker for semantic objectives."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

PLANNER_MODEL_ID = "pokemon.core.planning.masked-linear-ranker.v1"


class PlannerModelError(ValueError):
    pass


class ObjectiveRanker:
    def __init__(
        self,
        *,
        feature_names: Sequence[str],
        weights: ArrayLike,
        training_seed: int = 0,
    ) -> None:
        self.feature_names = tuple(feature_names)
        values = np.asarray(weights, dtype=np.float64)
        if values.shape != (len(self.feature_names),) or not np.all(np.isfinite(values)):
            raise PlannerModelError("planner weights do not match the feature schema")
        if type(training_seed) is not int or training_seed < 0:  # noqa: E721
            raise PlannerModelError("training seed must be a non-negative integer")
        values.setflags(write=False)
        self._weights = values
        self.training_seed = training_seed

    @property
    def weights(self) -> NDArray[np.float64]:
        return self._weights.copy()

    def probabilities(self, candidate_features: ArrayLike) -> NDArray[np.float64]:
        matrix = np.asarray(candidate_features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise PlannerModelError("planner candidate matrix has an invalid shape")
        scores = matrix @ self._weights
        scores -= np.max(scores)
        probabilities = np.exp(scores)
        probabilities /= np.sum(probabilities)
        return probabilities

    def predict(self, candidate_features: ArrayLike) -> int:
        return int(np.argmax(self.probabilities(candidate_features)))

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "model_id": PLANNER_MODEL_ID,
            "training_seed": self.training_seed,
            "feature_names": list(self.feature_names),
            "weights": [float(value) for value in self._weights],
        }

    @classmethod
    def fit(
        cls,
        *,
        feature_names: Sequence[str],
        examples: Iterable[tuple[ArrayLike, int]],
        seed: int = 0,
        epochs: int = 2500,
        learning_rate: float = 0.05,
        l2: float = 1e-4,
    ) -> ObjectiveRanker:
        rows = tuple(examples)
        if not rows:
            raise PlannerModelError("planner training requires examples")
        generator = np.random.default_rng(seed)
        weights = generator.normal(0.0, 1e-3, len(tuple(feature_names)))
        first = np.zeros_like(weights)
        second = np.zeros_like(weights)
        for epoch in range(1, epochs + 1):
            gradient = l2 * weights
            for candidate_features, chosen_index in rows:
                matrix = np.asarray(candidate_features, dtype=np.float64)
                if matrix.ndim != 2 or matrix.shape[1] != len(weights):
                    raise PlannerModelError("training matrix has an invalid shape")
                if not 0 <= chosen_index < matrix.shape[0]:
                    raise PlannerModelError("chosen objective index is invalid")
                scores = matrix @ weights
                scores -= np.max(scores)
                probabilities = np.exp(scores)
                probabilities /= np.sum(probabilities)
                probabilities[chosen_index] -= 1.0
                gradient += matrix.T @ probabilities / len(rows)
            first = 0.9 * first + 0.1 * gradient
            second = 0.999 * second + 0.001 * (gradient * gradient)
            corrected_first = first / (1.0 - math.pow(0.9, epoch))
            corrected_second = second / (1.0 - math.pow(0.999, epoch))
            weights -= learning_rate * corrected_first / (np.sqrt(corrected_second) + 1e-8)
        return cls(feature_names=feature_names, weights=weights, training_seed=seed)


def planner_accuracy(
    model: ObjectiveRanker,
    examples: Iterable[tuple[ArrayLike, int]],
) -> float:
    rows = tuple(examples)
    if not rows:
        raise PlannerModelError("planner evaluation requires examples")
    correct = sum(model.predict(features) == chosen for features, chosen in rows)
    return correct / len(rows)
