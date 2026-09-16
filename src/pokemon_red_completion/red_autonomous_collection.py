"""Rebuild a mixed collection menu from each live state without a chosen route."""

from dataclasses import replace

from .executor import CountingExecutor
from .goal_manager import GoalAvailability, GoalKind, GoalOpportunity, GoalUnavailableReason
from .goal_manager_runtime import GoalBindingSet
from .living_dex_goal_policy import project_living_dex_goal_candidate
from .living_dex_option_value import LivingDexOptionKind
from .red_autonomous_league_funding import bind_autonomous_league_funding
from .red_bounded_player import RedBoundedPlayerObserver
from .red_evolution_stones import buyable_evolution_stone
from .red_full_pokedex_direct_profile import derive_direct_full_pokedex_profile
from .red_goal_context import RedGoalContextRuntime
from .red_goal_context_profile import (
    RedGoalMechanic,
    bind_composable_trainer_funding_profile,
    bind_funding_fly_profile,
    bind_mart_funding_departure_profile,
)
from .red_live_option_menu import (
    RedLiveOptionSet,
    build_red_live_option_set,
    supplemental_live_option,
)
from .red_native_boxed_evolution import bind_native_boxed_evolution
from .red_native_boxed_item_evolution import bind_native_boxed_item_evolution
from .red_regional_acquisition import enumerate_red_regional_acquisitions
from .red_resource_economy import red_economy_snapshot
from .red_resource_goal_router import RedResourceGoalRouter
from .resource_economy_observation import EconomyMode, EconomyOffer
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def autonomous_collection_options(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    model_feature_version: int,
    ordering_seed_sha256: str,
    maximum_actions: int = 30_000,
    maximum_frames: int = 3_000_000,
) -> RedLiveOptionSet:
    """Expose up to eight real capture destinations alongside ordinary goals.

    Evolution target derivation and mechanical execution remain deterministic.
    The model selects the actual destination when it selects a capture option.
    No source/species identity is projected into policy features.
    """
    if runtime.registration_policy is None:
        raise ValueError("autonomous collection requires a registered objective")
    runtime = replace(
        runtime,
        adapter=replace(
            runtime.adapter,
            registration_policy=runtime.registration_policy,
        ),
    )
    live = runtime.adapter.observe()
    profile = derive_direct_full_pokedex_profile(runtime.profile, live, world)
    profile = bind_funding_fly_profile(
        bind_mart_funding_departure_profile(bind_composable_trainer_funding_profile(profile))
    )
    runtime = replace(runtime, profile=profile)
    evolution = next(spec for spec in profile.providers if spec.kind is GoalKind.EVOLVE_SPECIES)
    if evolution.mechanic is RedGoalMechanic.TARGETED_ITEM_EVOLUTION:
        native = bind_native_boxed_item_evolution(runtime, world, allow_cross_box=True)
    else:
        native = bind_native_boxed_evolution(
            runtime,
            world,
            maximum_quanta=128,
            allow_cross_box=True,
        )
    router = RedResourceGoalRouter(
        native,
        actions,
        world,
        maximum_controller_actions=maximum_actions,
        maximum_emulator_frames=maximum_frames,
        quote_resource_costs=True,
        prepare_capture_items=True,
        routed_storage_relief=True,
        trainer_funding=True,
        regional_trainer_funding=True,
        observed_trainer_funding=True,
        trainer_funding_target_cash=3_600,
        include_recovery_offers=False,
    )
    observed = RedBoundedPlayerObserver(
        native,
        actions,
        registered_objective=True,
        enumerate_bindings=router.enumerate,
    )()
    regional = enumerate_red_regional_acquisitions(
        native,
        live,
        actions,
        world,
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
    )
    # Regional candidates replace the legacy single preselected capture route.
    # Keep the ordinary one-per-kind question intact for emergency safety checks.
    ordinary = GoalBindingSet(
        tuple(
            GoalOpportunity(
                binding_ref=op.binding_ref,
                kind=op.kind,
                availability=GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.NO_LEGAL_TARGET,
            )
            if op.kind is GoalKind.ACQUIRE_SPECIES
            else op
            for op in observed.binding_set.opportunities
        ),
        tuple(b for b in observed.binding_set.bindings if b.kind is not GoalKind.ACQUIRE_SPECIES),
        allow_resource_variants=observed.binding_set.allow_resource_variants,
    )
    supplements = []
    for destination in regional:
        binding = destination.binding
        question = GoalBindingSet(
            tuple(
                binding.opportunity if op.kind is GoalKind.ACQUIRE_SPECIES else op
                for op in ordinary.opportunities
            ),
            (*ordinary.bindings, binding),
            allow_resource_variants=ordinary.allow_resource_variants,
        ).question(observed.situation)
        index = next(
            i
            for i, op in enumerate(question.opportunities)
            if op.binding_ref == binding.binding_ref
        )
        candidate = project_living_dex_goal_candidate(
            question,
            index,
            feature_version=model_feature_version,
            binding_ref=binding.binding_ref,
        )
        if candidate is None:
            raise ValueError("regional acquisition lacks a portable projection")
        supplements.append(supplemental_live_option(binding, candidate))
    league_funding = bind_autonomous_league_funding(
        native,
        actions,
        world,
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
    )
    if league_funding is not None:
        league_question = GoalBindingSet(
            tuple(
                op
                for op in ordinary.opportunities
                if op.kind is not GoalKind.RESUPPLY or op.availability is GoalAvailability.AVAILABLE
            )
            + (league_funding.opportunity,),
            (*ordinary.bindings, league_funding),
            allow_resource_variants=True,
        ).question(observed.situation)
        league_index = next(
            i
            for i, op in enumerate(league_question.opportunities)
            if op.binding_ref == league_funding.binding_ref
        )
        league_candidate = project_living_dex_goal_candidate(
            league_question,
            league_index,
            feature_version=model_feature_version,
            binding_ref=league_funding.binding_ref,
        )
        if league_candidate is None:
            raise ValueError("renewable League funding lacks a portable projection")
        supplements.append(supplemental_live_option(league_funding, league_candidate))
    economy = red_economy_snapshot(native.reader.read())
    if economy is None:
        raise ValueError("autonomous collection requires observed resources")
    options = build_red_live_option_set(
        situation=observed.situation,
        binding_set=ordinary,
        supplements=tuple(supplements),
        model_feature_version=model_feature_version,
        ordering_seed_sha256=ordering_seed_sha256,
        economy_snapshot=economy,
        target_cash=3_600,
    )
    if evolution.mechanic is RedGoalMechanic.TARGETED_ITEM_EVOLUTION:
        item_id = evolution.parameters["item_id"]
        assert isinstance(item_id, int)
        needs_shop = dict(native.reader.read().bag_items or ()).get(item_id, 0) == 0
        cost = buyable_evolution_stone(item_id).price if needs_shop else 0
        # The item-use goal owns a separate procurement stage. Its actual
        # prospective spend belongs in the policy input even though its goal
        # kind is EVOLVE, not the standalone RESUPPLY goal.
        options = replace(
            options,
            menu=replace(
                options.menu,
                candidates=tuple(
                    replace(
                        candidate, economy_offer=EconomyOffer(EconomyMode.OTHER, planned_spend=cost)
                    )
                    if candidate.features.kind is LivingDexOptionKind.EVOLVE
                    else candidate
                    for candidate in options.menu.candidates
                ),
            ),
        )
    return options
