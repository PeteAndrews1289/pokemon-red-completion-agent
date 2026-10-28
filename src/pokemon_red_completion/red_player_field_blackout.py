"""Mandatory settlement of an already observed field loss, never manufactured."""

from hashlib import sha256

from .goal_manager import GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .red_blackout_recovery import settle_red_blackout
from .red_goal_skills import _raw_party_fully_restored
from .red_player_field_goals import _field_ready
from .red_player_lesson import capture_player_lesson_snapshot


def field_blackout_binding(runtime, actions):
    raw = runtime.reader.read()
    native_loss = raw.battle_state in {1, 2}
    field_loss = (
        raw.battle_state == 0
        and not runtime.reader.read_input_readiness().ready
        and runtime.reader.read_bottom_dialogue_box_visible()
    )
    if (
        not (native_loss or field_loss)
        or not raw.party_hp
        or any(raw.party_hp)
        or runtime.emulator.pressed_buttons
    ):
        return None
    _, before = capture_player_lesson_snapshot(runtime)
    state = runtime.emulator.save_state_bytes()
    used, terminal = False, None

    def preserved(lesson):
        return [
            (
                m["specimen_ref"],
                m["species_id"],
                m["level"],
                m["experience"],
                tuple(x[0] for x in m["moves"]),
            )
            for m in lesson["party"]
        ]

    def execute():
        nonlocal used, terminal
        if used or runtime.emulator.save_state_bytes() != state:
            raise ValueError("field blackout boundary is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        evidence = settle_red_blackout(
            actions, runtime.reader, runtime.emulator, allow_field_loss=True
        )
        after, lesson = capture_player_lesson_snapshot(runtime)
        if (
            not _field_ready(runtime)
            or not _raw_party_fully_restored(after.raw)
            or preserved(before) != preserved(lesson)
            or before["completed_objectives"] != lesson["completed_objectives"]
        ):
            raise ValueError("field blackout did not preserve progress and settle")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(blackout=evidence, learned_recovery=False, model_queries=0),
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
        "pokemon.red:field-blackout:" + sha256(state).hexdigest(),
        GoalKind.RECOVER_CONTROL,
        0.04,
        0.02,
        execute,
        verify,
    )
