"""Opt-in venue scoring for ordinary preparation, with the existing K executor.

No evolution-executor yield estimate is transferred to this protocol. Concrete
routes stay private; only prospective mechanics enter the existing venue head.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field

from .collection import summarize_collection
from .gen1_cartridge import evolution_graph, wild_encounter_tables
from .party_development_adapter import (
    BoundPartyDevelopmentMenu, PartyDevelopmentCapabilityState,
    PartyDevelopmentExecutionCapability, observe_party_development_context,
)
from .party_development_outcome_learning import PartyDevelopmentOutcomeModel
from .party_development_rank import (
    CandidateCompletionSemantics, EvolutionRouteKind, EvolutionSemantics,
    PartyDevelopmentGoal, VenueOperationalPrior, VenuePriorFeatureMode,
    VenueTrainingWorkload, augment_training_candidate_set,
)
from .player_option_level_workload import OptionLevelWorkload
from .provenance import canonical_sha256
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_collection import RED_SOLO_COLLECTION_CONTRACT, red_internal_species_number, red_species_number
from .red_living_dex_wild_corridor import RedLivingDexWildCorridor
from .red_native_boxed_evolution import validate_native_evolution_venue_model
from .red_party import RED_BALANCED_ROSTER
from .red_party_development_adapter import (
    _member_profile, _require_party_matches_raw, _require_collection_matches_party, observe_red_venue_matchup_context,
)
from .red_safari_acquisition import _RED_ENCOUNTER_SLOT_WEIGHTS
from .team_training import BalancedTeamPolicy, GrindingArea
from .training_candidate_rank import TrainingCandidate, TrainingCandidateSet, TrainingChoiceKind, _candidate_features


@dataclass(frozen=True)
class OrdinaryPreparationVenuePolicy:
    """Separate declared authority; evolution qualifications do not cover it."""
    model: PartyDevelopmentOutcomeModel = field(repr=False, compare=False)
    model_sha256: str
    task_contract: str = "native-level-dose-v1"

    def __post_init__(self):
        if not isinstance(self.task_contract, str) or self.task_contract not in {
            "native-level-dose-v1", "party-development.fixed-level-ready-task-cost.v1"
        }:
            raise ValueError("ordinary preparation needs a known task contract")
        validate_native_evolution_venue_model(self.model, self.model_sha256)
        if self.model is None:
            raise ValueError("ordinary venue policy requires a scorer")


@dataclass(frozen=True)
class OrdinaryPreparationVenue:
    """Private binding from the existing legal route inventory, not a new route."""
    corridor: RedLivingDexWildCorridor
    source_id: str
    home_map: int

    def __post_init__(self):
        if not isinstance(self.corridor, RedLivingDexWildCorridor):
            raise ValueError("ordinary venue requires the existing corridor")
        if not isinstance(self.source_id, str) or self.source_id != self.corridor.source_id:
            raise ValueError("ordinary venue source differs from corridor")
        if type(self.home_map) is not int or not 0 <= self.home_map <= 255:
            raise ValueError("ordinary venue requires a native home map")


def build_ordinary_preparation_venue_menu(observation, *, rom, trainee, target_level, venues, geometry_quotes=None):
    """Project all executable sibling venues for one exact member/target.

    Caller first builds the existing routed bindings; this adapter neither
    establishes route feasibility nor manufactures availability from map tables.
    Encounter bands are decoded, never labelled as measured encounters. Actual
    participant count and K battle choices are unknown before execution.
    """
    if trainee not in observation.party.members or trainee.experience is None:
        raise ValueError("ordinary venue trainee requires the exact observed XP binding")
    if type(target_level) is not int or not trainee.level < target_level <= 100:
        raise ValueError("ordinary venue requires an unmet legal level target")
    if observation.raw.battle_state or not observation.input_ready:
        raise ValueError("ordinary venue requires released field control")
    _require_party_matches_raw(observation)
    _require_collection_matches_party(observation)
    if type(venues) is not tuple or not venues or any(type(v) is not OrdinaryPreparationVenue for v in venues):
        raise ValueError("ordinary venue requires typed executable inventory")
    if len({(v.corridor.map_id, v.source_id, v.home_map) for v in venues}) != len(venues):
        raise ValueError("ordinary venue inventory repeats a binding")
    from .red_native_venue_geometry import NativeVenueGeometryQuote
    if geometry_quotes is not None and (type(geometry_quotes) is not tuple
        or len(geometry_quotes) != len(venues) or any(type(q) is not NativeVenueGeometryQuote for q in geometry_quotes)):
        raise ValueError("ordinary geometry inventory differs")
    decoded = wild_encounter_tables(rom)
    tables = []
    areas = []
    for venue_index, venue in enumerate(venues):
        blocks = tuple(t for t in decoded.get(venue.corridor.map_id, ()) if t.medium == "grass")
        if len(blocks) != 1 or len(blocks[0].slots) != len(_RED_ENCOUNTER_SLOT_WEIGHTS):
            raise ValueError("ordinary venue requires a complete native grass table")
        tables.append(blocks[0].slots)
        levels = tuple(level for level, _ in blocks[0].slots)
        # Existing coarse healer capability is asserted only when the canonical
        # native return is actually quotable. Its distance is a separate feature.
        geometry = None if geometry_quotes is None else geometry_quotes[venue_index]
        area = GrindingArea(venue.source_id, min(levels), max(levels),
            has_nearby_healer=geometry is not None and geometry.recovery_steps is not None)
        if geometry is not None:
            from types import SimpleNamespace
            geometry.require_binding(observation.raw, SimpleNamespace(band=area, map_id=venue.corridor.map_id, home_map=venue.home_map))
        areas.append(area)
    areas = tuple(areas)
    cartridge = RedPracticeCartridge(rom)
    species = cartridge.species(trainee.species_id)
    if not species.experience_at_level(trainee.level) <= trainee.experience < species.experience_at_level(trainee.level + 1):
        raise ValueError("ordinary trainee XP differs from its observed level")
    workload = OptionLevelWorkload(trainee.level, target_level, species.experience_at_level(target_level) - trainee.experience)
    # This policy supplies normalization/context to the shared feature projector;
    # it does not screen or choose a K battle action.
    policy = BalancedTeamPolicy(minimum_level=target_level)
    graph = evolution_graph(rom)
    collection = observation.collection_observation
    contract = RED_SOLO_COLLECTION_CONTRACT
    owned = set(collection.owned_species)
    counts = Counter(item.species_ref for item in collection.specimens)
    living = set(contract.resolved_living_target_species)
    missing_registration = {red_species_number(ref) for ref in set(contract.target_species) - owned}
    missing_living = {red_species_number(ref) for ref in living if counts[ref] == 0}
    roster_internal = set(RED_BALANCED_ROSTER.species_ids)
    missing_roles = {red_internal_species_number(s) for s in roster_internal} - {red_internal_species_number(m.species_id) for m in observation.party.members}
    unknown = PartyDevelopmentCapabilityState.UNKNOWN
    capabilities = (PartyDevelopmentExecutionCapability(unknown, unknown, unknown),) * len(areas)
    profiles = tuple(_member_profile(m, execution_capabilities_by_venue=capabilities,
        party=observation.party.members, evolutions=graph, policy=policy, areas=areas,
        inventory=dict(observation.raw.bag_items or ()), missing_registration=missing_registration,
        missing_living=missing_living, missing_roles=missing_roles, living_targets=living,
        specimen_counts=counts, roster_internal=roster_internal, trade_available=False,
        active_conditions=()) for m in observation.party.members)
    report = summarize_collection(contract, collection)
    context = observe_party_development_context(goal=PartyDevelopmentGoal.BALANCE,
        party=observation.party, policy=policy, member_profiles=profiles,
        registration_owned_count=report.pokedex_owned_count, registration_target_count=report.target_count,
        living_unique_count=report.living_count, living_target_count=report.living_target_count,
        role_coverage_count=len(roster_internal & set(observation.party.species_ids())),
        role_target_count=len(RED_BALANCED_ROSTER.slots))
    # The chosen task is a level dose, not an evolution promise or registration.
    semantics = (CandidateCompletionSemantics(EvolutionSemantics(False, 0, EvolutionRouteKind.NONE)),) * len(areas)
    stats = observation.raw.party_stats
    if stats is not None and (type(stats) is not tuple or len(stats) != observation.party.size):
        raise ValueError("ordinary venue stat census differs from the observed party")
    matchups = tuple(observe_red_venue_matchup_context(trainee, encounter_slots=slots,
        weights=_RED_ENCOUNTER_SLOT_WEIGHTS,
        raw_stats=None if stats is None else stats[trainee.slot - 1],
        collection_attack_filter=False) for slots in tables)
    base = TrainingCandidateSet(TrainingChoiceKind.VENUE, tuple(TrainingCandidate(i,
        _candidate_features(kind=TrainingChoiceKind.VENUE, party=observation.party,
            policy=policy, trainee=trainee, areas=areas, venue=area)) for i, area in enumerate(areas)))
    candidates = augment_training_candidate_set(base, context, semantics, include_workload=True,
        level_workloads=(workload,) * len(areas), fixed_level_target=workload,
        venue_workloads=tuple(VenueTrainingWorkload(None, None,
            None if geometry_quotes is None else geometry_quotes[i].travel_steps,
            None if geometry_quotes is None else geometry_quotes[i].recovery_steps) for i in range(len(areas))),
        include_matchup_context=True, venue_matchups=matchups)
    snapshot = canonical_sha256(dict(schema="pokemon.red.ordinary-preparation-venue-menu.v1",
        party=asdict(observation.party), target_level=target_level,
        venues=[dict(source=v.source_id, map_id=v.corridor.map_id, home=v.home_map) for v in venues],
        protocol="existing-k-member-preparation-unknown-yield-v1", candidates=candidates.public_dict(),
        route_geometry=None if geometry_quotes is None else [q.public_dict() for q in geometry_quotes]))
    return BoundPartyDevelopmentMenu(candidates, snapshot, areas, (True,) * len(areas),
        (None,) * len(areas), (VenueOperationalPrior(),) * len(areas),
        venue_prior_feature_mode=VenuePriorFeatureMode.MASKED_UNCALIBRATED)