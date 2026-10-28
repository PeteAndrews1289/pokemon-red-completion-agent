"""Separate a model-selected story destination from preparation and gym combat."""

from dataclasses import replace
from hashlib import sha256

from .gen1_field_moves import surf_permission
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector
from .gen1_traversal import cut_capabilities, surf_capabilities
from .global_router import GlobalRouterError, find_macro_path
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import EventFlag, ItemId, MapId, event_flag_is_set, semantic_facts
from .provenance import canonical_sha256
from .red_player_cash_exposure import certified_cash_safe_transition
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot
from .red_story_map_frontier import story_frontier_target
from .route_plan import RoutePlanningError

# Adapter identities only. Neither names nor locations enter policy features.
DESTINATIONS = {
    "reach_pewter": int(MapId.PEWTER_CITY),
    "defeat_brock": int(MapId.PEWTER_GYM),
    "reach_cerulean": int(MapId.CERULEAN_CITY),
    "defeat_misty": int(MapId.CERULEAN_GYM),
    "help_bill": int(MapId.BILLS_HOUSE),
    "reach_vermilion": int(MapId.VERMILION_CITY),
    "obtain_cut": int(MapId.SS_ANNE_CAPTAINS_ROOM),
    "defeat_surge": int(MapId.VERMILION_GYM),
    "reach_lavender": int(MapId.LAVENDER_TOWN),
    "reach_celadon": int(MapId.CELADON_CITY),
    "defeat_erika": int(MapId.CELADON_GYM),
    "clear_rocket_hideout": int(MapId.ROCKET_HIDEOUT_B4F),
    "obtain_silph_scope": int(MapId.ROCKET_HIDEOUT_B4F),
    "rescue_fuji": int(MapId.POKEMON_TOWER_7F),
    # Entry boundary of the existing first Silph component, not liberation.
    "liberate_silph": int(MapId.SAFFRON_POKECENTER),
    "reach_saffron": int(MapId.SAFFRON_CITY),
    "reach_fuchsia": int(MapId.FUCHSIA_CITY),
    "obtain_surf": int(MapId.FUCHSIA_POKECENTER),
    "obtain_strength": int(MapId.FUCHSIA_POKECENTER),
    "reach_cinnabar": int(MapId.CINNABAR_ISLAND),
    "obtain_secret_key": int(MapId.POKEMON_MANSION_B1F),
    "defeat_koga": int(MapId.FUCHSIA_GYM),
    "defeat_sabrina": int(MapId.SAFFRON_GYM),
    "defeat_blaine": int(MapId.CINNABAR_GYM),
    "defeat_giovanni": int(MapId.VIRIDIAN_GYM),
    # First League staging only; arrival does not defeat Lorelei.
    "defeat_lorelei": int(MapId.INDIGO_PLATEAU),
}
ARRIVAL_OBJECTIVES = frozenset(
    {
        "reach_pewter",
        "reach_cerulean",
        "reach_vermilion",
        "reach_lavender",
        "reach_celadon",
        "reach_saffron",
        "reach_fuchsia",
        "reach_cinnabar",
    }
)


def story_destination_map(objective_id, raw):
    """Resolve an unfinished native phase, never choose a different objective."""
    destination = DESTINATIONS[objective_id]
    if objective_id == "rescue_fuji":
        events = getattr(raw, "event_flags", None)
        bag = getattr(raw, "bag_items", None)
        if (
            events is not None
            and len(events) * 8 > int(EventFlag.RESCUED_MR_FUJI_WORLD)
            and bag is not None
            and event_flag_is_set(events, int(EventFlag.RESCUED_MR_FUJI))
            and event_flag_is_set(events, int(EventFlag.RESCUED_MR_FUJI_WORLD))
            and not event_flag_is_set(events, int(EventFlag.GOT_POKE_FLUTE))
            and not dict(bag).get(int(ItemId.POKE_FLUTE))
        ):
            # The model may leave to heal after the rescue but before the gift.
            # Both native rescue flags put Fuji at home; do not route back to
            # the now-empty Tower. Arrival still cannot claim the flute.
            destination = int(MapId.MR_FUJIS_HOUSE)
    return destination


def story_travel_binding(
    runtime,
    actions,
    *,
    objective_id,
    route,
    intermediate_map=None,
    stop_at_map_boundary=False,
    frontier=False,
    destination_at=None,
    route_destination_at=None,
    certify_cash_approach=True,
    allow_surf=False,
):
    """Plan a legal destination, never auto-train, fight a leader or buy supplies."""
    if objective_id not in DESTINATIONS:
        raise ValueError("undeclared player story destination")
    if type(stop_at_map_boundary) is not bool:
        raise TypeError("map-boundary scope must be explicit")
    if type(certify_cash_approach) is not bool:
        raise TypeError("cash-approach certification scope must be explicit")
    if type(allow_surf) is not bool:
        raise TypeError("story Surf transport scope must be boolean")
    if allow_surf and getattr(route, "allow_surf", False) is not True:
        raise ValueError("story Surf quote requires a Surf-enabled native executor")
    if type(frontier) is not bool or (frontier and intermediate_map is not None):
        raise ValueError("frontier and fixed intermediate scopes differ")
    if destination_at is not None and (
        frontier
        or intermediate_map is not None
        or objective_id in ARRIVAL_OBJECTIVES
        or not isinstance(destination_at, tuple)
        or len(destination_at) != 2
        or any(type(v) is not int or v < 0 for v in destination_at)
    ):
        raise ValueError("local story approach requires an explicit nonarrival target")
    if route_destination_at is not None and (
        destination_at is not None
        or frontier
        or intermediate_map is not None
        or stop_at_map_boundary
        or objective_id in ARRIVAL_OBJECTIVES
        or not isinstance(route_destination_at, tuple)
        or len(route_destination_at) != 2
        or any(type(v) is not int or v < 0 for v in route_destination_at)
    ):
        raise ValueError("exact story route requires an explicit complete nonarrival scope")
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    graph = runtime.adapter.graph
    objective = graph.objective(objective_id)
    if objective_id not in {o.id for o in graph.available_objectives(before.game_state)}:
        return None
    raw = before.raw
    final_destination = story_destination_map(objective_id, raw)
    if (
        objective_id == "help_bill"
        and raw.map_id == int(MapId.CERULEAN_CITY)
        and not event_flag_is_set(raw.event_flags, int(EventFlag.BEAT_CERULEAN_RIVAL))
    ):
        # The coordinate-triggered rival is not an ordinary sight hazard. Its
        # separately selected combat binding must own this unavoidable gate.
        return None
    if intermediate_map is not None and (
        type(intermediate_map) is not int
        or not 0 <= intermediate_map <= 255
        or intermediate_map == final_destination
    ):
        raise ValueError("intermediate story boundary differs")
    destination = final_destination if intermediate_map is None else intermediate_map
    completes_objective = intermediate_map is None and objective_id in ARRIVAL_OBJECTIVES
    if raw.map_id == destination and destination_at is None:
        return None
    if destination_at is not None and raw.map_id != destination:
        return None
    # The legacy target remains local-only. Cross-map callers opt into a full
    # source-to-coordinate quote, never just replace an unquoted map endpoint.
    if route_destination_at is not None and raw.map_id == destination:
        return None
    exact_at = destination_at if destination_at is not None else route_destination_at
    if (
        not raw.party_hp
        or not any(raw.party_hp)
        or raw.player_money is None
        or raw.bag_items is None
    ):
        return None

    from .red_training_ground_route import RedVermilionGroundTransition

    if (
        not stop_at_map_boundary
        and raw.map_id != destination
        and isinstance(route, RedVermilionGroundTransition)
    ):
        from .red_player_fly import _noncombat_fly_world

        # A complete noncombat quote must respect known future trainer lanes.
        # Keep this projection in the executor and its Cut rebuilds too. A
        # blocked quote leaves frontier travel and combat to separate choices.
        route = replace(
            route, route_world=_noncombat_fly_world(route.route_world, raw)
        )

    def field_capabilities(raw):
        known = cut_capabilities(raw)
        if allow_surf:
            known |= surf_capabilities(
                raw, surf_allowed=surf_permission(runtime.emulator, raw).allowed
            )
        return known

    observer = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=field_capabilities if allow_surf else cut_capabilities,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    )
    try:
        start = observer.observe()
        if (
            isinstance(route, RedVermilionGroundTransition)
            and intermediate_map is None and exact_at is None
        ):
            from .red_player_story_fly import story_fly_binding

            flight = story_fly_binding(
                runtime, actions, objective_id=objective_id,
                final_destination=final_destination, route=route, start=start,
                before=before, lesson=lesson,
                arrival_objective=objective_id in ARRIVAL_OBJECTIVES,
                allow_surf=allow_surf,
            )
            if flight is not None:
                return flight
        if exact_at is not None:
            if raw.map_id == destination and start.at == exact_at:
                return None
            at = exact_at
        if frontier:
            destination, at = story_frontier_target(
                route.route_world, start, final_destination
            )
            completes_objective = (
                objective_id in ARRIVAL_OBJECTIVES and destination == final_destination
            )
        if intermediate_map is not None:
            # Topology establishes relevance, not current feasibility. Later
            # obstacles must not prevent a verified earlier regional endpoint.
            corridor = find_macro_path(
                route.route_world.macro_graph,
                start.map_id,
                final_destination,
                last_outside=start.last_outside_map,
            )
            if intermediate_map not in corridor.maps:
                raise ValueError("intermediate boundary is not on the planned story route")
        plan = route.route_world.plan_feasible_to_map(
            start,
            destination,
            **({"goal_at": at} if frontier or exact_at is not None else {}),
        )
    except (RoutePlanningError, GlobalRouterError):
        return None
    if exact_at is not None and (
        plan.terminal_map != destination or plan.terminal_at != exact_at
    ):
        return None
    terminal_at = plan.terminal_at
    if stop_at_map_boundary:
        # Trainer projections are observed on the CURRENT map. Re-enumerate
        # immediately after a warp/connection, before entering unseen lanes.
        first = next((s for s in plan.steps if s.expected_map != raw.map_id), None)
        if first is not None:
            destination, terminal_at = first.expected_map, first.expected_at
            completes_objective = completes_objective and destination == final_destination
    state = runtime.emulator.save_state_bytes()
    cash_plan = plan
    if stop_at_map_boundary and isinstance(route, RedVermilionGroundTransition):
        cash_plan = route.route_world.plan_feasible_to_map(start, destination, goal_at=terminal_at)
    # Known boarding/dialogue scripts must use the caller's existing bounded
    # dialogue executor, not a certificate that deliberately forbids text.
    # Opting out retains the full-wallet reservation and all native resource
    # checks; it grants no spending, combat or story-completion authority.
    cash_route = (
        certified_cash_safe_transition(route, raw, cash_plan) if certify_cash_approach else None
    )
    used = False
    terminal = None

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != state or not _field_ready(runtime):
            raise ValueError("story travel is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(cash_route or route, destination_map=destination, destination_at=terminal_at)(
            actions, runtime.reader, runtime.emulator
        )
        after = runtime.reader.read()
        if (
            not _field_ready(runtime)
            or after.map_id != destination
            or (exact_at is not None and (after.player_y, after.player_x) != terminal_at)
            or (completes_objective and not objective.completion_facts <= semantic_facts(after))
            or after.player_money != raw.player_money
            or after.bag_items != raw.bag_items
            or after.party_species_ids != raw.party_species_ids
            or after.badge_bits != raw.badge_bits
        ):
            raise RuntimeError("story destination or protected resources not verified")
        if completes_objective:
            runtime.observer.latch_verified_facts(objective.completion_facts)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                objective=objective_id,
                objective_completed=completes_objective,
                intermediate_boundary=intermediate_map,
                observed_map_boundary=destination if stop_at_map_boundary else None,
                support="observed_cartridge_route_and_wild_escape",
                automatic_objectives=[],
                purchases=0,
                trainer_battles=0,
                source_sha256=sha256(state).hexdigest(),
                terminal_sha256=sha256(terminal).hexdigest(),
            ),
        )

    def verify(report):
        after, snapshot = capture_player_lesson_snapshot(runtime)
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
            or after.raw.map_id != destination
            or (exact_at is not None and (after.raw.player_y, after.raw.player_x) != terminal_at)
            or (completes_objective and not objective.completion_facts <= semantic_facts(after.raw))
            or not set(lesson["completed_objectives"]) <= set(snapshot["completed_objectives"])
            or (completes_objective and objective_id not in snapshot["completed_objectives"])
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:story-travel:"
        + canonical_sha256(
            dict(
                objective=objective_id,
                intermediate=intermediate_map,
                stop_at_map_boundary=stop_at_map_boundary,
                frontier=frontier,
                source=sha256(state).hexdigest(),
                **({"certify_cash_approach": False} if not certify_cash_approach else {}),
                **({"allow_surf": True} if allow_surf else {}),
                **({"route_destination_at": route_destination_at}
                   if route_destination_at is not None else {}),
            )
        ),
        GoalKind.ADVANCE_STORY,
        min(1.0, plan.cost / 3000),
        0.15,
        execute,
        verify,
        maximum_cash_debit=0 if cash_route is not None else None,
        story_objective_ref=objective_id,
        story_approach_only=not completes_objective,
    )
