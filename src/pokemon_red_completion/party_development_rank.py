"""Completion-aware, identity-free party-development candidate features.

The historical v1 ranker remains frozen because it is reproducible evidence of
teacher imitation.  This v2 projection keeps every v1 feature as an exact
prefix, then adds the semantics needed by the actual product goal: balanced
teams, evolution, living collection, reusable party roles, survival, and the
prospective cost and reliability of a training venue.

Nothing in this module names a species, map, move, party slot, save state, or
game.  Concrete adapters retain those bindings privately and provide only the
portable facts below.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TrainingCandidateSet,
    TrainingChoiceKind,
)

PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID = (
    "pokemon.core.party-development.completion-candidate.v2"
)
MAX_EVOLUTION_STAGES = 4
MAX_PRIOR_SUPPORT = 64

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class PartyDevelopmentFeatureError(ValueError):
    """Raised when completion-aware candidate semantics are inconsistent."""


class PartyDevelopmentGoal(StrEnum):
    """The portable completion pressure this choice is intended to reduce."""

    BALANCE = "balance"
    EVOLUTION = "evolution"
    COLLECTION = "collection"
    ROLE_COVERAGE = "role_coverage"


class EvolutionRouteKind(StrEnum):
    """Cross-title evolution mechanisms without item, species, or title identity."""

    NONE = "none"
    LEVEL = "level"
    ITEM = "item"
    TRADE = "trade"
    CONDITION = "condition"


PARTY_DEVELOPMENT_FEATURE_NAMES = (
    *TRAINING_CANDIDATE_FEATURE_NAMES,
    *(f"context.goal.{goal.value}" for goal in PartyDevelopmentGoal),
    "party.below_floor_share",
    "party.evolution_needed_share",
    "party.registration_needed_share",
    "party.living_needed_share",
    "party.role_gap_share",
    "collection.registration_completion",
    "collection.living_completion",
    "party.role_coverage",
    "party.healthy_trainable_share",
    "party.exhausted_share",
    "party.fainted_share",
    "candidate.evolution_required",
    "candidate.evolution_stages_remaining",
    "candidate.evolution_level_distance_known",
    "candidate.evolution_level_distance",
    *(f"candidate.evolution_method.{kind.value}" for kind in EvolutionRouteKind),
    "candidate.evolution_feasible_now",
    "candidate.registration_needed",
    "candidate.living_target_needed",
    "candidate.living_retention_risk",
    "candidate.role_needed",
    "candidate.role_complete",
    "candidate.emergency_escort_required",
    "candidate.projected_survival_margin",
    "venue.prior_available",
    "venue.prior_reliability",
    "venue.prior_expected_yield",
    "venue.prior_matchup_safety",
    "venue.prior_travel_cost",
    "venue.prior_recovery_cost",
    "venue.prior_support",
)


@dataclass(frozen=True, slots=True)
class PartyDevelopmentContext:
    """Party-wide completion pressures visible before a candidate is executed."""

    goal: PartyDevelopmentGoal
    party_size: int
    below_floor_count: int
    evolution_needed_count: int
    registration_needed_count: int
    living_needed_count: int
    role_gap_count: int
    registration_completion_ratio: float
    living_completion_ratio: float
    role_coverage_ratio: float
    healthy_trainable_count: int
    exhausted_count: int
    fainted_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.goal, PartyDevelopmentGoal):
            raise PartyDevelopmentFeatureError("party-development goal is invalid")
        if type(self.party_size) is not int or not 1 <= self.party_size <= 6:  # noqa: E721
            raise PartyDevelopmentFeatureError("party size must be from one through six")
        for name in (
            "below_floor_count",
            "evolution_needed_count",
            "registration_needed_count",
            "living_needed_count",
            "role_gap_count",
            "healthy_trainable_count",
            "exhausted_count",
            "fainted_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= self.party_size:  # noqa: E721
                raise PartyDevelopmentFeatureError(
                    f"{name.replace('_', ' ')} must fit the active party"
                )
        if self.healthy_trainable_count + self.exhausted_count + self.fainted_count > (
            self.party_size
        ):
            raise PartyDevelopmentFeatureError(
                "healthy, exhausted, and fainted party counts overlap"
            )
        for name in (
            "registration_completion_ratio",
            "living_completion_ratio",
            "role_coverage_ratio",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
            ):
                raise PartyDevelopmentFeatureError(
                    f"{name.replace('_', ' ')} must be a finite unit value"
                )


@dataclass(frozen=True, slots=True)
class EvolutionSemantics:
    """How far one candidate is from its next required evolution."""

    required: bool
    stages_remaining: int
    route_kind: EvolutionRouteKind
    levels_to_next: int | None = None
    feasible_now: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.required, bool) or not isinstance(self.feasible_now, bool):
            raise PartyDevelopmentFeatureError("evolution flags must be boolean")
        if (
            type(self.stages_remaining) is not int  # noqa: E721
            or not 0 <= self.stages_remaining <= MAX_EVOLUTION_STAGES
        ):
            raise PartyDevelopmentFeatureError("evolution stages remaining are invalid")
        if not isinstance(self.route_kind, EvolutionRouteKind):
            raise PartyDevelopmentFeatureError("evolution route kind is invalid")
        if self.levels_to_next is not None and (
            type(self.levels_to_next) is not int  # noqa: E721
            or not 0 <= self.levels_to_next <= 99
        ):
            raise PartyDevelopmentFeatureError("levels to next evolution are invalid")
        if self.required:
            if self.stages_remaining < 1 or self.route_kind is EvolutionRouteKind.NONE:
                raise PartyDevelopmentFeatureError(
                    "a required evolution needs a remaining stage and route"
                )
        elif (
            self.stages_remaining != 0
            or self.route_kind is not EvolutionRouteKind.NONE
            or self.levels_to_next is not None
            or self.feasible_now
        ):
            raise PartyDevelopmentFeatureError(
                "a completed evolution path cannot carry a remaining requirement"
            )
        if self.levels_to_next is not None and self.route_kind is not EvolutionRouteKind.LEVEL:
            raise PartyDevelopmentFeatureError(
                "only a level evolution can carry a level distance"
            )


@dataclass(frozen=True, slots=True)
class CandidateCompletionSemantics:
    """Portable completion facts for one trainee or fixed venue trainee."""

    evolution: EvolutionSemantics
    registration_needed: bool = False
    living_target_needed: bool = False
    living_retention_risk: bool = False
    role_needed: bool = False
    role_complete: bool = False
    emergency_escort_required: bool = False
    projected_survival_margin: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.evolution, EvolutionSemantics):
            raise PartyDevelopmentFeatureError("candidate evolution semantics are invalid")
        for name in (
            "registration_needed",
            "living_target_needed",
            "living_retention_risk",
            "role_needed",
            "role_complete",
            "emergency_escort_required",
        ):
            if not isinstance(getattr(self, name), bool):
                raise PartyDevelopmentFeatureError(
                    f"{name.replace('_', ' ')} must be boolean"
                )
        if self.role_needed and self.role_complete:
            raise PartyDevelopmentFeatureError(
                "a candidate role cannot be both missing and complete"
            )
        if (
            isinstance(self.projected_survival_margin, bool)
            or not isinstance(self.projected_survival_margin, (int, float))
            or not math.isfinite(float(self.projected_survival_margin))
            or not -1.0 <= float(self.projected_survival_margin) <= 1.0
        ):
            raise PartyDevelopmentFeatureError(
                "projected survival margin must be a finite signed unit value"
            )


@dataclass(frozen=True, slots=True)
class VenueOperationalPrior:
    """Prospective venue evidence frozen before the current outcome is opened."""

    available: bool = False
    reliability: float = 0.0
    expected_yield: float = 0.0
    matchup_safety: float = 0.0
    travel_cost: float = 0.0
    recovery_cost: float = 0.0
    support_count: int = 0
    evidence_sha256: str | None = None
    frozen_before_scenario: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool) or not isinstance(
            self.frozen_before_scenario, bool
        ):
            raise PartyDevelopmentFeatureError("venue-prior flags must be boolean")
        for name in (
            "reliability",
            "expected_yield",
            "matchup_safety",
            "travel_cost",
            "recovery_cost",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
            ):
                raise PartyDevelopmentFeatureError(
                    f"venue-prior {name.replace('_', ' ')} must be a finite unit value"
                )
        if type(self.support_count) is not int or self.support_count < 0:  # noqa: E721
            raise PartyDevelopmentFeatureError("venue-prior support count is invalid")
        digest_valid = (
            isinstance(self.evidence_sha256, str)
            and _SHA256.fullmatch(self.evidence_sha256) is not None
        )
        if self.available:
            if (
                not self.frozen_before_scenario
                or self.support_count < 1
                or not digest_valid
            ):
                raise PartyDevelopmentFeatureError(
                    "an available venue prior needs frozen independent evidence"
                )
        elif (
            any(
                float(getattr(self, name)) != 0.0
                for name in (
                    "reliability",
                    "expected_yield",
                    "matchup_safety",
                    "travel_cost",
                    "recovery_cost",
                )
            )
            or self.support_count != 0
            or self.evidence_sha256 is not None
            or self.frozen_before_scenario
        ):
            raise PartyDevelopmentFeatureError(
                "an unavailable venue prior cannot carry measurements"
            )


@dataclass(frozen=True, slots=True)
class PartyDevelopmentCandidate:
    """One completion-aware candidate with no execution identity."""

    candidate_index: int
    features: tuple[float, ...]
    feature_schema_id: str = PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        if type(self.candidate_index) is not int or self.candidate_index < 0:  # noqa: E721
            raise PartyDevelopmentFeatureError("party-development candidate index is invalid")
        if self.feature_schema_id != PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID:
            raise PartyDevelopmentFeatureError(
                "party-development feature schema is unsupported"
            )
        if len(self.features) != len(PARTY_DEVELOPMENT_FEATURE_NAMES):
            raise PartyDevelopmentFeatureError(
                "party-development candidate feature width is invalid"
            )
        vector = np.asarray(self.features, dtype=np.float64)
        if (
            not np.all(np.isfinite(vector))
            or np.any(vector < -1.0)
            or np.any(vector > 1.0)
        ):
            raise PartyDevelopmentFeatureError(
                "party-development candidate features must be normalized"
            )

    def vector(self) -> NDArray[np.float64]:
        return np.asarray(self.features, dtype=np.float64).copy()

    def public_dict(self) -> dict[str, object]:
        return {
            "candidate_index": self.candidate_index,
            "feature_schema_id": self.feature_schema_id,
            "features": dict(
                zip(PARTY_DEVELOPMENT_FEATURE_NAMES, self.features, strict=True)
            ),
        }


@dataclass(frozen=True, slots=True)
class PartyDevelopmentCandidateSet:
    """A variable candidate menu for one explicit completion pressure."""

    kind: TrainingChoiceKind
    goal: PartyDevelopmentGoal
    candidates: tuple[PartyDevelopmentCandidate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TrainingChoiceKind):
            raise PartyDevelopmentFeatureError("party-development choice kind is invalid")
        if not isinstance(self.goal, PartyDevelopmentGoal):
            raise PartyDevelopmentFeatureError("party-development goal is invalid")
        if not self.candidates or tuple(
            item.candidate_index for item in self.candidates
        ) != tuple(range(len(self.candidates))):
            raise PartyDevelopmentFeatureError(
                "party-development candidate indexes must be contiguous"
            )
        kind_index = PARTY_DEVELOPMENT_FEATURE_NAMES.index("choice.trainee")
        expected = float(self.kind is TrainingChoiceKind.TRAINEE)
        if any(item.features[kind_index] != expected for item in self.candidates):
            raise PartyDevelopmentFeatureError(
                "party-development features contradict the choice kind"
            )
        goal_index = PARTY_DEVELOPMENT_FEATURE_NAMES.index(
            f"context.goal.{self.goal.value}"
        )
        if any(
            item.features[goal_index] != 1.0
            or sum(
                item.features[
                    PARTY_DEVELOPMENT_FEATURE_NAMES.index(
                        f"context.goal.{candidate_goal.value}"
                    )
                ]
                == 1.0
                for candidate_goal in PartyDevelopmentGoal
            )
            != 1
            or any(
                item.features[
                    PARTY_DEVELOPMENT_FEATURE_NAMES.index(
                        f"context.goal.{candidate_goal.value}"
                    )
                ]
                not in (0.0, 1.0)
                for candidate_goal in PartyDevelopmentGoal
            )
            for item in self.candidates
        ):
            raise PartyDevelopmentFeatureError(
                "party-development features contradict the declared goal"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-party-development-candidate-set-v2",
            "kind": self.kind.value,
            "goal": self.goal.value,
            "candidates": [item.public_dict() for item in self.candidates],
        }


def augment_training_candidate_set(
    base: TrainingCandidateSet,
    context: PartyDevelopmentContext,
    semantics: tuple[CandidateCompletionSemantics, ...],
    *,
    venue_priors: tuple[VenueOperationalPrior, ...] | None = None,
) -> PartyDevelopmentCandidateSet:
    """Add prospective completion semantics while preserving the exact v1 prefix."""

    if not isinstance(base, TrainingCandidateSet):
        raise TypeError("base must be a TrainingCandidateSet")
    if not isinstance(context, PartyDevelopmentContext):
        raise TypeError("context must be a PartyDevelopmentContext")
    if (
        not isinstance(semantics, tuple)
        or len(semantics) != len(base.candidates)
        or any(not isinstance(item, CandidateCompletionSemantics) for item in semantics)
    ):
        raise PartyDevelopmentFeatureError(
            "completion semantics must match the candidate menu"
        )
    if venue_priors is None:
        priors = tuple(VenueOperationalPrior() for _ in base.candidates)
    else:
        priors = venue_priors
    if (
        not isinstance(priors, tuple)
        or len(priors) != len(base.candidates)
        or any(not isinstance(item, VenueOperationalPrior) for item in priors)
    ):
        raise PartyDevelopmentFeatureError("venue priors must match the candidate menu")
    if base.kind is TrainingChoiceKind.TRAINEE and any(item.available for item in priors):
        raise PartyDevelopmentFeatureError(
            "trainee candidates cannot carry candidate-specific venue priors"
        )

    candidates = tuple(
        PartyDevelopmentCandidate(
            candidate_index=index,
            features=(
                *base_candidate.features,
                *_completion_features(context, candidate_semantics, prior),
            ),
        )
        for index, (base_candidate, candidate_semantics, prior) in enumerate(
            zip(base.candidates, semantics, priors, strict=True)
        )
    )
    return PartyDevelopmentCandidateSet(base.kind, context.goal, candidates)


def _completion_features(
    context: PartyDevelopmentContext,
    semantics: CandidateCompletionSemantics,
    prior: VenueOperationalPrior,
) -> tuple[float, ...]:
    evolution = semantics.evolution
    return (
        *(float(context.goal is goal) for goal in PartyDevelopmentGoal),
        _share(context.below_floor_count, context.party_size),
        _share(context.evolution_needed_count, context.party_size),
        _share(context.registration_needed_count, context.party_size),
        _share(context.living_needed_count, context.party_size),
        _share(context.role_gap_count, context.party_size),
        float(context.registration_completion_ratio),
        float(context.living_completion_ratio),
        float(context.role_coverage_ratio),
        _share(context.healthy_trainable_count, context.party_size),
        _share(context.exhausted_count, context.party_size),
        _share(context.fainted_count, context.party_size),
        float(evolution.required),
        _share(evolution.stages_remaining, MAX_EVOLUTION_STAGES),
        float(evolution.levels_to_next is not None),
        _share(evolution.levels_to_next or 0, 99),
        *(float(evolution.route_kind is kind) for kind in EvolutionRouteKind),
        float(evolution.feasible_now),
        float(semantics.registration_needed),
        float(semantics.living_target_needed),
        float(semantics.living_retention_risk),
        float(semantics.role_needed),
        float(semantics.role_complete),
        float(semantics.emergency_escort_required),
        float(semantics.projected_survival_margin),
        float(prior.available),
        float(prior.reliability),
        float(prior.expected_yield),
        float(prior.matchup_safety),
        float(prior.travel_cost),
        float(prior.recovery_cost),
        _share(prior.support_count, MAX_PRIOR_SUPPORT),
    )


def _share(numerator: int, denominator: int) -> float:
    return min(1.0, max(0.0, numerator / denominator))


__all__ = [
    "CandidateCompletionSemantics",
    "EvolutionRouteKind",
    "EvolutionSemantics",
    "PARTY_DEVELOPMENT_FEATURE_NAMES",
    "PARTY_DEVELOPMENT_FEATURE_SCHEMA_ID",
    "PartyDevelopmentCandidate",
    "PartyDevelopmentCandidateSet",
    "PartyDevelopmentContext",
    "PartyDevelopmentFeatureError",
    "PartyDevelopmentGoal",
    "VenueOperationalPrior",
    "augment_training_candidate_set",
]
