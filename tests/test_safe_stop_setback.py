from hashlib import sha256
from types import SimpleNamespace as N

import pytest
import run_configured_red_player as configured
from run_configured_red_player import (
    SAFE_STOP_CONTINUATION_SCHEMA,
    declared_safe_stop_continuation,
    qualified_safe_stop_setback,
)

STATE = b"terminal"
SHA = sha256(STATE).hexdigest()


class _Guard:
    def __init__(self, fail=False, carrier=None):
        self.fail, self.field_carrier, self.calls = fail, carrier, 0

    def verify_active_roster_restored(self):
        self.calls += 1
        if self.fail:
            raise ValueError("retained active party has not been restored")


def _runtime(*, pressed=0, state=STATE, battle=0, hp=(20, 0), guard=None):
    return N(
        emulator=N(pressed_buttons=pressed, save_state_bytes=lambda: state),
        reader=N(read=lambda: N(battle_state=battle, party_hp=hp)),
        adapter=N(party_guard=guard),
    )


def _row(**outcome):
    last = dict(
        selected_kind="resupply",
        safe_terminal=True,
        terminal_state_sha256=SHA,
        error_type="TrainerFundingBattleError",
        error="party species changed after battle",
        failure_phase="execution",
        verification=None,
        failure_reason=None,
    )
    last.update(outcome)
    return dict(
        released=True,
        field_ready=True,
        state_sha256=SHA,
        episode=dict(stop_reason="execution_failed", outcomes=[dict(selected_kind="advance_story"), last]),
    )


@pytest.fixture(autouse=True)
def _field(monkeypatch):
    monkeypatch.setattr(configured, "_field_ready", lambda runtime: True)
    monkeypatch.setattr(configured, "RedPlayerPartyGuard", _Guard)


def test_safe_execution_failure_is_a_typed_setback():
    guard = _Guard()
    assert qualified_safe_stop_setback(
        _row(), runtime=_runtime(guard=guard), reason="native_execution_error"
    ) == ("resupply", "TrainerFundingBattleError", "party species changed after battle")
    assert guard.calls == 1


def test_safe_verification_failure_is_a_typed_setback():
    row = _row(error_type=None, error=None, failure_phase=None, verification="failed",
               failure_reason="outcome_not_verified", selected_kind="evolve_species")
    row["episode"]["stop_reason"] = "verification_failed"
    assert qualified_safe_stop_setback(row, runtime=_runtime(), reason="verification_failed") == (
        "evolve_species", "verification", "outcome_not_verified")


def _fault(name):
    row, runtime, reason = _row(), _runtime(), "native_execution_error"
    if name == "reason":
        reason = "no_executable_progress"
    elif name == "runner_error":
        row["error_type"] = "PartyReadError"
    elif name == "checkpoint":
        row["checkpoint_export_error"] = "x"
    elif name == "admission":
        row["episode"]["admission_failure"] = {"x": 1}
    elif name == "unreleased":
        row["released"] = False
    elif name == "not_field_ready":
        row["field_ready"] = False
    elif name == "stop":
        row["episode"]["stop_reason"] = "unsafe_terminal"
    elif name == "unsafe":
        row["episode"]["outcomes"][-1]["safe_terminal"] = False
    elif name == "control":
        row["episode"]["outcomes"][-1]["selected_kind"] = "recover_control"
    elif name == "terminal":
        row["episode"]["outcomes"][-1]["terminal_state_sha256"] = "0" * 64
    elif name == "budget":
        row["episode"]["outcomes"][-1]["error_type"] = sorted(configured.CHUNK_BUDGET_ERRORS)[0]
    elif name == "prior_error":
        row["episode"]["outcomes"][0]["error_type"] = "RouteExecutionError"
    elif name == "phase":
        row["episode"]["outcomes"][-1]["failure_phase"] = "selection"
    elif name == "pressed":
        runtime = _runtime(pressed=1)
    elif name == "stale":
        runtime = _runtime(state=b"other")
    elif name == "battle":
        runtime = _runtime(battle=1)
    elif name == "fainted":
        runtime = _runtime(hp=(0, 0))
    elif name == "guard":
        runtime = _runtime(guard=_Guard(fail=True))
    elif name == "carrier":
        runtime = _runtime(guard=_Guard(carrier=object()))
    return row, runtime, reason


@pytest.mark.parametrize(
    "name",
    ["reason", "runner_error", "checkpoint", "admission", "unreleased", "not_field_ready", "stop",
     "unsafe", "control", "terminal", "budget", "prior_error", "phase", "pressed", "stale",
     "battle", "fainted", "guard", "carrier"],
)
def test_unsafe_or_unknown_stops_stay_terminal(name):
    row, runtime, reason = _fault(name)
    assert qualified_safe_stop_setback(row, runtime=runtime, reason=reason) is None


def test_field_not_ready_live_stays_terminal(monkeypatch):
    monkeypatch.setattr(configured, "_field_ready", lambda runtime: False)
    assert qualified_safe_stop_setback(_row(), runtime=_runtime(), reason="native_execution_error") is None


def _spec(**changes):
    spec = dict(schema=SAFE_STOP_CONTINUATION_SCHEMA, reason="M0 fresh baseline",
                maximum_total=16, maximum_repeats=2, hold_menus=3)
    spec.update(changes)
    return spec


def test_declaration_is_explicit_bounded_and_development_only():
    assert declared_safe_stop_continuation({"partition": "development"}) is None
    plan = {"partition": "development", "safe_stop_continuation": _spec()}
    assert declared_safe_stop_continuation(plan)["hold_menus"] == 3


@pytest.mark.parametrize(
    "plan",
    [
        {"partition": "train", "safe_stop_continuation": _spec()},
        {"partition": "development", "official_acceptance": True, "safe_stop_continuation": _spec()},
        {"partition": "development", "safe_stop_continuation": _spec(schema="x")},
        {"partition": "development", "safe_stop_continuation": _spec(reason=" ")},
        {"partition": "development", "safe_stop_continuation": _spec(maximum_total=0)},
        {"partition": "development", "safe_stop_continuation": _spec(maximum_total=65)},
        {"partition": "development", "safe_stop_continuation": _spec(maximum_repeats=17)},
        {"partition": "development", "safe_stop_continuation": _spec(hold_menus=17)},
        {"partition": "development", "safe_stop_continuation": _spec(hold_menus=True)},
        {"partition": "development", "safe_stop_continuation": dict(_spec(), extra=1)},
    ],
)
def test_declaration_rejects_unbounded_or_out_of_scope(plan):
    with pytest.raises(ValueError, match="bounded DEVELOPMENT"):
        declared_safe_stop_continuation(plan)
