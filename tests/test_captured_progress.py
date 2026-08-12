from __future__ import annotations

from pathlib import Path

import pytest

from pokemon_red_completion.captured_progress import (
    CapturedProgressEnvelope,
    CapturedProgressError,
    load_captured_progress,
    write_captured_progress,
)


def test_progress_envelope_is_bound_to_exact_private_state(tmp_path: Path) -> None:
    state = tmp_path / "capture.state"
    envelope = tmp_path / "capture.state.json"
    state.write_bytes(b"private state bytes")
    written = write_captured_progress(
        envelope,
        state_path=state,
        checkpoint_id="celadon_stable",
        checkpoint_label="Healed safely in Celadon",
        checkpoints_completed=124,
        checkpoints_total=312,
        verified_objective_ids=("power_on", "begin_adventure"),
    )

    assert load_captured_progress(envelope, state_path=state) == written
    state.write_bytes(b"different state")
    with pytest.raises(CapturedProgressError, match="does not match"):
        load_captured_progress(envelope, state_path=state)


def test_capture_checkpoint_identity_is_portable_for_downstream_binding() -> None:
    with pytest.raises(CapturedProgressError, match="checkpoint identity is invalid"):
        CapturedProgressEnvelope(
            state_sha256="0" * 64,
            checkpoint_id="scenario:materialized",
            checkpoint_label="Invalid materialized checkpoint",
            checkpoints_completed=1,
            checkpoints_total=1,
            verified_objective_ids=("power_on",),
        )
