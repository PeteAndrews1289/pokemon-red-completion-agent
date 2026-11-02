"""Compose a bounded observed exit with the existing paid Safari option."""

from dataclasses import asdict, replace

from .gen1_route_runtime import Gen1TraversalObserver
from .goal_manager_runtime import GoalExecutionReport
from .observation import MapId
from .provenance import canonical_sha256
from .red_dig_recovery import execute_dig_escape, plan_dig_escape
from .red_indoor_departure_plan import bounded_indoor_departure
from .red_live_option_menu import supplemental_live_option
from .red_live_safari import (
    RedLiveSafariInventory,
    build_red_live_safari_inventory,
    safari_health_stasis_available,
)
from .red_resource_goal_router import _ROUTE_LIMITS, _walking_plan
from .route_evidence import public_route_execution
from .route_executor import execute_route
from .route_plan import RoutePlanningError


class _ProjectedReader:
    def __init__(self, reader, raw):
        self.reader, self.raw = reader, raw

    def read(self):
        return self.raw

    def __getattr__(self, name):
        return getattr(self.reader, name)


def indoor_safari_inventory(
    rom,
    registered,
    context,
    *,
    free_storage_slots,
    world,
    controller,
    actions,
    reader,
    event_sink=None,
    expose_all_areas=False,
    complete_paid_session=False,
    departure_recovery=False,
    dig_departure=False,
    required_capture_numbers=None,
    acquisition_catalog=None,
    maximum_encounters=None,
    include_capture_invocation=False,
):
    if type(include_capture_invocation) is not bool:
        raise ValueError("Safari invocation observation must be an explicit boolean")
    if type(departure_recovery) is not bool:
        raise ValueError("Safari departure recovery must be boolean")
    if type(dig_departure) is not bool:
        raise ValueError("Safari Dig departure must be boolean")
    if maximum_encounters is not None and (
        type(maximum_encounters) is not int or maximum_encounters <= 0
    ):
        raise ValueError("Safari encounter bound must be a positive integer")
    empty = RedLiveSafariInventory((), ())
    before = reader.read()
    if (
        not safari_health_stasis_available(before)
        or before.map_id is None
        or (before.map_id < 0x25 and before.map_id != int(MapId.FUCHSIA_CITY))
        or before.map_id == int(MapId.SAFARI_ZONE_GATE)
        or reader.read_bottom_dialogue_box_visible()
        or reader.read_pending_trainer_battle_identity() is not None
    ):
        return empty
    traversal = Gen1TraversalObserver(reader)
    start = traversal.observe()
    if (start.map_id, *start.at) != (before.map_id, before.player_y, before.player_x):
        raise ValueError("Safari indoor origin changed during observation")
    in_fuchsia = start.map_id == int(MapId.FUCHSIA_CITY)
    escape = (plan_dig_escape(world, reader, before, start)
              if dig_departure and not in_fuchsia else None)
    plan = None if in_fuchsia or escape is not None else bounded_indoor_departure(start, world)
    if plan is None and not in_fuchsia and escape is None:
        return empty
    terminal_map = (escape.anchor if escape is not None else
                    start.map_id if in_fuchsia else plan.terminal_map)
    terminal_at = (escape.landing if escape is not None else
                   start.at if in_fuchsia else plan.terminal_at)
    if terminal_map == int(MapId.FUCHSIA_CITY):
        # Already in the destination town: continue to its unpaid gate instead
        # of demanding an impossible Fly-to-current-town operation. The world
        # derives the door/arrival; the existing gate binder owns clerk approach.
        session = reader.read_safari_session_state()
        if session.in_safari_zone or session.safari_game_over:
            return empty
        try:
            gate_start = (replace(start, map_id=terminal_map, at=terminal_at,
                                  last_outside_map=terminal_map, occupied=frozenset(), hazards=())
                          if escape is not None else start)
            gate_plan = world.plan_feasible_to_map(gate_start, int(MapId.SAFARI_ZONE_GATE))
        except RoutePlanningError:
            return empty
        allowed_maps = {start.map_id, int(MapId.FUCHSIA_CITY), int(MapId.SAFARI_ZONE_GATE)}
        if (not gate_plan.steps or len(gate_plan.steps) > 128 or not _walking_plan(gate_plan)
                or gate_plan.terminal_map != int(MapId.SAFARI_ZONE_GATE)
                or any(s.source_map not in allowed_maps or s.expected_map not in allowed_maps
                       for s in gate_plan.steps)):
            return empty
        plan = gate_plan
        terminal_map, terminal_at = plan.terminal_map, plan.terminal_at
    projected_raw = replace(
        before, map_id=terminal_map, player_y=terminal_at[0], player_x=terminal_at[1]
    )

    def inventory(port):
        return build_red_live_safari_inventory(
            rom,
            registered,
            context,
            free_storage_slots=free_storage_slots,
            world=world,
            controller=controller,
            actions=actions,
            reader=port,
            expose_all_areas=expose_all_areas,
            complete_paid_session=complete_paid_session,
            **({"include_capture_invocation": True} if include_capture_invocation else {}),
            **({} if maximum_encounters is None else {
                "maximum_encounters": maximum_encounters,
            }),
            **({} if required_capture_numbers is None else {
                "required_capture_numbers": required_capture_numbers,
                "acquisition_catalog": acquisition_catalog,
            }),
        )

    projected = inventory(_ProjectedReader(reader, projected_raw))
    if not projected.supplements:
        return empty
    claimed = False

    def wrap(original):
        played = []

        def execute():
            nonlocal claimed
            if claimed:
                raise ValueError("Safari indoor binding already consumed")
            claimed = True
            if (
                reader.read() != before
                or traversal.observe() != start
                or controller.pressed_buttons
            ):
                raise ValueError("Safari indoor origin changed before input")
            first_actions, first_frames = actions.actions_executed, controller.frame_count
            if event_sink is not None:
                event_sink(
                    {
                        "phase": "safari_indoor_departure",
                        "event": "route_started",
                        "steps": [asdict(step) for step in plan.steps] if plan is not None else [],
                        **({"dig_escape": asdict(escape)} if escape is not None else {}),
                    }
                )
            try:
                recovery = {}
                escape_receipt = (execute_dig_escape(world, reader, controller, actions, escape)
                                  if escape is not None else None)
                if departure_recovery:
                    from .red_routed_recovery import guarded_collection_route_handler

                    recovery["interruption_handler"] = guarded_collection_route_handler(
                        actions, reader, route_name="indoor Safari approach"
                    )
                route = None if plan is None else execute_route(
                    plan, actions, traversal, limits=_ROUTE_LIMITS, **recovery
                )
            except BaseException as error:
                if event_sink is not None:
                    failure = getattr(error, "failure", None)
                    event_sink(
                        {
                            "phase": "safari_indoor_departure",
                            "event": "route_failed",
                            "error": str(error),
                            "acknowledged_steps": [asdict(r.step) for r in failure.executed_steps]
                            if failure
                            else [],
                        }
                    )
                raise
            receipt = (public_route_execution(route) if route is not None else {"passed": True})
            if escape_receipt is not None:
                receipt = {**receipt, "dig_escape": escape_receipt, "learned_navigation": False}
            if event_sink is not None:
                event_sink(
                    {
                        "phase": "safari_indoor_departure",
                        "event": "route_finished",
                        "report": receipt,
                    }
                )
            actual = reader.read()
            if (
                (route is not None and not route.passed)
                or not reader.read_input_readiness().ready
                or (actual.map_id, actual.player_y, actual.player_x)
                != (terminal_map, *terminal_at)
                or actual.player_money != before.player_money
                or actual.bag_items != before.bag_items
                or actual.party_species_ids != before.party_species_ids
                or actual.party_hp != before.party_hp
                or actual.party_status != before.party_status
                or actual.party_pp != before.party_pp
            ):
                raise ValueError("Safari indoor departure changed boundary or resources")
            rebound = inventory(reader)
            if rebound.areas != projected.areas:
                raise ValueError("Safari offer changed after actual indoor departure")
            matches = [
                option
                for option in rebound.supplements
                if option.binding.binding_ref == original.binding.binding_ref
            ]
            if len(matches) != 1:
                raise ValueError("Selected Safari offer changed after actual indoor departure")
            if include_capture_invocation and (
                original.candidate.capture_invocation is None
                or matches[0].candidate.capture_invocation != original.candidate.capture_invocation
            ):
                raise ValueError("Safari invocation changed after actual indoor departure")
            child = matches[0].binding
            result = child.execute()
            played.append((child, result))
            return GoalExecutionReport(
                actions.actions_executed - first_actions,
                controller.frame_count - first_frames,
                {**result.evidence, "indoor_departure": receipt},
            )

        def verify(_report):
            if len(played) != 1:
                raise ValueError("Safari verification requires one actual executed child")
            child, result = played[0]
            return child.verify(result)

        identity = canonical_sha256(
            {
                "map": before.map_id,
                "x": before.player_x,
                "y": before.player_y,
                "outdoor": terminal_map,
                "at": terminal_at,
                "child": original.binding.binding_ref,
                **({"dig_escape": asdict(escape)} if escape is not None else {}),
            }
        )
        binding = replace(
            original.binding,
            binding_ref="red-indoor-safari:" + identity,
            execute=execute,
            verify=verify,
        )
        candidate = replace(
            original.candidate,
            features=replace(
                original.candidate.features,
                travel_effort=min(
                    1.0, original.candidate.features.travel_effort
                    + (len(plan.steps) / 256 if plan is not None else 0.05)
                ),
            ),
        )
        return supplemental_live_option(binding, candidate)

    return RedLiveSafariInventory(
        projected.areas, tuple(wrap(original) for original in projected.supplements)
    )
