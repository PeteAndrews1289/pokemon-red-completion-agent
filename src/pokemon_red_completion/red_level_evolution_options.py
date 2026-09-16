"""Expose observed, cartridge-supported level alternatives to canonical catches."""

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from .collection import CollectionLocation
from .executor import CountingExecutor
from .gen1_cartridge import EvolutionMethod, evolution_graph
from .goal_manager import GoalKind, GoalUnavailableReason
from .red_collection import RED_SOLO_COLLECTION_CONTRACT, red_species_ref
from .red_full_pokedex_direct_profile import _evolution_capability_parameters
from .red_goal_context import RedGoalContextRuntime
from .red_goal_context_profile import (
    RedGoalMechanic,
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from .red_goal_manager import RedGoalObservation
from .red_item_evolution_options import RedEvolutionOption
from .red_native_boxed_evolution import bind_native_boxed_evolution
from .red_resource_goal_router import RedResourceGoalRouter
from .resource_economy_observation import EconomyMode, EconomyOffer
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def enumerate_red_level_evolutions(
    runtime: RedGoalContextRuntime,
    observation: RedGoalObservation,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_actions: int,
    maximum_frames: int,
    maximum_quanta: int = 128,
) -> tuple[RedEvolutionOption, ...]:
    """Bind actual boxed or in-party alternatives to the catalog's default method.

    Discovery never moves the game. Native readiness preserves protected stock
    and verifies storage and training capability; remote execution requires the
    existing metered transport. Normalized remaining levels describe workload,
    not a species preference or a promised action count.
    """
    if runtime.registration_policy is None:
        raise ValueError("level enumeration requires a registration policy")
    before = actions.actions_executed, runtime.emulator.frame_count, runtime.reader.read()
    collection = observation.collection_observation
    registered = runtime.registration_policy.goal_registered(collection)
    candidates = []
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
                profile = parse_red_goal_context_profile(build_red_goal_context_profile_payload(
                    profile_id=runtime.profile.profile_id,
                    providers=tuple(
                        (spec.kind, RedGoalMechanic.TARGETED_LEVEL_EVOLUTION, parameters)
                        if spec.kind is GoalKind.EVOLVE_SPECIES else (
                            spec.kind, spec.mechanic,
                            cast(Mapping[str, object], _thaw(spec.parameters)),
                        ) for spec in runtime.profile.providers
                    ),
                ))
                native = bind_native_boxed_evolution(
                    replace(runtime, profile=profile), world,
                    maximum_quanta=maximum_quanta, allow_cross_box=True,
                )
                offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(observation)
                binding = offer.binding
                if (binding is None
                    and offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY):
                    routed = RedResourceGoalRouter(
                        native, actions, world, maximum_controller_actions=maximum_actions,
                        maximum_emulator_frames=maximum_frames,
                        quote_resource_costs=True, include_recovery_offers=False,
                    ).enumerate_routed_kinds(observation, frozenset({GoalKind.EVOLVE_SPECIES}))
                    bindings = tuple(
                        b for b in routed.bindings if b.kind is GoalKind.EVOLVE_SPECIES
                    )
                    if len(bindings) > 1:
                        raise ValueError("one level target supplied multiple bindings")
                    binding = bindings[0] if bindings else None
                if binding is not None:
                    candidates.append(RedEvolutionOption(
                        profile, binding, EconomyOffer(EconomyMode.OTHER, planned_spend=0),
                        min(1.0, max(1, level - precursor.level) / 99),
                    ))
    finally:
        if before != (
            actions.actions_executed, runtime.emulator.frame_count, runtime.reader.read(),
        ):
            raise ValueError("level target enumeration changed the game")
    if len({c.binding.binding_ref for c in candidates}) != len(candidates):
        raise ValueError("level targets supplied duplicate bindings")
    return tuple(candidates)
