"""Shared-candidate model for portable long-horizon goal arbitration.

Every option is scored by the same function.  Candidate order therefore has no
meaning, unavailable options receive zero probability, and game-specific
bindings never enter the feature matrix.  The model is intentionally small: it
is a first transferable manager seam, not a claim that a linear ranker is the
eventual final architecture.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.goal_manager import (
    BoundGoalSelection,
    GoalAvailability,
    GoalKind,
    GoalManagerExample,
    GoalManagerQuestion,
    GoalNeed,
    bind_goal_selection,
)

GOAL_MANAGER_FEATURE_SCHEMA_ID = "pokemon.core.goal-manager.shared-candidate.v1"
GOAL_MANAGER_MODEL_ID = "pokemon.core.goal-manager.linear.v1"
GOAL_MANAGER_FIT_EPOCHS = 800
GOAL_MANAGER_FIT_LEARNING_RATE = 0.02
GOAL_MANAGER_FIT_L2 = 0.02

# A deliberately simple, preregistered comparator: recover control and safety
# first, then unblock resources/storage, then favor story progress over the
# remaining optional work.  It never observes the need pressures.
FIXED_GOAL_KIND_PRIORITY = (
    GoalKind.RECOVER_CONTROL,
    GoalKind.RESTORE_TEAM,
    GoalKind.RESUPPLY,
    GoalKind.MANAGE_STORAGE,
    GoalKind.ADVANCE_STORY,
    GoalKind.DEVELOP_TEAM,
    GoalKind.EVOLVE_SPECIES,
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.EXPLORE,
)

GOAL_MANAGER_FEATURE_NAMES = (
    "set.available_count_scaled",
    "candidate.available",
    "candidate.estimated_effort",
    "candidate.estimated_risk",
    "candidate.effort_relative_rank",
    "candidate.risk_relative_rank",
    *(f"candidate.kind.{kind.value}" for kind in GoalKind),
    *(f"candidate.addresses.{need.value}" for need in GoalNeed),
    *(f"context_x_candidate.{need.value}" for need in GoalNeed),
    "candidate.addressed_pressure_mean",
    "candidate.addressed_pressure_max",
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class GoalManagerModelInput(Protocol):
    """Minimal identity-free question accepted by the scorer."""

    @property
    def opportunities(self) -> tuple[object, ...]: ...

    @property
    def available_indices(self) -> tuple[int, ...]: ...

    @property
    def policy_input(self) -> Mapping[str, object]: ...


class GoalManagerScorer(Protocol):
    """Model boundary implemented by linear and future nonlinear managers."""

    def probabilities(self, question: GoalManagerQuestion) -> NDArray[np.float64]: ...

    def to_dict(self) -> dict[str, object]: ...


class GoalManagerModelError(ValueError):
    """Raised when a goal-manager model or feature projection is invalid."""


@dataclass(frozen=True, slots=True)
class GoalManagerBaselineMetrics:
    """Paired comparison against one preregistered non-learned policy."""

    baseline_id: str
    accuracy: float
    model_wins: int
    model_losses: int
    paired_two_sided_exact_p: float

    def public_dict(self) -> dict[str, object]:
        return {
            "accuracy": self.accuracy,
            "paired_comparison": {
                "wins": self.model_wins,
                "losses": self.model_losses,
                "two_sided_exact_p": self.paired_two_sided_exact_p,
            },
        }


@dataclass(frozen=True, slots=True)
class GoalManagerMetrics:
    examples: int
    accuracy: float
    cross_entropy: float
    baseline_comparisons: tuple[GoalManagerBaselineMetrics, ...]
    environment_accuracy: tuple[tuple[str, float], ...]
    selected_kind_accuracy: tuple[tuple[str, float], ...]

    @property
    def lowest_effort_baseline_accuracy(self) -> float:
        return self._baseline("lowest_effort").accuracy

    @property
    def paired_wins_over_lowest_effort(self) -> int:
        return self._baseline("lowest_effort").model_wins

    @property
    def paired_losses_to_lowest_effort(self) -> int:
        return self._baseline("lowest_effort").model_losses

    @property
    def paired_two_sided_exact_p(self) -> float:
        return self._baseline("lowest_effort").paired_two_sided_exact_p

    def _baseline(self, baseline_id: str) -> GoalManagerBaselineMetrics:
        try:
            return next(
                item for item in self.baseline_comparisons if item.baseline_id == baseline_id
            )
        except StopIteration as error:  # pragma: no cover - evaluator constructs the record
            raise GoalManagerModelError("goal-manager baseline comparison is absent") from error

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.goal-manager-metrics.v1",
            "examples": self.examples,
            "accuracy": self.accuracy,
            "cross_entropy": self.cross_entropy,
            "baselines": {
                item.baseline_id: item.public_dict() for item in self.baseline_comparisons
            },
            "environment_accuracy": dict(self.environment_accuracy),
            "selected_kind_accuracy": dict(self.selected_kind_accuracy),
        }


@dataclass(frozen=True, slots=True)
class GoalManagerLinearModel:
    """A small permutation-equivariant conditional-choice model."""

    weights: NDArray[np.float64]
    feature_mean: NDArray[np.float64]
    feature_scale: NDArray[np.float64]
    l2: float
    training_epochs: int
    model_id: str = GOAL_MANAGER_MODEL_ID
    feature_schema_id: str = GOAL_MANAGER_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        width = len(GOAL_MANAGER_FEATURE_NAMES)
        arrays = tuple(
            np.asarray(value, dtype=np.float64)
            for value in (self.weights, self.feature_mean, self.feature_scale)
        )
        weights, mean, scale = arrays
        if self.model_id != GOAL_MANAGER_MODEL_ID:
            raise GoalManagerModelError("goal-manager model identity is unsupported")
        if self.feature_schema_id != GOAL_MANAGER_FEATURE_SCHEMA_ID:
            raise GoalManagerModelError("goal-manager feature schema is unsupported")
        if any(value.shape != (width,) for value in arrays):
            raise GoalManagerModelError("goal-manager model shapes are invalid")
        if not all(np.all(np.isfinite(value)) for value in arrays) or np.any(scale <= 0):
            raise GoalManagerModelError("goal-manager model parameters are invalid")
        if (
            isinstance(self.l2, bool)
            or not isinstance(self.l2, (int, float))
            or not math.isfinite(float(self.l2))
            or self.l2 < 0
        ):
            raise GoalManagerModelError("goal-manager regularization is invalid")
        if type(self.training_epochs) is not int or self.training_epochs < 1:  # noqa: E721
            raise GoalManagerModelError("goal-manager epoch count is invalid")
        object.__setattr__(self, "l2", float(self.l2))
        for name, value in zip(("weights", "feature_mean", "feature_scale"), arrays, strict=True):
            detached = value.copy()
            detached.setflags(write=False)
            object.__setattr__(self, name, detached)

    def scores(self, question: GoalManagerQuestion) -> NDArray[np.float64]:
        features = goal_manager_feature_matrix(question)
        normalized = (features - self.feature_mean) / self.feature_scale
        scores = normalized @ self.weights
        if scores.shape != (len(question.opportunities),) or not np.all(np.isfinite(scores)):
            raise GoalManagerModelError("goal-manager candidate scores are invalid")
        masked = scores.copy()
        unavailable = np.ones(len(question.opportunities), dtype=np.bool_)
        unavailable[list(question.available_indices)] = False
        masked[unavailable] = -np.inf
        return masked

    def probabilities(self, question: GoalManagerQuestion) -> NDArray[np.float64]:
        scores = self.scores(question)
        finite = np.isfinite(scores)
        shifted = scores[finite] - np.max(scores[finite])
        result = np.zeros_like(scores)
        result[finite] = np.exp(shifted)
        result /= np.sum(result)
        return result

    def predict(self, question: GoalManagerQuestion) -> int:
        return int(np.argmax(self.probabilities(question)))

    def to_dict(self) -> dict[str, object]:
        return {
            "feature_mean": self.feature_mean.tolist(),
            "feature_names": list(GOAL_MANAGER_FEATURE_NAMES),
            "feature_scale": self.feature_scale.tolist(),
            "feature_schema_id": self.feature_schema_id,
            "format_version": 1,
            "l2": self.l2,
            "model_id": self.model_id,
            "training_epochs": self.training_epochs,
            "weights": self.weights.tolist(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> GoalManagerLinearModel:
        l2 = value.get("l2")
        epochs = value.get("training_epochs")
        names = value.get("feature_names")
        if (
            value.get("format_version") != 1
            or value.get("model_id") != GOAL_MANAGER_MODEL_ID
            or value.get("feature_schema_id") != GOAL_MANAGER_FEATURE_SCHEMA_ID
            or not isinstance(names, list)
            or tuple(names) != GOAL_MANAGER_FEATURE_NAMES
            or isinstance(l2, bool)
            or not isinstance(l2, (int, float))
            or type(epochs) is not int  # noqa: E721
        ):
            raise GoalManagerModelError("goal-manager model record is incompatible")
        try:
            return cls(
                weights=np.asarray(value["weights"], dtype=np.float64),
                feature_mean=np.asarray(value["feature_mean"], dtype=np.float64),
                feature_scale=np.asarray(value["feature_scale"], dtype=np.float64),
                l2=float(l2),
                training_epochs=epochs,
            )
        except GoalManagerModelError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise GoalManagerModelError("goal-manager model record is invalid") from error

    @classmethod
    def fit(
        cls,
        examples: Iterable[GoalManagerExample],
        *,
        epochs: int = GOAL_MANAGER_FIT_EPOCHS,
        learning_rate: float = GOAL_MANAGER_FIT_LEARNING_RATE,
        l2: float = GOAL_MANAGER_FIT_L2,
    ) -> GoalManagerLinearModel:
        """Fit only successful teacher choices from the training partition."""

        rows = tuple(examples)
        if not rows or any(item.partition != "train" for item in rows):
            raise GoalManagerModelError(
                "goal-manager fitting requires training-partition examples only"
            )
        if any(item.teacher_choice_target is None for item in rows):
            raise GoalManagerModelError("goal-manager fitting requires successful teacher labels")
        if len({item.question.policy_context_sha256 for item in rows}) != len(rows):
            raise GoalManagerModelError("goal-manager fitting requires unique policy contexts")
        if len({item.selected_kind for item in rows}) < 2:
            raise GoalManagerModelError(
                "goal-manager fitting requires more than one selected goal kind"
            )
        if type(epochs) is not int or epochs < 1:  # noqa: E721
            raise GoalManagerModelError("goal-manager epoch count is invalid")
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
            raise GoalManagerModelError("goal-manager optimizer settings are invalid")

        matrices = tuple(goal_manager_feature_matrix(item.question) for item in rows)
        all_features = np.concatenate(matrices, axis=0)
        mean = np.mean(all_features, axis=0)
        scale = np.std(all_features, axis=0)
        inactive = scale < 1e-8
        scale[inactive] = 1.0
        normalized = tuple((matrix - mean) / scale for matrix in matrices)
        weights = np.zeros(len(GOAL_MANAGER_FEATURE_NAMES), dtype=np.float64)
        first = np.zeros_like(weights)
        second = np.zeros_like(weights)
        for epoch in range(1, epochs + 1):
            gradient = np.zeros_like(weights)
            for item, features in zip(rows, normalized, strict=True):
                available = np.asarray(item.question.available_indices, dtype=np.int64)
                logits = features[available] @ weights
                probabilities = np.exp(logits - np.max(logits))
                probabilities /= np.sum(probabilities)
                target = item.teacher_choice_target
                assert target is not None
                target_position = int(np.flatnonzero(available == target)[0])
                probabilities[target_position] -= 1.0
                gradient += features[available].T @ probabilities
            gradient = gradient / len(rows) + float(l2) * weights
            gradient[inactive] = 0.0
            first = 0.9 * first + 0.1 * gradient
            second = 0.999 * second + 0.001 * gradient * gradient
            weights -= (
                float(learning_rate)
                * (first / (1.0 - math.pow(0.9, epoch)))
                / (np.sqrt(second / (1.0 - math.pow(0.999, epoch))) + 1e-8)
            )
            weights[inactive] = 0.0
        return cls(
            weights=weights,
            feature_mean=mean,
            feature_scale=scale,
            l2=float(l2),
            training_epochs=epochs,
        )


def goal_manager_fit_configuration() -> dict[str, object]:
    """Return the source-bound optimizer settings used by counted fitting.

    The development-validation partition must not become a hyperparameter
    search set.  The production fitting command therefore consumes this fixed
    record instead of accepting optimizer settings from its command line.
    """

    return {
        "epochs": GOAL_MANAGER_FIT_EPOCHS,
        "l2": GOAL_MANAGER_FIT_L2,
        "learning_rate": GOAL_MANAGER_FIT_LEARNING_RATE,
        "model_id": GOAL_MANAGER_MODEL_ID,
        "schema": "pokemon-core-goal-manager-fit-configuration-v1",
        "selection": "fixed_before_context_collection",
    }


@dataclass(slots=True)
class LearnedGoalManagerPolicy:
    """Causal no-fallback boundary between a scorer and private goal bindings."""

    model: GoalManagerScorer
    confidence_threshold: float = 0.0
    decisions: int = 0
    learned_choice_decisions: int = 0
    fixed_dispatch_decisions: int = 0
    confidence_total: float = 0.0
    minimum_confidence: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise GoalManagerModelError(
                "goal-manager confidence threshold must be between zero and one"
            )

    def select(self, question: GoalManagerQuestion) -> BoundGoalSelection:
        """Authorize exactly the model's available choice, with no teacher query."""

        if not isinstance(question, GoalManagerQuestion):
            raise TypeError("question must be a GoalManagerQuestion")
        probabilities = np.asarray(self.model.probabilities(question), dtype=np.float64)
        if probabilities.shape != (len(question.opportunities),):
            raise GoalManagerModelError("goal-manager probability shape is invalid")
        if (
            not np.all(np.isfinite(probabilities))
            or np.any(probabilities < 0.0)
            or not math.isclose(float(np.sum(probabilities)), 1.0, abs_tol=1e-9)
        ):
            raise GoalManagerModelError("goal-manager probabilities are invalid")
        unavailable = set(range(len(question.opportunities))) - set(question.available_indices)
        if any(probabilities[index] != 0.0 for index in unavailable):
            raise GoalManagerModelError(
                "goal-manager scorer assigned authority to an unavailable option"
            )
        selected_index = int(np.argmax(probabilities))
        confidence = float(probabilities[selected_index])
        if confidence < self.confidence_threshold:
            raise GoalManagerModelError("goal-manager confidence is below threshold")
        selection = bind_goal_selection(question, selected_index)
        self.decisions += 1
        self.confidence_total += confidence
        self.minimum_confidence = min(self.minimum_confidence, confidence)
        if len(question.available_indices) >= 2:
            self.learned_choice_decisions += 1
        else:
            self.fixed_dispatch_decisions += 1
        return selection

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.goal-manager-live-policy.v1",
            "model_sha256": canonical_goal_manager_model_record_sha256(self.model.to_dict()),
            "decisions": self.decisions,
            "learned_choice_decisions": self.learned_choice_decisions,
            "fixed_dispatch_decisions": self.fixed_dispatch_decisions,
            "mean_confidence": (self.confidence_total / self.decisions if self.decisions else 0.0),
            "minimum_confidence": (self.minimum_confidence if self.decisions else 0.0),
            "teacher_queries": 0,
            "teacher_fallbacks": 0,
        }


def goal_manager_feature_matrix(
    question: GoalManagerQuestion,
) -> NDArray[np.float64]:
    """Project a variable-sized identity-free question into shared rows."""

    if not isinstance(question, GoalManagerQuestion):
        raise TypeError("question must be a GoalManagerQuestion")
    available = tuple(
        item for item in question.opportunities if item.availability is GoalAvailability.AVAILABLE
    )
    efforts = tuple(_known_metric(item.estimated_effort) for item in available)
    risks = tuple(_known_metric(item.estimated_risk) for item in available)
    rows: list[list[float]] = []
    for item in question.opportunities:
        is_available = item.availability is GoalAvailability.AVAILABLE
        effort = _known_metric(item.estimated_effort) if is_available else 0.0
        risk = _known_metric(item.estimated_risk) if is_available else 0.0
        addressed = frozenset(item.addressed_needs)
        pressures = tuple(question.situation.pressure(need) for need in addressed)
        row = [
            min(len(available), 8) / 8.0,
            float(is_available),
            effort,
            risk,
            _relative_rank(effort, efforts) if is_available else 0.0,
            _relative_rank(risk, risks) if is_available else 0.0,
        ]
        row.extend(float(item.kind is kind) for kind in GoalKind)
        row.extend(float(need in addressed) for need in GoalNeed)
        row.extend(
            question.situation.pressure(need) * float(need in addressed) for need in GoalNeed
        )
        row.extend(
            (
                sum(pressures) / len(pressures),
                max(pressures),
            )
        )
        rows.append(row)
    result = np.asarray(rows, dtype=np.float64)
    if result.shape != (
        len(question.opportunities),
        len(GOAL_MANAGER_FEATURE_NAMES),
    ):
        raise GoalManagerModelError("goal-manager feature width drifted")
    if not np.all(np.isfinite(result)):
        raise GoalManagerModelError("goal-manager features are not finite")
    return result


def evaluate_goal_manager_model(
    model: GoalManagerLinearModel,
    examples: Iterable[GoalManagerExample],
) -> GoalManagerMetrics:
    """Evaluate a frozen manager without using environment identity as input."""

    rows = tuple(examples)
    if not rows or any(item.teacher_choice_target is None for item in rows):
        raise GoalManagerModelError("goal-manager evaluation requires successful teacher labels")
    baseline_selectors = {
        "fixed_priority": fixed_priority_goal_index,
        "highest_pressure": highest_pressure_goal_index,
        "lowest_effort": lowest_effort_goal_index,
    }
    baseline_counts = {
        baseline_id: {"correct": 0, "wins": 0, "losses": 0} for baseline_id in baseline_selectors
    }
    correct = 0
    loss = 0.0
    environment_scores: dict[str, list[int]] = {}
    kind_scores: dict[GoalKind, list[int]] = {}
    for item in rows:
        target = item.teacher_choice_target
        assert target is not None
        probabilities = model.probabilities(item.question)
        predicted = int(np.argmax(probabilities))
        model_hit = predicted == target
        correct += model_hit
        for baseline_id, selector in baseline_selectors.items():
            baseline_hit = selector(item.question) == target
            baseline_counts[baseline_id]["correct"] += baseline_hit
            baseline_counts[baseline_id]["wins"] += model_hit and not baseline_hit
            baseline_counts[baseline_id]["losses"] += baseline_hit and not model_hit
        loss -= math.log(max(float(probabilities[target]), 1e-15))
        environment_scores.setdefault(item.environment_id, []).append(int(model_hit))
        kind_scores.setdefault(item.selected_kind, []).append(int(model_hit))
    return GoalManagerMetrics(
        examples=len(rows),
        accuracy=correct / len(rows),
        cross_entropy=loss / len(rows),
        baseline_comparisons=tuple(
            GoalManagerBaselineMetrics(
                baseline_id=baseline_id,
                accuracy=counts["correct"] / len(rows),
                model_wins=counts["wins"],
                model_losses=counts["losses"],
                paired_two_sided_exact_p=_paired_two_sided_exact_p(
                    counts["wins"], counts["losses"]
                ),
            )
            for baseline_id, counts in sorted(baseline_counts.items())
        ),
        environment_accuracy=tuple(
            (environment, sum(values) / len(values))
            for environment, values in sorted(environment_scores.items())
        ),
        selected_kind_accuracy=tuple(
            (kind.value, sum(values) / len(values))
            for kind, values in sorted(kind_scores.items(), key=lambda item: item[0].value)
        ),
    )


def fixed_priority_goal_index(question: GoalManagerQuestion) -> int:
    """Return a safety-first static ordering that never observes need pressure."""

    priority = {kind: index for index, kind in enumerate(FIXED_GOAL_KIND_PRIORITY)}
    return min(
        question.available_indices,
        key=lambda index: (
            priority[question.opportunities[index].kind],
            _known_metric(question.opportunities[index].estimated_effort),
            _known_metric(question.opportunities[index].estimated_risk),
        ),
    )


def highest_pressure_goal_index(question: GoalManagerQuestion) -> int:
    """Return the strongest hand-authored need-pressure heuristic."""

    def key(index: int) -> tuple[float, float, float, float, str]:
        opportunity = question.opportunities[index]
        pressures = tuple(question.situation.pressure(need) for need in opportunity.addressed_needs)
        return (
            -max(pressures),
            -(sum(pressures) / len(pressures)),
            _known_metric(opportunity.estimated_risk),
            _known_metric(opportunity.estimated_effort),
            opportunity.kind.value,
        )

    return min(question.available_indices, key=key)


def lowest_effort_goal_index(question: GoalManagerQuestion) -> int:
    """Return the deterministic convenience baseline for paired evaluation."""

    return min(
        question.available_indices,
        key=lambda index: (
            _known_metric(question.opportunities[index].estimated_effort),
            _known_metric(question.opportunities[index].estimated_risk),
            question.opportunities[index].kind.value,
        ),
    )


def canonical_goal_manager_model_sha256(model: GoalManagerLinearModel) -> str:
    return canonical_goal_manager_model_record_sha256(model.to_dict())


def canonical_goal_manager_model_record_sha256(
    value: Mapping[str, object],
) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def load_goal_manager_model(
    path: str | Path,
    *,
    expected_sha256: str,
) -> GoalManagerLinearModel:
    """Load one regular authenticated artifact and reject incompatible schemas."""

    if _SHA256.fullmatch(expected_sha256) is None:
        raise GoalManagerModelError("expected goal-manager digest is invalid")
    source = Path(path)
    try:
        metadata = source.lstat()
        payload = source.read_bytes()
    except OSError as error:
        raise GoalManagerModelError("goal-manager model cannot be read") from error
    if source.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise GoalManagerModelError("goal-manager model must be a regular file")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise GoalManagerModelError("goal-manager model failed authentication")
    try:
        value = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise GoalManagerModelError("goal-manager model is invalid JSON") from error
    if not isinstance(value, Mapping):
        raise GoalManagerModelError("goal-manager model must be an object")
    return GoalManagerLinearModel.from_dict(value)


def _relative_rank(value: float, values: tuple[float, ...]) -> float:
    ordered = sorted(values)
    if len(ordered) <= 1:
        return 0.0
    return ordered.index(value) / (len(ordered) - 1)


def _known_metric(value: float | None) -> float:
    if value is None:  # pragma: no cover - availability validation establishes this
        raise GoalManagerModelError("available goal is missing a normalized metric")
    return float(value)


def _paired_two_sided_exact_p(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / math.pow(2.0, discordant))
