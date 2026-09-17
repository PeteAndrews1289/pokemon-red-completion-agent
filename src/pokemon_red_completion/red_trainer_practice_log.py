"""Crash-retained, hash-chained decision log for bounded battle experiments.

The log is deliberately separate from the final episode receipt. A failed policy
or controller transition leaves every completed event on disk, including the
last decision boundary and (when available) the selected action.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from pokemon_red_completion.provenance import canonical_sha256


class TrainerPracticeEventLog:
    def __init__(self, directory: Path, *, run_identity: Mapping[str, object]) -> None:
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.directory = directory
        self.sequence = 0
        self.previous_sha256: str | None = None
        self.closed = False
        self.last_event: str | None = None
        self.emit({
            "event": "run_identity",
            "identity": dict(run_identity),
        })

    def emit(self, event: Mapping[str, object]) -> None:
        if self.closed:
            raise RuntimeError("trainer practice log is closed")
        self.sequence += 1
        record: dict[str, object] = {
            "schema": "pokemon.red.trainer-practice-event.v1",
            "sequence": self.sequence,
            "previous_sha256": self.previous_sha256,
            "payload": dict(event),
        }
        digest = canonical_sha256(record)
        record["record_sha256"] = digest
        _write_new(self.directory / f"event-{self.sequence:05d}.json", record)
        self.previous_sha256 = digest
        self.last_event = str(event.get("event"))

    def finish(self, outcome: Mapping[str, object]) -> None:
        self.emit({"event": "run_finished", "outcome": dict(outcome)})
        self.closed = True

    def fail(self, error: BaseException) -> None:
        last_event = self.last_event
        self.emit({
            "event": "run_failed",
            "error_type": type(error).__name__,
            "failure_after_event": last_event,
            "completed_events_before_failure": self.sequence,
        })
        self.closed = True


def verify_trainer_practice_event_log(directory: Path) -> dict[str, object]:
    """Check ordered file continuity and every hash link before consuming a log."""
    paths = sorted(directory.glob("event-*.json"))
    if not paths:
        raise ValueError("trainer practice event log is empty")
    previous: str | None = None
    final_event: str | None = None
    event_counts: dict[str, int] = {}
    for sequence, path in enumerate(paths, 1):
        if path.name != f"event-{sequence:05d}.json":
            raise ValueError("trainer practice event sequence has a gap")
        record = json.loads(path.read_bytes())
        if not isinstance(record, dict) or record.get("schema") != (
            "pokemon.red.trainer-practice-event.v1"
        ):
            raise ValueError("trainer practice event schema differs")
        digest = record.pop("record_sha256", None)
        if (
            record.get("sequence") != sequence
            or record.get("previous_sha256") != previous
            or digest != canonical_sha256(record)
        ):
            raise ValueError("trainer practice event chain differs")
        payload = record.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("event"), str):
            raise ValueError("trainer practice event payload differs")
        if final_event is not None:
            raise ValueError("trainer practice event follows a terminal")
        if payload["event"] in {"run_finished", "run_failed"}:
            final_event = payload["event"]
        event_name = payload["event"]
        event_counts[event_name] = event_counts.get(event_name, 0) + 1
        previous = digest
    return {
        "schema": "pokemon.red.trainer-practice-log-verification.v1",
        "event_count": len(paths),
        "last_record_sha256": previous,
        "terminal_event": final_event,
        "complete": final_event is not None,
        "event_counts": dict(sorted(event_counts.items())),
        "failed_runs": event_counts.get("run_failed", 0),
        "started_decisions": event_counts.get("decision_started", 0),
        "completed_decisions": event_counts.get("decision_completed", 0),
        "incomplete_decisions": (
            event_counts.get("decision_started", 0)
            - event_counts.get("decision_completed", 0)
        ),
    }


def _write_new(path: Path, document: Mapping[str, object]) -> None:
    payload = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
