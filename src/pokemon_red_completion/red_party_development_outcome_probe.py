"""Frozen Red venue counterfactual for one bounded evolution objective.

The learner receives portable party and venue features. Species, party slots,
map bindings, and controller sequences remain execution-only bindings.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.party import PartyObservation
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.team_training import BalancedTeamPolicy
from pokemon_red_completion.training_candidate_rank import (
    TrainingCandidate,
    TrainingCandidateSet,
    TrainingChoiceKind,
    project_venue_candidates,
)
from pokemon_red_completion.training_venue import TrainingVenue

RED_PARTY_DEVELOPMENT_SCENARIO_ID = "red-party-development-evolution-venue-v1"
RED_PARTY_DEVELOPMENT_ORDER_RULE = "state-sha256-high-bit-reverse-v1"


class RedPartyDevelopmentProbeError(ValueError):
    """Raised when the venue comparison cannot remain identity-free and exact."""


@dataclass(frozen=True, slots=True)
class BoundedEvolutionVenueQuestion:
    """Two portable venue candidates plus private execution bindings."""

    candidate_set: TrainingCandidateSet
    venue_bindings: tuple[TrainingVenue, TrainingVenue]
    target_slot: int
    source_species_id: int
    final_species_id: int
    initial_state_sha256: str

    def __post_init__(self) -> None:
        if self.candidate_set.kind is not TrainingChoiceKind.VENUE:
            raise RedPartyDevelopmentProbeError("party probe requires venue candidates")
        if len(self.candidate_set.candidates) != 2 or len(self.venue_bindings) != 2:
            raise RedPartyDevelopmentProbeError("party probe requires exactly two venues")
        if self.venue_bindings[0].band.identity == self.venue_bindings[1].band.identity:
            raise RedPartyDevelopmentProbeError("party probe venues must be distinct")
        if type(self.target_slot) is not int or self.target_slot < 1:  # noqa: E721
            raise RedPartyDevelopmentProbeError("party probe target slot is invalid")
        if (
            type(self.source_species_id) is not int  # noqa: E721
            or self.source_species_id <= 0
            or type(self.final_species_id) is not int  # noqa: E721
            or self.final_species_id <= 0
            or self.source_species_id == self.final_species_id
        ):
            raise RedPartyDevelopmentProbeError("party probe evolution binding is invalid")
        if (
            len(self.initial_state_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.initial_state_sha256)
        ):
            raise RedPartyDevelopmentProbeError("party probe state digest is invalid")

    @property
    def ordered_policy_input_sha256(self) -> str:
        return canonical_sha256(self.candidate_set.public_dict())

    def public_catalog(self) -> dict[str, object]:
        """Return the path-, identity-, and action-free prospective question."""

        return {
            "schema": "pokemon-red-party-development-catalog-v1",
            "scenario_id": RED_PARTY_DEVELOPMENT_SCENARIO_ID,
            "initial_state_sha256": self.initial_state_sha256,
            "candidate_count": 2,
            "candidate_order_rule": RED_PARTY_DEVELOPMENT_ORDER_RULE,
            "ordered_policy_input_sha256": self.ordered_policy_input_sha256,
            "choice_kind": self.candidate_set.kind.value,
            "candidate_feature_schema_id": self.candidate_set.candidates[0].feature_schema_id,
            "candidate_feature_values_public": False,
            "same_start": True,
            "same_trainee": True,
            "same_stop_condition": True,
            "stop_condition": "first_verified_level_triggered_evolution",
            "controller_action_labels": 0,
            "teacher_choice_targets": 0,
        }


def build_bounded_evolution_venue_question(
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    venues: tuple[TrainingVenue, TrainingVenue],
    *,
    source_species_id: int,
    final_species_id: int,
    initial_state_sha256: str,
) -> BoundedEvolutionVenueQuestion:
    """Build and digest-order two safe venue candidates for one trainee."""

    if (
        len(initial_state_sha256) != 64
        or any(character not in "0123456789abcdef" for character in initial_state_sha256)
    ):
        raise RedPartyDevelopmentProbeError("party probe state digest is invalid")
    trainee = next(
        (member for member in party.members if member.species_id == source_species_id),
        None,
    )
    if trainee is None:
        raise RedPartyDevelopmentProbeError("party probe source species is absent")
    projected = project_venue_candidates(
        party,
        policy,
        trainee,
        tuple(venue.band for venue in venues),
    )
    if projected is None:
        raise RedPartyDevelopmentProbeError("party probe has no genuine venue choice")
    _heuristic_venue, _heuristic_index, natural = projected
    if len(natural.candidates) != 2:
        raise RedPartyDevelopmentProbeError(
            "party probe requires both frozen venues to be eligible"
        )
    reverse = bool(int(initial_state_sha256[:2], 16) & 0x80)
    indexes = (1, 0) if reverse else (0, 1)
    candidates = tuple(
        TrainingCandidate(
            candidate_index=new_index,
            features=natural.candidates[natural_index].features,
        )
        for new_index, natural_index in enumerate(indexes)
    )
    bindings = (venues[indexes[0]], venues[indexes[1]])
    return BoundedEvolutionVenueQuestion(
        candidate_set=TrainingCandidateSet(TrainingChoiceKind.VENUE, candidates),
        venue_bindings=bindings,
        target_slot=trainee.slot,
        source_species_id=source_species_id,
        final_species_id=final_species_id,
        initial_state_sha256=initial_state_sha256,
    )


__all__ = [
    "RED_PARTY_DEVELOPMENT_ORDER_RULE",
    "RED_PARTY_DEVELOPMENT_SCENARIO_ID",
    "BoundedEvolutionVenueQuestion",
    "RedPartyDevelopmentProbeError",
    "build_bounded_evolution_venue_question",
]
