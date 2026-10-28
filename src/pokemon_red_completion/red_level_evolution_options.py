"""Expose observed, cartridge-supported level alternatives to canonical catches."""

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import cast

from .player_option_level_workload import OptionLevelWorkload
from .party_development_outcome_learning import PartyDevelopmentOutcomeModel
from .collection import CollectionLocation, LivingSpecimen
from .executor import CountingExecutor
from .gen1_cartridge import EvolutionMethod, evolution_graph
from .goal_manager import GoalKind, GoalUnavailableReason
from .observation import RedBoxSpecimenIdentity
from .red_battle_practice_cartridge import RedPracticeCartridge
from .red_collection import RED_SOLO_COLLECTION_CONTRACT, red_internal_species_id, red_species_ref
from .red_full_pokedex_direct_profile import _evolution_capability_parameters
from .red_goal_context import RedGoalContextRuntime
from .red_goal_context_profile import (
    RedGoalMechanic,
    RedGoalProviderSpec,
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from .red_goal_manager import RedGoalObservation
from .red_item_evolution_options import RedEvolutionOption
from .red_native_boxed_evolution import (
    bind_native_boxed_evolution,
    bind_native_evolution_goal_reserve,
)
from .red_party import PokemonRedPartyReader
from .red_resource_goal_router import RedResourceGoalRouter
from .resource_economy_observation import EconomyMode, EconomyOffer
from .route_executor import InterruptionHandler
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld
from .training_venue import TrainingVenue


def level_evolution_effort(
    current_level: int, target_level: int, level_progress: float | None,
) -> float:
    """Remaining-level workload, including observed partial-level XP.

    An overdue evolution still needs a native level-up. Missing XP retains the
    whole-level quote; this is not a promised battle or action count.
    """
    remaining = max(1, target_level - current_level)
    progress = 0.0 if level_progress is None else level_progress
    if not 0.0 <= progress <= 1.0:
        raise ValueError("evolution level progress must be a unit fraction")
    return min(1.0, (remaining - progress) / 99)


def _boxed_level_progress(
    precursor: LivingSpecimen,
    source_species_id: int,
    identities: tuple[RedBoxSpecimenIdentity, ...],
    cartridge: RedPracticeCartridge,
) -> float:
    """Quote the executor's physical source, not a better-progressed sibling."""
    matches = tuple(row for row in identities
                    if row.box_index == precursor.container_index
                    and row.box_slot == precursor.slot_index + 1)
    if (len(matches) != 1 or matches[0].species_id != source_species_id
            or matches[0].level != precursor.level):
        raise ValueError("boxed evolution identity differs from selected precursor")
    observed = matches[0]
    species = cartridge.species(source_species_id)
    floor = species.experience_at_level(observed.level)
    ceiling = species.experience_at_level(observed.level + 1)
    if ceiling <= floor or not floor <= observed.experience < ceiling:
        raise ValueError("boxed evolution experience differs from observed level")
    return (observed.experience - floor) / (ceiling - floor)


def enumerate_red_level_evolutions(
    runtime: RedGoalContextRuntime,
    observation: RedGoalObservation,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_actions: int,
    maximum_frames: int,
    maximum_quanta: int = 128,
    maximum_wall_seconds: int | None = None,
    prefer_highest_supported_venue: bool = False,
    allow_guarded_venue_escapes: bool = False,
    allow_direct_evolution: bool = True,
    training_venues: tuple[TrainingVenue, ...] | None = None,
    include_level_workload: bool = False,
    venue_model: PartyDevelopmentOutcomeModel | None = None,
    venue_model_sha256: str | None = None,
    observe_venue_decision: Callable[[object, tuple[TrainingVenue, ...], int, int], None] | None = None,
    interruption_handler_wrapper: (
        Callable[[InterruptionHandler, RedGoalProviderSpec], InterruptionHandler] | None
    ) = None,
) -> tuple[RedEvolutionOption, ...]:
    """Bind actual boxed or in-party alternatives to the catalog's default method.

    Discovery never moves the game. Native readiness preserves protected stock
    and verifies storage and training capability; remote execution requires the
    existing metered transport. Normalized remaining levels describe workload,
    not a species preference or a promised action count.
    """
    if interruption_handler_wrapper is not None and not callable(interruption_handler_wrapper):
        raise TypeError("evolution interruption wrapper must be callable")
    if maximum_wall_seconds is not None and (
        type(maximum_wall_seconds) is not int or maximum_wall_seconds <= 0
    ):
        raise ValueError('level evolution wall limit must be a positive integer')
    for permission in (prefer_highest_supported_venue, allow_guarded_venue_escapes, include_level_workload, allow_direct_evolution):
        if type(permission) is not bool:
            raise ValueError("level evolution venue options require explicit booleans")
    if training_venues is not None and (
        not isinstance(training_venues, tuple) or not training_venues
        or any(not isinstance(venue, TrainingVenue) for venue in training_venues)
        or len({venue.band.identity for venue in training_venues}) != len(training_venues)
    ):
        raise ValueError("level evolution requires distinct declared native venues")
    if runtime.registration_policy is None:
        raise ValueError("level enumeration requires a registration policy")
    runtime = bind_native_evolution_goal_reserve(
        runtime, actions, maximum_actions=maximum_actions, maximum_frames=maximum_frames,
    )
    before = actions.actions_executed, runtime.emulator.frame_count, runtime.reader.read()
    collection = observation.collection_observation
    registered = runtime.registration_policy.goal_registered(collection)
    candidates = []
    boxed_identities: tuple[RedBoxSpecimenIdentity, ...] | None = None
    cartridge: RedPracticeCartridge | None = None
    try:
        for source, edges in sorted(evolution_graph(world.rom).items()):
            source_ref = red_species_ref(source)
            party = tuple(
                specimen for specimen in collection.specimens
                if specimen.species_ref == source_ref
                and specimen.location is CollectionLocation.PARTY
            )
            # The native resume skill requires one unambiguous in-party source.
            if len(party) > 1:
                continue
            boxed = tuple(
                specimen for specimen in collection.specimens
                if specimen.species_ref == source_ref
                and specimen.location is CollectionLocation.BOX
                and collection.box_counts[specimen.container_index] < collection.box_capacity
            )
            if not party and not boxed:
                continue
            # Native execution resumes an in-party source before any boxed one.
            # Otherwise match its current-box-first storage selection.
            precursor = party[0] if party else min(boxed, key=lambda s: (
                s.container_index != collection.current_box_index, s.container_index, s.slot_index,
            ))
            if precursor.level >= 100:
                continue
            for edge in edges:
                target_ref = red_species_ref(edge.to_species)
                if (edge.method is not EvolutionMethod.LEVEL
                    or target_ref not in RED_SOLO_COLLECTION_CONTRACT.target_species
                    or target_ref in registered):
                    continue
                level = edge.requirement
                if type(level) is not int or not 1 <= level <= 100:
                    raise ValueError("cartridge level evolution threshold differs")
                parameters = {
                    **_evolution_capability_parameters(runtime.profile),
                    "source_species_ref": source_ref,
                    "target_species_ref": target_ref,
                    "evolution_level": level,
                }
                providers = {
                    spec.kind: (spec.kind, spec.mechanic,
                                cast(Mapping[str, object], _thaw(spec.parameters)))
                    for spec in runtime.profile.providers
                    if spec.kind is not GoalKind.EVOLVE_SPECIES
                }
                # A live capture-only profile need not predeclare an evolution.
                # Bind this observed edge, retaining canonical provider order.
                providers[GoalKind.EVOLVE_SPECIES] = (
                    GoalKind.EVOLVE_SPECIES, RedGoalMechanic.TARGETED_LEVEL_EVOLUTION, parameters,
                )
                profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
                    profile_id=runtime.profile.profile_id,
                    providers=tuple(providers[kind] for kind in GoalKind if kind in providers),
                ))
                native = bind_native_boxed_evolution(
                    replace(runtime, profile=profile), world,
                    maximum_quanta=maximum_quanta, allow_cross_box=True,
                    **({"allow_direct_evolution": False} if not allow_direct_evolution else {}),
                    **({'maximum_wall_seconds':maximum_wall_seconds}
                       if maximum_wall_seconds is not None else {}),
                    **({"prefer_highest_supported_venue": True}
                       if prefer_highest_supported_venue else {}),
                    **({"allow_guarded_venue_escapes": True}
                       if allow_guarded_venue_escapes else {}),
                    **({"training_venues": training_venues} if training_venues is not None else {}),
                    **({"venue_model": venue_model, "venue_model_sha256": venue_model_sha256}
                       if venue_model is not None or venue_model_sha256 is not None else {}),
                    **({"observe_venue_decision": observe_venue_decision}
                       if observe_venue_decision is not None else {}),
                )
                offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(observation)
                binding = offer.binding
                if (binding is None
                    and offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY):
                    routed = RedResourceGoalRouter(
                        native, actions, world, maximum_controller_actions=maximum_actions,
                        maximum_emulator_frames=maximum_frames,
                        quote_resource_costs=True, include_recovery_offers=False,
                        **({"interruption_handler_wrapper": interruption_handler_wrapper}
                           if interruption_handler_wrapper is not None else {}),
                    ).enumerate_routed_kinds(observation, frozenset({GoalKind.EVOLVE_SPECIES}))
                    bindings = tuple(
                        b for b in routed.bindings if b.kind is GoalKind.EVOLVE_SPECIES
                    )
                    if len(bindings) > 1:
                        raise ValueError("one level target supplied multiple bindings")
                    binding = bindings[0] if bindings else None
                if binding is not None:
                    progress = None
                    observed_xp = None
                    if party:
                        if cartridge is None:
                            cartridge = RedPracticeCartridge(world.rom)
                        rich_party = PokemonRedPartyReader(runtime.emulator).read_with_level_progress(
                            cartridge)
                        members = tuple(m for m in rich_party.members
                                        if m.species_id == red_internal_species_id(source))
                        progress = members[0].level_progress if len(members) == 1 else None
                        if include_level_workload and len(members) == 1:
                            observed_xp = members[0].experience
                    else:
                        # Some read-only observation ports expose only box levels.
                        # Retain the whole-level unknown quote for those ports.
                        read_identities = getattr(runtime.reader, "read_box_specimen_identities", None)
                        if read_identities is not None:
                            if boxed_identities is None:
                                boxed_identities = read_identities()
                            if cartridge is None:
                                cartridge = RedPracticeCartridge(world.rom)
                            progress = _boxed_level_progress(
                                precursor, red_internal_species_id(source),
                                boxed_identities, cartridge,
                            )
                            if include_level_workload:
                                observed_xp = next(row.experience for row in boxed_identities
                                    if row.box_index == precursor.container_index
                                    and row.box_slot == precursor.slot_index + 1)
                    workload = None
                    if include_level_workload and observed_xp is not None:
                        effective_target = max(precursor.level + 1, level)
                        species = cartridge.species(red_internal_species_id(source))
                        floor = species.experience_at_level(precursor.level)
                        ceiling = species.experience_at_level(precursor.level + 1)
                        if type(observed_xp) is not int or not floor <= observed_xp < ceiling:
                            raise ValueError("level evolution experience differs from observed level")
                        target_xp = species.experience_at_level(effective_target)
                        workload = OptionLevelWorkload(precursor.level, effective_target, target_xp - observed_xp)
                    candidates.append(RedEvolutionOption(
                        profile, binding, EconomyOffer(EconomyMode.OTHER, planned_spend=0),
                        level_evolution_effort(precursor.level, level, progress),
                        workload,
                    ))
    finally:
        if before != (
            actions.actions_executed, runtime.emulator.frame_count, runtime.reader.read(),
        ):
            raise ValueError("level target enumeration changed the game")
    if len({c.binding.binding_ref for c in candidates}) != len(candidates):
        raise ValueError("level targets supplied duplicate bindings")
    return tuple(candidates)
