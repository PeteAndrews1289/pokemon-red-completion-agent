"""Authenticate one infrastructure-only continuation of a model-selected capture."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass


class RedAutonomousCaptureRecoveryError(ValueError):
    """A failed autonomous capture is not eligible for exact-state recovery."""


@dataclass(frozen=True, slots=True)
class RedAutonomousCaptureRecoverySource:
    model_sha256: str
    terminal_state_sha256: str
    selected_binding_ref: str


def validate_autonomous_capture_recovery_source(
    *,
    result: Mapping[str, object],
    outcome: Mapping[str, object],
    decision: Mapping[str, object],
    execution_started: Mapping[str, object],
    terminal_state: bytes,
) -> RedAutonomousCaptureRecoverySource:
    """Admit only the retained terminal of one failed model acquisition.

    Recovery continues the already persisted choice.  It cannot select a new
    target, replay the route, relabel the failed outcome, or become a learning
    example.
    """

    if result.get("schema") != "pokemon.red.autonomous-option-result.v1":
        raise RedAutonomousCaptureRecoveryError("autonomous result schema differs")
    if result.get("stop_reason") != "execution_failed":
        raise RedAutonomousCaptureRecoveryError("autonomous run did not stop on execution failure")
    outcomes = result.get("outcomes")
    if not isinstance(outcomes, list) or not outcomes or outcomes[-1] != dict(outcome):
        raise RedAutonomousCaptureRecoveryError("failed outcome is not the retained run terminal")
    if (
        outcome.get("selected_kind") != "acquire_species"
        or outcome.get("learning_eligible") is not True
        or outcome.get("safe_terminal") is not False
        or not isinstance(outcome.get("error_type"), str)
    ):
        raise RedAutonomousCaptureRecoveryError("terminal is not a failed model acquisition")
    if (
        decision.get("schema") != "pokemon.red.live-mixed-option-choice.v1"
        or decision.get("mode") != "model_exploration"
        or decision.get("selected_option_kind") != "acquire"
    ):
        raise RedAutonomousCaptureRecoveryError("persisted choice is not a model acquisition")
    binding_ref = execution_started.get("selected_binding_ref")
    if (
        execution_started.get("selected_kind") != "acquire_species"
        or not isinstance(binding_ref, str)
        or not binding_ref
    ):
        raise RedAutonomousCaptureRecoveryError("execution receipt lacks its acquisition binding")
    terminal_sha256 = hashlib.sha256(terminal_state).hexdigest()
    if outcome.get("terminal_state_sha256") != terminal_sha256:
        raise RedAutonomousCaptureRecoveryError("retained terminal state hash differs")
    model_sha256 = result.get("model_sha256")
    if not isinstance(model_sha256, str) or len(model_sha256) != 64:
        raise RedAutonomousCaptureRecoveryError("autonomous model identity differs")
    return RedAutonomousCaptureRecoverySource(
        model_sha256=model_sha256,
        terminal_state_sha256=terminal_sha256,
        selected_binding_ref=binding_ref,
    )
