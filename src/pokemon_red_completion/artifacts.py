from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

PRIVATE_SUFFIXES = {
    ".gb",
    ".gbc",
    ".gba",
    ".sav",
    ".ram",
    ".rtc",
    ".state",
    ".ckpt",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
}
PRIVATE_DIRECTORY_NAMES = {
    ".git",
    ".venv",
    "checkpoints",
    "datasets",
    "recordings",
    "roms",
    "runs",
    "saves",
    "savestates",
    "screenshots",
    "videos",
}
TEXT_SUFFIXES = {
    ".cff",
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PLACEHOLDER_USERNAMES = {"example", "runner", "user", "username"}
PRIVATE_HOME_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:/(?:Users|home)/(?P<posix>[A-Za-z0-9._-]+)/|"
    r"[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]"
    r"(?P<windows>[A-Za-z0-9._-]+)[\\/])"
)
SECRET_PATTERNS = {
    "GitHub token": re.compile(r"gh[opsu]_[A-Za-z0-9]{20,}"),
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
}


@dataclass(frozen=True, slots=True)
class ArtifactViolation:
    path: str
    reason: str


def inspect_public_tree(root: Path) -> tuple[ArtifactViolation, ...]:
    """Inspect a candidate public tree without following links or reading binary payloads."""
    violations: list[ArtifactViolation] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in PRIVATE_DIRECTORY_NAMES for part in relative.parts[:-1]):
            continue
        violations.extend(_inspect_path(path, relative))
    return tuple(violations)


def inspect_tracked_tree(root: Path) -> tuple[ArtifactViolation, ...]:
    """Inspect every Git-tracked file, including files force-added under ignored directories."""
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
        timeout=5,
    )
    if completed.returncode != 0:
        return ()

    violations: list[ArtifactViolation] = []
    for raw_relative in completed.stdout.split(b"\0"):
        if not raw_relative:
            continue
        relative = Path(raw_relative.decode("utf-8"))
        violations.extend(_inspect_path(root / relative, relative))
    return tuple(violations)


def _inspect_path(path: Path, relative: Path) -> list[ArtifactViolation]:
    violations: list[ArtifactViolation] = []
    if path.is_symlink():
        return [ArtifactViolation(str(relative), "symbolic links are not publishable")]
    if not path.is_file():
        return violations
    if path.suffix.lower() in PRIVATE_SUFFIXES:
        return [ArtifactViolation(str(relative), "private artifact suffix")]
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
        ".env.example",
        ".gitignore",
        "LICENSE",
    }:
        return violations
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [ArtifactViolation(str(relative), "non-text public artifact")]
    for reason in sensitive_text_reasons(text):
        violations.append(ArtifactViolation(str(relative), reason))
    return violations


def sensitive_text_reasons(text: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for match in PRIVATE_HOME_PATH.finditer(text):
        username = (match.group("posix") or match.group("windows")).lower()
        if username not in PLACEHOLDER_USERNAMES:
            reasons.append("private home-directory path")
            break
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            reasons.append(label)
    return tuple(reasons)
