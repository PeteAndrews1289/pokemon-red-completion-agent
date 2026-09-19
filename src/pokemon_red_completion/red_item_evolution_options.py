"""Action-free enumeration of missing, executable buyable-stone targets.

Catalog identities are private executor bindings, never policy features. Every
candidate has its own immutable profile and freshly bound native readiness and
executor; one catalog-selected evolution is not cloned into several menu rows.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import cast

from .collection import CollectionLocation
from .executor import CountingExecutor
from .goal_manager import GoalKind, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding
from .observation import MAX_BAG_ITEMS
from .red_acquisition import RED_ACQUISITION_CATALOG, RedAcquisitionKind
from .red_evolution_stones import BUYABLE_EVOLUTION_STONES
from .red_full_pokedex_direct_profile import _evolution_capability_parameters
from .red_goal_context import RedGoalContextRuntime
from .red_goal_context_profile import (
    RedGoalContextProfile,
    RedGoalMechanic,
    _thaw,
    build_red_goal_context_profile_payload,
    parse_red_goal_context_profile,
)
from .red_goal_manager import RedGoalObservation
from .red_native_boxed_item_evolution import bind_native_boxed_item_evolution
from .red_resource_goal_router import RedResourceGoalRouter
from .resource_economy_observation import EconomyMode, EconomyOffer
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


@dataclass(frozen=True, slots=True)
class RedEvolutionOption:
    profile: RedGoalContextProfile
    binding: ExecutableGoalBinding
    economy_offer: EconomyOffer
    execution_effort: float | None = None


def enumerate_red_item_evolutions(
    runtime: RedGoalContextRuntime,
    observation: RedGoalObservation,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_actions: int,
    maximum_frames: int,
) -> tuple[RedEvolutionOption, ...]:
    """Offer every supported missing boxed stone target, or none when blocked.

    This does not choose a target, query a model, buy a stone or move to a shop.
    Native readiness checks resources, cartridge edges, storage, preservation and
    the entire procurement path. Off-boundary targets additionally need a verified
    resource-router binding. Equal semantic vectors remain equal, not identity-coded.
    """
    if runtime.registration_policy is None:
        raise ValueError("item target enumeration requires a registration policy")
    before = actions.actions_executed, runtime.emulator.frame_count, runtime.reader.read()
    registered = runtime.registration_policy.goal_registered(observation.collection_observation)
    boxed = {
        specimen.species_ref
        for specimen in observation.collection_observation.specimens
        if specimen.location is CollectionLocation.BOX
    }
    candidates = []
    try:
        for method in RED_ACQUISITION_CATALOG.methods:
            if (
                method.kind is not RedAcquisitionKind.EVOLUTION
                or method.species_ref in registered
                or method.consumes_species_ref not in boxed
            ):
                continue
            stones = tuple(
                stone
                for stone in BUYABLE_EVOLUTION_STONES.values()
                if method.source_id == stone.acquisition_source_id
                and method.required_item_ref == stone.catalog_item_ref
            )
            if len(stones) != 1:
                continue
            stone = stones[0]
            bag = observation.raw.bag_items
            cash = observation.raw.player_money
            held = dict(bag or ()).get(int(stone.item_id), 0)
            # A route cannot repair absent purchasing resources. Avoid routing
            # these known blockers; native readiness still checks the full skill.
            if (
                bag is None or cash is None or held > 1
                or (not held and (cash < stone.price or len(bag) >= MAX_BAG_ITEMS))
            ):
                continue
            parameters = {
                **_evolution_capability_parameters(runtime.profile),
                "source_species_ref": method.consumes_species_ref,
                "target_species_ref": method.species_ref,
                "item_id": int(stone.item_id),
            }
            profile = parse_red_goal_context_profile(
                build_red_goal_context_profile_payload(
                    profile_id=runtime.profile.profile_id,
                    providers=tuple(
                        (spec.kind, RedGoalMechanic.TARGETED_ITEM_EVOLUTION, parameters)
                        if spec.kind is GoalKind.EVOLVE_SPECIES
                        else (
                            spec.kind,
                            spec.mechanic,
                            cast(Mapping[str, object], _thaw(spec.parameters)),
                        )
                        for spec in runtime.profile.providers
                    ),
                )
            )
            native = bind_native_boxed_item_evolution(
                replace(runtime, profile=profile),
                world,
                allow_cross_box=True,
            )
            offer = native.provider_for(GoalKind.EVOLVE_SPECIES, actions).offer(observation)
            binding = offer.binding
            if (
                binding is None
                and offer.unavailable_reason is GoalUnavailableReason.MISSING_CAPABILITY
            ):
                routed = RedResourceGoalRouter(
                    native,
                    actions,
                    world,
                    maximum_controller_actions=maximum_actions,
                    maximum_emulator_frames=maximum_frames,
                    quote_resource_costs=True,
                    include_recovery_offers=False,
                ).enumerate_routed_kinds(observation, frozenset({GoalKind.EVOLVE_SPECIES}))
                bindings = tuple(b for b in routed.bindings if b.kind is GoalKind.EVOLVE_SPECIES)
                if len(bindings) > 1:
                    raise ValueError("one evolution target supplied multiple bindings")
                binding = bindings[0] if bindings else None
            if binding is not None:
                candidates.append(
                    RedEvolutionOption(
                        profile,
                        binding,
                        EconomyOffer(EconomyMode.OTHER, planned_spend=0 if held else stone.price),
                    )
                )
    finally:
        if before != (
            actions.actions_executed,
            runtime.emulator.frame_count,
            runtime.reader.read(),
        ):
            raise ValueError("item target enumeration changed the game")
    if len({c.binding.binding_ref for c in candidates}) != len(candidates):
        raise ValueError("item targets supplied duplicate bindings")
    return tuple(candidates)
