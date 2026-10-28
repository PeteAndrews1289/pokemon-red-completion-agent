"""Small observed Hideout interactions, separate from learned trainer combat."""

from dataclasses import replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector, TrainerFacing
from .gen1_traversal import cut_capabilities, map_object_events
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import EventFlag, ItemId, event_flag_is_set
from .red_pc_storage import face_pc_boundary
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot
from .red_silph_reward import reward_vitals_preserved
from .rom import verify_rom_bytes
from .route_plan import RoutePlanningError


def pending_hideout_interaction(raw, present):
    """Return only the currently native-enabled mechanical phase."""
    if raw.battle_state or raw.event_flags is None or raw.bag_items is None:
        return None
    bag = dict(raw.bag_items)
    if (
        raw.map_id == 135
        and 11 not in present
        and not event_flag_is_set(raw.event_flags, int(EventFlag.FOUND_ROCKET_HIDEOUT))
    ):
        return "poster", 11, None, int(EventFlag.FOUND_ROCKET_HIDEOUT)
    if raw.map_id != 202:
        return None
    if (
        4 in present
        and event_flag_is_set(raw.event_flags, 1700)
        and not event_flag_is_set(raw.event_flags, 1702)
    ):
        return "drop_key", 4, None, 1702
    if len(bag) >= 20:
        return None
    if 9 in present and event_flag_is_set(raw.event_flags, 1702) and not bag.get(74):
        return "lift_key", 9, int(ItemId.LIFT_KEY), None
    if 8 in present and event_flag_is_set(raw.event_flags, 1703) and not bag.get(72):
        return "scope", 8, int(ItemId.SILPH_SCOPE), None
    return None


def hideout_interaction_binding(runtime, actions, *, route):
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    live = runtime.reader.read_current_map_objects()
    spec = pending_hideout_interaction(raw, {o.sprite_index for o in live})
    if spec is None:
        return None
    phase, index, item, event = spec
    verify_rom_bytes(route.rom)
    targets = [o for o in map_object_events(route.rom, {raw.map_id}) if o.object_index == index]
    if len(targets) != 1:
        raise ValueError("Hideout interaction needs one cartridge object")
    target = targets[0]
    if phase != "poster" and not any(
        o.sprite_index == index and o.at == target.at and o.picture_id == target.sprite_id
        for o in live
    ):
        raise ValueError("Hideout interaction object moved or changed")
    origin = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=cut_capabilities,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    candidates = []
    for facing in TrainerFacing:
        if phase == "poster" and facing is not TrainerFacing.UP:
            continue
        at = (
            target.at
            if phase == "poster"
            else (target.at[0] - facing.delta[0], target.at[1] - facing.delta[1])
        )
        if min(at) < 0:
            continue
        try:
            plan = route.route_world.plan_feasible_to_map(origin, raw.map_id, goal_at=at)
        except RoutePlanningError:
            continue
        candidates.append((plan, facing))
    if not candidates:
        return None
    plan, facing = min(candidates, key=lambda p: p[0].cost)
    source = runtime.emulator.save_state_bytes()
    terminal, used = None, False

    def achieved(current):
        return (
            dict(current.bag_items or ()).get(item, 0) == 1
            if item is not None
            else event_flag_is_set(current.event_flags, event)
        )

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Hideout interaction is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(route, destination_map=raw.map_id, destination_at=plan.terminal_at)(
            actions, runtime.reader, runtime.emulator
        )
        if (
            pending_hideout_interaction(
                runtime.reader.read(),
                {o.sprite_index for o in runtime.reader.read_current_map_objects()},
            )
            != spec
        ):
            raise ValueError("Hideout interaction prerequisite changed")
        face_pc_boundary(actions, runtime.reader, facing.value)
        for _ in range(96):
            current = runtime.reader.read()
            if current.map_id != raw.map_id or current.battle_state:
                raise ValueError("Hideout mechanical interaction entered unexpected state")
            if achieved(current) and _field_ready(runtime):
                break
            actions.execute(
                MacroAction(
                    MacroActionKind.INTERACT if _field_ready(runtime) else MacroActionKind.CONFIRM
                )
            )
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=24))
        current = runtime.reader.read()
        expected_bag = dict(raw.bag_items)
        if item is not None:
            expected_bag[item] = 1
        expected_events = bytearray(raw.event_flags)
        if event is not None:
            expected_events[event // 8] |= 1 << (event % 8)
        if (
            not achieved(current)
            or not _field_ready(runtime)
            or dict(current.bag_items or ()) != expected_bag
            or current.event_flags != bytes(expected_events)
            or any(
                getattr(raw, k) != getattr(current, k)
                for k in (
                    "party_species_ids",
                    "party_hp",
                    "party_pp",
                    "party_status",
                    "player_money",
                    "badge_bits",
                )
            )
        ):
            raise ValueError("Hideout interaction outcome or protected state differs")
        capture_player_lesson_snapshot(runtime)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="native_hideout_interaction",
                phase=phase,
                learned=False,
                objective_completed=phase == "scope",
                source_sha256=sha256(source).hexdigest(),
                terminal_sha256=sha256(terminal).hexdigest(),
            ),
        )

    def verify(report):
        _, after = capture_player_lesson_snapshot(runtime)
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
            or not achieved(runtime.reader.read())
            or not set(lesson["completed_objectives"]) <= set(after["completed_objectives"])
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:hideout-interaction:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, 0.02 + plan.cost / 3000),
        0.05,
        execute,
        verify,
    )


def hideout_elevator_binding(runtime, actions, *, route, destination_floor=202):
    """Reach the keyed lift, then use its visible B4 menu on a separate decision."""
    if destination_floor not in (199, 200, 202):
        raise ValueError("Hideout lift requires a cartridge floor")
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    if (raw.party_hp is None or raw.party_status is None
            or len(raw.party_hp) != len(raw.party_status)):
        return None
    if (
        raw.map_id not in (199, 200, 201, 202, 203)
        or not dict(raw.bag_items or ()).get(int(ItemId.LIFT_KEY))
        or (destination_floor == 202 and dict(raw.bag_items or ()).get(int(ItemId.SILPH_SCOPE)))
        or (raw.map_id == destination_floor and destination_floor != 202)
    ):
        return None
    origin = Gen1TraversalObserver(
        runtime.reader,
        capability_projector=cut_capabilities,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    try:
        plan = route.route_world.plan_feasible_to_map(
            origin, 203, **({"goal_at": (2, 1)} if raw.map_id == 203 else {})
        )
    except RoutePlanningError:
        return None
    # Observe each new room before navigating through its trainer lanes.
    first = next((s for s in plan.steps if s.expected_map != raw.map_id), None)
    destination, at = (first.expected_map, first.expected_at) if first else (203, plan.terminal_at)
    source = runtime.emulator.save_state_bytes()
    terminal, used = None, False
    floor_at = (15, 25) if destination_floor == 202 else (19, 25)
    expected_map = destination_floor if raw.map_id == 203 else destination
    expected_at = floor_at if raw.map_id == 203 else at

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Hideout lift phase is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(route, destination_map=destination, destination_at=at)(
            actions, runtime.reader, runtime.emulator
        )
        if raw.map_id == 203:
            from .hideout import DEFAULT_HIDEOUT_TIMING, _select_cursor

            face_pc_boundary(actions, runtime.reader, "up")
            actions.execute(MacroAction(MacroActionKind.INTERACT))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=180))
            visible = " ".join(runtime.reader.read_screen_text_rows())
            if not all(label in visible for label in ("B1F", "B2F", "B4F")):
                raise ValueError("Hideout elevator did not expose its expected floor menu")
            _select_cursor(
                actions,
                runtime.emulator,
                (199, 200, 202).index(destination_floor),
                DEFAULT_HIDEOUT_TIMING,
            )
            actions.execute(MacroAction(MacroActionKind.CONFIRM))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=480))
            for direction, end_map, end_at in (
                ("right", 203, (2, 2)),
                ("up", destination_floor, floor_at),
            ):
                for _ in range(12):
                    current = runtime.reader.read()
                    if current.battle_state or current.map_id not in (203, end_map):
                        raise ValueError("Hideout elevator exit left its mechanical scope")
                    if (current.map_id, (current.player_y, current.player_x)) == (end_map, end_at):
                        break
                    actions.execute(MacroAction(MacroActionKind.MOVE, direction))
                    actions.execute(MacroAction(MacroActionKind.WAIT, repeat=24))
                else:
                    raise ValueError("Hideout elevator exit was not acknowledged")
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=120))
        current = runtime.reader.read()
        if (
            not _field_ready(runtime)
            or current.map_id != expected_map
            or (current.player_y, current.player_x) != expected_at
            or any(
                getattr(raw, k) != getattr(current, k)
                for k in (
                    "bag_items",
                    "player_money",
                    "party_species_ids",
                    "party_levels",
                    "party_moves",
                    "party_pp",
                    "badge_bits",
                )
            )
            or not reward_vitals_preserved(raw, current)
            or raw.event_flags != current.event_flags
        ):
            raise ValueError("Hideout lift terminal or protected resources differ")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="native_keyed_elevator",
                learned=False,
                objective_completed=False,
                destination_map=expected_map,
                field_poison_hp_loss=[old - new for old, new in zip(
                    raw.party_hp, current.party_hp, strict=True)],
                source_sha256=sha256(source).hexdigest(),
                terminal_sha256=sha256(terminal).hexdigest(),
            ),
        )

    def verify(report):
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:hideout-lift:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, 0.05 + plan.cost / 3000),
        0.05,
        execute,
        verify,
    )


def hideout_restoration_binding(runtime, actions, *, route, return_only=False):
    """Honor a selected heal goal through the lift's dynamic return destination."""
    from .red_goal_skills import _raw_party_fully_restored
    from .red_player_field_goals import routed_restoration_binding

    raw = runtime.reader.read()
    if type(return_only) is not bool:
        raise ValueError("explicit return-only mode required")
    if raw.map_id not in (199, 202, 203) or (not return_only and _raw_party_fully_restored(raw)):
        return None
    if return_only and (
        not dict(raw.bag_items or ()).get(72) or not _raw_party_fully_restored(raw)
    ):
        return None
    first = hideout_elevator_binding(runtime, actions, route=route, destination_floor=200)
    if first is None:
        return None
    source = runtime.emulator.save_state_bytes()
    used, child, child_report, terminal = False, None, None, None

    def execute():
        nonlocal used, child, child_report, terminal
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("Hideout restoration is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        # First phase enters the lift; second selects B2. The elevator mutates
        # its own exit records, so never use its static ROM return as a shortcut.
        # B1's elevator wing has another locked door; B2 permits backtracking
        # through the already traversed maze without inventing a healing fight.
        for _ in range(2):
            if runtime.reader.read().map_id == 200:
                break
            live_route = replace(
                route, route_world=route.route_world.with_current_observation(runtime.reader)
            )
            phase = hideout_elevator_binding(
                runtime, actions, route=live_route, destination_floor=200
            )
            if phase is None:
                raise ValueError("Hideout recovery cannot reach the keyed elevator")
            report = phase.execute()
            if phase.verify(report).status.value != "succeeded":
                raise ValueError("Hideout recovery elevator did not verify")
        if runtime.reader.read().map_id != 200:
            raise ValueError("Hideout recovery did not reach B2")
        world = route.route_world.with_current_observation(runtime.reader)
        world = replace(
            world,
            macro_graph=replace(
                world.macro_graph,
                edges={
                    m: tuple(e for e in edges if e.target_map != 203)
                    for m, edges in world.macro_graph.edges.items()
                    if m != 203
                },
            ),
        )
        live_route = replace(route, route_world=world, excluded_maps=frozenset({203}))
        if return_only:
            replace(live_route, destination_map=133, destination_at=(3, 3))(
                actions, runtime.reader, runtime.emulator
            )
            after = runtime.reader.read()
            if (
                not _field_ready(runtime)
                or after.map_id != 133
                or (after.player_y, after.player_x) != (3, 3)
                or any(
                    getattr(raw, k) != getattr(after, k)
                    for k in (
                        "bag_items",
                        "player_money",
                        "party_species_ids",
                        "party_hp",
                        "party_pp",
                        "party_status",
                        "event_flags",
                        "badge_bits",
                    )
                )
            ):
                raise ValueError("Hideout healthy return changed protected resources")
            terminal = runtime.emulator.save_state_bytes()
            return GoalExecutionReport(
                actions.actions_executed - a,
                runtime.emulator.frame_count - f,
                dict(
                    support="healthy_scope_center_return",
                    learned=False,
                    heals=0,
                    objective_completed=False,
                ),
            )
        child = routed_restoration_binding(runtime, actions, home_map=133, route=live_route)
        if child is None:
            raise ValueError("Hideout recovery cannot reach Celadon Center")
        child_report = child.execute()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support="keyed_lift_then_center",
                learned=False,
                restoration=dict(child_report.evidence),
            ),
        )

    def verify(report):
        if return_only:
            if (
                terminal is None
                or runtime.emulator.save_state_bytes() != terminal
                or not _field_ready(runtime)
            ):
                return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
            return GoalVerification.succeeded()
        if not used or child is None or child_report is None:
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return child.verify(child_report)

    return ExecutableGoalBinding(
        "pokemon.red:hideout-center:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY if return_only else GoalKind.RESTORE_TEAM,
        0.15,
        0.05,
        execute,
        verify,
    )
