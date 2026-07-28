from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

GIT_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")


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


def _git_output(root: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()
