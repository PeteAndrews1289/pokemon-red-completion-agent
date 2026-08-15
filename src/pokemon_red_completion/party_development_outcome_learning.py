"""Outcome adaptation for the completion-aware party-development scorer.

The v1 candidate ranker is a useful teacher-derived prior, not evidence that a
model knows which choice works.  This module embeds that scorer exactly in the
v2 feature space, then performs a bounded, prior-anchored update from measured
counterfactual outcomes.  Train and development roots remain separate and no
teacher selection is accepted as an outcome target.
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

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    PartyDevelopmentCandidateSet,
)
from pokemon_red_completion.scenario_lab import ScenarioFamily, ScenarioPartition
from pokemon_red_completion.scenario_outcomes import ScenarioOutcomeExample
from pokemon_red_completion.training_candidate_model import (
    TrainingCandidateMLP,
    canonical_training_candidate_model_sha256,
)
from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
)

PARTY_DEVELOPMENT_OUTCOME_MODEL_ID = (
    "pokemon.core.party-development.outcome-ranker.mlp.v2"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")


class PartyDevelopmentOutcomeLearningError(ValueError):
    """Raised when outcome fitting crosses a feature or partition boundary."""


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeModel:
    """Permutation-equivariant MLP over completion-aware candidate rows."""

    weights1: NDArray[np.float64]
    bias1: NDArray[np.float64]
    weights2: NDArray[np.float64]
    feature_mean: NDArray[np.float64]
    feature_scale: NDArray[np.float64]
    training_seed: int
    teacher_prior_sha256: str
    outcome_training_examples: int = 0
    outcome_training_root_lineage_ids: tuple[str, ...] = ()
    outcome_training_state_sha256: tuple[str, ...] = ()
    model_id: str = PARTY_DEVELOPMENT_OUTCOME_MODEL_ID
    feature_schema_id: str = PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        width = len(PARTY_DEVELOPMENT_FEATURE_NAMES)
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
        if self.model_id != PARTY_DEVELOPMENT_OUTCOME_MODEL_ID:
            raise PartyDevelopmentOutcomeLearningError(
                "party-development model identity is unsupported"
            )
        if self.feature_schema_id != PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID:
            raise PartyDevelopmentOutcomeLearningError(
                "party-development model feature schema is unsupported"
            )
        if (
            weights1.ndim != 2
            or weights1.shape[0] != width
            or bias1.shape != (weights1.shape[1],)
            or weights2.shape != (weights1.shape[1],)
            or mean.shape != (width,)
            or scale.shape != (width,)
            or weights1.shape[1] < 1
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development model parameter shapes are invalid"
            )
        if not all(np.all(np.isfinite(value)) for value in arrays) or np.any(scale <= 0):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development model parameters are not finite"
            )
        if type(self.training_seed) is not int or self.training_seed < 0:  # noqa: E721
            raise PartyDevelopmentOutcomeLearningError(
                "party-development training seed is invalid"
            )
        if (
            type(self.outcome_training_examples) is not int  # noqa: E721
            or self.outcome_training_examples < 0
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome example count is invalid"
            )
        if (
            not isinstance(self.outcome_training_root_lineage_ids, tuple)
            or len(self.outcome_training_root_lineage_ids)
            != self.outcome_training_examples
            or len(set(self.outcome_training_root_lineage_ids))
            != self.outcome_training_examples
            or any(
                not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None
                for value in self.outcome_training_root_lineage_ids
            )
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome training roots are invalid"
            )
        if (
            not isinstance(self.outcome_training_state_sha256, tuple)
            or len(self.outcome_training_state_sha256)
            != self.outcome_training_examples
            or len(set(self.outcome_training_state_sha256))
            != self.outcome_training_examples
            or any(
                not isinstance(value, str) or _SHA256.fullmatch(value) is None
                for value in self.outcome_training_state_sha256
            )
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome training states are invalid"
            )
        if not isinstance(self.teacher_prior_sha256, str) or _SHA256.fullmatch(
            self.teacher_prior_sha256
        ) is None:
            raise PartyDevelopmentOutcomeLearningError(
                "party-development teacher prior digest is invalid"
            )
        for name, value in zip(
            ("weights1", "bias1", "weights2", "feature_mean", "feature_scale"),
            arrays,
            strict=True,
        ):
            detached = value.copy()
            detached.setflags(write=False)
            object.__setattr__(self, name, detached)

    @property
    def training_target(self) -> str:
        return (
            "teacher_initialization"
            if self.outcome_training_examples == 0
            else "verified_outcome_preference"
        )

    def scores(self, candidates: PartyDevelopmentCandidateSet) -> NDArray[np.float64]:
        if not isinstance(candidates, PartyDevelopmentCandidateSet):
            raise TypeError("candidates must be a PartyDevelopmentCandidateSet")
        features = np.asarray(
            [item.features for item in candidates.candidates], dtype=np.float64
        )
        return self._scores(features)

    def probabilities(
        self, candidates: PartyDevelopmentCandidateSet
    ) -> NDArray[np.float64]:
        scores = self.scores(candidates)
        shifted = scores - np.max(scores)
        probabilities = np.exp(shifted)
        probabilities /= np.sum(probabilities)
        return probabilities

    def predict(self, candidates: PartyDevelopmentCandidateSet) -> int:
        return int(np.argmax(self.probabilities(candidates)))

    def _scores(self, features: NDArray[np.float64]) -> NDArray[np.float64]:
        if features.ndim != 2 or features.shape[1] != len(
            PARTY_DEVELOPMENT_FEATURE_NAMES
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development inference feature shape is invalid"
            )
        normalized = (features - self.feature_mean) / self.feature_scale
        hidden = np.tanh(normalized @ self.weights1 + self.bias1)
        scores = hidden @ self.weights2
        if scores.shape != (features.shape[0],) or not np.all(np.isfinite(scores)):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development candidate scores are invalid"
            )
        return scores

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 2,
            "model_id": self.model_id,
            "feature_schema_id": self.feature_schema_id,
            "feature_names": list(PARTY_DEVELOPMENT_FEATURE_NAMES),
            "hidden_units": int(self.weights1.shape[1]),
            "training_seed": self.training_seed,
            "teacher_prior_sha256": self.teacher_prior_sha256,
            "outcome_training_examples": self.outcome_training_examples,
            "outcome_training_root_lineage_ids": list(
                self.outcome_training_root_lineage_ids
            ),
            "outcome_training_state_sha256": list(
                self.outcome_training_state_sha256
            ),
            "training_target": self.training_target,
            "weights1": self.weights1.tolist(),
            "bias1": self.bias1.tolist(),
            "weights2": self.weights2.tolist(),
            "feature_mean": self.feature_mean.tolist(),
            "feature_scale": self.feature_scale.tolist(),
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, object]
    ) -> PartyDevelopmentOutcomeModel:
        names = value.get("feature_names")
        seed = value.get("training_seed")
        example_count = value.get("outcome_training_examples")
        roots = value.get("outcome_training_root_lineage_ids")
        states = value.get("outcome_training_state_sha256")
        prior_sha256 = value.get("teacher_prior_sha256")
        if (
            value.get("format_version") != 2
            or value.get("model_id") != PARTY_DEVELOPMENT_OUTCOME_MODEL_ID
            or value.get("feature_schema_id") != PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID
            or not isinstance(names, list)
            or tuple(names) != PARTY_DEVELOPMENT_FEATURE_NAMES
            or type(seed) is not int  # noqa: E721
            or type(example_count) is not int  # noqa: E721
            or not isinstance(prior_sha256, str)
            or not isinstance(roots, list)
            or not all(isinstance(item, str) for item in roots)
            or not isinstance(states, list)
            or not all(isinstance(item, str) for item in states)
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development model record is incompatible"
            )
        try:
            model = cls(
                weights1=np.asarray(value["weights1"], dtype=np.float64),
                bias1=np.asarray(value["bias1"], dtype=np.float64),
                weights2=np.asarray(value["weights2"], dtype=np.float64),
                feature_mean=np.asarray(value["feature_mean"], dtype=np.float64),
                feature_scale=np.asarray(value["feature_scale"], dtype=np.float64),
                training_seed=seed,
                teacher_prior_sha256=prior_sha256,
                outcome_training_examples=example_count,
                outcome_training_root_lineage_ids=tuple(roots),
                outcome_training_state_sha256=tuple(states),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise PartyDevelopmentOutcomeLearningError(
                "party-development model record is invalid"
            ) from error
        if value.get("training_target") != model.training_target:
            raise PartyDevelopmentOutcomeLearningError(
                "party-development model training target is inconsistent"
            )
        return model


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeUpdateReport:
    base_model_sha256: str
    updated_model_sha256: str
    training_example_count: int
    training_root_lineage_ids: tuple[str, ...]
    training_state_sha256: tuple[str, ...]
    tied_target_examples: int
    loss_before: float
    loss_after: float
    epochs: int
    learning_rate: float
    prior_l2: float

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.party-development-outcome-update.v2",
            "base_model_sha256": self.base_model_sha256,
            "updated_model_sha256": self.updated_model_sha256,
            "training_example_count": self.training_example_count,
            "training_root_lineage_ids": list(self.training_root_lineage_ids),
            "training_state_sha256": list(self.training_state_sha256),
            "tied_target_examples": self.tied_target_examples,
            "loss_before": self.loss_before,
            "loss_after": self.loss_after,
            "epochs": self.epochs,
            "learning_rate": self.learning_rate,
            "prior_l2": self.prior_l2,
            "teacher_choice_targets": 0,
            "authority_promoted": False,
        }


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeUpdate:
    model: PartyDevelopmentOutcomeModel
    report: PartyDevelopmentOutcomeUpdateReport


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeEvaluation:
    model_sha256: str
    example_count: int
    correct_preferences: int
    cross_entropy: float
    uniform_cross_entropy: float
    mean_winner_probability: float
    root_lineage_ids: tuple[str, ...]
    state_sha256: tuple[str, ...]

    @property
    def accuracy(self) -> float:
        return self.correct_preferences / self.example_count

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.party-development-outcome-evaluation.v2",
            "partition": ScenarioPartition.DEVELOPMENT.value,
            "model_sha256": self.model_sha256,
            "example_count": self.example_count,
            "correct_preferences": self.correct_preferences,
            "accuracy": self.accuracy,
            "cross_entropy": self.cross_entropy,
            "uniform_cross_entropy": self.uniform_cross_entropy,
            "mean_winner_probability": self.mean_winner_probability,
            "root_lineage_ids": list(self.root_lineage_ids),
            "state_sha256": list(self.state_sha256),
            "teacher_choice_targets": 0,
            "authority_promoted": False,
        }


@dataclass(frozen=True, slots=True)
class PartyDevelopmentPairedEvaluation:
    """Same-example comparison between the teacher prior and outcome update."""

    base_model_sha256: str
    updated_model_sha256: str
    example_count: int
    updated_wins: int
    base_wins: int
    correctness_ties: int
    winner_probability_improvements: int
    winner_probability_regressions: int
    winner_probability_ties: int
    mean_winner_probability_delta: float
    root_lineage_ids: tuple[str, ...]

    @property
    def discordant_correctness_pairs(self) -> int:
        return self.updated_wins + self.base_wins

    @property
    def paired_two_sided_exact_p(self) -> float:
        count = self.discordant_correctness_pairs
        if count == 0:
            return 1.0
        tail = min(self.updated_wins, self.base_wins)
        probability = sum(math.comb(count, value) for value in range(tail + 1)) / (
            2**count
        )
        return min(1.0, 2.0 * probability)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.party-development-outcome-paired-evaluation.v2",
            "partition": ScenarioPartition.DEVELOPMENT.value,
            "base_model_sha256": self.base_model_sha256,
            "updated_model_sha256": self.updated_model_sha256,
            "example_count": self.example_count,
            "correctness": {
                "updated_wins": self.updated_wins,
                "base_wins": self.base_wins,
                "ties": self.correctness_ties,
                "discordant_pairs": self.discordant_correctness_pairs,
                "two_sided_exact_p": self.paired_two_sided_exact_p,
            },
            "winner_probability": {
                "improvements": self.winner_probability_improvements,
                "regressions": self.winner_probability_regressions,
                "ties": self.winner_probability_ties,
                "mean_delta": self.mean_winner_probability_delta,
            },
            "root_lineage_ids": list(self.root_lineage_ids),
            "inferential_claim": False,
            "authority_promoted": False,
        }


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeLearningCycle:
    update: PartyDevelopmentOutcomeUpdate
    base_development: PartyDevelopmentOutcomeEvaluation
    updated_development: PartyDevelopmentOutcomeEvaluation
    paired_development: PartyDevelopmentPairedEvaluation

    def __post_init__(self) -> None:
        if not isinstance(self.update, PartyDevelopmentOutcomeUpdate):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development learning-cycle update is invalid"
            )
        if (
            self.base_development.model_sha256
            != self.update.report.base_model_sha256
            or self.updated_development.model_sha256
            != self.update.report.updated_model_sha256
            or self.paired_development.base_model_sha256
            != self.update.report.base_model_sha256
            or self.paired_development.updated_model_sha256
            != self.update.report.updated_model_sha256
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development learning-cycle model binding is invalid"
            )
        if (
            self.base_development.example_count
            != self.updated_development.example_count
            or self.base_development.example_count
            != self.paired_development.example_count
            or self.base_development.root_lineage_ids
            != self.updated_development.root_lineage_ids
            or self.base_development.root_lineage_ids
            != self.paired_development.root_lineage_ids
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development learning-cycle development binding is invalid"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.party-development-outcome-learning-cycle.v2",
            "update": self.update.report.public_dict(),
            "base_development": self.base_development.public_dict(),
            "updated_development": self.updated_development.public_dict(),
            "paired_development": self.paired_development.public_dict(),
            "descriptive_initial_curve": True,
            "inferential_claim": False,
            "sealed_test_cases_opened": 0,
            "teacher_choice_targets": 0,
            "authority_promoted": False,
        }


def initialize_from_teacher_model(
    teacher: TrainingCandidateMLP,
) -> PartyDevelopmentOutcomeModel:
    """Embed the v1 teacher scorer exactly and zero-initialize every v2 input."""

    if not isinstance(teacher, TrainingCandidateMLP):
        raise TypeError("teacher must be a TrainingCandidateMLP")
    if PARTY_DEVELOPMENT_FEATURE_NAMES[: len(TRAINING_CANDIDATE_FEATURE_NAMES)] != (
        TRAINING_CANDIDATE_FEATURE_NAMES
    ):
        raise PartyDevelopmentOutcomeLearningError(
            "party-development v2 no longer preserves the v1 feature prefix"
        )
    width = len(PARTY_DEVELOPMENT_FEATURE_NAMES)
    hidden = teacher.weights1.shape[1]
    weights1 = np.zeros((width, hidden), dtype=np.float64)
    weights1[: len(TRAINING_CANDIDATE_FEATURE_NAMES)] = teacher.weights1
    mean = np.zeros(width, dtype=np.float64)
    scale = np.ones(width, dtype=np.float64)
    mean[: len(TRAINING_CANDIDATE_FEATURE_NAMES)] = teacher.feature_mean
    scale[: len(TRAINING_CANDIDATE_FEATURE_NAMES)] = teacher.feature_scale
    return PartyDevelopmentOutcomeModel(
        weights1=weights1,
        bias1=teacher.bias1,
        weights2=teacher.weights2,
        feature_mean=mean,
        feature_scale=scale,
        training_seed=teacher.training_seed,
        teacher_prior_sha256=canonical_training_candidate_model_sha256(teacher),
    )


def adapt_party_development_model_from_outcomes(
    base_model: PartyDevelopmentOutcomeModel,
    examples: Iterable[ScenarioOutcomeExample],
    *,
    epochs: int = 200,
    learning_rate: float = 0.01,
    prior_l2: float = 0.1,
) -> PartyDevelopmentOutcomeUpdate:
    """Fit all scorer weights to train-only soft preferences with a prior anchor."""

    choices = tuple(examples)
    _require_examples(choices, partition=ScenarioPartition.TRAIN)
    choice_roots = {item.root_lineage_id for item in choices}
    choice_states = {item.initial_state_sha256 for item in choices}
    if choice_roots & set(base_model.outcome_training_root_lineage_ids):
        raise PartyDevelopmentOutcomeLearningError(
            "party-development outcome training root was already consumed"
        )
    if choice_states & set(base_model.outcome_training_state_sha256):
        raise PartyDevelopmentOutcomeLearningError(
            "party-development outcome training state was already consumed"
        )
    if not any(item.learner_update_eligible for item in choices):
        raise PartyDevelopmentOutcomeLearningError(
            "party-development outcomes contain no preference signal"
        )
    _require_hyperparameters(epochs, learning_rate, prior_l2)
    prior_weights1 = base_model.weights1.copy()
    prior_bias1 = base_model.bias1.copy()
    prior_weights2 = base_model.weights2.copy()
    weights1 = prior_weights1.copy()
    bias1 = prior_bias1.copy()
    weights2 = prior_weights2.copy()
    parameters = (weights1, bias1, weights2)
    priors = (prior_weights1, prior_bias1, prior_weights2)
    first = [np.zeros_like(value) for value in parameters]
    second = [np.zeros_like(value) for value in parameters]
    loss_before = _outcome_loss(base_model, choices)

    for step in range(1, epochs + 1):
        gradients = [np.zeros_like(value) for value in parameters]
        for example in choices:
            features = _example_features(example)
            normalized = (features - base_model.feature_mean) / base_model.feature_scale
            hidden = np.tanh(normalized @ weights1 + bias1)
            probabilities = _masked_probabilities(hidden @ weights2, example)
            delta = probabilities - example.target_distribution
            gradients[2] += hidden.T @ delta
            hidden_delta = delta[:, None] * weights2[None, :]
            hidden_delta *= 1.0 - hidden * hidden
            gradients[0] += normalized.T @ hidden_delta
            gradients[1] += np.sum(hidden_delta, axis=0)
        for index in range(len(gradients)):
            gradients[index] /= len(choices)
            gradients[index] += prior_l2 * (parameters[index] - priors[index])
            first[index] = 0.9 * first[index] + 0.1 * gradients[index]
            second[index] = 0.999 * second[index] + 0.001 * gradients[index] ** 2
            corrected_first = first[index] / (1.0 - 0.9**step)
            corrected_second = second[index] / (1.0 - 0.999**step)
            parameters[index][...] -= learning_rate * corrected_first / (
                np.sqrt(corrected_second) + 1e-8
            )

    updated = PartyDevelopmentOutcomeModel(
        weights1=weights1,
        bias1=bias1,
        weights2=weights2,
        feature_mean=base_model.feature_mean,
        feature_scale=base_model.feature_scale,
        training_seed=base_model.training_seed,
        teacher_prior_sha256=base_model.teacher_prior_sha256,
        outcome_training_examples=base_model.outcome_training_examples + len(choices),
        outcome_training_root_lineage_ids=tuple(
            sorted((*base_model.outcome_training_root_lineage_ids, *choice_roots))
        ),
        outcome_training_state_sha256=tuple(
            sorted((*base_model.outcome_training_state_sha256, *choice_states))
        ),
    )
    loss_after = _outcome_loss(updated, choices)
    if not loss_after < loss_before:
        raise PartyDevelopmentOutcomeLearningError(
            "bounded party-development update did not reduce training loss"
        )
    base_sha256 = canonical_party_development_outcome_model_sha256(base_model)
    updated_sha256 = canonical_party_development_outcome_model_sha256(updated)
    if updated_sha256 == base_sha256:
        raise PartyDevelopmentOutcomeLearningError(
            "bounded party-development update did not change the model"
        )
    return PartyDevelopmentOutcomeUpdate(
        model=updated,
        report=PartyDevelopmentOutcomeUpdateReport(
            base_model_sha256=base_sha256,
            updated_model_sha256=updated_sha256,
            training_example_count=len(choices),
            training_root_lineage_ids=tuple(
                sorted(item.root_lineage_id for item in choices)
            ),
            training_state_sha256=tuple(
                sorted(item.initial_state_sha256 for item in choices)
            ),
            tied_target_examples=sum(len(item.best_candidate_indices) > 1 for item in choices),
            loss_before=loss_before,
            loss_after=loss_after,
            epochs=epochs,
            learning_rate=float(learning_rate),
            prior_l2=float(prior_l2),
        ),
    )


def evaluate_party_development_outcomes(
    model: PartyDevelopmentOutcomeModel,
    examples: Iterable[ScenarioOutcomeExample],
) -> PartyDevelopmentOutcomeEvaluation:
    """Evaluate without fitting on untouched development roots."""

    choices = tuple(examples)
    _require_examples(choices, partition=ScenarioPartition.DEVELOPMENT)
    model_sha256 = canonical_party_development_outcome_model_sha256(model)
    correct = 0
    losses: list[float] = []
    uniform_losses: list[float] = []
    winner_probabilities: list[float] = []
    for example in choices:
        probabilities = _example_probabilities(model, example)
        selected = int(np.argmax(probabilities))
        correct += int(selected in example.best_candidate_indices)
        target = example.target_distribution
        positive = target > 0
        losses.append(float(-np.sum(target[positive] * np.log(probabilities[positive]))))
        available_count = len(example.available_candidate_indices)
        uniform_losses.append(math.log(available_count))
        winner_probabilities.append(float(np.sum(probabilities[list(example.best_candidate_indices)])))
    if canonical_party_development_outcome_model_sha256(model) != model_sha256:
        raise PartyDevelopmentOutcomeLearningError(
            "party-development evaluation mutated the model"
        )
    return PartyDevelopmentOutcomeEvaluation(
        model_sha256=model_sha256,
        example_count=len(choices),
        correct_preferences=correct,
        cross_entropy=float(np.mean(losses)),
        uniform_cross_entropy=float(np.mean(uniform_losses)),
        mean_winner_probability=float(np.mean(winner_probabilities)),
        root_lineage_ids=tuple(sorted(item.root_lineage_id for item in choices)),
        state_sha256=tuple(sorted(item.initial_state_sha256 for item in choices)),
    )


def compare_party_development_outcomes(
    base_model: PartyDevelopmentOutcomeModel,
    updated_model: PartyDevelopmentOutcomeModel,
    examples: Iterable[ScenarioOutcomeExample],
) -> PartyDevelopmentPairedEvaluation:
    """Compare both models on each identical development decision."""

    choices = tuple(examples)
    _require_examples(choices, partition=ScenarioPartition.DEVELOPMENT)
    base_sha256 = canonical_party_development_outcome_model_sha256(base_model)
    updated_sha256 = canonical_party_development_outcome_model_sha256(updated_model)
    updated_wins = 0
    base_wins = 0
    correctness_ties = 0
    probability_improvements = 0
    probability_regressions = 0
    probability_ties = 0
    probability_deltas: list[float] = []
    for item in choices:
        base_probabilities = _example_probabilities(base_model, item)
        updated_probabilities = _example_probabilities(updated_model, item)
        winners = item.best_candidate_indices
        base_correct = int(np.argmax(base_probabilities)) in winners
        updated_correct = int(np.argmax(updated_probabilities)) in winners
        if updated_correct and not base_correct:
            updated_wins += 1
        elif base_correct and not updated_correct:
            base_wins += 1
        else:
            correctness_ties += 1
        base_winner_probability = float(np.sum(base_probabilities[list(winners)]))
        updated_winner_probability = float(np.sum(updated_probabilities[list(winners)]))
        delta = updated_winner_probability - base_winner_probability
        probability_deltas.append(delta)
        if delta > 1e-12:
            probability_improvements += 1
        elif delta < -1e-12:
            probability_regressions += 1
        else:
            probability_ties += 1
    if (
        canonical_party_development_outcome_model_sha256(base_model) != base_sha256
        or canonical_party_development_outcome_model_sha256(updated_model)
        != updated_sha256
    ):
        raise PartyDevelopmentOutcomeLearningError(
            "paired party-development evaluation mutated a model"
        )
    return PartyDevelopmentPairedEvaluation(
        base_model_sha256=base_sha256,
        updated_model_sha256=updated_sha256,
        example_count=len(choices),
        updated_wins=updated_wins,
        base_wins=base_wins,
        correctness_ties=correctness_ties,
        winner_probability_improvements=probability_improvements,
        winner_probability_regressions=probability_regressions,
        winner_probability_ties=probability_ties,
        mean_winner_probability_delta=float(np.mean(probability_deltas)),
        root_lineage_ids=tuple(sorted(item.root_lineage_id for item in choices)),
    )


def run_party_development_outcome_learning_cycle(
    base_model: PartyDevelopmentOutcomeModel,
    *,
    training_examples: Iterable[ScenarioOutcomeExample],
    development_examples: Iterable[ScenarioOutcomeExample],
    epochs: int = 200,
    learning_rate: float = 0.01,
    prior_l2: float = 0.1,
) -> PartyDevelopmentOutcomeLearningCycle:
    """Update on train roots and compare both models on the same untouched roots."""

    training = tuple(training_examples)
    development = tuple(development_examples)
    _require_examples(training, partition=ScenarioPartition.TRAIN)
    _require_examples(development, partition=ScenarioPartition.DEVELOPMENT)
    if {item.root_lineage_id for item in training} & {
        item.root_lineage_id for item in development
    }:
        raise PartyDevelopmentOutcomeLearningError(
            "party-development root lineage crosses train and development"
        )
    if {item.initial_state_sha256 for item in training} & {
        item.initial_state_sha256 for item in development
    }:
        raise PartyDevelopmentOutcomeLearningError(
            "party-development state crosses train and development"
        )
    update = adapt_party_development_model_from_outcomes(
        base_model,
        training,
        epochs=epochs,
        learning_rate=learning_rate,
        prior_l2=prior_l2,
    )
    return PartyDevelopmentOutcomeLearningCycle(
        update=update,
        base_development=evaluate_party_development_outcomes(base_model, development),
        updated_development=evaluate_party_development_outcomes(
            update.model, development
        ),
        paired_development=compare_party_development_outcomes(
            base_model, update.model, development
        ),
    )


def canonical_party_development_outcome_model_sha256(
    model: PartyDevelopmentOutcomeModel,
) -> str:
    payload = json.dumps(
        model.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def load_party_development_outcome_model(
    path: str | Path,
    *,
    expected_sha256: str,
) -> PartyDevelopmentOutcomeModel:
    """Authenticate and decode one v2 model without following links."""

    if _SHA256.fullmatch(expected_sha256) is None:
        raise PartyDevelopmentOutcomeLearningError("expected v2 model digest is invalid")
    source = Path(path)
    try:
        metadata = source.lstat()
        payload = source.read_bytes()
    except OSError as error:
        raise PartyDevelopmentOutcomeLearningError("v2 model cannot be read") from error
    if source.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise PartyDevelopmentOutcomeLearningError("v2 model must be a regular file")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise PartyDevelopmentOutcomeLearningError("v2 model failed authentication")
    try:
        raw = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PartyDevelopmentOutcomeLearningError("v2 model is invalid JSON") from error
    if not isinstance(raw, Mapping):
        raise PartyDevelopmentOutcomeLearningError("v2 model must be an object")
    return PartyDevelopmentOutcomeModel.from_dict(raw)


def _require_examples(
    choices: tuple[ScenarioOutcomeExample, ...],
    *,
    partition: ScenarioPartition,
) -> None:
    if not choices:
        raise PartyDevelopmentOutcomeLearningError(
            "party-development outcome learning requires examples"
        )
    for item in choices:
        if not isinstance(item, ScenarioOutcomeExample):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome example is invalid"
            )
        if item.family is not ScenarioFamily.PARTY_DEVELOPMENT:
            raise PartyDevelopmentOutcomeLearningError(
                "outcome example belongs to a different family"
            )
        if item.partition is not partition:
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome partition is invalid"
            )
        if (
            item.feature_schema_id != PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID
            or item.feature_names != PARTY_DEVELOPMENT_FEATURE_NAMES
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome feature schema is incompatible"
            )
        if not item.fully_measured:
            raise PartyDevelopmentOutcomeLearningError(
                "censored party-development evidence cannot become a target"
            )
    for attribute, subject in (
        ("scenario_id", "scenario identity"),
        ("root_lineage_id", "root lineage"),
        ("initial_state_sha256", "initial state"),
    ):
        values = tuple(getattr(item, attribute) for item in choices)
        if len(values) != len(set(values)):
            raise PartyDevelopmentOutcomeLearningError(
                f"party-development {subject} repeats inside a partition"
            )


def _require_hyperparameters(
    epochs: int,
    learning_rate: float,
    prior_l2: float,
) -> None:
    if type(epochs) is not int or epochs < 1:  # noqa: E721
        raise PartyDevelopmentOutcomeLearningError("v2 epoch count is invalid")
    for value, name, strictly_positive in (
        (learning_rate, "learning rate", True),
        (prior_l2, "prior l2", False),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or (value <= 0 if strictly_positive else value < 0)
        ):
            raise PartyDevelopmentOutcomeLearningError(f"v2 {name} is invalid")


def _example_features(example: ScenarioOutcomeExample) -> NDArray[np.float64]:
    return np.asarray([item.features for item in example.candidates], dtype=np.float64)


def _example_probabilities(
    model: PartyDevelopmentOutcomeModel,
    example: ScenarioOutcomeExample,
) -> NDArray[np.float64]:
    return _masked_probabilities(model._scores(_example_features(example)), example)


def _masked_probabilities(
    scores: NDArray[np.float64],
    example: ScenarioOutcomeExample,
) -> NDArray[np.float64]:
    available = np.zeros(len(example.candidates), dtype=np.bool_)
    available[list(example.available_candidate_indices)] = True
    probabilities = np.zeros(len(example.candidates), dtype=np.float64)
    shifted = scores[available] - np.max(scores[available])
    exponentials = np.exp(shifted)
    probabilities[available] = exponentials / np.sum(exponentials)
    return probabilities


def _outcome_loss(
    model: PartyDevelopmentOutcomeModel,
    choices: tuple[ScenarioOutcomeExample, ...],
) -> float:
    losses = []
    for item in choices:
        probabilities = _example_probabilities(model, item)
        target = item.target_distribution
        positive = target > 0
        losses.append(float(-np.sum(target[positive] * np.log(probabilities[positive]))))
    return float(np.mean(losses))


__all__ = [
    "PARTY_DEVELOPMENT_OUTCOME_MODEL_ID",
    "PartyDevelopmentOutcomeEvaluation",
    "PartyDevelopmentOutcomeLearningCycle",
    "PartyDevelopmentOutcomeLearningError",
    "PartyDevelopmentOutcomeModel",
    "PartyDevelopmentPairedEvaluation",
    "PartyDevelopmentOutcomeUpdate",
    "PartyDevelopmentOutcomeUpdateReport",
    "adapt_party_development_model_from_outcomes",
    "canonical_party_development_outcome_model_sha256",
    "compare_party_development_outcomes",
    "evaluate_party_development_outcomes",
    "initialize_from_teacher_model",
    "load_party_development_outcome_model",
    "run_party_development_outcome_learning_cycle",
]
