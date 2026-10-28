"""Legal Fly prefix toward the same selected story objective; never a new goal."""

from dataclasses import asdict, replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_field_moves import (
    Gen1FieldMoveError, Gen1FieldMovePort, fly_menu_indices, fly_story_events_preserved,
)
from .global_router import GlobalRouterError, find_macro_path
from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from .goal_manager_composition_qualification import HardCompositionActionLimiter
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import Badge, MapId, OverworldMovementMode, RED_FLY_TOWN_NAMES, semantic_facts
from .provenance import canonical_sha256
from .red_collection_fly import red_fly_landings
from .red_player_field_goals import _field_ready
from .red_player_fly import _noncombat_fly_world
from .red_player_lesson import capture_player_lesson_snapshot
from .red_resource_goal_router import _supported_plan
from .red_story_map_frontier import story_frontier_target
from .route_plan import RoutePlanningError

# Existing collection flight compiler's conservative action allowance. This is
# a bound for the flight prefix, not a measured wall-time prediction.
_FLIGHT_ACTIONS = 256
_PROTECTED = (
    "party_count", "party_species_ids", "party_hp", "party_max_hp", "party_status",
    "party_moves", "party_pp", "party_levels", "bag_items", "player_money", "badge_bits",
)


def story_fly_binding(
    runtime, actions, *, objective_id, final_destination, route, start,
    before, lesson, arrival_objective, allow_surf=False,
):
    """Quote a useful departure or flight, without input or goal substitution.

    Topology ranks candidates only. A real noncombat quote to the first onward
    boundary must also pass. The relaxed story preview is never executed.
    """
    raw, reader = before.raw, runtime.reader
    if (
        not _field_ready(runtime) or not start.ready or start.interruption is not None
        or type(start.map_id) is not int or not 0 <= start.map_id <= 255 or start.map_id == 0x0B
        or (start.map_id, *start.at) != (raw.map_id, raw.player_y, raw.player_x)
        or start.map_id == final_destination or start.mode != "land"
        or not int(raw.badge_bits or 0) & int(Badge.THUNDER)
        or reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING
        or reader.read_pending_trainer_battle_identity() is not None
        or reader.read_fly_menu_state() is not None
    ):
        return None
    try:
        fly_menu_indices(raw)
    except Gen1FieldMoveError:
        return None
    if any(getattr(raw, name, None) is None for name in _PROTECTED):
        return None
    departure = None
    if start.map_id >= 0x25:
        from .red_indoor_departure_plan import bounded_indoor_departure

        if start.map_id == int(MapId.SAFARI_ZONE_GATE) and (
            reader.read_safari_session_state().has_active_session
            or reader.read_safari_zone_gate_script() != 0
        ):
            return None
        departure = bounded_indoor_departure(start, route.route_world)
        if departure is None:
            return None
        # Only quotation uses this outdoor projection. A selected option below
        # walks the actual exit; actual Fly needs a fresh outdoor observation.
        start = replace(start, map_id=departure.terminal_map, at=departure.terminal_at,
                        last_outside_map=departure.terminal_map,
                        occupied=frozenset(), hazards=())
    try:
        ground = find_macro_path(
            route.route_world.macro_graph, start.map_id, final_destination,
            last_outside=start.last_outside_map,
        )
    except GlobalRouterError:
        return None
    world = _noncombat_fly_world(route.route_world, raw)
    landings = dict(red_fly_landings(route.rom))
    candidates = []
    for town in reader.read_fly_destinations():
        if town == start.map_id or town not in landings or not 0 <= town < len(RED_FLY_TOWN_NAMES):
            continue
        landing = landings[town]
        graph = world.local_graphs.get(town)
        if graph is None or landing not in graph.edges or landing in world.object_blockers[town]:
            continue
        try:
            onward = find_macro_path(world.macro_graph, town, final_destination, last_outside=town)
        except GlobalRouterError:
            continue
        # Count the flight as one boundary. Require strict improvement, so a
        # nearby/equally distant town cannot cause a gratuitous flight or loop.
        if len(onward.edges) + 1 >= len(ground.edges):
            continue
        projected = replace(
            start, map_id=town, at=landing, last_outside_map=town,
            occupied=frozenset(), hazards=(),
        )
        candidates.append((len(onward.edges), town, projected))
    chosen = None
    for distance, town, projected in sorted(candidates, key=lambda item: item[:2]):
        try:
            target, at = story_frontier_target(world, projected, final_destination)
            plan = world.plan_feasible_to_map(projected, target, goal_at=at)
        except (RoutePlanningError, GlobalRouterError):
            continue
        if (
            plan.terminal_map != target or plan.terminal_at != at
            or not _supported_plan(plan, allow_cut=True, allow_surf=allow_surf)
            or (not plan.steps and town != final_destination)
        ):
            continue
        chosen = distance, town, projected.at, target, at
        break
    if chosen is None:
        return None
    distance, town, landing, onward_map, onward_at = chosen
    if departure is not None:
        return _indoor_departure_binding(
            runtime, actions, objective_id=objective_id, route=route,
            departure=departure, before=before, lesson=lesson,
            flight_town=town, onward_map=onward_map, onward_at=onward_at,
        )
    objective = runtime.adapter.graph.objective(objective_id)
    completes = arrival_objective and town == final_destination
    state = runtime.emulator.save_state_bytes()
    used = False
    terminal = None
    executed_report = None

    def execute():
        nonlocal used, terminal, executed_report
        if used or runtime.emulator.save_state_bytes() != state or not _field_ready(runtime):
            raise ValueError("story flight is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        limited = HardCompositionActionLimiter(
            actions, maximum_actions_per_decision=_FLIGHT_ACTIONS,
            maximum_episode_actions=_FLIGHT_ACTIONS,
        )
        receipt = Gen1FieldMovePort(limited, reader, runtime.emulator).execute(
            MacroAction(
                MacroActionKind.FIELD_MOVE,
                "fly:" + RED_FLY_TOWN_NAMES[town].lower().replace(" ", "_"),
            )
        )
        after = reader.read()
        if (
            not _field_ready(runtime)
            or (after.map_id, after.player_y, after.player_x) != (town, *landing)
            or reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING
            or any(getattr(after, name) != getattr(raw, name) for name in _PROTECTED)
            or not fly_story_events_preserved(raw, after, town, departure=False)
            or receipt.source_map != raw.map_id or receipt.destination_map != town
            or receipt.flight_confirmations != 1
            or (completes and not objective.completion_facts <= semantic_facts(after))
        ):
            raise RuntimeError("story flight landing or protected resources not verified")
        if completes:
            runtime.observer.latch_verified_facts(objective.completion_facts)
        terminal = runtime.emulator.save_state_bytes()
        executed_report = GoalExecutionReport(
            actions.actions_executed - a, runtime.emulator.frame_count - f,
            dict(
                objective=objective_id, objective_completed=completes,
                final_destination=final_destination, observed_map_boundary=town,
                support="native_fly_story_prefix", native_fly=asdict(receipt),
                quoted_onward_boundary=dict(map_id=onward_map, at=onward_at),
                topology_ground_edges=len(ground.edges), topology_onward_edges=distance,
                topology_is_not_wall_time_prediction=True,
                automatic_objectives=[], purchases=0, trainer_battles=0,
                source_sha256=sha256(state).hexdigest(),
                terminal_sha256=sha256(terminal).hexdigest(),
            ),
        )
        return executed_report

    def verify(report):
        after, snapshot = capture_player_lesson_snapshot(runtime)
        if (
            report is not executed_report or terminal is None
            or runtime.emulator.save_state_bytes() != terminal or not _field_ready(runtime)
            or (after.raw.map_id, after.raw.player_y, after.raw.player_x) != (town, *landing)
            or any(getattr(after.raw, name) != getattr(raw, name) for name in _PROTECTED)
            or not fly_story_events_preserved(raw, after.raw, town, departure=False)
            or (completes and not objective.completion_facts <= semantic_facts(after.raw))
            or not set(lesson["completed_objectives"]) <= set(snapshot["completed_objectives"])
            or (completes and objective_id not in snapshot["completed_objectives"])
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:story-fly:" + canonical_sha256(dict(
            objective=objective_id, source=sha256(state).hexdigest(),
            final_destination=final_destination, town=town, landing=landing,
            onward_map=onward_map, onward_at=onward_at, allow_surf=allow_surf,
        )),
        GoalKind.ADVANCE_STORY, _FLIGHT_ACTIONS / 3000, 0.15, execute, verify,
        maximum_cash_debit=0, story_objective_ref=objective_id, story_approach_only=not completes,
    )


def _indoor_departure_binding(runtime, actions, *, objective_id, route, departure,
                             before, lesson, flight_town, onward_map, onward_at):
    """Reuse real walking for the exit; the projected flight has no executor."""
    from .red_player_story_travel import story_travel_binding

    walking = story_travel_binding(
        runtime, actions, objective_id=objective_id, route=route,
        intermediate_map=departure.terminal_map, stop_at_map_boundary=False,
        certify_cash_approach=True,
    )
    if (walking is None or walking.maximum_cash_debit != 0
            or not walking.story_approach_only
            or walking.story_objective_ref != objective_id):
        return None
    source = runtime.emulator.save_state_bytes()
    raw = before.raw
    used, terminal, original_report, executed_report = False, None, None, None

    def preserved():
        after = runtime.reader.read()
        return (
            _field_ready(runtime) and after.battle_state == 0
            and (after.map_id, after.player_y, after.player_x)
                == (departure.terminal_map, *departure.terminal_at)
            and runtime.reader.read_overworld_movement_mode() is OverworldMovementMode.WALKING
            and all(getattr(after, name) == getattr(raw, name) for name in _PROTECTED)
            and fly_story_events_preserved(raw, after, departure.terminal_map, departure=False)
        )

    def execute():
        nonlocal used, terminal, original_report, executed_report
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError('story departure is stale or consumed')
        used = True
        original_report = walking.execute()
        if (walking.verify(original_report).status is not GoalDecisionOutcome.SUCCEEDED
                or not preserved()):
            raise RuntimeError('story departure arrival or protected facts not verified')
        _, after_lesson = capture_player_lesson_snapshot(runtime)
        if after_lesson['completed_objectives'] != lesson['completed_objectives']:
            raise RuntimeError('story departure changed objective progress')
        terminal = runtime.emulator.save_state_bytes()
        executed_report = GoalExecutionReport(
            original_report.actions_executed, original_report.frames_executed,
            dict(original_report.evidence, objective_completed=False,
                 support='native_indoor_story_fly_departure',
                 observed_map_boundary=departure.terminal_map,
                 projected_flight_town=flight_town,
                 quoted_onward_boundary=dict(map_id=onward_map, at=onward_at),
                 flight_executed=False, requires_fresh_outdoor_observation=True),
        )
        return executed_report

    def verify(report):
        if (report is not executed_report or executed_report is None or terminal is None
                or runtime.emulator.save_state_bytes() != terminal or not preserved()
                or walking.verify(original_report).status is not GoalDecisionOutcome.SUCCEEDED):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        _, after_lesson = capture_player_lesson_snapshot(runtime)
        if after_lesson['completed_objectives'] != lesson['completed_objectives']:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return replace(walking,
        binding_ref='pokemon.red:story-fly-departure:' + canonical_sha256(dict(
            source=sha256(source).hexdigest(), walk=walking.binding_ref,
            objective=objective_id, outside=departure.terminal_map,
            at=departure.terminal_at, flight_town=flight_town,
            onward_map=onward_map, onward_at=onward_at)),
        execute=execute, verify=verify,
    )
