"""Settle an already interrupted wild encounter with existing escape support."""

from dataclasses import asdict, replace
from hashlib import sha256

from .goal_manager import GoalDecisionOutcome, GoalFailureReason, GoalKind
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .observation import event_flag_is_set
from .red_player_field_goals import _field_ready
from .route_1_wild import flee_wild


def static_escape_expected_events(before, target):
    """Exactly one declared consumed encounter bit, not arbitrary event changes."""
    if before.event_flags is None or event_flag_is_set(before.event_flags, target.event_flag):
        raise ValueError("static escape needs an unconsumed native event")
    events = bytearray(before.event_flags)
    events[target.event_flag // 8] |= 1 << (target.event_flag % 8)
    return bytes(events)


def retained_native_static_target(reader, rom):
    """Recognize a cartridge one-off before offering any ordinary Run action.

    Its capture journal, not generic control recovery, owns the remaining
    encounter allocation. Original identity also protects transformed targets.
    """
    from .red_static_capture import red_static_capture_targets

    raw = reader.read()
    if raw.battle_state != 1:
        return None
    candidates = tuple(t for t in red_static_capture_targets(rom) if t.map_id == raw.map_id)
    if not candidates:
        return None
    identity_reader = getattr(
        reader, "read_retained_wild_identity", reader.read_wild_capture_identity
    )
    identity = identity_reader()
    if identity is None:
        raise ValueError("one-off map lacks wild identity; no ordinary Run authorized")
    return next((t for t in candidates if t.internal_species == identity.original_species_id), None)


def interrupted_wild_binding(
    runtime, actions, *, consumed_static_target=None, rom=None, allow_fainted_active=False,
    pending_trainer_factory=None,
):
    if pending_trainer_factory is not None and not callable(pending_trainer_factory):
        raise TypeError("pending trainer recovery factory must be callable")
    if pending_trainer_factory is not None and (rom is None or consumed_static_target is not None):
        raise ValueError("pending trainer recovery requires an ordinary cartridge-bound escape")
    if type(allow_fainted_active) is not bool:
        raise TypeError("fainted-active escape requires an explicit boolean")
    if allow_fainted_active and consumed_static_target is not None:
        raise ValueError("fainted-active escape is limited to ordinary encounters")
    before = runtime.reader.read()
    if before.battle_state != 1 or not before.party_hp or not any(before.party_hp):
        return None
    target = consumed_static_target
    if (target is None and rom is not None
            and retained_native_static_target(runtime.reader, rom) is not None):
        raise ValueError(
            "native one-off needs its retained capture allocation; no ordinary Run authorized"
        )
    expected_events = before.event_flags
    owned = None
    if target is not None:
        from .red_snorlax_capture import route12_snorlax_target
        from .red_static_capture import RedStaticCaptureTarget

        # Explicit Route12 loss only; ordinary escape and other one-offs keep
        # their historical strict boundary. No item or capture fallback.
        identity = runtime.reader.read_wild_capture_identity()
        if (
            type(target) is not RedStaticCaptureTarget
            or rom is None
            or target != route12_snorlax_target(rom)
            or before.map_id != target.map_id
            or before.enemy_level != target.level
            or identity is None
            or identity.original_species_id != target.internal_species
            or before.party_hp[0] <= 0
        ):
            raise ValueError("static escape requires the exact live supported encounter")
        expected_events = static_escape_expected_events(before, target)
        owned = runtime.reader.read_pokedex_state().owned_species
    source = runtime.emulator.save_state_bytes()
    used, terminal, trainer_verdict = False, None, None

    def execute():
        nonlocal used, terminal, trainer_verdict
        if used or runtime.emulator.save_state_bytes() != source:
            raise ValueError("interrupted wild recovery is stale or consumed")
        used = True
        a, f = actions.actions_executed, runtime.emulator.frame_count
        escape = flee_wild
        escape_options = {}
        if allow_fainted_active:
            # The existing whole-party proof also supports a fainted active
            # reserve. Historical callers retain their first-slot boundary.
            from .wild_party_flee import flee_with_fainted_lead

            escape = flee_with_fainted_lead
            escape_options = dict(
                emulator=runtime.emulator, allow_new_faints=True, allow_status_changes=True,
                allow_opponent_ko_exit=bool(rom is not None and callable(
                    getattr(runtime.reader, "read_retained_wild_identity", None)
                )),
            )
        evidence = escape(
            actions,
            runtime.reader,
            before,
            expected_map_id=before.map_id,
            route_name="interrupted player encounter",
            stabilization_frames=120,
            error_type=RuntimeError,
            **escape_options,
        )
        after = runtime.reader.read()
        if (
            not evidence.verified
            or after.player_money != before.player_money
            or after.bag_items != before.bag_items
            or after.event_flags != expected_events
            or after.badge_bits != before.badge_bits
        ):
            raise ValueError("interrupted wild recovery did not preserve field state")
        chained = None
        if not _field_ready(runtime):
            if (
                pending_trainer_factory is None
                or after.battle_state != 0
                or (after.map_id, after.player_y, after.player_x)
                != (before.map_id, before.player_y, before.player_x)
                or not runtime.reader.trainer_engagement_active()
            ):
                raise ValueError("interrupted wild recovery did not preserve field state")
            pending = runtime.emulator.save_state_bytes()
            frame = runtime.emulator.frame_count
            binding = pending_trainer_factory()
            if (
                runtime.emulator.save_state_bytes() != pending
                or runtime.emulator.frame_count != frame
                or binding is None
                or binding.kind is not GoalKind.RECOVER_CONTROL
                or binding.binding_ref
                != "pokemon.red:retained-engagement:" + sha256(pending).hexdigest()
            ):
                raise ValueError("wild escape successor lacks its exact retained trainer")
            trainer_actions = actions.actions_executed
            report = binding.execute()
            trainer_verdict = binding.verify(report)
            battle = report.evidence.get("battle", {})
            won = (trainer_verdict.status is GoalDecisionOutcome.SUCCEEDED
                   and battle.get("outcome") == "won")
            lost = (trainer_verdict.status is GoalDecisionOutcome.FAILED
                    and trainer_verdict.failure_reason is GoalFailureReason.RESOURCE_LOST
                    and battle.get("outcome") == "lost")
            if (
                not (won or lost)
                or not _field_ready(runtime)
                or battle.get("field_ready") is not True
                or report.evidence.get("support") != "already_engaged_native_trainer"
                or report.evidence.get("source_sha256") != sha256(pending).hexdigest()
                or report.evidence.get("terminal_sha256")
                != sha256(runtime.emulator.save_state_bytes()).hexdigest()
                or report.actions_executed != actions.actions_executed - trainer_actions
                or report.frames_executed != runtime.emulator.frame_count - frame
            ):
                raise ValueError("wild escape retained trainer did not independently settle")
            chained = dict(report.evidence,
                binding_ref=binding.binding_ref, verification=trainer_verdict.status.value,
                model_goal_queries=0, new_trainer_approach=False)
        if target is not None:
            from .wild_party_flee import validate_flee_party

            validate_flee_party(replace(before, event_flags=expected_events), after)
            if runtime.reader.read_pokedex_state().owned_species != owned or any(
                o.sprite_index == target.object_index and o.visible
                for o in runtime.reader.read_current_map_objects()
            ):
                raise ValueError("static escape lacks lost source and unchanged registration proof")
        terminal = runtime.emulator.save_state_bytes()
        return GoalExecutionReport(
            actions.actions_executed - a,
            runtime.emulator.frame_count - f,
            dict(
                escape=evidence.public_dict(),
                learned_recovery=False,
                model_queries=0,
                **({"chained_trainer_recovery": chained, "battle": chained["battle"]}
                   if chained is not None else {}),
                **({"lost_static_target": asdict(target), "captured": False} if target else {}),
            ),
        )

    def verify(report):
        if (
            terminal is None
            or runtime.emulator.save_state_bytes() != terminal
            or not _field_ready(runtime)
        ):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        return trainer_verdict if trainer_verdict is not None else GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:interrupted-wild:" + sha256(source).hexdigest(),
        GoalKind.RECOVER_CONTROL,
        0.04,
        0.1,
        execute,
        verify,
    )
