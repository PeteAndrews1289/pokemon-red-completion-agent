"""Cartridge Captain interaction, independently verified before crediting Cut."""

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
from .red_player_cash_exposure import certified_cash_safe_transition
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot
from .rom import verify_rom_bytes
from .route_plan import RoutePlanningError


def captain_interaction_binding(runtime, actions, *, route):
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    raw = before.raw
    room = int(MapId.SS_ANNE_CAPTAINS_ROOM)
    events = (int(EventFlag.RUBBED_CAPTAINS_BACK), int(EventFlag.GOT_HM01))
    if (
        raw.map_id != room
        or raw.event_flags is None
        or raw.bag_items is None
        or len(raw.bag_items) >= 20
        or dict(raw.bag_items).get(int(ItemId.HM01_CUT), 0)
        or event_flag_is_set(raw.event_flags, events[1])
        or runtime.reader.read_ss_anne_rival_script() != 4
        or "obtain_cut"
        not in {o.id for o in runtime.adapter.graph.available_objectives(before.game_state)}
    ):
        return None
    verify_rom_bytes(route.rom)
    objects = [o for o in map_object_events(route.rom, {room}) if o.object_index == 1]
    live = [o for o in runtime.reader.read_current_map_objects() if o.sprite_index == 1]
    if (
        len(objects) != 1
        or len(live) != 1
        or (objects[0].sprite_id, objects[0].movement) != (46, 255)
        or (live[0].picture_id, live[0].at) != (objects[0].sprite_id, (objects[0].y, objects[0].x))
    ):
        raise ValueError("Captain requires his observed cartridge object")
    target = live[0]
    start = Gen1TraversalObserver(
        runtime.reader,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    plans = []
    for facing in TrainerFacing:
        at = (target.at[0] - facing.delta[0], target.at[1] - facing.delta[1])
        if min(at) < 0:
            continue
        try:
            plan = route.route_world.plan_feasible_to_map(start, room, goal_at=at)
        except RoutePlanningError:
            continue
        plans.append((plan, facing))
    if not plans:
        return None
    plan, facing = min(plans, key=lambda row: row[0].cost)
    cash_route = certified_cash_safe_transition(route, raw, plan)
    source = runtime.emulator.save_state_bytes()
    terminal, used = None, False

    def execute():
        nonlocal terminal, used
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Captain interaction is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(cash_route or route, destination_map=room, destination_at=plan.terminal_at)(
            actions, runtime.reader, runtime.emulator
        )
        if not any(
            (o.sprite_index, o.picture_id, o.at) == (1, target.picture_id, target.at)
            for o in runtime.reader.read_current_map_objects()
        ):
            raise ValueError("Captain moved before interaction")
        face_pc_boundary(actions, runtime.reader, facing.value)
        for _ in range(128):
            current = runtime.reader.read()
            if current.map_id != room or current.battle_state:
                raise ValueError("Captain interaction left its native boundary")
            if all(event_flag_is_set(current.event_flags, e) for e in events) and _field_ready(
                runtime
            ):
                break
            kind = MacroActionKind.INTERACT if _field_ready(runtime) else MacroActionKind.CONFIRM
            actions.execute(MacroAction(kind))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=24))
        current = runtime.reader.read()
        expected_bag = dict(raw.bag_items)
        expected_bag[int(ItemId.HM01_CUT)] = 1
        if (
            not _field_ready(runtime)
            or not all(event_flag_is_set(current.event_flags, e) for e in events)
            or dict(current.bag_items or ()) != expected_bag
            or current.player_money != raw.player_money
            or current.badge_bits != raw.badge_bits
            or current.party_species_ids != raw.party_species_ids
            or current.party_hp != raw.party_hp
            or current.party_status != raw.party_status
            or runtime.reader.read_ss_anne_rival_script() != 4
        ):
            raise RuntimeError("Captain Cut reward or preserved resources not verified")
        runtime.observer.latch_verified_facts(
            runtime.adapter.graph.objective("obtain_cut").completion_facts
        )
        capture_player_lesson_snapshot(runtime)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                objective="obtain_cut",
                objective_completed=True,
                native_events=list(events),
                source_sha256=sha256(source).hexdigest(),
                terminal_sha256=sha256(terminal).hexdigest(),
                support="captain_dialogue_and_reward",
            ),
        )

    def verify(report):
        _, snapshot = capture_player_lesson_snapshot(runtime)
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
            or "obtain_cut" not in snapshot["completed_objectives"]
            or not set(lesson["completed_objectives"]) <= set(snapshot["completed_objectives"])
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:captain:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, 0.02 + plan.cost / 3000),
        0.05,
        execute,
        verify,
        maximum_cash_debit=0 if cash_route is not None else None,
    )
