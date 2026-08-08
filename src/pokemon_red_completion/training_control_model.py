"""Class-balanced, phase-masked model for portable training decisions."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from pokemon_red_completion.training_control import (
    TRAINING_CONTROL_CLASS_REFS,
    TRAINING_CONTROL_FEATURE_NAMES,
    TRAINING_CONTROL_FEATURE_SCHEMA_ID,
    TrainingControlAction,
    TrainingControlObservation,
)
from pokemon_red_completion.training_control_dataset import (
    TrainingControlDataset,
    TrainingControlExample,
    audit_training_control_partitions,
)
from pokemon_red_completion.trajectory import canonical_sha256

TRAINING_CONTROL_MODEL_ID = "pokemon.core.training.control.mlp.v1"


class TrainingControlModelError(ValueError):
    """Raised when a model, split, or prediction request is invalid."""


@dataclass(frozen=True, slots=True)
class TrainingControlMetrics:
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


@dataclass(frozen=True, slots=True)
class TrainingControlCandidate:
    model: TrainingControlMLP
    model_sha256: str
    training: TrainingControlMetrics
    validation: TrainingControlMetrics
    training_lineages: tuple[str, ...]
    validation_lineages: tuple[str, ...]
    source_artifact_sha256s: tuple[str, ...]

    def public_summary(self) -> dict[str, object]:
        return {
            "schema": "pokemon-training-control-candidate-summary-v1",
            "model_id": self.model.model_id,
            "model_sha256": self.model_sha256,
            "class_refs": list(self.model.class_refs),
            "training": self.training.public_dict(),
            "validation": self.validation.public_dict(),
            "training_lineages": list(self.training_lineages),
            "validation_lineages": list(self.validation_lineages),
            "source_artifact_sha256s": list(self.source_artifact_sha256s),
            "promotion_eligible": False,
            "limitations": [
                "offline_candidate_only",
                "shadow_and_model_control_not_yet_qualified",
            ],
        }


class TrainingControlMLP:
    """One-hidden-layer softmax classifier with legal-action masking."""

    def __init__(
        self,
        *,
        class_refs: Sequence[str],
        input_weights: ArrayLike,
        hidden_bias: ArrayLike,
        output_weights: ArrayLike,
        output_bias: ArrayLike,
        training_seed: int = 0,
        feature_schema_id: str = TRAINING_CONTROL_FEATURE_SCHEMA_ID,
    ) -> None:
        classes = tuple(class_refs)
        if (
            len(classes) < 2
            or len(set(classes)) != len(classes)
            or any(value not in TRAINING_CONTROL_CLASS_REFS for value in classes)
        ):
            raise TrainingControlModelError("training-control classes are invalid")
        if feature_schema_id != TRAINING_CONTROL_FEATURE_SCHEMA_ID:
            raise TrainingControlModelError("training-control feature schema is unsupported")
        first = np.asarray(input_weights, dtype=np.float64)
        hidden = np.asarray(hidden_bias, dtype=np.float64)
        second = np.asarray(output_weights, dtype=np.float64)
        output = np.asarray(output_bias, dtype=np.float64)
        if (
            first.ndim != 2
            or first.shape[1] != len(TRAINING_CONTROL_FEATURE_NAMES)
            or first.shape[0] < 2
        ):
            raise TrainingControlModelError("training-control input weights have the wrong shape")
        if hidden.shape != (first.shape[0],):
            raise TrainingControlModelError("training-control hidden bias has the wrong shape")
        if second.shape != (first.shape[0], len(classes)):
            raise TrainingControlModelError("training-control output weights have the wrong shape")
        if output.shape != (len(classes),):
            raise TrainingControlModelError("training-control output bias has the wrong shape")
        if not all(np.all(np.isfinite(value)) for value in (first, hidden, second, output)):
            raise TrainingControlModelError("training-control parameters must be finite")
        if type(training_seed) is not int or training_seed < 0:  # noqa: E721
            raise TrainingControlModelError("training-control seed is invalid")
        self.class_refs = classes
        self.input_weights = first.copy()
        self.hidden_bias = hidden.copy()
        self.output_weights = second.copy()
        self.output_bias = output.copy()
        self.training_seed = training_seed
        self.feature_schema_id = feature_schema_id

    @property
    def model_id(self) -> str:
        return TRAINING_CONTROL_MODEL_ID

    def probabilities(self, observation: TrainingControlObservation) -> Mapping[str, float]:
        if not isinstance(observation, TrainingControlObservation):
            raise TypeError("observation must be a TrainingControlObservation")
        hidden = np.tanh(observation.vector() @ self.input_weights.T + self.hidden_bias)
        scores = hidden @ self.output_weights + self.output_bias
        legal = {action.value for action in observation.candidate_actions}
        mask = np.asarray([class_ref in legal for class_ref in self.class_refs], dtype=bool)
        if not np.any(mask):
            raise TrainingControlModelError("model has no class legal in this training phase")
        masked = np.where(mask, scores, -np.inf)
        finite = masked[mask]
        finite -= np.max(finite)
        probabilities = np.zeros(len(self.class_refs), dtype=np.float64)
        probabilities[mask] = np.exp(finite)
        probabilities /= np.sum(probabilities)
        return {
            class_ref: float(probability)
            for class_ref, probability in zip(self.class_refs, probabilities, strict=True)
        }

    def predict(self, observation: TrainingControlObservation) -> TrainingControlAction:
        probabilities = self.probabilities(observation)
        return TrainingControlAction(max(probabilities, key=probabilities.__getitem__))

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "model_id": self.model_id,
            "feature_schema_id": self.feature_schema_id,
            "feature_names": list(TRAINING_CONTROL_FEATURE_NAMES),
            "class_refs": list(self.class_refs),
            "training_seed": self.training_seed,
            "input_weights": self.input_weights.tolist(),
            "hidden_bias": self.hidden_bias.tolist(),
            "output_weights": self.output_weights.tolist(),
            "output_bias": self.output_bias.tolist(),
        }

    @classmethod
    def fit(
        cls,
        examples: Iterable[TrainingControlExample],
        *,
        seed: int = 0,
        hidden_units: int = 24,
        epochs: int = 500,
        learning_rate: float = 0.01,
        l2: float = 1e-4,
        class_balance_power: float = 1.0,
    ) -> TrainingControlMLP:
        rows = tuple(examples)
        if not rows:
            raise TrainingControlModelError("training-control examples are empty")
        observed = tuple(
            class_ref
            for class_ref in TRAINING_CONTROL_CLASS_REFS
            if any(example.action.value == class_ref for example in rows)
        )
        if len(observed) < 2:
            raise TrainingControlModelError("training-control fitting needs two action classes")
        if type(hidden_units) is not int or not 2 <= hidden_units <= 128:  # noqa: E721
            raise TrainingControlModelError("training-control hidden-unit count is invalid")
        if type(epochs) is not int or epochs < 1:  # noqa: E721
            raise TrainingControlModelError("training-control epoch count is invalid")
        if not math.isfinite(learning_rate) or learning_rate <= 0.0:
            raise TrainingControlModelError("training-control learning rate is invalid")
        if not math.isfinite(l2) or l2 < 0.0:
            raise TrainingControlModelError("training-control regularization is invalid")
        if not 0.0 <= class_balance_power <= 1.0:
            raise TrainingControlModelError("training-control class balance is invalid")
        lookup = {class_ref: index for index, class_ref in enumerate(observed)}
        x = np.vstack([example.observation.vector() for example in rows])
        y = np.asarray([lookup[example.action.value] for example in rows], dtype=np.int64)
        counts = np.bincount(y, minlength=len(observed)).astype(np.float64)
        sample_weights = counts[y] ** (-class_balance_power)
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
            gradient_scores = probabilities
            gradient_scores[np.arange(len(rows)), y] -= 1.0
            gradient_scores *= sample_weights[:, None] / len(rows)
            gradient_hidden = gradient_scores @ w2.T * (1.0 - hidden**2)
            gradients = (
                gradient_hidden.T @ x + l2 * w1,
                np.sum(gradient_hidden, axis=0),
                hidden.T @ gradient_scores + l2 * w2,
                np.sum(gradient_scores, axis=0),
            )
            for parameter, gradient, first, second in zip(
                parameters,
                gradients,
                first_moments,
                second_moments,
                strict=True,
            ):
                first *= beta1
                first += (1.0 - beta1) * gradient
                second *= beta2
                second += (1.0 - beta2) * gradient**2
                parameter -= (
                    learning_rate
                    * (first / (1.0 - beta1**step))
                    / (np.sqrt(second / (1.0 - beta2**step)) + epsilon)
                )
        return cls(
            class_refs=observed,
            input_weights=w1,
            hidden_bias=b1,
            output_weights=w2,
            output_bias=b2,
            training_seed=seed,
        )


def fit_training_control_candidate(
    training_datasets: Iterable[TrainingControlDataset],
    validation_datasets: Iterable[TrainingControlDataset],
    **fit_kwargs: object,
) -> TrainingControlCandidate:
    """Fit only after whole-lineage partition and class coverage pass."""

    training = tuple(training_datasets)
    validation = tuple(validation_datasets)
    audit = audit_training_control_partitions((*training, *validation))
    if not audit.promotion_eligible:
        raise TrainingControlModelError(
            f"training-control partitions are ineligible: {audit.reasons!r}"
        )
    if any(dataset.partition != "train" for dataset in training):
        raise TrainingControlModelError("training input contains a non-training lineage")
    if any(dataset.partition != "validation" for dataset in validation):
        raise TrainingControlModelError("validation input contains a non-validation lineage")
    train_rows = tuple(example for dataset in training for example in dataset.examples)
    validation_rows = tuple(example for dataset in validation for example in dataset.examples)
    model = TrainingControlMLP.fit(train_rows, **fit_kwargs)  # type: ignore[arg-type]
    return TrainingControlCandidate(
        model=model,
        model_sha256=canonical_sha256(model.to_dict()),
        training=evaluate_training_control_model(model, train_rows),
        validation=evaluate_training_control_model(model, validation_rows),
        training_lineages=tuple(dataset.lineage_id for dataset in training),
        validation_lineages=tuple(dataset.lineage_id for dataset in validation),
        source_artifact_sha256s=tuple(
            dataset.artifact_sha256 for dataset in (*training, *validation)
        ),
    )


def evaluate_training_control_model(
    model: TrainingControlMLP,
    examples: Iterable[TrainingControlExample],
) -> TrainingControlMetrics:
    rows = tuple(examples)
    if not rows:
        raise TrainingControlModelError("training-control evaluation examples are empty")
    counts = Counter(example.action.value for example in rows)
    correct = Counter[str]()
    losses: list[float] = []
    for example in rows:
        probabilities = model.probabilities(example.observation)
        predicted = max(probabilities, key=probabilities.__getitem__)
        correct[example.action.value] += int(predicted == example.action.value)
        losses.append(-math.log(max(probabilities.get(example.action.value, 0.0), 1e-12)))
    return TrainingControlMetrics(
        examples=len(rows),
        accuracy=sum(correct.values()) / len(rows),
        balanced_accuracy=sum(correct[name] / count for name, count in counts.items())
        / len(counts),
        cross_entropy=sum(losses) / len(losses),
        class_counts=dict(counts),
    )
