"""Permutation-equivariant scorer for trainee and training-venue candidates."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.training_candidate_dataset import TrainingCandidateExample
from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TRAINING_CANDIDATE_FEATURE_SCHEMA_ID,
    TrainingCandidateSet,
)

TRAINING_CANDIDATE_MODEL_ID = "pokemon.core.training.candidate-ranker.mlp.v1"


class TrainingCandidateModelError(ValueError):
    """Raised when a candidate scorer or its training data is invalid."""


@dataclass(frozen=True, slots=True)
class TrainingCandidateMetrics:
    examples: int
    multi_candidate_examples: int
    accuracy: float
    cross_entropy: float
    shape_baseline_accuracy: float
    kind_counts: tuple[tuple[str, int], ...]
    kind_accuracy: tuple[tuple[str, float], ...]
    candidate_count_accuracy: tuple[tuple[int, float], ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "examples": self.examples,
            "multi_candidate_examples": self.multi_candidate_examples,
            "accuracy": self.accuracy,
            "cross_entropy": self.cross_entropy,
            "shape_baseline_accuracy": self.shape_baseline_accuracy,
            "kind_counts": dict(self.kind_counts),
            "kind_accuracy": dict(self.kind_accuracy),
            "candidate_count_accuracy": {
                str(count): accuracy for count, accuracy in self.candidate_count_accuracy
            },
        }


@dataclass(frozen=True, slots=True)
class CandidateShapeBaseline:
    """Majority selected index using only choice kind and candidate count."""

    selected_indexes: tuple[tuple[str, int, int], ...]

    @classmethod
    def fit(cls, examples: Iterable[TrainingCandidateExample]) -> CandidateShapeBaseline:
        counts: defaultdict[tuple[str, int], Counter[int]] = defaultdict(Counter)
        for example in examples:
            key = (example.observation.kind.value, len(example.observation.candidates))
            counts[key][example.selected_candidate_index] += 1
        if not counts:
            raise TrainingCandidateModelError("shape baseline requires examples")
        return cls(
            tuple(
                (kind, candidate_count, max(labels, key=lambda index: (labels[index], -index)))
                for (kind, candidate_count), labels in sorted(counts.items())
            )
        )

    def predict(self, observation: TrainingCandidateSet) -> int:
        key = (observation.kind.value, len(observation.candidates))
        matches = tuple(
            selected
            for kind, count, selected in self.selected_indexes
            if (kind, count) == key
        )
        return matches[0] if matches else 0

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-training-candidate-shape-baseline-v1",
            "selected_indexes": {
                f"{kind}/{count}": selected
                for kind, count, selected in self.selected_indexes
            },
        }


@dataclass(frozen=True, slots=True)
class TrainingCandidateMLP:
    """Score each candidate independently, then softmax within its choice set."""

    weights1: NDArray[np.float64]
    bias1: NDArray[np.float64]
    weights2: NDArray[np.float64]
    feature_mean: NDArray[np.float64]
    feature_scale: NDArray[np.float64]
    training_seed: int
    model_id: str = TRAINING_CANDIDATE_MODEL_ID
    feature_schema_id: str = TRAINING_CANDIDATE_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        width = len(TRAINING_CANDIDATE_FEATURE_NAMES)
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
        if self.model_id != TRAINING_CANDIDATE_MODEL_ID:
            raise TrainingCandidateModelError("candidate model identity is unsupported")
        if self.feature_schema_id != TRAINING_CANDIDATE_FEATURE_SCHEMA_ID:
            raise TrainingCandidateModelError("candidate feature schema is unsupported")
        if (
            weights1.ndim != 2
            or weights1.shape[0] != width
            or bias1.shape != (weights1.shape[1],)
            or weights2.shape != (weights1.shape[1],)
            or mean.shape != (width,)
            or scale.shape != (width,)
            or weights1.shape[1] < 1
        ):
            raise TrainingCandidateModelError("candidate model parameter shapes are invalid")
        if not all(np.all(np.isfinite(value)) for value in arrays) or np.any(scale <= 0):
            raise TrainingCandidateModelError("candidate model parameters are not finite")
        if type(self.training_seed) is not int or self.training_seed < 0:  # noqa: E721
            raise TrainingCandidateModelError("candidate training seed is invalid")
        for name, value in zip(
            ("weights1", "bias1", "weights2", "feature_mean", "feature_scale"),
            arrays,
            strict=True,
        ):
            detached = value.copy()
            detached.setflags(write=False)
            object.__setattr__(self, name, detached)

    def scores(self, observation: TrainingCandidateSet) -> NDArray[np.float64]:
        features = np.asarray(
            [candidate.features for candidate in observation.candidates], dtype=np.float64
        )
        normalized = (features - self.feature_mean) / self.feature_scale
        hidden = np.tanh(normalized @ self.weights1 + self.bias1)
        scores = hidden @ self.weights2
        if scores.shape != (len(observation.candidates),) or not np.all(np.isfinite(scores)):
            raise TrainingCandidateModelError("candidate scores are invalid")
        return scores

    def probabilities(self, observation: TrainingCandidateSet) -> NDArray[np.float64]:
        scores = self.scores(observation)
        shifted = scores - np.max(scores)
        probabilities = np.exp(shifted)
        probabilities /= np.sum(probabilities)
        return probabilities

    def predict(self, observation: TrainingCandidateSet) -> int:
        """Return the first highest-scoring ephemeral candidate index."""

        return int(np.argmax(self.probabilities(observation)))

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "model_id": self.model_id,
            "feature_schema_id": self.feature_schema_id,
            "feature_names": list(TRAINING_CANDIDATE_FEATURE_NAMES),
            "hidden_units": int(self.weights1.shape[1]),
            "training_seed": self.training_seed,
            "weights1": self.weights1.tolist(),
            "bias1": self.bias1.tolist(),
            "weights2": self.weights2.tolist(),
            "feature_mean": self.feature_mean.tolist(),
            "feature_scale": self.feature_scale.tolist(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> TrainingCandidateMLP:
        names = value.get("feature_names")
        training_seed = value.get("training_seed")
        if (
            value.get("format_version") != 1
            or value.get("model_id") != TRAINING_CANDIDATE_MODEL_ID
            or value.get("feature_schema_id") != TRAINING_CANDIDATE_FEATURE_SCHEMA_ID
            or not isinstance(names, list)
            or tuple(names) != TRAINING_CANDIDATE_FEATURE_NAMES
            or not isinstance(training_seed, int)
            or isinstance(training_seed, bool)
        ):
            raise TrainingCandidateModelError("candidate model record is incompatible")
        try:
            return cls(
                weights1=np.asarray(value["weights1"], dtype=np.float64),
                bias1=np.asarray(value["bias1"], dtype=np.float64),
                weights2=np.asarray(value["weights2"], dtype=np.float64),
                feature_mean=np.asarray(value["feature_mean"], dtype=np.float64),
                feature_scale=np.asarray(value["feature_scale"], dtype=np.float64),
                training_seed=training_seed,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise TrainingCandidateModelError("candidate model record is invalid") from error

    @classmethod
    def fit(
        cls,
        examples: Iterable[TrainingCandidateExample],
        *,
        hidden_units: int = 16,
        epochs: int = 400,
        learning_rate: float = 0.01,
        l2: float = 0.0001,
        kind_balance_power: float = 0.5,
        seed: int = 20260808,
    ) -> TrainingCandidateMLP:
        rows = tuple(examples)
        if not rows or not any(len(row.observation.candidates) > 1 for row in rows):
            raise TrainingCandidateModelError("candidate fitting requires genuine choices")
        if type(hidden_units) is not int or hidden_units < 1:  # noqa: E721
            raise TrainingCandidateModelError("hidden unit count is invalid")
        if type(epochs) is not int or epochs < 1:  # noqa: E721
            raise TrainingCandidateModelError("epoch count is invalid")
        if not (learning_rate > 0 and l2 >= 0 and 0 <= kind_balance_power <= 1):
            raise TrainingCandidateModelError("candidate optimizer settings are invalid")
        collapsed = _collapse_examples(rows)
        all_features = np.concatenate(
            [
                np.asarray(
                    [candidate.features for candidate in row.observation.candidates],
                    dtype=np.float64,
                )
                for row, _multiplicity in collapsed
            ],
            axis=0,
        )
        mean = np.mean(all_features, axis=0)
        scale = np.std(all_features, axis=0)
        scale[scale < 1e-8] = 1.0
        grouped = _training_groups(collapsed, mean, scale, kind_balance_power)
        random = np.random.default_rng(seed)
        weights1 = random.normal(
            0.0, 1.0 / math.sqrt(all_features.shape[1]), (all_features.shape[1], hidden_units)
        )
        bias1 = np.zeros(hidden_units, dtype=np.float64)
        weights2 = random.normal(0.0, 1.0 / math.sqrt(hidden_units), hidden_units)
        parameters = [weights1, bias1, weights2]
        first = [np.zeros_like(value) for value in parameters]
        second = [np.zeros_like(value) for value in parameters]
        for epoch in range(1, epochs + 1):
            gradients = [np.zeros_like(value) for value in parameters]
            total_weight = 0.0
            for features, selected, example_weights in grouped:
                hidden = np.tanh(features @ weights1 + bias1)
                logits = hidden @ weights2
                logits -= np.max(logits, axis=1, keepdims=True)
                probabilities = np.exp(logits)
                probabilities /= np.sum(probabilities, axis=1, keepdims=True)
                delta = probabilities
                delta[np.arange(len(selected)), selected] -= 1.0
                delta *= example_weights[:, None]
                gradients[2] += np.einsum("mnh,mn->h", hidden, delta)
                hidden_delta = delta[:, :, None] * weights2[None, None, :]
                hidden_delta *= 1.0 - hidden * hidden
                gradients[0] += np.einsum("mnd,mnh->dh", features, hidden_delta)
                gradients[1] += np.sum(hidden_delta, axis=(0, 1))
                total_weight += float(np.sum(example_weights))
            if total_weight <= 0:
                raise TrainingCandidateModelError("candidate fitting has zero weight")
            gradients[0] = gradients[0] / total_weight + l2 * weights1
            gradients[1] /= total_weight
            gradients[2] = gradients[2] / total_weight + l2 * weights2
            for index, (parameter, gradient) in enumerate(zip(parameters, gradients, strict=True)):
                first[index] = 0.9 * first[index] + 0.1 * gradient
                second[index] = 0.999 * second[index] + 0.001 * (gradient * gradient)
                corrected_first = first[index] / (1.0 - math.pow(0.9, epoch))
                corrected_second = second[index] / (1.0 - math.pow(0.999, epoch))
                parameter -= learning_rate * corrected_first / (
                    np.sqrt(corrected_second) + 1e-8
                )
        return cls(weights1, bias1, weights2, mean, scale, seed)


def evaluate_training_candidate_model(
    model: TrainingCandidateMLP,
    examples: Iterable[TrainingCandidateExample],
    *,
    baseline: CandidateShapeBaseline,
) -> TrainingCandidateMetrics:
    rows = tuple(examples)
    if not rows:
        raise TrainingCandidateModelError("candidate evaluation requires examples")
    correct = 0
    baseline_correct = 0
    loss = 0.0
    kind_counts: Counter[str] = Counter()
    kind_correct: Counter[str] = Counter()
    size_counts: Counter[int] = Counter()
    size_correct: Counter[int] = Counter()
    for row in rows:
        probabilities = model.probabilities(row.observation)
        predicted = int(np.argmax(probabilities))
        agreed = predicted == row.selected_candidate_index
        correct += int(agreed)
        baseline_correct += int(baseline.predict(row.observation) == row.selected_candidate_index)
        loss -= math.log(max(float(probabilities[row.selected_candidate_index]), 1e-12))
        kind = row.observation.kind.value
        count = len(row.observation.candidates)
        kind_counts[kind] += 1
        kind_correct[kind] += int(agreed)
        size_counts[count] += 1
        size_correct[count] += int(agreed)
    return TrainingCandidateMetrics(
        examples=len(rows),
        multi_candidate_examples=sum(len(row.observation.candidates) > 1 for row in rows),
        accuracy=correct / len(rows),
        cross_entropy=loss / len(rows),
        shape_baseline_accuracy=baseline_correct / len(rows),
        kind_counts=tuple(sorted(kind_counts.items())),
        kind_accuracy=tuple(
            (kind, kind_correct[kind] / count) for kind, count in sorted(kind_counts.items())
        ),
        candidate_count_accuracy=tuple(
            (count, size_correct[count] / examples)
            for count, examples in sorted(size_counts.items())
        ),
    )


def canonical_training_candidate_model_sha256(model: TrainingCandidateMLP) -> str:
    payload = json.dumps(
        model.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _collapse_examples(
    examples: tuple[TrainingCandidateExample, ...],
) -> tuple[tuple[TrainingCandidateExample, int], ...]:
    unique: dict[tuple[object, ...], tuple[TrainingCandidateExample, int]] = {}
    for row in examples:
        key = (
            row.observation.kind.value,
            tuple(candidate.features for candidate in row.observation.candidates),
            row.selected_candidate_index,
        )
        if key in unique:
            prior, count = unique[key]
            unique[key] = (prior, count + 1)
        else:
            unique[key] = (row, 1)
    return tuple(unique.values())


def _training_groups(
    collapsed: tuple[tuple[TrainingCandidateExample, int], ...],
    mean: NDArray[np.float64],
    scale: NDArray[np.float64],
    kind_balance_power: float,
) -> tuple[tuple[NDArray[np.float64], NDArray[np.int64], NDArray[np.float64]], ...]:
    kind_counts: Counter[str] = Counter()
    for row, multiplicity in collapsed:
        kind_counts[row.observation.kind.value] += multiplicity
    by_size: defaultdict[int, list[tuple[TrainingCandidateExample, int]]] = defaultdict(list)
    for row, multiplicity in collapsed:
        if len(row.observation.candidates) > 1:
            by_size[len(row.observation.candidates)].append((row, multiplicity))
    groups = []
    for candidate_count, rows in sorted(by_size.items()):
        features = np.asarray(
            [
                [candidate.features for candidate in row.observation.candidates]
                for row, _multiplicity in rows
            ],
            dtype=np.float64,
        )
        selected = np.asarray(
            [row.selected_candidate_index for row, _multiplicity in rows], dtype=np.int64
        )
        example_weights = np.asarray(
            [
                multiplicity
                * math.pow(kind_counts[row.observation.kind.value], -kind_balance_power)
                for row, multiplicity in rows
            ],
            dtype=np.float64,
        )
        if features.shape[1] != candidate_count:  # pragma: no cover - grouping invariant
            raise AssertionError("candidate group width drifted")
        groups.append(((features - mean) / scale, selected, example_weights))
    return tuple(groups)
