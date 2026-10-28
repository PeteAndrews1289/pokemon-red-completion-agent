"""Expose legal Cut teaching as disclosed story-execution support."""

from hashlib import sha256

from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import ItemId
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_machine_teaching import execute_machine_lesson, plan_machine_lesson
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot


def cut_lesson_binding(runtime, actions, *, rom, allow_status_replacement=False):
    """Prefer empty slots;explicit opt-in may replace a compatible non-HM status move."""
    if type(allow_status_replacement) is not bool:
        raise TypeError("Cut status replacement permission must be boolean")
    if not _field_ready(runtime):
        return None
    raw = runtime.reader.read()
    if any(15 in moves for moves in raw.party_moves or ()):
        return None
    if "defeat_surge" not in {
        o.id
        for o in runtime.adapter.graph.available_objectives(runtime.adapter.observe().game_state)
    }:
        return None
    lesson = None
    for slot, moves in enumerate(raw.party_moves or (), 1):
        if 0 not in moves:
            continue
        try:
            lesson = plan_machine_lesson(
                rom,
                runtime.reader,
                item_id=int(ItemId.HM01_CUT),
                party_slot=slot,
                replace_slot=moves.index(0) + 1,
            )
        except ValueError:
            continue
        break
    if lesson is None and allow_status_replacement:
        for slot, moves in enumerate(raw.party_moves or (), 1):
            if 0 in moves:
                continue
            for index, move in enumerate(moves, 1):
                if (
                    move in {15, 19, 57, 70, 148}
                    or RED_BATTLE_CATALOG.resolve_move(pokemon_red_move_ref(move)).category
                    != "status"
                ):
                    continue
                try:
                    lesson = plan_machine_lesson(
                        rom,
                        runtime.reader,
                        item_id=int(ItemId.HM01_CUT),
                        party_slot=slot,
                        replace_slot=index,
                    )
                except ValueError:
                    continue
                break
            if lesson is not None:
                break
    if lesson is None:
        return None
    source = runtime.emulator.save_state_bytes()
    terminal, used = None, False

    def execute():
        nonlocal terminal, used
        if used or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime):
            raise ValueError("Cut lesson is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        execute_machine_lesson(runtime.emulator, actions, runtime.reader, lesson, rom=rom)
        capture_player_lesson_snapshot(runtime)
        if not _field_ready(runtime):
            raise RuntimeError("Cut lesson did not restore field control")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                support=(
                    "first_compatible_empty_slot_cut_lesson"
                    if raw.party_moves[lesson.party_slot - 1][lesson.replace_slot - 1] == 0
                    else "first_compatible_non_hm_status_cut_lesson"
                ),
                party_slot=lesson.party_slot,
                move_slot=lesson.replace_slot,
                move=15,
                replaced_move=raw.party_moves[lesson.party_slot - 1][lesson.replace_slot - 1],
                recipient_selection_learned=False,
                replacement_selection_learned=False,
                objective_completed=False,
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
        "pokemon.red:cut-lesson:" + sha256(source).hexdigest(),
        GoalKind.ADVANCE_STORY,
        0.04,
        0.0,
        execute,
        verify,
        maximum_cash_debit=0,
    )
