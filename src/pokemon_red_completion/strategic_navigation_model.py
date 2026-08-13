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

    def scores(self, example: StrategicNavigationExample) -> NDArray[np.float64]:
        features = strategic_navigation_feature_matrix(example)
        normalized = (features - self.feature_mean) / self.feature_scale
        scores = np.tanh(normalized @ self.weights1 + self.bias1) @ self.weights2
        if scores.shape != (len(example.candidates),) or not np.all(np.isfinite(scores)):
            raise StrategicNavigationModelError("strategic candidate scores are invalid")
        return scores

    def probabilities(self, example: StrategicNavigationExample) -> NDArray[np.float64]:
        scores = self.scores(example)
        shifted = scores - np.max(scores)
        probabilities = np.exp(shifted)
        probabilities /= np.sum(probabilities)
        return probabilities

    def predict(self, example: StrategicNavigationExample) -> int:
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


def strategic_navigation_feature_matrix(
    example: StrategicNavigationExample,
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
    model: StrategicNavigationMLP,
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
    )


def route_cost_baseline_prediction(example: StrategicNavigationExample) -> int:
    available = tuple(
        (index, candidate.get("route_cost"))
        for index, candidate in enumerate(example.candidates)
        if candidate.get("availability") == DestinationAvailability.AVAILABLE.value
    )
    if not available or any(type(cost) is not int for _, cost in available):  # noqa: E721
        raise StrategicNavigationModelError("route-cost baseline has no valid candidate")
    return min(available, key=lambda item: (_known_int(item[1]), item[0]))[0]


def canonical_strategic_navigation_model_sha256(
    model: StrategicNavigationMLP,
) -> str:
    payload = json.dumps(
        model.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def load_strategic_navigation_model(
    path: str | Path,
    *,
    expected_sha256: str,
) -> StrategicNavigationMLP:
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
    return StrategicNavigationMLP.from_dict(raw)


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


def select_strategic_navigation_model(
    training: Sequence[StrategicNavigationExample],
    validation: Sequence[StrategicNavigationExample],
    *,
    configurations: Sequence[tuple[int, float]] = (
        (2, 0.1),
        (4, 0.1),
        (8, 0.1),
        (4, 0.01),
        (8, 0.01),
        (16, 0.01),
        (8, 0.001),
    ),
    epochs: int = 600,
    learning_rate: float = 0.01,
    seed: int = 20260813,
) -> tuple[StrategicNavigationMLP, tuple[dict[str, object], ...]]:
    """Select on development validation; the sealed test remains untouched."""

    if not training or not validation:
        raise StrategicNavigationModelError("strategic selection needs both partitions")
    if any(row.partition != "train" for row in training):
        raise StrategicNavigationModelError(
            "strategic selection training rows must be in the training partition"
        )
    if any(row.partition != "validation" for row in validation):
        raise StrategicNavigationModelError(
            "strategic selection validation rows must be in the validation partition"
        )
    trials: list[tuple[StrategicNavigationMLP, StrategicNavigationModelMetrics, float]] = []
    for hidden_units, l2 in configurations:
        model = StrategicNavigationMLP.fit(
            training,
            hidden_units=hidden_units,
            epochs=epochs,
            learning_rate=learning_rate,
            l2=l2,
            seed=seed,
        )
        metrics = evaluate_strategic_navigation_model(model, validation)
        trials.append((model, metrics, l2))
    best = max(
        trials,
        key=lambda item: (
            item[1].paired_wins_over_route_cost - item[1].paired_losses_to_route_cost,
            item[1].accuracy,
            -item[1].cross_entropy,
            item[2],
            -item[0].weights1.shape[1],
        ),
    )
    records = tuple(
        {
            "hidden_units": int(model.weights1.shape[1]),
            "l2": l2,
            "selected": model is best[0],
            "validation": metrics.public_dict(),
        }
        for model, metrics, l2 in trials
    )
    return best[0], records
