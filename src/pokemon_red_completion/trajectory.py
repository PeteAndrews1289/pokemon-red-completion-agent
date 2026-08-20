"""Game-neutral, privacy-safe trajectory records.

This module defines the durable boundary between game adapters and future
training pipelines.  Records contain semantic observations and semantic
actions only: no ROM bytes, save states, screenshots, raw memory, or private
filesystem paths.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from pathlib import PurePath
from types import MappingProxyType
from typing import Generic, Protocol, TypeAlias, TypeVar, cast

from pokemon_red_completion.runtime_identity import (
    is_canonical_distribution_inventory_name,
    is_runtime_identity_public_document,
)

TRAJECTORY_SCHEMA_VERSION = 1

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | tuple["JSONValue", ...] | Mapping[str, "JSONValue"]
_PathToken: TypeAlias = str | int

# Fingerprints are compared after punctuation is removed and case is folded.
# Hashes such as ``rom_sha256`` are deliberately not reserved: a public digest
# identifies a qualified build without revealing copyrighted content.
RESERVED_SENSITIVE_KEYS = frozenset(
    {
        "accesstoken",
        "apikey",
        "authorization",
        "checkpointpath",
        "cookie",
        "credential",
        "credentials",
        "filesystempath",
        "homedirectory",
        "homepath",
        "memoryaddress",
        "memorydump",
        "password",
        "privatekey",
        "rawmemory",
        "rom",
        "rombytes",
        "romdata",
        "rompath",
        "savedata",
        "savepath",
        "savestate",
        "savestatepath",
        "screenshot",
        "screenshotpath",
        "secret",
        "token",
        "videopath",
    }
)

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ERROR_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_WINDOWS_DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/]")


class TrajectoryValidationError(ValueError):
    """Raised when a trajectory value is unsafe or violates its schema."""


class TrajectorySinkClosedError(RuntimeError):
    """Raised when a finalized trajectory sink receives another record."""


class CanonicalJSONRecord(Protocol):
    """A record that can expose one validated JSON document."""

    def to_dict(self) -> dict[str, object]: ...


class SnapshotProvider(Protocol):
    """Provide the current game-neutral semantic observation."""

    def snapshot(self) -> SemanticSnapshot: ...


ActionT = TypeVar("ActionT")
ResultT = TypeVar("ResultT")


class ActionExecutor(Protocol[ActionT, ResultT]):
    """Delegate interface decorated by :class:`RecordingExecutor`."""

    def execute(self, action: ActionT) -> ResultT: ...


class TrajectorySink(Protocol):
    """Storage boundary shared by in-memory and durable trajectory writers."""

    def record_decision(self, record: DecisionRecord) -> None: ...

    def record_execution(self, record: ExecutionRecord) -> None: ...

    def record_event(self, event: SparseEvent) -> None: ...

    def finalize(self) -> None: ...


def _key_fingerprint(key: str) -> str:
    return "".join(character for character in key.casefold() if character.isalnum())


def _is_reserved_sensitive_key(key: str) -> bool:
    fingerprint = _key_fingerprint(key)
    return fingerprint in RESERVED_SENSITIVE_KEYS or fingerprint.endswith(
        ("password", "secret", "token")
    )


def _is_runtime_inventory_name_field(path_tokens: tuple[_PathToken, ...]) -> bool:
    return (
        len(path_tokens) == 5
        and path_tokens[:3] == ("runtime", "pyboy", "files")
        and type(path_tokens[3]) is int  # noqa: E721
        and path_tokens[4] == "name"
    )


def _freeze_json(
    value: object,
    *,
    path: str,
    path_tokens: tuple[_PathToken, ...] = (),
    allow_runtime_inventory_names: bool = False,
    active_containers: set[int] | None = None,
) -> JSONValue:
    """Validate and recursively freeze one JSON-safe value."""

    if isinstance(value, PurePath):
        raise TrajectoryValidationError(f"{path} contains a filesystem Path")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise TrajectoryValidationError(f"{path} contains binary data")
    if isinstance(value, StrEnum):
        value = str(value)
    if type(value) is str:  # noqa: E721
        path_like = (
            "/" in value
            or "\\" in value
            or value.startswith("~")
            or value.casefold().startswith("file:")
            or _WINDOWS_DRIVE_PATH.search(value)
        )
        if path_like and not (
            allow_runtime_inventory_names
            and _is_runtime_inventory_name_field(path_tokens)
            and is_canonical_distribution_inventory_name(value)
        ):
            raise TrajectoryValidationError(f"{path} contains path-like text")
        return value

    if value is None or type(value) in {bool, int}:  # noqa: E721
        return cast(JSONScalar, value)
    if type(value) is float:  # noqa: E721
        if not math.isfinite(value):
            raise TrajectoryValidationError(f"{path} contains a non-finite float")
        return value

    if active_containers is None:
        active_containers = set()

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active_containers:
            raise TrajectoryValidationError(f"{path} contains a recursive mapping")
        active_containers.add(identity)
        try:
            frozen: dict[str, JSONValue] = {}
            for key, item in value.items():
                if type(key) is not str:  # noqa: E721
                    raise TrajectoryValidationError(f"{path} contains a non-string mapping key")
                if _is_reserved_sensitive_key(key):
                    raise TrajectoryValidationError(f"{path}.{key} uses a reserved sensitive key")
                frozen[key] = _freeze_json(
                    item,
                    path=f"{path}.{key}",
                    path_tokens=(*path_tokens, key),
                    allow_runtime_inventory_names=allow_runtime_inventory_names,
                    active_containers=active_containers,
                )
            return MappingProxyType(frozen)
        finally:
            active_containers.remove(identity)

    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active_containers:
            raise TrajectoryValidationError(f"{path} contains a recursive sequence")
        active_containers.add(identity)
        try:
            return tuple(
                _freeze_json(
                    item,
                    path=f"{path}[{index}]",
                    path_tokens=(*path_tokens, index),
                    allow_runtime_inventory_names=allow_runtime_inventory_names,
                    active_containers=active_containers,
                )
                for index, item in enumerate(value)
            )
        finally:
            active_containers.remove(identity)

    raise TrajectoryValidationError(
        f"{path} contains unsupported JSON value type {type(value).__name__}"
    )


def _freeze_mapping(value: object, *, path: str) -> Mapping[str, JSONValue]:
    if not isinstance(value, Mapping):
        raise TrajectoryValidationError(f"{path} must be a mapping")
    frozen = _freeze_json(value, path=path, path_tokens=(path,))
    if not isinstance(frozen, Mapping):  # pragma: no cover - guarded above
        raise AssertionError("mapping validation returned a non-mapping")
    return frozen


def _thaw_json(value: JSONValue) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _require_non_empty(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrajectoryValidationError(f"{name} must be a non-empty string")
    return value


def _require_optional_label(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    return _require_non_empty(value, name=name)


def _require_index(value: object, *, name: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise TrajectoryValidationError(f"{name} must be a non-negative integer")
    return value


def _require_schema_version(value: object) -> int:
    if type(value) is not int or value != TRAJECTORY_SCHEMA_VERSION:  # noqa: E721
        raise TrajectoryValidationError(f"schema_version must equal {TRAJECTORY_SCHEMA_VERSION}")
    return value


def _require_sha256(value: object, *, name: str) -> str:
    if not isinstance(value, str) or _HEX_SHA256.fullmatch(value) is None:
        raise TrajectoryValidationError(f"{name} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class SemanticSnapshot:
    """A compact semantic observation suitable for more than one game."""

    game_id: str
    mode: str
    location: str | None = None
    facts: tuple[str, ...] = ()
    features: Mapping[str, JSONValue] = field(default_factory=dict)
    schema_version: int = TRAJECTORY_SCHEMA_VERSION
    _content_sha256: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_non_empty(self.game_id, name="game_id")
        _require_non_empty(self.mode, name="mode")
        _require_optional_label(self.location, name="location")
        if not isinstance(self.facts, Sequence) or isinstance(self.facts, (str, bytes, bytearray)):
            raise TrajectoryValidationError("facts must be a sequence of strings")
        normalized_facts: set[str] = set()
        for fact in self.facts:
            normalized_facts.add(_require_non_empty(fact, name="fact"))
        object.__setattr__(self, "facts", tuple(sorted(normalized_facts)))
        object.__setattr__(
            self,
            "features",
            _freeze_mapping(self.features, path="features"),
        )
        object.__setattr__(self, "_content_sha256", canonical_sha256(self))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "game_id": self.game_id,
            "mode": self.mode,
            "location": self.location,
            "facts": list(self.facts),
            "features": _thaw_json(self.features),
        }

    @property
    def sha256(self) -> str:
        return self._content_sha256


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """Game-neutral provenance for why an actor made one decision."""

    objective_id: str | None = None
    policy_id: str | None = None
    actor: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict)
    schema_version: int = TRAJECTORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_optional_label(self.objective_id, name="objective_id")
        _require_optional_label(self.policy_id, name="policy_id")
        _require_optional_label(self.actor, name="actor")
        object.__setattr__(
            self,
            "metadata",
            _freeze_mapping(self.metadata, path="metadata"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "objective_id": self.objective_id,
            "policy_id": self.policy_id,
            "actor": self.actor,
            "metadata": _thaw_json(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """One actor decision linked to the exact semantic state it observed."""

    decision_id: str
    episode_id: str
    step_index: int
    snapshot: SemanticSnapshot
    context: DecisionContext
    decision_type: str
    action: Mapping[str, JSONValue] | None = None
    schema_version: int = TRAJECTORY_SCHEMA_VERSION
    snapshot_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_non_empty(self.decision_id, name="decision_id")
        _require_non_empty(self.episode_id, name="episode_id")
        _require_index(self.step_index, name="step_index")
        if not isinstance(self.snapshot, SemanticSnapshot):
            raise TypeError("snapshot must be a SemanticSnapshot")
        if not isinstance(self.context, DecisionContext):
            raise TypeError("context must be a DecisionContext")
        _require_non_empty(self.decision_type, name="decision_type")
        if self.action is not None:
            object.__setattr__(
                self,
                "action",
                _freeze_mapping(self.action, path="action"),
            )
        object.__setattr__(self, "snapshot_sha256", self.snapshot.sha256)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "episode_id": self.episode_id,
            "step_index": self.step_index,
            "snapshot": self.snapshot.to_dict(),
            "snapshot_sha256": self.snapshot_sha256,
            "context": self.context.to_dict(),
            "decision_type": self.decision_type,
            "action": None if self.action is None else _thaw_json(self.action),
        }


class ExecutionStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """One executed semantic action linked to before/after observations."""

    execution_id: str
    episode_id: str
    step_index: int
    action: Mapping[str, JSONValue]
    before_snapshot: SemanticSnapshot
    after_snapshot: SemanticSnapshot
    buttons: tuple[str, ...] = ()
    frames: int = 0
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    error_type: str | None = None
    decision_id: str | None = None
    schema_version: int = TRAJECTORY_SCHEMA_VERSION
    before_sha256: str = field(init=False)
    after_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_non_empty(self.execution_id, name="execution_id")
        _require_non_empty(self.episode_id, name="episode_id")
        _require_index(self.step_index, name="step_index")
        _require_optional_label(self.decision_id, name="decision_id")
        object.__setattr__(self, "action", _freeze_mapping(self.action, path="action"))
        if not isinstance(self.before_snapshot, SemanticSnapshot):
            raise TypeError("before_snapshot must be a SemanticSnapshot")
        if not isinstance(self.after_snapshot, SemanticSnapshot):
            raise TypeError("after_snapshot must be a SemanticSnapshot")
        if not isinstance(self.buttons, Sequence) or isinstance(
            self.buttons, (str, bytes, bytearray)
        ):
            raise TrajectoryValidationError("buttons must be a sequence of strings")
        normalized_buttons = tuple(
            _require_non_empty(button, name="button") for button in self.buttons
        )
        object.__setattr__(self, "buttons", normalized_buttons)
        _require_index(self.frames, name="frames")
        if not isinstance(self.status, ExecutionStatus):
            raise TypeError("status must be an ExecutionStatus")
        if self.status is ExecutionStatus.SUCCESS and self.error_type is not None:
            raise TrajectoryValidationError("successful execution cannot contain error_type")
        if self.status is ExecutionStatus.ERROR:
            _require_non_empty(self.error_type, name="error_type")
            if _SAFE_ERROR_TYPE.fullmatch(cast(str, self.error_type)) is None:
                raise TrajectoryValidationError("error_type must be a sanitized class name")
        object.__setattr__(self, "before_sha256", self.before_snapshot.sha256)
        object.__setattr__(self, "after_sha256", self.after_snapshot.sha256)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "execution_id": self.execution_id,
            "episode_id": self.episode_id,
            "step_index": self.step_index,
            "decision_id": self.decision_id,
            "before_snapshot": self.before_snapshot.to_dict(),
            "before_sha256": self.before_sha256,
            "action": _thaw_json(self.action),
            "after_snapshot": self.after_snapshot.to_dict(),
            "after_sha256": self.after_sha256,
            "buttons": list(self.buttons),
            "frames": self.frames,
            "status": self.status.value,
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class SparseEvent:
    """A noteworthy sparse label, such as an objective or battle outcome."""

    event_id: str
    episode_id: str
    step_index: int
    kind: str
    payload: Mapping[str, JSONValue] = field(default_factory=dict)
    schema_version: int = TRAJECTORY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        _require_non_empty(self.event_id, name="event_id")
        _require_non_empty(self.episode_id, name="episode_id")
        _require_index(self.step_index, name="step_index")
        _require_non_empty(self.kind, name="kind")
        object.__setattr__(
            self,
            "payload",
            _freeze_mapping(self.payload, path="payload"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "episode_id": self.episode_id,
            "step_index": self.step_index,
            "kind": self.kind,
            "payload": _thaw_json(self.payload),
        }


def _canonical_document(value: object) -> object:
    if isinstance(
        value,
        (
            SemanticSnapshot,
            DecisionContext,
            DecisionRecord,
            ExecutionRecord,
            SparseEvent,
        ),
    ):
        value = value.to_dict()
    allow_runtime_inventory_names = (
        isinstance(value, Mapping)
        and is_runtime_identity_public_document(value.get("runtime"))
    )
    return _thaw_json(
        _freeze_json(
            value,
            path="$",
            allow_runtime_inventory_names=allow_runtime_inventory_names,
        )
    )


def canonical_json(value: object) -> str:
    """Return deterministic ASCII JSON after applying all safety checks."""

    return json.dumps(
        _canonical_document(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_sha256(value: object) -> str:
    """Return the SHA-256 digest of :func:`canonical_json`."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class InMemoryTrajectorySink:
    """Small deterministic sink for tests and bounded trajectory collection."""

    _decisions: list[DecisionRecord] = field(default_factory=list, init=False)
    _executions: list[ExecutionRecord] = field(default_factory=list, init=False)
    _events: list[SparseEvent] = field(default_factory=list, init=False)
    _record_ids: set[tuple[str, str]] = field(default_factory=set, init=False)
    _finalized: bool = field(default=False, init=False)

    @property
    def decisions(self) -> tuple[DecisionRecord, ...]:
        return tuple(self._decisions)

    @property
    def executions(self) -> tuple[ExecutionRecord, ...]:
        return tuple(self._executions)

    @property
    def events(self) -> tuple[SparseEvent, ...]:
        return tuple(self._events)

    @property
    def finalized(self) -> bool:
        return self._finalized

    def _accept_id(self, category: str, record_id: str) -> None:
        if self._finalized:
            raise TrajectorySinkClosedError("trajectory sink is finalized")
        identity = (category, record_id)
        if identity in self._record_ids:
            raise TrajectoryValidationError(f"duplicate {category} record id: {record_id}")
        self._record_ids.add(identity)

    def record_decision(self, record: DecisionRecord) -> None:
        if not isinstance(record, DecisionRecord):
            raise TypeError("record must be a DecisionRecord")
        self._accept_id("decision", record.decision_id)
        self._decisions.append(record)

    def record_execution(self, record: ExecutionRecord) -> None:
        if not isinstance(record, ExecutionRecord):
            raise TypeError("record must be an ExecutionRecord")
        self._accept_id("execution", record.execution_id)
        self._executions.append(record)

    def record_event(self, event: SparseEvent) -> None:
        if not isinstance(event, SparseEvent):
            raise TypeError("event must be a SparseEvent")
        self._accept_id("event", event.event_id)
        self._events.append(event)

    def finalize(self) -> None:
        self._finalized = True


ActionEncoder: TypeAlias = Callable[[ActionT], Mapping[str, object]]
DecisionFactory: TypeAlias = Callable[[], DecisionRecord]


def _default_action_encoder(action: object) -> Mapping[str, object]:
    if isinstance(action, Mapping):
        return cast(Mapping[str, object], action)
    if is_dataclass(action) and not isinstance(action, type):
        return {item.name: getattr(action, item.name) for item in fields(action) if item.init}
    to_dict = getattr(action, "to_dict", None)
    if callable(to_dict):
        encoded = to_dict()
        if isinstance(encoded, Mapping):
            return cast(Mapping[str, object], encoded)
    raise TrajectoryValidationError("action must be a mapping, dataclass, or expose to_dict()")


def _sanitized_error_type(error: Exception) -> str:
    name = type(error).__name__
    return name if _SAFE_ERROR_TYPE.fullmatch(name) is not None else "Exception"


@dataclass(slots=True)
class RecordingExecutor(Generic[ActionT, ResultT]):
    """Transparently decorate an executor with linked semantic trajectory records.

    The provider's ``snapshot()`` method is called immediately before and after
    each delegated execution.  The delegate's return object is returned by
    identity, and its exceptions are re-raised unchanged.  Recording failures
    are fail-open so instrumentation cannot alter controller behavior.
    """

    delegate: ActionExecutor[ActionT, ResultT]
    snapshot_provider: SnapshotProvider
    sink: TrajectorySink
    episode_id: str
    action_encoder: ActionEncoder[ActionT] = _default_action_encoder
    start_step_index: int = 0
    _next_step_index: int = field(init=False)
    _recording_failures: int = field(default=0, init=False)
    _recording_failure_reasons: dict[str, int] = field(default_factory=dict, init=False)
    _active_decision_id: str | None = field(default=None, init=False)
    _active_decision_step_index: int | None = field(default=None, init=False)
    _active_decision_snapshot_sha256: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        _require_non_empty(self.episode_id, name="episode_id")
        _require_index(self.start_step_index, name="start_step_index")
        if not callable(self.action_encoder):
            raise TypeError("action_encoder must be callable")
        object.__setattr__(self, "_next_step_index", self.start_step_index)

    @property
    def next_step_index(self) -> int:
        return self._next_step_index

    @property
    def recording_failures(self) -> int:
        """Return instrumentation failures without changing controller behavior."""

        return self._recording_failures

    @property
    def recording_failure_reasons(self) -> Mapping[str, int]:
        """Return fixed, privacy-safe instrumentation failure categories."""

        return dict(self._recording_failure_reasons)

    def _note_failure(self, reason: str) -> None:
        self._recording_failures += 1
        self._recording_failure_reasons[reason] = (
            self._recording_failure_reasons.get(reason, 0) + 1
        )

    def note_instrumentation_failure(self) -> None:
        """Make the episode ineligible for promotion without raising into the actor."""

        self._note_failure("observer_callback")

    def record_standalone_decision(
        self,
        decision: DecisionRecord | DecisionFactory,
    ) -> bool:
        """Record a semantic decision that does not own an execution span.

        Objective selection is an instantaneous planner decision.  Its step index
        divides the surrounding execution stream into objective-sized segments,
        but it must not remain active while nested battle decisions are recorded.
        As with the executor's other instrumentation, recording is fail-open and
        a failure makes the episode ineligible for promotion.
        """

        try:
            record = decision() if callable(decision) else decision
            if not isinstance(record, DecisionRecord):
                raise TypeError("decision must produce a DecisionRecord")
            if record.episode_id != self.episode_id:
                raise TrajectoryValidationError(
                    "decision episode_id must match the recording executor"
                )
            if record.step_index != self._next_step_index:
                raise TrajectoryValidationError(
                    "decision step_index must match the next execution step"
                )
            self.sink.record_decision(record)
        except Exception:
            self._note_failure("decision_record")
            return False
        return True

    @contextmanager
    def decision_scope(
        self,
        decision: DecisionRecord | DecisionFactory,
    ) -> Iterator[None]:
        """Record and link one high-level decision to all executions in its span.

        A callable may be supplied when constructing the decision requires a
        live observation. Decision construction, validation, or sink failures
        remain observational: the controller body still runs, while
        ``recording_failures`` prevents the episode from being promoted.
        """

        if self._active_decision_id is not None:
            self._note_failure("nested_decision_scope")
            yield
            return

        try:
            record = decision() if callable(decision) else decision
            if not isinstance(record, DecisionRecord):
                raise TypeError("decision must produce a DecisionRecord")
            if record.episode_id != self.episode_id:
                raise TrajectoryValidationError(
                    "decision episode_id must match the recording executor"
                )
            if record.step_index != self._next_step_index:
                raise TrajectoryValidationError(
                    "decision step_index must match the next execution step"
                )
            self.sink.record_decision(record)
        except Exception:
            self._note_failure("decision_record")
            yield
            return

        self._active_decision_id = record.decision_id
        self._active_decision_step_index = record.step_index
        self._active_decision_snapshot_sha256 = record.snapshot_sha256
        try:
            yield
        finally:
            if self._next_step_index == record.step_index:
                self._note_failure("decision_without_execution")
            self._active_decision_id = None
            self._active_decision_step_index = None
            self._active_decision_snapshot_sha256 = None

    def execute(self, action: ActionT, *, decision_id: str | None = None) -> ResultT:
        step_index = self._next_step_index
        before: SemanticSnapshot | None = None
        encoded_action: Mapping[str, JSONValue] | None = None
        effective_decision_id: str | None = None
        try:
            _require_optional_label(decision_id, name="decision_id")
            if (
                decision_id is not None
                and self._active_decision_id is not None
                and decision_id != self._active_decision_id
            ):
                raise TrajectoryValidationError(
                    "explicit decision_id conflicts with the active decision scope"
                )
            effective_decision_id = decision_id or self._active_decision_id
            encoded_action = _freeze_mapping(
                self.action_encoder(action),
                path="action",
            )
            candidate = self.snapshot_provider.snapshot()
            if not isinstance(candidate, SemanticSnapshot):
                raise TypeError("snapshot provider must return SemanticSnapshot")
            before = candidate
            if (
                step_index == self._active_decision_step_index
                and before.sha256 != self._active_decision_snapshot_sha256
            ):
                raise TrajectoryValidationError(
                    "decision snapshot must match its first execution observation"
                )
        except Exception:
            # Recording is observational; it must never prevent controller work.
            self._note_failure("execution_before")
            before = None
            encoded_action = None

        try:
            result = self.delegate.execute(action)
        except Exception as error:
            if before is not None and encoded_action is not None:
                self._record_error(
                    step_index=step_index,
                    decision_id=effective_decision_id,
                    action=encoded_action,
                    before=before,
                    error=error,
                )
            raise
        else:
            if before is not None and encoded_action is not None:
                self._record_success(
                    step_index=step_index,
                    decision_id=effective_decision_id,
                    action=encoded_action,
                    before=before,
                    result=result,
                )
            return result
        finally:
            self._next_step_index += 1

    def _record_success(
        self,
        *,
        step_index: int,
        decision_id: str | None,
        action: Mapping[str, JSONValue],
        before: SemanticSnapshot,
        result: ResultT,
    ) -> None:
        try:
            after = self.snapshot_provider.snapshot()
            if not isinstance(after, SemanticSnapshot):
                raise TypeError("snapshot provider must return SemanticSnapshot")
            buttons = tuple(getattr(result, "buttons", ()))
            frames = getattr(result, "frames", 0)
            record = ExecutionRecord(
                execution_id=f"{self.episode_id}:execution:{step_index}",
                episode_id=self.episode_id,
                step_index=step_index,
                decision_id=decision_id,
                action=action,
                before_snapshot=before,
                after_snapshot=after,
                buttons=buttons,
                frames=frames,
            )
            self.sink.record_execution(record)
        except Exception:
            # Preserve successful delegate behavior even if instrumentation fails.
            self._note_failure("execution_success_record")
            return

    def _record_error(
        self,
        *,
        step_index: int,
        decision_id: str | None,
        action: Mapping[str, JSONValue],
        before: SemanticSnapshot,
        error: Exception,
    ) -> None:
        try:
            after = self.snapshot_provider.snapshot()
            if not isinstance(after, SemanticSnapshot):
                raise TypeError("snapshot provider must return SemanticSnapshot")
            record = ExecutionRecord(
                execution_id=f"{self.episode_id}:execution:{step_index}",
                episode_id=self.episode_id,
                step_index=step_index,
                decision_id=decision_id,
                action=action,
                before_snapshot=before,
                after_snapshot=after,
                status=ExecutionStatus.ERROR,
                error_type=_sanitized_error_type(error),
            )
            self.sink.record_execution(record)
        except Exception:
            # Never replace the delegate's original exception with recorder failure.
            self._note_failure("execution_error_record")
            return
