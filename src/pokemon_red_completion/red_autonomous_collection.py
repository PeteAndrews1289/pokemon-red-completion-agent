"""Rebuild a mixed collection menu from each live state without a chosen route."""

from collections.abc import Callable
from dataclasses import replace

from .executor import CountingExecutor
from .goal_manager import GoalAvailability, GoalKind, GoalOpportunity, GoalUnavailableReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalBindingSet, GoalExecutionReport
from .living_dex_goal_policy import project_living_dex_goal_candidate
from .player_readiness import PlayerReadiness
from .red_autonomous_fishing import autonomous_fishing_options
from .red_autonomous_league_funding import bind_autonomous_league_funding
from .red_autonomous_safari import autonomous_safari_funding_quote, autonomous_safari_options
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
from .red_npc_trade_options import npc_trade_bindings
from .red_player_support import RedPlayerSupport
from .red_regional_acquisition import enumerate_red_regional_acquisitions
from .red_regional_trainer_funding import FundingGateTransit
from .red_resource_economy import red_economy_snapshot
from .red_resource_goal_router import RedResourceGoalRouter
from .red_scripted_gift import scripted_gift_bindings
from .red_trade_dependency_options import npc_trade_dependency_bindings
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
    include_league_funding: bool = True,
    include_game_corner: bool = False,
    include_coin_procurement: bool = False,
    allow_support: bool = False,
    readiness: PlayerReadiness | None = None,
    fishing_fast_transport: bool = False,
    funding_gate_transit: FundingGateTransit | None = None,
    additional_acquisitions: tuple[ExecutableGoalBinding, ...] = (),
    league_postgame_return: Callable[[], GoalExecutionReport] | None = None,
) -> RedLiveOptionSet | RedPlayerSupport:
    """Expose up to eight real capture destinations alongside ordinary goals.

    Capture destinations, stone targets and boxed level alternatives each retain
    their own executors. Mechanical execution remains deterministic support.
    No source/species identity is projected into policy features.
    """
    if type(include_league_funding) is not bool:
        raise ValueError("League funding scope must be an explicit boolean")
    if league_postgame_return is not None and (
        not include_league_funding or not callable(league_postgame_return)
    ):
        raise ValueError("League return requires explicit enabled funding and a callable")
    if type(fishing_fast_transport) is not bool:
        raise ValueError("fishing transport scope must be an explicit boolean")
    if type(include_game_corner) is not bool:
        raise ValueError("Game Corner scope must be an explicit boolean")
    if type(include_coin_procurement) is not bool or (
        include_coin_procurement and not include_game_corner
    ):
        raise ValueError("Coin procurement requires explicit enabled Game Corner scope")
    if not isinstance(additional_acquisitions, tuple) or any(
        not isinstance(binding, ExecutableGoalBinding)
        or binding.kind is not GoalKind.ACQUIRE_SPECIES
        for binding in additional_acquisitions
    ):
        raise ValueError("additional acquisitions require immutable acquisition bindings")
    if len({b.binding_ref for b in additional_acquisitions}) != len(additional_acquisitions):
        raise ValueError("additional acquisition bindings must be distinct")
    if funding_gate_transit is not None and not isinstance(
        funding_gate_transit, FundingGateTransit,
    ):
        raise ValueError("collection funding transit requires a typed bounded inventory")
    if type(allow_support) is not bool or (
        allow_support and not isinstance(readiness, PlayerReadiness)
    ):
        raise ValueError("explicit support scope requires actual player readiness")
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
    # An exhausted evolution category must not gate independent collection goals.
    # Keep the original transport declarations for per-target enumeration below.
    evolution_runtime = runtime
    profile = derive_direct_full_pokedex_profile(
        runtime.profile, live, world, require_evolution=False,
    )
    profile = bind_funding_fly_profile(
        bind_mart_funding_departure_profile(bind_composable_trainer_funding_profile(profile))
    )
    runtime = replace(runtime, profile=profile)
    evolution = next(
        (spec for spec in profile.providers if spec.kind is GoalKind.EVOLVE_SPECIES), None,
    )
    if evolution is None:
        native = runtime
    elif evolution.mechanic is RedGoalMechanic.TARGETED_ITEM_EVOLUTION:
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
    safari_quote = autonomous_safari_funding_quote(native, live, world)
    if safari_quote is not None:
        # Liquidity for either Mart capture items or single Safari admission.
        # This is liquidity for either alternative, NOT a declaration that both
        # purchases are jointly funded. Do not sum unrelated purchases.
        target_cash = max(target_cash, safari_quote.admission_cost)
    if include_coin_procurement:
        from .red_game_corner_goals import game_corner_funding_target_cash
        target_cash = max(target_cash, game_corner_funding_target_cash(native, world))
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
        funding_gate_transit=funding_gate_transit,
        trainer_funding_target_cash=target_cash,
        include_recovery_offers=True,
    )
    observed = RedBoundedPlayerObserver(
        native,
        actions,
        registered_objective=True,
        # Independent regional/target enumerators below replace these two
        # legacy kinds. Keep the complete local safety inventory, but do not
        # plan discarded capture/evolution transports first.
        enumerate_bindings=lambda observation: router.enumerate_routed_kinds(
            observation,
            frozenset(GoalKind) - {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES},
        ),
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
        evolution_runtime,
        live,
        actions,
        world,
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
    )
    evolutions += enumerate_red_level_evolutions(
        evolution_runtime, live, actions, world,
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
    acquisitions = tuple(destination.binding for destination in regional)
    acquisitions += scripted_gift_bindings(native, live, actions, world)
    acquisitions += additional_acquisitions
    acquisitions += npc_trade_dependency_bindings(
        native, live, actions, world, maximum_actions=maximum_actions,
        maximum_frames=maximum_frames, maximum_quanta=maximum_evolution_quanta,
    )
    acquisitions += npc_trade_bindings(
        native, live, actions, world,
        include_moving=getattr(native, "moving_npc_trades", False),
    )
    for binding in acquisitions:
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
    supplements.extend(autonomous_fishing_options(native, live, actions, world,
        **({} if not fishing_fast_transport else {"allow_fast_transport": True})))
    supplements.extend(autonomous_safari_options(native, live, actions, world))
    if include_game_corner:
        from .red_game_corner_goals import game_corner_options
        supplements.extend(game_corner_options(native,live,actions,world,
            situation=observed.situation,model_feature_version=model_feature_version,
            maximum_actions=maximum_actions,maximum_frames=maximum_frames))
        if include_coin_procurement:
            from .red_game_corner_goals import game_corner_coin_options
            supplements.extend(game_corner_coin_options(native,live,actions,world,
                situation=observed.situation,model_feature_version=model_feature_version,
                maximum_actions=maximum_actions,maximum_frames=maximum_frames))
    league_funding = bind_autonomous_league_funding(
        native,
        actions,
        world,
        maximum_actions=maximum_actions,
        maximum_frames=maximum_frames,
        **({} if league_postgame_return is None else {"postgame_return": league_postgame_return}),
    ) if include_league_funding else None
    if league_funding is not None:
        # Project this supplemental earning option in its own one-per-kind
        # question. The ordinary inventory can already contain both a Mart
        # purchase and finite trainer income; adding League income there would
        # violate the established resource-variant boundary. Keep those exact
        # ordinary executors for the final mixed menu and its safety checks.
        league_question = GoalBindingSet(
            tuple(
                op
                for op in ordinary.opportunities
                if op.kind is not GoalKind.RESUPPLY
            )
            + (league_funding.opportunity,),
            (*tuple(b for b in ordinary.bindings if b.kind is not GoalKind.RESUPPLY),
             league_funding),
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
    executable = (*ordinary.bindings, *(s.binding for s in supplements))
    if allow_support and len(executable) == 1:
        binding = executable[0]
        # Use the already enumerated executor. Re-enumerating an earlier profile
        # can produce a different quote/fingerprint and is not the same offer.
        return RedPlayerSupport(
            GoalBindingSet(
                tuple(o for o in ordinary.opportunities if o.binding_ref != binding.binding_ref)
                + (binding.opportunity,),
                (binding,), allow_resource_variants=ordinary.allow_resource_variants,
            ), readiness,
        )
    return build_red_live_option_set(
        situation=observed.situation,
        binding_set=ordinary,
        supplements=tuple(supplements),
        model_feature_version=model_feature_version,
        ordering_seed_sha256=ordering_seed_sha256,
        economy_snapshot=economy,
        target_cash=target_cash,
        readiness=readiness,
    )
