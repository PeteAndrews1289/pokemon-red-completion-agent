#!/usr/bin/env python3
"""Authenticate one Red living-Dex slot before any claim or runtime exists.

Run this preflight-only command with the pinned base interpreter under
``-I -S -B``.  The standard-library bootstrap authenticates the current clean
published commit and every importable project byte before adding the source
tree to ``sys.path``.  The project layer then opens one sealed producer record
and exactly one selected state/envelope pair.  This script has no ROM argument
and no execution mode.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import ssl
import stat
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Never

SCRIPT_PATH = Path(__file__).resolve(strict=True)
PROJECT_ROOT = SCRIPT_PATH.parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
SCRIPT_RELATIVE_PATH = "scripts/preflight_red_living_dex_claim_first_invocation.py"

_BOOTSTRAP_FAILURE_SCHEMA = (
    "pokemon.red.living-dex-claim-first-invocation-preflight-failure.v1"
)
_BOOTSTRAP_PYTHON = Path(
    "/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/"
    "Python.framework/Versions/3.14/bin/python3.14"
)
_BOOTSTRAP_PYTHON_SHA256 = (
    "cbf84109626aa1013bbe408fbb9590bd0f1c1548f038b2221c6b8b87de26ca43"
)
_BOOTSTRAP_BASE_PREFIX = Path(
    "/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/"
    "Python.framework/Versions/3.14"
)
_BOOTSTRAP_GIT = Path("/Library/Developer/CommandLineTools/usr/bin/git")
_BOOTSTRAP_GIT_SHA256 = (
    "74b90b9f97ec79bfe7886a4fc6132533b3e1014ef4195d28abd1ca9bf321f34a"
)
_MAXIMUM_GIT_OUTPUT = 128 * 1024 * 1024
_MAXIMUM_SOURCE_FILE = 16 * 1024 * 1024
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BOOTSTRAP_IDENTITY: tuple[str, str, int, int] | None = None
_GITHUB_HOST = "api.github.com"
_GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
_GITHUB_API_VERSION = "2022-11-28"
_CI_WORKFLOW_NAME = "CI"
_CI_WORKFLOW_PATH = ".github/workflows/ci.yml"
_MAXIMUM_CI_RESPONSE = 256 * 1024


class _BootstrapError(RuntimeError):
    pass


def _failure(stage: str) -> dict[str, object]:
    return {
        "behavior_draws": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "learner_outcomes": 0,
        "model_fits": 0,
        "model_predictions": 0,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "producer_executions": 0,
        "resolver_constructions": 0,
        "root_claims": 0,
        "schema": _BOOTSTRAP_FAILURE_SCHEMA,
        "setup_campaign_calls": 0,
        "stage": stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure",
        "status": "failed_closed",
        "teacher_queries": 0,
    }


def _emit(document: dict[str, object]) -> None:
    print(
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _minimal_git_environment() -> dict[str, str]:
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


def _git_directory() -> Path:
    marker = PROJECT_ROOT / ".git"
    try:
        metadata = marker.lstat()
        if marker.is_symlink():
            raise _BootstrapError
        if stat.S_ISDIR(metadata.st_mode):
            return marker.resolve(strict=True)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise _BootstrapError
        line = marker.read_text(encoding="ascii").strip()
        prefix = "gitdir: "
        if not line.startswith(prefix):
            raise _BootstrapError
        candidate = Path(line[len(prefix) :])
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir():
            raise _BootstrapError
        return resolved
    except (OSError, UnicodeError):
        raise _BootstrapError from None


def _read_regular(
    path: Path,
    *,
    maximum_bytes: int,
    single_link: bool = True,
) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        named = path.lstat()
        resolved = path.resolve(strict=True)
        if (
            path.is_symlink()
            or resolved != path
            or not stat.S_ISREG(named.st_mode)
            or (single_link and named.st_nlink != 1)
            or not 0 <= named.st_size <= maximum_bytes
        ):
            raise _BootstrapError
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != named.st_dev
            or opened.st_ino != named.st_ino
            or opened.st_size != named.st_size
            or opened.st_mtime_ns != named.st_mtime_ns
            or opened.st_ctime_ns != named.st_ctime_ns
        ):
            raise _BootstrapError
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise _BootstrapError
        finished = os.fstat(descriptor)
        if (
            total != opened.st_size
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
        ):
            raise _BootstrapError
        return b"".join(chunks)
    except (OSError, RuntimeError):
        raise _BootstrapError from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _require_executable(
    path: Path,
    *,
    expected_sha256: str,
    root_owned: bool,
) -> Path:
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.lstat()
        if (
            not resolved.is_absolute()
            or resolved.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise _BootstrapError
        if root_owned:
            for candidate in (resolved, *resolved.parents):
                item = candidate.lstat()
                if item.st_uid != 0 or stat.S_IMODE(item.st_mode) & 0o022:
                    raise _BootstrapError
        payload = _read_regular(
            resolved,
            maximum_bytes=128 * 1024 * 1024,
            single_link=False,
        )
    except OSError:
        raise _BootstrapError from None
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise _BootstrapError
    return resolved


def _git(arguments: tuple[str, ...], *, maximum_bytes: int = _MAXIMUM_GIT_OUTPUT) -> bytes:
    git = _require_executable(
        _BOOTSTRAP_GIT,
        expected_sha256=_BOOTSTRAP_GIT_SHA256,
        root_owned=True,
    )
    try:
        completed = subprocess.run(
            (
                str(git),
                f"--git-dir={_git_directory()}",
                f"--work-tree={PROJECT_ROOT}",
                "--no-replace-objects",
                "-c",
                "core.attributesFile=/dev/null",
                "-c",
                "core.bare=false",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                f"core.worktree={PROJECT_ROOT}",
                *arguments,
            ),
            cwd=PROJECT_ROOT,
            env=_minimal_git_environment(),
            capture_output=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        raise _BootstrapError from None
    if completed.returncode != 0 or len(completed.stdout) > maximum_bytes:
        raise _BootstrapError
    return completed.stdout


def _require_interpreter() -> None:
    if (
        not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.flags.dont_write_bytecode
        or any(name in sys.modules for name in ("site", "sitecustomize", "usercustomize"))
    ):
        raise _BootstrapError
    raw_base = getattr(sys, "_base_executable", None)
    if not isinstance(raw_base, str):
        raise _BootstrapError
    try:
        executable = Path(sys.executable).resolve(strict=True)
        base_executable = Path(raw_base).resolve(strict=True)
        expected_prefix = _BOOTSTRAP_BASE_PREFIX.resolve(strict=True)
        prefixes = tuple(
            Path(value).resolve(strict=True)
            for value in (
                sys.prefix,
                sys.exec_prefix,
                sys.base_prefix,
                sys.base_exec_prefix,
            )
        )
    except OSError:
        raise _BootstrapError from None
    if (
        executable != _BOOTSTRAP_PYTHON
        or base_executable != _BOOTSTRAP_PYTHON
        or any(value != expected_prefix for value in prefixes)
    ):
        raise _BootstrapError
    _require_executable(
        _BOOTSTRAP_PYTHON,
        expected_sha256=_BOOTSTRAP_PYTHON_SHA256,
        root_owned=False,
    )
    for raw in sys.path:
        try:
            candidate = Path(raw)
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError, TypeError):
            raise _BootstrapError from None
        if (
            not raw
            or not candidate.is_absolute()
            or resolved.is_relative_to(PROJECT_ROOT)
            or not resolved.is_relative_to(expected_prefix)
        ):
            raise _BootstrapError


def _require_environment() -> None:
    forbidden_exact = {
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
    }
    if any(os.environ.get(name, "").strip() for name in forbidden_exact) or any(
        name.startswith("OPENSSL_") for name in os.environ
    ):
        raise _BootstrapError
    if os.environ.get("POKEMON_RED_ENCOUNTER_LOG", "").strip():
        raise _BootstrapError


def _tracked_source_inventory(commit: str) -> set[str]:
    payload = _git(
        (
            "ls-tree",
            "-r",
            "-z",
            "--name-only",
            commit,
            "--",
            "pyproject.toml",
            "src",
        )
    )
    result: set[str] = set()
    for raw in payload.split(b"\0"):
        if not raw:
            continue
        try:
            relative = raw.decode("ascii")
        except UnicodeDecodeError:
            raise _BootstrapError from None
        if relative in result:
            raise _BootstrapError
        result.add(relative)
    if "pyproject.toml" not in result or not any(
        value.startswith("src/pokemon_red_completion/") for value in result
    ):
        raise _BootstrapError
    return result


def _filesystem_project_sources(expected: set[str]) -> set[str]:
    result = {"pyproject.toml"}
    expected_directories = {
        parent.as_posix()
        for relative in expected
        for parent in Path(relative).parents
        if parent not in {Path("."), Path("src")}
    }
    try:
        pyproject = PROJECT_ROOT / "pyproject.toml"
        _read_regular(pyproject, maximum_bytes=_MAXIMUM_SOURCE_FILE)
        metadata_root = SRC_ROOT / "pokemon_red_completion_agent.egg-info"
        for path in SRC_ROOT.rglob("*"):
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            if path.is_symlink():
                raise _BootstrapError
            if path.is_dir():
                if path == metadata_root:
                    continue
                if relative in expected_directories or path.name == "__pycache__":
                    continue
                raise _BootstrapError
            if path.parent == metadata_root:
                if (
                    not path.is_file()
                    or path.suffix in {".py", ".pyc", ".pyo", ".pth", ".so"}
                    or stat.S_IMODE(path.lstat().st_mode) & 0o022
                ):
                    raise _BootstrapError
                continue
            if path.parent.name == "__pycache__" and path.suffix in {".pyc", ".pyo"}:
                continue
            if path.name == ".DS_Store":
                continue
            if not path.is_file():
                raise _BootstrapError
            result.add(relative)
    except (OSError, ValueError):
        raise _BootstrapError from None
    return result


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _require_exact_green_ci_document(
    document: object,
    *,
    commit: str,
    exact_ci_run: int,
    exact_ci_attempt: int,
) -> None:
    repository = document.get("repository") if isinstance(document, dict) else None
    expected_url = f"https://github.com/{_GITHUB_REPOSITORY}/actions/runs/{exact_ci_run}"
    if (
        not isinstance(document, dict)
        or document.get("id") != exact_ci_run
        or document.get("run_attempt") != exact_ci_attempt
        or document.get("head_sha") != commit
        or document.get("status") != "completed"
        or document.get("conclusion") != "success"
        or document.get("name") != _CI_WORKFLOW_NAME
        or document.get("path") != _CI_WORKFLOW_PATH
        or document.get("event") != "push"
        or document.get("html_url") != expected_url
        or not isinstance(repository, dict)
        or repository.get("full_name") != _GITHUB_REPOSITORY
    ):
        raise _BootstrapError


def _require_exact_green_ci(
    *,
    commit: str,
    exact_ci_run: int,
    exact_ci_attempt: int,
) -> None:
    if exact_ci_run <= 0 or exact_ci_attempt <= 0:
        raise _BootstrapError
    connection: http.client.HTTPSConnection | None = None
    try:
        connection = http.client.HTTPSConnection(
            _GITHUB_HOST,
            timeout=15,
            context=ssl.create_default_context(),
        )
        path = (
            f"/repos/{_GITHUB_REPOSITORY}/actions/runs/{exact_ci_run}"
            f"/attempts/{exact_ci_attempt}"
        )
        connection.request(
            "GET",
            path,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "pokemon-red-completion-agent-claim-first-preflight",
                "X-GitHub-Api-Version": _GITHUB_API_VERSION,
            },
        )
        response = connection.getresponse()
        payload = response.read(_MAXIMUM_CI_RESPONSE + 1)
        if response.status != 200 or len(payload) > _MAXIMUM_CI_RESPONSE:
            raise _BootstrapError
        document = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_json_object)
        _require_exact_green_ci_document(
            document,
            commit=commit,
            exact_ci_run=exact_ci_run,
            exact_ci_attempt=exact_ci_attempt,
        )
    except _BootstrapError:
        raise
    except BaseException:
        raise _BootstrapError from None
    finally:
        if connection is not None:
            connection.close()


def _authenticate_current_source(argv: list[str]) -> tuple[str, str, int, int]:
    _require_interpreter()
    _require_environment()
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--exact-ci-run", required=True, type=int)
    parser.add_argument("--exact-ci-attempt", required=True, type=int)
    try:
        parsed, _unknown = parser.parse_known_args(argv)
    except SystemExit:
        raise _BootstrapError from None
    commit = parsed.expected_source_commit
    bundle = parsed.expected_source_bundle_sha256
    exact_ci_run = parsed.exact_ci_run
    exact_ci_attempt = parsed.exact_ci_attempt
    if _SHA1.fullmatch(commit) is None or _SHA256.fullmatch(bundle) is None:
        raise _BootstrapError
    head = _git(("rev-parse", "--verify", "HEAD^{commit}"), maximum_bytes=128)
    if head.decode("ascii", errors="strict").strip() != commit:
        raise _BootstrapError
    if _git(
        (
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--ignore-submodules=all",
        ),
        maximum_bytes=1024 * 1024,
    ):
        raise _BootstrapError
    refs = _git(
        (
            "for-each-ref",
            f"--contains={commit}",
            "--format=%(refname)",
            "refs/remotes",
        ),
        maximum_bytes=64 * 1024,
    ).decode("ascii", errors="strict")
    if not any(
        ref.startswith("refs/remotes/") and not ref.endswith("/HEAD")
        for ref in refs.splitlines()
    ):
        raise _BootstrapError
    tracked = _tracked_source_inventory(commit)
    if _filesystem_project_sources(tracked) != tracked:
        raise _BootstrapError
    for relative in sorted(tracked):
        current = _read_regular(
            PROJECT_ROOT / relative,
            maximum_bytes=_MAXIMUM_SOURCE_FILE,
        )
        committed = _git(
            ("show", f"{commit}:{relative}"),
            maximum_bytes=_MAXIMUM_SOURCE_FILE,
        )
        if current != committed:
            raise _BootstrapError
    script = _read_regular(SCRIPT_PATH, maximum_bytes=4 * 1024 * 1024)
    if script != _git(
        ("show", f"{commit}:{SCRIPT_RELATIVE_PATH}"),
        maximum_bytes=4 * 1024 * 1024,
    ):
        raise _BootstrapError
    _require_exact_green_ci(
        commit=commit,
        exact_ci_run=exact_ci_run,
        exact_ci_attempt=exact_ci_attempt,
    )
    return commit, bundle, exact_ci_run, exact_ci_attempt


class _NumpyTypingPlaceholder:
    @classmethod
    def __class_getitem__(cls, _item: object) -> type[_NumpyTypingPlaceholder]:
        return cls


_NUMPY_SENTINEL: ModuleType | None = None
_NUMPY_TYPING_SENTINEL: ModuleType | None = None
_NUMPY_ATTRIBUTE_ACCESSES = 0


def _blocked_numpy_attribute(_name: str) -> Never:
    global _NUMPY_ATTRIBUTE_ACCESSES
    _NUMPY_ATTRIBUTE_ACCESSES += 1
    raise _BootstrapError


def _install_numpy_sentinel() -> None:
    global _NUMPY_SENTINEL, _NUMPY_TYPING_SENTINEL
    if any(name == "numpy" or name.startswith("numpy.") for name in sys.modules):
        raise _BootstrapError
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
        or _NUMPY_ATTRIBUTE_ACCESSES != 0
    ):
        raise RuntimeError("third_party_execution_boundary")
    for name, module in tuple(sys.modules.items()):
        if module in {_NUMPY_SENTINEL, _NUMPY_TYPING_SENTINEL}:
            continue
        if name.startswith("numpy.") or any(
            name == root or name.startswith(f"{root}.")
            for root in ("pyboy", "PIL", "sdl2", "sdl2dll")
        ):
            raise RuntimeError("third_party_execution_boundary")


if __name__ == "__main__":
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
            _emit(_failure("bootstrap_source_authentication"))
            raise SystemExit(1)
        print(
            f"usage: {_BOOTSTRAP_PYTHON} -I -S -B {SCRIPT_RELATIVE_PATH} [options]"
        )
        raise SystemExit(0)
    try:
        _BOOTSTRAP_IDENTITY = _authenticate_current_source(sys.argv[1:])
        _install_numpy_sentinel()
        sys.dont_write_bytecode = True
        sys.pycache_prefix = str(PROJECT_ROOT / f".claim-first-pycache-{os.urandom(32).hex()}")
        sys.path.insert(0, str(SRC_ROOT))
    except BaseException:
        _emit(_failure("bootstrap_source_authentication"))
        raise SystemExit(1) from None
elif sys.flags.no_site:
    raise _BootstrapError

from pokemon_red_completion.captured_progress import (  # noqa: E402
    parse_captured_progress,
)
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    fixed_account_claim_registry_root,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PrivateArtifactRoot,
    open_private_root,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (  # noqa: E402
    RedLivingDexClaimFirstInvocationError,
    RedLivingDexCurrentConsumerBinding,
    RedLivingDexFrozenProducerBinding,
    RedLivingDexLoadedProducerSlot,
    preflight_red_living_dex_claim_first_invocation,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (  # noqa: E402
    RedLivingDexAuthenticatedSetupRoot,
)

_PLAN_RECORD_ID = "red-living-dex-provider-plan-v1"
_PLAN_RECORD_KIND = "red-living-dex-provider-plan-v1"
_MAXIMUM_STATE_BYTES = 16 * 1024 * 1024
_MAXIMUM_ENVELOPE_BYTES = 4 * 1024 * 1024


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RedLivingDexClaimFirstInvocationError("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--exact-ci-run", required=True, type=int)
    parser.add_argument("--exact-ci-attempt", required=True, type=int)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--expected-producer-plan-sha256", required=True)
    parser.add_argument("--expected-producer-private-plan-sha256", required=True)
    parser.add_argument("--expected-producer-manifest-sha256", required=True)
    parser.add_argument("--ordinal", required=True, type=int)
    parser.add_argument("--selected-state", required=True, type=Path)
    parser.add_argument("--selected-envelope", required=True, type=Path)
    parser.add_argument("--expected-selected-physical-root-sha256", required=True)
    parser.add_argument("--claim-registry", type=Path)
    return parser


def _git_worktree_probe(path: Path) -> bool:
    try:
        completed = subprocess.run(
            (
                str(_BOOTSTRAP_GIT),
                "--no-replace-objects",
                "-c",
                "core.attributesFile=/dev/null",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "rev-parse",
                "--is-inside-work-tree",
            ),
            cwd=path,
            env=_minimal_git_environment(),
            capture_output=True,
            check=False,
            timeout=5,
        )
        return completed.returncode == 0 and completed.stdout == b"true\n"
    except BaseException:
        raise RedLivingDexClaimFirstInvocationError(
            "private_namespace_authentication"
        ) from None


def _open_store(path: Path) -> PrivateArtifactRoot:
    try:
        return open_private_root(
            path,
            repository_root=PROJECT_ROOT,
            git_worktree_probe=_git_worktree_probe,
        )
    except BaseException:
        raise RedLivingDexClaimFirstInvocationError(
            "private_namespace_authentication"
        ) from None


def _require_selected_path(path: Path, *, private_root: Path) -> Path:
    try:
        resolved_root = private_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
        if (
            not path.is_absolute()
            or path.is_symlink()
            or resolved != path
            or not resolved.is_relative_to(resolved_root)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise RedLivingDexClaimFirstInvocationError("selected_root_authentication")
        return resolved
    except RedLivingDexClaimFirstInvocationError:
        raise
    except BaseException:
        raise RedLivingDexClaimFirstInvocationError(
            "selected_root_authentication"
        ) from None


def _selected_loader(
    args: argparse.Namespace,
    store: PrivateArtifactRoot,
):  # type: ignore[no-untyped-def]
    state_path = _require_selected_path(args.selected_state, private_root=args.private_root)
    envelope_path = _require_selected_path(
        args.selected_envelope,
        private_root=args.private_root,
    )
    if state_path == envelope_path:
        raise RedLivingDexClaimFirstInvocationError("selected_root_authentication")

    def load(ordinal: int) -> RedLivingDexLoadedProducerSlot:
        try:
            record = store.find_sealed_record(
                _PLAN_RECORD_ID,
                expected_kind=_PLAN_RECORD_KIND,
            )
            if record is None:
                raise ValueError("producer record absent")
            document = record.read()
            plan = document.get("recipe_plan")
            if not isinstance(plan, dict):
                raise ValueError("producer plan absent")
            recipes = plan.get("recipes")
            if not isinstance(recipes, list) or not 0 <= ordinal < len(recipes):
                raise ValueError("selected recipe absent")
            recipe = recipes[ordinal]
            if not isinstance(recipe, dict):
                raise ValueError("selected recipe differs")
            logical_root = recipe.get("root_consumption_sha256")
            if not isinstance(logical_root, str) or _SHA256.fullmatch(logical_root) is None:
                raise ValueError("selected root differs")
            state_bytes = _read_regular(
                state_path,
                maximum_bytes=_MAXIMUM_STATE_BYTES,
            )
            source_envelope = _read_regular(
                envelope_path,
                maximum_bytes=_MAXIMUM_ENVELOPE_BYTES,
            )
            envelope = parse_captured_progress(source_envelope, state_bytes=state_bytes)
            envelope_bytes = (
                json.dumps(
                    envelope.to_dict(),
                    ensure_ascii=True,
                    sort_keys=True,
                ).encode("ascii")
                + b"\n"
            )
            root = RedLivingDexAuthenticatedSetupRoot(
                root_consumption_sha256=logical_root,
                state_bytes=state_bytes,
                envelope_bytes=envelope_bytes,
            )
            if root.physical_root_sha256 != args.expected_selected_physical_root_sha256:
                raise ValueError("selected physical root differs")
            return RedLivingDexLoadedProducerSlot(record, root)
        except RedLivingDexClaimFirstInvocationError:
            raise
        except BaseException:
            raise RedLivingDexClaimFirstInvocationError(
                "selected_root_authentication"
            ) from None

    return load


def main(argv: list[str] | None = None) -> int:
    try:
        if _BOOTSTRAP_IDENTITY is None:
            raise RedLivingDexClaimFirstInvocationError("bootstrap_source_authentication")
        args = _parser().parse_args(argv)
        if (
            args.expected_source_commit,
            args.expected_source_bundle_sha256,
            args.exact_ci_run,
            args.exact_ci_attempt,
        ) != _BOOTSTRAP_IDENTITY:
            raise RedLivingDexClaimFirstInvocationError("bootstrap_source_authentication")
        _require_no_third_party_execution()
        store = _open_store(args.private_root)
        consumer = RedLivingDexCurrentConsumerBinding(
            source_commit=args.expected_source_commit,
            source_bundle_sha256=args.expected_source_bundle_sha256,
            exact_ci_run=args.exact_ci_run,
            exact_ci_attempt=args.exact_ci_attempt,
        )
        producer = RedLivingDexFrozenProducerBinding(
            producer_plan_sha256=args.expected_producer_plan_sha256,
            producer_private_plan_sha256=args.expected_producer_private_plan_sha256,
            producer_manifest_sha256=args.expected_producer_manifest_sha256,
            ordinal=args.ordinal,
        )
        registry = args.claim_registry or fixed_account_claim_registry_root()
        receipt = preflight_red_living_dex_claim_first_invocation(
            PROJECT_ROOT,
            consumer=consumer,
            producer=producer,
            producer_slot_loader=_selected_loader(args, store),
            claim_registry=registry,
        )
        _require_no_third_party_execution()
        _emit(receipt.public_dict())
        return 0
    except RedLivingDexClaimFirstInvocationError as error:
        _emit(_failure(error.stage))
        return 1
    except BaseException:
        _emit(_failure("unexpected_failure"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
