"""Portable, permutation-equivariant scorer for strategic destinations.

The model sees only the identity-free policy projection already admitted by
``strategic_navigation_dataset``.  Every candidate is scored with the same
network.  Candidate order therefore cannot become a shortcut, while relative
route features let the scorer compare variable-sized choice sets.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import stat
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.strategic_navigation import (
    DestinationAvailability,
    StrategicNavigationTag,
)
from pokemon_red_completion.strategic_navigation_dataset import (
    StrategicNavigationExample,
)

STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID = (
    "pokemon.core.strategic-navigation.destination-ranker.v1"
)
STRATEGIC_NAVIGATION_MODEL_ID = (
    "pokemon.core.strategic-navigation.destination-ranker.mlp.v1"
)
STRATEGIC_NAVIGATION_LINEAR_MODEL_ID = (
    "pokemon.core.strategic-navigation.destination-ranker.linear.v1"
)
_METRIC_NAMES = (
    "route_cost",
    "route_steps",
    "map_transitions",
    "field_actions",
    "mode_changes",
)
_TAG_VALUES = tuple(item.value for item in StrategicNavigationTag)
STRATEGIC_NAVIGATION_FEATURE_NAMES = (
    "set.candidate_count_scaled",
    *(f"candidate.availability.{item.value}" for item in DestinationAvailability),
    *(f"candidate.{name}.log1p" for name in _METRIC_NAMES),
    *(f"candidate.{name}.relative_rank" for name in _METRIC_NAMES),
    *(f"candidate.{name}.log_gap_to_minimum" for name in _METRIC_NAMES),
    *(
        f"context.need.{tag}"
        for tag in _TAG_VALUES
    ),
    *(
        f"context.origin.{tag}"
        for tag in _TAG_VALUES
    ),
    *(
        f"candidate.tag.{tag}"
        for tag in _TAG_VALUES
    ),
    "candidate.need_overlap_ratio",
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class StrategicNavigationModelInput(Protocol):
    """Identity-free question accepted before or after a teacher label exists."""

    @property
    def policy_input(self) -> Mapping[str, object]: ...

    @property
    def candidates(self) -> tuple[Mapping[str, object], ...]: ...

    @property
    def semantic_need_tags(self) -> tuple[str, ...]: ...


class StrategicNavigationScorer(Protocol):
    """Minimal shared interface for destination-ranking models."""

    def probabilities(
        self, example: StrategicNavigationModelInput
    ) -> NDArray[np.float64]: ...

    def predict(self, example: StrategicNavigationModelInput) -> int: ...

    def to_dict(self) -> dict[str, object]: ...


class StrategicNavigationModelError(ValueError):
    """Raised when a strategic scorer or its model-facing data is invalid."""


@dataclass(frozen=True, slots=True)
class StrategicNavigationModelMetrics:
    examples: int
    accuracy: float
    cross_entropy: float
    route_cost_baseline_accuracy: float
    paired_wins_over_route_cost: int
    paired_losses_to_route_cost: int
    paired_both_correct: int
    paired_both_wrong: int
    paired_two_sided_exact_p: float
    candidate_count_accuracy: tuple[tuple[int, float], ...]
    candidate_count_results: tuple[tuple[int, int, int], ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "strategic-navigation-model-metrics-v1",
            "examples": self.examples,
            "accuracy": self.accuracy,
            "cross_entropy": self.cross_entropy,
            "route_cost_baseline_accuracy": self.route_cost_baseline_accuracy,
            "paired_comparison": {
                "wins": self.paired_wins_over_route_cost,
                "losses": self.paired_losses_to_route_cost,
                "both_correct": self.paired_both_correct,
                "both_wrong": self.paired_both_wrong,
                "two_sided_exact_p": self.paired_two_sided_exact_p,
            },
            "candidate_count_accuracy": {
                str(count): accuracy for count, accuracy in self.candidate_count_accuracy
            },
            "candidate_count_results": {
                str(count): {
                    "correct": correct,
                    "examples": examples,
                    "accuracy": correct / examples,
                }
                for count, correct, examples in self.candidate_count_results
            },
        }


@dataclass(frozen=True, slots=True)
class StrategicNavigationMLP:
    """Score every candidate independently with one shared nonlinear function."""

    weights1: NDArray[np.float64]
    bias1: NDArray[np.float64]
    weights2: NDArray[np.float64]
    feature_mean: NDArray[np.float64]
    feature_scale: NDArray[np.float64]
    training_seed: int
    model_id: str = STRATEGIC_NAVIGATION_MODEL_ID
    feature_schema_id: str = STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        width = len(STRATEGIC_NAVIGATION_FEATURE_NAMES)
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
        if self.model_id != STRATEGIC_NAVIGATION_MODEL_ID:
            raise StrategicNavigationModelError("strategic model identity is unsupported")
        if self.feature_schema_id != STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID:
            raise StrategicNavigationModelError("strategic feature schema is unsupported")
        if (
            weights1.ndim != 2
            or weights1.shape[0] != width
            or bias1.shape != (weights1.shape[1],)
            or weights2.shape != (weights1.shape[1],)
            or mean.shape != (width,)
            or scale.shape != (width,)
            or weights1.shape[1] < 1
        ):
            raise StrategicNavigationModelError("strategic model shapes are invalid")
        if not all(np.all(np.isfinite(value)) for value in arrays) or np.any(scale <= 0):
            raise StrategicNavigationModelError("strategic model parameters are not finite")
        if type(self.training_seed) is not int or self.training_seed < 0:  # noqa: E721
            raise StrategicNavigationModelError("strategic training seed is invalid")
        for name, value in zip(
            ("weights1", "bias1", "weights2", "feature_mean", "feature_scale"),
            arrays,
            strict=True,
        ):
            detached = value.copy()
            detached.setflags(write=False)
            object.__setattr__(self, name, detached)

    def scores(self, example: StrategicNavigationModelInput) -> NDArray[np.float64]:
        features = strategic_navigation_feature_matrix(example)
        normalized = (features - self.feature_mean) / self.feature_scale
        scores = np.tanh(normalized @ self.weights1 + self.bias1) @ self.weights2
        if scores.shape != (len(example.candidates),) or not np.all(np.isfinite(scores)):
            raise StrategicNavigationModelError("strategic candidate scores are invalid")
        return scores

    def probabilities(
        self, example: StrategicNavigationModelInput
    ) -> NDArray[np.float64]:
        scores = self.scores(example)
        shifted = scores - np.max(scores)
        probabilities = np.exp(shifted)
        probabilities /= np.sum(probabilities)
        return probabilities

    def predict(self, example: StrategicNavigationModelInput) -> int:
        return int(np.argmax(self.probabilities(example)))

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "model_id": self.model_id,
            "feature_schema_id": self.feature_schema_id,
            "feature_names": list(STRATEGIC_NAVIGATION_FEATURE_NAMES),
            "hidden_units": int(self.weights1.shape[1]),
            "training_seed": self.training_seed,
            "weights1": self.weights1.tolist(),
            "bias1": self.bias1.tolist(),
            "weights2": self.weights2.tolist(),
            "feature_mean": self.feature_mean.tolist(),
            "feature_scale": self.feature_scale.tolist(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> StrategicNavigationMLP:
        names = value.get("feature_names")
        seed = value.get("training_seed")
        if (
            value.get("format_version") != 1
            or value.get("model_id") != STRATEGIC_NAVIGATION_MODEL_ID
            or value.get("feature_schema_id") != STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID
            or not isinstance(names, list)
            or tuple(names) != STRATEGIC_NAVIGATION_FEATURE_NAMES
            or type(seed) is not int  # noqa: E721
        ):
            raise StrategicNavigationModelError("strategic model record is incompatible")
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
            raise StrategicNavigationModelError("strategic model record is invalid") from error

    @classmethod
    def fit(
        cls,
        examples: Iterable[StrategicNavigationExample],
        *,
        hidden_units: int = 4,
        epochs: int = 600,
        learning_rate: float = 0.01,
        l2: float = 0.01,
        seed: int = 20260813,
    ) -> StrategicNavigationMLP:
        rows = tuple(examples)
        if not rows or any(row.partition != "train" for row in rows):
            raise StrategicNavigationModelError(
                "strategic fitting requires training-partition examples only"
            )
        if any(row.teacher_choice_target is None for row in rows):
            raise StrategicNavigationModelError(
                "strategic fitting requires successful teacher labels"
            )
        if type(hidden_units) is not int or hidden_units < 1:  # noqa: E721
            raise StrategicNavigationModelError("strategic hidden unit count is invalid")
        if type(epochs) is not int or epochs < 1:  # noqa: E721
            raise StrategicNavigationModelError("strategic epoch count is invalid")
        if learning_rate <= 0 or l2 < 0:
            raise StrategicNavigationModelError("strategic optimizer settings are invalid")

        matrices = tuple(strategic_navigation_feature_matrix(row) for row in rows)
        all_features = np.concatenate(matrices, axis=0)
        mean = np.mean(all_features, axis=0)
        scale = np.std(all_features, axis=0)
        inactive = scale < 1e-8
        scale[inactive] = 1.0
        normalized = tuple((matrix - mean) / scale for matrix in matrices)
        random = np.random.default_rng(seed)
        active_width = max(1, int(np.count_nonzero(~inactive)))
        weights1 = random.normal(
            0.0,
            1.0 / math.sqrt(active_width),
            (all_features.shape[1], hidden_units),
        )
        weights1[inactive, :] = 0.0
        bias1 = np.zeros(hidden_units, dtype=np.float64)
        weights2 = random.normal(0.0, 1.0 / math.sqrt(hidden_units), hidden_units)
        parameters = [weights1, bias1, weights2]
        first = [np.zeros_like(value) for value in parameters]
        second = [np.zeros_like(value) for value in parameters]
        for epoch in range(1, epochs + 1):
            gradients = [np.zeros_like(value) for value in parameters]
            for row, features in zip(rows, normalized, strict=True):
                selected = row.teacher_choice_target
                assert selected is not None
                hidden = np.tanh(features @ weights1 + bias1)
                logits = hidden @ weights2
                probabilities = np.exp(logits - np.max(logits))
                probabilities /= np.sum(probabilities)
                probabilities[selected] -= 1.0
                gradients[2] += hidden.T @ probabilities
                hidden_delta = probabilities[:, None] * weights2 * (1.0 - hidden * hidden)
                gradients[0] += features.T @ hidden_delta
                gradients[1] += np.sum(hidden_delta, axis=0)
            gradients[0] = gradients[0] / len(rows) + l2 * weights1
            gradients[0][inactive, :] = 0.0
            gradients[1] /= len(rows)
            gradients[2] = gradients[2] / len(rows) + l2 * weights2
            for index, (parameter, gradient) in enumerate(
                zip(parameters, gradients, strict=True)
            ):
                first[index] = 0.9 * first[index] + 0.1 * gradient
                second[index] = 0.999 * second[index] + 0.001 * gradient * gradient
                parameter -= learning_rate * (
                    first[index] / (1.0 - math.pow(0.9, epoch))
                ) / (
                    np.sqrt(second[index] / (1.0 - math.pow(0.999, epoch)))
                    + 1e-8
                )
        return cls(weights1, bias1, weights2, mean, scale, seed)


@dataclass(frozen=True, slots=True)
class StrategicNavigationLinear:
    """Score candidates with a deliberately small shared linear function."""

    weights: NDArray[np.float64]
    feature_mean: NDArray[np.float64]
    feature_scale: NDArray[np.float64]
    enabled_feature_names: tuple[str, ...]
    feature_set_id: str
    l2: float
    training_epochs: int
    model_id: str = STRATEGIC_NAVIGATION_LINEAR_MODEL_ID
    feature_schema_id: str = STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        width = len(STRATEGIC_NAVIGATION_FEATURE_NAMES)
        arrays = tuple(
            np.asarray(value, dtype=np.float64)
            for value in (self.weights, self.feature_mean, self.feature_scale)
        )
        weights, mean, scale = arrays
        if self.model_id != STRATEGIC_NAVIGATION_LINEAR_MODEL_ID:
            raise StrategicNavigationModelError("strategic model identity is unsupported")
        if self.feature_schema_id != STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID:
            raise StrategicNavigationModelError("strategic feature schema is unsupported")
        if any(value.shape != (width,) for value in arrays):
            raise StrategicNavigationModelError("strategic linear model shapes are invalid")
        if not all(np.all(np.isfinite(value)) for value in arrays) or np.any(scale <= 0):
            raise StrategicNavigationModelError(
                "strategic linear model parameters are not finite"
            )
        enabled = _canonical_enabled_feature_names(self.enabled_feature_names)
        enabled_indexes = {
            STRATEGIC_NAVIGATION_FEATURE_NAMES.index(name) for name in enabled
        }
        disabled = np.asarray(
            [index not in enabled_indexes for index in range(width)], dtype=np.bool_
        )
        if np.any(weights[disabled] != 0.0):
            raise StrategicNavigationModelError(
                "disabled strategic linear features must have zero weight"
            )
        if not isinstance(self.feature_set_id, str) or re.fullmatch(
            r"[a-z0-9][a-z0-9._-]{0,95}", self.feature_set_id
        ) is None:
            raise StrategicNavigationModelError("strategic feature-set identity is invalid")
        if (
            isinstance(self.l2, bool)
            or not isinstance(self.l2, (int, float))
            or not math.isfinite(float(self.l2))
            or self.l2 < 0
        ):
            raise StrategicNavigationModelError("strategic linear regularization is invalid")
        if type(self.training_epochs) is not int or self.training_epochs < 1:  # noqa: E721
            raise StrategicNavigationModelError("strategic linear epoch count is invalid")
        object.__setattr__(self, "enabled_feature_names", enabled)
        object.__setattr__(self, "l2", float(self.l2))
        for name, value in zip(
            ("weights", "feature_mean", "feature_scale"), arrays, strict=True
        ):
            detached = value.copy()
            detached.setflags(write=False)
            object.__setattr__(self, name, detached)

    @property
    def parameter_count(self) -> int:
        """Return the number of coefficients allowed to affect a score."""

        return len(self.enabled_feature_names)

    def scores(self, example: StrategicNavigationModelInput) -> NDArray[np.float64]:
        features = strategic_navigation_feature_matrix(example)
        normalized = (features - self.feature_mean) / self.feature_scale
        scores = normalized @ self.weights
        if scores.shape != (len(example.candidates),) or not np.all(np.isfinite(scores)):
            raise StrategicNavigationModelError("strategic candidate scores are invalid")
        return scores

    def probabilities(
        self, example: StrategicNavigationModelInput
    ) -> NDArray[np.float64]:
        scores = self.scores(example)
        shifted = scores - np.max(scores)
        probabilities = np.exp(shifted)
        probabilities /= np.sum(probabilities)
        return probabilities

    def predict(self, example: StrategicNavigationModelInput) -> int:
        return int(np.argmax(self.probabilities(example)))

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "model_id": self.model_id,
            "feature_schema_id": self.feature_schema_id,
            "feature_names": list(STRATEGIC_NAVIGATION_FEATURE_NAMES),
            "enabled_feature_names": list(self.enabled_feature_names),
            "feature_set_id": self.feature_set_id,
            "parameter_count": self.parameter_count,
            "l2": self.l2,
            "training_epochs": self.training_epochs,
            "weights": self.weights.tolist(),
            "feature_mean": self.feature_mean.tolist(),
            "feature_scale": self.feature_scale.tolist(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> StrategicNavigationLinear:
        names = value.get("feature_names")
        enabled = value.get("enabled_feature_names")
        feature_set_id = value.get("feature_set_id")
        l2 = value.get("l2")
        epochs = value.get("training_epochs")
        if (
            value.get("format_version") != 1
            or value.get("model_id") != STRATEGIC_NAVIGATION_LINEAR_MODEL_ID
            or value.get("feature_schema_id") != STRATEGIC_NAVIGATION_FEATURE_SCHEMA_ID
            or not isinstance(names, list)
            or tuple(names) != STRATEGIC_NAVIGATION_FEATURE_NAMES
            or not isinstance(enabled, list)
            or any(not isinstance(name, str) for name in enabled)
            or not isinstance(feature_set_id, str)
            or isinstance(l2, bool)
            or not isinstance(l2, (int, float))
            or type(epochs) is not int  # noqa: E721
        ):
            raise StrategicNavigationModelError("strategic model record is incompatible")
        try:
            model = cls(
                weights=np.asarray(value["weights"], dtype=np.float64),
                feature_mean=np.asarray(value["feature_mean"], dtype=np.float64),
                feature_scale=np.asarray(value["feature_scale"], dtype=np.float64),
                enabled_feature_names=tuple(enabled),
                feature_set_id=feature_set_id,
                l2=float(l2),
                training_epochs=epochs,
            )
        except StrategicNavigationModelError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise StrategicNavigationModelError("strategic model record is invalid") from error
        reported_parameter_count = value.get("parameter_count")
        if (
            type(reported_parameter_count) is not int  # noqa: E721
            or reported_parameter_count != model.parameter_count
        ):
            raise StrategicNavigationModelError("strategic model record is incompatible")
        return model

    @classmethod
    def fit(
        cls,
        examples: Iterable[StrategicNavigationExample],
        *,
        enabled_feature_names: Sequence[str],
        feature_set_id: str,
        epochs: int = 600,
        learning_rate: float = 0.01,
        l2: float = 0.01,
    ) -> StrategicNavigationLinear:
        rows = tuple(examples)
        if not rows or any(row.partition != "train" for row in rows):
            raise StrategicNavigationModelError(
                "strategic fitting requires training-partition examples only"
            )
        if any(row.teacher_choice_target is None for row in rows):
            raise StrategicNavigationModelError(
                "strategic fitting requires successful teacher labels"
            )
        enabled = _canonical_enabled_feature_names(enabled_feature_names)
        if type(epochs) is not int or epochs < 1:  # noqa: E721
            raise StrategicNavigationModelError("strategic epoch count is invalid")
        if (
            isinstance(learning_rate, bool)
            or not isinstance(learning_rate, (int, float))
            or not math.isfinite(float(learning_rate))
            or learning_rate <= 0
            or isinstance(l2, bool)
            or not isinstance(l2, (int, float))
            or not math.isfinite(float(l2))
            or l2 < 0
        ):
            raise StrategicNavigationModelError("strategic optimizer settings are invalid")

        matrices = tuple(strategic_navigation_feature_matrix(row) for row in rows)
        all_features = np.concatenate(matrices, axis=0)
        mean = np.mean(all_features, axis=0)
        scale = np.std(all_features, axis=0)
        inactive = scale < 1e-8
        scale[inactive] = 1.0
        normalized = tuple((matrix - mean) / scale for matrix in matrices)
        enabled_indexes = {
            STRATEGIC_NAVIGATION_FEATURE_NAMES.index(name) for name in enabled
        }
        trainable = np.asarray(
            [
                index in enabled_indexes and not inactive[index]
                for index in range(len(STRATEGIC_NAVIGATION_FEATURE_NAMES))
            ],
            dtype=np.bool_,
        )
        if not np.any(trainable):
            raise StrategicNavigationModelError(
                "strategic linear feature set is inactive in training"
            )
        weights = np.zeros(len(STRATEGIC_NAVIGATION_FEATURE_NAMES), dtype=np.float64)
        first = np.zeros_like(weights)
        second = np.zeros_like(weights)
        for epoch in range(1, epochs + 1):
            gradient = np.zeros_like(weights)
            for row, features in zip(rows, normalized, strict=True):
                selected = row.teacher_choice_target
                assert selected is not None
                logits = features @ weights
                probabilities = np.exp(logits - np.max(logits))
                probabilities /= np.sum(probabilities)
                probabilities[selected] -= 1.0
                gradient += features.T @ probabilities
            gradient = gradient / len(rows) + float(l2) * weights
            gradient[~trainable] = 0.0
            first = 0.9 * first + 0.1 * gradient
            second = 0.999 * second + 0.001 * gradient * gradient
            weights -= float(learning_rate) * (
                first / (1.0 - math.pow(0.9, epoch))
            ) / (
                np.sqrt(second / (1.0 - math.pow(0.999, epoch))) + 1e-8
            )
            weights[~trainable] = 0.0
        return cls(
            weights=weights,
            feature_mean=mean,
            feature_scale=scale,
            enabled_feature_names=enabled,
            feature_set_id=feature_set_id,
            l2=float(l2),
            training_epochs=epochs,
        )


def strategic_navigation_feature_matrix(
    example: StrategicNavigationModelInput,
) -> NDArray[np.float64]:
    """Project one identity-free variable-sized choice into frozen numeric rows."""

    candidates = example.candidates
    need = frozenset(example.semantic_need_tags)
    raw_origin = example.policy_input.get("origin_semantic_tags")
    if not isinstance(raw_origin, tuple) or any(
        not isinstance(tag, str) for tag in raw_origin
    ):
        raise StrategicNavigationModelError("strategic origin tags are invalid")
    origin = frozenset(raw_origin)
    metric_values: dict[str, tuple[int, ...]] = {}
    for name in _METRIC_NAMES:
        values_list: list[int] = []
        for candidate in candidates:
            if candidate.get("availability") != DestinationAvailability.AVAILABLE.value:
                continue
            value = candidate.get(name)
            if type(value) is not int:  # noqa: E721
                raise StrategicNavigationModelError("strategic route metric is invalid")
            values_list.append(value)
        values = tuple(values_list)
        metric_values[name] = values

    rows: list[list[float]] = []
    for candidate in candidates:
        availability = candidate.get("availability")
        if not isinstance(availability, str):
            raise StrategicNavigationModelError("strategic availability is invalid")
        candidate_tags_raw = candidate.get("semantic_tags")
        if not isinstance(candidate_tags_raw, tuple) or any(
            not isinstance(tag, str) for tag in candidate_tags_raw
        ):
            raise StrategicNavigationModelError("strategic candidate tags are invalid")
        candidate_tags = frozenset(candidate_tags_raw)
        row = [min(len(candidates), 8) / 8.0]
        row.extend(float(availability == item.value) for item in DestinationAvailability)
        raw_metrics: list[float] = []
        ranks: list[float] = []
        gaps: list[float] = []
        for name in _METRIC_NAMES:
            value = candidate.get(name)
            if availability == DestinationAvailability.AVAILABLE.value:
                if type(value) is not int:  # noqa: E721
                    raise StrategicNavigationModelError("strategic route metric is invalid")
                values = metric_values[name]
                ordered = sorted(values)
                raw_metrics.append(math.log1p(value))
                ranks.append(
                    ordered.index(value) / (len(ordered) - 1)
                    if len(ordered) > 1
                    else 0.0
                )
                gaps.append(math.log1p(value) - math.log1p(min(values)))
            else:
                raw_metrics.append(0.0)
                ranks.append(0.0)
                gaps.append(0.0)
        row.extend(raw_metrics)
        row.extend(ranks)
        row.extend(gaps)
        row.extend(float(tag in need) for tag in _TAG_VALUES)
        row.extend(float(tag in origin) for tag in _TAG_VALUES)
        row.extend(float(tag in candidate_tags) for tag in _TAG_VALUES)
        row.append(len(candidate_tags & need) / max(1, len(need)))
        rows.append(row)
    result = np.asarray(rows, dtype=np.float64)
    if result.shape != (len(candidates), len(STRATEGIC_NAVIGATION_FEATURE_NAMES)):
        raise StrategicNavigationModelError("strategic feature width drifted")
    if not np.all(np.isfinite(result)):
        raise StrategicNavigationModelError("strategic features are not finite")
    return result


def evaluate_strategic_navigation_model(
    model: StrategicNavigationScorer,
    examples: Iterable[StrategicNavigationExample],
) -> StrategicNavigationModelMetrics:
    rows = tuple(examples)
    if not rows or any(row.teacher_choice_target is None for row in rows):
        raise StrategicNavigationModelError(
            "strategic evaluation requires successful teacher labels"
        )
    correct = baseline_correct = both_correct = both_wrong = wins = losses = 0
    loss = 0.0
    by_size: dict[int, list[int]] = {}
    for row in rows:
        target = row.teacher_choice_target
        assert target is not None
        probabilities = model.probabilities(row)
        predicted = int(np.argmax(probabilities))
        baseline = route_cost_baseline_prediction(row)
        model_ok = predicted == target
        baseline_ok = baseline == target
        correct += int(model_ok)
        baseline_correct += int(baseline_ok)
        wins += int(model_ok and not baseline_ok)
        losses += int(not model_ok and baseline_ok)
        both_correct += int(model_ok and baseline_ok)
        both_wrong += int(not model_ok and not baseline_ok)
        loss -= math.log(max(float(probabilities[target]), 1e-12))
        slot = by_size.setdefault(len(row.candidates), [0, 0])
        slot[0] += 1
        slot[1] += int(model_ok)
    return StrategicNavigationModelMetrics(
        examples=len(rows),
        accuracy=correct / len(rows),
        cross_entropy=loss / len(rows),
        route_cost_baseline_accuracy=baseline_correct / len(rows),
        paired_wins_over_route_cost=wins,
        paired_losses_to_route_cost=losses,
        paired_both_correct=both_correct,
        paired_both_wrong=both_wrong,
        paired_two_sided_exact_p=_paired_two_sided_exact_p(wins, losses),
        candidate_count_accuracy=tuple(
            (count, matches / examples)
            for count, (examples, matches) in sorted(by_size.items())
        ),
        candidate_count_results=tuple(
            (count, matches, examples)
            for count, (examples, matches) in sorted(by_size.items())
        ),
    )


def route_cost_baseline_prediction(example: StrategicNavigationModelInput) -> int:
    available = tuple(
        (index, candidate.get("route_cost"))
        for index, candidate in enumerate(example.candidates)
        if candidate.get("availability") == DestinationAvailability.AVAILABLE.value
    )
    if not available or any(type(cost) is not int for _, cost in available):  # noqa: E721
        raise StrategicNavigationModelError("route-cost baseline has no valid candidate")
    return min(available, key=lambda item: (_known_int(item[1]), item[0]))[0]


def canonical_strategic_navigation_model_sha256(
    model: StrategicNavigationScorer,
) -> str:
    payload = json.dumps(
        model.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def load_strategic_navigation_model(
    path: str | Path,
    *,
    expected_sha256: str,
) -> StrategicNavigationMLP | StrategicNavigationLinear:
    if _SHA256.fullmatch(expected_sha256) is None:
        raise StrategicNavigationModelError("expected strategic model digest is invalid")
    source = Path(path)
    try:
        metadata = source.lstat()
        payload = source.read_bytes()
    except OSError as error:
        raise StrategicNavigationModelError("strategic model cannot be read") from error
    if source.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise StrategicNavigationModelError("strategic model must be a regular file")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise StrategicNavigationModelError("strategic model failed authentication")
    try:
        raw = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise StrategicNavigationModelError("strategic model is invalid JSON") from error
    if not isinstance(raw, Mapping):
        raise StrategicNavigationModelError("strategic model must be an object")
    if raw.get("model_id") == STRATEGIC_NAVIGATION_MODEL_ID:
        return StrategicNavigationMLP.from_dict(raw)
    if raw.get("model_id") == STRATEGIC_NAVIGATION_LINEAR_MODEL_ID:
        return StrategicNavigationLinear.from_dict(raw)
    raise StrategicNavigationModelError("strategic model identity is unsupported")


def _paired_two_sided_exact_p(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / math.pow(2.0, discordant))


def _known_int(value: object) -> int:
    if type(value) is not int:  # noqa: E721
        raise StrategicNavigationModelError("strategic route metric is invalid")
    return value


def _canonical_enabled_feature_names(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not values:
        raise StrategicNavigationModelError("strategic linear feature set is empty")
    if any(not isinstance(name, str) for name in values):
        raise StrategicNavigationModelError("strategic linear feature name is invalid")
    if len(set(values)) != len(values):
        raise StrategicNavigationModelError("strategic linear feature is duplicated")
    allowed = set(STRATEGIC_NAVIGATION_FEATURE_NAMES)
    if any(name not in allowed for name in values):
        raise StrategicNavigationModelError("strategic linear feature is unknown")
    selected = set(values)
    canonical = tuple(
        name for name in STRATEGIC_NAVIGATION_FEATURE_NAMES if name in selected
    )
    if tuple(values) != canonical:
        raise StrategicNavigationModelError(
            "strategic linear features must use canonical schema order"
        )
    return canonical


def select_strategic_navigation_linear_model(
    training: Sequence[StrategicNavigationExample],
    *,
    feature_sets: Sequence[tuple[str, Sequence[str]]] | None = None,
    l2_values: Sequence[float] = (0.001, 0.01, 0.1, 1.0, 10.0),
    epochs: int = 600,
    learning_rate: float = 0.01,
) -> tuple[StrategicNavigationLinear, dict[str, object]]:
    """Choose a small linear ranker using training-only leave-one-out evidence.

    Validation is intentionally absent from this API.  Each feature-set and
    regularization choice is scored by leaving out one training decision at a
    time.  The final choice uses a one-standard-error simplicity rule so a
    larger feature set must earn enough training-only evidence to justify its
    extra coefficients.
    """

    rows = tuple(training)
    if len(rows) < 3:
        raise StrategicNavigationModelError(
            "strategic linear selection needs at least three training examples"
        )
    if any(row.partition != "train" for row in rows):
        raise StrategicNavigationModelError(
            "strategic linear selection accepts training-partition examples only"
        )
    if any(row.teacher_choice_target is None for row in rows):
        raise StrategicNavigationModelError(
            "strategic linear selection requires successful teacher labels"
        )
    if type(epochs) is not int or epochs < 1:  # noqa: E721
        raise StrategicNavigationModelError("strategic epoch count is invalid")
    if not l2_values:
        raise StrategicNavigationModelError("strategic linear selection needs l2 values")
    canonical_l2: list[float] = []
    for value in l2_values:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
        ):
            raise StrategicNavigationModelError(
                "strategic linear selection l2 value is invalid"
            )
        canonical_l2.append(float(value))
    if len(set(canonical_l2)) != len(canonical_l2):
        raise StrategicNavigationModelError(
            "strategic linear selection l2 value is duplicated"
        )

    candidates = (
        _default_strategic_linear_feature_sets(rows)
        if feature_sets is None
        else _canonical_linear_feature_sets(feature_sets)
    )
    trial_rows: list[dict[str, object]] = []
    best_by_feature_set: dict[str, dict[str, object]] = {}
    for feature_set_id, names in candidates:
        feature_set_trials: list[dict[str, object]] = []
        for l2 in canonical_l2:
            correct = 0
            cross_entropy = 0.0
            for held_out_index, held_out in enumerate(rows):
                fold = rows[:held_out_index] + rows[held_out_index + 1 :]
                model = StrategicNavigationLinear.fit(
                    fold,
                    enabled_feature_names=names,
                    feature_set_id=feature_set_id,
                    epochs=epochs,
                    learning_rate=learning_rate,
                    l2=l2,
                )
                target = held_out.teacher_choice_target
                assert target is not None
                probabilities = model.probabilities(held_out)
                correct += int(int(np.argmax(probabilities)) == target)
                cross_entropy -= math.log(max(float(probabilities[target]), 1e-12))
            record: dict[str, object] = {
                "feature_set_id": feature_set_id,
                "feature_names": list(names),
                "parameter_count": len(names),
                "l2": l2,
                "leave_one_out": {
                    "examples": len(rows),
                    "correct": correct,
                    "accuracy": correct / len(rows),
                    "cross_entropy": cross_entropy / len(rows),
                },
            }
            feature_set_trials.append(record)
            trial_rows.append(record)
        best_regularization = min(
            feature_set_trials,
            key=lambda record: (
                -_selection_correct(record),
                _selection_cross_entropy(record),
                -_selection_l2(record),
            ),
        )
        best_by_feature_set[feature_set_id] = best_regularization

    feature_set_winners = tuple(best_by_feature_set.values())
    (
        selected,
        eligible,
        best_accuracy,
        standard_error,
        one_standard_error_threshold,
    ) = _select_one_standard_error_feature_set(
        feature_set_winners,
        example_count=len(rows),
    )
    selected_id = _selection_feature_set_id(selected)
    selected_names = tuple(
        name
        for name in STRATEGIC_NAVIGATION_FEATURE_NAMES
        if name in set(_selection_feature_names(selected))
    )
    selected_l2 = _selection_l2(selected)
    final_model = StrategicNavigationLinear.fit(
        rows,
        enabled_feature_names=selected_names,
        feature_set_id=selected_id,
        epochs=epochs,
        learning_rate=learning_rate,
        l2=selected_l2,
    )
    published_trials = []
    for record in trial_rows:
        feature_set_id = _selection_feature_set_id(record)
        feature_set_winner = best_by_feature_set[feature_set_id]
        published_trials.append(
            {
                **record,
                "best_regularization_for_feature_set": record is feature_set_winner,
                "one_standard_error_eligible": (
                    record is feature_set_winner and record in eligible
                ),
                "selected": record is selected,
            }
        )
    selection = {
        "schema": "strategic-navigation-linear-selection-v1",
        "selection_data": "train_only",
        "validation_used_for_selection": False,
        "sealed_test_used_for_selection": False,
        "cross_validation": "leave_one_training_example_out",
        "regularization_selection": (
            "highest_correct_then_lowest_cross_entropy_then_strongest_l2"
        ),
        "feature_set_selection": "one_standard_error_simplicity_rule",
        "best_leave_one_out_accuracy": best_accuracy,
        "best_leave_one_out_standard_error": standard_error,
        "one_standard_error_accuracy_threshold": one_standard_error_threshold,
        "selected_feature_set_id": selected_id,
        "selected_feature_names": list(selected_names),
        "selected_parameter_count": len(selected_names),
        "selected_l2": selected_l2,
        "trials": published_trials,
    }
    return final_model, selection


def _select_one_standard_error_feature_set(
    feature_set_winners: Sequence[Mapping[str, object]],
    *,
    example_count: int,
) -> tuple[
    Mapping[str, object],
    tuple[Mapping[str, object], ...],
    float,
    float,
    float,
]:
    if not feature_set_winners:
        raise StrategicNavigationModelError(
            "strategic linear selection has no feature-set winner"
        )
    if type(example_count) is not int or example_count < 1:  # noqa: E721
        raise StrategicNavigationModelError(
            "strategic linear selection example count is invalid"
        )
    best_correct = max(_selection_correct(record) for record in feature_set_winners)
    if not 0 <= best_correct <= example_count:
        raise StrategicNavigationModelError(
            "strategic linear selection correct count is invalid"
        )
    best_accuracy = best_correct / example_count
    standard_error = math.sqrt(
        best_accuracy * (1.0 - best_accuracy) / example_count
    )
    threshold = best_accuracy - standard_error
    eligible = tuple(
        record
        for record in feature_set_winners
        if _selection_correct(record) / example_count >= threshold - 1e-12
    )
    selected = min(
        eligible,
        key=lambda record: (
            _selection_parameter_count(record),
            -_selection_correct(record),
            _selection_cross_entropy(record),
            -_selection_l2(record),
            _selection_feature_set_id(record),
        ),
    )
    return selected, eligible, best_accuracy, standard_error, threshold


def _default_strategic_linear_feature_sets(
    training: Sequence[StrategicNavigationExample],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    matrices = tuple(strategic_navigation_feature_matrix(row) for row in training)
    all_features = np.concatenate(matrices, axis=0)
    active_names = tuple(
        name
        for index, name in enumerate(STRATEGIC_NAVIGATION_FEATURE_NAMES)
        if float(np.std(all_features[:, index])) >= 1e-8
    )
    route_cost_rank = ("candidate.route_cost.relative_rank",)
    relative_route = tuple(
        f"candidate.{metric}.relative_rank" for metric in _METRIC_NAMES
    )
    candidate_tags = tuple(
        name for name in active_names if name.startswith("candidate.tag.")
    )
    raw = (
        ("route_cost_rank", route_cost_rank),
        ("relative_route", relative_route),
        ("candidate_tags", candidate_tags),
        ("candidate_tags_plus_cost", candidate_tags + route_cost_rank),
        (
            "candidate_tags_plus_relative_route",
            candidate_tags + relative_route,
        ),
        ("all_training_active", active_names),
    )
    return _canonical_linear_feature_sets(raw)


def _canonical_linear_feature_sets(
    feature_sets: Sequence[tuple[str, Sequence[str]]],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not feature_sets:
        raise StrategicNavigationModelError(
            "strategic linear selection needs feature sets"
        )
    result: list[tuple[str, tuple[str, ...]]] = []
    identities: set[str] = set()
    for feature_set_id, raw_names in feature_sets:
        if not isinstance(feature_set_id, str) or re.fullmatch(
            r"[a-z0-9][a-z0-9._-]{0,95}", feature_set_id
        ) is None:
            raise StrategicNavigationModelError(
                "strategic linear feature-set identity is invalid"
            )
        if feature_set_id in identities:
            raise StrategicNavigationModelError(
                "strategic linear feature-set identity is duplicated"
            )
        identities.add(feature_set_id)
        if isinstance(raw_names, (str, bytes)):
            raise StrategicNavigationModelError(
                "strategic linear feature set is invalid"
            )
        selected = set(raw_names)
        ordered = tuple(
            name for name in STRATEGIC_NAVIGATION_FEATURE_NAMES if name in selected
        )
        if len(ordered) != len(raw_names):
            _canonical_enabled_feature_names(tuple(raw_names))
            raise AssertionError("unreachable canonical feature-set state")
        result.append((feature_set_id, _canonical_enabled_feature_names(ordered)))
    return tuple(result)


def _selection_feature_set_id(record: Mapping[str, object]) -> str:
    value = record.get("feature_set_id")
    if not isinstance(value, str):
        raise StrategicNavigationModelError("strategic linear selection record is invalid")
    return value


def _selection_feature_names(record: Mapping[str, object]) -> tuple[str, ...]:
    value = record.get("feature_names")
    if not isinstance(value, list) or any(not isinstance(name, str) for name in value):
        raise StrategicNavigationModelError("strategic linear selection record is invalid")
    return tuple(value)


def _selection_parameter_count(record: Mapping[str, object]) -> int:
    value = record.get("parameter_count")
    if type(value) is not int:  # noqa: E721
        raise StrategicNavigationModelError("strategic linear selection record is invalid")
    return value


def _selection_l2(record: Mapping[str, object]) -> float:
    value = record.get("l2")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StrategicNavigationModelError("strategic linear selection record is invalid")
    return float(value)


def _selection_correct(record: Mapping[str, object]) -> int:
    leave_one_out = record.get("leave_one_out")
    if not isinstance(leave_one_out, Mapping):
        raise StrategicNavigationModelError("strategic linear selection record is invalid")
    value = leave_one_out.get("correct")
    if type(value) is not int:  # noqa: E721
        raise StrategicNavigationModelError("strategic linear selection record is invalid")
    return value


def _selection_cross_entropy(record: Mapping[str, object]) -> float:
    leave_one_out = record.get("leave_one_out")
    if not isinstance(leave_one_out, Mapping):
        raise StrategicNavigationModelError("strategic linear selection record is invalid")
    value = leave_one_out.get("cross_entropy")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StrategicNavigationModelError("strategic linear selection record is invalid")
    return float(value)
