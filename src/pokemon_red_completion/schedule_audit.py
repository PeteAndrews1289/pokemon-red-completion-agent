"""Offline authentication of every recorded battle-start timing offset."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from pokemon_red_completion.collection_protocol import (
    BATTLE_START_SCHEDULE_SCHEMA,
    POKEMON_RED_GAME_ID,
    BattleStartOffset,
    battle_start_offsets_sha256,
)
from pokemon_red_completion.trajectory import (
    TRAJECTORY_SCHEMA_VERSION,
    canonical_sha256,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_EVENTS = 10_000
_MAX_EXECUTIONS = 1_000_000
_MAX_SNAPSHOTS = 1_000_000


class ScheduleAttestationError(RuntimeError):
    """Raised when durable schedule evidence does not match the frozen plan."""


class ScheduleEpisodeReader(Protocol):
    def read_header(self) -> Mapping[str, object]: ...

    def iter_stream(
        self,
        stream: str,
        *,
        max_records: int | None = None,
    ) -> Iterator[Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class ScheduleAttestation:
    """Aggregate path-free receipt for one authenticated schedule."""

    schedule_sha256: str
    expected_battles: int
    attested_battles: int
    positive_offsets: int
    zero_offsets: int

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-red-schedule-attestation-audit-v1",
            "schedule_sha256": self.schedule_sha256,
            "expected_battles": self.expected_battles,
            "attested_battles": self.attested_battles,
            "positive_offsets": self.positive_offsets,
            "zero_offsets": self.zero_offsets,
            "complete": self.attested_battles == self.expected_battles,
        }


def audit_schedule_attestations(
    reader: ScheduleEpisodeReader,
    *,
    episode_id: str,
    offsets: Sequence[BattleStartOffset],
    schedule_sha256: str,
) -> ScheduleAttestation:
    """Authenticate the header, per-offset events, linked WAITs, and terminal."""

    frozen_offsets = tuple(offsets)
    if not isinstance(episode_id, str) or not episode_id:
        raise ScheduleAttestationError("schedule episode identity is invalid")
    if not frozen_offsets or not all(
        isinstance(offset, BattleStartOffset) for offset in frozen_offsets
    ):
        raise ScheduleAttestationError("schedule offsets are invalid")
    if (
        not isinstance(schedule_sha256, str)
        or _SHA256.fullmatch(schedule_sha256) is None
        or battle_start_offsets_sha256(frozen_offsets) != schedule_sha256
    ):
        raise ScheduleAttestationError("schedule digest does not match its offsets")

    _audit_header(
        reader.read_header(),
        episode_id=episode_id,
        offsets=frozen_offsets,
        schedule_sha256=schedule_sha256,
    )
    schedule_events: list[Mapping[str, object]] = []
    terminals: list[Mapping[str, object]] = []
    for event in reader.iter_stream("events", max_records=_MAX_EVENTS):
        if event.get("kind") == "battle_start_offset_applied":
            schedule_events.append(event)
        elif event.get("kind") == "terminal":
            terminals.append(event)
    if len(schedule_events) != len(frozen_offsets):
        raise ScheduleAttestationError("schedule event count is incomplete")
    if len(terminals) != 1:
        raise ScheduleAttestationError("schedule terminal evidence is invalid")

    execution_indices = _expected_execution_indices(
        schedule_events,
        offsets=frozen_offsets,
        episode_id=episode_id,
        schedule_sha256=schedule_sha256,
    )
    snapshot_hashes = _audit_snapshots(reader)
    executions: dict[int, Mapping[str, object]] = {}
    seen_execution_steps: set[int] = set()
    for execution in reader.iter_stream("executions", max_records=_MAX_EXECUTIONS):
        step_index = execution.get("step_index")
        if isinstance(step_index, bool) or not isinstance(step_index, int) or step_index < 0:
            raise ScheduleAttestationError("execution step index is invalid")
        if step_index in seen_execution_steps:
            raise ScheduleAttestationError("execution step index is duplicated")
        seen_execution_steps.add(step_index)
        if step_index in execution_indices:
            executions[step_index] = execution
    if set(executions) != execution_indices:
        raise ScheduleAttestationError("scheduled WAIT execution is absent")

    for offset, event in zip(frozen_offsets, schedule_events, strict=True):
        _audit_offset_execution(
            offset=offset,
            event=event,
            execution=(
                executions[_integer_payload(event, "execution_step_index")]
                if offset.frames > 0
                else None
            ),
            snapshot_hashes=snapshot_hashes,
        )
    _audit_terminal(
        terminals[0],
        episode_id=episode_id,
        schedule_sha256=schedule_sha256,
        battle_count=len(frozen_offsets),
    )
    positive = sum(offset.frames > 0 for offset in frozen_offsets)
    return ScheduleAttestation(
        schedule_sha256=schedule_sha256,
        expected_battles=len(frozen_offsets),
        attested_battles=len(schedule_events),
        positive_offsets=positive,
        zero_offsets=len(frozen_offsets) - positive,
    )


def _audit_header(
    value: Mapping[str, object],
    *,
    episode_id: str,
    offsets: tuple[BattleStartOffset, ...],
    schedule_sha256: str,
) -> None:
    if (
        set(value)
        != {
            "episode_id",
            "game_id",
            "metadata",
            "record_type",
            "trajectory_schema",
        }
        or value.get("record_type") != "episode"
        or value.get("trajectory_schema") != "pokemon.trajectory.v1"
        or value.get("episode_id") != episode_id
        or value.get("game_id") != POKEMON_RED_GAME_ID
    ):
        raise ScheduleAttestationError("schedule episode header is invalid")
    metadata = _mapping(value.get("metadata"), subject="schedule episode metadata")
    configuration = _mapping(
        metadata.get("configuration"),
        subject="schedule configuration",
    )
    schedule = _mapping(
        configuration.get("battle_start_schedule"),
        subject="schedule configuration",
    )
    if (
        schedule.get("schema") != BATTLE_START_SCHEDULE_SCHEMA
        or schedule.get("schedule_sha256") != schedule_sha256
        or schedule.get("offsets") != [offset.public_dict() for offset in offsets]
    ):
        raise ScheduleAttestationError("episode header schedule does not match the plan")


def _expected_execution_indices(
    events: Sequence[Mapping[str, object]],
    *,
    offsets: tuple[BattleStartOffset, ...],
    episode_id: str,
    schedule_sha256: str,
) -> set[int]:
    result: set[int] = set()
    for ordinal, (event, offset) in enumerate(
        zip(events, offsets, strict=True),
        start=1,
    ):
        if (
            set(event)
            != {
                "episode_id",
                "event_id",
                "kind",
                "payload",
                "record_type",
                "schema_version",
                "step_index",
            }
            or event.get("record_type") != "event"
            or event.get("schema_version") != TRAJECTORY_SCHEMA_VERSION
            or event.get("episode_id") != episode_id
            or event.get("event_id") != f"{episode_id}:schedule:{ordinal}"
        ):
            raise ScheduleAttestationError("schedule event identity is invalid")
        step_index = event.get("step_index")
        if isinstance(step_index, bool) or not isinstance(step_index, int) or step_index < 0:
            raise ScheduleAttestationError("schedule event step is invalid")
        payload = _mapping(event.get("payload"), subject="schedule event payload")
        if set(payload) != {
            "after_snapshot_sha256",
            "battle_ordinal",
            "battle_plan_id",
            "before_snapshot_sha256",
            "execution_step_index",
            "frames",
            "schedule_sha256",
        }:
            raise ScheduleAttestationError("schedule event payload keys are invalid")
        if (
            payload.get("battle_ordinal") != ordinal
            or payload.get("battle_plan_id") != offset.battle_plan_id
            or payload.get("frames") != offset.frames
            or payload.get("schedule_sha256") != schedule_sha256
        ):
            raise ScheduleAttestationError("schedule event does not match its offset")
        before = payload.get("before_snapshot_sha256")
        after = payload.get("after_snapshot_sha256")
        if (
            not isinstance(before, str)
            or _SHA256.fullmatch(before) is None
            or not isinstance(after, str)
            or _SHA256.fullmatch(after) is None
            or before != after
        ):
            raise ScheduleAttestationError("schedule snapshot evidence is invalid")
        execution_step = payload.get("execution_step_index")
        if offset.frames == 0:
            if execution_step is not None:
                raise ScheduleAttestationError("zero offset created ambiguous evidence")
        else:
            if (
                isinstance(execution_step, bool)
                or not isinstance(execution_step, int)
                or execution_step < 0
                or step_index != execution_step + 1
                or execution_step in result
            ):
                raise ScheduleAttestationError("schedule WAIT linkage is invalid")
            result.add(execution_step)
    return result


def _audit_offset_execution(
    *,
    offset: BattleStartOffset,
    event: Mapping[str, object],
    execution: Mapping[str, object] | None,
    snapshot_hashes: frozenset[str],
) -> None:
    payload = _mapping(event.get("payload"), subject="schedule event payload")
    if offset.frames == 0:
        if execution is not None:
            raise ScheduleAttestationError("zero offset has an unexpected execution")
        return
    if execution is None:
        raise ScheduleAttestationError("positive offset has no WAIT execution")
    action = _mapping(execution.get("action"), subject="scheduled WAIT action")
    if (
        set(execution)
        != {
            "action",
            "after_sha256",
            "before_sha256",
            "buttons",
            "decision_id",
            "episode_id",
            "error_type",
            "execution_id",
            "frames",
            "record_type",
            "schema_version",
            "status",
            "step_index",
        }
        or execution.get("record_type") != "execution"
        or execution.get("schema_version") != TRAJECTORY_SCHEMA_VERSION
        or execution.get("episode_id") != event.get("episode_id")
        or execution.get("execution_id")
        != f"{event.get('episode_id')}:execution:{execution.get('step_index')}"
        or execution.get("status") != "success"
        or execution.get("error_type") is not None
        or execution.get("decision_id") is not None
        or execution.get("buttons") != []
        or execution.get("frames") != offset.frames
        or action
        != {
            "kind": "wait",
            "repeat": offset.frames,
            "value": None,
        }
        or execution.get("before_sha256") != payload["before_snapshot_sha256"]
        or execution.get("after_sha256") != payload["after_snapshot_sha256"]
        or execution.get("before_sha256") not in snapshot_hashes
        or execution.get("after_sha256") not in snapshot_hashes
    ):
        raise ScheduleAttestationError("scheduled WAIT execution does not match its event")


def _audit_terminal(
    terminal: Mapping[str, object],
    *,
    episode_id: str,
    schedule_sha256: str,
    battle_count: int,
) -> None:
    payload = _mapping(terminal.get("payload"), subject="terminal payload")
    schedule = _mapping(
        payload.get("battle_start_schedule"),
        subject="terminal schedule",
    )
    if (
        set(terminal)
        != {
            "episode_id",
            "event_id",
            "kind",
            "payload",
            "record_type",
            "schema_version",
            "step_index",
        }
        or terminal.get("record_type") != "event"
        or terminal.get("schema_version") != TRAJECTORY_SCHEMA_VERSION
        or terminal.get("episode_id") != episode_id
        or payload.get("status") != "complete"
        or payload.get("game_complete") is not True
        or payload.get("qualified_through") != "enter_hall_of_fame"
        or schedule
        != {
            "complete": True,
            "expected_battles": battle_count,
            "finished_battles": battle_count,
            "schedule_sha256": schedule_sha256,
        }
    ):
        raise ScheduleAttestationError("terminal schedule evidence is invalid")


def _audit_snapshots(reader: ScheduleEpisodeReader) -> frozenset[str]:
    result: set[str] = set()
    for snapshot in reader.iter_stream("snapshots", max_records=_MAX_SNAPSHOTS):
        if set(snapshot) != {"record_type", "snapshot", "snapshot_sha256"}:
            raise ScheduleAttestationError("schedule snapshot record is invalid")
        digest = snapshot.get("snapshot_sha256")
        document = snapshot.get("snapshot")
        if (
            snapshot.get("record_type") != "snapshot"
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
            or not isinstance(document, Mapping)
            or canonical_sha256(document) != digest
            or digest in result
        ):
            raise ScheduleAttestationError("schedule snapshot record is invalid")
        result.add(digest)
    if not result:
        raise ScheduleAttestationError("schedule snapshot evidence is absent")
    return frozenset(result)


def _integer_payload(event: Mapping[str, object], key: str) -> int:
    payload = _mapping(event.get("payload"), subject="schedule event payload")
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScheduleAttestationError("schedule execution index is invalid")
    return value


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ScheduleAttestationError(f"{subject} must be an object")
    return value
