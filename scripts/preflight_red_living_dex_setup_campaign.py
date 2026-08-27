#!/usr/bin/env python3
"""Authenticate the frozen Red setup plan without opening setup authority.

This bridge authenticates the exact immutable provider-plan record against its
tracked canonical receipt, verifies every static cartridge and execution-
identity join, rejoins the selected state/envelope bytes without restoring a
cartridge state, and checks that both logical and physical account-wide root
claims remain unused.  It deliberately has no emulator construction, setup-arm
factory, campaign runner, claim writer, controller executor, teacher, learner,
scorer, or fitter.

The command is a publication-disabled pre-controller rehearsal.  The prepared
object is internal and ephemeral; the qualified CLI surface emits only
path-free aggregates and immutable digests.
"""

# ruff: noqa: E402, I001 -- secure OpenSSL before imports; pin project roots.

from __future__ import annotations

import sys

_EARLY_BOOTSTRAP_FAILURE_JSON = (
    '{"controller_actions":0,"emulator_frames":0,"model_fits":0,'
    '"model_predictions":0,"outcomes":0,"private_identity_fields":0,'
    '"private_path_fields":0,"provider_executions":0,"root_claims":0,'
    '"schema":"pokemon.red.living-dex-setup-bridge-precontroller-failure.v1",'
    '"setup_campaign_calls":0,"setup_runtime_factory_calls":0,'
    '"stage":"bootstrap_source_authentication","status":"failed_closed",'
    '"teacher_queries":0}\n'
)
if __name__ == "__main__" and (
    sys.flags.debug != 0
    or sys.flags.inspect != 0
    or sys.flags.interactive != 0
    or sys.flags.optimize != 0
    or sys.flags.dont_write_bytecode != 1
    or sys.flags.no_user_site != 1
    or sys.flags.no_site != 1
    or sys.flags.ignore_environment != 1
    or sys.flags.verbose != 0
    or sys.flags.bytes_warning != 0
    or sys.flags.quiet != 0
    or sys.flags.hash_randomization != 1
    or sys.flags.isolated != 1
    or sys.flags.dev_mode is not False
    or sys.flags.utf8_mode != 0
    or sys.flags.warn_default_encoding != 0
    or sys.flags.safe_path is not True
    or sys.flags.int_max_str_digits != 4300
    or sys.pycache_prefix is not None
    or bool(sys._xoptions)
    or bool(sys.warnoptions)
):
    sys.stdout.write(_EARLY_BOOTSTRAP_FAILURE_JSON)
    raise SystemExit(1)

import os

if any(
    (
        (key.startswith("OPENSSL_") and not (key == "OPENSSL_CONF" and value == os.devnull))
        or key in {"CTLOG_FILE", "RANDFILE"}
    )
    for key, value in os.environ.items()
    if value.strip()
):
    os.write(1, _EARLY_BOOTSTRAP_FAILURE_JSON.encode("ascii"))
    raise SystemExit(1)
os.environ["OPENSSL_CONF"] = os.devnull

import argparse
import fcntl
import hashlib
import json
import platform
import re
import runpy
import stat
import subprocess
from collections import Counter
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field, replace
from importlib import metadata as importlib_metadata
from pathlib import Path
from types import FunctionType, MappingProxyType, ModuleType
from typing import Any, Literal, Never, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = Path(__file__).resolve()
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
_BRIDGE_SCRIPT_RELATIVE_PATH = "scripts/preflight_red_living_dex_setup_campaign.py"
_CANONICAL_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-provider-plan-freeze-result-v1-2026-08-26.json"
)
_CANONICAL_EVIDENCE_SHA256 = (
    "c317b258138e703a1afd532e77d3b71fec07bb1f856bb11afbbfd37479ba3ded"
)
_BOOTSTRAP_FAILURE_SCHEMA = (
    "pokemon.red.living-dex-setup-bridge-precontroller-failure.v1"
)
_BOOTSTRAP_MAX_GIT_BYTES = 128 * 1024 * 1024
_BOOTSTRAP_IDENTITY: tuple[str, str, str] | None = None
_BOOTSTRAP_DEPENDENCY_METADATA_ROOTS: tuple[Path, ...] = ()
_BOOTSTRAP_PYTHON_EXECUTABLE = Path(
    "/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/"
    "Python.framework/Versions/3.14/bin/python3.14"
)
_BOOTSTRAP_PYTHON_EXECUTABLE_SHA256 = (
    "cbf84109626aa1013bbe408fbb9590bd0f1c1548f038b2221c6b8b87de26ca43"
)
_BOOTSTRAP_BASE_PREFIX = Path(
    "/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/"
    "Python.framework/Versions/3.14"
)
_BOOTSTRAP_DEPENDENCY_METADATA_ROOT = (
    PROJECT_ROOT / ".venv/lib/python3.14/site-packages"
)
_BOOTSTRAP_USAGE = (
    f"usage: {_BOOTSTRAP_PYTHON_EXECUTABLE} -I -S -B "
    "scripts/preflight_red_living_dex_setup_campaign.py [options]\n"
    "Authenticate the frozen Red setup plan without runtime, claims, or gameplay."
)
_BOOTSTRAP_GIT_EXECUTABLE = Path(
    "/Library/Developer/CommandLineTools/usr/bin/git"
)
_BOOTSTRAP_GIT_EXECUTABLE_SHA256 = (
    "74b90b9f97ec79bfe7886a4fc6132533b3e1014ef4195d28abd1ca9bf321f34a"
)
_BOOTSTRAP_GIT_CONFIG_OVERRIDES = (
    "-c",
    "core.attributesFile=/dev/null",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
)
_BOOTSTRAP_PROJECT_GIT_CONFIG_OVERRIDES = (
    "-c",
    "core.bare=false",
    *_BOOTSTRAP_GIT_CONFIG_OVERRIDES,
    "-c",
    f"core.worktree={PROJECT_ROOT}",
)
_BOOTSTRAP_CA_BUNDLE = Path("/opt/homebrew/etc/ca-certificates/cert.pem")
_BOOTSTRAP_CA_BUNDLE_SHA256 = (
    "e0547ad4423c097fa7a9ba57464634a7ed331072a49cfbcad8fcc396bbc7bb15"
)
_BOOTSTRAP_PYBOY_METADATA_DIRECTORY = "pyboy-2.7.0.dist-info"
_BOOTSTRAP_PYBOY_METADATA_SHA256 = MappingProxyType(
    {
        "INSTALLER": (
            "ceebae7b8927a3227e5303cf5e0f1f7b34bb542ad7250ac03fbcde36ec2f1508"
        ),
        "METADATA": (
            "5b5699f2da10c24e161420ce2c90d60e2b21dba606451e4347afb0ee3780a378"
        ),
        "RECORD": (
            "1dd1f07936aee27a9f23c845b216651853e0d877fdeb1cd77424b409defcd75d"
        ),
        "WHEEL": (
            "5468e9e32c3c96df8c0462d3cd7260bc03df9f6830cbc1b4e63334c6ca0be6da"
        ),
        "entry_points.txt": (
            "9461da2d0fbe0f69a78e8a64a89bf32047ba6650d04802d612dcf0e6a5117af8"
        ),
        "licenses/LICENSE.md": (
            "a27d3e242d91483cc55cd35a3605aaeac2d9a6df7c06a5ffe24eabc9e0ec9d17"
        ),
        "top_level.txt": (
            "f42943e1d79f5d2a2f7c41bab3a7c67c8688660ec3e57119290f97716021f89a"
        ),
    }
)
_CI_WORKFLOW_RELATIVE_PATH = ".github/workflows/ci.yml"
_BOOTSTRAP_EXPECTED_SCRIPT_DELTA = f"A\t{_BRIDGE_SCRIPT_RELATIVE_PATH}\n"
_BOOTSTRAP_ALLOWED_LOCAL_METADATA_SHA256 = MappingProxyType(
    {
        "src/pokemon_red_completion_agent.egg-info/PKG-INFO": (
            "abc1702c48fa05493e728bbaa081765d889df40b424cf2ff5208b65544a3df25"
        ),
        "src/pokemon_red_completion_agent.egg-info/SOURCES.txt": (
            "131ce2babee8e4ae36dae5143ae91f95e160dd9266268a49cfe9d7fbb343a1e2"
        ),
        "src/pokemon_red_completion_agent.egg-info/dependency_links.txt": (
            "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b"
        ),
        "src/pokemon_red_completion_agent.egg-info/entry_points.txt": (
            "ff55e5095e16b6c96ebf68a4f862467a715d2270e1831a27932b715f3500715f"
        ),
        "src/pokemon_red_completion_agent.egg-info/requires.txt": (
            "9c6e01476b85a4ea20686f1da12b9fc07745b08824eb5f462456083bce690e49"
        ),
        "src/pokemon_red_completion_agent.egg-info/top_level.txt": (
            "d4ef837deeb515b1de375c0eac87f3eb1ae11dc09b08c04b2236032b6a484a45"
        ),
    }
)


class _BootstrapAuthenticationError(RuntimeError):
    """The stdlib-only import boundary could not authenticate exact source."""


def _minimal_git_environment() -> dict[str, str]:
    """Return the complete, allowlisted environment for every Git child."""

    return {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }


def _bootstrap_git_directory() -> Path:
    """Resolve this exact worktree's Git directory without consulting Git."""

    marker = PROJECT_ROOT / ".git"
    try:
        metadata = marker.lstat()
        if marker.is_symlink() or metadata.st_uid != os.getuid():
            raise _BootstrapAuthenticationError
        if stat.S_ISDIR(metadata.st_mode):
            git_directory = marker
        elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
            payload = _bootstrap_read_regular(marker, maximum_bytes=4096)
            line = payload.decode("ascii", errors="strict")
            if not line.endswith("\n") or line.count("\n") != 1:
                raise _BootstrapAuthenticationError
            prefix = "gitdir: "
            raw_directory = line.removesuffix("\n")
            if not raw_directory.startswith(prefix):
                raise _BootstrapAuthenticationError
            git_directory = Path(raw_directory.removeprefix(prefix))
        else:
            raise _BootstrapAuthenticationError
        resolved = git_directory.resolve(strict=True)
        resolved_metadata = resolved.lstat()
        if (
            not git_directory.is_absolute()
            or git_directory.is_symlink()
            or resolved != git_directory
            or not stat.S_ISDIR(resolved_metadata.st_mode)
            or resolved_metadata.st_uid != os.getuid()
            or stat.S_IMODE(resolved_metadata.st_mode) & 0o022
        ):
            raise _BootstrapAuthenticationError
        return resolved
    except (OSError, UnicodeDecodeError):
        raise _BootstrapAuthenticationError from None


def _bootstrap_git_common_directory(git_directory: Path) -> Path:
    """Resolve the common object/config directory for a linked worktree."""

    marker = git_directory / "commondir"
    try:
        metadata = marker.lstat()
    except FileNotFoundError:
        return git_directory
    except OSError:
        raise _BootstrapAuthenticationError from None
    if (
        marker.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise _BootstrapAuthenticationError
    try:
        line = _bootstrap_read_regular(marker, maximum_bytes=256).decode(
            "ascii",
            errors="strict",
        )
    except UnicodeDecodeError:
        raise _BootstrapAuthenticationError from None
    if not line.endswith("\n") or line.count("\n") != 1:
        raise _BootstrapAuthenticationError
    relative = Path(line.removesuffix("\n"))
    if (
        relative.is_absolute()
        or not relative.parts
        or len(relative.parts) > 4
        or any(part != ".." for part in relative.parts)
    ):
        raise _BootstrapAuthenticationError
    try:
        common = (git_directory / relative).resolve(strict=True)
        common_metadata = common.lstat()
    except OSError:
        raise _BootstrapAuthenticationError from None
    if (
        common.is_symlink()
        or not stat.S_ISDIR(common_metadata.st_mode)
        or common_metadata.st_uid != os.getuid()
        or stat.S_IMODE(common_metadata.st_mode) & 0o022
    ):
        raise _BootstrapAuthenticationError
    return common


def _bootstrap_reject_index_attributes() -> None:
    """Read only index pathnames and reject staged attribute fallbacks."""

    _bootstrap_require_executable(
        _BOOTSTRAP_GIT_EXECUTABLE,
        expected_sha256=_BOOTSTRAP_GIT_EXECUTABLE_SHA256,
        require_root_owned_path=True,
    )
    try:
        completed = subprocess.run(
            (
                str(_BOOTSTRAP_GIT_EXECUTABLE),
                f"--git-dir={_bootstrap_git_directory()}",
                f"--work-tree={PROJECT_ROOT}",
                "--no-replace-objects",
                *_BOOTSTRAP_PROJECT_GIT_CONFIG_OVERRIDES,
                "ls-files",
                "-z",
                "--cached",
            ),
            cwd=PROJECT_ROOT,
            env=_minimal_git_environment(),
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        raise _BootstrapAuthenticationError from None
    if completed.returncode != 0 or len(completed.stdout) > 16 * 1024 * 1024:
        raise _BootstrapAuthenticationError
    seen: set[str] = set()
    for raw_path in completed.stdout.split(b"\0"):
        if not raw_path:
            continue
        try:
            relative = raw_path.decode("ascii", errors="strict")
        except UnicodeDecodeError:
            raise _BootstrapAuthenticationError from None
        path = Path(relative)
        if (
            relative in seen
            or path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.name.casefold() == ".gitattributes"
        ):
            raise _BootstrapAuthenticationError
        seen.add(relative)


def _authenticate_git_attribute_boundary() -> None:
    """Reject repository attributes before Git can invoke a content driver."""

    global _BOOTSTRAP_GIT_ATTRIBUTES_AUTHENTICATED
    _BOOTSTRAP_GIT_ATTRIBUTES_AUTHENTICATED = False
    git_directory = _bootstrap_git_directory()
    common_directory = _bootstrap_git_common_directory(git_directory)
    for directory in {git_directory, common_directory}:
        try:
            (directory / "info/attributes").lstat()
        except FileNotFoundError:
            pass
        except OSError:
            raise _BootstrapAuthenticationError from None
        else:
            raise _BootstrapAuthenticationError

    excluded_directories = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
    }

    def fail_walk(_error: OSError) -> Never:
        raise _BootstrapAuthenticationError

    try:
        for raw_root, directories, files in os.walk(
            PROJECT_ROOT,
            topdown=True,
            onerror=fail_walk,
            followlinks=False,
        ):
            root = Path(raw_root)
            directories[:] = [
                name
                for name in directories
                if name not in excluded_directories
                and not (root / name).is_symlink()
            ]
            if any(name.casefold() == ".gitattributes" for name in files):
                raise _BootstrapAuthenticationError
    except _BootstrapAuthenticationError:
        raise
    except BaseException:
        raise _BootstrapAuthenticationError from None
    _bootstrap_reject_index_attributes()
    _BOOTSTRAP_GIT_ATTRIBUTES_AUTHENTICATED = True


def _bootstrap_git_bytes(
    arguments: tuple[str, ...],
    *,
    maximum_bytes: int = _BOOTSTRAP_MAX_GIT_BYTES,
) -> bytes:
    if maximum_bytes <= 0:
        raise _BootstrapAuthenticationError
    if not _BOOTSTRAP_GIT_ATTRIBUTES_AUTHENTICATED:
        raise _BootstrapAuthenticationError
    _bootstrap_require_executable(
        _BOOTSTRAP_GIT_EXECUTABLE,
        expected_sha256=_BOOTSTRAP_GIT_EXECUTABLE_SHA256,
        require_root_owned_path=True,
    )
    environment = _minimal_git_environment()
    try:
        completed = subprocess.run(
            (
                str(_BOOTSTRAP_GIT_EXECUTABLE),
                f"--git-dir={_bootstrap_git_directory()}",
                f"--work-tree={PROJECT_ROOT}",
                "--no-replace-objects",
                *_BOOTSTRAP_PROJECT_GIT_CONFIG_OVERRIDES,
                *arguments,
            ),
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        raise _BootstrapAuthenticationError from None
    if completed.returncode != 0 or len(completed.stdout) > maximum_bytes:
        raise _BootstrapAuthenticationError
    return completed.stdout


def _bootstrap_read_regular(
    path: Path,
    *,
    maximum_bytes: int,
    require_single_link: bool = True,
) -> bytes:
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        raise _BootstrapAuthenticationError from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or (require_single_link and metadata.st_nlink != 1)
        or metadata.st_size < 0
        or metadata.st_size > maximum_bytes
        or resolved != path
    ):
        raise _BootstrapAuthenticationError
    try:
        payload = path.read_bytes()
        final = path.lstat()
    except OSError:
        raise _BootstrapAuthenticationError from None
    if (
        len(payload) != metadata.st_size
        or final.st_dev != metadata.st_dev
        or final.st_ino != metadata.st_ino
        or final.st_size != metadata.st_size
        or final.st_mtime_ns != metadata.st_mtime_ns
        or final.st_ctime_ns != metadata.st_ctime_ns
    ):
        raise _BootstrapAuthenticationError
    return payload


def _bootstrap_require_executable(
    path: Path,
    *,
    expected_sha256: str,
    require_root_owned_path: bool = False,
) -> Path:
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.lstat()
    except OSError:
        raise _BootstrapAuthenticationError from None
    if (
        not resolved.is_absolute()
        or resolved.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or metadata.st_size <= 0
        or metadata.st_size > 128 * 1024 * 1024
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
    ):
        raise _BootstrapAuthenticationError
    if require_root_owned_path:
        try:
            for candidate in (resolved, *resolved.parents):
                candidate_metadata = candidate.lstat()
                if (
                    candidate_metadata.st_uid != 0
                    or stat.S_IMODE(candidate_metadata.st_mode) & 0o022
                ):
                    raise _BootstrapAuthenticationError
        except OSError:
            raise _BootstrapAuthenticationError from None
    payload = _bootstrap_read_regular(
        resolved,
        maximum_bytes=128 * 1024 * 1024,
        require_single_link=False,
    )
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise _BootstrapAuthenticationError
    return resolved


def _bootstrap_filesystem_src_root_inventory(
    project_root: Path,
    src_root: Path,
    expected_files: set[str],
    *,
    allowed_local_metadata_sha256: Mapping[str, str],
) -> set[str]:
    expected_directories = {
        parent.as_posix()
        for relative in expected_files
        for parent in Path(relative).parents
        if parent != Path(".") and parent != Path("src")
    }
    local_metadata_root = src_root / "pokemon_red_completion_agent.egg-info"
    local_metadata_present = False
    local_metadata_seen: set[str] = set()
    result: set[str] = set()
    try:
        for path in src_root.rglob("*"):
            relative = path.relative_to(project_root).as_posix()
            if path.is_symlink():
                raise _BootstrapAuthenticationError
            if path.is_dir():
                if path == local_metadata_root:
                    local_metadata_present = True
                    continue
                if relative in expected_directories:
                    continue
                if (
                    path.name == "__pycache__"
                    and path.parent.relative_to(project_root).as_posix()
                    in expected_directories
                ):
                    continue
                raise _BootstrapAuthenticationError
            if path.parent == local_metadata_root:
                expected_sha256 = allowed_local_metadata_sha256.get(relative)
                if expected_sha256 is None:
                    raise _BootstrapAuthenticationError
                payload = _bootstrap_read_regular(path, maximum_bytes=4 * 1024 * 1024)
                if hashlib.sha256(payload).hexdigest() != expected_sha256:
                    raise _BootstrapAuthenticationError
                local_metadata_seen.add(relative)
                continue
            if (
                path.parent.name == "__pycache__"
                and path.parent.parent.relative_to(project_root).as_posix()
                in expected_directories
                and path.suffix in {".pyc", ".pyo"}
            ):
                continue
            if path == src_root / ".DS_Store" and path.is_file():
                continue
            if not path.is_file():
                raise _BootstrapAuthenticationError
            result.add(relative)
    except (OSError, ValueError):
        raise _BootstrapAuthenticationError from None
    if local_metadata_present and local_metadata_seen != set(
        allowed_local_metadata_sha256
    ):
        raise _BootstrapAuthenticationError
    if result != expected_files:
        raise _BootstrapAuthenticationError
    return result


def _bootstrap_filesystem_script_inventory(
    project_root: Path,
    scripts_root: Path,
) -> set[str]:
    result: set[str] = set()
    try:
        for path in scripts_root.rglob("*"):
            relative = path.relative_to(project_root).as_posix()
            if path.is_symlink():
                raise _BootstrapAuthenticationError
            if path.is_dir():
                if path == scripts_root / "__pycache__":
                    continue
                raise _BootstrapAuthenticationError
            if path.parent == scripts_root / "__pycache__" and path.suffix in {
                ".pyc",
                ".pyo",
            }:
                continue
            if path == scripts_root / ".DS_Store" and path.is_file():
                continue
            if not path.is_file():
                raise _BootstrapAuthenticationError
            result.add(relative)
    except OSError:
        raise _BootstrapAuthenticationError from None
    return result


class _NumpyTypingPlaceholder:
    """Permit postponed typing imports while refusing numerical execution."""

    @classmethod
    def __class_getitem__(cls, _item: object) -> type[_NumpyTypingPlaceholder]:
        return cls


_NUMPY_SENTINEL: ModuleType | None = None
_NUMPY_TYPING_SENTINEL: ModuleType | None = None
_NUMPY_SENTINEL_ATTRIBUTE_ACCESSES = 0
_SSL_EXTENSION_MODULE: ModuleType | None = None
_SSL_MODULE: ModuleType | None = None
_URLLIB_REQUEST_MODULE: ModuleType | None = None
_ORIGINAL_EXCEPTHOOK: object | None = None
_POST_BOOTSTRAP_FAILURE_BYTES: bytes | None = None
_BOOTSTRAP_GIT_ATTRIBUTES_AUTHENTICATED = False


def _blocked_numpy_attribute(_name: str) -> Never:
    global _NUMPY_SENTINEL_ATTRIBUTE_ACCESSES
    _NUMPY_SENTINEL_ATTRIBUTE_ACCESSES += 1
    raise _BootstrapAuthenticationError


def _bootstrap_dependency_metadata_roots() -> tuple[Path, ...]:
    """Bind the direct base interpreter and inert project-venv metadata root."""

    if (
        not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.dont_write_bytecode
        or any(
            name in sys.modules
            for name in ("site", "sitecustomize", "usercustomize")
        )
    ):
        raise _BootstrapAuthenticationError
    raw_base_executable = getattr(sys, "_base_executable", None)
    if not isinstance(raw_base_executable, str):
        raise _BootstrapAuthenticationError
    try:
        executable = Path(sys.executable).resolve(strict=True)
        base_executable = Path(raw_base_executable).resolve(strict=True)
        prefix = Path(sys.prefix).resolve(strict=True)
        exec_prefix = Path(sys.exec_prefix).resolve(strict=True)
        base_prefix = Path(sys.base_prefix).resolve(strict=True)
        base_exec_prefix = Path(sys.base_exec_prefix).resolve(strict=True)
        expected_prefix = _BOOTSTRAP_BASE_PREFIX.resolve(strict=True)
    except OSError:
        raise _BootstrapAuthenticationError from None
    if (
        executable != _BOOTSTRAP_PYTHON_EXECUTABLE
        or base_executable != _BOOTSTRAP_PYTHON_EXECUTABLE
        or prefix != expected_prefix
        or exec_prefix != expected_prefix
        or base_prefix != expected_prefix
        or base_exec_prefix != expected_prefix
    ):
        raise _BootstrapAuthenticationError
    _bootstrap_require_executable(
        _BOOTSTRAP_PYTHON_EXECUTABLE,
        expected_sha256=_BOOTSTRAP_PYTHON_EXECUTABLE_SHA256,
    )
    for raw in sys.path:
        try:
            candidate = Path(raw)
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError, TypeError):
            raise _BootstrapAuthenticationError from None
        if (
            not raw
            or not candidate.is_absolute()
            or resolved.is_relative_to(PROJECT_ROOT)
            or not resolved.is_relative_to(expected_prefix)
        ):
            raise _BootstrapAuthenticationError

    root = _BOOTSTRAP_DEPENDENCY_METADATA_ROOT
    try:
        metadata = root.lstat()
        resolved = root.resolve(strict=True)
    except OSError:
        raise _BootstrapAuthenticationError from None
    if (
        root.is_symlink()
        or resolved != root
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or str(resolved) in sys.path
    ):
        raise _BootstrapAuthenticationError
    return (resolved,)


def _post_bootstrap_import_excepthook(
    _exception_type: type[BaseException],
    _exception: BaseException,
    _traceback: object,
) -> None:
    """Emit one path-free receipt if authenticated imports fail before ``main``."""

    try:
        if _POST_BOOTSTRAP_FAILURE_BYTES is not None:
            os.write(1, _POST_BOOTSTRAP_FAILURE_BYTES)
    except BaseException:
        pass


def _install_post_bootstrap_failure_boundary() -> None:
    global _ORIGINAL_EXCEPTHOOK, _POST_BOOTSTRAP_FAILURE_BYTES
    if _ORIGINAL_EXCEPTHOOK is not None or _POST_BOOTSTRAP_FAILURE_BYTES is not None:
        raise _BootstrapAuthenticationError
    receipt = _bootstrap_failure_dict()
    receipt["stage"] = "project_import_authentication"
    _POST_BOOTSTRAP_FAILURE_BYTES = (
        json.dumps(receipt, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("ascii")
    _ORIGINAL_EXCEPTHOOK = sys.excepthook
    sys.excepthook = _post_bootstrap_import_excepthook


def _release_post_bootstrap_failure_boundary() -> None:
    global _ORIGINAL_EXCEPTHOOK, _POST_BOOTSTRAP_FAILURE_BYTES
    if _ORIGINAL_EXCEPTHOOK is None or _POST_BOOTSTRAP_FAILURE_BYTES is None:
        raise SetupBridgePreflightError("project_import_authentication")
    sys.excepthook = cast(Any, _ORIGINAL_EXCEPTHOOK)
    _ORIGINAL_EXCEPTHOOK = None
    _POST_BOOTSTRAP_FAILURE_BYTES = None


def _install_numpy_typing_sentinel() -> None:
    """Satisfy type-only imports while making any NumPy execution fail closed."""

    global _NUMPY_SENTINEL, _NUMPY_TYPING_SENTINEL
    if _NUMPY_SENTINEL is not None or _NUMPY_TYPING_SENTINEL is not None:
        raise _BootstrapAuthenticationError
    if any(
        name == "numpy"
        or name.startswith("numpy.")
        or name == "pyboy"
        or name.startswith("pyboy.")
        or name == "PIL"
        or name.startswith("PIL.")
        or name == "sdl2"
        or name.startswith("sdl2.")
        or name == "sdl2dll"
        or name.startswith("sdl2dll.")
        for name in sys.modules
    ):
        raise _BootstrapAuthenticationError
    numpy = ModuleType("numpy")
    typing = ModuleType("numpy.typing")
    numpy.__dict__.update(
        {
            "__all__": ("typing",),
            "__getattr__": _blocked_numpy_attribute,
            "__package__": "numpy",
            "__path__": (),
            "typing": typing,
        }
    )
    typing.__dict__.update(
        {
            "ArrayLike": _NumpyTypingPlaceholder,
            "NDArray": _NumpyTypingPlaceholder,
            "__package__": "numpy",
        }
    )
    sys.modules["numpy"] = numpy
    sys.modules["numpy.typing"] = typing
    _NUMPY_SENTINEL = numpy
    _NUMPY_TYPING_SENTINEL = typing


def _require_no_third_party_execution() -> None:
    if (
        _NUMPY_SENTINEL is None
        or _NUMPY_TYPING_SENTINEL is None
        or sys.modules.get("numpy") is not _NUMPY_SENTINEL
        or sys.modules.get("numpy.typing") is not _NUMPY_TYPING_SENTINEL
        or _NUMPY_SENTINEL_ATTRIBUTE_ACCESSES != 0
        or any(str(root) in sys.path for root in _BOOTSTRAP_DEPENDENCY_METADATA_ROOTS)
    ):
        raise SetupBridgePreflightError("third_party_execution_boundary")
    for name, module in tuple(sys.modules.items()):
        if module is _NUMPY_SENTINEL or module is _NUMPY_TYPING_SENTINEL:
            continue
        if name.startswith("numpy.") and name != "numpy.typing":
            raise SetupBridgePreflightError("third_party_execution_boundary")
        if any(
            name == root or name.startswith(f"{root}.")
            for root in ("pyboy", "PIL", "sdl2", "sdl2dll")
        ):
            raise SetupBridgePreflightError("third_party_execution_boundary")
        raw_path = getattr(module, "__file__", None)
        if not isinstance(raw_path, str):
            continue
        try:
            origin = Path(raw_path).resolve(strict=True)
        except OSError:
            raise SetupBridgePreflightError("third_party_execution_boundary") from None
        if any(
            origin.is_relative_to(root)
            for root in _BOOTSTRAP_DEPENDENCY_METADATA_ROOTS
        ):
            raise SetupBridgePreflightError("third_party_execution_boundary")


def _bootstrap_cli_identity(argv: list[str]) -> tuple[str, str, str] | None:
    """Authenticate package bytes before any project module can be imported."""

    if (
        not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.dont_write_bytecode
    ):
        raise _BootstrapAuthenticationError
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--expected-bridge-source-commit", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    try:
        parsed, _unknown = parser.parse_known_args(argv)
    except SystemExit:
        raise _BootstrapAuthenticationError from None
    bridge_commit = parsed.expected_bridge_source_commit
    plan_commit = parsed.expected_source_commit
    source_bundle = parsed.expected_source_bundle_sha256
    if (
        re.fullmatch(r"[0-9a-f]{40}", bridge_commit) is None
        or re.fullmatch(r"[0-9a-f]{40}", plan_commit) is None
        or re.fullmatch(r"[0-9a-f]{64}", source_bundle) is None
        or os.environ.get("POKEMON_RED_ENCOUNTER_LOG", "").strip()
    ):
        raise _BootstrapAuthenticationError

    evidence_payload = _bootstrap_read_regular(
        _CANONICAL_EVIDENCE_PATH,
        maximum_bytes=128 * 1024,
    )
    if hashlib.sha256(evidence_payload).hexdigest() != _CANONICAL_EVIDENCE_SHA256:
        raise _BootstrapAuthenticationError
    try:
        evidence = json.loads(evidence_payload.decode("ascii"))
        publication = evidence["publication"]
    except (KeyError, TypeError, UnicodeDecodeError, ValueError):
        raise _BootstrapAuthenticationError from None
    if (
        not isinstance(evidence, dict)
        or not isinstance(publication, dict)
        or publication.get("merged_main_commit") != plan_commit
        or publication.get("source_bundle_sha256") != source_bundle
    ):
        raise _BootstrapAuthenticationError

    _authenticate_git_attribute_boundary()
    head = _bootstrap_git_bytes(("rev-parse", "--verify", "HEAD^{commit}"), maximum_bytes=128)
    if head.decode("ascii", errors="strict").strip() != bridge_commit:
        raise _BootstrapAuthenticationError
    status = _bootstrap_git_bytes(
        (
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignore-submodules=all",
        ),
        maximum_bytes=1024 * 1024,
    )
    if status:
        raise _BootstrapAuthenticationError
    remote_refs = _bootstrap_git_bytes(
        (
            "for-each-ref",
            f"--contains={bridge_commit}",
            "--format=%(refname)",
            "refs/remotes",
        ),
        maximum_bytes=64 * 1024,
    ).decode("ascii", errors="strict")
    if not any(
        ref.startswith("refs/remotes/") and not ref.endswith("/HEAD")
        for ref in remote_refs.splitlines()
    ):
        raise _BootstrapAuthenticationError

    source_delta = _bootstrap_git_bytes(
        (
            "diff",
            "--no-ext-diff",
            "--name-status",
            "--no-renames",
            plan_commit,
            bridge_commit,
            "--",
            "pyproject.toml",
            "src",
        ),
        maximum_bytes=1024 * 1024,
    )
    if source_delta:
        raise _BootstrapAuthenticationError
    inventory_payload = _bootstrap_git_bytes(
        (
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            plan_commit,
            "--",
            "pyproject.toml",
            "src",
        )
    )
    inventory: set[str] = set()
    for raw_path in inventory_payload.split(b"\0"):
        if not raw_path:
            continue
        try:
            relative = raw_path.decode("ascii")
        except UnicodeDecodeError:
            raise _BootstrapAuthenticationError from None
        if relative in inventory:
            raise _BootstrapAuthenticationError
        inventory.add(relative)
        current = _bootstrap_read_regular(
            PROJECT_ROOT / relative,
            maximum_bytes=16 * 1024 * 1024,
        )
        committed = _bootstrap_git_bytes(
            ("show", f"{plan_commit}:{relative}"),
            maximum_bytes=16 * 1024 * 1024,
        )
        if current != committed:
            raise _BootstrapAuthenticationError
    filesystem_inventory = {"pyproject.toml"} | _bootstrap_filesystem_src_root_inventory(
        PROJECT_ROOT,
        SRC_ROOT,
        inventory - {"pyproject.toml"},
        allowed_local_metadata_sha256=_BOOTSTRAP_ALLOWED_LOCAL_METADATA_SHA256,
    )
    if inventory != filesystem_inventory:
        raise _BootstrapAuthenticationError

    workflow_delta = _bootstrap_git_bytes(
        (
            "diff",
            "--no-ext-diff",
            "--name-status",
            "--no-renames",
            plan_commit,
            bridge_commit,
            "--",
            _CI_WORKFLOW_RELATIVE_PATH,
        ),
        maximum_bytes=1024,
    )
    if workflow_delta:
        raise _BootstrapAuthenticationError
    workflow_path = PROJECT_ROOT / _CI_WORKFLOW_RELATIVE_PATH
    workflow_bytes = _bootstrap_read_regular(
        workflow_path,
        maximum_bytes=1024 * 1024,
    )
    if (
        workflow_bytes
        != _bootstrap_git_bytes(
            ("show", f"{plan_commit}:{_CI_WORKFLOW_RELATIVE_PATH}"),
            maximum_bytes=1024 * 1024,
        )
        or workflow_bytes
        != _bootstrap_git_bytes(
            ("show", f"{bridge_commit}:{_CI_WORKFLOW_RELATIVE_PATH}"),
            maximum_bytes=1024 * 1024,
        )
    ):
        raise _BootstrapAuthenticationError

    script_delta = _bootstrap_git_bytes(
        (
            "diff",
            "--no-ext-diff",
            "--name-status",
            "--no-renames",
            plan_commit,
            bridge_commit,
            "--",
            "scripts",
        ),
        maximum_bytes=1024 * 1024,
    ).decode("ascii", errors="strict")
    if script_delta != _BOOTSTRAP_EXPECTED_SCRIPT_DELTA:
        raise _BootstrapAuthenticationError
    script_inventory_payload = _bootstrap_git_bytes(
        (
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            bridge_commit,
            "--",
            "scripts",
        )
    )
    script_inventory: set[str] = set()
    for raw_path in script_inventory_payload.split(b"\0"):
        if not raw_path:
            continue
        try:
            relative = raw_path.decode("ascii")
        except UnicodeDecodeError:
            raise _BootstrapAuthenticationError from None
        if relative in script_inventory:
            raise _BootstrapAuthenticationError
        script_inventory.add(relative)
        current = _bootstrap_read_regular(
            PROJECT_ROOT / relative,
            maximum_bytes=4 * 1024 * 1024,
        )
        committed = _bootstrap_git_bytes(
            ("show", f"{bridge_commit}:{relative}"),
            maximum_bytes=4 * 1024 * 1024,
        )
        if current != committed:
            raise _BootstrapAuthenticationError
    if script_inventory != _bootstrap_filesystem_script_inventory(
        PROJECT_ROOT,
        SCRIPTS_ROOT,
    ):
        raise _BootstrapAuthenticationError

    bridge_bytes = _bootstrap_read_regular(SCRIPT_PATH, maximum_bytes=4 * 1024 * 1024)
    committed_bridge = _bootstrap_git_bytes(
        ("show", f"{bridge_commit}:{_BRIDGE_SCRIPT_RELATIVE_PATH}"),
        maximum_bytes=4 * 1024 * 1024,
    )
    if bridge_bytes != committed_bridge:
        raise _BootstrapAuthenticationError
    return bridge_commit, plan_commit, source_bundle


def _fresh_unused_pycache_prefix() -> Path:
    candidate = PROJECT_ROOT / f".bridge-pycache-{os.urandom(32).hex()}"
    try:
        candidate.lstat()
    except FileNotFoundError:
        return candidate
    except OSError:
        raise _BootstrapAuthenticationError from None
    raise _BootstrapAuthenticationError


def _bootstrap_failure_dict() -> dict[str, object]:
    return {
        "controller_actions": 0,
        "emulator_frames": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "outcomes": 0,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "provider_executions": 0,
        "root_claims": 0,
        "schema": _BOOTSTRAP_FAILURE_SCHEMA,
        "setup_campaign_calls": 0,
        "setup_runtime_factory_calls": 0,
        "stage": "bootstrap_source_authentication",
        "status": "failed_closed",
        "teacher_queries": 0,
    }


if __name__ == "__main__":
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        if (
            not sys.flags.isolated
            or not sys.flags.no_site
            or not sys.flags.dont_write_bytecode
        ):
            print(
                json.dumps(
                    _bootstrap_failure_dict(),
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            raise SystemExit(1)
        print(_BOOTSTRAP_USAGE)
        raise SystemExit(0)
    try:
        _BOOTSTRAP_DEPENDENCY_METADATA_ROOTS = (
            _bootstrap_dependency_metadata_roots()
        )
        _install_numpy_typing_sentinel()
        _BOOTSTRAP_IDENTITY = _bootstrap_cli_identity(sys.argv[1:])
        _install_post_bootstrap_failure_boundary()
    except BaseException:
        print(json.dumps(_bootstrap_failure_dict(), separators=(",", ":"), sort_keys=True))
        raise SystemExit(1) from None
    if _BOOTSTRAP_IDENTITY is not None:
        # Force imports from authenticated source text rather than ignored local caches.
        sys.dont_write_bytecode = True
        sys.pycache_prefix = str(_fresh_unused_pycache_prefix())
        os.environ["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
elif sys.flags.no_site:
    # The qualified production surface is CLI-only.  An isolated/no-site
    # non-main load must stop before project roots or project modules are added.
    raise _BootstrapAuthenticationError

_PRELOADED_PROJECT_MODULES = tuple(
    sorted(
        name
        for name in sys.modules
        if name == "pokemon_red_completion" or name.startswith("pokemon_red_completion.")
    )
)
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

_FREEZER_SCRIPT_PATH = SCRIPTS_ROOT / "freeze_red_living_dex_provider_plan.py"
_AUTHENTICATION_SUPPORT_SCRIPT_PATH = (
    SCRIPTS_ROOT / "freeze_red_living_dex_multifamily_pilot.py"
)
_EXPECTED_SCRIPT_DELTA = f"A\t{_BRIDGE_SCRIPT_RELATIVE_PATH}\n"
_PLAN_RECORD_ID = "red-living-dex-provider-plan-v1"
_PLAN_RECORD_KIND = "red-living-dex-provider-plan-v1"
_FREEZER: Mapping[str, object] | None = None
_FREEZER_BINDING: _BridgeSourceBinding | None = None

from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.encounters import ENCOUNTER_LOG_VARIABLE
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_claim_is_available,
)
from pokemon_red_completion.goal_manager_protocol import (
    GOAL_MANAGER_REGISTRY_DIGEST_RELATIVE_PATH,
    GOAL_MANAGER_REGISTRY_DIGEST_SCHEMA,
    GOAL_MANAGER_REGISTRY_RELATIVE_PATH,
    parse_goal_manager_registry,
)
from pokemon_red_completion.goal_manager_protocol import (
    load_committed_goal_manager_registry_at_revision as _unsafe_registry_loader,
)
from pokemon_red_completion.private_artifacts import (
    PRIVATE_ROOT_SENTINEL,
    PrivateArtifactRoot,
    SealedRecordSummary,
    open_private_root,
    validate_private_record,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_provider_plan import (
    derive_red_living_dex_provider_corridors,
)
from pokemon_red_completion.red_living_dex_setup_identity import (
    compose_red_living_dex_setup_execution_identity,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
)
from pokemon_red_completion.red_living_dex_setup_recipe_campaign import (
    RED_LIVING_DEX_RECIPE_PLAN_RECORD_ID,
    RED_LIVING_DEX_RECIPE_PLAN_RECORD_KIND,
    RED_LIVING_DEX_RECIPE_TERMINAL_RECORD_KIND,
)
from pokemon_red_completion.rom import verify_rom
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentity,
    build_runtime_identity_from,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)
from pokemon_red_completion.strategic_navigation_scenarios import (
    load_strategic_navigation_scenario_registry,
)

RESULT_SCHEMA = "pokemon.red.living-dex-setup-bridge-precontroller-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-setup-bridge-precontroller-failure.v1"
_GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
_CI_WORKFLOW_NAME = "CI"
_GITHUB_API_VERSION = "2022-11-28"
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PRIVATE_PLAN_KEYS = frozenset(
    {
        "context_catalog_sha256",
        "context_plan_sha256",
        "controller_actions",
        "emulator_frames",
        "execution_identity",
        "execution_identity_sha256",
        "freeze",
        "freeze_sha256",
        "goal_registry_sha256",
        "model_fits",
        "model_predictions",
        "outcomes",
        "private_plan_sha256",
        "provider_executions",
        "recipe_plan",
        "recipe_plan_sha256",
        "root_claims",
        "route_registry_sha256",
        "rom_sha256",
        "runtime_identity_sha256",
        "schema",
        "source_catalog_partition_reused_as_prospective_label",
        "source_bundle_sha256",
        "source_commit",
        "status",
        "teacher_queries",
    }
)
_ZERO_EFFECT_KEYS = (
    "controller_actions",
    "emulator_frames",
    "model_fits",
    "model_predictions",
    "outcomes",
    "provider_executions",
    "root_claims",
    "teacher_queries",
)
_RECIPE_PLAN_SCHEMA = "pokemon.red.private-living-dex-setup-recipe-plan.v2"
_SLOT_RECIPE_SCHEMA = "pokemon.red.private-living-dex-setup-slot-recipe.v2"
_PROVIDER_RECIPE_SCHEMA = "pokemon.red.private-living-dex-setup-provider-recipe.v2"
_PROVIDER_FREEZE_SCHEMA = "pokemon.red.private-living-dex-provider-plan-freeze.v1"
_RECIPE_PLAN_KEYS = frozenset(
    {
        "claim_before_controller_input",
        "execution_identity",
        "execution_identity_sha256",
        "learner_effects",
        "prospective_plan_sha256",
        "recipes",
        "retry_after_controller_input",
        "same_origin_fork_required",
        "schema",
    }
)
_SLOT_RECIPE_KEYS = frozenset(
    {
        "available_option_kinds",
        "base_boundary_sha256",
        "construction_route_sha256",
        "origin_boundary_sha256",
        "partition",
        "providers",
        "root_consumption_sha256",
        "root_envelope_sha256",
        "root_state_sha256",
        "schema",
        "slot_sha256",
    }
)
_PROVIDER_RECIPE_KEYS = frozenset(
    {
        "expected_family_sha256",
        "family",
        "goal_kind",
        "option_kind",
        "profile_sha256",
        "provider_configuration_sha256",
        "provider_contract_id",
        "route_recipe_sha256",
        "schema",
    }
)
_FREEZE_KEYS = frozenset(
    {
        "corridor_binding_sha256s",
        "effects_after",
        "effects_before",
        "recipe_plan_sha256",
        "schema",
    }
)


class SetupBridgePreflightError(RuntimeError):
    """One sanitized bridge stage failed closed."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


def _stdlib_pyboy_distribution() -> object:
    """Open the one exact inert PyBoy metadata record without a global scan."""

    _require_no_third_party_execution()
    try:
        if len(_BOOTSTRAP_DEPENDENCY_METADATA_ROOTS) != 1:
            raise SetupBridgePreflightError("runtime_identity_authentication")
        dependency_root = _BOOTSTRAP_DEPENDENCY_METADATA_ROOTS[0]
        candidates = {
            entry.name
            for entry in dependency_root.iterdir()
            if entry.name.casefold().startswith("pyboy")
            and entry.name.casefold().endswith(".dist-info")
        }
        if candidates != {_BOOTSTRAP_PYBOY_METADATA_DIRECTORY}:
            raise SetupBridgePreflightError("runtime_identity_authentication")
        metadata_root = dependency_root / _BOOTSTRAP_PYBOY_METADATA_DIRECTORY
        metadata_root_stat = metadata_root.lstat()
        if (
            metadata_root.is_symlink()
            or metadata_root.resolve(strict=True) != metadata_root
            or not stat.S_ISDIR(metadata_root_stat.st_mode)
            or metadata_root_stat.st_uid != os.getuid()
            or stat.S_IMODE(metadata_root_stat.st_mode) & 0o022
        ):
            raise SetupBridgePreflightError("runtime_identity_authentication")

        expected_root_entries = {
            Path(relative).parts[0]
            for relative in _BOOTSTRAP_PYBOY_METADATA_SHA256
        }
        root_entries = {entry.name for entry in metadata_root.iterdir()}
        if root_entries != expected_root_entries:
            raise SetupBridgePreflightError("runtime_identity_authentication")
        licenses = metadata_root / "licenses"
        license_stat = licenses.lstat()
        if (
            licenses.is_symlink()
            or licenses.resolve(strict=True) != licenses
            or not stat.S_ISDIR(license_stat.st_mode)
            or license_stat.st_uid != os.getuid()
            or stat.S_IMODE(license_stat.st_mode) & 0o022
            or {entry.name for entry in licenses.iterdir()} != {"LICENSE.md"}
        ):
            raise SetupBridgePreflightError("runtime_identity_authentication")

        for relative, expected_sha256 in _BOOTSTRAP_PYBOY_METADATA_SHA256.items():
            path = metadata_root / relative
            metadata = path.lstat()
            if (
                path.is_symlink()
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise SetupBridgePreflightError("runtime_identity_authentication")
            payload = _bootstrap_read_regular(path, maximum_bytes=4 * 1024 * 1024)
            if hashlib.sha256(payload).hexdigest() != expected_sha256:
                raise SetupBridgePreflightError("runtime_identity_authentication")

        distribution = importlib_metadata.PathDistribution(metadata_root)
        if (
            distribution.metadata.get("Name") != "pyboy"
            or distribution.version != "2.7.0"
        ):
            raise SetupBridgePreflightError("runtime_identity_authentication")
        _require_no_third_party_execution()
        return distribution
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("runtime_identity_authentication") from None


def _build_stdlib_runtime_identity() -> RuntimeIdentity:
    """Rebuild the frozen Python/PyBoy identity without importing third-party code."""

    try:
        identity = build_runtime_identity_from(
            python_executable=sys.executable,
            python_implementation=platform.python_implementation(),
            python_version=platform.python_version(),
            pyboy_distribution=_stdlib_pyboy_distribution(),
        )
        _require_no_third_party_execution()
        return identity
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("runtime_identity_authentication") from None


def _require_runtime_identity_without_imports(identity: RuntimeIdentity) -> None:
    if not isinstance(identity, RuntimeIdentity):
        raise SetupBridgePreflightError("runtime_identity_authentication")
    _require_no_third_party_execution()


class _ExistingClaimRegistryReadLease:
    """Hold a shared lock without creating or modifying coordination metadata."""

    __slots__ = ("_descriptor", "_registry")

    def __init__(self, registry: Path) -> None:
        self._registry = registry
        self._descriptor = -1

    def __enter__(self) -> _ExistingClaimRegistryReadLease:
        marker = self._registry / ".coordination.lock"
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = -1
        try:
            descriptor = os.open(marker, flags)
            opened = os.fstat(descriptor)
            named = marker.lstat()
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or named.st_dev != opened.st_dev
                or named.st_ino != opened.st_ino
            ):
                raise OSError("unsafe coordination file")
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
            self._descriptor = descriptor
            return self
        except OSError:
            if descriptor >= 0:
                with suppress(OSError):
                    os.close(descriptor)
            raise SetupBridgePreflightError("root_claim_availability") from None

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: object,
    ) -> Literal[False]:
        if self._descriptor >= 0:
            with suppress(OSError):
                fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            with suppress(OSError):
                os.close(self._descriptor)
            self._descriptor = -1
        return False


def _existing_claim_registry_read_lease(
    registry: Path,
) -> _ExistingClaimRegistryReadLease:
    return _ExistingClaimRegistryReadLease(registry)


def _read_only_input_claim_registry_lease(
    registry: Path,
    *,
    exclusive: bool,
) -> _ExistingClaimRegistryReadLease:
    if exclusive is not False:
        raise SetupBridgePreflightError("root_claim_availability")
    return _existing_claim_registry_read_lease(registry)


def _committed_source_bundle_sha256(revision: str) -> str:
    """Rebuild one historical source bundle using only hardened Git reads."""

    try:
        commit = _run_git_bytes(
            ("rev-parse", "--verify", f"{revision}^{{commit}}"),
            maximum_bytes=128,
        ).decode("ascii", errors="strict").strip()
        if _SHA1.fullmatch(commit) is None:
            raise SetupBridgePreflightError("private_input_authentication")
        listing = _run_git_bytes(
            (
                "ls-tree",
                "-r",
                "-z",
                "--full-tree",
                commit,
                "--",
                "pyproject.toml",
                "src/pokemon_red_completion",
            ),
            maximum_bytes=8 * 1024 * 1024,
        )
        entries: list[dict[str, object]] = []
        seen_paths: set[str] = set()
        total_bytes = 0
        for record in listing.split(b"\0"):
            if not record:
                continue
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, raw_oid = metadata.split(b" ", 2)
            path = raw_path.decode("ascii", errors="strict")
            oid = raw_oid.decode("ascii", errors="strict")
            if (
                mode not in {b"100644", b"100755"}
                or object_type != b"blob"
                or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", oid) is None
                or not (
                    path == "pyproject.toml"
                    or path.startswith("src/pokemon_red_completion/")
                )
                or "\\" in path
                or path in seen_paths
            ):
                raise SetupBridgePreflightError("private_input_authentication")
            seen_paths.add(path)
            raw_size = _run_git_bytes(
                ("cat-file", "-s", oid),
                maximum_bytes=128,
            )
            size = int(raw_size.decode("ascii", errors="strict").strip())
            if not 0 <= size <= 16 * 1024 * 1024:
                raise SetupBridgePreflightError("private_input_authentication")
            payload = _run_git_bytes(
                ("cat-file", "blob", oid),
                maximum_bytes=16 * 1024 * 1024,
            )
            if len(payload) != size:
                raise SetupBridgePreflightError("private_input_authentication")
            total_bytes += size
            if total_bytes > 128 * 1024 * 1024:
                raise SetupBridgePreflightError("private_input_authentication")
            entries.append(
                {
                    "bytes": size,
                    "mode": mode.decode("ascii"),
                    "path": path,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        entries.sort(key=lambda entry: str(entry["path"]))
        if (
            not entries
            or entries[0]["path"] != "pyproject.toml"
            or not any(
                str(entry["path"]).startswith("src/pokemon_red_completion/")
                for entry in entries
            )
        ):
            raise SetupBridgePreflightError("private_input_authentication")
        document = {
            "files": entries,
            "schema": "pokemon-red-executable-source-bundle-v2",
        }
        encoded = json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii") + b"\n"
        return hashlib.sha256(encoded).hexdigest()
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("private_input_authentication") from None


def _load_committed_goal_manager_registry_at_revision(
    repository_root: str | Path,
    revision: str,
) -> object:
    """Authenticate the historical registry without its ambient Git helpers."""

    try:
        if Path(repository_root).resolve(strict=True) != PROJECT_ROOT:
            raise SetupBridgePreflightError("private_input_authentication")
        commit = _run_git_bytes(
            ("rev-parse", "--verify", f"{revision}^{{commit}}"),
            maximum_bytes=128,
        ).decode("ascii", errors="strict").strip()
        if _SHA1.fullmatch(commit) is None:
            raise SetupBridgePreflightError("private_input_authentication")
        digest_payload = _run_git_bytes(
            ("show", f"{commit}:{GOAL_MANAGER_REGISTRY_DIGEST_RELATIVE_PATH}"),
            maximum_bytes=4096,
        )
        registry_payload = _run_git_bytes(
            ("show", f"{commit}:{GOAL_MANAGER_REGISTRY_RELATIVE_PATH}"),
            maximum_bytes=2 * 1024 * 1024,
        )
        digest = json.loads(
            digest_payload,
            object_pairs_hook=_unique_json_object,
        )
        if (
            not isinstance(digest, Mapping)
            or set(digest) != {"bytes", "schema", "sha256"}
            or digest.get("schema") != GOAL_MANAGER_REGISTRY_DIGEST_SCHEMA
            or type(digest.get("bytes")) is not int  # noqa: E721
            or digest.get("bytes") != len(registry_payload)
            or not isinstance(digest.get("sha256"), str)
            or _SHA256.fullmatch(cast(str, digest["sha256"])) is None
            or hashlib.sha256(registry_payload).hexdigest() != digest["sha256"]
        ):
            raise SetupBridgePreflightError("private_input_authentication")
        registry = parse_goal_manager_registry(registry_payload)
        if (
            registry.execution.source_bundle_sha256
            != _committed_source_bundle_sha256(commit)
        ):
            raise SetupBridgePreflightError("private_input_authentication")
        return replace(
            registry,
            execution=replace(registry.execution, source_commit=commit),
        )
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("private_input_authentication") from None


def _bind_read_only_input_authenticator(function: object) -> FunctionType:
    """Clone exact helper code while replacing only its create-capable read lease."""

    if (
        not isinstance(function, FunctionType)
        or function.__closure__ is not None
        or function.__globals__.get("fixed_account_claim_registry_lease")
        is not fixed_account_claim_registry_lease
        or function.__globals__.get(
            "load_committed_goal_manager_registry_at_revision"
        )
        is not _unsafe_registry_loader
    ):
        raise SetupBridgePreflightError("frozen_script_support_authentication")
    namespace = dict(function.__globals__)
    namespace["fixed_account_claim_registry_lease"] = (
        _read_only_input_claim_registry_lease
    )
    namespace["load_committed_goal_manager_registry_at_revision"] = (
        _load_committed_goal_manager_registry_at_revision
    )
    bound = FunctionType(
        function.__code__,
        namespace,
        name=function.__name__,
        argdefs=function.__defaults__,
    )
    bound.__kwdefaults__ = function.__kwdefaults__
    bound.__annotations__ = function.__annotations__
    return bound


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise SetupBridgePreflightError("arguments")


@dataclass(slots=True)
class _DiagnosticState:
    authenticated_contexts: int = 0
    authenticated_supplemental_roots: int = 0
    eligible_root_pool: int = 0
    action_free_root_observations: int = 0
    selected_roots: int = 0
    roots_rejoined: int = 0
    logical_claims_available: int = 0
    physical_claims_available: int = 0
    setup_runtime_factory_calls: int = 0
    setup_campaign_calls: int = 0
    controller_actions: int = 0
    emulator_frames: int = 0
    provider_executions: int = 0
    teacher_queries: int = 0
    model_predictions: int = 0
    outcomes: int = 0
    model_fits: int = 0
    root_claims: int = 0

    def failure_dict(self, stage: str) -> dict[str, object]:
        return {
            "controller_actions": self.controller_actions,
            "emulator_frames": self.emulator_frames,
            "model_fits": self.model_fits,
            "model_predictions": self.model_predictions,
            "outcomes": self.outcomes,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": self.provider_executions,
            "root_claims": self.root_claims,
            "schema": FAILURE_SCHEMA,
            "setup_campaign_calls": self.setup_campaign_calls,
            "setup_runtime_factory_calls": self.setup_runtime_factory_calls,
            "stage": stage,
            "status": "failed_closed",
            "teacher_queries": self.teacher_queries,
        }


@dataclass(frozen=True, slots=True)
class _BridgeSourceBinding:
    """Published wrapper plus the exact frozen script-support closure."""

    bridge_source_commit: str
    bridge_script_sha256: str
    freezer_script_sha256: str
    authentication_support_script_sha256: str

    def __post_init__(self) -> None:
        _require_sha1(self.bridge_source_commit, "bridge source")
        _require_sha256(self.bridge_script_sha256, "bridge script")
        _require_sha256(self.freezer_script_sha256, "freezer script")
        _require_sha256(
            self.authentication_support_script_sha256,
            "authentication support script",
        )


@dataclass(frozen=True, slots=True)
class _FrozenRootBinding:
    root_consumption_sha256: str
    root_state_sha256: str
    root_envelope_sha256: str
    recipe_sha256: str


@dataclass(frozen=True, slots=True)
class _RecipePlanInventory:
    root_bindings: tuple[_FrozenRootBinding, ...]
    recipe_sha256s: tuple[str, ...]
    train_slots: int
    development_slots: int
    option_count: int
    routed_option_count: int
    semantic_family_count: int
    origin_boundary_count: int


@dataclass(frozen=True, slots=True)
class PreparedRedLivingDexSetupBridge:
    """Exact private bytes and frozen documents before any runtime may exist."""

    plan_document: Mapping[str, object] = field(repr=False)
    freeze_document: Mapping[str, object] = field(repr=False)
    roots: tuple[RedLivingDexAuthenticatedSetupRoot, ...] = field(repr=False)
    corridor_binding_sha256s: tuple[str, ...]
    record_summary: SealedRecordSummary
    private_plan_sha256: str
    plan_source_commit: str
    source_bundle_sha256: str
    bridge_source_commit: str
    bridge_script_sha256: str
    freezer_script_sha256: str
    authentication_support_script_sha256: str
    exact_ci_run: int
    exact_ci_attempt: int

    def __post_init__(self) -> None:
        inventory = _inspect_recipe_plan(self.plan_document)
        _inspect_freeze_document(
            self.freeze_document,
            recipe_plan_sha256=canonical_sha256(dict(self.plan_document)),
            corridor_binding_sha256s=self.corridor_binding_sha256s,
        )
        if len(self.roots) != len(inventory.root_bindings):
            raise SetupBridgePreflightError("root_inventory_join")
        for binding, root in zip(inventory.root_bindings, self.roots, strict=True):
            root.__post_init__()
            if (
                binding.root_consumption_sha256 != root.root_consumption_sha256
                or binding.root_state_sha256 != root.state_sha256
                or binding.root_envelope_sha256 != root.envelope_sha256
            ):
                raise SetupBridgePreflightError("root_inventory_join")
        _require_sha1(self.bridge_source_commit, "bridge source")
        _require_sha1(self.plan_source_commit, "plan source")
        _require_sha256(self.private_plan_sha256, "private plan")
        _require_sha256(self.source_bundle_sha256, "source bundle")
        _require_sha256(self.bridge_script_sha256, "bridge script")
        _require_sha256(self.freezer_script_sha256, "freezer script")
        _require_sha256(
            self.authentication_support_script_sha256,
            "authentication support script",
        )
        if self.exact_ci_run <= 0 or self.exact_ci_attempt <= 0:
            raise SetupBridgePreflightError("bridge_ci_authentication")

    def public_dict(self) -> dict[str, object]:
        inventory = _inspect_recipe_plan(self.plan_document)
        return {
            "action_free_root_observations": 0,
            "authenticated_root_bytes": len(self.roots),
            "authentication_support_script_sha256": (
                self.authentication_support_script_sha256
            ),
            "bridge_script_sha256": self.bridge_script_sha256,
            "bridge_source_commit": self.bridge_source_commit,
            "cartridge_derived_corridors": len(self.corridor_binding_sha256s),
            "canonical_evidence_sha256": _CANONICAL_EVIDENCE_SHA256,
            "claim_before_controller_input": True,
            "controller_actions": 0,
            "development_slots": inventory.development_slots,
            "emulator_frames": 0,
            "exact_ci_attempt": self.exact_ci_attempt,
            "exact_ci_run": self.exact_ci_run,
            "execution_identity_sha256": cast(
                str,
                self.plan_document["execution_identity_sha256"],
            ),
            "freezer_script_sha256": self.freezer_script_sha256,
            "learner_effects": 0,
            "model_fits": 0,
            "model_predictions": 0,
            "option_count": inventory.option_count,
            "outcomes": 0,
            "origin_boundary_count": inventory.origin_boundary_count,
            "plan_manifest_sha256": self.record_summary.manifest_sha256,
            "plan_source_commit": self.plan_source_commit,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "private_plan_sha256": self.private_plan_sha256,
            "provider_executions": 0,
            "recipe_plan_sha256": canonical_sha256(dict(self.plan_document)),
            "root_claims": 0,
            "root_inventory_rejoined": len(self.roots),
            "routed_option_count": inventory.routed_option_count,
            "same_origin_fork_required": True,
            "schema": RESULT_SCHEMA,
            "semantic_family_count": inventory.semantic_family_count,
            "setup_campaign_calls": 0,
            "setup_runtime_factory_calls": 0,
            "source_bundle_sha256": self.source_bundle_sha256,
            "status": "exact_plan_authenticated_precontroller_only",
            "teacher_queries": 0,
            "train_slots": inventory.train_slots,
        }


def _inspect_recipe_plan(plan: Mapping[str, object]) -> _RecipePlanInventory:
    """Validate the complete lossless identity surface available before runtime."""

    try:
        if set(plan) != _RECIPE_PLAN_KEYS or plan.get("schema") != _RECIPE_PLAN_SCHEMA:
            raise SetupBridgePreflightError("reconstructed_plan_join")
        execution = _mapping(plan["execution_identity"])
        if (
            canonical_sha256(execution) != plan["execution_identity_sha256"]
            or plan.get("claim_before_controller_input") is not True
            or plan.get("retry_after_controller_input") is not False
            or plan.get("same_origin_fork_required") is not True
            or plan.get("learner_effects") != 0
        ):
            raise SetupBridgePreflightError("reconstructed_plan_join")
        recipes_raw = plan.get("recipes")
        if not isinstance(recipes_raw, list) or len(recipes_raw) != 15:
            raise SetupBridgePreflightError("reconstructed_plan_join")
        bindings: list[_FrozenRootBinding] = []
        recipe_sha256s: list[str] = []
        partitions: Counter[str] = Counter()
        families: set[str] = set()
        origins: set[str] = set()
        option_count = 0
        routed_option_count = 0
        for raw_recipe in recipes_raw:
            recipe = _mapping(raw_recipe)
            if set(recipe) != _SLOT_RECIPE_KEYS or recipe.get("schema") != (
                _SLOT_RECIPE_SCHEMA
            ):
                raise SetupBridgePreflightError("reconstructed_plan_join")
            partition = recipe.get("partition")
            if partition not in {"train", "development"}:
                raise SetupBridgePreflightError("reconstructed_plan_join")
            option_kinds = recipe.get("available_option_kinds")
            providers_raw = recipe.get("providers")
            if (
                not isinstance(option_kinds, list)
                or not option_kinds
                or any(not isinstance(item, str) or not item for item in option_kinds)
                or len(set(option_kinds)) != len(option_kinds)
                or not isinstance(providers_raw, list)
                or len(providers_raw) != len(option_kinds)
            ):
                raise SetupBridgePreflightError("reconstructed_plan_join")
            for value in (
                recipe.get("slot_sha256"),
                recipe.get("root_consumption_sha256"),
                recipe.get("root_state_sha256"),
                recipe.get("root_envelope_sha256"),
                recipe.get("base_boundary_sha256"),
                recipe.get("origin_boundary_sha256"),
            ):
                _require_document_sha256(value)
            construction_route = recipe.get("construction_route_sha256")
            if construction_route is not None:
                _require_document_sha256(construction_route)
            for ordinal, raw_provider in enumerate(providers_raw):
                provider = _mapping(raw_provider)
                if set(provider) != _PROVIDER_RECIPE_KEYS or provider.get(
                    "schema"
                ) != _PROVIDER_RECIPE_SCHEMA:
                    raise SetupBridgePreflightError("reconstructed_plan_join")
                family = _mapping(provider["family"])
                family_sha256 = _require_document_sha256(
                    provider.get("expected_family_sha256")
                )
                if (
                    canonical_sha256(family) != family_sha256
                    or provider.get("option_kind") != option_kinds[ordinal]
                    or family.get("option_kind") != provider.get("option_kind")
                    or family.get("goal_kind") != provider.get("goal_kind")
                    or not isinstance(provider.get("provider_contract_id"), str)
                ):
                    raise SetupBridgePreflightError("reconstructed_plan_join")
                for field_name in (
                    "profile_sha256",
                    "provider_configuration_sha256",
                ):
                    _require_document_sha256(provider.get(field_name))
                route = provider.get("route_recipe_sha256")
                if route is not None:
                    _require_document_sha256(route)
                    routed_option_count += 1
                families.add(family_sha256)
            recipe_sha256 = canonical_sha256(recipe)
            bindings.append(
                _FrozenRootBinding(
                    root_consumption_sha256=cast(
                        str,
                        recipe["root_consumption_sha256"],
                    ),
                    root_state_sha256=cast(str, recipe["root_state_sha256"]),
                    root_envelope_sha256=cast(
                        str,
                        recipe["root_envelope_sha256"],
                    ),
                    recipe_sha256=recipe_sha256,
                )
            )
            recipe_sha256s.append(recipe_sha256)
            partitions[cast(str, partition)] += 1
            origins.add(cast(str, recipe["origin_boundary_sha256"]))
            option_count += len(providers_raw)
        for values in (
            recipe_sha256s,
            [item.root_consumption_sha256 for item in bindings],
            [item.root_state_sha256 for item in bindings],
            [item.root_envelope_sha256 for item in bindings],
        ):
            if len(values) != len(set(values)):
                raise SetupBridgePreflightError("reconstructed_plan_join")
        if option_count != 45 or len(families) != 33:
            raise SetupBridgePreflightError("reconstructed_plan_join")
        return _RecipePlanInventory(
            root_bindings=tuple(bindings),
            recipe_sha256s=tuple(recipe_sha256s),
            train_slots=partitions["train"],
            development_slots=partitions["development"],
            option_count=option_count,
            routed_option_count=routed_option_count,
            semantic_family_count=len(families),
            origin_boundary_count=len(origins),
        )
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("reconstructed_plan_join") from None


def _inspect_freeze_document(
    freeze: Mapping[str, object],
    *,
    recipe_plan_sha256: str,
    corridor_binding_sha256s: tuple[str, ...],
) -> None:
    try:
        if (
            set(freeze) != _FREEZE_KEYS
            or freeze.get("schema") != _PROVIDER_FREEZE_SCHEMA
            or freeze.get("recipe_plan_sha256") != recipe_plan_sha256
            or freeze.get("corridor_binding_sha256s")
            != list(corridor_binding_sha256s)
        ):
            raise SetupBridgePreflightError("reconstructed_plan_join")
        before = _mapping(freeze["effects_before"])
        after = _mapping(freeze["effects_after"])
        if before != after or any(
            value != 0 for key, value in before.items() if key != "schema"
        ):
            raise SetupBridgePreflightError("reconstructed_plan_join")
        for digest in corridor_binding_sha256s:
            _require_document_sha256(digest)
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("reconstructed_plan_join") from None


def _require_document_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise SetupBridgePreflightError("reconstructed_plan_join")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--expected-bridge-source-commit", required=True)
    parser.add_argument("--exact-ci-run", required=True, type=int)
    parser.add_argument("--exact-ci-attempt", required=True, type=int)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--registry-source-commit", required=True)
    parser.add_argument("--expected-registry-sha256", required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--expected-context-catalog-sha256", required=True)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--expected-private-plan-sha256", required=True)
    parser.add_argument("--expected-plan-manifest-sha256", required=True)
    parser.add_argument("--expected-recipe-plan-sha256", required=True)
    parser.add_argument("--expected-execution-identity-sha256", required=True)
    parser.add_argument("--rom", type=Path)
    parser.add_argument(
        "--supplemental-state",
        action="append",
        default=[],
        type=Path,
    )
    parser.add_argument(
        "--expected-supplemental-physical-root-sha256",
        action="append",
        default=[],
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    state = _DiagnosticState()
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        prepared = prepare_red_living_dex_setup_bridge(args, state=state)
        print(
            json.dumps(
                prepared.public_dict(),
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except SetupBridgePreflightError as error:
        stage = error.stage
    except BaseException:
        stage = "unexpected_failure"
    print(
        json.dumps(
            state.failure_dict(stage),
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


def prepare_red_living_dex_setup_bridge(
    args: argparse.Namespace,
    *,
    state: _DiagnosticState | None = None,
) -> PreparedRedLivingDexSetupBridge:
    """Return exact campaign inputs after every pre-controller check passes."""

    diagnostics = _DiagnosticState() if state is None else state
    _require_authenticated_cli_invocation(args)
    bridge_binding = _authenticate_bridge_source(args)
    initial_ci = _require_exact_green_ci_run(
        args.exact_ci_run,
        args.exact_ci_attempt,
        source_commit=bridge_binding.bridge_source_commit,
    )
    _authenticate_canonical_evidence(args)
    _load_freezer_support(bridge_binding)
    store = _open_store(args)
    _require_plan_namespace_binding(args)
    record, summary = _authenticate_plan_record(store, args)
    (
        rom_path,
        rom_sha256,
        rom_bytes,
        contexts,
        catalog_sha256,
        context_plan_sha256,
    ) = _authenticate_inputs(
        args,
        _require_sha1(args.expected_source_commit, "plan source"),
        _require_sha256(args.expected_source_bundle_sha256, "source bundle"),
    )
    diagnostics.authenticated_contexts = len(contexts)
    supplements = _authenticate_supplemental_roots(
        tuple(args.supplemental_state),
        tuple(args.expected_supplemental_physical_root_sha256),
    )
    diagnostics.authenticated_supplemental_roots = len(supplements)
    runtime = _build_stdlib_runtime_identity()
    _require_runtime_identity_without_imports(runtime)
    route_registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    world = StrategicScenarioRouteWorld.from_rom(rom_bytes)
    corridors = derive_red_living_dex_provider_corridors(world)
    execution_identity = compose_red_living_dex_setup_execution_identity(
        source_commit=args.expected_source_commit,
        source_bundle_sha256=args.expected_source_bundle_sha256,
        route_registry_sha256=route_registry.registry_sha256,
        runtime_identity=runtime,
    )
    plan_document = _mapping(record["recipe_plan"])
    freeze_document = _mapping(record["freeze"])
    inventory = _inspect_recipe_plan(plan_document)
    corridor_binding_sha256s = tuple(item.binding_sha256 for item in corridors)
    _require_static_plan_join(
        record,
        execution_identity=execution_identity.private_dict(),
        execution_identity_sha256=execution_identity.identity_sha256,
        plan_document=plan_document,
        freeze_document=freeze_document,
        corridor_binding_sha256s=corridor_binding_sha256s,
        catalog_sha256=catalog_sha256,
        context_plan_sha256=context_plan_sha256,
        runtime_sha256=runtime.sha256,
        route_registry_sha256=route_registry.registry_sha256,
    )
    roots = _join_authenticated_root_bytes(
        inventory,
        contexts=contexts,
        supplements=supplements,
    )
    diagnostics.eligible_root_pool = len(contexts) + len(supplements)
    diagnostics.selected_roots = len(roots)
    claim_registry = open_fixed_account_claim_registry()
    with _existing_claim_registry_read_lease(claim_registry):
        diagnostics.roots_rejoined = _require_root_inventory(
            inventory.root_bindings,
            roots,
            claim_registry=claim_registry,
            diagnostics=diagnostics,
        )
        _require_protected_integrity(
            args,
            store=store,
            record=record,
            record_summary=summary,
            bridge_source_binding=bridge_binding,
            rom_path=rom_path,
            rom_sha256=rom_sha256,
            rom_bytes=rom_bytes,
            runtime_sha256=runtime.sha256,
            route_registry_sha256=route_registry.registry_sha256,
            plan_document=plan_document,
            freeze_document=freeze_document,
            corridor_binding_sha256s=corridor_binding_sha256s,
            catalog_sha256=catalog_sha256,
            context_plan_sha256=context_plan_sha256,
            ci_document=initial_ci,
        )
    _require_campaign_namespace_pristine(store, inventory.recipe_sha256s)
    prepared = PreparedRedLivingDexSetupBridge(
        plan_document=MappingProxyType(dict(plan_document)),
        freeze_document=MappingProxyType(dict(freeze_document)),
        roots=roots,
        corridor_binding_sha256s=corridor_binding_sha256s,
        record_summary=summary,
        private_plan_sha256=cast(str, record["private_plan_sha256"]),
        plan_source_commit=args.expected_source_commit,
        source_bundle_sha256=args.expected_source_bundle_sha256,
        bridge_source_commit=bridge_binding.bridge_source_commit,
        bridge_script_sha256=bridge_binding.bridge_script_sha256,
        freezer_script_sha256=bridge_binding.freezer_script_sha256,
        authentication_support_script_sha256=(
            bridge_binding.authentication_support_script_sha256
        ),
        exact_ci_run=args.exact_ci_run,
        exact_ci_attempt=args.exact_ci_attempt,
    )
    prepared.__post_init__()
    return prepared


def _require_authenticated_cli_invocation(
    args: argparse.Namespace,
) -> tuple[str, str, str]:
    """Require the exact token minted only by the authenticated CLI bootstrap."""

    try:
        expected = (
            _require_sha1(args.expected_bridge_source_commit, "bridge source"),
            _require_sha1(args.expected_source_commit, "plan source"),
            _require_sha256(args.expected_source_bundle_sha256, "source bundle"),
        )
    except BaseException:
        raise SetupBridgePreflightError("bridge_source_authentication") from None
    if expected != _BOOTSTRAP_IDENTITY:
        raise SetupBridgePreflightError("bridge_source_authentication")
    return expected


def _authenticate_bridge_source(args: argparse.Namespace) -> _BridgeSourceBinding:
    try:
        _require_project_import_origins()
        bridge_commit, plan_commit, source_bundle = (
            _require_authenticated_cli_invocation(args)
        )
        final_bootstrap_identity = _bootstrap_cli_identity(
            [
                "--expected-bridge-source-commit",
                bridge_commit,
                "--expected-source-commit",
                plan_commit,
                "--expected-source-bundle-sha256",
                source_bundle,
            ]
        )
        if final_bootstrap_identity != (bridge_commit, plan_commit, source_bundle):
            raise SetupBridgePreflightError("bridge_source_authentication")
        if os.environ.get(ENCOUNTER_LOG_VARIABLE, "").strip():
            raise SetupBridgePreflightError("bridge_source_authentication")
        freezer_script_sha256, authentication_support_script_sha256 = (
            _authenticate_frozen_script_closure(
                plan_commit=plan_commit,
                bridge_commit=bridge_commit,
            )
        )
        binding = _BridgeSourceBinding(
            bridge_source_commit=bridge_commit,
            bridge_script_sha256=hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest(),
            freezer_script_sha256=freezer_script_sha256,
            authentication_support_script_sha256=(
                authentication_support_script_sha256
            ),
        )
        binding.__post_init__()
        return binding
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("bridge_source_authentication") from None


def _authenticate_frozen_script_closure(
    *,
    plan_commit: str,
    bridge_commit: str,
) -> tuple[str, str]:
    """Prove every pre-existing script is byte-identical to the freeze source."""

    try:
        delta = _run_git_bytes(
            (
                "diff",
                "--no-ext-diff",
                "--name-status",
                "--no-renames",
                plan_commit,
                bridge_commit,
                "--",
                "scripts",
            )
        ).decode("utf-8", errors="strict")
        if delta != _EXPECTED_SCRIPT_DELTA:
            raise SetupBridgePreflightError("frozen_script_support_authentication")
        digests: list[str] = []
        for path in (
            _FREEZER_SCRIPT_PATH,
            _AUTHENTICATION_SUPPORT_SCRIPT_PATH,
        ):
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            current = path.read_bytes()
            frozen = _run_git_bytes(("show", f"{plan_commit}:{relative}"))
            if current != frozen:
                raise SetupBridgePreflightError(
                    "frozen_script_support_authentication"
                )
            digests.append(hashlib.sha256(current).hexdigest())
        return cast(tuple[str, str], tuple(digests))
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError(
            "frozen_script_support_authentication"
        ) from None


def _run_git_bytes(
    arguments: tuple[str, ...],
    *,
    maximum_bytes: int = 4_000_000,
) -> bytes:
    if maximum_bytes <= 0:
        raise SetupBridgePreflightError("frozen_script_support_authentication")
    if not _BOOTSTRAP_GIT_ATTRIBUTES_AUTHENTICATED:
        raise SetupBridgePreflightError("frozen_script_support_authentication")
    git = _bootstrap_require_executable(
        _BOOTSTRAP_GIT_EXECUTABLE,
        expected_sha256=_BOOTSTRAP_GIT_EXECUTABLE_SHA256,
        require_root_owned_path=True,
    )
    completed = subprocess.run(
        (
            str(git),
            f"--git-dir={_bootstrap_git_directory()}",
            f"--work-tree={PROJECT_ROOT}",
            "--no-replace-objects",
            *_BOOTSTRAP_PROJECT_GIT_CONFIG_OVERRIDES,
            *arguments,
        ),
        cwd=PROJECT_ROOT,
        env=_minimal_git_environment(),
        capture_output=True,
        check=False,
        timeout=10,
    )
    if completed.returncode != 0 or len(completed.stdout) > maximum_bytes:
        raise SetupBridgePreflightError("frozen_script_support_authentication")
    return cast(bytes, completed.stdout)


def _current_frozen_script_digests() -> tuple[str, str]:
    return (
        hashlib.sha256(_FREEZER_SCRIPT_PATH.read_bytes()).hexdigest(),
        hashlib.sha256(_AUTHENTICATION_SUPPORT_SCRIPT_PATH.read_bytes()).hexdigest(),
    )


def _load_freezer_support(binding: _BridgeSourceBinding) -> Mapping[str, object]:
    """Load the old action-free implementation only after source authentication."""

    global _FREEZER, _FREEZER_BINDING
    if _FREEZER is not None or _FREEZER_BINDING is not None:
        if _FREEZER is None or binding != _FREEZER_BINDING:
            raise SetupBridgePreflightError("frozen_script_support_authentication")
        return _FREEZER
    expected_digests = (
        binding.freezer_script_sha256,
        binding.authentication_support_script_sha256,
    )
    try:
        if _current_frozen_script_digests() != expected_digests:
            raise SetupBridgePreflightError("frozen_script_support_authentication")
        loaded = runpy.run_path(
            str(_FREEZER_SCRIPT_PATH),
            run_name="red_living_dex_setup_bridge_freezer_support",
        )
        if _current_frozen_script_digests() != expected_digests:
            raise SetupBridgePreflightError("frozen_script_support_authentication")
        _require_project_import_origins()
        _require_script_import_origins()
        for name in (
            "_authenticate_inputs",
            "_authenticate_supplemental_roots",
        ):
            if not callable(loaded.get(name)):
                raise SetupBridgePreflightError(
                    "frozen_script_support_authentication"
                )
        if (
            loaded.get("PLAN_RECORD_ID") != _PLAN_RECORD_ID
            or loaded.get("PLAN_RECORD_KIND") != _PLAN_RECORD_KIND
        ):
            raise SetupBridgePreflightError("frozen_script_support_authentication")
        _FREEZER = MappingProxyType(dict(loaded))
        _FREEZER_BINDING = binding
        return _FREEZER
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError(
            "frozen_script_support_authentication"
        ) from None


def _freezer_support() -> Mapping[str, object]:
    if _FREEZER is None:
        raise SetupBridgePreflightError("frozen_script_support_authentication")
    return _FREEZER


def _require_project_import_origins() -> None:
    if _PRELOADED_PROJECT_MODULES:
        raise SetupBridgePreflightError("project_import_authentication")
    package_root = (SRC_ROOT / "pokemon_red_completion").resolve()
    for name, module in tuple(sys.modules.items()):
        if name != "pokemon_red_completion" and not name.startswith(
            "pokemon_red_completion."
        ):
            continue
        _require_regular_import_origin(
            getattr(module, "__file__", None),
            expected_root=package_root,
            exact_path=None,
            stage="project_import_authentication",
        )


def _require_script_import_origins() -> None:
    for name, filename in (
        ("run_red_dual_capability_preflight", "run_red_dual_capability_preflight.py"),
        ("freeze_rootless_execution_manifest", "freeze_rootless_execution_manifest.py"),
        ("public_execution_manifest", "public_execution_manifest.py"),
        ("rootless_execution_manifest", "rootless_execution_manifest.py"),
    ):
        module = sys.modules.get(name)
        _require_regular_import_origin(
            getattr(module, "__file__", None),
            expected_root=SCRIPTS_ROOT.resolve(),
            exact_path=(SCRIPTS_ROOT / filename).resolve(),
            stage="script_import_authentication",
        )


def _require_regular_import_origin(
    raw_path: object,
    *,
    expected_root: Path,
    exact_path: Path | None,
    stage: str,
) -> None:
    if not isinstance(raw_path, str):
        raise SetupBridgePreflightError(stage)
    path = Path(raw_path)
    try:
        named = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        raise SetupBridgePreflightError(stage) from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(named.st_mode)
        or named.st_nlink != 1
        or not resolved.is_relative_to(expected_root)
        or (exact_path is not None and resolved != exact_path)
    ):
        raise SetupBridgePreflightError(stage)


def _require_exact_green_ci_run(
    exact_ci_run: int,
    exact_ci_attempt: int,
    *,
    source_commit: str,
) -> Mapping[str, object]:
    if (
        type(exact_ci_run) is not int  # noqa: E721
        or exact_ci_run <= 0
        or type(exact_ci_attempt) is not int  # noqa: E721
        or exact_ci_attempt <= 0
        or _SHA1.fullmatch(source_commit) is None
    ):
        raise SetupBridgePreflightError("bridge_ci_authentication")
    try:
        api_url = (
            f"https://api.github.com/repos/{_GITHUB_REPOSITORY}/actions/runs/"
            f"{exact_ci_run}/attempts/{exact_ci_attempt}"
        )
        document = _fetch_github_json(api_url)
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("bridge_ci_authentication") from None
    expected_url = f"https://github.com/{_GITHUB_REPOSITORY}/actions/runs/{exact_ci_run}"
    repository = document.get("repository") if isinstance(document, Mapping) else None
    if (
        not isinstance(document, Mapping)
        or document.get("id") != exact_ci_run
        or document.get("run_attempt") != exact_ci_attempt
        or document.get("head_sha") != source_commit
        or document.get("status") != "completed"
        or document.get("conclusion") != "success"
        or document.get("name") != _CI_WORKFLOW_NAME
        or document.get("path") != _CI_WORKFLOW_RELATIVE_PATH
        or document.get("event") != "push"
        or document.get("html_url") != expected_url
        or not isinstance(repository, Mapping)
        or repository.get("full_name") != _GITHUB_REPOSITORY
    ):
        raise SetupBridgePreflightError("bridge_ci_authentication")
    return MappingProxyType(
        {
            "attempt": exact_ci_attempt,
            "conclusion": "success",
            "databaseId": exact_ci_run,
            "event": "push",
            "headSha": source_commit,
            "path": _CI_WORKFLOW_RELATIVE_PATH,
            "repository": _GITHUB_REPOSITORY,
            "status": "completed",
            "url": expected_url,
            "workflowName": _CI_WORKFLOW_NAME,
        }
    )


def _fetch_github_json(url: str) -> Mapping[str, object]:
    """Read one bounded GitHub API document through an explicit trust path."""

    if (
        not isinstance(url, str)
        or not url.startswith(
            f"https://api.github.com/repos/{_GITHUB_REPOSITORY}/actions/runs/"
        )
        or any(
            os.environ.get(name, "").strip()
            for name in (
                "ALL_PROXY",
                "CURL_CA_BUNDLE",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "NO_PROXY",
                "PYTHONHTTPSVERIFY",
                "REQUESTS_CA_BUNDLE",
                "SSL_CERT_DIR",
                "SSL_CERT_FILE",
                "SSLKEYLOGFILE",
            )
        )
    ):
        raise SetupBridgePreflightError("bridge_ci_authentication")
    try:
        ssl_module, urllib_request = _secure_https_modules()

        ca_bytes = _bootstrap_read_regular(
            _BOOTSTRAP_CA_BUNDLE,
            maximum_bytes=1024 * 1024,
        )
        if hashlib.sha256(ca_bytes).hexdigest() != _BOOTSTRAP_CA_BUNDLE_SHA256:
            raise SetupBridgePreflightError("bridge_ci_authentication")
        context = ssl_module.SSLContext(ssl_module.PROTOCOL_TLS_CLIENT)
        context.check_hostname = True
        context.verify_mode = ssl_module.CERT_REQUIRED
        context.load_verify_locations(cadata=ca_bytes.decode("ascii", errors="strict"))

        def _reject_redirect(
            _self: object,
            *_args: object,
            **_kwargs: object,
        ) -> None:
            return None

        reject_redirects = type(
            "_RejectRedirects",
            (cast(Any, urllib_request.HTTPRedirectHandler),),
            {"redirect_request": _reject_redirect},
        )()

        opener = urllib_request.build_opener(
            urllib_request.ProxyHandler({}),
            urllib_request.HTTPSHandler(context=context),
            reject_redirects,
        )
        request = urllib_request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "pokemon-red-completion-agent-setup-bridge-v1",
                "X-GitHub-Api-Version": _GITHUB_API_VERSION,
            },
            method="GET",
        )
        with opener.open(request, timeout=30) as response:
            if response.getcode() != 200 or response.geturl() != url:
                raise SetupBridgePreflightError("bridge_ci_authentication")
            payload = response.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise SetupBridgePreflightError("bridge_ci_authentication")
        document = json.loads(
            payload,
            object_pairs_hook=_unique_json_object,
        )
        if not isinstance(document, Mapping) or any(
            not isinstance(key, str) for key in document
        ):
            raise SetupBridgePreflightError("bridge_ci_authentication")
        return MappingProxyType(dict(document))
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("bridge_ci_authentication") from None


def _secure_https_modules() -> tuple[ModuleType, ModuleType]:
    """Load SSL once after sealing its environment, then pin module identities."""

    global _SSL_EXTENSION_MODULE, _SSL_MODULE, _URLLIB_REQUEST_MODULE
    if (
        os.environ.get("OPENSSL_CONF") != os.devnull
        or any(
            name != "OPENSSL_CONF" and name.startswith("OPENSSL_")
            for name in os.environ
        )
    ):
        raise SetupBridgePreflightError("bridge_ci_authentication")
    if (
        _SSL_EXTENSION_MODULE is None
        and _SSL_MODULE is None
        and _URLLIB_REQUEST_MODULE is None
    ):
        if any(name in sys.modules for name in ("_ssl", "ssl", "urllib.request")):
            raise SetupBridgePreflightError("bridge_ci_authentication")
        try:
            ssl_module = __import__("ssl")
            urllib_request = __import__("urllib.request", fromlist=("request",))
            ssl_extension = sys.modules.get("_ssl")
        except BaseException:
            raise SetupBridgePreflightError("bridge_ci_authentication") from None
        if not all(
            isinstance(module, ModuleType)
            for module in (ssl_extension, ssl_module, urllib_request)
        ):
            raise SetupBridgePreflightError("bridge_ci_authentication")
        _require_stdlib_module_origin(cast(ModuleType, ssl_extension))
        _require_stdlib_module_origin(cast(ModuleType, ssl_module))
        _require_stdlib_module_origin(cast(ModuleType, urllib_request))
        _SSL_EXTENSION_MODULE = cast(ModuleType, ssl_extension)
        _SSL_MODULE = ssl_module
        _URLLIB_REQUEST_MODULE = urllib_request
    if (
        sys.modules.get("_ssl") is not _SSL_EXTENSION_MODULE
        or sys.modules.get("ssl") is not _SSL_MODULE
        or sys.modules.get("urllib.request") is not _URLLIB_REQUEST_MODULE
        or _SSL_MODULE is None
        or _URLLIB_REQUEST_MODULE is None
    ):
        raise SetupBridgePreflightError("bridge_ci_authentication")
    _require_stdlib_module_origin(cast(ModuleType, _SSL_EXTENSION_MODULE))
    _require_stdlib_module_origin(_SSL_MODULE)
    _require_stdlib_module_origin(_URLLIB_REQUEST_MODULE)
    return _SSL_MODULE, _URLLIB_REQUEST_MODULE


def _require_stdlib_module_origin(module: ModuleType) -> None:
    raw_path = getattr(module, "__file__", None)
    if not isinstance(raw_path, str):
        raise SetupBridgePreflightError("bridge_ci_authentication")
    try:
        path = Path(raw_path)
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
        base_prefix = Path(sys.base_prefix).resolve(strict=True)
    except OSError:
        raise SetupBridgePreflightError("bridge_ci_authentication") from None
    if (
        path.is_symlink()
        or resolved != path
        or not resolved.is_relative_to(base_prefix)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise SetupBridgePreflightError("bridge_ci_authentication")


def _authenticate_canonical_evidence(args: argparse.Namespace) -> Mapping[str, object]:
    """Anchor caller-supplied private bindings to the tracked canonical receipt."""

    try:
        metadata = _CANONICAL_EVIDENCE_PATH.lstat()
        if (
            _CANONICAL_EVIDENCE_PATH.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size <= 0
            or metadata.st_size > 64 * 1024
        ):
            raise SetupBridgePreflightError("canonical_evidence_authentication")
        payload = _CANONICAL_EVIDENCE_PATH.read_bytes()
        if hashlib.sha256(payload).hexdigest() != _CANONICAL_EVIDENCE_SHA256:
            raise SetupBridgePreflightError("canonical_evidence_authentication")
        document = json.loads(payload, object_pairs_hook=_unique_json_object)
        publication_value = document.get("publication")
        if not isinstance(publication_value, Mapping) or any(
            not isinstance(key, str) for key in publication_value
        ):
            raise SetupBridgePreflightError("canonical_evidence_authentication")
        publication = cast(Mapping[str, object], publication_value)
        if (
            document.get("schema")
            != "pokemon.red.living-dex-provider-plan-freeze-public-result.v1"
            or document.get("status")
            != "authenticated_action_free_provider_plan_frozen"
            or document.get("private_plan_sha256")
            != args.expected_private_plan_sha256
            or document.get("plan_manifest_sha256")
            != args.expected_plan_manifest_sha256
            or publication.get("merged_main_commit") != args.expected_source_commit
            or publication.get("source_bundle_sha256")
            != args.expected_source_bundle_sha256
            or document.get("slot_count") != 15
            or document.get("option_count") != 45
            or document.get("semantic_family_count") != 33
            or document.get("physical_origin_count") != 10
            or document.get("root_claims") != 0
            or document.get("controller_actions") != 0
            or document.get("emulator_frames") != 0
            or document.get("provider_executions") != 0
            or document.get("model_fits") != 0
            or document.get("outcomes") != 0
        ):
            raise SetupBridgePreflightError("canonical_evidence_authentication")
        return MappingProxyType(dict(document))
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("canonical_evidence_authentication") from None


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _open_store(args: argparse.Namespace) -> PrivateArtifactRoot:
    try:
        return open_private_root(
            args.private_root,
            repository_root=PROJECT_ROOT,
            git_worktree_probe=_hardened_git_worktree_probe,
        )
    except BaseException:
        raise SetupBridgePreflightError("private_namespace_authentication") from None


def _nearest_initialized_private_root(path: Path) -> Path:
    """Return the nearest exact private-store ancestor without scanning siblings."""

    try:
        candidate = Path(path)
        if not candidate.is_absolute():
            raise SetupBridgePreflightError("private_namespace_authentication")
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        if (
            candidate.is_symlink()
            or resolved != candidate
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
        ):
            raise SetupBridgePreflightError("private_namespace_authentication")
        for ancestor in resolved.parents:
            marker = ancestor / PRIVATE_ROOT_SENTINEL
            try:
                marker_metadata = marker.lstat()
            except FileNotFoundError:
                continue
            if (
                marker.is_symlink()
                or not stat.S_ISREG(marker_metadata.st_mode)
                or marker_metadata.st_nlink != 1
            ):
                raise SetupBridgePreflightError("private_namespace_authentication")
            return ancestor
    except SetupBridgePreflightError:
        raise
    except BaseException:
        pass
    raise SetupBridgePreflightError("private_namespace_authentication") from None


def _require_plan_namespace_binding(args: argparse.Namespace) -> None:
    """Bind the catalog and plan to the exact store that owns the sealed plan."""

    try:
        private_root = Path(args.private_root)
        resolved_root = private_root.resolve(strict=True)
        root_metadata = private_root.lstat()
        if (
            not private_root.is_absolute()
            or private_root.is_symlink()
            or resolved_root != private_root
            or not stat.S_ISDIR(root_metadata.st_mode)
        ):
            raise SetupBridgePreflightError("private_namespace_authentication")
        catalog_root = _nearest_initialized_private_root(Path(args.context_catalog))
        plan_root = _nearest_initialized_private_root(Path(args.context_plan))
        if catalog_root != resolved_root or plan_root != resolved_root:
            raise SetupBridgePreflightError("private_namespace_authentication")
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("private_namespace_authentication") from None


def _hardened_git_worktree_probe(path: Path) -> bool:
    """Check one private root without ambient executables, config, or environment."""

    try:
        candidate = Path(path)
        resolved = candidate.resolve(strict=True)
        metadata = resolved.lstat()
        if (
            not candidate.is_absolute()
            or candidate.is_symlink()
            or resolved != candidate
            or not stat.S_ISDIR(metadata.st_mode)
        ):
            raise SetupBridgePreflightError("private_namespace_authentication")
        marker_found = False
        for ancestor in (resolved, *resolved.parents):
            marker = ancestor / ".git"
            try:
                marker_metadata = marker.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                raise SetupBridgePreflightError(
                    "private_namespace_authentication"
                ) from None
            if marker.is_symlink() or not (
                stat.S_ISDIR(marker_metadata.st_mode)
                or (stat.S_ISREG(marker_metadata.st_mode) and marker_metadata.st_nlink == 1)
            ):
                raise SetupBridgePreflightError("private_namespace_authentication")
            marker_found = True
            break
        if not marker_found:
            return False
        git = _bootstrap_require_executable(
            _BOOTSTRAP_GIT_EXECUTABLE,
            expected_sha256=_BOOTSTRAP_GIT_EXECUTABLE_SHA256,
            require_root_owned_path=True,
        )
        completed = subprocess.run(
            (
                str(git),
                "--no-replace-objects",
                *_BOOTSTRAP_GIT_CONFIG_OVERRIDES,
                "-c",
                "core.bare=false",
                "-c",
                f"core.worktree={resolved}",
                "rev-parse",
                "--is-inside-work-tree",
            ),
            cwd=resolved,
            env=_minimal_git_environment(),
            capture_output=True,
            check=False,
            timeout=5,
        )
        if completed.returncode == 0:
            if completed.stdout == b"true\n":
                return True
            raise SetupBridgePreflightError("private_namespace_authentication")
        raise SetupBridgePreflightError("private_namespace_authentication")
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("private_namespace_authentication") from None


def _authenticate_plan_record(
    store: PrivateArtifactRoot,
    args: argparse.Namespace,
) -> tuple[dict[str, object], SealedRecordSummary]:
    try:
        record = store.find_sealed_record(
            _PLAN_RECORD_ID,
            expected_kind=_PLAN_RECORD_KIND,
        )
        if record is None:
            raise SetupBridgePreflightError("immutable_plan_record_absent")
        summary = record.summary
        document = record.read()
        validate_private_record(document)
        if set(document) != _PRIVATE_PLAN_KEYS:
            raise SetupBridgePreflightError("immutable_plan_authentication")
        expected_private_plan = _require_sha256(
            args.expected_private_plan_sha256,
            "private plan",
        )
        payload = dict(document)
        embedded_private_plan = payload.pop("private_plan_sha256", None)
        if (
            summary.manifest_sha256
            != _require_sha256(
                args.expected_plan_manifest_sha256,
                "plan manifest",
            )
            or embedded_private_plan != expected_private_plan
            or canonical_sha256(payload) != expected_private_plan
            or document["source_commit"] != args.expected_source_commit
            or document["source_bundle_sha256"]
            != args.expected_source_bundle_sha256
            or document["recipe_plan_sha256"]
            != args.expected_recipe_plan_sha256
            or document["execution_identity_sha256"]
            != args.expected_execution_identity_sha256
            or document["rom_sha256"] != POKEMON_RED_US_REV_0.sha256
            or document["status"]
            != "frozen_before_claim_controller_input_outcome_or_fit"
            or document["source_catalog_partition_reused_as_prospective_label"]
            is not False
            or any(document[key] != 0 for key in _ZERO_EFFECT_KEYS)
        ):
            raise SetupBridgePreflightError("immutable_plan_authentication")
        execution = _mapping(document["execution_identity"])
        recipe_plan = _mapping(document["recipe_plan"])
        freeze = _mapping(document["freeze"])
        if (
            canonical_sha256(execution) != document["execution_identity_sha256"]
            or recipe_plan.get("execution_identity") != execution
            or recipe_plan.get("execution_identity_sha256")
            != document["execution_identity_sha256"]
            or canonical_sha256(recipe_plan) != document["recipe_plan_sha256"]
            or freeze.get("recipe_plan_sha256") != document["recipe_plan_sha256"]
            or canonical_sha256(freeze) != document["freeze_sha256"]
        ):
            raise SetupBridgePreflightError("immutable_plan_authentication")
        return document, summary
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("immutable_plan_authentication") from None


def _require_static_plan_join(
    record: Mapping[str, object],
    *,
    execution_identity: Mapping[str, object],
    execution_identity_sha256: str,
    plan_document: Mapping[str, object],
    freeze_document: Mapping[str, object],
    corridor_binding_sha256s: tuple[str, ...],
    catalog_sha256: str,
    context_plan_sha256: str,
    runtime_sha256: str,
    route_registry_sha256: str,
) -> None:
    """Join every fact available without restoring a cartridge state."""

    try:
        recipe_plan_sha256 = canonical_sha256(dict(plan_document))
        _inspect_recipe_plan(plan_document)
        _inspect_freeze_document(
            freeze_document,
            recipe_plan_sha256=recipe_plan_sha256,
            corridor_binding_sha256s=corridor_binding_sha256s,
        )
        if (
            dict(execution_identity) != record.get("execution_identity")
            or execution_identity_sha256
            != record.get("execution_identity_sha256")
            or canonical_sha256(execution_identity) != execution_identity_sha256
            or dict(plan_document) != record.get("recipe_plan")
            or recipe_plan_sha256 != record.get("recipe_plan_sha256")
            or dict(freeze_document) != record.get("freeze")
            or canonical_sha256(freeze_document) != record.get("freeze_sha256")
            or catalog_sha256 != record.get("context_catalog_sha256")
            or context_plan_sha256 != record.get("context_plan_sha256")
            or runtime_sha256 != record.get("runtime_identity_sha256")
            or route_registry_sha256 != record.get("route_registry_sha256")
        ):
            raise SetupBridgePreflightError("reconstructed_plan_join")
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("reconstructed_plan_join") from None


def _join_authenticated_root_bytes(
    inventory: _RecipePlanInventory,
    *,
    contexts: tuple[Any, ...],
    supplements: tuple[Any, ...],
) -> tuple[RedLivingDexAuthenticatedSetupRoot, ...]:
    """Select exact frozen bytes from authenticated files without an emulator."""

    try:
        pool: dict[str, RedLivingDexAuthenticatedSetupRoot] = {}
        for private in contexts:
            capture = private.capture
            envelope_bytes = (
                json.dumps(
                    capture.envelope.to_dict(),
                    ensure_ascii=True,
                    sort_keys=True,
                ).encode("ascii")
                + b"\n"
            )
            root = RedLivingDexAuthenticatedSetupRoot(
                root_consumption_sha256=private.root_consumption_sha256,
                state_bytes=capture.state_bytes,
                envelope_bytes=envelope_bytes,
            )
            _add_root_to_pool(pool, root)
        for supplement in supplements:
            root = supplement.root
            if not isinstance(root, RedLivingDexAuthenticatedSetupRoot):
                raise SetupBridgePreflightError("root_inventory_join")
            root.__post_init__()
            _add_root_to_pool(pool, root)
        selected: list[RedLivingDexAuthenticatedSetupRoot] = []
        for binding in inventory.root_bindings:
            selected_root = pool.get(binding.root_consumption_sha256)
            if (
                selected_root is None
                or selected_root.state_sha256 != binding.root_state_sha256
                or selected_root.envelope_sha256 != binding.root_envelope_sha256
            ):
                raise SetupBridgePreflightError("root_inventory_join")
            selected.append(selected_root)
        return tuple(selected)
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("root_inventory_join") from None


def _add_root_to_pool(
    pool: dict[str, RedLivingDexAuthenticatedSetupRoot],
    root: RedLivingDexAuthenticatedSetupRoot,
) -> None:
    root.__post_init__()
    existing = pool.get(root.root_consumption_sha256)
    if existing is not None and (
        existing.state_bytes != root.state_bytes
        or existing.envelope_bytes != root.envelope_bytes
    ):
        raise SetupBridgePreflightError("root_inventory_join")
    pool[root.root_consumption_sha256] = root


def _require_root_inventory(
    bindings: tuple[_FrozenRootBinding, ...],
    roots: tuple[RedLivingDexAuthenticatedSetupRoot, ...],
    *,
    claim_registry: Path,
    diagnostics: _DiagnosticState,
) -> int:
    if len(roots) != len(bindings):
        raise SetupBridgePreflightError("root_inventory_join")
    for binding, root in zip(bindings, roots, strict=True):
        root.__post_init__()
        if (
            root.root_consumption_sha256 != binding.root_consumption_sha256
            or root.state_sha256 != binding.root_state_sha256
            or root.envelope_sha256 != binding.root_envelope_sha256
        ):
            raise SetupBridgePreflightError("root_inventory_join")
        if not root_claim_is_available(
            claim_registry,
            root.root_consumption_sha256,
        ):
            raise SetupBridgePreflightError("root_claim_availability")
        diagnostics.logical_claims_available += 1
        if not root_claim_is_available(
            claim_registry,
            root.physical_root_sha256,
        ):
            raise SetupBridgePreflightError("root_claim_availability")
        diagnostics.physical_claims_available += 1
    return len(roots)


def _require_protected_integrity(
    args: argparse.Namespace,
    *,
    store: PrivateArtifactRoot,
    record: Mapping[str, object],
    record_summary: SealedRecordSummary,
    bridge_source_binding: _BridgeSourceBinding,
    rom_path: Path,
    rom_sha256: str,
    rom_bytes: bytes,
    runtime_sha256: str,
    route_registry_sha256: str,
    plan_document: Mapping[str, object],
    freeze_document: Mapping[str, object],
    corridor_binding_sha256s: tuple[str, ...],
    catalog_sha256: str,
    context_plan_sha256: str,
    ci_document: Mapping[str, object],
) -> None:
    try:
        final_bridge = _authenticate_bridge_source(args)
        final_ci = _require_exact_green_ci_run(
            args.exact_ci_run,
            args.exact_ci_attempt,
            source_commit=bridge_source_binding.bridge_source_commit,
        )
        _authenticate_canonical_evidence(args)
        final_record, final_summary = _authenticate_plan_record(store, args)
        final_runtime = _build_stdlib_runtime_identity()
        _require_runtime_identity_without_imports(final_runtime)
        final_route_registry = load_strategic_navigation_scenario_registry(
            PROJECT_ROOT
        )
        final_world = StrategicScenarioRouteWorld.from_rom(rom_bytes)
        final_corridors = derive_red_living_dex_provider_corridors(final_world)
        final_execution = compose_red_living_dex_setup_execution_identity(
            source_commit=args.expected_source_commit,
            source_bundle_sha256=args.expected_source_bundle_sha256,
            route_registry_sha256=final_route_registry.registry_sha256,
            runtime_identity=final_runtime,
        )
        _require_static_plan_join(
            final_record,
            execution_identity=final_execution.private_dict(),
            execution_identity_sha256=final_execution.identity_sha256,
            plan_document=plan_document,
            freeze_document=freeze_document,
            corridor_binding_sha256s=tuple(
                item.binding_sha256 for item in final_corridors
            ),
            catalog_sha256=catalog_sha256,
            context_plan_sha256=context_plan_sha256,
            runtime_sha256=final_runtime.sha256,
            route_registry_sha256=final_route_registry.registry_sha256,
        )
        if (
            final_bridge != bridge_source_binding
            or final_record != dict(record)
            or final_summary != record_summary
            or verify_rom(rom_path).sha256 != rom_sha256
            or rom_sha256 != POKEMON_RED_US_REV_0.sha256
            or hashlib.sha256(rom_bytes).hexdigest() != rom_sha256
            or final_ci != ci_document
            or final_runtime.sha256 != runtime_sha256
            or record["runtime_identity_sha256"] != final_runtime.sha256
            or final_route_registry.registry_sha256 != route_registry_sha256
            or record["route_registry_sha256"] != final_route_registry.registry_sha256
            or tuple(item.binding_sha256 for item in final_corridors)
            != corridor_binding_sha256s
        ):
            raise SetupBridgePreflightError("protected_input_integrity")
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("protected_input_integrity") from None


def _require_campaign_namespace_pristine(
    store: PrivateArtifactRoot,
    recipe_sha256s: tuple[str, ...],
) -> None:
    try:
        if (
            store.find_sealed_record(
                RED_LIVING_DEX_RECIPE_PLAN_RECORD_ID,
                expected_kind=RED_LIVING_DEX_RECIPE_PLAN_RECORD_KIND,
            )
            is not None
        ):
            raise SetupBridgePreflightError("campaign_namespace_not_pristine")
        for ordinal, recipe_sha256 in enumerate(recipe_sha256s):
            episode_id = (
                f"red-living-dex-recipe-{ordinal:02d}-{recipe_sha256[:20]}"
            )
            terminal_id = (
                "red-living-dex-recipe-terminal-"
                f"{recipe_sha256[:24]}"
            )
            if (
                store.inspect_episode_state(episode_id).status != "absent"
                or store.find_sealed_record(
                    terminal_id,
                    expected_kind=RED_LIVING_DEX_RECIPE_TERMINAL_RECORD_KIND,
                )
                is not None
            ):
                raise SetupBridgePreflightError("campaign_namespace_not_pristine")
    except SetupBridgePreflightError:
        raise
    except BaseException:
        raise SetupBridgePreflightError("campaign_namespace_not_pristine") from None


def _authenticate_inputs(
    args: argparse.Namespace,
    source_commit: str,
    source_bundle: str,
) -> tuple[Path, str, bytes, tuple[Any, ...], str, str]:
    try:
        nested = _mapping(_freezer_support()["_AUTHENTICATION_SUPPORT"])
        function = _bind_read_only_input_authenticator(
            nested.get("_authenticate_inputs")
        )
        return cast(
            tuple[Path, str, bytes, tuple[Any, ...], str, str],
            function(args, source_commit, source_bundle),
        )
    except BaseException:
        raise SetupBridgePreflightError("private_input_authentication") from None


def _authenticate_supplemental_roots(
    state_paths: tuple[Path, ...],
    expected_physical_root_sha256s: tuple[str, ...],
) -> tuple[Any, ...]:
    function = cast(Any, _freezer_support()["_authenticate_supplemental_roots"])
    try:
        return cast(
            tuple[Any, ...],
            function(state_paths, expected_physical_root_sha256s),
        )
    except BaseException:
        raise SetupBridgePreflightError("supplemental_root_authentication") from None


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise SetupBridgePreflightError("immutable_plan_authentication")
    return cast(Mapping[str, object], value)


def _require_sha1(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA1.fullmatch(value) is None:
        raise SetupBridgePreflightError(
            "bridge_source_authentication" if "source" in subject else "arguments"
        )
    return value


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        del subject
        raise SetupBridgePreflightError("arguments")
    return value


if __name__ == "__main__":
    _release_post_bootstrap_failure_boundary()
    raise SystemExit(main())
