"""Aggregate-only comparison for the sealed rootless dependency roster."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DependencyCandidateFeatures,
    VerifiedDevelopmentComparison,
    VerifiedDevelopmentOpening,
    dependency_predecision_features,
)
from pokemon_red_completion.living_dex_dependency_ranker import DependencyRankerModel
from pokemon_red_completion.provenance import canonical_sha256

DEPENDENCY_COMPARISON_SCHEMA = "pokemon.core.rootless-dependency-comparison.v1"


class LivingDexDependencyComparisonError(ValueError):
    """The sealed dependency comparison or its aggregate claim is invalid."""


@dataclass(frozen=True, slots=True)
class DependencyComparisonResult:
    design_sha256: str
    model_sha256: str
    fit_manifest_sha256: str
    fit_terminal_sha256: str
    row_count: int
    family_count: int
    candidate_correct: int
    baseline_correct: int
    candidate_cross_entropy: float
    baseline_cross_entropy: float
    candidate_mean_winner_probability: float
    baseline_mean_winner_probability: float
    descriptive_gate_passed: bool

    def __post_init__(self) -> None:
        if (
            not all(
                _is_sha256(value)
                for value in (
                    self.design_sha256,
                    self.model_sha256,
                    self.fit_manifest_sha256,
                    self.fit_terminal_sha256,
                )
            )
            or self.row_count != 4
            or self.family_count != 2
            or not 0 <= self.candidate_correct <= 4
            or self.baseline_correct != 2
            or not all(
                type(value) is float and math.isfinite(value)
                for value in (
                    self.candidate_cross_entropy,
                    self.baseline_cross_entropy,
                    self.candidate_mean_winner_probability,
                    self.baseline_mean_winner_probability,
                )
            )
            or self.baseline_cross_entropy != math.log(2.0)
            or self.baseline_mean_winner_probability != 0.5
        ):
            raise LivingDexDependencyComparisonError("dependency comparison metrics differ")
        expected_gate = (
            self.candidate_correct >= 3
            and self.candidate_cross_entropy < self.baseline_cross_entropy
            and self.candidate_mean_winner_probability > self.baseline_mean_winner_probability
        )
        if self.descriptive_gate_passed is not expected_gate:
            raise LivingDexDependencyComparisonError("dependency comparison gate differs")

    @property
    def comparison_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": DEPENDENCY_COMPARISON_SCHEMA,
            "design_sha256": self.design_sha256,
            "model_sha256": self.model_sha256,
            "fit_manifest_sha256": self.fit_manifest_sha256,
            "fit_terminal_sha256": self.fit_terminal_sha256,
            "row_count": self.row_count,
            "family_count": self.family_count,
            "candidate_correct": self.candidate_correct,
            "baseline_correct": self.baseline_correct,
            "candidate_cross_entropy": self.candidate_cross_entropy,
            "baseline_cross_entropy": self.baseline_cross_entropy,
            "candidate_mean_winner_probability": self.candidate_mean_winner_probability,
            "baseline_mean_winner_probability": self.baseline_mean_winner_probability,
            "descriptive_gate_passed": self.descriptive_gate_passed,
            "claim_boundary": (
                "descriptive held-out-structure behavior only; not statistical promotion, "
                "gameplay competence, authority, or cross-title transfer"
            ),
            "development_rows_disclosed": 0,
        }


def compare_dependency_ranker(
    *,
    design_sha256: str,
    model: DependencyRankerModel,
    verified: VerifiedDevelopmentComparison,
) -> DependencyComparisonResult:
    """Compare once on four verified openings and return aggregate metrics only."""

    if not _is_sha256(design_sha256):
        raise LivingDexDependencyComparisonError("dependency design identity differs")
    if not isinstance(model, DependencyRankerModel):
        raise TypeError("model must be a DependencyRankerModel")
    if not isinstance(verified, VerifiedDevelopmentComparison):
        raise TypeError("verified must be a VerifiedDevelopmentComparison")
    if len(verified.openings) != 4:
        raise LivingDexDependencyComparisonError("comparison denominator differs")
    winner_probabilities: list[float] = []
    correct = 0
    for opening in verified.openings:
        acquire_probability = _acquire_probability(model, opening)
        preferred = (
            opening.assigned_action
            if opening.derived_reward == 1
            else _other_action(opening.assigned_action)
        )
        winner_probability = (
            acquire_probability
            if preferred is GoalKind.ACQUIRE_SPECIES
            else 1.0 - acquire_probability
        )
        winner_probabilities.append(winner_probability)
        correct += int(winner_probability >= 0.5)
    if Counter(opening.derived_reward for opening in verified.openings) != {-1: 2, 1: 2}:
        raise LivingDexDependencyComparisonError("comparison reward balance differs")
    candidate_loss = -sum(math.log(max(1e-12, value)) for value in winner_probabilities) / 4
    candidate_mean = sum(winner_probabilities) / 4
    return DependencyComparisonResult(
        design_sha256=design_sha256,
        model_sha256=model.model_sha256,
        fit_manifest_sha256=verified.fit_manifest_sha256,
        fit_terminal_sha256=verified.fit_terminal_sha256,
        row_count=4,
        family_count=2,
        candidate_correct=correct,
        baseline_correct=2,
        candidate_cross_entropy=float(candidate_loss),
        baseline_cross_entropy=math.log(2.0),
        candidate_mean_winner_probability=float(candidate_mean),
        baseline_mean_winner_probability=0.5,
        descriptive_gate_passed=(
            correct >= 3 and candidate_loss < math.log(2.0) and candidate_mean > 0.5
        ),
    )


def _acquire_probability(
    model: DependencyRankerModel,
    opening: VerifiedDevelopmentOpening,
) -> float:
    state = dependency_predecision_features(opening.before, opening.structure)
    acquire = DependencyCandidateFeatures(state, 1, 0, 0)
    evolve = DependencyCandidateFeatures(state, 0, 1, 1)
    delta = model.score(acquire) - model.score(evolve)
    if delta >= 0.0:
        inverse = math.exp(-delta)
        return 1.0 / (1.0 + inverse)
    exponent = math.exp(delta)
    return exponent / (1.0 + exponent)


def _other_action(action: GoalKind) -> GoalKind:
    if action is GoalKind.ACQUIRE_SPECIES:
        return GoalKind.EVOLVE_SPECIES
    if action is GoalKind.EVOLVE_SPECIES:
        return GoalKind.ACQUIRE_SPECIES
    raise LivingDexDependencyComparisonError("dependency action differs")


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
