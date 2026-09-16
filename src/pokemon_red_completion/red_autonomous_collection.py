"""Rebuild a mixed collection menu from each live state without a chosen route."""

from dataclasses import replace

from .executor import CountingExecutor
from .goal_manager import GoalAvailability, GoalKind, GoalOpportunity, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet
from .living_dex_goal_policy import project_living_dex_goal_candidate
from .red_autonomous_fishing import autonomous_fishing_options
from .red_autonomous_league_funding import bind_autonomous_league_funding
from .red_autonomous_safari import autonomous_safari_options
from .red_bounded_player import RedBoundedPlayerObserver
from .red_capture_funding_budget import red_capture_funding_budget
from .red_full_pokedex_direct_profile import derive_direct_full_pokedex_profile
from .red_goal_context import RedGoalContextRuntime
from .red_goal_context_profile import (
    RedGoalMechanic,
    bind_composable_trainer_funding_profile,
    bind_funding_fly_profile,
    bind_mart_funding_departure_profile,
)
from .red_goal_skills import RedMartResupplyGoalProvider
from .red_item_evolution_options import enumerate_red_item_evolutions
from .red_level_evolution_options import enumerate_red_level_evolutions
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
from .resource_economy_observation import EconomySnapshot
from .strategic_navigation_scenario_runtime import StrategicScenarioRouteWorld


def autonomous_capture_funding_target_cash(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    economy: EconomySnapshot,
) -> int:
    """Use an observed capture purchase, never a standing cash accumulation target."""
    if not any(spec.kind is GoalKind.RESUPPLY for spec in runtime.profile.providers):
        return economy.cash
    provider = runtime.provider_for(GoalKind.RESUPPLY, actions)
    if not isinstance(provider, RedMartResupplyGoalProvider):
        raise ValueError("autonomous funding requires a supported Mart provider")
    budget = red_capture_funding_budget(
        runtime.adapter.observe(),
        provider,
    )
    # A blocked/unsupported purchase is not an excuse to earn toward an
    # invented reserve. With a real quote, fund only its unmet amount.
    return economy.cash if budget is None else budget.target_cash


def autonomous_evolution_continuation_bindings(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    maximum_actions: int,
    maximum_frames: int,
    maximum_quanta: int,
) -> tuple[ExecutableGoalBinding, ...]:
    """Discover live level evolutions without constructing unrelated capture routes.

    This is a private execution inventory for an already-recorded model goal,
    never a new policy menu or a teacher-selected target. The caller checks
    unchanged state and requires one exact configuration fingerprint match.
    """
    if runtime.registration_policy is None:
        raise ValueError("continuation requires a registration policy")
    runtime = replace(
        runtime,
        adapter=replace(runtime.adapter, registration_policy=runtime.registration_policy),
    )
    live = runtime.adapter.observe()
    return tuple(
        option.binding for option in enumerate_red_level_evolutions(
            runtime, live, actions, world,
            maximum_actions=maximum_actions,
            maximum_frames=maximum_frames,
            maximum_quanta=maximum_quanta,
        )
    )


def autonomous_collection_options(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld,
    *,
    model_feature_version: int,
    ordering_seed_sha256: str,
    maximum_actions: int = 30_000,
    maximum_frames: int = 3_000_000,
    maximum_evolution_quanta: int = 128,
) -> RedLiveOptionSet:
    """Expose up to eight real capture destinations alongside ordinary goals.

    Capture destinations, stone targets and boxed level alternatives each retain
    their own executors. Mechanical execution remains deterministic support.
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
            maximum_quanta=maximum_evolution_quanta,
            allow_cross_box=True,
        )
    economy = red_economy_snapshot(native.reader.read())
    if economy is None:
        raise ValueError("autonomous collection requires observed resources")
    target_cash = autonomous_capture_funding_target_cash(native, actions, economy)
    router = RedResourceGoalRouter(
        native,
        actions,
        world,
        maximum_controller_actions=maximum_actions,
        maximum_emulator_frames=maximum_frames,
        quote_resource_costs=True,
        prepare_capture_items=True,
        routed_storage_relief=True,
        routed_recovery=True,
        trainer_funding=True,
        regional_trainer_funding=True,
        observed_trainer_funding=True,
        trainer_funding_target_cash=target_cash,
        include_recovery_offers=True,
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
    evolutions = enumerate_red_item_evolutions(
        runtime,
        live,
        actions,
        world,
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
    )
    evolutions += enumerate_red_level_evolutions(
        runtime, live, actions, world,
        maximum_actions=maximum_actions, maximum_frames=maximum_frames,
        maximum_quanta=maximum_evolution_quanta,
    )
    replaced_kinds = {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}
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
            if op.kind in replaced_kinds
            else op
            for op in observed.binding_set.opportunities
        ),
        tuple(b for b in observed.binding_set.bindings if b.kind not in replaced_kinds),
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
    for target in evolutions:
        binding = target.binding
        # The ordinary API remains one-per-kind. Project each target in its own
        # question, then join only at the multi-binding live-menu boundary.
        question = GoalBindingSet(
            tuple(
                binding.opportunity if op.kind is GoalKind.EVOLVE_SPECIES else op
                for op in ordinary.opportunities
            ),
            (
                *tuple(b for b in ordinary.bindings if b.kind is not GoalKind.EVOLVE_SPECIES),
                binding,
            ),
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
            raise ValueError("evolution lacks a portable projection")
        if target.execution_effort is not None:
            candidate = replace(candidate, features=replace(
                candidate.features, execution_effort=target.execution_effort,
            ))
        supplements.append(
            supplemental_live_option(
                binding,
                replace(candidate, economy_offer=target.economy_offer),
            )
        )
    supplements.extend(autonomous_fishing_options(native, live, actions, world))
    supplements.extend(autonomous_safari_options(native, live, actions, world))
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
    return build_red_live_option_set(
        situation=observed.situation,
        binding_set=ordinary,
        supplements=tuple(supplements),
        model_feature_version=model_feature_version,
        ordering_seed_sha256=ordering_seed_sha256,
        economy_snapshot=economy,
        target_cash=target_cash,
    )
