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
from typing import cast

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.party_development_rank import (
    PARTY_DEVELOPMENT_FEATURE_NAMES,
    PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    PARTY_DEVELOPMENT_WORKLOAD_FEATURE_NAMES,
    PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID,
    PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID,
    PARTY_DEVELOPMENT_MATCHUP_FEATURE_NAMES,
    VENUE_MATCHUP_FEATURE_NAMES,
    PartyDevelopmentCandidateSet,
    party_development_feature_names,
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

PARTY_DEVELOPMENT_OUTCOME_MODEL_ID = "pokemon.core.party-development.outcome-ranker.mlp.v2"
PARTY_DEVELOPMENT_WORKLOAD_MODEL_ID = "pokemon.core.party-development.outcome-ranker.mlp.v3"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")


class PartyDevelopmentOutcomeLearningError(ValueError):
    """Raised when outcome fitting crosses a feature or partition boundary."""


@dataclass(frozen=True, slots=True)
class PartyDevelopmentTeacherPrior:
    """Authenticated v1 model and every root already consumed to establish it."""

    model_file_sha256: str
    model_canonical_sha256: str
    offline_evidence_sha256: str
    training_root_lineage_ids: tuple[str, ...]
    training_state_sha256: tuple[str, ...]
    evaluation_root_lineage_ids: tuple[str, ...]
    evaluation_state_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, subject in (
            (self.model_file_sha256, "teacher-prior model file"),
            (self.model_canonical_sha256, "teacher-prior canonical model"),
            (self.offline_evidence_sha256, "teacher-prior offline evidence"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise PartyDevelopmentOutcomeLearningError(f"{subject} digest is invalid")
        self._require_partition(
            self.training_root_lineage_ids,
            self.training_state_sha256,
            subject="training",
        )
        self._require_partition(
            self.evaluation_root_lineage_ids,
            self.evaluation_state_sha256,
            subject="evaluation",
        )
        if set(self.training_root_lineage_ids) & set(self.evaluation_root_lineage_ids):
            raise PartyDevelopmentOutcomeLearningError(
                "teacher-prior root crosses training and evaluation"
            )
        if set(self.training_state_sha256) & set(self.evaluation_state_sha256):
            raise PartyDevelopmentOutcomeLearningError(
                "teacher-prior state crosses training and evaluation"
            )

    @staticmethod
    def _require_partition(
        roots: tuple[str, ...],
        states: tuple[str, ...],
        *,
        subject: str,
    ) -> None:
        if (
            not isinstance(roots, tuple)
            or not roots
            or len(roots) != len(states)
            or len(set(roots)) != len(roots)
            or any(
                not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None for value in roots
            )
            or not isinstance(states, tuple)
            or len(set(states)) != len(states)
            or any(
                not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in states
            )
        ):
            raise PartyDevelopmentOutcomeLearningError(f"teacher-prior {subject} roots are invalid")
        if tuple(zip(roots, states, strict=True)) != tuple(sorted(zip(roots, states, strict=True))):
            raise PartyDevelopmentOutcomeLearningError(
                f"teacher-prior {subject} roots are not in canonical order"
            )

    @property
    def consumed_root_lineage_ids(self) -> frozenset[str]:
        return frozenset((*self.training_root_lineage_ids, *self.evaluation_root_lineage_ids))

    @property
    def consumed_state_sha256(self) -> frozenset[str]:
        return frozenset((*self.training_state_sha256, *self.evaluation_state_sha256))

    def to_dict(self) -> dict[str, object]:
        return {
            "model_file_sha256": self.model_file_sha256,
            "model_canonical_sha256": self.model_canonical_sha256,
            "offline_evidence_sha256": self.offline_evidence_sha256,
            "training_root_lineage_ids": list(self.training_root_lineage_ids),
            "training_state_sha256": list(self.training_state_sha256),
            "evaluation_root_lineage_ids": list(self.evaluation_root_lineage_ids),
            "evaluation_state_sha256": list(self.evaluation_state_sha256),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> PartyDevelopmentTeacherPrior:
        expected = {
            "model_file_sha256",
            "model_canonical_sha256",
            "offline_evidence_sha256",
            "training_root_lineage_ids",
            "training_state_sha256",
            "evaluation_root_lineage_ids",
            "evaluation_state_sha256",
        }
        if set(value) != expected:
            raise PartyDevelopmentOutcomeLearningError("teacher-prior record is incompatible")
        training_roots = value["training_root_lineage_ids"]
        training_states = value["training_state_sha256"]
        evaluation_roots = value["evaluation_root_lineage_ids"]
        evaluation_states = value["evaluation_state_sha256"]
        sequences = (
            training_roots,
            training_states,
            evaluation_roots,
            evaluation_states,
        )
        if any(
            not isinstance(items, list) or not all(isinstance(item, str) for item in items)
            for items in sequences
        ):
            raise PartyDevelopmentOutcomeLearningError("teacher-prior lineage record is invalid")
        file_sha, canonical_sha, evidence_sha = (
            value["model_file_sha256"],
            value["model_canonical_sha256"],
            value["offline_evidence_sha256"],
        )
        if not all(isinstance(item, str) for item in (file_sha, canonical_sha, evidence_sha)):
            raise PartyDevelopmentOutcomeLearningError("teacher-prior digest record is invalid")
        return cls(
            model_file_sha256=cast(str, file_sha),
            model_canonical_sha256=cast(str, canonical_sha),
            offline_evidence_sha256=cast(str, evidence_sha),
            training_root_lineage_ids=tuple(cast(list[str], training_roots)),
            training_state_sha256=tuple(cast(list[str], training_states)),
            evaluation_root_lineage_ids=tuple(cast(list[str], evaluation_roots)),
            evaluation_state_sha256=tuple(cast(list[str], evaluation_states)),
        )


@dataclass(frozen=True, slots=True)
class PartyDevelopmentOutcomeModel:
    """Permutation-equivariant MLP over completion-aware candidate rows."""

    weights1: NDArray[np.float64]
    bias1: NDArray[np.float64]
    weights2: NDArray[np.float64]
    feature_mean: NDArray[np.float64]
    feature_scale: NDArray[np.float64]
    training_seed: int
    teacher_prior: PartyDevelopmentTeacherPrior
    outcome_training_examples: int = 0
    outcome_training_root_lineage_ids: tuple[str, ...] = ()
    outcome_training_state_sha256: tuple[str, ...] = ()
    model_id: str = PARTY_DEVELOPMENT_OUTCOME_MODEL_ID
    feature_schema_id: str = PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        try:
            width = len(party_development_feature_names(self.feature_schema_id))
        except ValueError as error:
            raise PartyDevelopmentOutcomeLearningError(
                "model feature schema is unsupported"
            ) from error
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
        expected_id = (
            PARTY_DEVELOPMENT_OUTCOME_MODEL_ID
            if self.feature_schema_id == PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID
            else PARTY_DEVELOPMENT_WORKLOAD_MODEL_ID
        )
        if self.model_id != expected_id:
            raise PartyDevelopmentOutcomeLearningError(
                "party-development model identity is unsupported"
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
            raise PartyDevelopmentOutcomeLearningError("party-development training seed is invalid")
        if (
            type(self.outcome_training_examples) is not int  # noqa: E721
            or self.outcome_training_examples < 0
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome example count is invalid"
            )
        if (
            not isinstance(self.outcome_training_root_lineage_ids, tuple)
            or len(self.outcome_training_root_lineage_ids) != self.outcome_training_examples
            or len(set(self.outcome_training_root_lineage_ids)) != self.outcome_training_examples
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
            or len(self.outcome_training_state_sha256) != self.outcome_training_examples
            or len(set(self.outcome_training_state_sha256)) != self.outcome_training_examples
            or any(
                not isinstance(value, str) or _SHA256.fullmatch(value) is None
                for value in self.outcome_training_state_sha256
            )
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome training states are invalid"
            )
        if not isinstance(self.teacher_prior, PartyDevelopmentTeacherPrior):
            raise PartyDevelopmentOutcomeLearningError("party-development teacher prior is invalid")
        if set(self.outcome_training_root_lineage_ids) & (
            self.teacher_prior.consumed_root_lineage_ids
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome roots overlap teacher-prior evidence"
            )
        if set(self.outcome_training_state_sha256) & (self.teacher_prior.consumed_state_sha256):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome states overlap teacher-prior evidence"
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
    def feature_names(self) -> tuple[str, ...]:
        return party_development_feature_names(self.feature_schema_id)

    @property
    def training_target(self) -> str:
        return (
            "teacher_initialization"
            if self.outcome_training_examples == 0
            else "verified_outcome_preference"
        )

    @property
    def teacher_prior_sha256(self) -> str:
        """Canonical v1 model identity retained for concise public reporting."""

        return self.teacher_prior.model_canonical_sha256

    def scores(self, candidates: PartyDevelopmentCandidateSet) -> NDArray[np.float64]:
        if not isinstance(candidates, PartyDevelopmentCandidateSet):
            raise TypeError("candidates must be a PartyDevelopmentCandidateSet")
        features = np.asarray([item.features for item in candidates.candidates], dtype=np.float64)
        return self._scores(_aligned_features(features, candidates.feature_schema_id, self.feature_schema_id))

    def probabilities(self, candidates: PartyDevelopmentCandidateSet) -> NDArray[np.float64]:
        scores = self.scores(candidates)
        shifted = scores - np.max(scores)
        probabilities = np.exp(shifted)
        probabilities /= np.sum(probabilities)
        return probabilities

    def predict(self, candidates: PartyDevelopmentCandidateSet) -> int:
        return int(np.argmax(self.probabilities(candidates)))

    def _scores(self, features: NDArray[np.float64]) -> NDArray[np.float64]:
        if features.ndim != 2 or features.shape[1] != len(self.feature_names):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development inference feature shape is invalid"
            )
        normalized = (features - self.feature_mean) / self.feature_scale
        hidden = _hidden_activations(normalized, self.weights1, self.bias1, self.feature_schema_id)
        scores = hidden @ self.weights2
        if scores.shape != (features.shape[0],) or not np.all(np.isfinite(scores)):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development candidate scores are invalid"
            )
        return scores

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": (
                3 if self.feature_schema_id == PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID else 4
            ),
            "model_id": self.model_id,
            "feature_schema_id": self.feature_schema_id,
            "feature_names": list(self.feature_names),
            "hidden_units": int(self.weights1.shape[1]),
            "training_seed": self.training_seed,
            "teacher_prior": self.teacher_prior.to_dict(),
            "outcome_training_examples": self.outcome_training_examples,
            "outcome_training_root_lineage_ids": list(self.outcome_training_root_lineage_ids),
            "outcome_training_state_sha256": list(self.outcome_training_state_sha256),
            "training_target": self.training_target,
            "weights1": self.weights1.tolist(),
            "bias1": self.bias1.tolist(),
            "weights2": self.weights2.tolist(),
            "feature_mean": self.feature_mean.tolist(),
            "feature_scale": self.feature_scale.tolist(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> PartyDevelopmentOutcomeModel:
        names = value.get("feature_names")
        seed = value.get("training_seed")
        example_count = value.get("outcome_training_examples")
        roots = value.get("outcome_training_root_lineage_ids")
        states = value.get("outcome_training_state_sha256")
        prior_value = value.get("teacher_prior")
        schema_id = value.get("feature_schema_id")
        try:
            if not isinstance(schema_id, str):
                raise ValueError("party-development feature schema must be a string")
            expected_names = party_development_feature_names(schema_id)
        except ValueError as error:
            raise PartyDevelopmentOutcomeLearningError(
                "party-development model record is incompatible"
            ) from error
        legacy = schema_id == PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID
        expected_id = (
            PARTY_DEVELOPMENT_OUTCOME_MODEL_ID if legacy else PARTY_DEVELOPMENT_WORKLOAD_MODEL_ID
        )
        if (
            value.get("format_version") != (3 if legacy else 4)
            or value.get("model_id") != expected_id
            or not isinstance(names, list)
            or tuple(names) != expected_names
            or type(seed) is not int  # noqa: E721
            or type(example_count) is not int  # noqa: E721
            or not isinstance(prior_value, Mapping)
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
                teacher_prior=PartyDevelopmentTeacherPrior.from_dict(prior_value),
                outcome_training_examples=example_count,
                outcome_training_root_lineage_ids=tuple(roots),
                outcome_training_state_sha256=tuple(states),
                model_id=expected_id,
                feature_schema_id=schema_id,
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
    route_geometry_fit: dict[str, object] | None = None
    rehearsal_training: dict[str, object] | None = None
    workload_fit: dict[str, object] | None = None

    def public_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
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

        if self.route_geometry_fit is not None:
            result["schema"] = "pokemon.core.party-development-outcome-update.v3"
            result["route_geometry_fit"] = dict(self.route_geometry_fit)
        if self.rehearsal_training is not None:
            result["schema"] = "pokemon.core.party-development-outcome-update.v4"
            result["rehearsal_training"] = dict(self.rehearsal_training)
        if self.workload_fit is not None:
            result["schema"] = "pokemon.core.party-development-outcome-update.v5"
            result["workload_fit"] = dict(self.workload_fit)
        return result


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
        probability = sum(math.comb(count, value) for value in range(tail + 1)) / (2**count)
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
            self.base_development.model_sha256 != self.update.report.base_model_sha256
            or self.updated_development.model_sha256 != self.update.report.updated_model_sha256
            or self.paired_development.base_model_sha256 != self.update.report.base_model_sha256
            or self.paired_development.updated_model_sha256
            != self.update.report.updated_model_sha256
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "party-development learning-cycle model binding is invalid"
            )
        if (
            self.base_development.example_count != self.updated_development.example_count
            or self.base_development.example_count != self.paired_development.example_count
            or self.base_development.root_lineage_ids != self.updated_development.root_lineage_ids
            or self.base_development.root_lineage_ids != self.paired_development.root_lineage_ids
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
    *,
    teacher_prior: PartyDevelopmentTeacherPrior,
) -> PartyDevelopmentOutcomeModel:
    """Embed the v1 teacher scorer exactly and zero-initialize every v2 input."""

    if not isinstance(teacher, TrainingCandidateMLP):
        raise TypeError("teacher must be a TrainingCandidateMLP")
    if not isinstance(teacher_prior, PartyDevelopmentTeacherPrior):
        raise TypeError("teacher_prior must be a PartyDevelopmentTeacherPrior")
    if canonical_training_candidate_model_sha256(teacher) != teacher_prior.model_canonical_sha256:
        raise PartyDevelopmentOutcomeLearningError(
            "teacher model differs from its authenticated prior provenance"
        )
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
        teacher_prior=teacher_prior,
    )


def upgrade_party_development_model_for_workload(
    model: PartyDevelopmentOutcomeModel,
) -> PartyDevelopmentOutcomeModel:
    """Embed the existing scorer exactly; new observed inputs start at zero weight.

    This is representation compatibility, not a learned improvement. It does not
    read outcomes, call an optimizer, consume a root or activate runtime authority.
    """
    if not isinstance(model, PartyDevelopmentOutcomeModel):
        raise TypeError("model must be a PartyDevelopmentOutcomeModel")
    if model.feature_schema_id in (PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID, PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID):
        return model
    extra = len(PARTY_DEVELOPMENT_WORKLOAD_FEATURE_NAMES) - len(model.feature_names)
    return PartyDevelopmentOutcomeModel(
        weights1=np.vstack((model.weights1, np.zeros((extra, model.weights1.shape[1])))),
        bias1=model.bias1,
        weights2=model.weights2,
        feature_mean=np.concatenate((model.feature_mean, np.zeros(extra))),
        feature_scale=np.concatenate((model.feature_scale, np.ones(extra))),
        training_seed=model.training_seed,
        teacher_prior=model.teacher_prior,
        outcome_training_examples=model.outcome_training_examples,
        outcome_training_root_lineage_ids=model.outcome_training_root_lineage_ids,
        outcome_training_state_sha256=model.outcome_training_state_sha256,
        model_id=PARTY_DEVELOPMENT_WORKLOAD_MODEL_ID,
        feature_schema_id=PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID,
    )


def upgrade_party_development_model_for_matchups(model: PartyDevelopmentOutcomeModel) -> PartyDevelopmentOutcomeModel:
    """Explicitly append zero-influence observed mechanics; no fitting or new ancestry."""
    from dataclasses import replace
    model = upgrade_party_development_model_for_workload(model)
    if model.feature_schema_id == PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID:
        return model
    extra = len(VENUE_MATCHUP_FEATURE_NAMES)
    return replace(model, weights1=np.vstack((model.weights1, np.zeros((extra, model.weights1.shape[1])))),
                   feature_mean=np.concatenate((model.feature_mean, np.zeros(extra))),
                   feature_scale=np.concatenate((model.feature_scale, np.ones(extra))),
                   feature_schema_id=PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID)


def _hidden_activations(normalized, weights, bias, schema_id):
    if schema_id == PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID:
        prefix = len(PARTY_DEVELOPMENT_WORKLOAD_FEATURE_NAMES)
        # Keep the existing scorer's accumulation order when the appended
        # observations have zero influence (including legacy unknown inputs).
        return np.tanh((normalized[:, :prefix] @ weights[:prefix] + bias)
                       + normalized[:, prefix:] @ weights[prefix:])
    return np.tanh(normalized @ weights + bias)


def _aligned_features(features, source_schema, target_schema):
    if source_schema == target_schema:
        return features
    # An old document contains no observations of the new fields. Preserve it
    # verbatim and supply unknown zeros only at this explicit new-model seam.
    if target_schema == PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID and source_schema in (
        PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID, PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID
    ):
        old_names = party_development_feature_names(source_schema)
        if features.ndim != 2 or features.shape[1] != len(old_names):
            raise PartyDevelopmentOutcomeLearningError("legacy feature width differs")
        return np.pad(features, ((0, 0), (0, len(PARTY_DEVELOPMENT_MATCHUP_FEATURE_NAMES) - len(old_names))))
    raise PartyDevelopmentOutcomeLearningError("candidate and model feature schemas differ")


def bind_teacher_prior_from_offline_evidence(
    teacher: TrainingCandidateMLP,
    *,
    model_file_sha256: str,
    evidence_payload: bytes,
    expected_evidence_sha256: str,
) -> PartyDevelopmentTeacherPrior:
    """Authenticate the historical v1 receipt and bind all previously used roots."""

    if not isinstance(teacher, TrainingCandidateMLP):
        raise TypeError("teacher must be a TrainingCandidateMLP")
    for value, subject in (
        (model_file_sha256, "teacher model file"),
        (expected_evidence_sha256, "teacher offline evidence"),
    ):
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise PartyDevelopmentOutcomeLearningError(f"{subject} digest is invalid")
    if not isinstance(evidence_payload, bytes) or not evidence_payload:
        raise PartyDevelopmentOutcomeLearningError("teacher offline evidence payload is invalid")
    if hashlib.sha256(evidence_payload).hexdigest() != expected_evidence_sha256:
        raise PartyDevelopmentOutcomeLearningError("teacher offline evidence failed authentication")
    try:
        document = json.loads(evidence_payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PartyDevelopmentOutcomeLearningError(
            "teacher offline evidence is invalid JSON"
        ) from error
    canonical_model_sha256 = canonical_training_candidate_model_sha256(teacher)
    if (
        not isinstance(document, Mapping)
        or document.get("schema") != "pokemon-training-candidate-offline-receipt-v1"
        or document.get("status") != "offline_candidate_eligible"
        or document.get("candidate_model_file_sha256") != model_file_sha256
        or document.get("candidate_model_canonical_sha256") != canonical_model_sha256
        or document.get("offline_candidate_eligible") is not True
        or document.get("private_artifacts_tracked") is not False
    ):
        raise PartyDevelopmentOutcomeLearningError(
            "teacher offline evidence does not bind the supplied model"
        )
    lineages = document.get("lineages")
    if not isinstance(lineages, list) or not lineages:
        raise PartyDevelopmentOutcomeLearningError(
            "teacher offline evidence has no lineage inventory"
        )
    partitions: dict[str, list[tuple[str, str]]] = {
        "train": [],
        "validation": [],
    }
    for row in lineages:
        if not isinstance(row, Mapping):
            raise PartyDevelopmentOutcomeLearningError("teacher offline lineage record is invalid")
        partition = row.get("partition")
        lineage_id = row.get("lineage_id")
        state_sha256 = row.get("root_sha256")
        if (
            partition not in partitions
            or not isinstance(lineage_id, str)
            or _SAFE_ID.fullmatch(lineage_id) is None
            or not isinstance(state_sha256, str)
            or _SHA256.fullmatch(state_sha256) is None
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "teacher offline lineage identity is invalid"
            )
        partitions[partition].append((lineage_id, state_sha256))
    if len(partitions["train"]) != 2 or len(partitions["validation"]) != 1:
        raise PartyDevelopmentOutcomeLearningError(
            "teacher offline evidence has an unexpected partition shape"
        )
    training = tuple(sorted(partitions["train"]))
    evaluation = tuple(sorted(partitions["validation"]))
    return PartyDevelopmentTeacherPrior(
        model_file_sha256=model_file_sha256,
        model_canonical_sha256=canonical_model_sha256,
        offline_evidence_sha256=expected_evidence_sha256,
        training_root_lineage_ids=tuple(item[0] for item in training),
        training_state_sha256=tuple(item[1] for item in training),
        evaluation_root_lineage_ids=tuple(item[0] for item in evaluation),
        evaluation_state_sha256=tuple(item[1] for item in evaluation),
    )


def _route_geometry_fit_projection(base_model, choices):
    """Condition only newly activated route columns, using TRAIN inputs only.

    Unknown geometry is all-zero and keeps its old output exactly. Requiring
    zero prior weights makes the pre-fit rescaling a score-preserving change.
    No label, development menu or desired winner chooses a normalization scale.
    """
    from .party_development_rank import PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID

    names = (
        "venue.travel_steps_known",
        "venue.travel_steps",
        "venue.recovery_steps_known",
        "venue.recovery_steps",
    )
    if base_model.feature_schema_id != PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID:
        raise PartyDevelopmentOutcomeLearningError("geometry activation requires workload schema")
    columns = tuple(base_model.feature_names.index(n) for n in names)
    if np.any(base_model.weights1[list(columns)] != 0) or np.any(
        base_model.feature_mean[list(columns)] != 0
    ):
        raise PartyDevelopmentOutcomeLearningError(
            "geometry activation requires zero-influence parent"
        )
    matrices = [_example_features(example) for example in choices]
    numeric = (columns[1], columns[3])
    if not any(len(np.unique(x[:, numeric], axis=0)) > 1 for x in matrices):
        raise PartyDevelopmentOutcomeLearningError(
            "geometry activation needs comparative numeric variation"
        )
    features = np.concatenate(matrices, axis=0)
    if (
        np.any(features[:, columns[0]] != 1)
        or np.any(features[:, columns[2]] != 1)
        or np.any(features[:, numeric] < 0)
        or np.any(features[:, 0] != 0)
    ):
        raise PartyDevelopmentOutcomeLearningError(
            "geometry fit needs known nonnegative venue quotes"
        )
    scales = base_model.feature_scale.copy()
    for column in numeric:
        scale = float(np.sqrt(np.mean(features[:, column] ** 2)))
        if not math.isfinite(scale) or scale <= 0:
            raise PartyDevelopmentOutcomeLearningError("geometry value has no finite TRAIN support")
        scales[column] = scale
    return (
        scales,
        columns,
        dict(
            trainable_feature_names=list(names),
            parameter_scope="weights1_geometry_rows_only",
            scale_rule="zero_mean_TRAIN_candidate_RMS_numeric_steps_only",
            feature_scale_before=[float(base_model.feature_scale[c]) for c in columns],
            feature_scale_after=[float(scales[c]) for c in columns],
            labels_used_for_scaling=False,
            retained_unknown_geometry_algebra=True,
            other_parameters_frozen=True,
        ),
    )


def _workload_fit_projection(base_model, choices):
    """Condition newly introduced zero-influence inputs from TRAIN features.

    Fixed public unit divisors are not useful optimizer scales for small XP
    values. Zero means and zero initial weights preserve the entire prior
    function, including old menus with no workload, before learning starts.
    """
    names = tuple(PARTY_DEVELOPMENT_WORKLOAD_FEATURE_NAMES[len(PARTY_DEVELOPMENT_FEATURE_NAMES) :])
    if not all(name in base_model.feature_names for name in names):
        raise PartyDevelopmentOutcomeLearningError("workload activation requires workload schema")
    columns = tuple(base_model.feature_names.index(name) for name in names)
    if np.any(base_model.weights1[list(columns)] != 0) or np.any(
        base_model.feature_mean[list(columns)] != 0
    ):
        raise PartyDevelopmentOutcomeLearningError(
            "workload activation requires zero-influence prior"
        )
    if any(not item.fully_measured for item in choices):
        raise PartyDevelopmentOutcomeLearningError("workload activation requires measured TRAIN")
    features = np.concatenate(
        [_example_features(item)[list(item.available_candidate_indices)] for item in choices]
    )
    yield_column = base_model.feature_names.index("venue.expected_recipient_xp_per_encounter")
    if np.ptp(features[:, yield_column]) <= 0:
        raise PartyDevelopmentOutcomeLearningError(
            "workload activation needs comparative yield variation"
        )
    numeric = {
        "level_workload.current_level",
        "level_workload.target_level",
        "level_workload.level_gain",
        "level_workload.remaining_xp",
        "venue.expected_recipient_xp_per_encounter",
        "venue.travel_steps",
        "venue.recovery_steps",
    }
    scales = base_model.feature_scale.copy()
    for name in numeric:
        column = base_model.feature_names.index(name)
        rms = float(np.sqrt(np.mean(features[:, column] ** 2)))
        if not math.isfinite(rms):
            raise PartyDevelopmentOutcomeLearningError("workload TRAIN scale is not finite")
        scales[column] = rms if rms > 0 else 1.0
    return (
        scales,
        columns,
        dict(
            trainable_feature_names=list(names),
            parameter_scope="weights1_workload_rows_only",
            normalization="fixed_available_TRAIN_candidate_RMS_zero_mean",
            labels_used_for_scaling=False,
            retained_zero_workload_algebra=True,
            teacher_choice_targets=0,
        ),
    )


def recondition_party_development_workload(
    base_model: PartyDevelopmentOutcomeModel,
    examples: Iterable[ScenarioOutcomeExample],
) -> tuple[PartyDevelopmentOutcomeModel, dict[str, object]]:
    """Change optimizer units while preserving an already learned scorer.

    Only new, fully measured TRAIN candidate inputs determine RMS scales. Labels
    do not enter this operation. Rescaling each corresponding first-layer row
    preserves its coefficient divided by scale, including nonzero means and
    unknown-workload menus. No fit, ancestry consumption or policy adoption occurs.
    """
    from dataclasses import replace

    choices = tuple(examples)
    if base_model.feature_schema_id != PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID:
        raise PartyDevelopmentOutcomeLearningError("reconditioning requires workload schema")
    _require_examples(
        choices,
        partition=ScenarioPartition.TRAIN,
        feature_schema_id=base_model.feature_schema_id,
    )
    _require_disjoint_from_teacher_prior(base_model, choices)
    _require_disjoint_from_outcome_training(base_model, choices)
    if any(not item.fully_measured for item in choices):
        raise PartyDevelopmentOutcomeLearningError("reconditioning requires measured TRAIN")
    features = np.concatenate(
        [_example_features(item)[list(item.available_candidate_indices)] for item in choices]
    )
    numeric = (
        "level_workload.current_level",
        "level_workload.target_level",
        "level_workload.level_gain",
        "level_workload.remaining_xp",
        "venue.expected_recipient_xp_per_encounter",
        "venue.travel_steps",
        "venue.recovery_steps",
    )
    yield_column = base_model.feature_names.index(numeric[4])
    if np.ptp(features[:, yield_column]) <= 0:
        raise PartyDevelopmentOutcomeLearningError("reconditioning needs yield variation")
    scales = base_model.feature_scale.copy()
    weights = base_model.weights1.copy()
    for name in numeric:
        column = base_model.feature_names.index(name)
        rms = float(np.sqrt(np.mean(features[:, column] ** 2)))
        if not math.isfinite(rms):
            raise PartyDevelopmentOutcomeLearningError("nonfinite TRAIN reconditioning scale")
        scales[column] = rms if rms > 0 else 1.0
        weights[column] *= scales[column] / base_model.feature_scale[column]
    model = replace(base_model, weights1=weights, feature_scale=scales)
    return model, dict(
        normalization="available_new_TRAIN_candidate_RMS_function_preserving",
        numeric_feature_names=list(numeric),
        labels_used_for_scaling=False,
        optimizer_calls=0,
        new_training_examples=0,
        ancestry_consumed=False,
        original_model_sha256=canonical_party_development_outcome_model_sha256(base_model),
        reconditioned_model_sha256=canonical_party_development_outcome_model_sha256(model),
    )


def adapt_party_development_model_from_outcomes(
    base_model: PartyDevelopmentOutcomeModel,
    examples: Iterable[ScenarioOutcomeExample],
    *,
    epochs: int = 200,
    learning_rate: float = 0.01,
    prior_l2: float = 0.1,
    restrict_route_geometry: bool = False,
    freeze_route_geometry: bool = False,
    restrict_workload: bool = False,
    condition_workload: bool = False,
    refine_workload: bool = False,
    refine_suitability: bool = False,
    include_observed_stats: bool = False,
    mix_completed_task_costs: bool = False,
    rehearsal_examples: Iterable[ScenarioOutcomeExample] = (),
    rehearsal_attestation_sha256: str | None = None,
    related_task_rehearsal: bool = False,
) -> PartyDevelopmentOutcomeUpdate:
    """Fit TRAIN soft preferences; optionally activate only fresh route-cost rows.

    The default preserves the existing unrestricted update exactly. Restricted
    activation freezes all other parameters and retains unknown-geometry outputs.
    """

    if type(restrict_route_geometry) is not bool:
        raise PartyDevelopmentOutcomeLearningError("route geometry restriction must be boolean")
    if type(restrict_workload) is not bool or (
        restrict_workload and (restrict_route_geometry or freeze_route_geometry)
    ):
        raise PartyDevelopmentOutcomeLearningError("incompatible workload fitting mode")
    if type(condition_workload) is not bool or (
        condition_workload and (restrict_workload or restrict_route_geometry)
    ):
        raise PartyDevelopmentOutcomeLearningError("incompatible workload conditioning mode")
    if type(refine_workload) is not bool or (
        refine_workload
        and (
            restrict_route_geometry
            or restrict_workload
            or condition_workload
            or freeze_route_geometry
        )
    ):
        raise PartyDevelopmentOutcomeLearningError("incompatible workload refinement mode")
    if type(refine_suitability) is not bool or (refine_suitability and (
        restrict_route_geometry or restrict_workload or condition_workload or freeze_route_geometry or refine_workload
    )):
        raise PartyDevelopmentOutcomeLearningError("incompatible suitability refinement mode")
    if type(include_observed_stats) is not bool or (include_observed_stats and not refine_suitability):
        raise PartyDevelopmentOutcomeLearningError("observed-stat refinement requires explicit suitability scope")
    if type(mix_completed_task_costs) is not bool or (
        mix_completed_task_costs and not (refine_suitability and include_observed_stats)
    ):
        raise PartyDevelopmentOutcomeLearningError(
            "mixed complete-task cost fitting requires explicit observed-stat scope"
        )
    if type(related_task_rehearsal) is not bool or (
        related_task_rehearsal and not mix_completed_task_costs
    ):
        raise PartyDevelopmentOutcomeLearningError(
            "related-task rehearsal requires explicit mixed completed-task scope"
        )
    replay = tuple(rehearsal_examples)
    if mix_completed_task_costs and replay and not related_task_rehearsal:
        raise PartyDevelopmentOutcomeLearningError(
            "mixed complete-task cost fitting has no rehearsal scope"
        )
    choices = tuple(examples)
    _require_examples(
        choices,
        partition=ScenarioPartition.TRAIN,
        feature_schema_id=base_model.feature_schema_id,
        mix_completed_task_costs=mix_completed_task_costs,
    )
    choice_roots = {item.root_lineage_id for item in choices}
    choice_states = {item.initial_state_sha256 for item in choices}
    _require_disjoint_from_teacher_prior(base_model, choices)
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
    if type(freeze_route_geometry) is not bool or (
        freeze_route_geometry and restrict_route_geometry
    ):
        raise PartyDevelopmentOutcomeLearningError("incompatible route geometry fitting modes")
    rehearsal = None
    if replay:
        if (
            restrict_route_geometry
            or restrict_workload
            or condition_workload
            or not isinstance(rehearsal_attestation_sha256, str)
            or _SHA256.fullmatch(rehearsal_attestation_sha256) is None
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "rehearsal needs its authenticated TRAIN attestation"
            )
        _require_examples(
            replay,
            partition=ScenarioPartition.TRAIN,
            feature_schema_id=(replay[0].feature_schema_id if refine_suitability else base_model.feature_schema_id),
            mix_completed_task_costs=related_task_rehearsal,
        )
        if refine_suitability:
            for example in replay:
                _aligned_features(_example_features(example), example.feature_schema_id, base_model.feature_schema_id)
        _require_disjoint_from_teacher_prior(base_model, replay)
        if related_task_rehearsal:
            _require_related_task_rehearsal(choices, replay)
        elif (
            any(not x.fully_measured or not x.learner_update_eligible for x in replay)
            or not {x.root_lineage_id for x in replay}
            <= set(base_model.outcome_training_root_lineage_ids)
            or not {x.initial_state_sha256 for x in replay}
            <= set(base_model.outcome_training_state_sha256)
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "rehearsal is not a previously fitted measured TRAIN source"
            )
        rehearsal = dict(
            attestation_sha256=rehearsal_attestation_sha256,
            replay_example_sha256s=[x.example_sha256 for x in replay],
            replay_example_count=len(replay),
            new_example_count=len(choices),
            replay_counted_as_new=False,
            geometry_frozen=freeze_route_geometry,
        )
        if related_task_rehearsal:
            rehearsal.update(
                related_current_source_tasks=True,
                independent_origins_added=0,
                one_extra_distinct_task_per_primary_origin=True,
                source_authority="caller-authenticated TRAIN task bindings;not admission here",
            )
    elif related_task_rehearsal:
        raise PartyDevelopmentOutcomeLearningError("related-task rehearsal needs measured tasks")
    elif rehearsal_attestation_sha256 is not None:
        raise PartyDevelopmentOutcomeLearningError("unused rehearsal attestation")
    training_choices = (*choices, *replay)
    example_weights = None
    if related_task_rehearsal:
        counts = {x.root_lineage_id: 1 for x in choices}
        for example in replay:
            counts[example.root_lineage_id] += 1
        example_weights = tuple(
            1.0 / (len(choices) * counts[x.root_lineage_id]) for x in training_choices
        )
        rehearsal.update(
            normalization="equal-origin-mean-of-distinct-task-losses",
            primary_origin_count=len(choices),
            total_task_questions=len(training_choices),
            task_loss_weights=list(example_weights),
        )
    frozen_geometry_columns = None
    if freeze_route_geometry:
        names = (
            "venue.travel_steps_known",
            "venue.travel_steps",
            "venue.recovery_steps_known",
            "venue.recovery_steps",
        )
        if not all(n in base_model.feature_names for n in names):
            raise PartyDevelopmentOutcomeLearningError("geometry freeze requires workload schema")
        frozen_geometry_columns = tuple(base_model.feature_names.index(n) for n in names)
        if np.any(base_model.weights1[list(frozen_geometry_columns)] != 0):
            raise PartyDevelopmentOutcomeLearningError(
                "geometry freeze requires the unchanged zero-weight parent"
            )
    feature_scale = base_model.feature_scale
    geometry_fit = None
    workload_fit = None
    geometry_columns = None
    if restrict_route_geometry:
        feature_scale, geometry_columns, geometry_fit = _route_geometry_fit_projection(
            base_model, choices
        )
    if restrict_workload:
        feature_scale, geometry_columns, workload_fit = _workload_fit_projection(
            base_model, choices
        )
    if condition_workload:
        feature_scale, _, workload_fit = _workload_fit_projection(base_model, choices)
        workload_fit["parameter_scope"] = "existing_full_update_with_workload_conditioning"
        workload_fit["retained_zero_workload_algebra"] = False
    if refine_workload:
        names = tuple(
            name
            for name in PARTY_DEVELOPMENT_WORKLOAD_FEATURE_NAMES
            if name.startswith("level_workload.")
        )
        if base_model.feature_schema_id != PARTY_DEVELOPMENT_WORKLOAD_FEATURE_SCHEMA_ID:
            raise PartyDevelopmentOutcomeLearningError(
                "workload refinement requires workload schema"
            )
        geometry_columns = tuple(base_model.feature_names.index(name) for name in names)
        if np.any(base_model.feature_mean[list(geometry_columns)] != 0):
            raise PartyDevelopmentOutcomeLearningError(
                "workload refinement requires zero workload means"
            )
        workload_fit = dict(
            parameter_scope="existing_level_workload_first_layer_rows_only",
            feature_names=list(names),
            retained_zero_workload_algebra=True,
            venue_covariates_frozen=True,
            feature_scale_changed=False,
            activation_of_zero_weights_required=False,
        )
    if refine_suitability:
        if base_model.feature_schema_id != PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID:
            raise PartyDevelopmentOutcomeLearningError("suitability refinement needs the observed matchup schema")
        # Default scope retains the first six rows. Explicit observed-stat scope
        # uses the existing transferable numeric stats, never species/slot identity.
        names = (VENUE_MATCHUP_FEATURE_NAMES if include_observed_stats else VENUE_MATCHUP_FEATURE_NAMES[:6])
        geometry_columns = tuple(base_model.feature_names.index(n) for n in names)
        all_matchup_columns = tuple(base_model.feature_names.index(n) for n in VENUE_MATCHUP_FEATURE_NAMES)
        if np.any(base_model.feature_mean[list(all_matchup_columns)] != 0):
            raise PartyDevelopmentOutcomeLearningError("suitability unknown zeros require zero means")
        normalization_choices = training_choices if related_task_rehearsal else choices
        input_blocks = tuple(
            _example_features(e)[list(e.available_candidate_indices)]
            for e in normalization_choices
        )
        inputs = np.concatenate(input_blocks)
        if not np.all(inputs[:, geometry_columns[0]] == 1):
            raise PartyDevelopmentOutcomeLearningError("fresh suitability fit requires observed matchups on every available candidate")
        if include_observed_stats and not np.all(inputs[:, base_model.feature_names.index("trainee.stats_known")] == 1):
            raise PartyDevelopmentOutcomeLearningError("observed-stat refinement requires native stats on every fresh candidate")
        feature_scale = base_model.feature_scale.copy()
        for col in geometry_columns:
            if related_task_rehearsal:
                rms = float(np.sqrt(sum(
                    weight * float(np.mean(block[:, col] ** 2))
                    for weight, block in zip(example_weights, input_blocks, strict=True)
                )))
            else:
                rms = float(np.sqrt(np.mean(inputs[:, col] ** 2)))
            feature_scale[col] = rms if rms > 0 else 1.0
        workload_fit = dict(parameter_scope=("venue_matchup_and_observed_stats_first_layer_rows_only" if include_observed_stats else "venue_matchup_and_max_hp_first_layer_rows_only"),
                            feature_names=list(names),
                            diagnostic_stat_rows_frozen=[] if include_observed_stats else list(VENUE_MATCHUP_FEATURE_NAMES[6:]),
                            normalization="available_fresh_TRAIN_input_RMS_zero_mean",
                            labels_used_for_scaling=False, retained_unknown_matchup_algebra=True,
                            legacy_parameters_frozen=True)
        if related_task_rehearsal:
            workload_fit["normalization"] = "equal-origin-task-candidate-RMS-zero-mean"
    if mix_completed_task_costs:
        workload_fit["mixed_completed_task_costs"] = dict(
            objective_sha256s=sorted({e.objective.objective_sha256 for e in training_choices}),
            targets_and_prospective_bindings_unchanged=True,
            unique_fastest_complete_task_required=True,
            native_admission_granted_here=False,
        )
    prior_weights1 = base_model.weights1.copy()
    if refine_suitability:
        prior_weights1[list(geometry_columns)] *= (feature_scale / base_model.feature_scale)[list(geometry_columns), None]
    prior_bias1 = base_model.bias1.copy()
    prior_weights2 = base_model.weights2.copy()
    weights1 = prior_weights1.copy()
    bias1 = prior_bias1.copy()
    weights2 = prior_weights2.copy()
    parameters = (weights1, bias1, weights2)
    priors = (prior_weights1, prior_bias1, prior_weights2)
    first = [np.zeros_like(value) for value in parameters]
    second = [np.zeros_like(value) for value in parameters]
    loss_before = _outcome_loss(base_model, training_choices, example_weights)

    for step in range(1, epochs + 1):
        gradients = [np.zeros_like(value) for value in parameters]
        for example_index, example in enumerate(training_choices):
            features = _aligned_features(_example_features(example), example.feature_schema_id, base_model.feature_schema_id)
            normalized = (features - base_model.feature_mean) / feature_scale
            hidden = _hidden_activations(normalized, weights1, bias1, base_model.feature_schema_id)
            probabilities = _masked_probabilities(hidden @ weights2, example)
            delta = probabilities - example.target_distribution
            if example_weights is not None:
                delta = delta * example_weights[example_index]
            gradients[2] += hidden.T @ delta
            hidden_delta = delta[:, None] * weights2[None, :]
            hidden_delta *= 1.0 - hidden * hidden
            gradients[0] += normalized.T @ hidden_delta
            gradients[1] += np.sum(hidden_delta, axis=0)
        for index in range(len(gradients)):
            if example_weights is None:
                gradients[index] /= len(training_choices)
            gradients[index] += prior_l2 * (parameters[index] - priors[index])
            if frozen_geometry_columns is not None and index == 0:
                gradients[index][list(frozen_geometry_columns)] = 0.0
            if geometry_columns is not None:
                if index == 0:
                    frozen = np.ones(gradients[index].shape[0], dtype=bool)
                    frozen[list(geometry_columns)] = False
                    gradients[index][frozen] = 0.0
                else:
                    gradients[index].fill(0.0)
            first[index] = 0.9 * first[index] + 0.1 * gradients[index]
            second[index] = 0.999 * second[index] + 0.001 * gradients[index] ** 2
            corrected_first = first[index] / (1.0 - 0.9**step)
            corrected_second = second[index] / (1.0 - 0.999**step)
            parameters[index][...] -= (
                learning_rate * corrected_first / (np.sqrt(corrected_second) + 1e-8)
            )

    updated = PartyDevelopmentOutcomeModel(
        weights1=weights1,
        bias1=bias1,
        weights2=weights2,
        feature_mean=base_model.feature_mean,
        feature_scale=feature_scale,
        training_seed=base_model.training_seed,
        teacher_prior=base_model.teacher_prior,
        outcome_training_examples=base_model.outcome_training_examples + len(choices),
        model_id=base_model.model_id,
        feature_schema_id=base_model.feature_schema_id,
        outcome_training_root_lineage_ids=tuple(
            sorted((*base_model.outcome_training_root_lineage_ids, *choice_roots))
        ),
        outcome_training_state_sha256=tuple(
            sorted((*base_model.outcome_training_state_sha256, *choice_states))
        ),
    )
    if geometry_columns is not None:
        frozen = np.ones(base_model.weights1.shape[0], dtype=bool)
        frozen[list(geometry_columns)] = False
        if (
            not np.array_equal(updated.weights1[frozen], base_model.weights1[frozen])
            or not np.array_equal(updated.bias1, base_model.bias1)
            or not np.array_equal(updated.weights2, base_model.weights2)
            or not np.array_equal(updated.feature_mean, base_model.feature_mean)
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "restricted geometry changed retained parameters"
            )
    loss_after = _outcome_loss(updated, training_choices, example_weights)
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
            training_root_lineage_ids=tuple(sorted(item.root_lineage_id for item in choices)),
            training_state_sha256=tuple(sorted(item.initial_state_sha256 for item in choices)),
            tied_target_examples=sum(len(item.best_candidate_indices) > 1 for item in choices),
            loss_before=loss_before,
            loss_after=loss_after,
            epochs=epochs,
            learning_rate=float(learning_rate),
            prior_l2=float(prior_l2),
            route_geometry_fit=geometry_fit,
            rehearsal_training=rehearsal,
            workload_fit=workload_fit,
        ),
    )


def evaluate_party_development_outcomes(
    model: PartyDevelopmentOutcomeModel,
    examples: Iterable[ScenarioOutcomeExample],
) -> PartyDevelopmentOutcomeEvaluation:
    """Evaluate without fitting on untouched development roots."""

    choices = tuple(examples)
    _require_examples(
        choices,
        partition=ScenarioPartition.DEVELOPMENT,
        feature_schema_id=model.feature_schema_id,
    )
    _require_disjoint_from_teacher_prior(model, choices)
    _require_disjoint_from_outcome_training(model, choices)
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
        winner_probabilities.append(
            float(np.sum(probabilities[list(example.best_candidate_indices)]))
        )
    if canonical_party_development_outcome_model_sha256(model) != model_sha256:
        raise PartyDevelopmentOutcomeLearningError("party-development evaluation mutated the model")
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
    _require_examples(
        choices,
        partition=ScenarioPartition.DEVELOPMENT,
        feature_schema_id=base_model.feature_schema_id,
    )
    if base_model.feature_schema_id != updated_model.feature_schema_id:
        raise PartyDevelopmentOutcomeLearningError("paired models use different feature schemas")
    if base_model.teacher_prior != updated_model.teacher_prior:
        raise PartyDevelopmentOutcomeLearningError(
            "paired party-development models do not share one teacher prior"
        )
    _require_disjoint_from_teacher_prior(base_model, choices)
    _require_disjoint_from_outcome_training(base_model, choices)
    _require_disjoint_from_outcome_training(updated_model, choices)
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
        or canonical_party_development_outcome_model_sha256(updated_model) != updated_sha256
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
    _require_examples(
        training,
        partition=ScenarioPartition.TRAIN,
        feature_schema_id=base_model.feature_schema_id,
    )
    _require_examples(
        development,
        partition=ScenarioPartition.DEVELOPMENT,
        feature_schema_id=base_model.feature_schema_id,
    )
    if training[0].objective != development[0].objective:
        raise PartyDevelopmentOutcomeLearningError("training and development objectives differ")
    _require_disjoint_from_teacher_prior(base_model, training)
    _require_disjoint_from_teacher_prior(base_model, development)
    _require_disjoint_from_outcome_training(base_model, development)
    if {item.root_lineage_id for item in training} & {item.root_lineage_id for item in development}:
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
        updated_development=evaluate_party_development_outcomes(update.model, development),
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
    feature_schema_id: str = PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID,
    mix_completed_task_costs: bool = False,
) -> None:
    expected_names = party_development_feature_names(feature_schema_id)
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
        if item.feature_schema_id != feature_schema_id or item.feature_names != expected_names:
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome feature schema is incompatible"
            )
        if not mix_completed_task_costs and item.objective != choices[0].objective:
            raise PartyDevelopmentOutcomeLearningError(
                "party-development outcome objectives differ"
            )
        if not item.fully_measured:
            raise PartyDevelopmentOutcomeLearningError(
                "censored party-development evidence cannot become a target"
            )
    if mix_completed_task_costs:
        _require_completed_task_cost_compatibility(choices)
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



def _require_related_task_rehearsal(choices, replay):
    """One additional distinct TRAIN question per fresh primary source.

    Native eligibility and distinct private recipient/task contracts remain the
    caller's authenticated responsibility. This check grants no new origin,
    partition change, duplicate-input lesson or previously consumed source.
    """
    primary = {x.root_lineage_id: x for x in choices}
    seen = set()
    for example in replay:
        source = primary.get(example.root_lineage_id)
        if (
            source is None
            or example.root_lineage_id in seen
            or example.initial_state_sha256 != source.initial_state_sha256
            or example.partition is not ScenarioPartition.TRAIN
            or source.partition is not ScenarioPartition.TRAIN
            or not example.fully_measured
            or not example.learner_update_eligible
            or example.scenario_id == source.scenario_id
            or example.prospective_binding_sha256 == source.prospective_binding_sha256
            or tuple(c.features for c in example.candidates)
            == tuple(c.features for c in source.candidates)
        ):
            raise PartyDevelopmentOutcomeLearningError(
                "related rehearsal needs one distinct measured TRAIN task on an exact primary source"
            )
        seen.add(example.root_lineage_id)


def _require_completed_task_cost_compatibility(choices):
    """Validate canonical completed task contracts; never rewrite outcomes.

    The optional loss uses each example's existing winner distribution. Its
    conservative initial scope requires a unique completed cost winner before either
    objective's differing tail can decide a preference. Native admission remains
    the caller's independently authenticated responsibility.
    """
    from .party_development_outcomes import PARTY_DEVELOPMENT_TARGET_TASK_OBJECTIVE
    from .party_development_fixed_target_outcomes import FIXED_LEVEL_READY_OBJECTIVE
    from .party_development_fixed_target_repeats import FIXED_LEVEL_READY_REPEATED_OBJECTIVE

    for example in choices:
        if example.feature_schema_id != PARTY_DEVELOPMENT_MATCHUP_FEATURE_SCHEMA_ID:
            raise PartyDevelopmentOutcomeLearningError("mixed task cost needs observed-matchup schema")
        if example.objective == PARTY_DEVELOPMENT_TARGET_TASK_OBJECTIVE:
            goal = "context.goal.evolution"
        elif example.objective in (FIXED_LEVEL_READY_OBJECTIVE, FIXED_LEVEL_READY_REPEATED_OBJECTIVE):
            goal = "context.goal.balance"
        else:
            raise PartyDevelopmentOutcomeLearningError("mixed task cost objective is not canonical")
        costs = []
        for index in example.available_candidate_indices:
            candidate, outcome = example.candidates[index], example.outcomes[index]
            if candidate.features[example.feature_names.index(goal)] != 1.0:
                raise PartyDevelopmentOutcomeLearningError("mixed task cost semantic goal differs")
            if (
                outcome is None
                or outcome.criterion_values[:2] != (1.0, 1.0)
                or outcome.frames_executed < 1
                or outcome.criterion_values[2] not in (0.0, 1.0)
            ):
                raise PartyDevelopmentOutcomeLearningError("mixed task cost needs safe measured arms")
            completed = outcome.criterion_values[2] == 1.0
            if completed:
                if outcome.criterion_values[3] != outcome.frames_executed:
                    raise PartyDevelopmentOutcomeLearningError("completed task cost differs from physical frames")
                costs.append((index, outcome.frames_executed))
            elif example.objective != PARTY_DEVELOPMENT_TARGET_TASK_OBJECTIVE or outcome.criterion_values[3] != 0.0:
                # The historical evolution objective masks unfinished-task cost
                # behind its false completion bit. Keep actual frames separately;
                # never make that arm a cheap completed task or ready lesson.
                raise PartyDevelopmentOutcomeLearningError("unfinished task cost contract differs")
        if not costs:
            raise PartyDevelopmentOutcomeLearningError("mixed task cost needs an observed completed arm")
        minimum = min(frames for _, frames in costs)
        fastest = tuple(index for index, frames in costs if frames == minimum)
        if len(fastest) != 1 or example.best_candidate_indices != fastest:
            raise PartyDevelopmentOutcomeLearningError("mixed task cost needs an unambiguous original cost winner")

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
            or not isinstance(value, int | float)
            or not math.isfinite(float(value))
            or (value <= 0 if strictly_positive else value < 0)
        ):
            raise PartyDevelopmentOutcomeLearningError(f"v2 {name} is invalid")


def _require_disjoint_from_teacher_prior(
    model: PartyDevelopmentOutcomeModel,
    choices: tuple[ScenarioOutcomeExample, ...],
) -> None:
    roots = {item.root_lineage_id for item in choices}
    states = {item.initial_state_sha256 for item in choices}
    if roots & model.teacher_prior.consumed_root_lineage_ids:
        raise PartyDevelopmentOutcomeLearningError(
            "party-development root overlaps teacher-prior evidence"
        )
    if states & model.teacher_prior.consumed_state_sha256:
        raise PartyDevelopmentOutcomeLearningError(
            "party-development state overlaps teacher-prior evidence"
        )


def _require_disjoint_from_outcome_training(
    model: PartyDevelopmentOutcomeModel,
    choices: tuple[ScenarioOutcomeExample, ...],
) -> None:
    roots = {item.root_lineage_id for item in choices}
    states = {item.initial_state_sha256 for item in choices}
    if roots & set(model.outcome_training_root_lineage_ids):
        raise PartyDevelopmentOutcomeLearningError(
            "party-development development root overlaps outcome training"
        )
    if states & set(model.outcome_training_state_sha256):
        raise PartyDevelopmentOutcomeLearningError(
            "party-development development state overlaps outcome training"
        )


def _example_features(example: ScenarioOutcomeExample) -> NDArray[np.float64]:
    return np.asarray([item.features for item in example.candidates], dtype=np.float64)


def _example_probabilities(
    model: PartyDevelopmentOutcomeModel,
    example: ScenarioOutcomeExample,
) -> NDArray[np.float64]:
    return _masked_probabilities(model._scores(_aligned_features(_example_features(example), example.feature_schema_id, model.feature_schema_id)), example)


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
    example_weights: tuple[float, ...] | None = None,
) -> float:
    losses = []
    for item in choices:
        probabilities = _example_probabilities(model, item)
        target = item.target_distribution
        positive = target > 0
        losses.append(float(-np.sum(target[positive] * np.log(probabilities[positive]))))
    if example_weights is None:
        return float(np.mean(losses))
    if (
        len(example_weights) != len(losses)
        or any(not math.isfinite(w) or w <= 0 for w in example_weights)
        or not math.isclose(sum(example_weights), 1.0, rel_tol=0, abs_tol=1e-12)
    ):
        raise PartyDevelopmentOutcomeLearningError("task loss weights must form an origin-balanced mean")
    return float(sum(w * loss for w, loss in zip(example_weights, losses, strict=True)))


__all__ = [
    "PARTY_DEVELOPMENT_OUTCOME_MODEL_ID",
    "PartyDevelopmentOutcomeEvaluation",
    "PartyDevelopmentOutcomeLearningCycle",
    "PartyDevelopmentOutcomeLearningError",
    "PartyDevelopmentOutcomeModel",
    "PartyDevelopmentPairedEvaluation",
    "PartyDevelopmentTeacherPrior",
    "PartyDevelopmentOutcomeUpdate",
    "PartyDevelopmentOutcomeUpdateReport",
    "adapt_party_development_model_from_outcomes",
    "bind_teacher_prior_from_offline_evidence",
    "canonical_party_development_outcome_model_sha256",
    "compare_party_development_outcomes",
    "evaluate_party_development_outcomes",
    "initialize_from_teacher_model",
    "load_party_development_outcome_model",
    "run_party_development_outcome_learning_cycle",
]



