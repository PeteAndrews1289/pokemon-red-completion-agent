"""Bounded native fossil pickup; route/interaction support, not learned ordering."""

from dataclasses import replace
from hashlib import sha256

from .actions import MacroAction, MacroActionKind
from .gen1_route_runtime import Gen1TraversalObserver
from .gen1_trainer_sight import Gen1TrainerSightProjector, TrainerFacing
from .gen1_traversal import map_object_events
from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import EventFlag, ItemId, MapId, event_flag_is_set
from .red_pc_storage import face_pc_boundary
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot
from .rom import verify_rom_bytes
from .route_plan import RoutePlanningError

FOSSILS = (
    (6, ItemId.DOME_FOSSIL, EventFlag.GOT_DOME_FOSSIL),
    (7, ItemId.HELIX_FOSSIL, EventFlag.GOT_HELIX_FOSSIL),
)


def fossil_pending(raw):
    events = raw.event_flags
    return bool(
        raw.map_id == int(MapId.MT_MOON_B2F)
        and events is not None
        and len(events) * 8 > int(EventFlag.GOT_HELIX_FOSSIL)
        and event_flag_is_set(events, int(EventFlag.BEAT_MT_MOON_EXIT_SUPER_NERD))
        and not any(event_flag_is_set(events, int(e)) for _, _, e in FOSSILS)
        and raw.bag_items is not None
        and len(raw.bag_items) < 20
        and not any(dict(raw.bag_items).get(int(item), 0) for _, item, _ in FOSSILS)
    )


def fossil_pickup_binding(runtime, actions, *, route):
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    if not fossil_pending(before.raw):
        return None
    verify_rom_bytes(route.rom)
    objects = map_object_events(route.rom, {int(MapId.MT_MOON_B2F)})
    start = Gen1TraversalObserver(
        runtime.reader,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    approaches = []
    for index, item, event in FOSSILS:
        matches = [o for o in objects if o.object_index == index]
        if len(matches) != 1 or matches[0].sprite_id != 62:
            raise ValueError("cartridge fossil object identity differs")
        target = matches[0]
        for facing in TrainerFacing:
            dy, dx = facing.delta
            at = target.at[0] - dy, target.at[1] - dx
            if min(at) < 0:
                continue
            try:
                plan = route.route_world.plan_feasible_to_map(start, target.map_id, goal_at=at)
            except RoutePlanningError:
                continue
            approaches.append((plan, facing, target, item, event))
    if not approaches:
        return None
    plan, facing, target, item, event = min(approaches, key=lambda row: row[0].cost)
    source = runtime.emulator.save_state_bytes()
    terminal, used = None, False

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("fossil pickup is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(route, destination_map=target.map_id, destination_at=plan.terminal_at)(
            actions, runtime.reader, runtime.emulator
        )
        if not any(
            o.sprite_index == target.object_index
            and o.picture_id == target.sprite_id
            and o.at == target.at
            for o in runtime.reader.read_current_map_objects()
        ):
            raise ValueError("fossil object changed before interaction")
        face_pc_boundary(actions, runtime.reader, facing.value)
        for _ in range(96):
            raw = runtime.reader.read()
            if raw.map_id != target.map_id or raw.battle_state != 0:
                raise ValueError("fossil interaction left its native boundary")
            taken = event_flag_is_set(raw.event_flags, int(event))
            if taken and _field_ready(runtime):
                break
            action = MacroActionKind.INTERACT if _field_ready(runtime) else MacroActionKind.CONFIRM
            actions.execute(MacroAction(action))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=24))
        raw = runtime.reader.read()
        expected = dict(before.raw.bag_items)
        expected[int(item)] = expected.get(int(item), 0) + 1
        if (
            not _field_ready(runtime)
            or not event_flag_is_set(raw.event_flags, int(event))
            or any(event_flag_is_set(raw.event_flags, int(e)) for _, _, e in FOSSILS if e != event)
            or dict(raw.bag_items or ()) != expected
            or raw.player_money != before.raw.player_money
            or raw.badge_bits != before.raw.badge_bits
            or raw.party_species_ids != before.raw.party_species_ids
        ):
            raise ValueError("native fossil reward or preserved resources not verified")
        capture_player_lesson_snapshot(runtime)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                objective="reach_cerulean",
                objective_completed=False,
                item=int(item),
                support="least_cost_reachable_fossil_interaction",
                learned_fossil_choice=False,
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
            or not set(lesson["completed_objectives"]) <= set(after["completed_objectives"])
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:fossil-pickup:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, plan.cost / 3000),
        0.1,
        execute,
        verify,
    )
