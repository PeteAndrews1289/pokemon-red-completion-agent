"""Conservative train-only updates from verified goal-manager outcomes."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from pokemon_red_completion.goal_manager import GoalManagerExample
from pokemon_red_completion.goal_manager_development import GoalManagerDevelopmentTarget
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    goal_manager_feature_matrix,
)

OUTCOME_UPDATE_STEP_SIZE = 0.02
OUTCOME_UPDATE_WEIGHT_DELTA_L2_CAP = 0.02
OUTCOME_UPDATE_MENU_KL_CAP = 0.01
OUTCOME_UPDATE_MAX_IMPORTANCE_WEIGHT = 4.0
OUTCOME_UPDATE_OBJECTIVE_ID = "pokemon.core.goal-manager.capped-ips-policy-gradient.v1"


class GoalManagerOutcomeLearningError(ValueError):
    """Raised when outcome evidence cannot support the frozen update."""


@dataclass(frozen=True, slots=True)
class GoalManagerOutcomeFitMetrics:
    examples: int
    positive_examples: int
    negative_examples: int
    weighted_binary_cross_entropy: float
    mean_selected_probability: float
    selected_probabilities: tuple[float, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.goal-manager-outcome-fit-metrics.v1",
            "examples": self.examples,
            "positive_examples": self.positive_examples,
            "negative_examples": self.negative_examples,
            "weighted_binary_cross_entropy": self.weighted_binary_cross_entropy,
            "mean_selected_probability": self.mean_selected_probability,
            "selected_probabilities": list(self.selected_probabilities),
        }


@dataclass(frozen=True, slots=True)
class GoalManagerOutcomeUpdate:
    model: GoalManagerLinearModel
    before: GoalManagerOutcomeFitMetrics
    after: GoalManagerOutcomeFitMetrics
    maximum_weight_delta: float
    weight_delta_l2: float

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.goal-manager-outcome-update.v1",
            "objective_id": OUTCOME_UPDATE_OBJECTIVE_ID,
            "step_size": OUTCOME_UPDATE_STEP_SIZE,
            "maximum_importance_weight": OUTCOME_UPDATE_MAX_IMPORTANCE_WEIGHT,
            "menu_kl_cap": OUTCOME_UPDATE_MENU_KL_CAP,
            "update_steps": 1,
            "before": self.before.public_dict(),
            "after": self.after.public_dict(),
            "maximum_weight_delta": self.maximum_weight_delta,
            "weight_delta_l2": self.weight_delta_l2,
            "weight_delta_l2_cap": OUTCOME_UPDATE_WEIGHT_DELTA_L2_CAP,
        }


@dataclass(frozen=True, slots=True)
class GoalManagerOutcomeSuccessorUpdate:
    """One fixed update plus no-regression measurements on earlier outcomes."""

    update: GoalManagerOutcomeUpdate
    anchor_before: GoalManagerOutcomeFitMetrics
    anchor_after: GoalManagerOutcomeFitMetrics

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.goal-manager-outcome-successor-update.v1",
            "update": self.update.public_dict(),
            "anchor_before": self.anchor_before.public_dict(),
            "anchor_after": self.anchor_after.public_dict(),
        }


def fit_goal_manager_outcome_update(
    base_model: GoalManagerLinearModel,
    rows: Iterable[tuple[GoalManagerExample, GoalManagerDevelopmentTarget]],
) -> GoalManagerOutcomeUpdate:
    """Apply one frozen full-batch outcome update from an authenticated base model."""

    if not isinstance(base_model, GoalManagerLinearModel):
        raise TypeError("base_model must be a GoalManagerLinearModel")
    evidence = _validated_rows(rows, expected_partition="development")
    return _fit_validated_goal_manager_outcome_update(base_model, evidence)


def fit_goal_manager_train_outcome_update(
    base_model: GoalManagerLinearModel,
    rows: Iterable[tuple[GoalManagerExample, GoalManagerDevelopmentTarget]],
) -> GoalManagerOutcomeUpdate:
    """Apply the frozen update to explicitly train-partitioned outcome evidence."""

    if not isinstance(base_model, GoalManagerLinearModel):
        raise TypeError("base_model must be a GoalManagerLinearModel")
    evidence = _validated_rows(rows, expected_partition="train")
    return _fit_validated_goal_manager_outcome_update(base_model, evidence)


def _fit_validated_goal_manager_outcome_update(
    base_model: GoalManagerLinearModel,
    evidence: tuple[tuple[GoalManagerExample, GoalManagerDevelopmentTarget], ...],
) -> GoalManagerOutcomeUpdate:
    before = evaluate_goal_manager_outcomes(
        base_model,
        evidence,
        expected_partition=evidence[0][0].partition,
    )
    gradient = np.zeros_like(base_model.weights)
    for example, target in evidence:
        features = goal_manager_feature_matrix(example.question)
        normalized = (features - base_model.feature_mean) / base_model.feature_scale
        available = np.asarray(example.question.available_indices, dtype=np.int64)
        probabilities = base_model.probabilities(example.question)
        selected = target.selected_candidate_index
        expectation = probabilities[available] @ normalized[available]
        selected_features = normalized[selected]
        gradient += target.importance_weight * target.reward * (selected_features - expectation)
    gradient /= len(evidence)
    delta = OUTCOME_UPDATE_STEP_SIZE * gradient
    delta_l2 = float(np.linalg.norm(delta))
    if delta_l2 > OUTCOME_UPDATE_WEIGHT_DELTA_L2_CAP:
        delta *= OUTCOME_UPDATE_WEIGHT_DELTA_L2_CAP / delta_l2
        delta_l2 = OUTCOME_UPDATE_WEIGHT_DELTA_L2_CAP
    candidate_weights = base_model.weights + delta
    if not np.all(np.isfinite(candidate_weights)):
        raise GoalManagerOutcomeLearningError("outcome update produced invalid weights")
    candidate = GoalManagerLinearModel(
        weights=candidate_weights,
        feature_mean=base_model.feature_mean,
        feature_scale=base_model.feature_scale,
        l2=base_model.l2,
        training_epochs=1,
    )
    after = evaluate_goal_manager_outcomes(
        candidate,
        evidence,
        expected_partition=evidence[0][0].partition,
    )
    comparisons = tuple(
        (target.reward, old, new)
        for (_, target), old, new in zip(
            evidence,
            before.selected_probabilities,
            after.selected_probabilities,
            strict=True,
        )
    )
    if any(
        new + 1e-12 < old if reward == 1.0 else new > old + 1e-12
        for reward, old, new in comparisons
    ) or not any(
        new > old + 1e-12 if reward == 1.0 else new + 1e-12 < old
        for reward, old, new in comparisons
    ):
        raise GoalManagerOutcomeLearningError(
            "outcome update did not move every settled choice in the rewarded direction"
        )
    if not after.weighted_binary_cross_entropy < before.weighted_binary_cross_entropy:
        raise GoalManagerOutcomeLearningError("outcome update did not reduce training loss")
    return GoalManagerOutcomeUpdate(
        model=candidate,
        before=before,
        after=after,
        maximum_weight_delta=float(np.max(np.abs(candidate.weights - base_model.weights))),
        weight_delta_l2=delta_l2,
    )


def fit_goal_manager_outcome_successor_update(
    base_model: GoalManagerLinearModel,
    new_rows: Iterable[tuple[GoalManagerExample, GoalManagerDevelopmentTarget]],
    anchor_rows: Iterable[tuple[GoalManagerExample, GoalManagerDevelopmentTarget]],
) -> GoalManagerOutcomeSuccessorUpdate:
    """Assimilate fresh evidence while preserving earlier settled choices.

    Anchor rows are evaluated but never included in the gradient.  This keeps the
    successor experiment from counting the same outcomes as fresh training data.
    """

    fresh = _validated_rows(new_rows, expected_partition="development")
    anchors = _validated_rows(anchor_rows, expected_partition="development")
    if {target.decision_id for _, target in fresh} & {target.decision_id for _, target in anchors}:
        raise GoalManagerOutcomeLearningError(
            "successor evidence overlaps its no-regression anchors"
        )
    update = fit_goal_manager_outcome_update(base_model, fresh)
    anchor_before = evaluate_goal_manager_outcomes(base_model, anchors)
    anchor_after = evaluate_goal_manager_outcomes(update.model, anchors)
    comparisons = zip(
        anchors,
        anchor_before.selected_probabilities,
        anchor_after.selected_probabilities,
        strict=True,
    )
    for (_, target), old, new in comparisons:
        regressed = new + 1e-12 < old if target.reward == 1.0 else new > old + 1e-12
        if regressed:
            raise GoalManagerOutcomeLearningError(
                "successor update regressed an earlier settled choice"
            )
    return GoalManagerOutcomeSuccessorUpdate(
        update=update,
        anchor_before=anchor_before,
        anchor_after=anchor_after,
    )


def evaluate_goal_manager_outcomes(
    model: GoalManagerLinearModel,
    rows: Iterable[tuple[GoalManagerExample, GoalManagerDevelopmentTarget]],
    *,
    expected_partition: str = "development",
) -> GoalManagerOutcomeFitMetrics:
    """Evaluate the frozen selected-action binary outcome objective."""

    evidence = _validated_rows(rows, expected_partition=expected_partition)
    losses: list[float] = []
    selected_probabilities: list[float] = []
    importance: list[float] = []
    for example, target in evidence:
        probability = float(model.probabilities(example.question)[target.selected_candidate_index])
        selected_probabilities.append(probability)
        importance.append(target.importance_weight)
        likelihood = probability if target.reward == 1.0 else 1.0 - probability
        losses.append(-math.log(max(likelihood, 1e-12)))
    total_importance = sum(importance)
    weighted_loss = (
        sum(weight * loss for weight, loss in zip(importance, losses, strict=True))
        / total_importance
    )
    return GoalManagerOutcomeFitMetrics(
        examples=len(evidence),
        positive_examples=sum(target.reward == 1.0 for _, target in evidence),
        negative_examples=sum(target.reward == -1.0 for _, target in evidence),
        weighted_binary_cross_entropy=weighted_loss,
        mean_selected_probability=sum(selected_probabilities) / len(evidence),
        selected_probabilities=tuple(selected_probabilities),
    )


def require_unchanged_guard_winners(
    base_model: GoalManagerLinearModel,
    candidate_model: GoalManagerLinearModel,
    guard_examples: Sequence[GoalManagerExample],
) -> None:
    """Reject an update that flips a protected train-only semantic winner."""

    if not guard_examples:
        raise GoalManagerOutcomeLearningError("outcome update guard set is empty")
    for example in guard_examples:
        if base_model.predict(example.question) != candidate_model.predict(example.question):
            raise GoalManagerOutcomeLearningError(
                "outcome update changed a protected train-only winner"
            )


def maximum_policy_kl(
    base_model: GoalManagerLinearModel,
    candidate_model: GoalManagerLinearModel,
    examples: Sequence[GoalManagerExample],
) -> float:
    """Return the largest base-to-candidate KL over authenticated menus."""

    if not examples:
        raise GoalManagerOutcomeLearningError("outcome update KL set is empty")
    maximum = 0.0
    for example in examples:
        base = base_model.probabilities(example.question)
        candidate = candidate_model.probabilities(example.question)
        available = np.asarray(example.question.available_indices, dtype=np.int64)
        divergence = float(
            np.sum(
                base[available]
                * np.log(
                    np.maximum(base[available], 1e-12) / np.maximum(candidate[available], 1e-12)
                )
            )
        )
        maximum = max(maximum, divergence)
    return maximum


def outcome_update_configuration() -> dict[str, object]:
    """Return the fixed, non-searchable two-target update contract."""

    return {
        "schema": "pokemon.core.goal-manager-outcome-update-configuration.v1",
        "objective_id": OUTCOME_UPDATE_OBJECTIVE_ID,
        "update_steps": 1,
        "optimizer": "full_batch_gradient_descent",
        "step_size": OUTCOME_UPDATE_STEP_SIZE,
        "weight_delta_l2_cap": OUTCOME_UPDATE_WEIGHT_DELTA_L2_CAP,
        "menu_kl_cap": OUTCOME_UPDATE_MENU_KL_CAP,
        "importance_weight": "inverse_behavior_probability_capped",
        "maximum_importance_weight": OUTCOME_UPDATE_MAX_IMPORTANCE_WEIGHT,
        "normalization": "frozen_authenticated_base",
        "initialization": "frozen_authenticated_base_weights",
        "hyperparameter_search": False,
    }


def _validated_rows(
    rows: Iterable[tuple[GoalManagerExample, GoalManagerDevelopmentTarget]],
    *,
    expected_partition: str,
) -> tuple[tuple[GoalManagerExample, GoalManagerDevelopmentTarget], ...]:
    if expected_partition not in {"train", "development"}:
        raise GoalManagerOutcomeLearningError("outcome update partition is invalid")
    result = tuple(rows)
    if not result:
        raise GoalManagerOutcomeLearningError("outcome update evidence is empty")
    if len({target.decision_id for _, target in result}) != len(result):
        raise GoalManagerOutcomeLearningError("outcome update decision identities repeat")
    for example, target in result:
        if not isinstance(example, GoalManagerExample) or not isinstance(
            target, GoalManagerDevelopmentTarget
        ):
            raise TypeError("outcome update rows are invalid")
        if (
            example.partition != expected_partition
            or example.decision_id != target.decision_id
            or example.selected_candidate_index != target.selected_candidate_index
            or target.selected_candidate_index not in example.question.available_indices
            or target.reward not in {-1.0, 1.0}
            or not math.isfinite(target.behavior_probability)
            or not 0.0 < target.behavior_probability <= 1.0
            or not math.isfinite(target.importance_weight)
            or not 1.0 <= target.importance_weight <= OUTCOME_UPDATE_MAX_IMPORTANCE_WEIGHT
            or target.importance_weight
            != min(
                OUTCOME_UPDATE_MAX_IMPORTANCE_WEIGHT,
                1.0 / target.behavior_probability,
            )
        ):
            raise GoalManagerOutcomeLearningError("outcome update row differs")
    return result


__all__ = [
    "GoalManagerOutcomeFitMetrics",
    "GoalManagerOutcomeLearningError",
    "GoalManagerOutcomeUpdate",
    "GoalManagerOutcomeSuccessorUpdate",
    "OUTCOME_UPDATE_MAX_IMPORTANCE_WEIGHT",
    "OUTCOME_UPDATE_MENU_KL_CAP",
    "OUTCOME_UPDATE_OBJECTIVE_ID",
    "OUTCOME_UPDATE_STEP_SIZE",
    "OUTCOME_UPDATE_WEIGHT_DELTA_L2_CAP",
    "evaluate_goal_manager_outcomes",
    "fit_goal_manager_outcome_update",
    "fit_goal_manager_outcome_successor_update",
    "fit_goal_manager_train_outcome_update",
    "maximum_policy_kl",
    "outcome_update_configuration",
    "require_unchanged_guard_winners",
]
