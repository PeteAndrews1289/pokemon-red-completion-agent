from __future__ import annotations

import hashlib
import runpy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(PROJECT_ROOT / "scripts" / "run_red_training_dashboard.py"))
_exception_message_sha256 = SCRIPT["_exception_message_sha256"]
_private_failure_record = SCRIPT["_private_failure_record"]


def test_private_failure_record_retains_exact_path_free_message_and_counters() -> None:
    error = RuntimeError("training action budget exhausted")
    snapshot = {"stage": "Saffron", "frame_count": 123, "battle_policy": {}}

    record = _private_failure_record(error=error, snapshot=snapshot)

    assert record["exception_type"] == "RuntimeError"
    assert record["exception_message"] == "training action budget exhausted"
    assert record["exception_message_retained_exactly"] is True
    assert record["exception_message_sha256"] == hashlib.sha256(
        b"training action budget exhausted"
    ).hexdigest()
    assert record["last_verified"] == snapshot


def test_private_failure_record_hashes_but_does_not_copy_path_bearing_message() -> None:
    error = RuntimeError("failed while opening /private/location/state.bin")

    record = _private_failure_record(error=error, snapshot={})

    assert record["exception_message"] is None
    assert record["exception_message_retained_exactly"] is False
    assert record["exception_message_sha256"] == _exception_message_sha256(error)
    assert "/private/" not in repr(record)


def test_private_failure_record_accepts_a_graceful_interrupt() -> None:
    error = KeyboardInterrupt("user requested stop")

    record = _private_failure_record(error=error, snapshot={})

    assert record["exception_type"] == "KeyboardInterrupt"
    assert record["exception_message"] == "user requested stop"
    assert record["exception_message_retained_exactly"] is True
