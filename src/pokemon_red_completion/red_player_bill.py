"""One observed Bill interaction phase, without an automatic chapter route.

Exact-Red separator object is (y=4,x=1); interact from (y=5,x=1), facing up.
This is a mechanic endpoint, not a movement recipe. See data/events/hidden_events.asm
and engine/events/hidden_events/bills_house_pc.asm. NPC positions come from the
current toggle-aware table, including Bill's scripted movement.
"""

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


def bill_interaction_phase(raw):
    if raw.map_id != int(MapId.BILLS_HOUSE) or raw.event_flags is None:
        return None
    def has(flag):
        return event_flag_is_set(raw.event_flags, int(flag))
    if has(EventFlag.GOT_SS_TICKET):
        return None
    if not has(EventFlag.BILL_SAID_USE_CELL_SEPARATOR):
        return "request", 1, int(EventFlag.BILL_SAID_USE_CELL_SEPARATOR)
    if not has(EventFlag.USED_CELL_SEPARATOR_ON_BILL):
        return "separator", None, int(EventFlag.MET_BILL_2)
    if has(EventFlag.MET_BILL) and has(EventFlag.MET_BILL_2):
        return "ticket", 2, int(EventFlag.GOT_SS_TICKET)
    return None


def bill_interaction_binding(runtime, actions, *, route):
    if not _field_ready(runtime):
        return None
    before, lesson = capture_player_lesson_snapshot(runtime)
    phase = bill_interaction_phase(before.raw)
    if phase is None or "help_bill" not in {
        o.id for o in runtime.adapter.graph.available_objectives(before.game_state)
    }:
        return None
    name, object_index, expected_event = phase
    required_events = (int(EventFlag.BILL_SAID_USE_CELL_SEPARATOR),)
    if name in {"separator", "ticket"}:
        required_events += tuple(
            int(e)
            for e in (
                EventFlag.USED_CELL_SEPARATOR_ON_BILL,
                EventFlag.MET_BILL,
                EventFlag.MET_BILL_2,
            )
        )
    if name == "ticket":
        required_events += (int(EventFlag.GOT_SS_TICKET),)
    if before.raw.bag_items is None or (
        name == "ticket"
        and (
            len(before.raw.bag_items) >= 20
            or dict(before.raw.bag_items).get(int(ItemId.SS_TICKET), 0)
        )
    ):
        return None
    verify_rom_bytes(route.rom)
    start = Gen1TraversalObserver(
        runtime.reader,
        hazard_projector=Gen1TrainerSightProjector(
            route.rom, runtime.reader, full_event_offsets=True
        ),
    ).observe()
    live_target = None
    if object_index is None:
        choices = [((5, 1), TrainerFacing.UP)]
    else:
        objects = [
            o
            for o in map_object_events(route.rom, {int(MapId.BILLS_HOUSE)})
            if o.object_index == object_index
        ]
        matches = [
            o for o in runtime.reader.read_current_map_objects() if o.sprite_index == object_index
        ]
        if len(objects) != 1 or len(matches) != 1 or matches[0].picture_id != objects[0].sprite_id:
            raise ValueError("Bill phase requires its observed cartridge object")
        live_target = matches[0]
        choices = [
            ((live_target.at[0] - f.delta[0], live_target.at[1] - f.delta[1]), f)
            for f in TrainerFacing
        ]
    plans = []
    for at, facing in choices:
        if min(at) < 0:
            continue
        try:
            plan = route.route_world.plan_feasible_to_map(start, int(MapId.BILLS_HOUSE), goal_at=at)
        except RoutePlanningError:
            continue
        plans.append((plan, facing))
    if not plans:
        return None
    plan, facing = min(plans, key=lambda row: row[0].cost)
    cash_route = certified_cash_safe_transition(route, before.raw, plan)
    source = runtime.emulator.save_state_bytes()
    terminal, used = None, False

    def execute():
        nonlocal terminal, used
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Bill interaction is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        replace(
            cash_route or route, destination_map=int(MapId.BILLS_HOUSE),
            destination_at=plan.terminal_at,
        )(
            actions, runtime.reader, runtime.emulator
        )
        if live_target is not None and not any(
            (o.sprite_index, o.picture_id, o.at)
            == (live_target.sprite_index, live_target.picture_id, live_target.at)
            for o in runtime.reader.read_current_map_objects()
        ):
            raise ValueError("Bill moved before interaction")
        if bill_interaction_phase(runtime.reader.read()) != phase:
            raise ValueError("Bill phase changed before interaction")
        face_pc_boundary(actions, runtime.reader, facing.value)
        actions.execute(MacroAction(MacroActionKind.INTERACT))
        for _ in range(128):
            raw = runtime.reader.read()
            if raw.map_id != int(MapId.BILLS_HOUSE) or raw.battle_state:
                raise ValueError("Bill interaction left its native boundary")
            if event_flag_is_set(raw.event_flags, expected_event) and _field_ready(runtime):
                break
            actions.execute(MacroAction(MacroActionKind.CONFIRM))
            actions.execute(MacroAction(MacroActionKind.WAIT, repeat=24))
        raw = runtime.reader.read()
        expected_bag = dict(before.raw.bag_items)
        if name == "ticket":
            expected_bag[int(ItemId.SS_TICKET)] = 1
        if (
            not _field_ready(runtime)
            or not all(event_flag_is_set(raw.event_flags, e) for e in required_events)
            or dict(raw.bag_items or ()) != expected_bag
            or raw.player_money != before.raw.player_money
            or raw.badge_bits != before.raw.badge_bits
            or raw.party_species_ids != before.raw.party_species_ids
        ):
            raise RuntimeError("Bill phase or preserved resources not verified")
        if name == "ticket":
            runtime.observer.latch_verified_facts(
                runtime.adapter.graph.objective("help_bill").completion_facts
            )
        capture_player_lesson_snapshot(runtime)
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                objective="help_bill",
                objective_completed=name == "ticket",
                phase=name,
                native_event=expected_event,
                source_sha256=sha256(source).hexdigest(),
                terminal_sha256=sha256(terminal).hexdigest(),
                support="bill_dialogue_phase",
            ),
        )

    def verify(report):
        _, snapshot = capture_player_lesson_snapshot(runtime)
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
            or not set(lesson["completed_objectives"]) <= set(snapshot["completed_objectives"])
            or (name == "ticket" and "help_bill" not in snapshot["completed_objectives"])
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:bill-phase:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        min(1.0, 0.02 + plan.cost / 3000),
        0.05,
        execute,
        verify,
        maximum_cash_debit=0 if cash_route is not None else None,
    )
