"""Authenticate a zero-input failed carrier-return transaction, not a PC return.

Old source documents stay immutable. Only a proved never-started return may
recover its previously committed active custody, with the original guard intact.
"""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from .goal_manager import GoalKind, GoalFailureReason
from .goal_manager_runtime import ExecutableGoalBinding, GoalExecutionReport, GoalVerification
from .provenance import canonical_sha256
from .red_player_field_goals import _field_ready
from .red_player_party_guard import RedPlayerPartyGuard

ERROR = "party-loan return has no executable walking Center"


def _qualified_return_abort_guard(runtime, result, context_bytes, execution_started):
    """Read-only strict source/zero-input/native-custody proof; no phase writes."""
    guard = getattr(getattr(runtime, "adapter", None), "party_guard", None)
    custody = None if guard is None else guard.field_carrier
    if (not isinstance(guard, RedPlayerPartyGuard) or custody is None
            or custody.phase != "pending" or not _field_ready(runtime)
            or runtime.emulator.pressed_buttons):
        return None
    try:
        context = json.loads(context_bytes)
        source = sha256(runtime.emulator.save_state_bytes()).hexdigest()
        rows = result["episode"]["outcomes"]
        row = rows[-1]
        if (type(result) is not dict or type(context) is not dict or not isinstance(rows, list)
                or type(row) is not dict or type(row.get("before")) is not dict
                or type(row.get("after")) is not dict or type(row.get("observed_cost")) is not dict
                or type(execution_started) is not dict or any(type(r) is not dict for r in rows)):
            return None
        chain = [dict(error_type="ValueError", error=ERROR)]
        if (result.get("passed") is not True or result["episode"].get("stop_reason") != "execution_failed"
                or result["episode"].get("admission_failure") is not None
                or result.get("released") is not True or result.get("field_ready") is not True
                or result.get("paired_context_authenticated") is not True
                or result.get("error") is not None or result.get("error_type") is not None
                or result.get("context_error") is not None or result.get("cost_lower_bound") is True
                or result.get("state_sha256") != source or context.get("state_sha256") != source
                or result.get("context_sha256") != sha256(context_bytes).hexdigest()
                or result.get("spent") != context.get("spent")
                or context.get("fit_allowed") is not False or context.get("grants_new_budget") is not False
                or canonical_sha256(context.get("field_carrier")) != canonical_sha256(custody.private_dict())
                or row.get("selected_kind") != GoalKind.MANAGE_STORAGE.value
                or row.get("error_type") != "ValueError" or row.get("error") != ERROR
                or row.get("error_chain") != chain or result.get("error_chain") not in (None, chain)
                or row.get("failure_phase") != "execution" or row.get("verification") is not None
                or row.get("ordinary_setback") is not False or row.get("safe_terminal") is not True
                or row.get("before_state_sha256") != source or row.get("terminal_state_sha256") != source
                or row.get("before") != row.get("after")
                or row.get("observed_cost") != dict(actions=0, completed_actions=0, frames=0, cash_spent=0)
                or execution_started.get("selected_kind") != GoalKind.MANAGE_STORAGE.value
                or execution_started.get("state_sha256") != source
                or execution_started.get("selected_binding_ref") != "pokemon.red:field-carrier-return:" + source
                or any(r.get("error_type") or r.get("error") or r.get("error_chain")
                       or r.get("verification") == "failed" and r.get("ordinary_setback") is not True
                       for r in rows[:-1])):
            return None
        for key in ("actions", "completed_actions", "frames", "cash"):
            if type(row["before"].get(key)) is not int or row["before"][key] < 0:
                return None
        for key in ("actions", "completed_actions", "frames", "cash_spent"):
            if type(row["observed_cost"].get(key)) is not int:
                return None
        if row["before"].get("battle_state") != 0 or row["before"].get("buttons_released") is not True:
            return None
        candidate = replace(guard, field_carrier=replace(custody, phase="active"))
        # Same immutable baseline, roles, loanable refs and carrier provenance.
        candidate.verify_authorized_active_roster()
        return candidate
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return None


def retained_field_carrier_return_abort_binding(runtime, actions, *, parent, on_abort=None):
    """Compulsory metadata abort of the exact authenticated failed return only."""
    guard = getattr(getattr(runtime, "adapter", None), "party_guard", None)
    if (not isinstance(guard, RedPlayerPartyGuard) or guard.field_carrier is None
            or guard.field_carrier.phase != "pending"):
        return None
    parent = Path(parent)
    try:
        result = json.loads((parent / "RESULT.json").read_bytes())
        context_bytes = (parent / "CONTEXT.json").read_bytes()
        row = result["episode"]["outcomes"][-1]
        ordinal = row["ordinal"]
        if type(ordinal) is not int or not 0 <= ordinal <= 10000:
            return None
        started_path = parent / "native" / "episode" / f"step-{ordinal:03d}" / "execution-started.json"
        execution_started = json.loads(started_path.read_bytes())
    except (OSError, KeyError, IndexError, TypeError, ValueError):
        return None
    candidate = _qualified_return_abort_guard(runtime, result, context_bytes, execution_started)
    if candidate is None:
        return None
    source = runtime.emulator.save_state_bytes()
    source_sha = sha256(source).hexdigest()
    original_guard_sha = guard.field_carrier.original_guard_sha256
    used, receipt = False, None
    counters = None

    def execute():
        nonlocal used, receipt, counters
        if (used or runtime.adapter.party_guard is not guard
                or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime)
                or runtime.emulator.pressed_buttons):
            raise ValueError("zero-input field-carrier abort source is stale or consumed")
        rechecked = _qualified_return_abort_guard(runtime, result, context_bytes, execution_started)
        if rechecked != candidate:
            raise ValueError("zero-input field-carrier abort custody proof changed")
        used = True
        counters = actions.actions_executed, runtime.emulator.frame_count
        runtime.adapter.party_guard = candidate
        projection_sha = None
        try:
            if on_abort is not None:
                projection_sha = on_abort(candidate.field_carrier)
                if (type(projection_sha) is not str or len(projection_sha) != 64
                        or any(c not in "0123456789abcdef" for c in projection_sha)):
                    raise ValueError("aborted return lacks an exact active preparation projection")
        except BaseException:
            runtime.adapter.party_guard = guard
            raise
        receipt = GoalExecutionReport(0, 0, dict(
            support="authenticated_zero_input_field_carrier_return_abort", model_queries=0,
            source_sha256=source_sha, terminal_sha256=source_sha,
            original_guard_sha256=original_guard_sha, original_source_pending_preserved=True,
            retained_active_field_carrier=True, original_roster_restored=False,
            active_preparation_projection_sha256=projection_sha,
            objective_completed=False, no_controller_input=True, historical_costs_retained=True,
        ))
        return receipt

    def verify(report):
        if (receipt is None or report is not receipt or runtime.adapter.party_guard is not candidate
                or runtime.emulator.save_state_bytes() != source or not _field_ready(runtime)
                or runtime.emulator.pressed_buttons
                or (actions.actions_executed, runtime.emulator.frame_count) != counters):
            return GoalVerification.failed(GoalFailureReason.OUTCOME_NOT_VERIFIED)
        candidate.verify_authorized_active_roster()
        return GoalVerification.succeeded()

    return ExecutableGoalBinding(
        "pokemon.red:aborted-field-carrier-return:" + source_sha,
        GoalKind.RECOVER_CONTROL, 0.0, 0.0, execute, verify, maximum_cash_debit=0,
    )