import hashlib

import pytest

from pokemon_red_completion.red_autonomous_capture_recovery import (
    RedAutonomousCaptureRecoveryError,
    validate_autonomous_capture_recovery_source,
)


def _documents():
    state = b"failed-wild-battle"
    outcome = {
        "selected_kind": "acquire_species",
        "learning_eligible": True,
        "safe_terminal": False,
        "error_type": "RedTravelCaptureError",
        "terminal_state_sha256": hashlib.sha256(state).hexdigest(),
    }
    result = {
        "schema": "pokemon.red.autonomous-option-result.v1",
        "stop_reason": "execution_failed",
        "model_sha256": "a" * 64,
        "outcomes": [outcome],
    }
    decision = {
        "schema": "pokemon.red.live-mixed-option-choice.v1",
        "mode": "model_exploration",
        "selected_option_kind": "acquire",
    }
    execution = {
        "selected_kind": "acquire_species",
        "selected_binding_ref": "pokemon.red:acquisition:wild:generic",
    }
    return state, result, outcome, decision, execution


def test_exact_failed_model_acquisition_is_recoverable_without_a_new_choice():
    state, result, outcome, decision, execution = _documents()

    source = validate_autonomous_capture_recovery_source(
        result=result,
        outcome=outcome,
        decision=decision,
        execution_started=execution,
        terminal_state=state,
    )

    assert source.model_sha256 == "a" * 64
    assert source.terminal_state_sha256 == hashlib.sha256(state).hexdigest()
    assert source.selected_binding_ref == execution["selected_binding_ref"]


@pytest.mark.parametrize(
    ("document", "key", "value"),
    [
        ("result", "stop_reason", "decision_budget"),
        ("outcome", "selected_kind", "resupply"),
        ("outcome", "learning_eligible", False),
        ("outcome", "safe_terminal", True),
        ("decision", "mode", "deterministic_safety"),
        ("execution", "selected_kind", "manage_storage"),
    ],
)
def test_nonmatching_or_safe_terminals_cannot_be_relabelled_as_capture_recovery(
    document, key, value
):
    state, result, outcome, decision, execution = _documents()
    documents = {
        "result": result,
        "outcome": outcome,
        "decision": decision,
        "execution": execution,
    }
    documents[document][key] = value
    if document == "outcome":
        result["outcomes"][-1] = outcome

    with pytest.raises(RedAutonomousCaptureRecoveryError):
        validate_autonomous_capture_recovery_source(
            result=result,
            outcome=outcome,
            decision=decision,
            execution_started=execution,
            terminal_state=state,
        )


def test_terminal_hash_mismatch_is_rejected():
    state, result, outcome, decision, execution = _documents()

    with pytest.raises(RedAutonomousCaptureRecoveryError, match="hash differs"):
        validate_autonomous_capture_recovery_source(
            result=result,
            outcome=outcome,
            decision=decision,
            execution_started=execution,
            terminal_state=state + b"changed",
        )
