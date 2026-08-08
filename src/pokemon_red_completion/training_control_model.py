"""Class-balanced, phase-masked model for portable training decisions."""

from __future__ import annotations

import hashlib
import json
import math
import re
import stat
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

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
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


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
    def from_dict(cls, raw: object) -> TrainingControlMLP:
        """Decode only the exact portable model format emitted by ``to_dict``."""

        if not isinstance(raw, Mapping):
            raise TrainingControlModelError("training-control model must be an object")
        expected = {
            "format_version", "model_id", "feature_schema_id", "feature_names",
            "class_refs", "training_seed", "input_weights", "hidden_bias",
            "output_weights", "output_bias",
        }
        if set(raw) != expected:
            raise TrainingControlModelError("training-control model fields are incompatible")
        if raw.get("format_version") != 1 or raw.get("model_id") != TRAINING_CONTROL_MODEL_ID:
            raise TrainingControlModelError("training-control model format is unsupported")
        names = raw.get("feature_names")
        classes = raw.get("class_refs")
        if not isinstance(names, list) or tuple(names) != TRAINING_CONTROL_FEATURE_NAMES:
            raise TrainingControlModelError("training-control feature names are incompatible")
        if not isinstance(classes, list) or not all(isinstance(value, str) for value in classes):
            raise TrainingControlModelError("training-control model classes are invalid")
        arrays = tuple(
            raw.get(name)
            for name in ("input_weights", "hidden_bias", "output_weights", "output_bias")
        )
        if any(not isinstance(value, list) for value in arrays):
            raise TrainingControlModelError("training-control model parameters are invalid")
        seed = raw.get("training_seed")
        schema = raw.get("feature_schema_id")
        return cls(
            class_refs=classes,
            input_weights=arrays[0],  # type: ignore[arg-type]
            hidden_bias=arrays[1],  # type: ignore[arg-type]
            output_weights=arrays[2],  # type: ignore[arg-type]
            output_bias=arrays[3],  # type: ignore[arg-type]
            training_seed=seed,  # type: ignore[arg-type]
            feature_schema_id=schema,  # type: ignore[arg-type]
        )

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
        legal = np.asarray(
            [
                [
                    TrainingControlAction(class_ref) in example.observation.candidate_actions
                    for class_ref in observed
                ]
                for example in rows
            ],
            dtype=bool,
        )
        if not np.all(legal[np.arange(len(rows)), y]):
            raise TrainingControlModelError("teacher action is absent from its candidate set")
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
            scores = np.where(legal, scores, -np.inf)
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


def load_training_control_model(
    path: str | Path,
    *,
    expected_sha256: str,
) -> TrainingControlMLP:
    """Authenticate and decode one private model artifact without following links."""

    if _SHA256.fullmatch(expected_sha256) is None:
        raise TrainingControlModelError("expected model digest is invalid")
    source = Path(path)
    try:
        metadata = source.lstat()
        payload = source.read_bytes()
    except OSError as error:
        raise TrainingControlModelError("training-control model cannot be read") from error
    if source.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise TrainingControlModelError("training-control model must be a regular file")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise TrainingControlModelError("training-control model failed authentication")
    try:
        raw = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise TrainingControlModelError("training-control model is invalid JSON") from error
    return TrainingControlMLP.from_dict(raw)


@dataclass(slots=True)
class TrainingControlShadowAudit:
    """Observe teacher decisions without granting the model execution authority."""

    model: TrainingControlMLP
    decisions: int = 0
    agreements: int = 0
    confidence_total: float = 0.0
    teacher_counts: Counter[str] = field(default_factory=Counter)
    correct_counts: Counter[str] = field(default_factory=Counter)
    predicted_counts: Counter[str] = field(default_factory=Counter)
    phase_counts: Counter[str] = field(default_factory=Counter)
    phase_agreements: Counter[str] = field(default_factory=Counter)
    confusion: Counter[str] = field(default_factory=Counter)
    phase_confusion: Counter[str] = field(default_factory=Counter)
    candidate_counts: Counter[str] = field(default_factory=Counter)
    forced_decisions: int = 0
    forced_agreements: int = 0
    genuine_decisions: int = 0
    genuine_agreements: int = 0

    def observe(self, decision: object) -> None:
        from pokemon_red_completion.training_control import TrainingControlDecision

        if not isinstance(decision, TrainingControlDecision):
            raise TypeError("shadow input must be a TrainingControlDecision")
        probabilities = self.model.probabilities(decision.observation)
        predicted = max(probabilities, key=probabilities.__getitem__)
        actual = decision.action.value
        phase = decision.observation.phase.value
        agreed = predicted == actual
        self.decisions += 1
        self.agreements += int(agreed)
        self.confidence_total += probabilities[predicted]
        self.teacher_counts[actual] += 1
        self.correct_counts[actual] += int(agreed)
        self.predicted_counts[predicted] += 1
        self.phase_counts[phase] += 1
        self.phase_agreements[phase] += int(agreed)
        self.confusion[f"{actual} -> {predicted}"] += 1
        self.phase_confusion[f"{phase}: {actual} -> {predicted}"] += 1
        candidates = "/".join(action.value for action in decision.observation.candidate_actions)
        self.candidate_counts[candidates] += 1
        if len(decision.observation.candidate_actions) == 1:
            self.forced_decisions += 1
            self.forced_agreements += int(agreed)
        else:
            self.genuine_decisions += 1
            self.genuine_agreements += int(agreed)

    def public_dict(self) -> dict[str, object]:
        balanced = (
            sum(self.correct_counts[name] / count for name, count in self.teacher_counts.items())
            / len(self.teacher_counts)
            if self.teacher_counts
            else 0.0
        )
        return {
            "schema": "pokemon-training-control-shadow-summary-v1",
            "model_id": self.model.model_id,
            "model_sha256": canonical_sha256(self.model.to_dict()),
            "decisions": self.decisions,
            "agreements": self.agreements,
            "accuracy": self.agreements / self.decisions if self.decisions else 0.0,
            "balanced_accuracy": balanced,
            "mean_confidence": self.confidence_total / self.decisions if self.decisions else 0.0,
            "teacher_counts": dict(sorted(self.teacher_counts.items())),
            "predicted_counts": dict(sorted(self.predicted_counts.items())),
            "phase_accuracy": {
                phase: self.phase_agreements[phase] / count
                for phase, count in sorted(self.phase_counts.items())
            },
            "confusion": dict(sorted(self.confusion.items())),
            "phase_confusion": dict(sorted(self.phase_confusion.items())),
            "candidate_counts": dict(sorted(self.candidate_counts.items())),
            "forced_decisions": self.forced_decisions,
            "forced_accuracy": (
                self.forced_agreements / self.forced_decisions if self.forced_decisions else 0.0
            ),
            "genuine_decisions": self.genuine_decisions,
            "genuine_accuracy": (
                self.genuine_agreements / self.genuine_decisions
                if self.genuine_decisions
                else 0.0
            ),
            "operational_errors": {
                "unnecessary_heal": self.confusion["seek -> heal"],
                "missed_required_heal": self.confusion["heal -> seek"]
                + self.confusion["heal -> stop"],
                "premature_stop": sum(
                    count
                    for key, count in self.confusion.items()
                    if not key.startswith("stop ->") and key.endswith(" -> stop")
                ),
                "missed_stop": sum(
                    count
                    for key, count in self.confusion.items()
                    if key.startswith("stop ->") and key != "stop -> stop"
                ),
            },
            "model_had_execution_authority": False,
            "promotion_eligible": False,
        }


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
