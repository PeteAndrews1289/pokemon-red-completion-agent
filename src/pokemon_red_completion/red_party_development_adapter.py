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
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pokemon_red_completion.collection import (
    CollectionContract,
    CollectionLocation,
    summarize_collection,
)
from pokemon_red_completion.gen1_cartridge import Evolution, EvolutionMethod
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.party import PartyMemberObservation, StatusCondition
from pokemon_red_completion.party_development_adapter import (
    BoundPartyDevelopmentMenu,
    PartyDevelopmentCapabilityState,
    PartyDevelopmentExecutionCapability,
    PartyDevelopmentMemberProfile,
    PartyDevelopmentSemanticSnapshot,
)
from pokemon_red_completion.party_development_catalog import (
    PartyDevelopmentProspectiveBinding,
)
from pokemon_red_completion.party_development_outcomes import PartyCompletionSnapshot
from pokemon_red_completion.party_development_question_reservations import (
    PartyDevelopmentContextPreparation,
    PartyDevelopmentQuestionReservation,
)
from pokemon_red_completion.party_development_rank import (
    EvolutionRouteKind,
    EvolutionSemantics,
    VenuePriorFeatureMode,
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
from pokemon_red_completion.red_party import (
    BLASTOISE_SPECIES_ID,
    RED_BALANCED_ROSTER,
    party_observation_from_raw,
)
from pokemon_red_completion.red_party_pp import RedPartyPpState, decode_red_party_pp
from pokemon_red_completion.red_team_training import (
    ESCORT_LEVEL_CAP,
    TRAINING_MOVE_IDS,
    training_attack_pp_reserve,
)
from pokemon_red_completion.red_training_transitions import (
    red_vermilion_training_transition_available,
)
from pokemon_red_completion.team_training import (
    MINIMUM_FIGHTABLE_SHARE,
    BalancedTeamPolicy,
    GrindingArea,
    TeamRosterPlan,
    member_can_train_at,
    training_safety_ceiling,
)
from pokemon_red_completion.training_candidate_rank import TrainingChoiceKind
from pokemon_red_completion.training_venue import TrainingVenue

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


class RedPartyDevelopmentExecutionCapabilityError(RedPartyDevelopmentAdapterError):
    """Raised when an exact Red checkpoint cannot support capability screening."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


RedPartyDevelopmentTransitionGuard = Callable[[RawGameState, int, int], bool | None]

RED_PARTY_DEVELOPMENT_TRANSITION_GUARDS: tuple[
    RedPartyDevelopmentTransitionGuard, ...
] = (
    red_vermilion_training_transition_available,
    red_vermilion_training_transition_available,
)


@dataclass(frozen=True, slots=True)
class RedPartyDevelopmentQuestionPreflight:
    """One in-memory, action-free candidate binding ready for catalog freeze."""

    reservation: PartyDevelopmentQuestionReservation
    source_root_lineage_id: str
    snapshot: PartyDevelopmentSemanticSnapshot
    menu: (
        BoundPartyDevelopmentMenu[PartyMemberObservation] | BoundPartyDevelopmentMenu[GrindingArea]
    )
    binding: PartyDevelopmentProspectiveBinding

    def __post_init__(self) -> None:
        reservation = self.reservation
        source_root_lineage_id = self.source_root_lineage_id
        snapshot = self.snapshot
        menu = self.menu
        binding = self.binding
        if not isinstance(reservation, PartyDevelopmentQuestionReservation):
            raise RedPartyDevelopmentAdapterError("Red party preflight needs a typed reservation")
        if not isinstance(snapshot, PartyDevelopmentSemanticSnapshot):
            raise RedPartyDevelopmentAdapterError(
                "Red party preflight needs a typed semantic snapshot"
            )
        if not isinstance(menu, BoundPartyDevelopmentMenu):
            raise RedPartyDevelopmentAdapterError(
                "Red party preflight needs a bound candidate menu"
            )
        if not isinstance(binding, PartyDevelopmentProspectiveBinding):
            raise RedPartyDevelopmentAdapterError("Red party preflight needs a prospective binding")
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
            or len(binding.candidate_feature_sha256) != len(menu.candidate_set.candidates)
            or binding.candidate_available != menu.candidate_available
            or binding.candidate_unavailable_reasons != menu.candidate_unavailable_reasons
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
                value is not None for value in self.binding.venue_prior_evidence_sha256
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
    training_venues: tuple[TrainingVenue, ...] | None = None,
    transition_guards: tuple[RedPartyDevelopmentTransitionGuard, ...] | None = None,
    last_blackout_map: int | None = None,
    current_map_tileset: int | None = None,
    venue_prior_feature_mode: VenuePriorFeatureMode = VenuePriorFeatureMode.CALIBRATED,
    switch_assisted_battle_credit: bool = False,
) -> PartyDevelopmentSemanticSnapshot:
    """Derive the shared snapshot from one coherent, action-free Red read."""

    if not isinstance(reservation, PartyDevelopmentQuestionReservation):
        raise TypeError("reservation must be a PartyDevelopmentQuestionReservation")
    if not isinstance(observation, RedGoalObservation):
        raise TypeError("observation must be a RedGoalObservation")
    if not isinstance(policy, BalancedTeamPolicy):
        raise TypeError("policy must be a BalancedTeamPolicy")
    if not isinstance(venue_prior_registry, PartyDevelopmentVenuePriorRegistry):
        raise TypeError("venue_prior_registry must be a PartyDevelopmentVenuePriorRegistry")
    if not isinstance(venue_prior_feature_mode, VenuePriorFeatureMode):
        raise TypeError("venue_prior_feature_mode must be a VenuePriorFeatureMode")
    if not isinstance(switch_assisted_battle_credit, bool):
        raise TypeError("switch_assisted_battle_credit must be boolean")
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
        raise RedPartyDevelopmentAdapterError("Red party snapshot needs typed training areas")
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
    missing_registration = {red_species_number(item) for item in registration_targets - owned}
    missing_living = {
        red_species_number(item) for item in living_targets if specimen_counts[item] == 0
    }
    roster_internal = set(roster.species_ids)
    roster_national = {red_internal_species_number(species_id) for species_id in roster_internal}
    present_national = {
        red_internal_species_number(member.species_id) for member in observation.party.members
    }
    missing_roles = roster_national - present_national
    inventory = dict(observation.raw.bag_items)
    execution_capabilities = _execution_capability_matrix(
        observation,
        policy=policy,
        areas=areas,
        training_venues=training_venues,
        transition_guards=transition_guards,
        last_blackout_map=last_blackout_map,
        current_map_tileset=current_map_tileset,
        switch_assisted_battle_credit=switch_assisted_battle_credit,
    )

    profiles = tuple(
        _member_profile(
            member,
            execution_capabilities_by_venue=execution_capabilities[index],
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
        for index, member in enumerate(observation.party.members)
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
        venue_prior_feature_mode=venue_prior_feature_mode,
        execution_protocol_id=(
            "switch-assisted-fixed-dose-v1"
            if switch_assisted_battle_credit
            else "legacy-adaptive-v1"
        ),
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
    training_venues: tuple[TrainingVenue, ...] | None = None,
    transition_guards: tuple[RedPartyDevelopmentTransitionGuard, ...] | None = None,
    last_blackout_map: int | None = None,
    current_map_tileset: int | None = None,
    venue_prior_feature_mode: VenuePriorFeatureMode = VenuePriorFeatureMode.CALIBRATED,
    switch_assisted_battle_credit: bool = False,
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
        training_venues=training_venues,
        transition_guards=transition_guards,
        last_blackout_map=last_blackout_map,
        current_map_tileset=current_map_tileset,
        venue_prior_feature_mode=venue_prior_feature_mode,
        switch_assisted_battle_credit=switch_assisted_battle_credit,
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


def red_party_completion_snapshot(
    observation: RedGoalObservation,
    *,
    evolutions: Mapping[int, tuple[Evolution, ...]],
    policy: BalancedTeamPolicy,
    collection_contract: CollectionContract = RED_SOLO_COLLECTION_CONTRACT,
    roster: TeamRosterPlan = RED_BALANCED_ROSTER,
    trade_available: bool = False,
) -> PartyCompletionSnapshot:
    """Project verifier counters at one stable Red execution boundary.

    This is intentionally smaller than candidate construction: an outcome may
    change HP, PP, party order, level, and species, but the verifier needs only
    completion counts and remaining deficits.  Recomputing those facts from the
    live post-dose observation avoids carrying the frozen candidate's answer
    into its own outcome.
    """

    if not isinstance(observation, RedGoalObservation):
        raise TypeError("observation must be a RedGoalObservation")
    if not isinstance(policy, BalancedTeamPolicy):
        raise TypeError("policy must be a BalancedTeamPolicy")
    if not isinstance(collection_contract, CollectionContract):
        raise TypeError("collection_contract must be a CollectionContract")
    if not isinstance(roster, TeamRosterPlan):
        raise TypeError("roster must be a TeamRosterPlan")
    if not isinstance(trade_available, bool):
        raise TypeError("trade_available must be boolean")
    if (
        not observation.raw.game_started
        or observation.raw.battle_state != 0
        or not observation.input_ready
        or observation.raw.bag_items is None
    ):
        raise RedPartyDevelopmentAdapterError(
            "Red party completion snapshot requires stable ready overworld control"
        )
    _require_party_matches_raw(observation)
    _require_collection_matches_party(observation)
    _require_evolution_graph(evolutions)

    collection = observation.collection_observation
    owned = set(collection.owned_species)
    specimen_counts = Counter(item.species_ref for item in collection.specimens)
    living_targets = set(collection_contract.resolved_living_target_species)
    registration_targets = set(collection_contract.target_species)
    missing_registration = {red_species_number(item) for item in registration_targets - owned}
    missing_living = {
        red_species_number(item) for item in living_targets if specimen_counts[item] == 0
    }
    roster_internal = set(roster.species_ids)
    roster_national = {red_internal_species_number(species_id) for species_id in roster_internal}
    present_national = {
        red_internal_species_number(member.species_id) for member in observation.party.members
    }
    missing_roles = roster_national - present_national
    inventory = dict(observation.raw.bag_items)
    evolution_steps = 0
    for member in observation.party.members:
        national = red_internal_species_number(member.species_id)
        descendants = _descendant_distances(national, evolutions)
        required_targets = (missing_registration | missing_living | missing_roles) & set(
            descendants
        )
        evolution_steps += _evolution_semantics(
            member,
            national_species=national,
            evolutions=evolutions,
            required_targets=required_targets,
            inventory=inventory,
            trade_available=trade_available,
        ).stages_remaining
    report = summarize_collection(collection_contract, collection)
    return PartyCompletionSnapshot(
        registered_target_count=report.pokedex_owned_count,
        registration_target_total=report.target_count,
        living_target_count=report.living_count,
        living_target_total=report.living_target_count,
        role_coverage_count=len(roster_internal & set(observation.party.species_ids())),
        role_target_total=len(roster.slots),
        evolution_steps_remaining=evolution_steps,
        level_floor_deficit=sum(
            max(0, policy.minimum_level - member.level) for member in observation.party.members
        ),
    )


def _member_profile(
    member: PartyMemberObservation,
    *,
    execution_capabilities_by_venue: tuple[PartyDevelopmentExecutionCapability, ...],
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
    required_targets = (missing_registration | missing_living | missing_roles) & set(descendants)
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
        execution_capabilities_by_venue=execution_capabilities_by_venue,
        registration_needed=registration_needed,
        living_target_needed=living_needed,
        living_retention_risk=(
            evolution.required and member_ref in living_targets and specimen_counts[member_ref] == 1
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
            _projected_survival_margin(member, policy=policy, area=area) for area in areas
        ),
    )


def _execution_capability_matrix(
    observation: RedGoalObservation,
    *,
    policy: BalancedTeamPolicy,
    areas: tuple[GrindingArea, ...],
    training_venues: tuple[TrainingVenue, ...] | None,
    transition_guards: tuple[RedPartyDevelopmentTransitionGuard, ...] | None,
    last_blackout_map: int | None,
    current_map_tileset: int | None,
    switch_assisted_battle_credit: bool = False,
) -> tuple[tuple[PartyDevelopmentExecutionCapability, ...], ...]:
    """Derive dynamic Red facts, then discard every Red identity.

    Historical catalog reconstruction did not carry an execution-capability
    contract, so callers that omit every optional input retain their exact
    all-ready behavior. New outcome development must supply the complete dynamic
    contract. Supplying only part of that contract fails closed rather than
    mixing prospective and legacy menus.
    """

    if (
        training_venues is None
        and transition_guards is None
        and last_blackout_map is None
        and current_map_tileset is None
    ):
        return tuple(
            tuple(PartyDevelopmentExecutionCapability.ready() for _ in areas)
            for _ in observation.party.members
        )
    if (
        not isinstance(training_venues, tuple)
        or tuple(venue.band for venue in training_venues) != areas
        or not isinstance(transition_guards, tuple)
        or len(transition_guards) != len(areas)
        or any(not callable(guard) for guard in transition_guards)
        or type(last_blackout_map) is not int  # noqa: E721
        or last_blackout_map < 0
        or type(current_map_tileset) is not int  # noqa: E721
        or not 0 <= current_map_tileset <= 0xFF
    ):
        raise RedPartyDevelopmentExecutionCapabilityError(
            "adapter_contract_misaligned",
            "Red prospective execution inputs must align with every venue",
        )
    raw = observation.raw
    if raw.party_moves is None or raw.party_pp is None:
        raise RedPartyDevelopmentExecutionCapabilityError(
            "packed_party_pp_unavailable",
            "Red prospective execution needs complete packed party PP",
        )
    if len(raw.party_moves) != len(observation.party.members) or len(raw.party_pp) != len(
        observation.party.members
    ):
        raise RedPartyDevelopmentExecutionCapabilityError(
            "packed_party_pp_misaligned",
            "Red prospective execution PP differs from the party",
        )
    try:
        decoded = tuple(
            decode_red_party_pp(tuple(moves), tuple(pp))
            for moves, pp in zip(raw.party_moves, raw.party_pp, strict=True)
        )
    except (TypeError, ValueError) as error:
        raise RedPartyDevelopmentExecutionCapabilityError(
            "packed_party_pp_misaligned",
            "Red prospective execution PP differs from the party",
        ) from error
    if not isinstance(switch_assisted_battle_credit, bool):
        raise RedPartyDevelopmentExecutionCapabilityError(
            "adapter_contract_misaligned",
            "Red prospective battle-credit mode must be boolean",
        )
    escorts = tuple(
        (index, member)
        for index, member in enumerate(observation.party.members)
        if member.species_id == BLASTOISE_SPECIES_ID
    )
    if len(escorts) != 1:
        raise RedPartyDevelopmentExecutionCapabilityError(
            "qualified_escape_escort_unavailable",
            "Red prospective execution needs one qualified escape escort",
        )
    escort_index, escort = escorts[0]
    escort_slots, escort_maximum_pp = _recoverable_attack_profile(
        escort,
        decoded[escort_index],
    )
    escort_recoverable = escort_maximum_pp > training_attack_pp_reserve(escort, policy)
    escort_can_win = len(escort_slots) >= 2 and escort.level < ESCORT_LEVEL_CAP

    rows = []
    for member_index, member in enumerate(observation.party.members):
        attack_slots, maximum_attack_pp = _recoverable_attack_profile(
            member,
            decoded[member_index],
        )
        member_recoverable = maximum_attack_pp > training_attack_pp_reserve(
            member,
            policy,
        )
        row = []
        for area, transition_guard in zip(
            areas,
            transition_guards,
            strict=True,
        ):
            transition = transition_guard(raw, last_blackout_map, current_map_tileset)
            if transition is not None and not isinstance(transition, bool):
                raise RedPartyDevelopmentExecutionCapabilityError(
                    "transition_guard_invalid",
                    "Red prospective transition guard returned no boolean verdict",
                )
            transition_state = (
                PartyDevelopmentCapabilityState.UNKNOWN
                if transition is None
                else PartyDevelopmentCapabilityState.READY
                if transition
                else PartyDevelopmentCapabilityState.BLOCKED
            )
            member_fights_here = member_can_train_at(member, policy, area)
            direct_fight_ready = member_fights_here and len(attack_slots) >= 2
            battle_state = (
                PartyDevelopmentCapabilityState.READY
                if (
                    escort_can_win
                    if switch_assisted_battle_credit
                    else direct_fight_ready
                    or (not member_fights_here and escort_can_win)
                )
                else PartyDevelopmentCapabilityState.BLOCKED
            )
            recovery_state = (
                PartyDevelopmentCapabilityState.READY
                if (
                    escort_recoverable
                    if switch_assisted_battle_credit
                    else member_recoverable
                    and (direct_fight_ready or escort_recoverable)
                )
                else PartyDevelopmentCapabilityState.BLOCKED
            )
            row.append(
                PartyDevelopmentExecutionCapability(
                    transition=transition_state,
                    battle=battle_state,
                    recovery=recovery_state,
                )
            )
        rows.append(tuple(row))
    return tuple(rows)


def _recoverable_attack_profile(
    member: PartyMemberObservation,
    pp_state: RedPartyPpState,
) -> tuple[tuple[int, ...], int]:
    """Return slots and PP after the venue's explicit heal-and-return action."""

    preferred = frozenset(TRAINING_MOVE_IDS.get(member.species_id, ()))
    eligible = tuple(
        item
        for item in pp_state.moves
        if item.move_id and (not preferred or item.move_id in preferred)
    )
    return tuple(item.slot for item in eligible if item.maximum_pp > 0), sum(
        item.maximum_pp for item in eligible
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
            if step.method is EvolutionMethod.LEVEL and isinstance(step.requirement, int)
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
            raise RedPartyDevelopmentAdapterError("Red evolution graph contains a cycle")
        previous = distances.get(species)
        if previous is not None and previous <= distance:
            continue
        distances[species] = distance
        if distance >= 4:
            continue
        next_ancestors = ancestors | {species}
        frontier.extend(
            (step.to_species, distance + 1, next_ancestors) for step in evolutions.get(species, ())
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
        return isinstance(step.requirement, int) and inventory.get(step.requirement, 0) > 0
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
        return (share - MINIMUM_FIGHTABLE_SHARE) / (1.0 - MINIMUM_FIGHTABLE_SHARE)
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
        raise RedPartyDevelopmentAdapterError("Red raw and semantic party counts differ")
    for raw_member, member in zip(
        raw_party.members,
        observation.party.members,
        strict=True,
    ):
        raw_moves = tuple((move.move_id, move.current_pp) for move in raw_member.moves)
        observed_moves = tuple((move.move_id, move.current_pp) for move in member.moves)
        if (
            raw_member.slot != member.slot
            or raw_member.species_id != member.species_id
            or raw_member.level != member.level
            or raw_member.hp != member.hp
            or raw_member.max_hp != member.max_hp
            or raw_member.status is not member.status
            or raw_moves != observed_moves
        ):
            raise RedPartyDevelopmentAdapterError("Red raw and semantic party observations differ")


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
        raise RedPartyDevelopmentAdapterError("Red collection and party observations differ")
    report = observation.collection.collection
    if report.pokedex_owned_count != len(
        set(observation.collection_observation.owned_species)
        & set(RED_SOLO_COLLECTION_CONTRACT.target_species)
    ) or report.living_count != len(
        {
            item.species_ref
            for item in observation.collection_observation.specimens
            if item.species_ref in set(RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species)
        }
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
                not isinstance(step, Evolution) or step.from_species != species for step in steps
            )
        ):
            raise RedPartyDevelopmentAdapterError("Red evolution graph is invalid")


__all__ = [
    "RED_PARTY_DEVELOPMENT_CURRICULUM_POLICY",
    "RedPartyDevelopmentAdapterError",
    "RedPartyDevelopmentQuestionPreflight",
    "build_red_party_development_snapshot",
    "preflight_red_party_development_question",
    "red_party_completion_snapshot",
]
