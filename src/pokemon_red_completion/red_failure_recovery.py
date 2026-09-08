"""Exact failed-state provenance for separately metered deterministic recovery.

A failed choice stays failed and unfit. Recovery is a support operation with
zero policy decisions, not a new independent root or an evolution retry.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pokemon_red_completion.private_artifacts import PrivateArtifactRoot

RECOVERY_TERMINAL_SCHEMA = "pokemon.red.forced-failure-recovery-terminal.v1"
RECOVERY_CHECKPOINT_SCHEMA = "pokemon.red.private-recovery-checkpoint.v1"


class RedFailureRecoveryError(ValueError):
    """A recovery cannot preserve its exact failed predecessor and accounting."""


def authenticated_failure_state(
    store: PrivateArtifactRoot,
    *,
    episode_id: str,
    manifest_sha256: str,
    state_sha256: str,
    parent_state_sha256: str,
    parent_envelope_sha256: str,
    profile_sha256: str,
    rom_sha256: str,
) -> Mapping[str, object]:
    """Read the last exact failure capture, not a preceding safe quantum."""
    episode = store.open_failed_episode(episode_id)
    if episode.manifest_sha256 != manifest_sha256:
        raise RedFailureRecoveryError("failed trajectory identity differs")
    metadata = episode.read_header().get("metadata")
    expected = {
        "state_sha256": parent_state_sha256,
        "envelope_sha256": parent_envelope_sha256,
        "profile_sha256": profile_sha256,
        "rom_sha256": rom_sha256,
        "context_origin": "training",
    }
    if not isinstance(metadata, Mapping) or any(
        metadata.get(key) != value for key, value in expected.items()
    ):
        raise RedFailureRecoveryError("failed trajectory parent or scope differs")
    states = list(episode.iter_stream("failure_state", max_records=16))
    if not states:
        raise RedFailureRecoveryError("failed trajectory lacks an exact terminal state")
    state = states[-1]
    if any(
        state.get(key) != value
        for key, value in {
            "schema": "pokemon.red.private-failure-state.v1",
            "state_sha256": state_sha256,
            "held_buttons": [],
            "safe_checkpoint": False,
            "admitted_continuation": False,
            "training_target": False,
        }.items()
    ):
        raise RedFailureRecoveryError("failed state is not an exact released diagnostic")
    encoded = state.get("state_base64")
    if not isinstance(encoded, str) or not 0 < len(encoded) <= 699052:
        raise RedFailureRecoveryError("failed state encoding differs")
    try:
        payload = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except ValueError as error:
        raise RedFailureRecoveryError("failed state encoding differs") from error
    if not payload or hashlib.sha256(payload).hexdigest() != state_sha256:
        raise RedFailureRecoveryError("failed state bytes differ")
    return state


@dataclass(frozen=True, slots=True)
class RedFailureRecoveryResult:
    """No made-up model step; support costs remain explicit and measurable."""

    failure_episode_id: str
    failure_manifest_sha256: str
    failure_state_sha256: str
    failed_actions: int
    failed_frames: int
    actions: int
    frames: int

    @property
    def steps(self) -> tuple[()]:
        return ()

    def public_dict(self) -> dict[str, object]:
        if any(
            type(value) is not int or value <= 0
            for value in (
                self.failed_actions,
                self.failed_frames,
                self.actions,
                self.frames,
            )
        ):
            raise RedFailureRecoveryError("recovery costs must include actual inputs")
        return {
            "schema": RECOVERY_TERMINAL_SCHEMA,
            "authority_id": "deterministic-failure-recovery",
            "status": "durable_terminal",
            "steps": [],
            "authority_decisions": 0,
            "decisions": 0,
            "training_examples": 0,
            "completion_satisfied": False,
            "independent_root": False,
            "recovery_attempts": 1,
            "total_actions": self.actions,
            "total_frames": self.frames,
            "original_choice_retried": False,
            "failure_origin": {
                "episode_id": self.failure_episode_id,
                "manifest_sha256": self.failure_manifest_sha256,
                "state_sha256": self.failure_state_sha256,
                "actions": self.failed_actions,
                "frames": self.failed_frames,
            },
        }


def require_recovery_checkpoint_origin(
    store: PrivateArtifactRoot,
    document: Mapping[str, object],
) -> None:
    """Verify every recovery checkpoint against the unmodified failed prefix."""
    terminal = document.get("terminal_result")
    recovery_checkpoint = document.get("schema") == RECOVERY_CHECKPOINT_SCHEMA
    recovery_terminal = (
        isinstance(terminal, Mapping) and terminal.get("schema") == RECOVERY_TERMINAL_SCHEMA
    )
    if recovery_checkpoint != recovery_terminal:
        raise RedFailureRecoveryError("recovery checkpoint and terminal types differ")
    if not recovery_checkpoint:
        return
    assert isinstance(terminal, Mapping)
    origin = terminal.get("failure_origin")
    if not isinstance(origin, Mapping):
        raise RedFailureRecoveryError("recovery origin missing")
    state = authenticated_failure_state(
        store,
        episode_id=cast(str, origin["episode_id"]),
        manifest_sha256=cast(str, origin["manifest_sha256"]),
        state_sha256=cast(str, origin["state_sha256"]),
        parent_state_sha256=cast(str, document["original_state_sha256"]),
        parent_envelope_sha256=cast(str, document["original_envelope_sha256"]),
        profile_sha256=cast(str, document["profile_sha256"]),
        rom_sha256=cast(str, document["rom_sha256"]),
    )
    expected = RedFailureRecoveryResult(
        cast(str, origin["episode_id"]),
        cast(str, origin["manifest_sha256"]),
        cast(str, origin["state_sha256"]),
        cast(int, state["actions"]),
        cast(int, state["frames"]),
        terminal["total_actions"],
        terminal["total_frames"],
    ).public_dict()
    if terminal != expected:
        raise RedFailureRecoveryError("recovery terminal changed support scope or costs")
    episode = store.open_episode(cast(str, document["episode_id"]))
    rows = list(episode.iter_stream("executions"))
    if (
        len(rows) != terminal["total_actions"]
        or sum(cast(int, row["frames"]) for row in rows) != (terminal["total_frames"])
    ):
        raise RedFailureRecoveryError("recovery controller costs disagree with trajectory")
    if "decisions" in episode.stream_names:
        raise RedFailureRecoveryError("forced recovery may not contain model decisions")
