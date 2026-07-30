from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import subprocess
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PRIVATE_ROOT_SENTINEL = ".pokemon-red-completion-private-root.json"
PRIVATE_ROOT_FORMAT = "pokemon-red-completion-private-root"
EPISODE_FORMAT = "pokemon-red-completion-episode-jsonl"
PRIVATE_ARTIFACT_SCHEMA_VERSION = 1

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
_SAFE_STREAM = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_SAFE_REASON = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
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

    def begin_episode(self, episode_id: str) -> EpisodeWriter:
        """Create a new, exclusive partial episode.

        An existing final, partial, or failed artifact is never reused or overwritten.
        """
        _validate_episode_id(episode_id)
        self._revalidate()

        partial = self._root / f"{episode_id}.partial"
        final = self._root / episode_id
        failed = self._root / f"{episode_id}.failed.partial"
        if any(_lexists(candidate) for candidate in (partial, final, failed)):
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

        return EpisodeWriter(
            episode_id=episode_id,
            partial=partial,
            final=final,
            failed=failed,
        )

    def _revalidate(self) -> None:
        _validate_root_location(
            self._root,
            repository_root=self._repository_root,
            allow_same_device=self._allow_same_device,
            device_id=self._device_id,
            git_worktree_probe=self._git_worktree_probe,
        )
        _validate_sentinel(self._root)


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

    def append(self, stream: str, record: Mapping[str, object]) -> None:
        """Append one canonical JSON object to a named JSONL stream."""
        self._require_active()
        _validate_stream_name(stream)
        payload = _canonical_record(record)

        target = self._streams.get(stream)
        if target is None:
            target = self._open_stream(stream)
            self._streams[stream] = target
        try:
            target.handle.write(payload)
        except OSError as error:
            raise PrivateArtifactError("unable to write a private episode record") from error
        target.records += 1

    def complete(self) -> EpisodeSummary:
        """Write the manifest last and atomically publish the completed directory."""
        self._require_active()
        summary = self._finalize(status="complete", reason_code=None)
        if _lexists(self._final):
            raise PrivateArtifactError("completed episode already exists; refusing to overwrite")
        try:
            os.rename(self._partial, self._final)
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
        summary = self._finalize(status="failed", reason_code=reason_code)
        if _lexists(self._failed):
            raise PrivateArtifactError("failed episode already exists; refusing to overwrite")
        try:
            os.rename(self._partial, self._failed)
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
            raise PrivateArtifactError(
                "unable to retain the failed private episode without overwriting"
            )
        try:
            os.rename(manifest, unpublished_manifest)
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
            os.rename(self._partial, self._failed)
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


def _validate_stream_name(stream: str) -> None:
    if not isinstance(stream, str) or not _SAFE_STREAM.fullmatch(stream):
        raise PrivateArtifactError("stream name must be a safe lowercase identifier")
    if stream == "manifest":
        raise PrivateArtifactError("manifest is a reserved stream name")


def _canonical_record(record: Mapping[str, object]) -> bytes:
    if not isinstance(record, Mapping):
        raise PrivateArtifactError("episode records must be JSON objects")
    normalized = _normalize_json(record)
    if not isinstance(normalized, dict):
        raise PrivateArtifactError("episode records must be JSON objects")
    return _canonical_json_line(normalized)


def _normalize_json(value: object) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PrivateArtifactError("episode records require finite numeric values")
        return value
    if isinstance(value, str):
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
            normalized[key] = _normalize_json(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_normalize_json(item) for item in value]
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
