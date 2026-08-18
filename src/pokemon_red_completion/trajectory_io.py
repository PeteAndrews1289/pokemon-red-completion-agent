"""Bridge typed trajectory records to one integrity-checked private episode."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.private_artifacts import EpisodeWriter
from pokemon_red_completion.trajectory import (
    DecisionRecord,
    ExecutionRecord,
    SemanticSnapshot,
    SparseEvent,
    TrajectorySinkClosedError,
    TrajectoryValidationError,
    canonical_json,
)


@dataclass(slots=True)
class EpisodeTrajectorySink:
    """Persist one internally consistent, content-addressed trajectory episode.

    The sink binds identity at construction so callers cannot accidentally mix
    records from different episodes or games.  Snapshots are written once to a
    content-addressed stream; decision and execution rows retain only their
    snapshot hashes.
    """

    writer: EpisodeWriter
    episode_id: str
    game_id: str
    durable_writes: bool = False
    _decision_count: int = field(default=0, init=False)
    _execution_count: int = field(default=0, init=False)
    _event_count: int = field(default=0, init=False)
    _snapshot_count: int = field(default=0, init=False)
    _header_written: bool = field(default=False, init=False)
    _terminal_written: bool = field(default=False, init=False)
    _finalized: bool = field(default=False, init=False)
    _record_ids: set[str] = field(default_factory=set, init=False)
    _decision_ids: set[str] = field(default_factory=set, init=False)
    _snapshot_hashes: set[str] = field(default_factory=set, init=False)
    _last_execution_index: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        _require_non_empty(self.episode_id, name="episode_id")
        _require_non_empty(self.game_id, name="game_id")
        if type(self.durable_writes) is not bool:  # noqa: E721
            raise TypeError("durable_writes must be a bool")

    def write_episode_header(self, *, metadata: Mapping[str, object]) -> None:
        """Write the sole episode header with caller-supplied provenance metadata."""

        self._require_open()
        if self._terminal_written:
            raise TrajectoryValidationError("cannot write a header after the terminal event")
        if self._header_written:
            raise TrajectoryValidationError("episode header has already been written")
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata must be a mapping")

        # Round-tripping through the trajectory validator freezes no caller-owned
        # objects into the durable record and rejects binary/path/sensitive values.
        safe_metadata = json.loads(canonical_json(metadata))
        self._append(
            "episode",
            {
                "record_type": "episode",
                "trajectory_schema": "pokemon.trajectory.v1",
                "episode_id": self.episode_id,
                "game_id": self.game_id,
                "metadata": safe_metadata,
            },
        )
        self._header_written = True

    def record_decision(self, record: DecisionRecord) -> None:
        self._require_recording()
        if not isinstance(record, DecisionRecord):
            raise TypeError("record must be a DecisionRecord")
        self._validate_episode(record.episode_id)
        self._validate_snapshot(record.snapshot)
        self._validate_unique_id(record.decision_id)

        self._write_snapshot(record.snapshot, record.snapshot_sha256)
        payload = record.to_dict()
        del payload["snapshot"]
        payload["record_type"] = "decision"
        self._append("decisions", payload)
        self._record_ids.add(record.decision_id)
        self._decision_ids.add(record.decision_id)
        self._decision_count += 1

    def record_execution(self, record: ExecutionRecord) -> None:
        self._require_recording()
        if not isinstance(record, ExecutionRecord):
            raise TypeError("record must be an ExecutionRecord")
        self._validate_episode(record.episode_id)
        self._validate_snapshot(record.before_snapshot)
        self._validate_snapshot(record.after_snapshot)
        self._validate_unique_id(record.execution_id)
        if record.decision_id is not None and record.decision_id not in self._decision_ids:
            raise TrajectoryValidationError(
                f"execution references unknown decision id: {record.decision_id}"
            )
        if (
            self._last_execution_index is not None
            and record.step_index <= self._last_execution_index
        ):
            raise TrajectoryValidationError(
                "execution step_index must be strictly greater than the previous execution"
            )

        self._write_snapshot(record.before_snapshot, record.before_sha256)
        self._write_snapshot(record.after_snapshot, record.after_sha256)
        payload = record.to_dict()
        del payload["before_snapshot"]
        del payload["after_snapshot"]
        payload["record_type"] = "execution"
        self._append("executions", payload)
        self._record_ids.add(record.execution_id)
        self._last_execution_index = record.step_index
        self._execution_count += 1

    def record_event(self, event: SparseEvent) -> None:
        self._require_recording()
        if not isinstance(event, SparseEvent):
            raise TypeError("event must be a SparseEvent")
        self._validate_episode(event.episode_id)
        self._validate_unique_id(event.event_id)

        payload = event.to_dict()
        payload["record_type"] = "event"
        self._append("events", payload)
        self._record_ids.add(event.event_id)
        self._event_count += 1
        if event.kind == "terminal":
            self._terminal_written = True

    def finalize(self) -> None:
        self._require_open()
        if not self._header_written:
            raise TrajectoryValidationError("episode header must be written before finalization")
        if not self._terminal_written:
            raise TrajectoryValidationError(
                "exactly one terminal event is required before finalization"
            )
        self._finalized = True

    @property
    def counts(self) -> dict[str, int]:
        return {
            "decisions": self._decision_count,
            "executions": self._execution_count,
            "events": self._event_count,
            "snapshots": self._snapshot_count,
        }

    def _write_snapshot(self, snapshot: SemanticSnapshot, digest: str) -> None:
        if digest in self._snapshot_hashes:
            return
        self._append(
            "snapshots",
            {
                "record_type": "snapshot",
                "snapshot_sha256": digest,
                "snapshot": snapshot.to_dict(),
            },
        )
        self._snapshot_hashes.add(digest)
        self._snapshot_count += 1

    def _append(self, stream: str, record: Mapping[str, object]) -> None:
        if self.durable_writes:
            self.writer.append(stream, record, durable=True)
        else:
            self.writer.append(stream, record)

    def _validate_episode(self, episode_id: str) -> None:
        if episode_id != self.episode_id:
            raise TrajectoryValidationError(
                f"record episode_id does not match sink episode: {episode_id}"
            )

    def _validate_snapshot(self, snapshot: SemanticSnapshot) -> None:
        if snapshot.game_id != self.game_id:
            raise TrajectoryValidationError(
                f"snapshot game_id does not match sink game: {snapshot.game_id}"
            )

    def _validate_unique_id(self, record_id: str) -> None:
        if record_id in self._record_ids:
            raise TrajectoryValidationError(f"duplicate trajectory record id: {record_id}")

    def _require_recording(self) -> None:
        self._require_open()
        if not self._header_written:
            raise TrajectoryValidationError(
                "episode header must be written before trajectory records"
            )
        if self._terminal_written:
            raise TrajectoryValidationError("cannot record after the terminal event")

    def _require_open(self) -> None:
        if self._finalized:
            raise TrajectorySinkClosedError("trajectory sink is finalized")


def _require_non_empty(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrajectoryValidationError(f"{name} must be a non-empty string")
    return value
