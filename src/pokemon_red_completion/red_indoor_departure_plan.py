"""One observed indoor-to-outdoor exit, without a chapter route or new input."""

from .actions import MacroActionKind
from .route_plan import RoutePlanningError


def bounded_indoor_departure(start, world):
    outside = start.last_outside_map
    if (
        not start.ready
        or start.interruption is not None
        or start.mode != "land"
        or type(start.map_id) is not int
        or start.map_id < 0x25
        or type(outside) is not int
        or not 0 <= outside <= 0x24
        or outside == 0x0B
    ):
        return None
    try:
        plan = world.plan_feasible_to_map(start, outside)
    except RoutePlanningError:
        return None
    if (
        not plan.steps
        or len(plan.steps) > 128
        or plan.terminal_map != outside
        or plan.terminal_mode not in {None, "land"}
        or any(
            type(s.source_map) is not int
            or s.source_map < 0x25
            or type(s.expected_map) is not int
            or (s.expected_map < 0x25 and s.expected_map != outside)
            or s.kind not in {"walk", "warp", "return"}
            or s.action_kind is not MacroActionKind.MOVE
            or s.action not in {"up", "down", "left", "right"}
            or s.source_mode not in {None, "land"}
            or s.expected_mode not in {None, "land"}
            for s in plan.steps
        )
    ):
        return None
    # A building may contain several interior maps. Require a continuous chain
    # and exactly one outdoor boundary, at the end; never allow outdoor detours.
    current = start.map_id
    for index, step in enumerate(plan.steps):
        if step.source_map != current:
            return None
        if step.expected_map == outside and index != len(plan.steps) - 1:
            return None
        current = step.expected_map
    if current != outside:
        return None
    return plan


def bounded_indoor_boundary_departure(start, world):
    """Quote only the current room when a remote layout prevents a full exit.

    Initial cartridge objects can occupy a later room's arrival tile after an
    earned script has removed them. Do not delete those unobserved objects.
    Follow only the first real warp in the existing corridor toward the observed
    outside map, then require a new coherent map observation and full menu.
    """
    from .global_router import GlobalRouterError, find_macro_path

    outside = start.last_outside_map
    if (not start.ready or start.interruption is not None or start.mode != 'land'
            or type(start.map_id) is not int or start.map_id < 0x25
            or type(outside) is not int or not 0 <= outside <= 0x24 or outside == 0x0B):
        return None
    try:
        corridor = find_macro_path(world.macro_graph, start.map_id, outside, last_outside=outside)
        if (len(corridor.maps) < 2 or not corridor.edges
                or corridor.edges[0].kind not in {'warp', 'return'}):
            return None
        boundary = corridor.maps[1]
        if boundary < 0x25 and boundary != outside:
            return None
        plan = world.plan_feasible_to_map(start, boundary)
    except (GlobalRouterError, RoutePlanningError):
        return None
    if (plan.macro_path.maps != (start.map_id, boundary)
            or not plan.steps or len(plan.steps) > 128
            or plan.terminal_map != boundary or plan.terminal_mode not in {None, 'land'}):
        return None
    # No action may take place after the one current-map boundary crossing.
    for index, step in enumerate(plan.steps):
        if (step.source_map != start.map_id
                or step.expected_map != (boundary if index == len(plan.steps) - 1 else start.map_id)
                or step.kind not in {'walk', 'warp', 'return'}
                or step.action_kind is not MacroActionKind.MOVE
                or step.action not in {'up', 'down', 'left', 'right'}
                or step.source_mode not in {None, 'land'}
                or step.expected_mode not in {None, 'land'}):
            return None
    return plan


def indoor_departure_binding(runtime, actions, *, route):
    """Recover an otherwise empty indoor menu to its observed outdoor boundary.

    This quotes the existing walking planner and transport executor. It supplies
    no story destination, recipient, battle, field move or strategic completion.
    The menu calls it only after every ordinary and supplemental offer is absent.
    """
    from hashlib import sha256

    from .gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
    from .gen1_trainer_sight import Gen1TrainerSightProjector
    from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
    from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
    from .observation import OverworldMovementMode
    from .provenance import canonical_sha256
    from .red_player_field_goals import _field_ready
    from .red_player_lesson import capture_player_lesson_snapshot
    from .red_routed_semantic_goal import RedSemanticTransportRoute

    if not _field_ready(runtime):
        return None
    reader = runtime.reader
    if (reader.read_overworld_movement_mode() is not OverworldMovementMode.WALKING
            or reader.read_pending_trainer_battle_identity() is not None
            or reader.read_fly_menu_state() is not None):
        return None
    source = runtime.emulator.save_state_bytes()
    before, lesson = capture_player_lesson_snapshot(runtime)
    observer = Gen1TraversalObserver(
        reader, capability_projector=lambda raw: frozenset(),
        hazard_projector=Gen1TrainerSightProjector(route.rom, reader, full_event_offsets=True),
    )
    start = observer.observe()
    world = route.route_world.with_current_observation(reader)
    plan = bounded_indoor_departure(start, world)
    if plan is None:
        plan = bounded_indoor_boundary_departure(start, world)
    if plan is None or runtime.emulator.save_state_bytes() != source:
        return None
    # A walking-only quote does not authorize crossing any known battle lane.
    from .red_player_cash_exposure import require_cash_safe_plan
    from .route_executor import RouteExecutionError
    try:
        require_cash_safe_plan(route.rom, before.raw, plan)
    except RouteExecutionError:
        return None
    ship_handler = Gen1WildFleeHandler(actions, reader, maximum_flees=0, stabilization_frames=120)
    ship_handoffs = []

    class NativeShipHandoff(Exception):
        pass

    class DepartureInterruptionHandler:
        handled_hazard_kinds = frozenset()
        handled_interruption_kinds = frozenset({'native_ship_departure'})

        def handle(self, observed):
            if (observed.interruption != 'native_ship_departure'
                    or ship_handoffs
                    or not any((step.expected_map, step.expected_at)
                               == (observed.map_id, observed.at) for step in plan.steps)):
                raise RouteExecutionError('departure interruption is not its quoted native ship boundary')
            receipt = ship_handler.handle(observed)
            if (not receipt.details.get('verified') or not receipt.allows_map_transition
                    or not receipt.allows_relocation or receipt.resumed_map != start.last_outside_map):
                raise RouteExecutionError('native ship landing differs from observed outside map')
            ship_handoffs.append(receipt)
            # The automatic native warp settles beyond the original walking
            # quote. Return control for a fresh menu, never retarget that quote.
            raise NativeShipHandoff

    transport = RedSemanticTransportRoute(
        binding_ref='pokemon.red:empty-indoor-departure-route:' + sha256(source).hexdigest(),
        origin_observation_sha256=canonical_sha256(lesson),
        planner_binding_sha256=canonical_sha256(dict(
            source_map=start.map_id, outside=plan.terminal_map, at=plan.terminal_at)),
        plan=plan, actions=actions, traversal_observer=observer, emulator=runtime.emulator,
        interruption_handler=DepartureInterruptionHandler(),
    ).route_binding()
    terminal = None
    original_report = None
    transport_verified = False
    result = None
    used = False
    protected = ('party_species_ids', 'party_levels', 'party_hp', 'party_max_hp',
                 'party_stats', 'party_status', 'party_moves', 'party_pp', 'bag_items',
                 'player_money', 'badge_bits')

    def preserved():
        current = reader.read()
        _, current_lesson = capture_player_lesson_snapshot(runtime)
        boundary = ((plan.terminal_map, *plan.terminal_at) if not ship_handoffs else
                    (ship_handoffs[0].resumed_map, *ship_handoffs[0].resumed_at))
        return (
            _field_ready(runtime)
            and (current.map_id, current.player_y, current.player_x) == boundary
            and reader.read_overworld_movement_mode() is OverworldMovementMode.WALKING
            and all(getattr(current, name) == getattr(before.raw, name) for name in protected)
            and current_lesson['completed_objectives'] == lesson['completed_objectives']
            and current_lesson['party'] == lesson['party']
        )

    def execute():
        nonlocal used, terminal, original_report, transport_verified, result
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError('indoor departure is stale or consumed')
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        try:
            original_report = transport.execute()
        except NativeShipHandoff:
            if len(ship_handoffs) != 1:
                raise RuntimeError('native ship handoff has no verified receipt')
            evidence = dict(ship_handoffs[0].details, quoted_route_completed=False,
                            automatic_native_handoff=True)
        else:
            transport_verified = transport.verify(original_report).status is GoalDecisionOutcome.SUCCEEDED
            evidence = dict(original_report.evidence, quoted_route_completed=transport_verified)
        if not (transport_verified or len(ship_handoffs) == 1) or not preserved():
            raise RuntimeError('indoor departure boundary or protected facts not verified')
        terminal = runtime.emulator.save_state_bytes()
        result = GoalExecutionReport(
            actions.actions_executed-a, runtime.emulator.frame_count-f,
            dict(evidence, support=('native_ship_departure' if ship_handoffs else 'empty_indoor_menu_departure'),
                 selection_authority='deterministic_control_recovery',
                 objective_completed=False, destination_selected_by_model=False,
                 requires_fresh_boundary_observation=True,
                 requires_fresh_outdoor_observation=plan.terminal_map == start.last_outside_map,
                 source_sha256=sha256(source).hexdigest(),
                 terminal_sha256=sha256(terminal).hexdigest()),
        )
        return result

    def verify(report):
        if (report is not result or result is None or terminal is None
                or runtime.emulator.save_state_bytes() != terminal or not preserved()
                or not (transport_verified or len(ship_handoffs) == 1)):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        'pokemon.red:empty-indoor-departure:' + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL, min(1.0, len(plan.steps) / 1000), 0.0,
        execute, verify, maximum_cash_debit=0,
    )


def native_ship_departure_binding(runtime, actions):
    """Finish only the cartridge's already-active, strictly verified departure.

    The existing handler owns the pending scene and its automatic landing. This
    adds no navigation, dialogue, combat, field move or strategic selection.
    """
    from hashlib import sha256

    from .gen1_route_runtime import Gen1TraversalObserver, Gen1WildFleeHandler
    from .goal_manager import GoalFailureReason, GoalKind
    from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
    from .red_player_field_goals import _field_ready
    from .red_player_lesson import capture_player_lesson_snapshot

    reader = getattr(runtime, 'reader', None)
    if not callable(getattr(reader, 'read', None)):
        return None
    if getattr(reader.read(), 'ss_anne_departure_pending', False) is not True or runtime.emulator.pressed_buttons:
        return None
    observed = Gen1TraversalObserver(reader).observe()
    if observed.interruption != 'native_ship_departure':
        return None
    source = runtime.emulator.save_state_bytes()
    _, lesson = capture_player_lesson_snapshot(runtime)
    handler = Gen1WildFleeHandler(actions, reader, maximum_flees=0, stabilization_frames=120)
    if handler.handled_interruption_kinds != frozenset({'native_ship_departure'}):
        raise ValueError('native departure handler gained unrelated authority')
    terminal = None
    result = None
    used = False

    def preserved():
        _, current = capture_player_lesson_snapshot(runtime)
        return (_field_ready(runtime)
                and current['party'] == lesson['party']
                and current['completed_objectives'] == lesson['completed_objectives'])

    def execute():
        nonlocal used, terminal, result
        if used or runtime.emulator.save_state_bytes() != source or runtime.emulator.pressed_buttons:
            raise ValueError('native ship departure is stale or consumed')
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        receipt = handler.handle(observed)
        if (not receipt.details.get('verified') or not receipt.allows_relocation
                or not receipt.allows_map_transition or not preserved()):
            raise RuntimeError('native ship departure did not verify settled field control')
        terminal = runtime.emulator.save_state_bytes()
        result = GoalExecutionReport(
            actions.actions_executed-a, runtime.emulator.frame_count-f,
            dict(receipt.details, support='native_ship_departure',
                 selection_authority='deterministic_control_recovery',
                 objective_completed=False, requires_fresh_boundary_observation=True,
                 source_sha256=sha256(source).hexdigest(),
                 terminal_sha256=sha256(terminal).hexdigest()),
        )
        return result

    def verify(report):
        if (report is not result or result is None or terminal is None
                or runtime.emulator.save_state_bytes() != terminal
                or len(handler.ship_departure_evidence) != 1 or not preserved()):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        'pokemon.red:retained-motion:' + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL, 0.0, 0.0, execute, verify, maximum_cash_debit=0,
    )
