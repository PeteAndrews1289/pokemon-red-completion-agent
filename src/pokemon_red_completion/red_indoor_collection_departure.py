"""Indoor departure composition for collection goals requiring Fly transport.

When the learner or setup pipeline selects a collection destination (capture or
evolution) while indoors (such as a Pokemon Center or Mart), direct flight is
prohibited by the cartridge. This module plans a truthful indoor exit walk to the
declared last outside map, confirms projected eligibility with the existing Fly
binder without executing it, and composes the indoor departure walk with fresh
outdoor Fly transport under one unified budget.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from pokemon_red_completion.goal_manager import (
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport
from pokemon_red_completion.observation import OverworldMovementMode
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalMechanic,
    RedGoalProviderSpec,
)
from pokemon_red_completion.red_goal_manager import RedGoalBindingProvider
from pokemon_red_completion.red_goal_skills import prepare_center_departure
from pokemon_red_completion.red_living_dex_setup_source import (
    red_living_dex_setup_fresh_observation_sha256,
)
from pokemon_red_completion.red_resource_goal_router import (
    _ROUTE_LIMITS,
    _walking_plan,
)
from pokemon_red_completion.red_routed_recovery import (
    guarded_collection_route_handler,
)
from pokemon_red_completion.red_routed_semantic_goal import (
    FreshRedGoalObservation,
    RedRoutedSemanticBoundary,
    RedRoutedSemanticBudgetMeter,
    RedSemanticTransportRoute,
)
from pokemon_red_completion.route_executor import TraversalObserver
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.routed_semantic_goal import (
    FreshDestinationGoalOffer,
    RoutedSemanticBudgetCheckpoint,
    RoutedSemanticGoalComposer,
    RoutedSemanticGoalError,
    RoutedSemanticGoalLimits,
)

if TYPE_CHECKING:
    from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter


def bind_indoor_collection_departure(
    router: RedResourceGoalRouter,
    spec: RedGoalProviderSpec,
    provider: RedGoalBindingProvider,
    fresh: FreshRedGoalObservation,
    traversal: TraversalObserver,
) -> ExecutableGoalBinding | None:
    """Offer an indoor exit walk composed with existing Fly transport.

    Applies only when the player is indoors (map_id >= 0x25) with a valid
    outdoor last_outside_map, eligible collection mechanic, and explicit
    fly_transport parameter.

    During qualification, plans a feasible indoor-to-outdoor walking route,
    projects the outdoor arrival observation, and confirms Fly transport
    availability and effort via the existing bind_collection_fly binder.
    The projected flight is never executed.

    When executed, the indoor walking route runs under RedSemanticTransportRoute,
    settles menus, verifies the exact outdoor arrival boundary, takes a fresh
    coherent observation, and rebinds Fly transport to the final destination.
    """
    from pokemon_red_completion.red_collection_fly import bind_collection_fly

    if (
        spec.mechanic not in {
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
            RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
        }
        or spec.parameters.get("fly_transport") is not True
    ):
        return None

    runtime, actions = router.runtime, router.actions
    reader = runtime.reader
    raw, start = fresh.observation.raw, fresh.traversal

    if (
        not fresh.observation.input_ready
        or raw.battle_state
        or start.interruption is not None
        or start.map_id < 0x25
        or start.mode != "land"
        or start.last_outside_map is None
        or not (0 <= start.last_outside_map <= 0x24)
        or start.last_outside_map == 0x0B
        or reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING
        or reader.read_bottom_dialogue_box_visible()
        or reader.read_pending_trainer_battle_identity() is not None
        or reader.read_fly_menu_state() is not None
    ):
        return None

    try:
        plan = router.world.plan_feasible_to_map(start, start.last_outside_map)
    except RoutePlanningError:
        return None

    if (
        not plan.steps
        or not _walking_plan(plan)
        or plan.terminal_map != start.last_outside_map
        or not (0 <= plan.terminal_map <= 0x24)
        or plan.terminal_map == 0x0B
        or (plan.terminal_mode is not None and plan.terminal_mode != "land")
    ):
        return None

    terminal_y, terminal_x = plan.terminal_at
    projected_raw = replace(
        raw,
        map_id=plan.terminal_map,
        player_y=terminal_y,
        player_x=terminal_x,
    )
    projected_obs = replace(
        fresh.observation,
        raw=projected_raw,
    )
    projected_traversal = replace(
        start,
        map_id=plan.terminal_map,
        at=plan.terminal_at,
        last_outside_map=plan.terminal_map,
        occupied=frozenset(),
    )
    projected_fresh = FreshRedGoalObservation(
        observation_sha256="0" * 64,
        observation=projected_obs,
        traversal=projected_traversal,
    )
    projected_fresh = replace(
        projected_fresh,
        observation_sha256=red_living_dex_setup_fresh_observation_sha256(projected_fresh),
    )

    disposable_flight = bind_collection_fly(
        router, spec, provider, projected_fresh, traversal
    )
    if disposable_flight is None:
        return None

    origin = red_living_dex_setup_fresh_observation_sha256(fresh)
    terminal_boundary = RedRoutedSemanticBoundary.from_plan(plan)
    meter = RedRoutedSemanticBudgetMeter(actions, runtime.emulator)
    started: list[RoutedSemanticBudgetCheckpoint] = []

    transport = RedSemanticTransportRoute(
        binding_ref="red-indoor-departure-route:" + spec.configuration_sha256,
        origin_observation_sha256=origin,
        planner_binding_sha256=canonical_sha256(
            {
                "schema": "pokemon.red.indoor-collection-departure.v1",
                "profile": runtime.profile.profile_sha256,
            }
        ),
        plan=plan,
        actions=actions,
        traversal_observer=traversal,
        emulator=runtime.emulator,
        interruption_handler=guarded_collection_route_handler(
            actions, reader, route_name="indoor collection departure"
        ),
        replanner=router._replan,
        route_limits=_ROUTE_LIMITS,
        prepare_departure=lambda: prepare_center_departure(actions, reader),
    )
    departure = transport.route_binding()

    def execute_departure() -> GoalExecutionReport:
        current = FreshRedGoalObservation(
            "0" * 64, runtime.adapter.observe(), traversal.observe()
        )
        if (
            current.observation != fresh.observation or current.traversal != fresh.traversal
            or red_living_dex_setup_fresh_observation_sha256(current) != origin
        ):
            raise RoutedSemanticGoalError("indoor departure origin changed before input")
        started.append(meter.checkpoint())
        return departure.execute()

    def bind_destination() -> FreshDestinationGoalOffer:
        current_obs = runtime.adapter.observe()
        current_trav = traversal.observe()
        actual = FreshRedGoalObservation("0" * 64, current_obs, current_trav)
        actual = replace(
            actual,
            observation_sha256=red_living_dex_setup_fresh_observation_sha256(actual),
        )
        if (
            not terminal_boundary.matches_traversal(actual.traversal)
            or not terminal_boundary.matches_goal_observation(actual.observation)
        ):
            return FreshDestinationGoalOffer.unavailable(
                observation_sha256=actual.observation_sha256,
                terminal_boundary_sha256=terminal_boundary.sha256,
                kind=spec.kind,
                reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        now = meter.checkpoint()
        remaining_actions = (
            router.maximum_controller_actions
            - now.controller_actions + started[0].controller_actions
        )
        remaining_frames = (
            router.maximum_emulator_frames - now.emulator_frames + started[0].emulator_frames
        )
        if remaining_actions <= 0 or remaining_frames <= 0:
            return FreshDestinationGoalOffer.unavailable(
                observation_sha256=actual.observation_sha256,
                terminal_boundary_sha256=terminal_boundary.sha256,
                kind=spec.kind,
                reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        remaining_router = replace(
            router, maximum_controller_actions=remaining_actions,
            maximum_emulator_frames=remaining_frames,
        )
        actual_flight = bind_collection_fly(
            remaining_router, spec, provider, actual, traversal
        )
        if actual_flight is None:
            return FreshDestinationGoalOffer.unavailable(
                observation_sha256=actual.observation_sha256,
                terminal_boundary_sha256=terminal_boundary.sha256,
                kind=spec.kind,
                reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        if actual_flight.kind is not spec.kind:
            return FreshDestinationGoalOffer.unavailable(
                observation_sha256=actual.observation_sha256,
                terminal_boundary_sha256=terminal_boundary.sha256,
                kind=spec.kind,
                reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
            expected_source = "pokemon.red:acquisition:" + str(spec.parameters["source_id"])
            if actual_flight.search_source_ref != expected_source:
                return FreshDestinationGoalOffer.unavailable(
                    observation_sha256=actual.observation_sha256,
                    terminal_boundary_sha256=terminal_boundary.sha256,
                    kind=spec.kind,
                    reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
                )
        return FreshDestinationGoalOffer.available(
            observation_sha256=actual.observation_sha256,
            terminal_boundary_sha256=terminal_boundary.sha256,
            binding=actual_flight,
        )

    composer = RoutedSemanticGoalComposer(
        binding_ref=(
            "red-indoor-collection-departure-goal:" + origin + ":" + spec.configuration_sha256
        ),
        destination_kind=spec.kind,
        estimated_effort=min(1.0, disposable_flight.estimated_effort + len(plan.steps) / 1000),
        estimated_risk=disposable_flight.estimated_risk,
        route=replace(departure, execute=execute_departure),
        bind_fresh_destination=bind_destination,
        budget_meter=meter,
        limits=RoutedSemanticGoalLimits(
            router.maximum_controller_actions,
            router.maximum_emulator_frames,
        ),
    )
    binding = composer.binding()
    if spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE:
        binding = replace(
            binding,
            search_source_ref="pokemon.red:acquisition:" + str(spec.parameters["source_id"]),
        )
    return binding


__all__ = ["bind_indoor_collection_departure"]
