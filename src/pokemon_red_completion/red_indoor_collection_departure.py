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

from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort
from pokemon_red_completion.goal_manager import (
    GoalFailureReason,
    GoalUnavailableReason,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.observation import OverworldMovementMode
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_dig_recovery import execute_dig_escape, plan_dig_escape
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
    _MAX_ROUTE_SCRIPTED_DIALOGUES,
    _ROUTE_LIMITS,
    _supported_plan,
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
from pokemon_red_completion.red_safari_exit import (
    RedSafariDepartureInterruptionHandler,
    RedSafariExitDialogueHandler,
    normalize_active_safari_exit_plan,
    safari_departure_within_steps,
)
from pokemon_red_completion.route_executor import InterruptionHandler, TraversalObserver
from pokemon_red_completion.route_plan import RoutePlanningError
from pokemon_red_completion.routed_semantic_goal import (
    FreshDestinationGoalOffer,
    RoutedSemanticBudgetCheckpoint,
    RoutedSemanticGoalComposer,
    RoutedSemanticGoalError,
    RoutedSemanticGoalLimits,
    RoutedSemanticRouteBinding,
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
        spec.mechanic
        not in {
            RedGoalMechanic.TARGETED_LEVEL_EVOLUTION,
            RedGoalMechanic.TARGETED_ITEM_EVOLUTION,
            RedGoalMechanic.WILD_CORRIDOR_CAPTURE,
            RedGoalMechanic.MART_RESUPPLY,
        }
        or spec.parameters.get("fly_transport") is not True
        or spec.parameters.get("indoor_fly_departure") is not True
    ):
        return None

    runtime, actions = router.runtime, router.actions
    reader = runtime.reader
    raw, start = fresh.observation.raw, fresh.traversal
    ordinary_surf = getattr(runtime, "collection_surf_departure", False) is True
    safari_surf = getattr(runtime, "safari_departure_surf", False) is True
    in_safari = (reader.read_safari_session_state().in_safari_zone
                 if ordinary_surf or safari_surf else False)
    water_departure = (ordinary_surf and not in_safari and start.mode == "water"
                       and "move:surf" in start.capabilities)

    if (
        not fresh.observation.input_ready
        or raw.battle_state
        or start.interruption is not None
        or start.map_id < 0x25
        or (start.mode != "land" and not water_departure)
        or reader.read_overworld_movement_mode() is not (
            OverworldMovementMode.SURFING if water_departure else OverworldMovementMode.WALKING)
        or reader.read_bottom_dialogue_box_visible()
        or reader.read_pending_trainer_battle_identity() is not None
        or reader.read_fly_menu_state() is not None
    ):
        return None

    escape = (
        plan_dig_escape(router.world, reader, raw, start)
        if getattr(runtime, "collection_dig_departure", False) is True else None
    )
    if escape is None and (
        start.last_outside_map is None or not (0 <= start.last_outside_map <= 0x24)
        or start.last_outside_map == 0x0B
    ):
        return None

    allow_surf = ("move:surf" in start.capabilities
                  and ((ordinary_surf and not in_safari) or (safari_surf and in_safari)))

    def executable_start(snapshot):
        return replace(snapshot, capabilities=frozenset(
            c for c in snapshot.capabilities
            if not c.startswith("move:") or (allow_surf and c == "move:surf")
        ))

    plan = None
    try:
        # Advertise only wired actions: walking by default, plus explicitly
        # opted-in live Surf. Paid Safari uses its separate step guards and
        # permission; ordinary cave permission never enables a paid exit.
        # Cut stays excluded.
        if escape is None:
            assert start.last_outside_map is not None
            # A compiled collection router can retain the cartridge layout.
            # Door switches and other live indoor changes must govern admission
            # as well as replanning after movement has already failed.
            world = router.world.with_current_observation(reader)
            if reader.read() != raw:
                return None
            router = replace(router, world=world)
            walking_start = executable_start(start)
            plan = router.world.plan_feasible_to_map(walking_start, start.last_outside_map)
    except RoutePlanningError:
        return None

    safari_exit_plan = normalize_active_safari_exit_plan(plan) if plan is not None else None
    if safari_exit_plan is not None:
        plan = safari_exit_plan

    if plan is not None and (
        not plan.steps
        or not _supported_plan(plan, allow_surf=allow_surf)
        or plan.terminal_map != start.last_outside_map
        or not (0 <= plan.terminal_map <= 0x24)
        or plan.terminal_map == 0x0B
        or (plan.terminal_mode is not None and plan.terminal_mode != "land")
    ):
        return None

    if safari_exit_plan is not None and not safari_departure_within_steps(safari_exit_plan, reader):
        return None

    if escape is not None:
        terminal_map, terminal_at = escape.anchor, escape.landing
        terminal_boundary = RedRoutedSemanticBoundary(terminal_map, terminal_at, "land")
        departure_effort = 0.05
    else:
        assert plan is not None
        terminal_map, terminal_at = plan.terminal_map, plan.terminal_at
        terminal_boundary = RedRoutedSemanticBoundary.from_plan(plan)
        departure_effort = len(plan.steps) / 1000
    terminal_y, terminal_x = terminal_at
    projected_raw = replace(
        raw,
        map_id=terminal_map,
        player_y=terminal_y,
        player_x=terminal_x,
    )
    projected_obs = replace(
        fresh.observation,
        raw=projected_raw,
    )
    projected_traversal = replace(
        start,
        map_id=terminal_map,
        at=terminal_at,
        last_outside_map=terminal_map,
        occupied=frozenset(),
        mode="land",
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
        router, spec, provider, projected_fresh, traversal,
        **({"land_departure_projection": True} if water_departure else {}),
    )
    if disposable_flight is None:
        return None

    origin = red_living_dex_setup_fresh_observation_sha256(fresh)
    meter = RedRoutedSemanticBudgetMeter(actions, runtime.emulator)
    started: list[RoutedSemanticBudgetCheckpoint] = []

    from pokemon_red_completion.red_travel_capture_runtime import bind_travel_capture_handler

    route_handler: InterruptionHandler = guarded_collection_route_handler(
        actions,
        reader,
        route_name="indoor collection departure",
        maximum_scripted_dialogues=_MAX_ROUTE_SCRIPTED_DIALOGUES,
    )
    if safari_exit_plan is not None:
        route_handler = RedSafariExitDialogueHandler(actions, reader, route_handler)
        route_handler = RedSafariDepartureInterruptionHandler(
            runtime.emulator, actions, reader, route_handler
        )

    def replan(request):
        walking_request = replace(request, current=executable_start(request.current))
        replacement = router._replan(walking_request, allow_surf=allow_surf)
        if safari_exit_plan is None:
            return replacement
        replacement = normalize_active_safari_exit_plan(replacement) or replacement
        if not safari_departure_within_steps(replacement, reader):
            raise RoutedSemanticGoalError("Safari exit exceeds remaining paid steps")
        return replacement

    # Indoor departure must retain the same explicitly supplied learned
    # interruption owner as ordinary walking and Fly onward transport.
    # The wrapper only binds callbacks here; it issues no model query/input.
    travel_handler = bind_travel_capture_handler(router, spec, route_handler)
    if plan is not None and router.interruption_handler_wrapper is not None:
        travel_handler = router.interruption_handler_wrapper(travel_handler, spec)
    transport = None if plan is None else RedSemanticTransportRoute(
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
        interruption_handler=travel_handler,
        replanner=replan,
        field_actions=Gen1FieldMovePort(actions, reader, runtime.emulator) if allow_surf else None,
        route_limits=_ROUTE_LIMITS,
        prepare_departure=lambda: prepare_center_departure(actions, reader),
    )
    if transport is not None:
        departure = transport.route_binding()
    else:
        assert escape is not None
        escaped_terminal = []

        def execute_escape():
            checkpoint = meter.checkpoint()
            evidence = execute_dig_escape(router.world, reader, runtime.emulator, actions, escape)
            escaped_terminal.append(runtime.emulator.save_state_bytes())
            after_escape = meter.checkpoint()
            return GoalExecutionReport(
                after_escape.controller_actions - checkpoint.controller_actions,
                after_escape.emulator_frames - checkpoint.emulator_frames,
                {"dig_escape": evidence, "learned_navigation": False},
            )

        def verify_escape(_report):
            passed = (
                len(escaped_terminal) == 1
                and runtime.emulator.save_state_bytes() == escaped_terminal[0]
                and terminal_boundary.matches_traversal(traversal.observe())
                and terminal_boundary.matches_goal_observation(runtime.adapter.observe())
            )
            return (GoalVerification.succeeded() if passed else
                    GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED))

        departure = RoutedSemanticRouteBinding(
            "red-indoor-dig-route:" + spec.configuration_sha256,
            origin, terminal_boundary.sha256, execute_escape, verify_escape,
        )

    def execute_departure() -> GoalExecutionReport:
        current = FreshRedGoalObservation("0" * 64, runtime.adapter.observe(), traversal.observe())
        if (
            current.observation != fresh.observation
            or current.traversal != fresh.traversal
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
        if not terminal_boundary.matches_traversal(
            actual.traversal
        ) or not terminal_boundary.matches_goal_observation(actual.observation):
            return FreshDestinationGoalOffer.unavailable(
                observation_sha256=actual.observation_sha256,
                terminal_boundary_sha256=terminal_boundary.sha256,
                kind=spec.kind,
                reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
        now = meter.checkpoint()
        remaining_actions = (
            router.maximum_controller_actions
            - now.controller_actions
            + started[0].controller_actions
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
            router,
            maximum_controller_actions=remaining_actions,
            maximum_emulator_frames=remaining_frames,
        )
        actual_flight = bind_collection_fly(remaining_router, spec, provider, actual, traversal)
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

    estimated_effort = min(1.0, disposable_flight.estimated_effort + departure_effort)
    estimated_risk = disposable_flight.estimated_risk
    if (plan is not None and getattr(router, "quote_capture_route_work", False)
            and spec.mechanic is RedGoalMechanic.WILD_CORRIDOR_CAPTURE):
        from pokemon_red_completion.red_resource_goal_router import (
            ordinary_route_work_quote, route_work_estimates,
        )

        work_quote = ordinary_route_work_quote(plan, fresh.observation, router.world.rom, reader)
        estimated_effort, departure_risk = route_work_estimates(
            estimated_effort, work_quote["ordinary_trainers_crossed"]
        )
        estimated_risk = min(1.0, estimated_risk + departure_risk - 0.18)
        actions.record_diagnostic_event("capture_route_work_quote", dict(
            source_id=str(spec.parameters["source_id"]), **work_quote,
            transport_leg="indoor_departure", estimated_effort=estimated_effort,
            estimated_risk=estimated_risk,
            policy_features="existing_normalized_effort_and_risk",
        ))
    composer = RoutedSemanticGoalComposer(
        binding_ref=(
            "red-indoor-collection-departure-goal:" + origin + ":" + spec.configuration_sha256
        ),
        destination_kind=spec.kind,
        estimated_effort=estimated_effort,
        estimated_risk=estimated_risk,
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
