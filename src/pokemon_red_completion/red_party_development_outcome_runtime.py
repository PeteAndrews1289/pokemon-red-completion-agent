"""Red execution bindings for the completion-aware party outcome campaign.

The learner-facing catalog deliberately contains no species, slot, map, or
controller identity.  A live counterfactual still needs those facts, so this
module reconstructs exactly one private candidate binding and applies hard
action/frame budgets without changing the frozen feature menu.

Nothing here selects a candidate.  The assignment is fixed by the prospective
campaign plan, and every validation happens before controller input.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pokemon_red_completion.actions import MacroAction
from pokemon_red_completion.executor import FrameBudgetController
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.party import PartyMemberObservation, PartyObservation
from pokemon_red_completion.party_development_adapter import BoundPartyDevelopmentMenu
from pokemon_red_completion.party_development_frozen_catalog import (
    PartyDevelopmentFrozenQuestion,
)
from pokemon_red_completion.party_development_outcome_campaign import (
    PartyDevelopmentOutcomeDose,
    PartyDevelopmentOutcomeTrialAssignment,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import red_internal_species_number
from pokemon_red_completion.red_team_training import FixedPartyTrainingDose
from pokemon_red_completion.team_training import GrindingArea
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind
from pokemon_red_completion.training_venue import TrainingVenue


class RedPartyDevelopmentOutcomeRuntimeError(RuntimeError):
    """Raised before a frozen party candidate can be executed ambiguously."""


class _ActionExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


@dataclass(frozen=True, slots=True)
class RedPartyDevelopmentTrialBinding:
    """One exact private trainee/venue pair for a frozen candidate row."""

    assignment: PartyDevelopmentOutcomeTrialAssignment
    candidate_index: int
    target_slot: int
    target_species_id: int
    trainee_species_lineage: tuple[int, ...]
    venue_identity: tuple[str, tuple[str, ...]]
    training_venue: TrainingVenue
    fixed_dose: FixedPartyTrainingDose

    def __post_init__(self) -> None:
        if not isinstance(
            self.assignment, PartyDevelopmentOutcomeTrialAssignment
        ):
            raise RedPartyDevelopmentOutcomeRuntimeError(
                "Red party trial binding needs a typed campaign assignment"
            )
        if (
            self.candidate_index != self.assignment.candidate_index
            or type(self.target_slot) is not int  # noqa: E721
            or self.target_slot < 1
            or type(self.target_species_id) is not int  # noqa: E721
            or self.target_species_id <= 0
            or not isinstance(self.training_venue, TrainingVenue)
            or self.training_venue.band.identity != self.venue_identity
            or self.fixed_dose.trainee_species_lineage
            != self.trainee_species_lineage
            or self.fixed_dose.venue_identity != self.venue_identity
        ):
            raise RedPartyDevelopmentOutcomeRuntimeError(
                "Red party trial execution binding is internally inconsistent"
            )

    def public_summary(self) -> dict[str, object]:
        """Expose only bound counts and digests, never private execution values."""

        return {
            "schema": "pokemon.red.party-development-outcome-trial-preflight.v1",
            "ordinal": self.assignment.ordinal,
            "partition": self.assignment.partition.value,
            "kind": self.assignment.kind.value,
            "goal": self.assignment.goal.value,
            "candidate_index": self.assignment.candidate_index,
            "assignment_sha256": self.assignment.assignment_sha256,
            "candidate_sha256": self.assignment.candidate_sha256,
            "trainee_lineage_size": len(self.trainee_species_lineage),
            "fixed_dose_sha256": canonical_sha256(
                {
                    "trainee_lineage_size": len(self.trainee_species_lineage),
                    "venue_identity_sha256": canonical_sha256(
                        {
                            "area": self.venue_identity[0],
                            "conditions": list(self.venue_identity[1]),
                        }
                    ),
                    "completed_battles": self.fixed_dose.completed_battles,
                }
            ),
            "controller_actions": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "private_binding_values_public": False,
            "private_path_fields": 0,
        }


def bind_red_party_development_outcome_trial(
    question: PartyDevelopmentFrozenQuestion,
    menu: (
        BoundPartyDevelopmentMenu[PartyMemberObservation]
        | BoundPartyDevelopmentMenu[GrindingArea]
    ),
    assignment: PartyDevelopmentOutcomeTrialAssignment,
    *,
    party: PartyObservation,
    venue_question_trainee: PartyMemberObservation | None,
    training_venues: Sequence[TrainingVenue],
    evolutions: Mapping[int, tuple[Evolution, ...]],
    internal_to_national: Mapping[int, int],
    dose: PartyDevelopmentOutcomeDose,
) -> RedPartyDevelopmentTrialBinding:
    """Resolve one already-assigned row into fixed Red mechanics.

    The candidate/menu hashes, initial state, partition, goal, and availability
    are rechecked before any species or venue binding is returned.  An automatic
    level-evolution lineage is used so a Pokémon that evolves during the four
    battles remains the same specimen without making stone/trade branches
    falsely ambiguous.
    """

    if not isinstance(question, PartyDevelopmentFrozenQuestion):
        raise TypeError("question must be a PartyDevelopmentFrozenQuestion")
    if not isinstance(menu, BoundPartyDevelopmentMenu):
        raise TypeError("menu must be a BoundPartyDevelopmentMenu")
    if not isinstance(assignment, PartyDevelopmentOutcomeTrialAssignment):
        raise TypeError("assignment must be a PartyDevelopmentOutcomeTrialAssignment")
    if not isinstance(party, PartyObservation):
        raise TypeError("party must be a PartyObservation")
    if not isinstance(dose, PartyDevelopmentOutcomeDose):
        raise TypeError("dose must be a PartyDevelopmentOutcomeDose")
    question.binding.require_candidate_set(menu.candidate_set)
    if (
        menu.candidate_set != question.candidate_set
        or assignment.scenario_id != question.scenario_id
        or assignment.root_lineage_id != question.binding.root_lineage_id
        or assignment.initial_state_sha256 != question.binding.initial_state_sha256
        or assignment.partition is not question.binding.partition
        or assignment.kind is not question.binding.kind
        or assignment.goal is not question.binding.goal
        or assignment.binding_sha256 != question.binding.binding_sha256
        or assignment.candidate_index not in range(len(menu.bindings))
        or assignment.candidate_index
        not in range(len(question.binding.candidate_available))
    ):
        raise RedPartyDevelopmentOutcomeRuntimeError(
            "Red party assignment differs from its frozen question"
        )
    index = assignment.candidate_index
    candidate = question.candidate_set.candidates[index]
    if (
        not question.binding.candidate_available[index]
        or not menu.candidate_available[index]
        or canonical_sha256(candidate.public_dict()) != assignment.candidate_sha256
        or question.binding.candidate_feature_sha256[index]
        != assignment.candidate_feature_sha256
    ):
        raise RedPartyDevelopmentOutcomeRuntimeError(
            "Red party assignment is not one available frozen candidate"
        )

    target: PartyMemberObservation
    venue_area: GrindingArea
    if assignment.kind is TrainingChoiceKind.TRAINEE:
        selected_target = menu.bindings[index]
        shared_venue = menu.shared_venue
        if (
            not isinstance(selected_target, PartyMemberObservation)
            or not isinstance(shared_venue, GrindingArea)
            or venue_question_trainee is not None
        ):
            raise RedPartyDevelopmentOutcomeRuntimeError(
                "Red trainee question lost its selected member or shared venue"
            )
        target = selected_target
        venue_area = shared_venue
    else:
        selected_venue = menu.bindings[index]
        if not isinstance(venue_question_trainee, PartyMemberObservation) or not isinstance(
            selected_venue, GrindingArea
        ):
            raise RedPartyDevelopmentOutcomeRuntimeError(
                "Red venue question lost its fixed trainee or selected venue"
            )
        target = venue_question_trainee
        venue_area = selected_venue
    observed_target = party.member_in_slot(target.slot)
    if observed_target != target:
        raise RedPartyDevelopmentOutcomeRuntimeError(
            "Red party trial target differs from the cloned starting party"
        )
    venues = tuple(
        item for item in training_venues if item.band.identity == venue_area.identity
    )
    if len(venues) != 1:
        raise RedPartyDevelopmentOutcomeRuntimeError(
            "Red party trial venue is not uniquely executable"
        )
    lineage = automatic_level_evolution_lineage(
        target.species_id,
        evolutions=evolutions,
        internal_to_national=internal_to_national,
    )
    if (
        sum(member.species_id in lineage for member in party.members) != 1
        or target.species_id not in lineage
    ):
        raise RedPartyDevelopmentOutcomeRuntimeError(
            "Red party trial trainee lineage is not unique in the cloned party"
        )
    fixed_dose = FixedPartyTrainingDose(
        trainee_species_lineage=lineage,
        venue_identity=venue_area.identity,
        completed_battles=dose.completed_battles,
    )
    return RedPartyDevelopmentTrialBinding(
        assignment=assignment,
        candidate_index=index,
        target_slot=target.slot,
        target_species_id=target.species_id,
        trainee_species_lineage=lineage,
        venue_identity=venue_area.identity,
        training_venue=venues[0],
        fixed_dose=fixed_dose,
    )


def automatic_level_evolution_lineage(
    internal_species_id: int,
    *,
    evolutions: Mapping[int, tuple[Evolution, ...]],
    internal_to_national: Mapping[int, int],
) -> tuple[int, ...]:
    """Return the current internal species plus automatic level descendants."""

    try:
        mapping_is_red = bool(internal_to_national) and all(
            type(internal) is int  # noqa: E721
            and type(national) is int  # noqa: E721
            and red_internal_species_number(internal) == national
            for internal, national in internal_to_national.items()
        )
    except ValueError:
        mapping_is_red = False
    if (
        type(internal_species_id) is not int  # noqa: E721
        or internal_species_id not in internal_to_national
        or not mapping_is_red
    ):
        raise RedPartyDevelopmentOutcomeRuntimeError(
            "Red party trial species mapping is invalid"
        )
    reverse = {national: internal for internal, national in internal_to_national.items()}
    if len(reverse) != len(internal_to_national):
        raise RedPartyDevelopmentOutcomeRuntimeError(
            "Red cartridge species mapping is not one-to-one"
        )
    current = internal_to_national[internal_species_id]
    visited: set[int] = set()
    frontier = [current]
    while frontier:
        species = frontier.pop()
        if species in visited:
            continue
        visited.add(species)
        frontier.extend(
            step.to_species
            for step in evolutions.get(species, ())
            if step.method is EvolutionMethod.LEVEL
        )
    try:
        lineage = tuple(
            sorted(reverse[national] for national in visited)
        )
    except KeyError as error:
        raise RedPartyDevelopmentOutcomeRuntimeError(
            "Red evolution lineage contains an unmapped species"
        ) from error
    if internal_species_id not in lineage:
        raise RedPartyDevelopmentOutcomeRuntimeError(
            "Red evolution lineage lost its starting species"
        )
    return lineage


class FrameBudgetEmulator(FrameBudgetController):
    """Campaign-typed view of the executor-owned frame-budget controller."""

    def __init__(self, delegate: Any, *, maximum_frames: int) -> None:
        super().__init__(
            delegate,
            maximum_frames=maximum_frames,
            error_type=RedPartyDevelopmentOutcomeRuntimeError,
            error_message="Red party trial exhausted its hard frame budget",
        )


class BoundedActionExecutor:
    """Count actions and refuse before an action can exceed its hard budget."""

    __slots__ = ("_delegate", "_maximum_actions", "actions_executed")

    def __init__(self, delegate: _ActionExecutor, *, maximum_actions: int) -> None:
        if type(maximum_actions) is not int or maximum_actions <= 0:  # noqa: E721
            raise ValueError("maximum_actions must be a positive integer")
        self._delegate = delegate
        self._maximum_actions = maximum_actions
        self.actions_executed = 0

    def execute(self, action: MacroAction) -> object:
        if self.actions_executed >= self._maximum_actions:
            raise RedPartyDevelopmentOutcomeRuntimeError(
                "Red party trial exhausted its hard controller-action budget"
            )
        result = self._delegate.execute(action)
        self.actions_executed += 1
        return result


__all__ = [
    "BoundedActionExecutor",
    "FrameBudgetEmulator",
    "RedPartyDevelopmentOutcomeRuntimeError",
    "RedPartyDevelopmentTrialBinding",
    "automatic_level_evolution_lineage",
    "bind_red_party_development_outcome_trial",
]
