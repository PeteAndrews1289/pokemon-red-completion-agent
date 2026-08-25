from __future__ import annotations

import ctypes
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pokemon_red_completion.runtime_identity import (
    is_canonical_distribution_inventory_name,
    is_runtime_identity_public_document,
)

PRIVATE_ROOT_SENTINEL = ".pokemon-red-completion-private-root.json"
PRIVATE_ROOT_FORMAT = "pokemon-red-completion-private-root"
EPISODE_FORMAT = "pokemon-red-completion-episode-jsonl"
PRIVATE_JSON_ARTIFACT_FORMAT = "pokemon-red-completion-private-artifact-jsonl"
PRIVATE_SEALED_RECORD_FORMAT = "pokemon-red-completion-private-sealed-record"
PRIVATE_ARTIFACT_SCHEMA_VERSION = 1
_PRIVATE_DIRECTORY_MODE = 0o700
_PRIVATE_FILE_MODE = 0o600
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_SEALED_RECORD_BYTES = 1024 * 1024
_MAX_JSONL_LINE_BYTES = 16 * 1024 * 1024
# The qualified balanced-team curriculum has measured just over 506 MB before
# its missing battle labels are included.  One GiB retains a strict reader
# bound while covering the declared 7,000-battle safety envelope and schedule
# variation without making a valid full-game episode unopenable at promotion.
_MAX_EPISODE_BYTES = 1024 * 1024 * 1024
_READER_VALIDATION_TOKEN = object()
_WRITER_VALIDATION_TOKEN = object()
_SESSION_VALIDATION_TOKEN = object()

_SENTINEL_BYTES = (
    json.dumps(
        {
            "format": PRIVATE_ROOT_FORMAT,
            "schema_version": PRIVATE_ARTIFACT_SCHEMA_VERSION,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    + b"\n"
)
_SAFE_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}\Z")
_SAFE_KIND = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_SAFE_STREAM = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_SAFE_REASON = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_WINDOWS_DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/]")
_PATH_KEYS = {
    "cwd",
    "directory",
    "file",
    "filename",
    "filepath",
    "path",
    "rom_filename",
    "rom_path",
}

DeviceId = Callable[[Path], int]
GitWorktreeProbe = Callable[[Path], bool]


class PrivateArtifactError(RuntimeError):
    """Raised when private artifacts cannot be handled without weakening isolation."""


def validate_private_record(record: Mapping[str, object]) -> None:
    """Require a mapping to satisfy the exact sealed-record JSON contract.

    This permits callers to distinguish deterministic encoding defects from a
    later filesystem publication failure without exposing a private path or
    weakening the canonical writer.
    """

    _canonical_record(record)


@dataclass(frozen=True, slots=True)
class SealedRecordSummary:
    """Path-free identity and integrity data for one immutable private record."""

    record_id: str
    kind: str
    record_sha256: str
    manifest_sha256: str
    total_bytes: int

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "private-sealed-record-summary-v1",
            "record_id": self.record_id,
            "kind": self.kind,
            "record_sha256": self.record_sha256,
            "manifest_sha256": self.manifest_sha256,
            "total_bytes": self.total_bytes,
        }


@dataclass(frozen=True, slots=True)
class SealedRecordManifestMetadata:
    """Manifest-only metadata for one sealed record whose payload was not opened.

    ``declared_record_sha256`` and ``declared_total_bytes`` are authenticated as
    canonical manifest fields and checked against the payload file's filesystem
    metadata.  They do not assert that the payload bytes themselves were read,
    hashed, decoded, or otherwise verified.
    """

    record_id: str
    kind: str
    declared_record_sha256: str
    manifest_sha256: str
    declared_total_bytes: int

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "private-sealed-record-manifest-metadata-v1",
            "record_id": self.record_id,
            "kind": self.kind,
            "declared_record_sha256": self.declared_record_sha256,
            "manifest_sha256": self.manifest_sha256,
            "declared_total_bytes": self.declared_total_bytes,
            "payload_integrity_verified": False,
            "payload_opened": False,
        }


class PrivateSealedRecord:
    """An immutable in-memory view of one fully verified private record."""

    __slots__ = ("_payload", "_summary")

    def __init__(self, *, payload: bytes, summary: SealedRecordSummary) -> None:
        self._payload = payload
        self._summary = summary

    def __repr__(self) -> str:
        return (
            "PrivateSealedRecord("
            f"record_id={self._summary.record_id!r}, "
            f"kind={self._summary.kind!r}, validated=True)"
        )

    @property
    def summary(self) -> SealedRecordSummary:
        return self._summary

    def read(self) -> dict[str, object]:
        """Return a fresh mapping so callers cannot mutate the verified snapshot."""

        value = json.loads(self._payload.decode("ascii"))
        if not isinstance(value, dict):  # Defensive: construction already proves this.
            raise PrivateArtifactError("sealed private record is not a JSON object")
        return value


@dataclass(frozen=True, slots=True)
class EpisodeArtifactState:
    """Path-free terminal or recoverable state of one deterministic episode ID."""

    episode_id: str
    status: str
    reason_code: str | None = None
    manifest_sha256: str | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "private-episode-artifact-state-v1",
            "episode_id": self.episode_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True, slots=True)
class EpisodeSummary:
    """A deliberately path-free account of a finalized private episode."""

    episode_id: str
    status: str
    stream_records: tuple[tuple[str, int], ...]
    total_records: int
    total_bytes: int
    manifest_sha256: str

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "private-episode-summary-v1",
            "episode_id": self.episode_id,
            "status": self.status,
            "stream_records": dict(self.stream_records),
            "total_records": self.total_records,
            "total_bytes": self.total_bytes,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True, slots=True)
class PrivateArtifactSummary:
    """A deliberately path-free account of a finalized typed JSON artifact."""

    artifact_id: str
    kind: str
    status: str
    stream_records: tuple[tuple[str, int], ...]
    total_records: int
    total_bytes: int
    manifest_sha256: str

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "private-json-artifact-summary-v1",
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "status": self.status,
            "stream_records": dict(self.stream_records),
            "total_records": self.total_records,
            "total_bytes": self.total_bytes,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True, slots=True)
class _EpisodeFile:
    stream: str
    filename: str
    records: int
    size: int
    sha256: str


@dataclass(slots=True)
class _Stream:
    name: str
    handle: Any
    records: int = 0


class PrivateArtifactRoot:
    """A validated private root.

    The location is intentionally absent from ``repr`` and all public summaries. Callers
    receive instances from :func:`initialize_private_root` or :func:`open_private_root`.
    """

    __slots__ = (
        "_allow_same_device",
        "_device_id",
        "_git_worktree_probe",
        "_repository_root",
        "_root",
    )

    def __init__(
        self,
        root: Path,
        *,
        repository_root: Path,
        allow_same_device: bool,
        device_id: DeviceId,
        git_worktree_probe: GitWorktreeProbe,
    ) -> None:
        self._root = root
        self._repository_root = repository_root
        self._allow_same_device = allow_same_device
        self._device_id = device_id
        self._git_worktree_probe = git_worktree_probe

    def __repr__(self) -> str:
        return "PrivateArtifactRoot(validated=True)"

    def collection_session(self, collection_id: str) -> CollectionSession:
        """Return an exclusive collection session without exposing its lock location."""

        _validate_artifact_id(collection_id)
        self._revalidate()
        return CollectionSession(
            _validation_token=_SESSION_VALIDATION_TOKEN,
            store=self,
            collection_id=collection_id,
        )

    def publish_sealed_record(
        self,
        record_id: str,
        *,
        kind: str,
        record: Mapping[str, object],
    ) -> PrivateSealedRecord:
        """Publish one small immutable record, idempotently only for identical bytes.

        A unique partial directory is used for each publication attempt. A process
        interruption can therefore leave evidence behind without permanently
        blocking reconstruction of the same deterministic final record.
        """

        _validate_artifact_id(record_id)
        _validate_artifact_kind(kind)
        self._revalidate()
        payload = _canonical_record(record)
        if len(payload) > _MAX_SEALED_RECORD_BYTES:
            raise PrivateArtifactError("sealed private record exceeds the allowed size")

        existing = self.find_sealed_record(record_id, expected_kind=kind)
        if existing is not None:
            if existing._payload != payload:
                raise PrivateArtifactError(
                    "sealed private record already exists with different content"
                )
            return existing

        for suffix in (".partial", ".failed.partial", ".interrupted.partial"):
            if _lexists(self._root / f"{record_id}{suffix}"):
                raise PrivateArtifactError(
                    "sealed private record identity collides with another private artifact"
                )

        temporary = self._root / (f".{record_id}.sealed-{uuid.uuid4().hex}.partial")
        final = self._root / record_id
        try:
            os.mkdir(temporary, mode=_PRIVATE_DIRECTORY_MODE)
            os.chmod(temporary, _PRIVATE_DIRECTORY_MODE)
            _write_exclusive_file(
                temporary / "record.json",
                payload,
                mode=_PRIVATE_FILE_MODE,
            )
            manifest = {
                "bytes": len(payload),
                "format": PRIVATE_SEALED_RECORD_FORMAT,
                "kind": kind,
                "record_id": record_id,
                "record_sha256": hashlib.sha256(payload).hexdigest(),
                "schema_version": PRIVATE_ARTIFACT_SCHEMA_VERSION,
                "status": "complete",
            }
            _write_exclusive_file(
                temporary / "manifest.json",
                _canonical_json_line(manifest),
                mode=_PRIVATE_FILE_MODE,
            )
            _fsync_directory(temporary)
            _rename_no_replace(temporary, final)
            _fsync_directory(self._root)
        except FileExistsError:
            existing = self.find_sealed_record(record_id, expected_kind=kind)
            if existing is not None and existing._payload == payload:
                return existing
            raise PrivateArtifactError(
                "sealed private record already exists with different content"
            ) from None
        except PrivateArtifactError:
            raise
        except OSError:
            existing = self.find_sealed_record(record_id, expected_kind=kind)
            if existing is not None and existing._payload == payload:
                return existing
            raise PrivateArtifactError("unable to publish the sealed private record") from None
        return _open_private_sealed_record(self._root, record_id, expected_kind=kind)

    def find_sealed_record(
        self,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ) -> PrivateSealedRecord | None:
        """Open a verified immutable record, or return ``None`` when it is absent."""

        _validate_artifact_id(record_id)
        if expected_kind is not None:
            _validate_artifact_kind(expected_kind)
        self._revalidate()
        if not _lexists(self._root / record_id):
            return None
        return _open_private_sealed_record(
            self._root,
            record_id,
            expected_kind=expected_kind,
        )

    def inspect_sealed_record_metadata(
        self,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ) -> SealedRecordManifestMetadata | None:
        """Inspect only a sealed record's manifest and payload file metadata.

        This method deliberately never opens ``record.json``.  The returned digest
        is therefore a manifest declaration suitable for commitment inventory, not
        proof that the payload currently hashes to that value.  Call
        :meth:`find_sealed_record` only at the separately authorized payload-opening
        stage when full integrity and canonical JSON verification are required.
        """

        _validate_artifact_id(record_id)
        if expected_kind is not None:
            _validate_artifact_kind(expected_kind)
        self._revalidate()
        if not _lexists(self._root / record_id):
            return None
        return _inspect_private_sealed_record_metadata(
            self._root,
            record_id,
            expected_kind=expected_kind,
        )

    def inspect_episode_state(self, episode_id: str) -> EpisodeArtifactState:
        """Inspect a deterministic episode namespace without returning its location."""

        _validate_episode_id(episode_id)
        self._revalidate()
        return _inspect_episode_artifact_state(self._root, episode_id)

    def begin_episode(self, episode_id: str) -> EpisodeWriter:
        """Create a new, exclusive partial episode.

        An existing final, partial, failed, or interrupted artifact is never reused
        or overwritten.
        """
        _validate_episode_id(episode_id)
        self._revalidate()

        partial = self._root / f"{episode_id}.partial"
        final = self._root / episode_id
        failed = self._root / f"{episode_id}.failed.partial"
        interrupted = self._root / f"{episode_id}.interrupted.partial"
        if any(_lexists(candidate) for candidate in (partial, final, failed, interrupted)):
            raise PrivateArtifactError("episode id is already present; refusing to overwrite")

        try:
            os.mkdir(partial, mode=0o700)
            os.chmod(partial, 0o700)
        except FileExistsError as error:
            raise PrivateArtifactError(
                "episode id is already present; refusing to overwrite"
            ) from error
        except OSError as error:
            raise PrivateArtifactError("unable to create the private partial episode") from error

        try:
            # The partial namespace is the durable, one-shot attempt claim. Persist
            # both its own metadata and the parent directory entry before returning
            # control to a caller that may start emulator execution.
            _fsync_directory(partial)
            _fsync_directory(self._root)
        except PrivateArtifactError:
            # Retain the visible partial so an in-process reconciliation fails
            # closed. The public error deliberately contains no private location.
            raise PrivateArtifactError("unable to durably claim the private episode") from None

        return EpisodeWriter(
            episode_id=episode_id,
            partial=partial,
            final=final,
            failed=failed,
        )

    def begin_artifact(
        self,
        artifact_id: str,
        *,
        kind: str,
    ) -> PrivateArtifactWriter:
        """Create a new typed JSON artifact in the private root.

        Typed artifacts and episodes share one collision-safe identifier namespace,
        while their manifests use distinct formats and identity fields.
        """
        _validate_artifact_id(artifact_id)
        _validate_artifact_kind(kind)
        try:
            self._revalidate()
        except PrivateArtifactError as error:
            raise PrivateArtifactError(str(error)) from None

        partial = self._root / f"{artifact_id}.partial"
        final = self._root / artifact_id
        failed = self._root / f"{artifact_id}.failed.partial"
        try:
            occupied = any(_lexists(candidate) for candidate in (partial, final, failed))
        except PrivateArtifactError as error:
            raise PrivateArtifactError(str(error)) from None
        if occupied:
            raise PrivateArtifactError("artifact id is already present; refusing to overwrite")

        try:
            os.mkdir(partial, mode=_PRIVATE_DIRECTORY_MODE)
            os.chmod(partial, _PRIVATE_DIRECTORY_MODE)
        except FileExistsError:
            raise PrivateArtifactError(
                "artifact id is already present; refusing to overwrite"
            ) from None
        except OSError:
            raise PrivateArtifactError("unable to create the private partial artifact") from None

        try:
            # A typed artifact may guard a one-shot measurement just as an
            # episode does.  Persist the exclusive partial namespace before
            # returning control to code that can send emulator input.
            _fsync_directory(partial)
            _fsync_directory(self._root)
        except PrivateArtifactError:
            # Retain the visible partial so a restart treats the attempt as
            # consumed.  Do not expose the private location in the error.
            raise PrivateArtifactError("unable to durably claim the private artifact") from None

        return PrivateArtifactWriter(
            _validation_token=_WRITER_VALIDATION_TOKEN,
            artifact_id=artifact_id,
            kind=kind,
            partial=partial,
            final=final,
            failed=failed,
        )

    def open_episode(self, episode_id: str) -> PrivateEpisodeReader:
        """Open one complete episode only after validating all of its private data."""
        _validate_episode_id(episode_id)
        try:
            self._revalidate()
        except PrivateArtifactError as error:
            # Root validation predates the read API and may retain a path-bearing
            # operating-system exception as its cause. Preserve only its sanitized
            # public message at this boundary.
            raise PrivateArtifactError(str(error)) from None
        return _open_private_episode(self._root, episode_id)

    def _revalidate(self) -> None:
        _validate_root_location(
            self._root,
            repository_root=self._repository_root,
            allow_same_device=self._allow_same_device,
            device_id=self._device_id,
            git_worktree_probe=self._git_worktree_probe,
        )
        _validate_sentinel(self._root)

    def _recover_interrupted_episode(
        self,
        episode_id: str,
    ) -> EpisodeArtifactState:
        self._revalidate()
        state = _inspect_episode_artifact_state(self._root, episode_id)
        if state.status != "partial":
            return state

        partial = self._root / f"{episode_id}.partial"
        try:
            complete = _validate_episode_directory_state(
                self._root,
                partial.name,
                episode_id=episode_id,
                expected_status="complete",
            )
        except PrivateArtifactError:
            complete = None
        if complete is not None:
            try:
                _rename_no_replace(partial, self._root / episode_id)
                _fsync_directory(self._root)
            except (OSError, PrivateArtifactError):
                return self._stable_recovery_state(episode_id)
            return complete

        try:
            failed = _validate_episode_directory_state(
                self._root,
                partial.name,
                episode_id=episode_id,
                expected_status="failed",
            )
        except PrivateArtifactError:
            failed = None
        if failed is not None:
            try:
                _rename_no_replace(
                    partial,
                    self._root / f"{episode_id}.failed.partial",
                )
                _fsync_directory(self._root)
            except (OSError, PrivateArtifactError):
                return self._stable_recovery_state(episode_id)
            return failed

        interrupted = self._root / f"{episode_id}.interrupted.partial"
        try:
            _require_private_directory(partial, subject="partial episode")
            _rename_no_replace(partial, interrupted)
            _fsync_directory(self._root)
        except (OSError, PrivateArtifactError):
            return self._stable_recovery_state(episode_id)
        return EpisodeArtifactState(
            episode_id,
            "interrupted",
            reason_code="process_interrupted",
        )

    def _stable_recovery_state(self, episode_id: str) -> EpisodeArtifactState:
        """Return only a re-observed terminal state after a failed transition."""

        try:
            state = self.inspect_episode_state(episode_id)
        except PrivateArtifactError:
            raise PrivateArtifactError(
                "unable to establish a stable recovered episode state"
            ) from None
        if state.status in {"complete", "failed", "interrupted", "invalid"}:
            return state
        raise PrivateArtifactError("unable to establish a stable recovered episode state")


class CollectionSession:
    """Exclusive, path-free recovery authority for one collection campaign."""

    __slots__ = ("_collection_id", "_descriptor", "_state", "_store")

    def __init__(
        self,
        *,
        _validation_token: object,
        store: PrivateArtifactRoot,
        collection_id: str,
    ) -> None:
        if _validation_token is not _SESSION_VALIDATION_TOKEN:
            raise PrivateArtifactError(
                "collection sessions must be created from a validated private root"
            )
        self._store = store
        self._collection_id = collection_id
        self._descriptor = -1
        self._state = "ready"

    def __repr__(self) -> str:
        return f"CollectionSession(collection_id={self._collection_id!r}, state={self._state!r})"

    @property
    def collection_id(self) -> str:
        return self._collection_id

    @property
    def active(self) -> bool:
        return self._state == "active"

    def __enter__(self) -> CollectionSession:
        if self._state != "ready":
            raise PrivateArtifactError("collection session cannot be entered again")
        self._store._revalidate()
        digest = hashlib.sha256(self._collection_id.encode("ascii")).hexdigest()
        lock_file = self._store._root / f".collection-{digest}.lock"
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = -1
        try:
            descriptor = os.open(lock_file, flags, _PRIVATE_FILE_MODE)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise PrivateArtifactError("collection lock failed validation")
            os.fchmod(descriptor, _PRIVATE_FILE_MODE)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise PrivateArtifactError("collection is already active") from None
        except PrivateArtifactError:
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)
            raise
        except OSError as error:
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise PrivateArtifactError("collection is already active") from None
            raise PrivateArtifactError("unable to acquire the collection session") from None
        self._descriptor = descriptor
        self._state = "active"
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> bool:
        del exception_type, exception, traceback
        if self._state == "active":
            with suppress(OSError):
                fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            try:
                os.close(self._descriptor)
            except OSError:
                self._descriptor = -1
                self._state = "closed"
                raise PrivateArtifactError("unable to close the collection session") from None
            self._descriptor = -1
            self._state = "closed"
        return False

    def inspect_episode(self, episode_id: str) -> EpisodeArtifactState:
        self._require_active()
        return self._store.inspect_episode_state(episode_id)

    def recover_interrupted_episode(self, episode_id: str) -> EpisodeArtifactState:
        """Seal an orphan partial as complete, failed, or permanently interrupted."""

        self._require_active()
        _validate_episode_id(episode_id)
        return self._store._recover_interrupted_episode(episode_id)

    def require_store(self, store: PrivateArtifactRoot) -> None:
        """Fail unless this active session authorizes recovery in ``store``."""

        self._require_active()
        if self._store is not store:
            raise PrivateArtifactError("collection session belongs to another private root")

    def _require_active(self) -> None:
        if self._state != "active":
            raise PrivateArtifactError("collection session is not active")


class PrivateEpisodeReader:
    """A read-only, path-free view over one fully verified private episode.

    Construction is intentionally internal. The verified stream bytes are retained
    in memory so subsequent filesystem changes cannot alter a reader that has
    already passed its all-stream integrity check.
    """

    __slots__ = ("_episode_id", "_files", "_payloads", "_summary")

    def __init__(
        self,
        *,
        _validation_token: object,
        episode_id: str,
        files: tuple[_EpisodeFile, ...],
        payloads: Mapping[str, bytes],
        summary: EpisodeSummary,
    ) -> None:
        if _validation_token is not _READER_VALIDATION_TOKEN:
            raise PrivateArtifactError(
                "private episode readers must be opened from a validated private root"
            )
        self._episode_id = episode_id
        self._files = files
        self._payloads = dict(payloads)
        self._summary = summary

    def __repr__(self) -> str:
        return (
            "PrivateEpisodeReader("
            f"episode_id={self._episode_id!r}, validated=True, streams={len(self._files)}"
            ")"
        )

    @property
    def summary(self) -> EpisodeSummary:
        """Return the immutable, deliberately path-free episode summary."""
        return self._summary

    @property
    def manifest_sha256(self) -> str:
        """Return the digest of the exact canonical manifest that was validated."""
        return self._summary.manifest_sha256

    @property
    def stream_names(self) -> tuple[str, ...]:
        """Return validated logical stream names, never filesystem names or paths."""
        return tuple(file.stream for file in self._files)

    def public_summary(self) -> dict[str, object]:
        """Return a fresh path-free dictionary suitable for aggregate reporting."""
        return self._summary.public_dict()

    def read_header(self) -> dict[str, object]:
        """Read the episode stream when it contains exactly one verified object."""
        stream = "episode"
        file = self._require_stream(stream)
        if file.records != 1:
            raise PrivateArtifactError("episode header stream must contain exactly one record")
        return next(_iter_verified_json_objects(self._payloads[stream]))

    def iter_stream(
        self,
        stream: str,
        *,
        max_records: int | None = None,
    ) -> Iterator[dict[str, object]]:
        """Iterate a validated stream within its manifest or caller-supplied bound."""
        file = self._require_stream(stream)
        if max_records is not None:
            if isinstance(max_records, bool) or not isinstance(max_records, int):
                raise PrivateArtifactError("record limit must be a non-negative integer")
            if max_records < 0:
                raise PrivateArtifactError("record limit must be a non-negative integer")
            if file.records > max_records:
                raise PrivateArtifactError("episode stream exceeds the requested record limit")
        return _iter_verified_json_objects(self._payloads[stream])

    def _require_stream(self, stream: str) -> _EpisodeFile:
        _validate_stream_name(stream)
        for file in self._files:
            if file.stream == stream:
                return file
        raise PrivateArtifactError("episode stream is absent")


class EpisodeWriter:
    """Write canonical, path-free JSONL streams into one private episode."""

    __slots__ = (
        "_episode_id",
        "_failed",
        "_final",
        "_partial",
        "_state",
        "_streams",
        "_summary",
    )

    def __init__(
        self,
        *,
        episode_id: str,
        partial: Path,
        final: Path,
        failed: Path,
    ) -> None:
        self._episode_id = episode_id
        self._partial = partial
        self._final = final
        self._failed = failed
        self._streams: dict[str, _Stream] = {}
        self._state = "active"
        self._summary: EpisodeSummary | None = None

    def __enter__(self) -> EpisodeWriter:
        self._require_active()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> bool:
        del exception, traceback
        if exception_type is not None:
            with suppress(PrivateArtifactError):
                self.abort("unhandled_exception")
            return False

        if self._state == "active":
            try:
                self.complete()
            except BaseException:
                if self._state == "active":
                    with suppress(PrivateArtifactError):
                        self.abort("finalization_failed")
                raise
        return False

    def append(
        self,
        stream: str,
        record: Mapping[str, object],
        *,
        durable: bool = False,
    ) -> None:
        """Append one canonical JSON object, optionally syncing it before return."""
        if type(durable) is not bool:  # noqa: E721
            raise TypeError("durable must be a bool")
        self._require_active()
        _validate_stream_name(stream)
        payload = _canonical_record(
            record,
            allow_runtime_inventory_names=_is_trajectory_episode_header(
                stream,
                record,
            ),
        )

        target = self._streams.get(stream)
        opened_stream = target is None
        if target is None:
            target = self._open_stream(stream)
            self._streams[stream] = target
        try:
            target.handle.write(payload)
        except OSError as error:
            raise PrivateArtifactError("unable to write a private episode record") from error
        target.records += 1
        if not durable:
            return
        try:
            target.handle.flush()
            os.fsync(target.handle.fileno())
            if opened_stream:
                _fsync_directory(self._partial)
        except (OSError, PrivateArtifactError):
            raise PrivateArtifactError(
                "unable to synchronize a private episode record"
            ) from None

    def complete(self) -> EpisodeSummary:
        """Write the manifest last and atomically publish the completed directory."""
        self._require_active()
        if _lexists(self._final):
            raise PrivateArtifactError("completed episode already exists; refusing to overwrite")
        summary = self._finalize(status="complete", reason_code=None)
        try:
            _rename_no_replace(self._partial, self._final)
        except OSError as error:
            # A sealed complete manifest must not remain under a partial name: callers
            # and offline tooling could otherwise mistake a failed publication for a
            # completed episode.  Mark the writer before attempting recovery so
            # __exit__ never tries to create a second manifest.
            self._state = "publication_failed"
            self._retain_publication_failure()
            raise PrivateArtifactError("unable to publish the completed private episode") from error
        self._state = "complete"
        self._summary = summary
        _fsync_directory(self._final.parent)
        return summary

    def abort(self, reason_code: str = "episode_aborted") -> EpisodeSummary:
        """Retain a visibly failed partial artifact without persisting exception text."""
        self._require_active()
        if not _SAFE_REASON.fullmatch(reason_code):
            raise PrivateArtifactError("failure reason must be a sanitized identifier")
        if _lexists(self._failed):
            raise PrivateArtifactError("failed episode already exists; refusing to overwrite")
        summary = self._finalize(status="failed", reason_code=reason_code)
        try:
            _rename_no_replace(self._partial, self._failed)
        except OSError as error:
            # The manifest already identifies the remaining .partial directory as
            # failed. Prevent context-manager cleanup from colliding with it.
            self._state = "failed"
            self._summary = summary
            raise PrivateArtifactError("unable to retain the failed private episode") from error
        self._state = "failed"
        self._summary = summary
        _fsync_directory(self._failed.parent)
        return summary

    @property
    def summary(self) -> EpisodeSummary:
        if self._summary is None:
            raise PrivateArtifactError("episode has not been finalized")
        return self._summary

    def _open_stream(self, stream: str) -> _Stream:
        filename = f"{stream}.jsonl"
        path = self._partial / filename
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = -1
        try:
            descriptor = os.open(path, flags, 0o600)
            os.fchmod(descriptor, 0o600)
            handle = os.fdopen(descriptor, "wb")
            descriptor = -1
        except FileExistsError as error:
            raise PrivateArtifactError(
                "episode stream already exists; refusing to overwrite"
            ) from error
        except OSError as error:
            raise PrivateArtifactError("unable to create a private episode stream") from error
        finally:
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)
        return _Stream(name=stream, handle=handle)

    def _finalize(self, *, status: str, reason_code: str | None) -> EpisodeSummary:
        self._close_streams()
        files: list[dict[str, object]] = []
        total_records = 0
        total_bytes = 0
        stream_records: list[tuple[str, int]] = []

        for stream_name in sorted(self._streams):
            stream = self._streams[stream_name]
            filename = f"{stream_name}.jsonl"
            path = self._partial / filename
            try:
                size = path.stat().st_size
            except OSError as error:
                raise PrivateArtifactError("unable to inspect a private episode stream") from error
            digest = _sha256_file(path)
            files.append(
                {
                    "bytes": size,
                    "filename": filename,
                    "records": stream.records,
                    "sha256": digest,
                }
            )
            total_records += stream.records
            total_bytes += size
            stream_records.append((stream_name, stream.records))

        manifest: dict[str, object] = {
            "episode_id": self._episode_id,
            "files": files,
            "format": EPISODE_FORMAT,
            "schema_version": PRIVATE_ARTIFACT_SCHEMA_VERSION,
            "status": status,
            "totals": {
                "bytes": total_bytes,
                "files": len(files),
                "records": total_records,
            },
        }
        if reason_code is not None:
            manifest["reason_code"] = reason_code
        manifest_bytes = _canonical_json_line(manifest)
        _write_exclusive_file(self._partial / "manifest.json", manifest_bytes, mode=0o600)
        _fsync_directory(self._partial)
        return EpisodeSummary(
            episode_id=self._episode_id,
            status=status,
            stream_records=tuple(stream_records),
            total_records=total_records,
            total_bytes=total_bytes,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        )

    def _retain_publication_failure(self) -> None:
        """Convert a sealed-but-unpublished episode into an explicit failed artifact."""
        manifest = self._partial / "manifest.json"
        unpublished_manifest = self._partial / "manifest.unpublished.json"
        if _lexists(unpublished_manifest):
            try:
                manifest.unlink()
            except OSError as error:
                raise PrivateArtifactError(
                    "unable to mark an unpublished private episode as failed"
                ) from error
        else:
            try:
                _rename_no_replace(manifest, unpublished_manifest)
            except OSError:
                # Retention must never leave a complete manifest under a .partial
                # name, even when exclusive rename is unavailable on the volume.
                try:
                    manifest.unlink()
                except OSError as error:
                    raise PrivateArtifactError(
                        "unable to mark an unpublished private episode as failed"
                    ) from error

        failed_summary = self._finalize(
            status="failed",
            reason_code="publication_failed",
        )
        self._summary = failed_summary
        if _lexists(self._failed):
            # The remaining .partial directory has a failed manifest, so it cannot
            # masquerade as complete even though no collision-safe rename is possible.
            self._state = "failed"
            raise PrivateArtifactError("failed episode already exists; refusing to overwrite")
        try:
            _rename_no_replace(self._partial, self._failed)
        except OSError as error:
            # Leave the path explicitly partial with a failed manifest.
            self._state = "failed"
            raise PrivateArtifactError("unable to retain the failed private episode") from error
        self._state = "failed"
        _fsync_directory(self._failed.parent)

    def _close_streams(self) -> None:
        first_error: OSError | None = None
        for stream in self._streams.values():
            if stream.handle.closed:
                continue
            try:
                stream.handle.flush()
                os.fsync(stream.handle.fileno())
                stream.handle.close()
            except OSError as error:
                first_error = first_error or error
        if first_error is not None:
            raise PrivateArtifactError(
                "unable to finalize private episode streams"
            ) from first_error

    def _require_active(self) -> None:
        if self._state != "active":
            raise PrivateArtifactError("episode writer is already finalized")


class PrivateArtifactWriter:
    """Write one typed, canonical JSONL artifact outside the episode format."""

    __slots__ = (
        "_artifact_id",
        "_failed",
        "_final",
        "_kind",
        "_partial",
        "_state",
        "_streams",
        "_summary",
    )

    def __init__(
        self,
        *,
        _validation_token: object,
        artifact_id: str,
        kind: str,
        partial: Path,
        final: Path,
        failed: Path,
    ) -> None:
        if _validation_token is not _WRITER_VALIDATION_TOKEN:
            raise PrivateArtifactError(
                "private artifact writers must be created from a validated private root"
            )
        self._artifact_id = artifact_id
        self._kind = kind
        self._partial = partial
        self._final = final
        self._failed = failed
        self._streams: dict[str, _Stream] = {}
        self._state = "active"
        self._summary: PrivateArtifactSummary | None = None

    def __repr__(self) -> str:
        return (
            "PrivateArtifactWriter("
            f"artifact_id={self._artifact_id!r}, kind={self._kind!r}, state={self._state!r}"
            ")"
        )

    def __enter__(self) -> PrivateArtifactWriter:
        self._require_active()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> bool:
        del exception, traceback
        if exception_type is not None:
            with suppress(PrivateArtifactError):
                self.abort("unhandled_exception")
            return False

        if self._state == "active":
            try:
                self.complete()
            except BaseException:
                if self._state == "active":
                    with suppress(PrivateArtifactError):
                        self.abort("finalization_failed")
                raise
        return False

    def append(
        self,
        stream: str,
        record: Mapping[str, object],
        *,
        durable: bool = False,
    ) -> None:
        """Append one path-free canonical JSON object to a named stream.

        ``durable=True`` flushes and synchronizes the record before returning.
        It is intended for sparse one-shot evidence where losing the last
        observable attempt to a power failure is more costly than one fsync.
        """
        self._require_active()
        _validate_stream_name(stream)
        payload = _canonical_record(record)

        target = self._streams.get(stream)
        opened_stream = target is None
        if target is None:
            target = self._open_stream(stream)
            self._streams[stream] = target
        try:
            target.handle.write(payload)
            target.records += 1
        except OSError:
            raise PrivateArtifactError("unable to write a private artifact record") from None
        if not durable:
            return
        try:
            target.handle.flush()
            os.fsync(target.handle.fileno())
        except OSError:
            raise PrivateArtifactError(
                "unable to synchronize a private artifact record"
            ) from None
        if opened_stream:
            try:
                _fsync_directory(self._partial)
            except PrivateArtifactError:
                raise PrivateArtifactError(
                    "unable to synchronize a private artifact record"
                ) from None

    def complete(self) -> PrivateArtifactSummary:
        """Write the typed manifest last and atomically publish the artifact."""
        self._require_active()
        try:
            final_exists = _lexists(self._final)
        except PrivateArtifactError as error:
            raise PrivateArtifactError(str(error)) from None
        if final_exists:
            raise PrivateArtifactError("completed artifact already exists; refusing to overwrite")
        summary = self._finalize(status="complete", reason_code=None)
        try:
            _rename_no_replace(self._partial, self._final)
        except OSError:
            self._state = "publication_failed"
            self._retain_publication_failure()
            raise PrivateArtifactError("unable to publish the completed private artifact") from None
        self._state = "complete"
        self._summary = summary
        try:
            _fsync_directory(self._final.parent)
        except PrivateArtifactError as error:
            raise PrivateArtifactError(str(error)) from None
        return summary

    def abort(self, reason_code: str = "artifact_aborted") -> PrivateArtifactSummary:
        """Retain a visibly failed partial artifact with a sanitized reason code."""
        self._require_active()
        if not isinstance(reason_code, str) or not _SAFE_REASON.fullmatch(reason_code):
            raise PrivateArtifactError("failure reason must be a sanitized identifier")
        try:
            failed_exists = _lexists(self._failed)
        except PrivateArtifactError as error:
            raise PrivateArtifactError(str(error)) from None
        if failed_exists:
            raise PrivateArtifactError("failed artifact already exists; refusing to overwrite")
        summary = self._finalize(status="failed", reason_code=reason_code)
        try:
            _rename_no_replace(self._partial, self._failed)
        except OSError:
            self._state = "failed"
            self._summary = summary
            raise PrivateArtifactError("unable to retain the failed private artifact") from None
        self._state = "failed"
        self._summary = summary
        try:
            _fsync_directory(self._failed.parent)
        except PrivateArtifactError as error:
            raise PrivateArtifactError(str(error)) from None
        return summary

    @property
    def summary(self) -> PrivateArtifactSummary:
        if self._summary is None:
            raise PrivateArtifactError("artifact has not been finalized")
        return self._summary

    def _open_stream(self, stream: str) -> _Stream:
        filename = f"{stream}.jsonl"
        path = self._partial / filename
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = -1
        try:
            descriptor = os.open(path, flags, _PRIVATE_FILE_MODE)
            os.fchmod(descriptor, _PRIVATE_FILE_MODE)
            handle = os.fdopen(descriptor, "wb")
            descriptor = -1
        except FileExistsError:
            raise PrivateArtifactError(
                "artifact stream already exists; refusing to overwrite"
            ) from None
        except OSError:
            raise PrivateArtifactError("unable to create a private artifact stream") from None
        finally:
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)
        return _Stream(name=stream, handle=handle)

    def _finalize(
        self,
        *,
        status: str,
        reason_code: str | None,
    ) -> PrivateArtifactSummary:
        self._close_streams()
        files: list[dict[str, object]] = []
        total_records = 0
        total_bytes = 0
        stream_records: list[tuple[str, int]] = []

        for stream_name in sorted(self._streams):
            stream = self._streams[stream_name]
            filename = f"{stream_name}.jsonl"
            path = self._partial / filename
            try:
                metadata = path.lstat()
            except OSError:
                raise PrivateArtifactError("unable to inspect a private artifact stream") from None
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != _PRIVATE_FILE_MODE
            ):
                raise PrivateArtifactError("private artifact stream failed validation")
            try:
                digest = _sha256_file(path)
            except PrivateArtifactError:
                raise PrivateArtifactError("unable to hash a private artifact stream") from None
            files.append(
                {
                    "bytes": metadata.st_size,
                    "filename": filename,
                    "records": stream.records,
                    "sha256": digest,
                }
            )
            total_records += stream.records
            total_bytes += metadata.st_size
            stream_records.append((stream_name, stream.records))

        manifest: dict[str, object] = {
            "artifact_id": self._artifact_id,
            "files": files,
            "format": PRIVATE_JSON_ARTIFACT_FORMAT,
            "kind": self._kind,
            "schema_version": PRIVATE_ARTIFACT_SCHEMA_VERSION,
            "status": status,
            "totals": {
                "bytes": total_bytes,
                "files": len(files),
                "records": total_records,
            },
        }
        if reason_code is not None:
            manifest["reason_code"] = reason_code
        manifest_bytes = _canonical_json_line(manifest)
        try:
            _write_exclusive_file(
                self._partial / "manifest.json",
                manifest_bytes,
                mode=_PRIVATE_FILE_MODE,
            )
            _fsync_directory(self._partial)
        except PrivateArtifactError as error:
            raise PrivateArtifactError(str(error)) from None
        return PrivateArtifactSummary(
            artifact_id=self._artifact_id,
            kind=self._kind,
            status=status,
            stream_records=tuple(stream_records),
            total_records=total_records,
            total_bytes=total_bytes,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        )

    def _retain_publication_failure(self) -> None:
        manifest = self._partial / "manifest.json"
        unpublished_manifest = self._partial / "manifest.unpublished.json"
        try:
            unpublished_exists = _lexists(unpublished_manifest)
        except PrivateArtifactError as error:
            raise PrivateArtifactError(str(error)) from None
        if unpublished_exists:
            try:
                manifest.unlink()
            except OSError:
                raise PrivateArtifactError(
                    "unable to mark an unpublished private artifact as failed"
                ) from None
        else:
            try:
                _rename_no_replace(manifest, unpublished_manifest)
            except OSError:
                try:
                    manifest.unlink()
                except OSError:
                    raise PrivateArtifactError(
                        "unable to mark an unpublished private artifact as failed"
                    ) from None

        failed_summary = self._finalize(
            status="failed",
            reason_code="publication_failed",
        )
        self._summary = failed_summary
        try:
            failed_exists = _lexists(self._failed)
        except PrivateArtifactError as error:
            raise PrivateArtifactError(str(error)) from None
        if failed_exists:
            self._state = "failed"
            raise PrivateArtifactError("failed artifact already exists; refusing to overwrite")
        try:
            _rename_no_replace(self._partial, self._failed)
        except OSError:
            self._state = "failed"
            raise PrivateArtifactError("unable to retain the failed private artifact") from None
        self._state = "failed"
        try:
            _fsync_directory(self._failed.parent)
        except PrivateArtifactError as error:
            raise PrivateArtifactError(str(error)) from None

    def _close_streams(self) -> None:
        failed = False
        for stream in self._streams.values():
            if stream.handle.closed:
                continue
            try:
                stream.handle.flush()
                os.fsync(stream.handle.fileno())
                stream.handle.close()
            except OSError:
                failed = True
        if failed:
            raise PrivateArtifactError("unable to finalize private artifact streams") from None

    def _require_active(self) -> None:
        if self._state != "active":
            raise PrivateArtifactError("artifact writer is already finalized")


def initialize_private_root(
    root: str | Path,
    *,
    repository_root: str | Path,
    allow_same_device: bool = False,
    device_id: DeviceId | None = None,
    git_worktree_probe: GitWorktreeProbe | None = None,
) -> PrivateArtifactRoot:
    """Mark an explicit, existing directory as an isolated private-artifact root.

    The directory itself is never created. Existing valid initialization is idempotent;
    an existing malformed sentinel is treated as tampering and is never replaced.
    """
    device_id = device_id or _default_device_id
    git_worktree_probe = git_worktree_probe or _default_git_worktree_probe
    validated_root, validated_repository = _validate_root_location(
        root,
        repository_root=repository_root,
        allow_same_device=allow_same_device,
        device_id=device_id,
        git_worktree_probe=git_worktree_probe,
    )
    sentinel = validated_root / PRIVATE_ROOT_SENTINEL
    if _lexists(sentinel):
        _validate_sentinel(validated_root)
    else:
        try:
            _write_exclusive_file(sentinel, _SENTINEL_BYTES, mode=0o600)
            _fsync_directory(validated_root)
        except PrivateArtifactError:
            if _lexists(sentinel):
                _validate_sentinel(validated_root)
            else:
                raise
    return PrivateArtifactRoot(
        validated_root,
        repository_root=validated_repository,
        allow_same_device=allow_same_device,
        device_id=device_id,
        git_worktree_probe=git_worktree_probe,
    )


def open_private_root(
    root: str | Path,
    *,
    repository_root: str | Path,
    allow_same_device: bool = False,
    device_id: DeviceId | None = None,
    git_worktree_probe: GitWorktreeProbe | None = None,
) -> PrivateArtifactRoot:
    """Open an initialized root, failing closed when its sentinel is absent or altered."""
    device_id = device_id or _default_device_id
    git_worktree_probe = git_worktree_probe or _default_git_worktree_probe
    validated_root, validated_repository = _validate_root_location(
        root,
        repository_root=repository_root,
        allow_same_device=allow_same_device,
        device_id=device_id,
        git_worktree_probe=git_worktree_probe,
    )
    _validate_sentinel(validated_root)
    return PrivateArtifactRoot(
        validated_root,
        repository_root=validated_repository,
        allow_same_device=allow_same_device,
        device_id=device_id,
        git_worktree_probe=git_worktree_probe,
    )


def _open_private_sealed_record(
    root: Path,
    record_id: str,
    *,
    expected_kind: str | None,
) -> PrivateSealedRecord:
    root_descriptor = -1
    record_descriptor = -1
    try:
        root_descriptor = os.open(root, _directory_read_flags())
        expected_directory = _entry_metadata(root_descriptor, record_id)
        if expected_directory is None:
            raise PrivateArtifactError("sealed private record is absent")
        if (
            not stat.S_ISDIR(expected_directory.st_mode)
            or stat.S_IMODE(expected_directory.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            raise PrivateArtifactError("sealed private record directory is unsafe")
        record_descriptor = os.open(
            record_id,
            _directory_read_flags(),
            dir_fd=root_descriptor,
        )
        opened_directory = _fstat(
            record_descriptor,
            subject="sealed private record directory",
        )
        if (
            not _same_file(expected_directory, opened_directory)
            or not stat.S_ISDIR(opened_directory.st_mode)
            or stat.S_IMODE(opened_directory.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            raise PrivateArtifactError("sealed private record changed while opening")
        if _directory_entries(record_descriptor) != {"manifest.json", "record.json"}:
            raise PrivateArtifactError("sealed private record contents do not match its format")

        manifest_bytes = _read_private_entry(
            record_descriptor,
            "manifest.json",
            subject="sealed record manifest",
            maximum_bytes=_MAX_MANIFEST_BYTES,
        )
        kind, size, record_sha256 = _sealed_record_manifest_fields(
            manifest_bytes,
            record_id=record_id,
            expected_kind=expected_kind,
        )
        payload = _read_private_entry(
            record_descriptor,
            "record.json",
            subject="sealed private record",
            maximum_bytes=_MAX_SEALED_RECORD_BYTES,
            expected_bytes=size,
        )
        if hashlib.sha256(payload).hexdigest() != record_sha256:
            raise PrivateArtifactError("sealed private record failed its integrity check")
        value = _decode_canonical_json_object(
            payload,
            subject="sealed private record",
            maximum_bytes=_MAX_SEALED_RECORD_BYTES,
        )
        if _canonical_record(value) != payload:
            raise PrivateArtifactError("sealed private record contains unsafe values")
        final_directory = _fstat(
            record_descriptor,
            subject="sealed private record directory",
        )
        if not _same_file(opened_directory, final_directory) or _directory_entries(
            record_descriptor
        ) != {"manifest.json", "record.json"}:
            raise PrivateArtifactError("sealed private record changed during validation")
        return PrivateSealedRecord(
            payload=payload,
            summary=SealedRecordSummary(
                record_id=record_id,
                kind=kind,
                record_sha256=record_sha256,
                manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                total_bytes=size,
            ),
        )
    except PrivateArtifactError:
        raise
    except OSError:
        raise PrivateArtifactError("unable to inspect the sealed private record") from None
    finally:
        for descriptor in (record_descriptor, root_descriptor):
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)


def _inspect_private_sealed_record_metadata(
    root: Path,
    record_id: str,
    *,
    expected_kind: str | None,
) -> SealedRecordManifestMetadata:
    root_descriptor = -1
    record_descriptor = -1
    try:
        root_descriptor = os.open(root, _directory_read_flags())
        expected_directory = _entry_metadata(root_descriptor, record_id)
        if expected_directory is None:
            raise PrivateArtifactError("sealed private record is absent")
        if (
            not stat.S_ISDIR(expected_directory.st_mode)
            or stat.S_IMODE(expected_directory.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            raise PrivateArtifactError("sealed private record directory is unsafe")
        record_descriptor = os.open(
            record_id,
            _directory_read_flags(),
            dir_fd=root_descriptor,
        )
        opened_directory = _fstat(
            record_descriptor,
            subject="sealed private record directory",
        )
        if (
            not _same_file(expected_directory, opened_directory)
            or not stat.S_ISDIR(opened_directory.st_mode)
            or stat.S_IMODE(opened_directory.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            raise PrivateArtifactError("sealed private record changed while opening")
        expected_entries = {"manifest.json", "record.json"}
        if _directory_entries(record_descriptor) != expected_entries:
            raise PrivateArtifactError("sealed private record contents do not match its format")

        manifest_bytes = _read_private_entry(
            record_descriptor,
            "manifest.json",
            subject="sealed record manifest",
            maximum_bytes=_MAX_MANIFEST_BYTES,
        )
        kind, size, declared_record_sha256 = _sealed_record_manifest_fields(
            manifest_bytes,
            record_id=record_id,
            expected_kind=expected_kind,
        )
        expected_payload = _entry_metadata(record_descriptor, "record.json")
        _validate_sealed_payload_metadata(expected_payload, expected_bytes=size)

        final_payload = _entry_metadata(record_descriptor, "record.json")
        _validate_sealed_payload_metadata(final_payload, expected_bytes=size)
        final_directory = _fstat(
            record_descriptor,
            subject="sealed private record directory",
        )
        named_directory = _entry_metadata(root_descriptor, record_id)
        if (
            final_payload is None
            or expected_payload is None
            or named_directory is None
            or not _same_file(expected_payload, final_payload)
            or not _same_file(opened_directory, final_directory)
            or not _same_file(opened_directory, named_directory)
            or stat.S_IMODE(final_directory.st_mode) != _PRIVATE_DIRECTORY_MODE
            or _directory_entries(record_descriptor) != expected_entries
        ):
            raise PrivateArtifactError("sealed private record changed during metadata inspection")
        return SealedRecordManifestMetadata(
            record_id=record_id,
            kind=kind,
            declared_record_sha256=declared_record_sha256,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            declared_total_bytes=size,
        )
    except PrivateArtifactError:
        raise
    except OSError:
        raise PrivateArtifactError("unable to inspect sealed private record metadata") from None
    finally:
        for descriptor in (record_descriptor, root_descriptor):
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)


def _sealed_record_manifest_fields(
    manifest_bytes: bytes,
    *,
    record_id: str,
    expected_kind: str | None,
) -> tuple[str, int, str]:
    manifest = _decode_canonical_json_object(
        manifest_bytes,
        subject="sealed record manifest",
        maximum_bytes=_MAX_MANIFEST_BYTES,
    )
    _require_exact_keys(
        manifest,
        {
            "bytes",
            "format",
            "kind",
            "record_id",
            "record_sha256",
            "schema_version",
            "status",
        },
        subject="sealed record manifest",
    )
    if manifest["format"] != PRIVATE_SEALED_RECORD_FORMAT:
        raise PrivateArtifactError("sealed private record format is unsupported")
    schema_version = manifest["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != PRIVATE_ARTIFACT_SCHEMA_VERSION
    ):
        raise PrivateArtifactError("sealed private record schema is unsupported")
    if manifest["status"] != "complete" or manifest["record_id"] != record_id:
        raise PrivateArtifactError("sealed private record identity is invalid")
    kind = manifest["kind"]
    if not isinstance(kind, str):
        raise PrivateArtifactError("sealed private record kind is invalid")
    try:
        _validate_artifact_kind(kind)
    except PrivateArtifactError:
        raise PrivateArtifactError("sealed private record kind is invalid") from None
    if expected_kind is not None and kind != expected_kind:
        raise PrivateArtifactError("sealed private record kind does not match")
    size = _manifest_integer(manifest, "bytes")
    if size <= 0 or size > _MAX_SEALED_RECORD_BYTES:
        raise PrivateArtifactError("sealed private record size is invalid")
    record_sha256 = manifest["record_sha256"]
    if not isinstance(record_sha256, str) or _SHA256.fullmatch(record_sha256) is None:
        raise PrivateArtifactError("sealed private record digest is invalid")
    return kind, size, record_sha256


def _validate_sealed_payload_metadata(
    metadata: os.stat_result | None,
    *,
    expected_bytes: int,
) -> None:
    if metadata is None:
        raise PrivateArtifactError("sealed private record payload is absent")
    if not stat.S_ISREG(metadata.st_mode):
        raise PrivateArtifactError("sealed private record payload is not a regular file")
    if stat.S_IMODE(metadata.st_mode) != _PRIVATE_FILE_MODE:
        raise PrivateArtifactError("sealed private record payload permissions are unsafe")
    if metadata.st_nlink != 1:
        raise PrivateArtifactError("sealed private record payload has an unsafe link count")
    if metadata.st_size != expected_bytes:
        raise PrivateArtifactError(
            "sealed private record payload byte count does not match its manifest"
        )


def _inspect_episode_artifact_state(
    root: Path,
    episode_id: str,
) -> EpisodeArtifactState:
    candidates = {
        "complete": root / episode_id,
        "partial": root / f"{episode_id}.partial",
        "failed": root / f"{episode_id}.failed.partial",
        "interrupted": root / f"{episode_id}.interrupted.partial",
    }
    present = [status for status, candidate in candidates.items() if _lexists(candidate)]
    if not present:
        return EpisodeArtifactState(episode_id, "absent")
    if len(present) != 1:
        return EpisodeArtifactState(
            episode_id,
            "invalid",
            reason_code="ambiguous_episode_state",
        )

    status = present[0]
    candidate = candidates[status]
    if status in {"partial", "interrupted"}:
        try:
            _require_private_directory(candidate, subject=f"{status} episode")
        except PrivateArtifactError:
            return EpisodeArtifactState(
                episode_id,
                "invalid",
                reason_code=f"invalid_{status}_artifact",
            )
        return EpisodeArtifactState(
            episode_id,
            status,
            reason_code=("process_interrupted" if status == "interrupted" else None),
        )

    try:
        return _validate_episode_directory_state(
            root,
            candidate.name,
            episode_id=episode_id,
            expected_status=status,
        )
    except PrivateArtifactError:
        return EpisodeArtifactState(
            episode_id,
            "invalid",
            reason_code=f"invalid_{status}_artifact",
        )


def _validate_episode_directory_state(
    root: Path,
    directory_name: str,
    *,
    episode_id: str,
    expected_status: str,
) -> EpisodeArtifactState:
    root_descriptor = -1
    episode_descriptor = -1
    try:
        root_descriptor = os.open(root, _directory_read_flags())
        expected_directory = _entry_metadata(root_descriptor, directory_name)
        if expected_directory is None:
            raise PrivateArtifactError("episode artifact is absent")
        if (
            not stat.S_ISDIR(expected_directory.st_mode)
            or stat.S_IMODE(expected_directory.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            raise PrivateArtifactError("episode artifact directory is unsafe")
        episode_descriptor = os.open(
            directory_name,
            _directory_read_flags(),
            dir_fd=root_descriptor,
        )
        opened_directory = _fstat(
            episode_descriptor,
            subject="episode artifact directory",
        )
        if (
            not _same_file(expected_directory, opened_directory)
            or not stat.S_ISDIR(opened_directory.st_mode)
            or stat.S_IMODE(opened_directory.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            raise PrivateArtifactError("episode artifact changed while opening")

        manifest_bytes = _read_private_entry(
            episode_descriptor,
            "manifest.json",
            subject="episode manifest",
            maximum_bytes=_MAX_MANIFEST_BYTES,
        )
        manifest, files = _validate_episode_manifest(
            manifest_bytes,
            episode_id=episode_id,
            expected_status=expected_status,
        )
        expected_entries = {"manifest.json", *(file.filename for file in files)}
        entries = _directory_entries(episode_descriptor)
        unpublished = "manifest.unpublished.json" in entries
        if unpublished:
            if expected_status != "failed" or manifest.get("reason_code") != "publication_failed":
                raise PrivateArtifactError("episode artifact has an unexpected unpublished seal")
            expected_entries.add("manifest.unpublished.json")
        if entries != expected_entries:
            raise PrivateArtifactError(
                "episode artifact contents do not exactly match its manifest"
            )

        for file in files:
            payload = _read_private_entry(
                episode_descriptor,
                file.filename,
                subject="episode stream",
                maximum_bytes=_MAX_EPISODE_BYTES,
                expected_bytes=file.size,
            )
            if hashlib.sha256(payload).hexdigest() != file.sha256:
                raise PrivateArtifactError("episode stream failed its integrity check")
            _validate_jsonl_payload(payload, expected_records=file.records)

        if unpublished:
            unpublished_payload = _read_private_entry(
                episode_descriptor,
                "manifest.unpublished.json",
                subject="unpublished episode manifest",
                maximum_bytes=_MAX_MANIFEST_BYTES,
            )
            _, unpublished_files = _validate_episode_manifest(
                unpublished_payload,
                episode_id=episode_id,
                expected_status="complete",
            )
            if unpublished_files != files:
                raise PrivateArtifactError(
                    "unpublished episode manifest does not match failed streams"
                )

        if _directory_entries(episode_descriptor) != expected_entries:
            raise PrivateArtifactError("episode artifact changed during validation")
        final_directory = _fstat(
            episode_descriptor,
            subject="episode artifact directory",
        )
        if (
            not _same_file(opened_directory, final_directory)
            or stat.S_IMODE(final_directory.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            raise PrivateArtifactError("episode artifact changed during validation")
        return EpisodeArtifactState(
            episode_id=episode_id,
            status=expected_status,
            reason_code=(str(manifest["reason_code"]) if expected_status == "failed" else None),
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        )
    except PrivateArtifactError:
        raise
    except OSError:
        raise PrivateArtifactError("unable to inspect the episode artifact") from None
    finally:
        for descriptor in (episode_descriptor, root_descriptor):
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)


def _require_private_directory(path: Path, *, subject: str) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        raise PrivateArtifactError(f"{subject} cannot be inspected") from None
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != _PRIVATE_DIRECTORY_MODE
    ):
        raise PrivateArtifactError(f"{subject} is not a regular private directory")


def _open_private_episode(root: Path, episode_id: str) -> PrivateEpisodeReader:
    root_descriptor = -1
    episode_descriptor = -1
    try:
        root_descriptor = os.open(root, _directory_read_flags())

        if _entry_metadata(root_descriptor, f"{episode_id}.partial") is not None:
            raise PrivateArtifactError("episode is still partial and cannot be read")
        if _entry_metadata(root_descriptor, f"{episode_id}.failed.partial") is not None:
            raise PrivateArtifactError("failed episode cannot be read")
        if _entry_metadata(root_descriptor, f"{episode_id}.interrupted.partial") is not None:
            raise PrivateArtifactError("interrupted episode cannot be read")

        expected_directory = _entry_metadata(root_descriptor, episode_id)
        if expected_directory is None:
            raise PrivateArtifactError("completed episode is absent")
        if not stat.S_ISDIR(expected_directory.st_mode):
            raise PrivateArtifactError("completed episode is not a regular private directory")
        if stat.S_IMODE(expected_directory.st_mode) != _PRIVATE_DIRECTORY_MODE:
            raise PrivateArtifactError("completed episode directory permissions are unsafe")

        try:
            episode_descriptor = os.open(
                episode_id,
                _directory_read_flags(),
                dir_fd=root_descriptor,
            )
        except OSError:
            raise PrivateArtifactError("unable to open the completed private episode") from None
        opened_directory = _fstat(
            episode_descriptor,
            subject="completed episode directory",
        )
        if not _same_file(expected_directory, opened_directory):
            raise PrivateArtifactError("completed episode changed while it was being opened")
        if (
            not stat.S_ISDIR(opened_directory.st_mode)
            or stat.S_IMODE(opened_directory.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            raise PrivateArtifactError("completed episode directory permissions are unsafe")

        manifest_bytes = _read_private_entry(
            episode_descriptor,
            "manifest.json",
            subject="episode manifest",
            maximum_bytes=_MAX_MANIFEST_BYTES,
        )
        manifest, files = _validate_complete_manifest(
            manifest_bytes,
            episode_id=episode_id,
        )

        expected_entries = {"manifest.json", *(file.filename for file in files)}
        if _directory_entries(episode_descriptor) != expected_entries:
            raise PrivateArtifactError(
                "episode directory contents do not exactly match its manifest"
            )

        payloads: dict[str, bytes] = {}
        for file in files:
            payload = _read_private_entry(
                episode_descriptor,
                file.filename,
                subject="episode stream",
                maximum_bytes=_MAX_EPISODE_BYTES,
                expected_bytes=file.size,
            )
            if hashlib.sha256(payload).hexdigest() != file.sha256:
                raise PrivateArtifactError("episode stream failed its integrity check")
            _validate_jsonl_payload(payload, expected_records=file.records)
            payloads[file.stream] = payload

        # Detect additions or removals made during validation before publishing the
        # in-memory snapshot to the caller.
        if _directory_entries(episode_descriptor) != expected_entries:
            raise PrivateArtifactError("episode directory changed during validation")
        final_directory = _fstat(
            episode_descriptor,
            subject="completed episode directory",
        )
        if (
            not _same_file(opened_directory, final_directory)
            or stat.S_IMODE(final_directory.st_mode) != _PRIVATE_DIRECTORY_MODE
        ):
            raise PrivateArtifactError("completed episode changed during validation")

        totals = manifest["totals"]
        if not isinstance(totals, dict):  # Kept local for static type narrowing.
            raise PrivateArtifactError("episode manifest totals are invalid")
        summary = EpisodeSummary(
            episode_id=episode_id,
            status="complete",
            stream_records=tuple((file.stream, file.records) for file in files),
            total_records=_manifest_integer(totals, "records"),
            total_bytes=_manifest_integer(totals, "bytes"),
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        )
        return PrivateEpisodeReader(
            _validation_token=_READER_VALIDATION_TOKEN,
            episode_id=episode_id,
            files=files,
            payloads=payloads,
            summary=summary,
        )
    except PrivateArtifactError:
        raise
    except OSError:
        raise PrivateArtifactError("unable to inspect the completed private episode") from None
    finally:
        for descriptor in (episode_descriptor, root_descriptor):
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)


def _validate_complete_manifest(
    payload: bytes,
    *,
    episode_id: str,
) -> tuple[dict[str, object], tuple[_EpisodeFile, ...]]:
    return _validate_episode_manifest(
        payload,
        episode_id=episode_id,
        expected_status="complete",
    )


def _validate_episode_manifest(
    payload: bytes,
    *,
    episode_id: str,
    expected_status: str,
) -> tuple[dict[str, object], tuple[_EpisodeFile, ...]]:
    if expected_status not in {"complete", "failed"}:
        raise PrivateArtifactError("episode manifest expected status is unsupported")
    manifest = _decode_canonical_json_object(
        payload,
        subject="episode manifest",
        maximum_bytes=_MAX_MANIFEST_BYTES,
    )
    expected_keys = {
        "episode_id",
        "files",
        "format",
        "schema_version",
        "status",
        "totals",
    }
    if expected_status == "failed":
        expected_keys.add("reason_code")
    _require_exact_keys(
        manifest,
        expected_keys,
        subject="episode manifest",
    )
    if manifest["format"] != EPISODE_FORMAT:
        raise PrivateArtifactError("episode manifest format is unsupported")
    if (
        isinstance(manifest["schema_version"], bool)
        or not isinstance(manifest["schema_version"], int)
        or manifest["schema_version"] != PRIVATE_ARTIFACT_SCHEMA_VERSION
    ):
        raise PrivateArtifactError("episode manifest schema version is unsupported")
    if manifest["status"] != expected_status:
        raise PrivateArtifactError("episode manifest status does not match its artifact")
    if manifest["episode_id"] != episode_id:
        raise PrivateArtifactError("episode manifest identity does not match the requested episode")
    if expected_status == "failed":
        reason_code = manifest["reason_code"]
        if not isinstance(reason_code, str) or _SAFE_REASON.fullmatch(reason_code) is None:
            raise PrivateArtifactError("episode manifest failure reason is invalid")

    raw_files = manifest["files"]
    if not isinstance(raw_files, list):
        raise PrivateArtifactError("episode manifest files must be a list")
    files: list[_EpisodeFile] = []
    filenames: list[str] = []
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            raise PrivateArtifactError("episode manifest file entries must be objects")
        _require_exact_keys(
            raw_file,
            {"bytes", "filename", "records", "sha256"},
            subject="episode manifest file entry",
        )
        filename = raw_file["filename"]
        if not isinstance(filename, str) or not filename.endswith(".jsonl"):
            raise PrivateArtifactError("episode manifest contains an invalid stream filename")
        stream = filename.removesuffix(".jsonl")
        try:
            _validate_stream_name(stream)
        except PrivateArtifactError:
            raise PrivateArtifactError(
                "episode manifest contains an invalid stream filename"
            ) from None
        if filename != f"{stream}.jsonl":
            raise PrivateArtifactError("episode manifest contains an invalid stream filename")

        size = _manifest_integer(raw_file, "bytes")
        records = _manifest_integer(raw_file, "records")
        digest = raw_file["sha256"]
        if records == 0 or size == 0:
            raise PrivateArtifactError("episode manifest contains an empty declared stream")
        if size > _MAX_EPISODE_BYTES:
            raise PrivateArtifactError("episode stream exceeds the private reader size limit")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise PrivateArtifactError("episode manifest contains an invalid stream digest")
        if filename in filenames:
            raise PrivateArtifactError("episode manifest contains duplicate stream filenames")
        filenames.append(filename)
        files.append(
            _EpisodeFile(
                stream=stream,
                filename=filename,
                records=records,
                size=size,
                sha256=digest,
            )
        )

    if filenames != sorted(filenames):
        raise PrivateArtifactError("episode manifest stream entries are not canonical")

    raw_totals = manifest["totals"]
    if not isinstance(raw_totals, dict):
        raise PrivateArtifactError("episode manifest totals must be an object")
    _require_exact_keys(
        raw_totals,
        {"bytes", "files", "records"},
        subject="episode manifest totals",
    )
    total_bytes = _manifest_integer(raw_totals, "bytes")
    total_files = _manifest_integer(raw_totals, "files")
    total_records = _manifest_integer(raw_totals, "records")
    if total_bytes > _MAX_EPISODE_BYTES:
        raise PrivateArtifactError("episode exceeds the private reader size limit")
    if total_files != len(files):
        raise PrivateArtifactError("episode manifest file total does not match its entries")
    if total_bytes != sum(file.size for file in files):
        raise PrivateArtifactError("episode manifest byte total does not match its entries")
    if total_records != sum(file.records for file in files):
        raise PrivateArtifactError("episode manifest record total does not match its entries")
    return manifest, tuple(files)


def _manifest_integer(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PrivateArtifactError("episode manifest contains an invalid non-negative integer")
    return value


def _require_exact_keys(
    mapping: Mapping[str, object],
    expected: set[str],
    *,
    subject: str,
) -> None:
    if set(mapping) != expected:
        raise PrivateArtifactError(f"{subject} has unsupported or missing fields")


def _read_private_entry(
    directory_descriptor: int,
    filename: str,
    *,
    subject: str,
    maximum_bytes: int,
    expected_bytes: int | None = None,
) -> bytes:
    expected = _entry_metadata(directory_descriptor, filename)
    if expected is None:
        raise PrivateArtifactError(f"{subject} is absent")
    if not stat.S_ISREG(expected.st_mode):
        raise PrivateArtifactError(f"{subject} is not a regular file")
    if stat.S_IMODE(expected.st_mode) != _PRIVATE_FILE_MODE:
        raise PrivateArtifactError(f"{subject} permissions are unsafe")
    if expected.st_nlink != 1:
        raise PrivateArtifactError(f"{subject} has an unsafe link count")
    if expected.st_size < 0 or expected.st_size > maximum_bytes:
        raise PrivateArtifactError(f"{subject} exceeds the private reader size limit")
    if expected_bytes is not None and expected.st_size != expected_bytes:
        raise PrivateArtifactError(f"{subject} byte count does not match its manifest")

    descriptor = -1
    try:
        descriptor = os.open(
            filename,
            _regular_file_read_flags(),
            dir_fd=directory_descriptor,
        )
        opened = _fstat(descriptor, subject=subject)
        if not _same_file(expected, opened):
            raise PrivateArtifactError(f"{subject} changed while it was being opened")
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != _PRIVATE_FILE_MODE
            or opened.st_nlink != 1
        ):
            raise PrivateArtifactError(f"{subject} permissions are unsafe")

        chunks: list[bytes] = []
        bytes_read = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes - bytes_read + 1))
            if not chunk:
                break
            chunks.append(chunk)
            bytes_read += len(chunk)
            if bytes_read > maximum_bytes:
                raise PrivateArtifactError(f"{subject} exceeds the private reader size limit")
        payload = b"".join(chunks)
        final = _fstat(descriptor, subject=subject)
        if (
            not _same_file(opened, final)
            or final.st_size != len(payload)
            or stat.S_IMODE(final.st_mode) != _PRIVATE_FILE_MODE
            or final.st_nlink != 1
        ):
            raise PrivateArtifactError(f"{subject} changed during validation")
        if expected_bytes is not None and len(payload) != expected_bytes:
            raise PrivateArtifactError(f"{subject} byte count does not match its manifest")
        return payload
    except PrivateArtifactError:
        raise
    except OSError:
        raise PrivateArtifactError(f"unable to read the {subject}") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _validate_jsonl_payload(payload: bytes, *, expected_records: int) -> None:
    records = 0
    for _ in _iter_canonical_json_lines(payload, subject="episode stream record"):
        records += 1
        if records > expected_records:
            raise PrivateArtifactError("episode stream record count exceeds its manifest")
    if records != expected_records:
        raise PrivateArtifactError("episode stream record count does not match its manifest")


def _iter_verified_json_objects(payload: bytes) -> Iterator[dict[str, object]]:
    yield from _iter_canonical_json_lines(payload, subject="episode stream record")


def _iter_canonical_json_lines(
    payload: bytes,
    *,
    subject: str,
) -> Iterator[dict[str, object]]:
    position = 0
    while position < len(payload):
        newline = payload.find(b"\n", position)
        if newline < 0:
            raise PrivateArtifactError(f"{subject} is missing its final newline")
        line_end = newline + 1
        if line_end - position > _MAX_JSONL_LINE_BYTES:
            raise PrivateArtifactError(f"{subject} exceeds the maximum line size")
        line = payload[position:line_end]
        yield _decode_canonical_json_object(
            line,
            subject=subject,
            maximum_bytes=_MAX_JSONL_LINE_BYTES,
        )
        position = line_end


def _decode_canonical_json_object(
    payload: bytes,
    *,
    subject: str,
    maximum_bytes: int,
) -> dict[str, object]:
    if not payload or len(payload) > maximum_bytes:
        raise PrivateArtifactError(f"{subject} exceeds the allowed size")
    try:
        rendered = payload.decode("ascii")
        value = json.loads(
            rendered,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError):
        raise PrivateArtifactError(f"{subject} is not valid canonical JSON") from None
    if not isinstance(value, dict):
        raise PrivateArtifactError(f"{subject} must be a JSON object")
    try:
        canonical = _canonical_json_line(value)
    except PrivateArtifactError:
        raise PrivateArtifactError(f"{subject} is not valid canonical JSON") from None
    if canonical != payload:
        raise PrivateArtifactError(f"{subject} is not canonical JSON")
    return value


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    del value
    raise ValueError("non-finite JSON number")


def _directory_entries(descriptor: int) -> set[str]:
    try:
        entries = os.listdir(descriptor)
    except OSError:
        raise PrivateArtifactError("unable to inspect private episode entries") from None
    if any(not isinstance(entry, str) for entry in entries):
        raise PrivateArtifactError("private episode contains an invalid entry name")
    return set(entries)


def _entry_metadata(directory_descriptor: int, filename: str) -> os.stat_result | None:
    try:
        return os.stat(
            filename,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    except OSError:
        raise PrivateArtifactError("unable to inspect a private episode entry") from None


def _fstat(descriptor: int, *, subject: str) -> os.stat_result:
    try:
        return os.fstat(descriptor)
    except OSError:
        raise PrivateArtifactError(f"unable to inspect the {subject}") from None


def _same_file(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _directory_read_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _regular_file_read_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return flags


def _validate_root_location(
    root: str | Path,
    *,
    repository_root: str | Path,
    allow_same_device: bool,
    device_id: DeviceId,
    git_worktree_probe: GitWorktreeProbe,
) -> tuple[Path, Path]:
    raw_root = Path(root)
    if not raw_root.is_absolute():
        raise PrivateArtifactError("private root must be an explicit absolute path")
    normalized_root = Path(os.path.abspath(raw_root))
    _ensure_no_symlink_components(normalized_root)
    if not _is_directory(normalized_root, subject="private root"):
        raise PrivateArtifactError("private root must already exist as a directory")

    raw_repository = Path(repository_root)
    if not raw_repository.is_absolute():
        raise PrivateArtifactError("repository root must be an explicit absolute path")
    normalized_repository = Path(os.path.abspath(raw_repository))
    if not _is_directory(normalized_repository, subject="repository root"):
        raise PrivateArtifactError("repository root must exist as a directory")

    resolved_root = _resolve_directory(normalized_root, subject="private root")
    resolved_repository = _resolve_directory(
        normalized_repository,
        subject="repository root",
    )
    if _contains(resolved_repository, resolved_root) or _contains(
        resolved_root, resolved_repository
    ):
        raise PrivateArtifactError("private root must be outside the repository tree")

    try:
        inside_worktree = git_worktree_probe(resolved_root)
    except Exception as error:
        raise PrivateArtifactError("unable to verify Git-worktree isolation") from error
    if inside_worktree:
        raise PrivateArtifactError("private root must not be inside a Git worktree")

    if not allow_same_device:
        try:
            same_device = device_id(resolved_root) == device_id(resolved_repository)
        except Exception as error:
            raise PrivateArtifactError("unable to verify storage-device isolation") from error
        if same_device:
            raise PrivateArtifactError(
                "private root must be on a different storage device by default"
            )
    return resolved_root, resolved_repository


def _validate_sentinel(root: Path) -> None:
    sentinel = root / PRIVATE_ROOT_SENTINEL
    try:
        metadata = sentinel.lstat()
    except FileNotFoundError as error:
        raise PrivateArtifactError("private root sentinel is absent") from error
    except OSError as error:
        raise PrivateArtifactError("private root sentinel cannot be inspected") from error
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise PrivateArtifactError("private root sentinel is not a regular file")
    try:
        contents = sentinel.read_bytes()
    except OSError as error:
        raise PrivateArtifactError("private root sentinel cannot be read") from error
    if contents != _SENTINEL_BYTES:
        raise PrivateArtifactError("private root sentinel failed validation")


def _ensure_no_symlink_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError as error:
            raise PrivateArtifactError("private root must already exist as a directory") from error
        except OSError as error:
            raise PrivateArtifactError("private root component cannot be inspected") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise PrivateArtifactError("private root must not contain symbolic-link components")


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _lexists(path: Path) -> bool:
    try:
        return os.path.lexists(path)
    except OSError as error:
        raise PrivateArtifactError("unable to inspect a private artifact") from error


def _is_directory(path: Path, *, subject: str) -> bool:
    try:
        return path.is_dir()
    except OSError as error:
        raise PrivateArtifactError(f"{subject} cannot be inspected") from error


def _resolve_directory(path: Path, *, subject: str) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError as error:
        raise PrivateArtifactError(f"{subject} cannot be resolved") from error


def _validate_episode_id(episode_id: str) -> None:
    if not isinstance(episode_id, str) or not _SAFE_NAME.fullmatch(episode_id):
        raise PrivateArtifactError("episode id must be a safe lowercase identifier")
    if episode_id.endswith((".partial", ".failed")):
        raise PrivateArtifactError("episode id uses a reserved suffix")


def _validate_artifact_id(artifact_id: str) -> None:
    if not isinstance(artifact_id, str) or not _SAFE_NAME.fullmatch(artifact_id):
        raise PrivateArtifactError("artifact id must be a safe lowercase identifier")
    if artifact_id.endswith((".partial", ".failed")):
        raise PrivateArtifactError("artifact id uses a reserved suffix")


def _validate_artifact_kind(kind: str) -> None:
    if not isinstance(kind, str) or not _SAFE_KIND.fullmatch(kind):
        raise PrivateArtifactError("artifact kind must be a safe lowercase identifier")


def _validate_stream_name(stream: str) -> None:
    if not isinstance(stream, str) or not _SAFE_STREAM.fullmatch(stream):
        raise PrivateArtifactError("stream name must be a safe lowercase identifier")
    if stream == "manifest":
        raise PrivateArtifactError("manifest is a reserved stream name")


def _is_trajectory_episode_header(
    stream: str,
    record: Mapping[str, object],
) -> bool:
    return (
        stream == "episode"
        and set(record) == {
            "record_type",
            "trajectory_schema",
            "episode_id",
            "game_id",
            "metadata",
        }
        and record.get("record_type") == "episode"
        and record.get("trajectory_schema") == "pokemon.trajectory.v1"
        and isinstance(record.get("metadata"), Mapping)
        and is_runtime_identity_public_document(record["metadata"].get("runtime"))
    )


def _is_runtime_inventory_name_field(path_tokens: tuple[str | int, ...]) -> bool:
    return (
        len(path_tokens) == 6
        and path_tokens[:4] == ("metadata", "runtime", "pyboy", "files")
        and type(path_tokens[4]) is int  # noqa: E721
        and path_tokens[5] == "name"
    )


def _canonical_record(
    record: Mapping[str, object],
    *,
    allow_runtime_inventory_names: bool = False,
) -> bytes:
    if not isinstance(record, Mapping):
        raise PrivateArtifactError("episode records must be JSON objects")
    normalized = _normalize_json(
        record,
        path_tokens=(),
        allow_runtime_inventory_names=allow_runtime_inventory_names,
    )
    if not isinstance(normalized, dict):
        raise PrivateArtifactError("episode records must be JSON objects")
    return _canonical_json_line(normalized)


def _normalize_json(
    value: object,
    *,
    path_tokens: tuple[str | int, ...],
    allow_runtime_inventory_names: bool,
) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PrivateArtifactError("episode records require finite numeric values")
        return value
    if isinstance(value, str):
        if not (
            allow_runtime_inventory_names
            and _is_runtime_inventory_name_field(path_tokens)
            and is_canonical_distribution_inventory_name(value)
        ):
            _reject_path_text(value)
        return value
    if isinstance(value, os.PathLike):
        raise PrivateArtifactError("episode records may not contain filesystem paths")
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PrivateArtifactError("episode record keys must be strings")
            _reject_path_key(key)
            normalized[key] = _normalize_json(
                item,
                path_tokens=(*path_tokens, key),
                allow_runtime_inventory_names=allow_runtime_inventory_names,
            )
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [
            _normalize_json(
                item,
                path_tokens=(*path_tokens, index),
                allow_runtime_inventory_names=allow_runtime_inventory_names,
            )
            for index, item in enumerate(value)
        ]
    raise PrivateArtifactError("episode records contain a non-JSON value")


def _reject_path_key(key: str) -> None:
    lowered = key.casefold().replace("-", "_")
    if (
        lowered in _PATH_KEYS
        or lowered.endswith(("_directory", "_filename", "_filepath", "_path"))
        or "/" in key
        or "\\" in key
    ):
        raise PrivateArtifactError("episode records may not contain filesystem path fields")


def _reject_path_text(value: str) -> None:
    if (
        "/" in value
        or "\\" in value
        or value.startswith("~")
        or value.casefold().startswith("file:")
        or _WINDOWS_DRIVE_PATH.search(value)
    ):
        raise PrivateArtifactError("episode records may not contain filesystem paths")


def _canonical_json_line(value: Mapping[str, object]) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise PrivateArtifactError("unable to encode a canonical JSON record") from error
    return rendered.encode("ascii") + b"\n"


def _rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename ``source`` only when ``destination`` is absent.

    Plain POSIX ``rename`` may replace an existing empty directory. Publication
    requires a kernel-enforced no-replace primitive; unsupported platforms fail
    closed instead of falling back to a check-then-rename sequence.
    """
    encoded_source = os.fsencode(source)
    encoded_destination = os.fsencode(destination)
    if sys.platform == "darwin":
        _rename_no_replace_darwin(encoded_source, encoded_destination)
        return
    if sys.platform.startswith("linux"):
        _rename_no_replace_linux(encoded_source, encoded_destination)
        return
    if os.name == "nt":
        # Python's Windows rename uses MoveFile semantics and raises when the
        # destination already exists; it does not replace it.
        os.rename(source, destination)
        return
    raise OSError(
        errno.ENOTSUP,
        "atomic no-replace rename is unsupported on this platform",
    )


def _rename_no_replace_darwin(source: bytes, destination: bytes) -> None:
    rename_exclusive = 0x00000004
    try:
        library = ctypes.CDLL(None, use_errno=True)
        rename = library.renamex_np
    except (AttributeError, OSError):
        raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable") from None
    rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    ctypes.set_errno(0)
    if rename(source, destination, rename_exclusive) == 0:
        return
    error_number = ctypes.get_errno() or errno.EIO
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, "destination already exists")
    raise OSError(error_number, os.strerror(error_number))


def _rename_no_replace_linux(source: bytes, destination: bytes) -> None:
    at_current_working_directory = -100
    rename_no_replace = 1
    try:
        library = ctypes.CDLL(None, use_errno=True)
        rename = library.renameat2
    except (AttributeError, OSError):
        raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable") from None
    rename.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    rename.restype = ctypes.c_int
    ctypes.set_errno(0)
    if (
        rename(
            at_current_working_directory,
            source,
            at_current_working_directory,
            destination,
            rename_no_replace,
        )
        == 0
    ):
        return
    error_number = ctypes.get_errno() or errno.EIO
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, "destination already exists")
    raise OSError(error_number, os.strerror(error_number))


def _write_exclusive_file(path: Path, payload: bytes, *, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags, mode)
    except FileExistsError as error:
        raise PrivateArtifactError(
            "private artifact already exists; refusing to overwrite"
        ) from error
    except OSError as error:
        raise PrivateArtifactError("unable to create a private artifact") from error
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise PrivateArtifactError("unable to persist a private artifact") from error
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as error:
                raise PrivateArtifactError("unable to close a private artifact") from error


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise PrivateArtifactError("unable to hash a private episode stream") from error
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise PrivateArtifactError("unable to open a private artifact directory") from error
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise PrivateArtifactError("unable to synchronize a private artifact directory") from error
    finally:
        try:
            os.close(descriptor)
        except OSError as error:
            raise PrivateArtifactError("unable to close a private artifact directory") from error


def _default_device_id(path: Path) -> int:
    return path.stat().st_dev


def _default_git_worktree_probe(path: Path) -> bool:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PrivateArtifactError("Git-worktree check could not run") from error
    if completed.returncode == 0:
        return completed.stdout.strip() == b"true"
    return False
