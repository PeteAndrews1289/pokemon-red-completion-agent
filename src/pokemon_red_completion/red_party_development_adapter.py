"""Read-only Pokémon Red projection for party-development questions.

The shared party-development adapter deliberately knows nothing about Red.
This module supplies the narrow title adapter that was still missing: it turns
one already-coherent :class:`RedGoalObservation` into the exact semantic
snapshot used by the learner, derives completion and evolution facts from
cartridge data, and preflights one reserved question without accepting an
executor or producing a controller action.

Red species, item, party-slot, and venue identities remain private bindings.
Only the title-neutral candidate rows and their authenticated digests cross the
learner boundary.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.collection import (
    CollectionContract,
    CollectionLocation,
    summarize_collection,
)
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.party import PartyMemberObservation, StatusCondition
from pokemon_red_completion.party_development_adapter import (
    BoundPartyDevelopmentMenu,
    PartyDevelopmentMemberProfile,
    PartyDevelopmentSemanticSnapshot,
)
from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentProspectiveBinding,
)
from pokemon_red_completion.party_development_question_reservations import (
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservation,
)
from pokemon_red_completion.party_development_rank import (
    EvolutionRouteKind,
    EvolutionSemantics,
)
from pokemon_red_completion.party_development_venue_priors import (
    PartyDevelopmentVenuePriorRegistry,
)
from pokemon_red_completion.red_collection import (
    RED_SOLO_COLLECTION_CONTRACT,
    red_internal_species_number,
    red_species_number,
    red_species_ref,
)
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_party import RED_BALANCED_ROSTER, party_observation_from_raw
from pokemon_red_completion.team_training import (
    MINIMUM_FIGHTABLE_SHARE,
    BalancedTeamPolicy,
    GrindingArea,
    TeamRosterPlan,
    member_can_train_at,
    training_safety_ceiling,
)
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind

RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY = BalancedTeamPolicy(
    minimum_level=60,
    maximum_level_spread=5,
    required_size=6,
    retreat_hp_ratio=0.45,
    reserve_total_pp=2,
    safe_lead_level=42,
    max_enemy_level_delta=0,
    minimum_direct_level_advantage=5,
    max_battles=200,
    max_steps=20_000,
    max_healing_trips=50,
    max_faints=0,
)


class RedPartyDevelopmentAdapterError(ValueError):
    """Raised when Red state cannot support an honest prospective question."""


@dataclass(frozen=True, slots=True)
class RedPartyDevelopmentQuestionPreflight:
    """One in-memory, action-free candidate binding ready for catalog freeze."""

    reservation: PartyDevelopmentQuestionReservation
    source_root_lineage_id: str
    snapshot: PartyDevelopmentSemanticSnapshot
    menu: (
        BoundPartyDevelopmentMenu[PartyMemberObservation]
        | BoundPartyDevelopmentMenu[GrindingArea]
    )
    binding: PartyDevelopmentProspectiveBinding

    def __post_init__(self) -> None:
        reservation = self.reservation
        source_root_lineage_id = self.source_root_lineage_id
        snapshot = self.snapshot
        menu = self.menu
        binding = self.binding
        if not isinstance(reservation, PartyDevelopmentQuestionReservation):
            raise RedPartyDevelopmentAdapterError(
                "Red party preflight needs a typed reservation"
            )
        if not isinstance(snapshot, PartyDevelopmentSemanticSnapshot):
            raise RedPartyDevelopmentAdapterError(
                "Red party preflight needs a typed semantic snapshot"
            )
        if not isinstance(menu, BoundPartyDevelopmentMenu):
            raise RedPartyDevelopmentAdapterError(
                "Red party preflight needs a bound candidate menu"
            )
        if not isinstance(binding, PartyDevelopmentProspectiveBinding):
            raise RedPartyDevelopmentAdapterError(
                "Red party preflight needs a prospective binding"
            )
        expected_binding = snapshot.freeze_binding(
            menu,
            scenario_id=reservation.scenario_id,
        )
        if (
            not isinstance(source_root_lineage_id, str)
            or snapshot.root_lineage_id != source_root_lineage_id
            or snapshot.initial_state_sha256 != reservation.source_state_sha256
            or snapshot.partition is not reservation.partition
            or snapshot.goal is not reservation.goal
            or menu.semantic_snapshot_sha256 != snapshot.semantic_snapshot_sha256
            or menu.candidate_set.kind is not reservation.kind
            or binding.scenario_id != reservation.scenario_id
            or binding.root_lineage_id != source_root_lineage_id
            or binding.initial_state_sha256 != reservation.source_state_sha256
            or binding.partition is not reservation.partition
            or binding.kind is not reservation.kind
            or binding.goal is not reservation.goal
            or binding.semantic_snapshot_sha256 != snapshot.semantic_snapshot_sha256
            or len(binding.candidate_feature_sha256)
            != len(menu.candidate_set.candidates)
            or binding.candidate_available != menu.candidate_available
            or binding.candidate_unavailable_reasons
            != menu.candidate_unavailable_reasons
            or binding != expected_binding
        ):
            raise RedPartyDevelopmentAdapterError(
                "Red party preflight differs from its reserved question"
            )

    def public_dict(self) -> dict[str, object]:
        """Return a path-free readiness summary, never the private bindings."""

        reason_counts = Counter(
            reason.value
            for reason in self.binding.candidate_unavailable_reasons
            if reason is not None
        )
        return {
            "schema": "pokemon.red.party-development-question-preflight.v1",
            "scenario_id": self.binding.scenario_id,
            "partition": self.binding.partition.value,
            "kind": self.binding.kind.value,
            "goal": self.binding.goal.value,
            "semantic_snapshot_sha256": self.binding.semantic_snapshot_sha256,
            "candidate_menu_sha256": self.binding.candidate_menu_sha256,
            "binding_sha256": self.binding.binding_sha256,
            "candidate_count": len(self.binding.candidate_feature_sha256),
            "available_candidate_count": sum(self.binding.candidate_available),
            "unavailable_reason_counts": dict(sorted(reason_counts.items())),
            "shared_venue_prior_present": (
                self.binding.shared_venue_prior_evidence_sha256 is not None
            ),
            "candidate_venue_prior_count": sum(
                value is not None
                for value in self.binding.venue_prior_evidence_sha256
            ),
            "ready_to_freeze": True,
            "actions_executed": 0,
            "teacher_queries": 0,
            "model_predictions": 0,
            "outcomes_opened": 0,
            "private_binding_values_public": False,
            "private_path_fields": 0,
        }


def build_red_party_development_snapshot(
    reservation: PartyDevelopmentQuestionReservation,
    *,
    source_root_lineage_id: str,
    observation: RedGoalObservation,
    evolutions: Mapping[int, tuple[Evolution, ...]],
    policy: BalancedTeamPolicy,
    areas: tuple[GrindingArea, ...],
    venue_prior_registry: PartyDevelopmentVenuePriorRegistry,
    venue_operational_contract_sha256: tuple[str, ...],
    source_commit: str,
    source_bundle_sha256: str,
    collection_contract: CollectionContract = RED_SOLO_COLLECTION_CONTRACT,
    roster: TeamRosterPlan = RED_BALANCED_ROSTER,
    trade_available: bool = False,
    active_conditions: tuple[str, ...] = (),
) -> PartyDevelopmentSemanticSnapshot:
    """Derive the shared snapshot from one coherent, action-free Red read."""

    if not isinstance(reservation, PartyDevelopmentQuestionReservation):
        raise TypeError("reservation must be a PartyDevelopmentQuestionReservation")
    if not isinstance(observation, RedGoalObservation):
        raise TypeError("observation must be a RedGoalObservation")
    if not isinstance(policy, BalancedTeamPolicy):
        raise TypeError("policy must be a BalancedTeamPolicy")
    if not isinstance(venue_prior_registry, PartyDevelopmentVenuePriorRegistry):
        raise TypeError(
            "venue_prior_registry must be a PartyDevelopmentVenuePriorRegistry"
        )
    if not isinstance(collection_contract, CollectionContract):
        raise TypeError("collection_contract must be a CollectionContract")
    if not isinstance(roster, TeamRosterPlan):
        raise TypeError("roster must be a TeamRosterPlan")
    if not isinstance(trade_available, bool):
        raise TypeError("trade_available must be boolean")
    if reservation.preparation is not PartyDevelopmentContextPreparation.NONE:
        raise RedPartyDevelopmentAdapterError(
            "PP-prepared reservations require a newly authenticated post-materialization "
            "reservation before menu preflight"
        )
    if (
        not isinstance(areas, tuple)
        or not areas
        or any(not isinstance(area, GrindingArea) for area in areas)
    ):
        raise RedPartyDevelopmentAdapterError(
            "Red party snapshot needs typed training areas"
        )
    if (
        not observation.raw.game_started
        or observation.raw.battle_state != 0
        or not observation.input_ready
    ):
        raise RedPartyDevelopmentAdapterError(
            "Red party snapshot requires stable ready overworld control"
        )
    if observation.raw.bag_items is None:
        raise RedPartyDevelopmentAdapterError(
            "Red party snapshot requires a complete bag observation"
        )
    _require_party_matches_raw(observation)
    _require_collection_matches_party(observation)
    _require_evolution_graph(evolutions)

    collection = observation.collection_observation
    owned = set(collection.owned_species)
    specimen_counts = Counter(item.species_ref for item in collection.specimens)
    living_targets = set(collection_contract.resolved_living_target_species)
    registration_targets = set(collection_contract.target_species)
    missing_registration = {
        red_species_number(item) for item in registration_targets - owned
    }
    missing_living = {
        red_species_number(item)
        for item in living_targets
        if specimen_counts[item] == 0
    }
    roster_internal = set(roster.species_ids)
    roster_national = {
        red_internal_species_number(species_id) for species_id in roster_internal
    }
    present_national = {
        red_internal_species_number(member.species_id)
        for member in observation.party.members
    }
    missing_roles = roster_national - present_national
    inventory = dict(observation.raw.bag_items)

    profiles = tuple(
        _member_profile(
            member,
            party=observation.party.members,
            evolutions=evolutions,
            policy=policy,
            areas=areas,
            inventory=inventory,
            missing_registration=missing_registration,
            missing_living=missing_living,
            missing_roles=missing_roles,
            living_targets=living_targets,
            specimen_counts=specimen_counts,
            roster_internal=roster_internal,
            trade_available=trade_available,
            active_conditions=active_conditions,
        )
        for member in observation.party.members
    )
    report = summarize_collection(collection_contract, collection)
    return PartyDevelopmentSemanticSnapshot(
        root_lineage_id=source_root_lineage_id,
        initial_state_sha256=reservation.source_state_sha256,
        partition=reservation.partition,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        party=observation.party,
        policy=policy,
        areas=areas,
        goal=reservation.goal,
        member_profiles=profiles,
        venue_prior_registry=venue_prior_registry,
        venue_operational_contract_sha256=venue_operational_contract_sha256,
        registration_owned_count=report.pokedex_owned_count,
        registration_target_count=report.target_count,
        living_unique_count=report.living_count,
        living_target_count=report.living_target_count,
        role_coverage_count=len(roster_internal & set(observation.party.species_ids())),
        role_target_count=len(roster.slots),
        active_conditions=active_conditions,
    )


def preflight_red_party_development_question(
    reservation: PartyDevelopmentQuestionReservation,
    *,
    source_root_lineage_id: str,
    observation: RedGoalObservation,
    evolutions: Mapping[int, tuple[Evolution, ...]],
    policy: BalancedTeamPolicy,
    areas: tuple[GrindingArea, ...],
    venue_prior_registry: PartyDevelopmentVenuePriorRegistry,
    venue_operational_contract_sha256: tuple[str, ...],
    source_commit: str,
    source_bundle_sha256: str,
    shared_venue: GrindingArea | None = None,
    fixed_trainee: PartyMemberObservation | None = None,
    collection_contract: CollectionContract = RED_SOLO_COLLECTION_CONTRACT,
    roster: TeamRosterPlan = RED_BALANCED_ROSTER,
    trade_available: bool = False,
    active_conditions: tuple[str, ...] = (),
) -> RedPartyDevelopmentQuestionPreflight:
    """Build one exact question without selecting an answer or acting."""

    snapshot = build_red_party_development_snapshot(
        reservation,
        source_root_lineage_id=source_root_lineage_id,
        observation=observation,
        evolutions=evolutions,
        policy=policy,
        areas=areas,
        venue_prior_registry=venue_prior_registry,
        venue_operational_contract_sha256=venue_operational_contract_sha256,
        source_commit=source_commit,
        source_bundle_sha256=source_bundle_sha256,
        collection_contract=collection_contract,
        roster=roster,
        trade_available=trade_available,
        active_conditions=active_conditions,
    )
    menu: (
        BoundPartyDevelopmentMenu[PartyMemberObservation]
        | BoundPartyDevelopmentMenu[GrindingArea]
        | None
    )
    if reservation.kind is TrainingChoiceKind.TRAINEE:
        if not isinstance(shared_venue, GrindingArea) or fixed_trainee is not None:
            raise RedPartyDevelopmentAdapterError(
                "trainee preflight needs only one explicit shared venue"
            )
        menu = snapshot.trainee_menu(shared_venue)
    else:
        if not isinstance(fixed_trainee, PartyMemberObservation) or shared_venue is not None:
            raise RedPartyDevelopmentAdapterError(
                "venue preflight needs only one explicit fixed trainee"
            )
        menu = snapshot.venue_menu(fixed_trainee)
    if menu is None:
        raise RedPartyDevelopmentAdapterError(
            "reserved Red state does not produce a multi-candidate question"
        )
    binding = snapshot.freeze_binding(menu, scenario_id=reservation.scenario_id)
    return RedPartyDevelopmentQuestionPreflight(
        reservation=reservation,
        source_root_lineage_id=source_root_lineage_id,
        snapshot=snapshot,
        menu=menu,
        binding=binding,
    )


def _member_profile(
    member: PartyMemberObservation,
    *,
    party: tuple[PartyMemberObservation, ...],
    evolutions: Mapping[int, tuple[Evolution, ...]],
    policy: BalancedTeamPolicy,
    areas: tuple[GrindingArea, ...],
    inventory: Mapping[int, int],
    missing_registration: set[int],
    missing_living: set[int],
    missing_roles: set[int],
    living_targets: set[str],
    specimen_counts: Counter[str],
    roster_internal: set[int],
    trade_available: bool,
    active_conditions: tuple[str, ...],
) -> PartyDevelopmentMemberProfile:
    national = red_internal_species_number(member.species_id)
    descendants = _descendant_distances(national, evolutions)
    registration_needed = bool(set(descendants) & missing_registration)
    living_needed = bool(set(descendants) & missing_living)
    role_needed = bool(set(descendants) & missing_roles)
    required_targets = (
        missing_registration | missing_living | missing_roles
    ) & set(descendants)
    evolution = _evolution_semantics(
        member,
        national_species=national,
        evolutions=evolutions,
        required_targets=required_targets,
        inventory=inventory,
        trade_available=trade_available,
    )
    member_ref = red_species_ref(national)
    return PartyDevelopmentMemberProfile(
        member=member,
        evolution=evolution,
        registration_needed=registration_needed,
        living_target_needed=living_needed,
        living_retention_risk=(
            evolution.required
            and member_ref in living_targets
            and specimen_counts[member_ref] == 1
        ),
        role_needed=role_needed,
        role_complete=member.species_id in roster_internal,
        emergency_escort_required=_is_only_emergency_escort(
            member,
            party=party,
            policy=policy,
            areas=areas,
            active_conditions=active_conditions,
        ),
        projected_survival_by_venue=tuple(
            _projected_survival_margin(member, policy=policy, area=area)
            for area in areas
        ),
    )


def _evolution_semantics(
    member: PartyMemberObservation,
    *,
    national_species: int,
    evolutions: Mapping[int, tuple[Evolution, ...]],
    required_targets: set[int],
    inventory: Mapping[int, int],
    trade_available: bool,
) -> EvolutionSemantics:
    choices = []
    for step in evolutions.get(national_species, ()):
        descendants = _descendant_distances(step.to_species, evolutions, initial_distance=1)
        relevant = required_targets & set(descendants)
        if not relevant:
            continue
        stages = max(descendants[target] for target in relevant)
        route = _route_kind(step.method)
        levels_to_next = (
            max(0, int(step.requirement) - member.level)
            if step.method is EvolutionMethod.LEVEL
            and isinstance(step.requirement, int)
            else None
        )
        feasible = _evolution_feasible(
            member,
            step=step,
            inventory=inventory,
            trade_available=trade_available,
        )
        choices.append(
            (
                -len(relevant),
                -int(feasible),
                stages,
                tuple(EvolutionRouteKind).index(route),
                step.to_species,
                EvolutionSemantics(
                    required=True,
                    stages_remaining=stages,
                    route_kind=route,
                    levels_to_next=levels_to_next,
                    feasible_now=feasible,
                ),
            )
        )
    if not choices:
        return EvolutionSemantics(False, 0, EvolutionRouteKind.NONE)
    return min(choices, key=lambda item: item[:-1])[-1]


def _descendant_distances(
    national_species: int,
    evolutions: Mapping[int, tuple[Evolution, ...]],
    *,
    initial_distance: int = 0,
) -> dict[int, int]:
    distances: dict[int, int] = {}
    frontier: list[tuple[int, int, frozenset[int]]] = [
        (national_species, initial_distance, frozenset())
    ]
    while frontier:
        species, distance, ancestors = frontier.pop()
        if species in ancestors:
            raise RedPartyDevelopmentAdapterError(
                "Red evolution graph contains a cycle"
            )
        previous = distances.get(species)
        if previous is not None and previous <= distance:
            continue
        distances[species] = distance
        if distance >= 4:
            continue
        next_ancestors = ancestors | {species}
        frontier.extend(
            (step.to_species, distance + 1, next_ancestors)
            for step in evolutions.get(species, ())
        )
    if initial_distance == 0:
        distances.pop(national_species, None)
    return distances


def _route_kind(method: EvolutionMethod) -> EvolutionRouteKind:
    return {
        EvolutionMethod.LEVEL: EvolutionRouteKind.LEVEL,
        EvolutionMethod.STONE: EvolutionRouteKind.ITEM,
        EvolutionMethod.TRADE: EvolutionRouteKind.TRADE,
    }[method]


def _evolution_feasible(
    member: PartyMemberObservation,
    *,
    step: Evolution,
    inventory: Mapping[int, int],
    trade_available: bool,
) -> bool:
    if step.method is EvolutionMethod.LEVEL:
        return member.is_trainable
    if step.method is EvolutionMethod.STONE:
        return (
            isinstance(step.requirement, int)
            and inventory.get(step.requirement, 0) > 0
        )
    if step.method is EvolutionMethod.TRADE:
        return trade_available
    return False


def _member_ready(member: PartyMemberObservation, policy: BalancedTeamPolicy) -> bool:
    return (
        member.is_trainable
        and member.hp_ratio > policy.retreat_hp_ratio
        and member.status is StatusCondition.HEALTHY
        and member.total_pp > policy.reserve_total_pp
    )


def _projected_survival_margin(
    member: PartyMemberObservation,
    *,
    policy: BalancedTeamPolicy,
    area: GrindingArea,
) -> float:
    if not _member_ready(member, policy):
        return -1.0
    share = area.fightable_share(training_safety_ceiling(member, policy))
    if share >= MINIMUM_FIGHTABLE_SHARE:
        return (share - MINIMUM_FIGHTABLE_SHARE) / (
            1.0 - MINIMUM_FIGHTABLE_SHARE
        )
    return (share - MINIMUM_FIGHTABLE_SHARE) / MINIMUM_FIGHTABLE_SHARE


def _is_only_emergency_escort(
    member: PartyMemberObservation,
    *,
    party: tuple[PartyMemberObservation, ...],
    policy: BalancedTeamPolicy,
    areas: tuple[GrindingArea, ...],
    active_conditions: tuple[str, ...],
) -> bool:
    active = tuple(area for area in areas if area.conditions_match(active_conditions))
    if not active or not any(item.level < policy.minimum_level for item in party):
        return False
    escorts = tuple(
        item
        for item in party
        if _member_ready(item, policy)
        and all(member_can_train_at(item, policy, area) for area in active)
    )
    return escorts == (member,)


def _require_party_matches_raw(observation: RedGoalObservation) -> None:
    raw_party = party_observation_from_raw(observation.raw)
    if len(raw_party.members) != len(observation.party.members):
        raise RedPartyDevelopmentAdapterError(
            "Red raw and semantic party counts differ"
        )
    for raw_member, member in zip(
        raw_party.members,
        observation.party.members,
        strict=True,
    ):
        raw_moves = tuple(
            (move.move_id, move.current_pp) for move in raw_member.moves
        )
        observed_moves = tuple(
            (move.move_id, move.current_pp) for move in member.moves
        )
        if (
            raw_member.slot != member.slot
            or raw_member.species_id != member.species_id
            or raw_member.level != member.level
            or raw_member.hp != member.hp
            or raw_member.max_hp != member.max_hp
            or raw_member.status is not member.status
            or raw_moves != observed_moves
        ):
            raise RedPartyDevelopmentAdapterError(
                "Red raw and semantic party observations differ"
            )


def _require_collection_matches_party(observation: RedGoalObservation) -> None:
    party_specimens = tuple(
        sorted(
            (
                item.slot_index,
                item.species_ref,
            )
            for item in observation.collection_observation.specimens
            if item.location is CollectionLocation.PARTY
        )
    )
    expected = tuple(
        (index, red_species_ref(red_internal_species_number(member.species_id)))
        for index, member in enumerate(observation.party.members)
    )
    if party_specimens != expected:
        raise RedPartyDevelopmentAdapterError(
            "Red collection and party observations differ"
        )
    report = observation.collection.collection
    if (
        report.pokedex_owned_count
        != len(
            set(observation.collection_observation.owned_species)
            & set(RED_SOLO_COLLECTION_CONTRACT.target_species)
        )
        or report.living_count
        != len(
            {
                item.species_ref
                for item in observation.collection_observation.specimens
                if item.species_ref
                in set(RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species)
            }
        )
    ):
        raise RedPartyDevelopmentAdapterError(
            "Red collection summary differs from its specimen observation"
        )


def _require_evolution_graph(
    evolutions: Mapping[int, tuple[Evolution, ...]],
) -> None:
    if not isinstance(evolutions, Mapping):
        raise TypeError("evolutions must be a mapping")
    for species, steps in evolutions.items():
        if (
            type(species) is not int  # noqa: E721
            or species <= 0
            or not isinstance(steps, tuple)
            or any(
                not isinstance(step, Evolution) or step.from_species != species
                for step in steps
            )
        ):
            raise RedPartyDevelopmentAdapterError(
                "Red evolution graph is invalid"
            )


__all__ = [
    "RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY",
    "RedPartyDevelopmentAdapterError",
    "RedPartyDevelopmentQuestionPreflight",
    "build_red_party_development_snapshot",
    "preflight_red_party_development_question",
]
