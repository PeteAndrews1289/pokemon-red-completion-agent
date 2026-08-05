"""Small nonlinear classifier for transferable full-battle actions."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from pokemon_red_completion.battle_control_features import (
    CONTROL_CLASS_REFS,
    CONTROL_FEATURE_NAMES,
    CONTROL_FEATURE_SCHEMA_ID,
    BattleControlExample,
)

BATTLE_CONTROL_MODEL_ID = "pokemon.core.battle.control.mlp.v1"
BATTLE_CONTROL_MODEL_FORMAT_VERSION = 1


class BattleControlModelError(ValueError):
    """Raised when a full-battle classifier or training request is invalid."""


@dataclass(frozen=True, slots=True)
class BattleControlMetrics:
    examples: int
    accuracy: float
    balanced_accuracy: float
    cross_entropy: float
    class_counts: Mapping[str, int]

    def public_dict(self) -> dict[str, object]:
        return {
            "examples": self.examples,
            "accuracy": self.accuracy,
            "balanced_accuracy": self.balanced_accuracy,
            "cross_entropy": self.cross_entropy,
            "class_counts": dict(sorted(self.class_counts.items())),
        }


class BattleControlMLP:
    """One-hidden-layer softmax model with balanced-class training."""

    def __init__(
        self,
        *,
        feature_names: Sequence[str],
        class_refs: Sequence[str],
        input_weights: ArrayLike,
        hidden_bias: ArrayLike,
        output_weights: ArrayLike,
        output_bias: ArrayLike,
        feature_schema_id: str = CONTROL_FEATURE_SCHEMA_ID,
        training_seed: int = 0,
    ) -> None:
        names = tuple(feature_names)
        classes = tuple(class_refs)
        if names != CONTROL_FEATURE_NAMES:
            raise BattleControlModelError("control feature names do not match the live schema")
        if (
            len(classes) < 2
            or len(set(classes)) != len(classes)
            or any(value not in CONTROL_CLASS_REFS for value in classes)
        ):
            raise BattleControlModelError("control classes are invalid")
        first = np.asarray(input_weights, dtype=np.float64)
        hidden = np.asarray(hidden_bias, dtype=np.float64)
        second = np.asarray(output_weights, dtype=np.float64)
        output = np.asarray(output_bias, dtype=np.float64)
        if first.ndim != 2 or first.shape[1] != len(names) or first.shape[0] < 2:
            raise BattleControlModelError("control input weights have the wrong shape")
        if hidden.shape != (first.shape[0],):
            raise BattleControlModelError("control hidden bias has the wrong shape")
        if second.shape != (first.shape[0], len(classes)):
            raise BattleControlModelError("control output weights have the wrong shape")
        if output.shape != (len(classes),):
            raise BattleControlModelError("control output bias has the wrong shape")
        if not all(np.all(np.isfinite(value)) for value in (first, hidden, second, output)):
            raise BattleControlModelError("control model parameters must be finite")
        if feature_schema_id != CONTROL_FEATURE_SCHEMA_ID:
            raise BattleControlModelError("control feature schema is unsupported")
        if type(training_seed) is not int or training_seed < 0:  # noqa: E721
            raise BattleControlModelError("control training seed is invalid")
        self.feature_names = names
        self.class_refs = classes
        self.input_weights = first.copy()
        self.hidden_bias = hidden.copy()
        self.output_weights = second.copy()
        self.output_bias = output.copy()
        self.feature_schema_id = feature_schema_id
        self.training_seed = training_seed

    @property
    def model_id(self) -> str:
        return BATTLE_CONTROL_MODEL_ID

    def predict_proba(self, features: ArrayLike) -> NDArray[np.float64]:
        values = np.asarray(features, dtype=np.float64)
        single = values.ndim == 1
        if single:
            values = values.reshape(1, -1)
        if values.ndim != 2 or values.shape[1] != len(self.feature_names):
            raise BattleControlModelError("control prediction features have the wrong shape")
        if not np.all(np.isfinite(values)):
            raise BattleControlModelError("control prediction features must be finite")
        hidden = np.tanh(values @ self.input_weights.T + self.hidden_bias)
        scores = hidden @ self.output_weights + self.output_bias
        scores -= np.max(scores, axis=1, keepdims=True)
        probabilities = np.exp(scores)
        probabilities /= np.sum(probabilities, axis=1, keepdims=True)
        return probabilities[0] if single else probabilities

    def predict_ref(self, features: ArrayLike) -> str:
        probabilities = self.predict_proba(features)
        if probabilities.ndim != 1:
            raise BattleControlModelError("predict_ref requires exactly one observation")
        return self.class_refs[int(np.argmax(probabilities))]

    @classmethod
    def fit(
        cls,
        examples: Iterable[BattleControlExample],
        *,
        seed: int = 0,
        hidden_units: int = 24,
        epochs: int = 500,
        learning_rate: float = 0.01,
        l2: float = 1e-4,
    ) -> BattleControlMLP:
        rows = tuple(examples)
        if not rows:
            raise BattleControlModelError("control training examples are empty")
        observed = tuple(
            class_ref
            for index, class_ref in enumerate(CONTROL_CLASS_REFS)
            if any(row.class_index == index for row in rows)
        )
        if len(observed) < 2:
            raise BattleControlModelError("control training requires at least two action classes")
        if type(seed) is not int or seed < 0:  # noqa: E721
            raise BattleControlModelError("control training seed is invalid")
        if type(hidden_units) is not int or not 2 <= hidden_units <= 128:  # noqa: E721
            raise BattleControlModelError("control hidden-unit count is invalid")
        if type(epochs) is not int or epochs < 1:  # noqa: E721
            raise BattleControlModelError("control epoch count is invalid")
        if not math.isfinite(learning_rate) or learning_rate <= 0.0:
            raise BattleControlModelError("control learning rate is invalid")
        if not math.isfinite(l2) or l2 < 0.0:
            raise BattleControlModelError("control regularization is invalid")
        class_lookup = {value: index for index, value in enumerate(observed)}
        x = np.vstack([row.features for row in rows])
        y = np.asarray(
            [class_lookup[CONTROL_CLASS_REFS[row.class_index]] for row in rows],
            dtype=np.int64,
        )
        counts = np.bincount(y, minlength=len(observed)).astype(np.float64)
        sample_weights = len(rows) / (len(observed) * counts[y])
        sample_weights /= np.mean(sample_weights)
        rng = np.random.default_rng(seed)
        w1 = rng.normal(0.0, 0.04, size=(hidden_units, x.shape[1]))
        b1 = np.zeros(hidden_units, dtype=np.float64)
        w2 = rng.normal(0.0, 0.04, size=(hidden_units, len(observed)))
        b2 = np.zeros(len(observed), dtype=np.float64)
        parameters = (w1, b1, w2, b2)
        first_moments = tuple(np.zeros_like(value) for value in parameters)
        second_moments = tuple(np.zeros_like(value) for value in parameters)
        beta1, beta2, epsilon = 0.9, 0.999, 1e-8
        for step in range(1, epochs + 1):
            hidden = np.tanh(x @ w1.T + b1)
            scores = hidden @ w2 + b2
            scores -= np.max(scores, axis=1, keepdims=True)
            probabilities = np.exp(scores)
            probabilities /= np.sum(probabilities, axis=1, keepdims=True)
            score_gradient = probabilities
            score_gradient[np.arange(len(rows)), y] -= 1.0
            score_gradient *= sample_weights[:, None] / len(rows)
            hidden_gradient = score_gradient @ w2.T * (1.0 - hidden**2)
            gradients = (
                hidden_gradient.T @ x + l2 * w1,
                np.sum(hidden_gradient, axis=0),
                hidden.T @ score_gradient + l2 * w2,
                np.sum(score_gradient, axis=0),
            )
            for parameter, gradient, first, second in zip(
                parameters, gradients, first_moments, second_moments, strict=True
            ):
                first *= beta1
                first += (1.0 - beta1) * gradient
                second *= beta2
                second += (1.0 - beta2) * gradient**2
                corrected_first = first / (1.0 - beta1**step)
                corrected_second = second / (1.0 - beta2**step)
                parameter -= learning_rate * corrected_first / (
                    np.sqrt(corrected_second) + epsilon
                )
        return cls(
            feature_names=CONTROL_FEATURE_NAMES,
            class_refs=observed,
            input_weights=w1,
            hidden_bias=b1,
            output_weights=w2,
            output_bias=b2,
            training_seed=seed,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "format_version": BATTLE_CONTROL_MODEL_FORMAT_VERSION,
            "feature_schema_id": self.feature_schema_id,
            "feature_names": list(self.feature_names),
            "class_refs": list(self.class_refs),
            "training_seed": self.training_seed,
            "input_weights": self.input_weights.tolist(),
            "hidden_bias": self.hidden_bias.tolist(),
            "output_weights": self.output_weights.tolist(),
            "output_bias": self.output_bias.tolist(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> BattleControlMLP:
        if (
            value.get("model_id") != BATTLE_CONTROL_MODEL_ID
            or value.get("format_version") != BATTLE_CONTROL_MODEL_FORMAT_VERSION
        ):
            raise BattleControlModelError("control model identity is unsupported")
        try:
            return cls(
                feature_names=value["feature_names"],  # type: ignore[arg-type]
                class_refs=value["class_refs"],  # type: ignore[arg-type]
                input_weights=value["input_weights"],
                hidden_bias=value["hidden_bias"],
                output_weights=value["output_weights"],
                output_bias=value["output_bias"],
                feature_schema_id=str(value["feature_schema_id"]),
                training_seed=value["training_seed"],  # type: ignore[arg-type]
            )
        except (KeyError, TypeError, ValueError) as error:
            raise BattleControlModelError("control model payload is invalid") from error


def evaluate_control_model(
    model: BattleControlMLP,
    examples: Iterable[BattleControlExample],
) -> BattleControlMetrics:
    rows = tuple(examples)
    if not rows:
        raise BattleControlModelError("control evaluation examples are empty")
    lookup = {value: index for index, value in enumerate(model.class_refs)}
    expected_refs = tuple(CONTROL_CLASS_REFS[row.class_index] for row in rows)
    if any(value not in lookup for value in expected_refs):
        raise BattleControlModelError("evaluation contains an unseen action class")
    expected = np.asarray([lookup[value] for value in expected_refs], dtype=np.int64)
    probabilities = model.predict_proba(np.vstack([row.features for row in rows]))
    predicted = np.argmax(probabilities, axis=1)
    accuracy = float(np.mean(predicted == expected))
    recalls = tuple(
        float(np.mean(predicted[expected == index] == index))
        for index in sorted(set(expected.tolist()))
    )
    loss = -float(
        np.mean(np.log(np.clip(probabilities[np.arange(len(rows)), expected], 1e-12, 1.0)))
    )
    counts = Counter(expected_refs)
    return BattleControlMetrics(
        examples=len(rows),
        accuracy=accuracy,
        balanced_accuracy=math.fsum(recalls) / len(recalls),
        cross_entropy=loss,
        class_counts=dict(counts),
    )
