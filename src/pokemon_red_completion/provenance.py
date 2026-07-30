from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import selectors
import subprocess
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

GIT_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")
_GIT_OUTPUT_LIMIT_BYTES = 1024 * 1024
_GIT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    git_commit: str | None
    worktree_dirty: bool | None

    def public_dict(self) -> dict[str, str | bool]:
        return {
            "git_commit": self.git_commit or "unknown",
            "worktree_dirty": (
                self.worktree_dirty if self.worktree_dirty is not None else "unknown"
            ),
        }


@dataclass(frozen=True, slots=True)
class EvaluationIdentity:
    """Public identity of everything allowed to influence an evaluation."""

    schema_version: int
    source: SourceIdentity
    python_version: str
    rom_sha1: str
    rom_sha256: str
    objective_graph_sha256: str
    configuration_sha256: str
    model_sha256: tuple[str, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["source"] = self.source.public_dict()
        result["model_sha256"] = list(self.model_sha256)
        return result


class EvaluationIdentityError(RuntimeError):
    """Raised when an official evaluation cannot prove a frozen identity."""


def detect_source_identity(
    project_root: Path,
    *,
    include_untracked: bool = True,
) -> SourceIdentity:
    commit = _git_output(project_root, "rev-parse", "HEAD")
    if commit is None or GIT_COMMIT.fullmatch(commit) is None:
        return SourceIdentity(None, None)

    status = _git_output(
        project_root,
        "status",
        "--porcelain",
        "--untracked-files=all" if include_untracked else "--untracked-files=no",
    )
    return SourceIdentity(commit, None if status is None else bool(status))


def require_clean_source(identity: SourceIdentity) -> None:
    if identity.git_commit is None or identity.worktree_dirty is None:
        raise EvaluationIdentityError("Source identity is unavailable.")
    if identity.worktree_dirty:
        raise EvaluationIdentityError("Official evaluation requires a clean worktree.")


def require_published_source(project_root: Path, identity: SourceIdentity) -> None:
    """Require the exact clean commit to be reachable from a remote-tracking ref."""

    require_clean_source(identity)
    commit = identity.git_commit
    if commit is None:  # pragma: no cover - require_clean_source establishes this
        raise AssertionError("clean source identity has no commit")
    refs = _git_output(
        project_root,
        "for-each-ref",
        f"--contains={commit}",
        "--format=%(refname)",
        "refs/remotes",
    )
    if refs is None:
        raise EvaluationIdentityError("Published source identity is unavailable.")
    published_refs = tuple(
        ref
        for ref in refs.splitlines()
        if ref.startswith("refs/remotes/") and not ref.endswith("/HEAD")
    )
    if not published_refs:
        raise EvaluationIdentityError(
            "Scheduled collection requires the exact source commit to be pushed."
        )


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_evaluation_identity(
    *,
    source: SourceIdentity,
    rom_sha1: str,
    rom_sha256: str,
    objective_graph: object,
    configuration: object,
    model_paths: tuple[Path, ...] = (),
) -> EvaluationIdentity:
    require_clean_source(source)
    return EvaluationIdentity(
        schema_version=1,
        source=source,
        python_version=platform.python_version(),
        rom_sha1=rom_sha1,
        rom_sha256=rom_sha256,
        objective_graph_sha256=canonical_sha256(objective_graph),
        configuration_sha256=canonical_sha256(configuration),
        model_sha256=tuple(file_sha256(path) for path in model_paths),
    )


def _sanitized_git_environment() -> dict[str, str]:
    """Return a deterministic read-only Git environment for identity checks."""

    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LANG": "C",
            "LC_ALL": "C",
        }
    )
    return environment


def _git_output(
    root: Path,
    *arguments: str,
    maximum_output_bytes: int = _GIT_OUTPUT_LIMIT_BYTES,
) -> str | None:
    """Read bounded Git output, returning ``None`` on every ambiguous failure."""

    if (
        isinstance(maximum_output_bytes, bool)
        or not isinstance(maximum_output_bytes, int)
        or maximum_output_bytes <= 0
    ):
        return None
    try:
        resolved_root = Path(root).resolve(strict=True)
    except (OSError, RuntimeError, TypeError):
        return None
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    try:
        process = subprocess.Popen(
            [
                "git",
                "--no-replace-objects",
                f"--work-tree={resolved_root}",
                *arguments,
            ],
            cwd=resolved_root,
            env=_sanitized_git_environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if process.stdout is None:  # pragma: no cover - Popen contract
            return None
        os.set_blocking(process.stdout.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + _GIT_TIMEOUT_SECONDS
        chunks: list[bytes] = []
        total = 0
        eof = False
        while not eof:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            for key, _mask in selector.select(min(remaining, 0.25)):
                try:
                    chunk = os.read(
                        key.fileobj.fileno(),
                        min(64 * 1024, maximum_output_bytes - total + 1),
                    )
                except BlockingIOError:
                    continue
                if not chunk:
                    eof = True
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > maximum_output_bytes:
                    return None
        remaining = max(0.001, deadline - time.monotonic())
        if process.wait(timeout=remaining) != 0:
            return None
        try:
            return b"".join(chunks).decode("utf-8").strip()
        except UnicodeDecodeError:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        if selector is not None:
            selector.close()
        if process is not None and process.poll() is None:
            process.kill()
            with suppress(OSError, subprocess.SubprocessError):
                process.wait(timeout=1)
