"""Identity-free candidate ranking for trainee and training-venue choices.

The first training-control policy proved that a model can sit in the live
execution path, but its candidate masks fully determined every observed label.
This module exposes the two choices the teacher still makes before that seam:
which party member to develop and which viable encounter band to use.  Each
candidate is projected independently, so a future scorer can be permutation
equivariant and cannot memorize species, party slots, or area names.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.party import (
    MAX_LEVEL,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    member_can_train_at,
    member_needs_training,
    training_safety_ceiling,
)

TRAINING_CANDIDATE_FEATURE_SCHEMA_ID = "pokemon.core.training.candidate-ranker.v1"
TRAINING_CANDIDATE_FEATURE_NAMES = (
    "choice.trainee",
    "party.fill_ratio",
    "party.minimum_level",
    "party.average_level",
    "party.level_spread",
    "policy.minimum_level",
    "policy.maximum_level_spread",
    "candidate.level",
    "candidate.level_floor_deficit",
    "candidate.relative_to_party_minimum",
    "candidate.relative_to_party_average",
    "candidate.hp_ratio",
    "candidate.status_healthy",
    "candidate.can_battle",
    "candidate.attack_pp",
    "candidate.is_lead",
    "candidate.viable_venue_share",
    "candidate.best_fightable_share",
    "venue.minimum_level",
    "venue.maximum_level",
    "venue.rare_maximum_level",
    "venue.band_width",
    "venue.fightable_share",
    "venue.has_nearby_healer",
    "venue.has_rare_ceiling",
    "venue.relative_minimum_to_trainee",
    "venue.relative_maximum_to_trainee",
)


class TrainingCandidateRankError(ValueError):
    """Raised when candidate-ranking supervision is malformed."""


class TrainingChoiceKind(StrEnum):
    """The two strategic selections still owned by the training teacher."""

    TRAINEE = "trainee"
    VENUE = "venue"


@dataclass(frozen=True, slots=True)
class TrainingCandidate:
    """One ephemeral candidate represented only by portable semantics."""

    candidate_index: int
    features: tuple[float, ...]
    feature_schema_id: str = TRAINING_CANDIDATE_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        if type(self.candidate_index) is not int or self.candidate_index < 0:  # noqa: E721
            raise TrainingCandidateRankError("candidate index is invalid")
        if self.feature_schema_id != TRAINING_CANDIDATE_FEATURE_SCHEMA_ID:
            raise TrainingCandidateRankError("candidate feature schema is unsupported")
        if len(self.features) != len(TRAINING_CANDIDATE_FEATURE_NAMES):
            raise TrainingCandidateRankError("candidate feature vector has the wrong width")
        values = np.asarray(self.features, dtype=np.float64)
        if not np.all(np.isfinite(values)) or np.any(values < -1.0) or np.any(values > 1.0):
            raise TrainingCandidateRankError(
                "candidate features must be finite and normalized"
            )

    def vector(self) -> NDArray[np.float64]:
        """Return a detached numeric vector for a shared candidate scorer."""

        return np.asarray(self.features, dtype=np.float64).copy()

    def public_dict(self) -> dict[str, object]:
        """Serialize without species, move, slot, map, or venue identity."""

        return {
            "candidate_index": self.candidate_index,
            "feature_schema_id": self.feature_schema_id,
            "features": dict(
                zip(TRAINING_CANDIDATE_FEATURE_NAMES, self.features, strict=True)
            ),
        }


@dataclass(frozen=True, slots=True)
class TrainingCandidateSet:
    """A variable-sized choice set scored one candidate at a time."""

    kind: TrainingChoiceKind
    candidates: tuple[TrainingCandidate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TrainingChoiceKind):
            raise TrainingCandidateRankError("candidate-set kind is invalid")
        if not self.candidates:
            raise TrainingCandidateRankError("candidate set cannot be empty")
        if tuple(candidate.candidate_index for candidate in self.candidates) != tuple(
            range(len(self.candidates))
        ):
            raise TrainingCandidateRankError("candidate indexes must be contiguous")
        expected_kind = float(self.kind is TrainingChoiceKind.TRAINEE)
        kind_index = TRAINING_CANDIDATE_FEATURE_NAMES.index("choice.trainee")
        if any(candidate.features[kind_index] != expected_kind for candidate in self.candidates):
            raise TrainingCandidateRankError("candidate features contradict the choice kind")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-training-candidate-set-v1",
            "kind": self.kind.value,
            "candidates": [candidate.public_dict() for candidate in self.candidates],
        }


@dataclass(frozen=True, slots=True)
class TrainingCandidateDecision:
    """One teacher label over an identity-free variable-sized candidate set."""

    decision_index: int
    selected_candidate_index: int
    observation: TrainingCandidateSet
    reason: str

    def __post_init__(self) -> None:
        if type(self.decision_index) is not int or self.decision_index < 0:  # noqa: E721
            raise TrainingCandidateRankError("decision index is invalid")
        if self.selected_candidate_index not in range(len(self.observation.candidates)):
            raise TrainingCandidateRankError("selected candidate index is invalid")
        if not self.reason.strip():
            raise TrainingCandidateRankError("candidate decision needs a reason")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-training-candidate-decision-v1",
            "decision_index": self.decision_index,
            "selected_candidate_index": self.selected_candidate_index,
            "reason": self.reason,
            "observation": self.observation.public_dict(),
        }


@dataclass(slots=True)
class TrainingCandidateDecisionRecorder:
    """Retain strategic state transitions instead of repeated identical polls.

    The training loop recomputes trainee and venue choices before many mechanic
    actions. Long walks can therefore emit the exact same choice thousands of
    times. Keeping those duplicates would make route duration, rather than
    strategic choice, dominate both storage and metrics. This recorder keeps
    the first decision and every later change independently for each choice
    kind, while reporting the full observed/retained denominator.
    """

    _decisions: list[TrainingCandidateDecision] = field(default_factory=list)
    _last_by_kind: dict[TrainingChoiceKind, tuple[object, ...]] = field(
        default_factory=dict
    )
    observed_decisions: int = 0

    def observe(self, decision: TrainingCandidateDecision) -> bool:
        """Record a changed choice state and return whether it was retained."""

        self.observed_decisions += 1
        signature = (
            decision.selected_candidate_index,
            decision.reason,
            tuple(
                candidate.features for candidate in decision.observation.candidates
            ),
        )
        kind = decision.observation.kind
        if self._last_by_kind.get(kind) == signature:
            return False
        self._last_by_kind[kind] = signature
        self._decisions.append(
            replace(decision, decision_index=len(self._decisions))
        )
        return True

    @property
    def decisions(self) -> tuple[TrainingCandidateDecision, ...]:
        return tuple(self._decisions)

    def public_summary(self) -> dict[str, object]:
        retained = len(self._decisions)
        return {
            "method": "retain_first_and_per_kind_state_transitions",
            "observed_decisions": self.observed_decisions,
            "retained_decisions": retained,
            "consecutive_duplicate_decisions_removed": (
                self.observed_decisions - retained
            ),
        }


def project_trainee_candidates(
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    areas: tuple[GrindingArea, ...],
) -> tuple[PartyMemberObservation, int, TrainingCandidateSet] | None:
    """Project every trainable below-floor member and label the teacher choice.

    The returned member is an execution binding only; it is never serialized.
    The public candidate index is positional linkage and is deliberately absent
    from the feature vector.
    """

    eligible = _eligible_trainees(party, policy, areas)
    if not eligible:
        return None
    candidates = tuple(
        TrainingCandidate(
            index,
            _candidate_features(
                kind=TrainingChoiceKind.TRAINEE,
                party=party,
                policy=policy,
                trainee=member,
                areas=areas,
                venue=None,
            ),
        )
        for index, member in enumerate(eligible)
    )
    observation = TrainingCandidateSet(TrainingChoiceKind.TRAINEE, candidates)
    weakest_level = min(member.level for member in eligible)
    weakest = tuple(member for member in eligible if member.level == weakest_level)
    if len(weakest) > 1:
        leads = tuple(member for member in weakest if member.slot == 1)
        if len(leads) != 1:
            # The teacher would break this tie by an unobserved party-position
            # identity. It is not valid candidate-ranking supervision.
            return None
        selected = leads[0]
    else:
        selected = weakest[0]
    selected_index = eligible.index(selected)
    return selected, selected_index, observation


def project_venue_candidates(
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    trainee: PartyMemberObservation,
    areas: tuple[GrindingArea, ...],
    *,
    require_healer: bool = True,
) -> tuple[GrindingArea, int, TrainingCandidateSet] | None:
    """Project every safe venue and label the teacher's efficiency choice."""

    eligible = _eligible_venues(
        trainee,
        policy,
        areas,
        require_healer=require_healer,
    )
    if not eligible:
        return None
    candidates = tuple(
        TrainingCandidate(
            index,
            _candidate_features(
                kind=TrainingChoiceKind.VENUE,
                party=party,
                policy=policy,
                trainee=trainee,
                areas=areas,
                venue=area,
            ),
        )
        for index, area in enumerate(eligible)
    )
    observation = TrainingCandidateSet(TrainingChoiceKind.VENUE, candidates)
    best_minimum = max(area.minimum_encounter_level for area in eligible)
    best = tuple(area for area in eligible if area.minimum_encounter_level == best_minimum)
    if len(best) != 1:
        # The current teacher breaks this tie by area identity, which is
        # intentionally absent from the portable observation.
        return None
    selected = best[0]
    selected_index = eligible.index(selected)
    return selected, selected_index, observation


def bind_trainee_candidate(
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    areas: tuple[GrindingArea, ...],
    candidate_index: int,
) -> PartyMemberObservation:
    """Resolve one ephemeral model index against the exact live trainee set."""

    eligible = _eligible_trainees(party, policy, areas)
    if type(candidate_index) is not int or candidate_index not in range(len(eligible)):  # noqa: E721
        raise TrainingCandidateRankError("trainee candidate binding index is invalid")
    return eligible[candidate_index]


def bind_venue_candidate(
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    trainee: PartyMemberObservation,
    areas: tuple[GrindingArea, ...],
    candidate_index: int,
    *,
    require_healer: bool = True,
) -> GrindingArea:
    """Resolve one ephemeral model index against the exact live venue set."""

    del party  # kept in the public binding signature for projector symmetry
    eligible = _eligible_venues(
        trainee,
        policy,
        areas,
        require_healer=require_healer,
    )
    if type(candidate_index) is not int or candidate_index not in range(len(eligible)):  # noqa: E721
        raise TrainingCandidateRankError("venue candidate binding index is invalid")
    return eligible[candidate_index]


def _eligible_trainees(
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    areas: tuple[GrindingArea, ...],
) -> tuple[PartyMemberObservation, ...]:
    return tuple(
        member
        for member in party.members
        if member_needs_training(member, policy)
        and member.is_trainable
        and any(member_can_train_at(member, policy, area) for area in areas)
    )


def _eligible_venues(
    trainee: PartyMemberObservation,
    policy: BalancedTeamPolicy,
    areas: tuple[GrindingArea, ...],
    *,
    require_healer: bool,
) -> tuple[GrindingArea, ...]:
    return tuple(
        area
        for area in areas
        if member_can_train_at(trainee, policy, area)
        and (area.has_nearby_healer or not require_healer)
    )


def _candidate_features(
    *,
    kind: TrainingChoiceKind,
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    trainee: PartyMemberObservation,
    areas: tuple[GrindingArea, ...],
    venue: GrindingArea | None,
) -> tuple[float, ...]:
    minimum = party.minimum_level or 0
    average = party.average_level or 0.0
    spread = party.level_spread or 0
    viable = tuple(area for area in areas if member_can_train_at(trainee, policy, area))
    fightable = tuple(
        area.fightable_share(training_safety_ceiling(trainee, policy)) for area in areas
    )
    typical_maximum = venue.maximum_encounter_level if venue is not None else 0
    rare_maximum = venue.worst_case_encounter_level if venue is not None else 0
    values = (
        float(kind is TrainingChoiceKind.TRAINEE),
        _ratio(party.size, policy.required_size),
        _ratio(minimum, MAX_LEVEL),
        _ratio_float(average, MAX_LEVEL),
        _ratio(spread, MAX_LEVEL - 1),
        _ratio(policy.minimum_level, MAX_LEVEL),
        _ratio(policy.maximum_level_spread, MAX_LEVEL - 1),
        _ratio(trainee.level, MAX_LEVEL),
        _ratio(max(0, policy.minimum_level - trainee.level), MAX_LEVEL),
        _ratio(trainee.level - minimum, MAX_LEVEL - 1),
        _signed_ratio(trainee.level - average, MAX_LEVEL - 1),
        trainee.hp_ratio,
        float(not trainee.is_fainted and trainee.status is StatusCondition.HEALTHY),
        float(trainee.can_battle),
        _ratio(trainee.total_pp, 256),
        float(trainee.slot == 1),
        _ratio(len(viable), max(1, len(areas))),
        max(fightable, default=0.0),
        _ratio(venue.minimum_encounter_level if venue is not None else 0, MAX_LEVEL),
        _ratio(typical_maximum, MAX_LEVEL),
        _ratio(rare_maximum, MAX_LEVEL),
        _ratio(
            typical_maximum - venue.minimum_encounter_level if venue is not None else 0,
            MAX_LEVEL - 1,
        ),
        venue.fightable_share(training_safety_ceiling(trainee, policy))
        if venue is not None
        else 0.0,
        float(venue is not None and venue.has_nearby_healer),
        float(venue is not None and venue.has_rare_ceiling),
        _signed_ratio(
            venue.minimum_encounter_level - trainee.level if venue is not None else 0,
            MAX_LEVEL - 1,
        ),
        _signed_ratio(typical_maximum - trainee.level, MAX_LEVEL - 1),
    )
    return values


def _ratio(numerator: int, denominator: int) -> float:
    return min(1.0, max(0.0, numerator / denominator))


def _ratio_float(numerator: float, denominator: int) -> float:
    return min(1.0, max(0.0, numerator / denominator))


def _signed_ratio(numerator: float, denominator: int) -> float:
    return min(1.0, max(-1.0, numerator / denominator))
