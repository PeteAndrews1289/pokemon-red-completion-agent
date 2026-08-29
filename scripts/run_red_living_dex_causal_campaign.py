#!/usr/bin/env python3
"""Execute or recover one admitted Red causal train assignment.

The default mode preserves the historical one-campaign recovery surface.  The
clustered mode accepts only train ordinals 0 through 7 from the exact frozen
8+4 schedule; no development ordinal is parseable.  Neither mode accepts a
behavior choice, private identity digest, teacher, model, Crystal cartridge, or
full-game replay.  Red remains unopened on terminal recovery, and the selected
causal runtime opens only after its behavior commitment is durable.
"""

# ruff: noqa: E402 -- authenticate the project before importing it.

from __future__ import annotations

import sys

_EARLY_BOOTSTRAP_FAILURE = '{"stage":"bootstrap_source_authentication","status":"failed_closed"}\n'
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
    sys.stdout.write(_EARLY_BOOTSTRAP_FAILURE)
    raise SystemExit(1)

import os

_EARLY_FORBIDDEN_ENVIRONMENT = {
    "ALL_PROXY",
    "CTLOG_FILE",
    "CURL_CA_BUNDLE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "NO_PROXY",
    "PYSDL2_DLL_PATH",
    "PYTHONHTTPSVERIFY",
    "RANDFILE",
    "REQUESTS_CA_BUNDLE",
    "SDL_DYNAMIC_API",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "SSLKEYLOGFILE",
}
if __name__ == "__main__" and any(
    value.strip()
    and (
        key in _EARLY_FORBIDDEN_ENVIRONMENT or key.startswith("DYLD_") or key.startswith("OPENSSL_")
    )
    for key, value in os.environ.items()
):
    os.write(1, _EARLY_BOOTSTRAP_FAILURE.encode("ascii"))
    raise SystemExit(1)
if __name__ == "__main__":
    os.environ["OPENSSL_CONF"] = os.devnull

import argparse
import hashlib
import http.client
import json
import re
import ssl
import stat
import subprocess
from contextlib import suppress
from pathlib import Path
from types import ModuleType
from typing import Never

SCRIPT_PATH = Path(__file__).resolve(strict=True)
PROJECT_ROOT = SCRIPT_PATH.parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
VENV_SITE_PACKAGES = PROJECT_ROOT / ".venv/lib/python3.14/site-packages"
SCRIPT_RELATIVE_PATH = "scripts/run_red_living_dex_causal_campaign.py"

_BOOTSTRAP_PYTHON = Path(
    "/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/"
    "Python.framework/Versions/3.14/bin/python3.14"
)
_BOOTSTRAP_PYTHON_SHA256 = "cbf84109626aa1013bbe408fbb9590bd0f1c1548f038b2221c6b8b87de26ca43"
_BOOTSTRAP_BASE_PREFIX = Path(
    "/opt/homebrew/Cellar/python@3.14/3.14.3_1/Frameworks/Python.framework/Versions/3.14"
)
_BOOTSTRAP_ORIGINAL_EXECUTABLE = (
    _BOOTSTRAP_BASE_PREFIX / "Resources/Python.app/Contents/MacOS/Python"
)
_BOOTSTRAP_GIT = Path("/Library/Developer/CommandLineTools/usr/bin/git")
_BOOTSTRAP_GIT_SHA256 = "74b90b9f97ec79bfe7886a4fc6132533b3e1014ef4195d28abd1ca9bf321f34a"
_BOOTSTRAP_CA_BUNDLE = Path("/opt/homebrew/etc/ca-certificates/cert.pem")
_BOOTSTRAP_CA_BUNDLE_SHA256 = "e0547ad4423c097fa7a9ba57464634a7ed331072a49cfbcad8fcc396bbc7bb15"
_GITHUB_HOST = "api.github.com"
_GITHUB_REPOSITORY = "PeteAndrews1289/pokemon-red-completion-agent"
_GITHUB_API_VERSION = "2022-11-28"
_CI_WORKFLOW_NAME = "CI"
_CI_WORKFLOW_PATH = ".github/workflows/ci.yml"
_MAXIMUM_SOURCE_FILE = 16 * 1024 * 1024
_MAXIMUM_SOURCE_TOTAL = 128 * 1024 * 1024
_MAXIMUM_GIT_OUTPUT = 128 * 1024 * 1024
_MAXIMUM_CI_RESPONSE = 256 * 1024
_SOURCE_BUNDLE_SCHEMA = "pokemon-red-executable-source-bundle-v2"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_BOOTSTRAP_IDENTITY: tuple[str, str, int, int] | None = None
_RUNTIME_STAGE = None
_RUNTIME_FINDER = None
_NUMPY_SENTINEL: ModuleType | None = None
_NUMPY_TYPING_SENTINEL: ModuleType | None = None
_NUMPY_ATTRIBUTE_ACCESSES = 0


class _BootstrapError(RuntimeError):
    pass


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


def _read_regular(
    path: Path,
    *,
    maximum_bytes: int,
    single_link: bool = True,
) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
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
        if not line.startswith("gitdir: "):
            raise _BootstrapError
        candidate = Path(line.removeprefix("gitdir: "))
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir():
            raise _BootstrapError
        return resolved
    except (OSError, UnicodeError):
        raise _BootstrapError from None


def _require_no_local_git_attributes() -> None:
    git_directory = _git_directory()
    candidates = [git_directory / "info/attributes"]
    commondir = git_directory / "commondir"
    if commondir.exists():
        try:
            relative = commondir.read_text(encoding="ascii").strip()
            common = (git_directory / relative).resolve(strict=True)
        except (OSError, UnicodeError):
            raise _BootstrapError from None
        if not common.is_dir():
            raise _BootstrapError
        candidates.append(common / "info/attributes")
    if any(os.path.lexists(path) for path in candidates):
        raise _BootstrapError


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
        or "site" in sys.modules
        or any(
            name == "pokemon_red_completion" or name.startswith("pokemon_red_completion.")
            for name in sys.modules
        )
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
    original = tuple(sys.orig_argv)
    if (
        len(original) < 5
        or Path(original[0]).resolve(strict=True) != _BOOTSTRAP_ORIGINAL_EXECUTABLE
        or original[1:4] != ("-I", "-S", "-B")
        or Path(original[4]).resolve(strict=True) != SCRIPT_PATH
        or original[5:] != tuple(sys.argv[1:])
    ):
        raise _BootstrapError
    for raw in sys.path:
        candidate = Path(raw)
        resolved = candidate.resolve(strict=False)
        if (
            not raw
            or not candidate.is_absolute()
            or resolved.is_relative_to(PROJECT_ROOT)
            or not resolved.is_relative_to(expected_prefix)
        ):
            raise _BootstrapError
    for name in (
        "_hashlib",
        "_ssl",
        "hashlib",
        "http.client",
        "json",
        "ssl",
        "subprocess",
    ):
        module = sys.modules.get(name)
        raw_origin = getattr(module, "__file__", None)
        if not isinstance(raw_origin, str):
            raise _BootstrapError
        try:
            origin = Path(raw_origin).resolve(strict=True)
        except (OSError, TypeError):
            raise _BootstrapError from None
        if not origin.is_relative_to(expected_prefix):
            raise _BootstrapError


def _require_environment(
    *,
    authenticated_pysdl2_dll_path: Path | None = None,
) -> None:
    allowed_pysdl2_dll_path: str | None = None
    if authenticated_pysdl2_dll_path is not None:
        try:
            resolved = authenticated_pysdl2_dll_path.resolve(strict=True)
            metadata = authenticated_pysdl2_dll_path.lstat()
            if (
                not authenticated_pysdl2_dll_path.is_absolute()
                or resolved != authenticated_pysdl2_dll_path
                or authenticated_pysdl2_dll_path.is_symlink()
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise OSError("authenticated SDL directory differs")
        except (OSError, TypeError, ValueError):
            raise _BootstrapError from None
        allowed_pysdl2_dll_path = str(authenticated_pysdl2_dll_path)
    if any(
        value.strip()
        and (
            (
                key in _EARLY_FORBIDDEN_ENVIRONMENT
                and not (
                    key == "PYSDL2_DLL_PATH"
                    and allowed_pysdl2_dll_path is not None
                    and value == allowed_pysdl2_dll_path
                )
            )
            or key.startswith("DYLD_")
            or (key.startswith("OPENSSL_") and not (key == "OPENSSL_CONF" and value == os.devnull))
        )
        for key, value in os.environ.items()
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
        item.startswith("src/pokemon_red_completion/") for item in result
    ):
        raise _BootstrapError
    return result


def _committed_red_source_bundle_sha256(commit: str) -> str:
    listing = _git(
        (
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            commit,
            "--",
            "pyproject.toml",
            "src/pokemon_red_completion",
        )
    )
    entries: list[dict[str, object]] = []
    paths: set[str] = set()
    total_bytes = 0
    for record in listing.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, _object_id = metadata.split(b" ", 2)
            relative = raw_path.decode("ascii")
        except (UnicodeDecodeError, ValueError):
            raise _BootstrapError from None
        if (
            mode not in {b"100644", b"100755"}
            or object_type != b"blob"
            or relative in paths
            or not (
                relative == "pyproject.toml" or relative.startswith("src/pokemon_red_completion/")
            )
            or "\\" in relative
        ):
            raise _BootstrapError
        blob = _git(
            ("show", f"{commit}:{relative}"),
            maximum_bytes=_MAXIMUM_SOURCE_FILE,
        )
        total_bytes += len(blob)
        if total_bytes > _MAXIMUM_SOURCE_TOTAL:
            raise _BootstrapError
        paths.add(relative)
        entries.append(
            {
                "bytes": len(blob),
                "mode": mode.decode("ascii"),
                "path": relative,
                "sha256": hashlib.sha256(blob).hexdigest(),
            }
        )
    entries.sort(key=lambda entry: str(entry["path"]))
    if (
        not entries
        or entries[0]["path"] != "pyproject.toml"
        or not any(
            str(entry["path"]).startswith("src/pokemon_red_completion/") for entry in entries
        )
    ):
        raise _BootstrapError
    payload = (
        json.dumps(
            {
                "files": entries,
                "schema": _SOURCE_BUNDLE_SCHEMA,
            },
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    return hashlib.sha256(payload).hexdigest()


def _filesystem_project_sources(expected: set[str]) -> set[str]:
    result = {"pyproject.toml"}
    expected_directories = {
        parent.as_posix()
        for relative in expected
        for parent in Path(relative).parents
        if parent not in {Path("."), Path("src")}
    }
    try:
        _read_regular(PROJECT_ROOT / "pyproject.toml", maximum_bytes=_MAXIMUM_SOURCE_FILE)
        metadata_root = SRC_ROOT / "pokemon_red_completion_agent.egg-info"
        for path in SRC_ROOT.rglob("*"):
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            if path.is_symlink():
                raise _BootstrapError
            if path.is_dir():
                if path == metadata_root:
                    continue
                if path.name == "__pycache__":
                    raise _BootstrapError
                if relative in expected_directories:
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
            if path.suffix in {".pyc", ".pyo"}:
                raise _BootstrapError
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


def _require_exact_green_ci(
    *,
    commit: str,
    exact_ci_run: int,
    exact_ci_attempt: int,
) -> None:
    connection: http.client.HTTPSConnection | None = None
    try:
        ca_bundle = _BOOTSTRAP_CA_BUNDLE.resolve(strict=True)
        if (
            ca_bundle != _BOOTSTRAP_CA_BUNDLE
            or hashlib.sha256(
                _read_regular(
                    ca_bundle,
                    maximum_bytes=4 * 1024 * 1024,
                    single_link=False,
                )
            ).hexdigest()
            != _BOOTSTRAP_CA_BUNDLE_SHA256
        ):
            raise _BootstrapError
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        context.load_verify_locations(cafile=str(ca_bundle))
        connection = http.client.HTTPSConnection(
            _GITHUB_HOST,
            timeout=15,
            context=context,
        )
        connection.request(
            "GET",
            (
                f"/repos/{_GITHUB_REPOSITORY}/actions/runs/{exact_ci_run}"
                f"/attempts/{exact_ci_attempt}"
            ),
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "pokemon-red-causal-campaign-execution",
                "X-GitHub-Api-Version": _GITHUB_API_VERSION,
            },
        )
        response = connection.getresponse()
        payload = response.read(_MAXIMUM_CI_RESPONSE + 1)
        if response.status != 200 or len(payload) > _MAXIMUM_CI_RESPONSE:
            raise _BootstrapError
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
        )
        repository = document.get("repository") if isinstance(document, dict) else None
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
            or document.get("head_branch") != "main"
            or document.get("html_url")
            != f"https://github.com/{_GITHUB_REPOSITORY}/actions/runs/{exact_ci_run}"
            or not isinstance(repository, dict)
            or repository.get("full_name") != _GITHUB_REPOSITORY
        ):
            raise _BootstrapError
    except _BootstrapError:
        raise
    except BaseException:
        raise _BootstrapError from None
    finally:
        if connection is not None:
            connection.close()


def _require_source_state(
    *,
    commit: str,
    exact_ci_run: int,
    exact_ci_attempt: int,
) -> None:
    _require_no_local_git_attributes()
    head = _git(("rev-parse", "--verify", "HEAD^{commit}"), maximum_bytes=128)
    origin_main = _git(
        ("rev-parse", "--verify", "refs/remotes/origin/main^{commit}"),
        maximum_bytes=128,
    )
    if (
        head.decode("ascii", errors="strict").strip() != commit
        or origin_main.decode("ascii", errors="strict").strip() != commit
    ):
        raise _BootstrapError
    tracked = _tracked_source_inventory(commit)
    if _filesystem_project_sources(tracked) != tracked:
        raise _BootstrapError
    for relative in sorted(tracked):
        if _read_regular(
            PROJECT_ROOT / relative,
            maximum_bytes=_MAXIMUM_SOURCE_FILE,
        ) != _git(
            ("show", f"{commit}:{relative}"),
            maximum_bytes=_MAXIMUM_SOURCE_FILE,
        ):
            raise _BootstrapError
    if _read_regular(SCRIPT_PATH, maximum_bytes=4 * 1024 * 1024) != _git(
        ("show", f"{commit}:{SCRIPT_RELATIVE_PATH}"),
        maximum_bytes=4 * 1024 * 1024,
    ):
        raise _BootstrapError
    _require_exact_green_ci(
        commit=commit,
        exact_ci_run=exact_ci_run,
        exact_ci_attempt=exact_ci_attempt,
    )


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
    identity = (
        parsed.expected_source_commit,
        parsed.expected_source_bundle_sha256,
        parsed.exact_ci_run,
        parsed.exact_ci_attempt,
    )
    if (
        _GIT_COMMIT.fullmatch(identity[0]) is None
        or _SHA256.fullmatch(identity[1]) is None
        or identity[2] <= 0
        or identity[3] <= 0
    ):
        raise _BootstrapError
    if _committed_red_source_bundle_sha256(identity[0]) != identity[1]:
        raise _BootstrapError
    _require_source_state(
        commit=identity[0],
        exact_ci_run=identity[2],
        exact_ci_attempt=identity[3],
    )
    return identity


class _NumpyTypingPlaceholder:
    @classmethod
    def __class_getitem__(
        cls,
        _item: object,
    ) -> type[_NumpyTypingPlaceholder]:
        return cls


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


def _require_project_import_boundary() -> None:
    if (
        _BOOTSTRAP_IDENTITY is None
        or _NUMPY_SENTINEL is None
        or _NUMPY_TYPING_SENTINEL is None
        or sys.modules.get("numpy") is not _NUMPY_SENTINEL
        or sys.modules.get("numpy.typing") is not _NUMPY_TYPING_SENTINEL
        or _NUMPY_ATTRIBUTE_ACCESSES != 0
    ):
        raise _BootstrapError
    tracked = _tracked_source_inventory(_BOOTSTRAP_IDENTITY[0])
    for name, module in tuple(sys.modules.items()):
        if module in {_NUMPY_SENTINEL, _NUMPY_TYPING_SENTINEL}:
            continue
        if name.startswith("numpy.") or any(
            name == root or name.startswith(f"{root}.")
            for root in (
                "OpenGL",
                "PIL",
                "cython",
                "glfw",
                "openal",
                "pyboy",
                "sdl2",
                "sdl2dll",
            )
        ):
            raise _BootstrapError
        if name == "pokemon_red_completion" or name.startswith("pokemon_red_completion."):
            raw_origin = getattr(module, "__file__", None)
            if not isinstance(raw_origin, str):
                raise _BootstrapError
            try:
                origin = Path(raw_origin).resolve(strict=True)
                relative = origin.relative_to(PROJECT_ROOT).as_posix()
            except (OSError, TypeError, ValueError):
                raise _BootstrapError from None
            if origin.suffix != ".py" or relative not in tracked:
                raise _BootstrapError


def _enable_authenticated_project() -> None:
    root = str(SRC_ROOT)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.insert(0, root)


def _enable_authenticated_third_party_search(
    closure: ExecutionRuntimeClosure,
) -> None:
    try:
        site_packages = closure.site_packages.resolve(strict=True)
        original_site = VENV_SITE_PACKAGES.resolve(strict=True)
        if (
            site_packages != closure.site_packages
            or site_packages == original_site
            or not site_packages.is_dir()
            or stat.S_IMODE(site_packages.lstat().st_mode) & 0o022
            or str(original_site) in sys.path
        ):
            raise _BootstrapError
    except OSError:
        raise _BootstrapError from None
    root = str(site_packages)
    while root in sys.path:
        sys.path.remove(root)
    sys.path.append(root)


def _remove_numpy_sentinel_for_postclaim_runtime() -> None:
    if (
        _NUMPY_SENTINEL is None
        or _NUMPY_TYPING_SENTINEL is None
        or sys.modules.get("numpy") is not _NUMPY_SENTINEL
        or sys.modules.get("numpy.typing") is not _NUMPY_TYPING_SENTINEL
        or _NUMPY_ATTRIBUTE_ACCESSES != 0
    ):
        raise _BootstrapError
    del sys.modules["numpy"]
    del sys.modules["numpy.typing"]


if __name__ == "__main__":
    if "-h" in sys.argv[1:] or "--help" in sys.argv[1:]:
        if not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
            print('{"stage":"bootstrap_source_authentication","status":"failed_closed"}')
            raise SystemExit(1)
        print(f"usage: {_BOOTSTRAP_PYTHON} -I -S -B {SCRIPT_RELATIVE_PATH} [options]")
        raise SystemExit(0)
    try:
        _BOOTSTRAP_IDENTITY = _authenticate_current_source(sys.argv[1:])
        _install_numpy_sentinel()
        _enable_authenticated_project()
    except BaseException:
        print('{"stage":"bootstrap_source_authentication","status":"failed_closed"}')
        raise SystemExit(1) from None
elif sys.flags.no_site:
    raise _BootstrapError
else:
    while str(SRC_ROOT) in sys.path:
        sys.path.remove(str(SRC_ROOT))
    sys.path.insert(0, str(SRC_ROOT))

from pokemon_red_completion.execution_runtime_closure import (
    AuthenticatedRuntimeFinder,
    ExecutionRuntimeClosure,
    prepare_authenticated_runtime_stage,
    require_authenticated_runtime_finder,
    require_loaded_runtime_origins,
)
from pokemon_red_completion.private_artifacts import (
    PRIVATE_ROOT_SENTINEL,
    open_private_root,
)
from pokemon_red_completion.red_living_dex_causal_campaign import (
    load_red_living_dex_causal_campaign,
)
from pokemon_red_completion.red_living_dex_causal_invocation import (
    RedLivingDexCausalInvocationError,
    bind_red_living_dex_authenticated_consumer,
    execute_red_living_dex_causal_campaign,
)
from pokemon_red_completion.red_living_dex_claim_first_invocation import (
    RED_LIVING_DEX_PROVIDER_PLAN_RECORD_ID,
    RED_LIVING_DEX_PROVIDER_PLAN_RECORD_KIND,
    RedLivingDexCurrentConsumerBinding,
    RedLivingDexLoadedProducerSlot,
)
from pokemon_red_completion.red_living_dex_clustered_train_runner import (
    RED_LIVING_DEX_CLUSTERED_TRAIN_PREFLIGHT_SCHEMA,
    RED_LIVING_DEX_CLUSTERED_TRAIN_RECEIPT_SCHEMA,
    RedLivingDexClusteredTrainRunnerError,
    RedLivingDexClusteredTrainSelection,
    execute_red_living_dex_clustered_train_assignment,
    load_red_living_dex_clustered_train_selection,
    preflight_red_living_dex_clustered_train_assignment,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
    RedLivingDexSetupEffectMeter,
)

if __name__ == "__main__":
    try:
        _require_project_import_boundary()
        _RUNTIME_STAGE = prepare_authenticated_runtime_stage(VENV_SITE_PACKAGES)
        _RUNTIME_FINDER = AuthenticatedRuntimeFinder(_RUNTIME_STAGE.closure)
        sys.meta_path.insert(0, _RUNTIME_FINDER)
        _enable_authenticated_third_party_search(_RUNTIME_STAGE.closure)
        _remove_numpy_sentinel_for_postclaim_runtime()
    except BaseException:
        if _RUNTIME_STAGE is not None:
            with suppress(BaseException):
                _RUNTIME_STAGE.close()
        print('{"stage":"bootstrap_source_authentication","status":"failed_closed"}')
        raise SystemExit(1) from None

RESULT_SCHEMA = "pokemon.red.living-dex-causal-campaign-execution-result.v1"
FAILURE_SCHEMA = "pokemon.red.living-dex-causal-campaign-execution-failure.v1"

_MAXIMUM_STATE_BYTES = 16 * 1024 * 1024
_MAXIMUM_ENVELOPE_BYTES = 4 * 1024 * 1024


class CausalCampaignExecutionError(RuntimeError):
    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise CausalCampaignExecutionError("argument_authentication")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--exact-ci-run", required=True, type=int)
    parser.add_argument("--exact-ci-attempt", required=True, type=int)
    parser.add_argument("--selected-state", required=True, type=Path)
    parser.add_argument("--selected-envelope", required=True, type=Path)
    parser.add_argument("--rom", type=Path)
    parser.add_argument(
        "--clustered-train-ordinal",
        choices=range(8),
        type=int,
    )
    parser.add_argument("--clustered-preflight-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "argument_authentication"
    invocation_returned = False
    preflight = False
    meter = RedLivingDexSetupEffectMeter()
    try:
        args = _parser().parse_args(argv)
        _require_arguments(args)
        if (
            args.expected_source_commit,
            args.expected_source_bundle_sha256,
            args.exact_ci_run,
            args.exact_ci_attempt,
        ) != _BOOTSTRAP_IDENTITY:
            raise CausalCampaignExecutionError("bootstrap_source_authentication")
        consumer_binding = RedLivingDexCurrentConsumerBinding(
            source_commit=args.expected_source_commit,
            source_bundle_sha256=args.expected_source_bundle_sha256,
            exact_ci_run=args.exact_ci_run,
            exact_ci_attempt=args.exact_ci_attempt,
        )
        if _BOOTSTRAP_IDENTITY is None:
            raise CausalCampaignExecutionError("bootstrap_source_authentication")
        consumer = bind_red_living_dex_authenticated_consumer(
            consumer_binding,
            bootstrap_identity=_BOOTSTRAP_IDENTITY,
        )
        stage = "private_namespace_authentication"
        store = open_private_root(
            args.private_root,
            repository_root=PROJECT_ROOT,
            git_worktree_probe=_filesystem_git_worktree_probe,
        )
        state_path = _require_private_regular_path(
            args.selected_state,
            private_root=args.private_root,
        )
        envelope_path = _require_private_regular_path(
            args.selected_envelope,
            private_root=args.private_root,
        )
        if state_path == envelope_path:
            raise CausalCampaignExecutionError("selected_root_authentication")
        clustered = args.clustered_train_ordinal is not None
        if clustered:
            selection = load_red_living_dex_clustered_train_selection(
                store,
                args.clustered_train_ordinal,
            )
            clustered_loader = _clustered_selected_loader(
                selection,
                private_root=args.private_root,
                state_path=state_path,
                envelope_path=envelope_path,
            )
            preflight = args.clustered_preflight_only
            if preflight:
                stage = "clustered_train_preflight"
                receipt = preflight_red_living_dex_clustered_train_assignment(
                    PROJECT_ROOT,
                    store,
                    consumer=consumer,
                    ordinal=args.clustered_train_ordinal,
                    root_loader=clustered_loader,
                    meter=meter,
                )
            else:
                stage = "clustered_train_execution"
                receipt = execute_red_living_dex_clustered_train_assignment(
                    PROJECT_ROOT,
                    store,
                    consumer=consumer,
                    ordinal=args.clustered_train_ordinal,
                    root_loader=clustered_loader,
                    rom_path=args.rom,
                    meter=meter,
                )
        else:
            campaign = load_red_living_dex_causal_campaign(store)
            loader = _selected_loader(
                store,
                logical_root_sha256=campaign.logical_root_sha256,
                physical_root_sha256=campaign.physical_root_sha256,
                private_root=args.private_root,
                state_path=state_path,
                envelope_path=envelope_path,
            )
            stage = "campaign_execution"
            receipt = execute_red_living_dex_causal_campaign(
                PROJECT_ROOT,
                store,
                consumer=consumer,
                producer_slot_loader=loader,
                rom_path=args.rom,
                meter=meter,
            )
        invocation_returned = True
        stage = "post_execution_source_authentication"
        _require_runtime_postcheck()
        _require_source_state(
            commit=args.expected_source_commit,
            exact_ci_run=args.exact_ci_run,
            exact_ci_attempt=args.exact_ci_attempt,
        )
        checkpoint = meter.checkpoint()
        if (
            checkpoint.model_fits != 0
            or checkpoint.model_predictions != 0
            or checkpoint.teacher_queries != 0
            or checkpoint.learner_labels != 0
            or checkpoint.learner_outcomes != 0
            or checkpoint.behavior_draws != 0
            or checkpoint.provider_executions not in {0, 1}
        ):
            raise CausalCampaignExecutionError("forbidden_authority_effect")
    except CausalCampaignExecutionError as error:
        stage = error.stage
    except RedLivingDexCausalInvocationError as error:
        stage = error.stage
    except RedLivingDexClusteredTrainRunnerError:
        stage = "clustered_train_authentication"
    except BaseException:
        stage = "unexpected_failure"
    else:
        public = receipt.public_dict()
        checkpoint = meter.checkpoint()
        if preflight:
            public.update(
                {
                    "automatic_retry_allowed": False,
                    "result_schema": RED_LIVING_DEX_CLUSTERED_TRAIN_PREFLIGHT_SCHEMA,
                    "retry_allowed": False,
                    "status": "one_clustered_train_assignment_ready",
                }
            )
            print(_encoded(public))
            return 0
        causal = receipt.causal
        public.update(
            {
                "automatic_retry_allowed": False,
                "campaign_kind": (
                    "clustered_train"
                    if clustered
                    else "historical_single_campaign"
                ),
                "causal_behavior_commitments": 0 if causal is None else 1,
                "controller_actions": checkpoint.controller_actions,
                "emulator_frames": checkpoint.emulator_frames,
                "model_fits": checkpoint.model_fits,
                "model_predictions": checkpoint.model_predictions,
                "provider_executions": checkpoint.provider_executions,
                "result_schema": (
                    RED_LIVING_DEX_CLUSTERED_TRAIN_RECEIPT_SCHEMA
                    if clustered
                    else RESULT_SCHEMA
                ),
                "retry_allowed": False,
                "root_claims_metered_setup_only": checkpoint.root_claims,
                "status": (
                    "preinput_recovery_required_no_automatic_retry"
                    if causal is not None and causal.retry_allowed
                    else (
                        "one_causal_campaign_settled"
                        if public["causal_train_example_recorded"]
                        else "one_causal_campaign_terminal_without_train_example"
                    )
                ),
                "setup_behavior_draws_metered": checkpoint.behavior_draws,
                "teacher_queries": checkpoint.teacher_queries,
            }
        )
        print(_encoded(public))
        return 1 if causal is not None and causal.retry_allowed else 0

    try:
        _require_runtime_postcheck()
    except BaseException:
        stage = "runtime_postauthentication"

    print(
        _encoded(
            _failure(
                stage,
                meter=meter,
                invocation_returned=invocation_returned,
            )
        )
    )
    return 1


def _require_runtime_postcheck() -> None:
    if __name__ != "__main__":
        return
    if (
        _RUNTIME_STAGE is None
        or _RUNTIME_FINDER is None
        or not isinstance(_RUNTIME_FINDER, AuthenticatedRuntimeFinder)
    ):
        raise CausalCampaignExecutionError("runtime_postauthentication")
    _require_environment(
        authenticated_pysdl2_dll_path=(
            _RUNTIME_STAGE.closure.site_packages / "sdl2dll/dll"
        )
    )
    require_authenticated_runtime_finder(_RUNTIME_STAGE.closure)
    require_loaded_runtime_origins(_RUNTIME_STAGE.closure)


def _filesystem_git_worktree_probe(path: Path) -> bool:
    """Reject filesystem-visible worktree ancestors without invoking Git."""

    try:
        resolved = path.resolve(strict=True)
        return any(os.path.lexists(ancestor / ".git") for ancestor in (resolved, *resolved.parents))
    except OSError:
        raise CausalCampaignExecutionError("private_namespace_authentication") from None


def _require_arguments(args: argparse.Namespace) -> None:
    if (
        not isinstance(args.expected_source_commit, str)
        or _GIT_COMMIT.fullmatch(args.expected_source_commit) is None
        or not isinstance(args.expected_source_bundle_sha256, str)
        or _SHA256.fullmatch(args.expected_source_bundle_sha256) is None
        or type(args.exact_ci_run) is not int  # noqa: E721
        or args.exact_ci_run <= 0
        or type(args.exact_ci_attempt) is not int  # noqa: E721
        or args.exact_ci_attempt <= 0
        or (
            args.clustered_train_ordinal is not None
            and (
                type(args.clustered_train_ordinal) is not int  # noqa: E721
                or not 0 <= args.clustered_train_ordinal < 8
            )
        )
        or (
            args.clustered_preflight_only
            and (
                args.clustered_train_ordinal is None
                or args.rom is not None
            )
        )
        or (not args.clustered_preflight_only and not isinstance(args.rom, Path))
    ):
        raise CausalCampaignExecutionError("argument_authentication")


def _selected_loader(
    store,  # type: ignore[no-untyped-def]
    *,
    logical_root_sha256: str,
    physical_root_sha256: str,
    private_root: Path,
    state_path: Path,
    envelope_path: Path,
):  # type: ignore[no-untyped-def]
    def load(ordinal: int) -> RedLivingDexLoadedProducerSlot:
        try:
            record = store.find_sealed_record(
                RED_LIVING_DEX_PROVIDER_PLAN_RECORD_ID,
                expected_kind=RED_LIVING_DEX_PROVIDER_PLAN_RECORD_KIND,
            )
            if record is None:
                raise ValueError("producer record absent")
            current_state_path = _require_private_regular_path(
                state_path,
                private_root=private_root,
            )
            current_envelope_path = _require_private_regular_path(
                envelope_path,
                private_root=private_root,
            )
            if current_state_path == current_envelope_path:
                raise ValueError("selected files alias")
            root = RedLivingDexAuthenticatedSetupRoot(
                root_consumption_sha256=logical_root_sha256,
                state_bytes=_read_private_regular(
                    current_state_path,
                    maximum_bytes=_MAXIMUM_STATE_BYTES,
                ),
                envelope_bytes=_read_private_regular(
                    current_envelope_path,
                    maximum_bytes=_MAXIMUM_ENVELOPE_BYTES,
                ),
            )
            if root.physical_root_sha256 != physical_root_sha256:
                raise ValueError("selected physical root differs")
            document = record.read()
            recipe_plan = document.get("recipe_plan")
            recipes = recipe_plan.get("recipes") if isinstance(recipe_plan, dict) else None
            if not isinstance(recipes, list) or not 0 <= ordinal < len(recipes):
                raise ValueError("selected recipe absent")
            recipe = recipes[ordinal]
            if (
                not isinstance(recipe, dict)
                or recipe.get("root_consumption_sha256") != logical_root_sha256
            ):
                raise ValueError("selected logical root differs")
            return RedLivingDexLoadedProducerSlot(record, root)
        except BaseException:
            raise RedLivingDexCausalInvocationError("selected_root_authentication") from None

    return load


def _clustered_selected_loader(
    expected: RedLivingDexClusteredTrainSelection,
    *,
    private_root: Path,
    state_path: Path,
    envelope_path: Path,
):  # type: ignore[no-untyped-def]
    def load(
        selection: RedLivingDexClusteredTrainSelection,
    ) -> RedLivingDexAuthenticatedSetupRoot:
        try:
            if selection != expected:
                raise ValueError("selected clustered assignment differs")
            current_state_path = _require_private_regular_path(
                state_path,
                private_root=private_root,
            )
            current_envelope_path = _require_private_regular_path(
                envelope_path,
                private_root=private_root,
            )
            if current_state_path == current_envelope_path:
                raise ValueError("selected files alias")
            root = RedLivingDexAuthenticatedSetupRoot(
                root_consumption_sha256=selection.logical_root_sha256,
                state_bytes=_read_private_regular(
                    current_state_path,
                    maximum_bytes=_MAXIMUM_STATE_BYTES,
                ),
                envelope_bytes=_read_private_regular(
                    current_envelope_path,
                    maximum_bytes=_MAXIMUM_ENVELOPE_BYTES,
                ),
            )
            if (
                root.physical_root_sha256 != selection.physical_root_sha256
                or root.state_sha256 != selection.root_state_sha256
                or root.envelope_sha256 != selection.root_envelope_sha256
            ):
                raise ValueError("selected clustered root differs")
            return root
        except BaseException:
            raise RedLivingDexClusteredTrainRunnerError(
                "clustered selected root authentication failed"
            ) from None

    return load


def _require_private_regular_path(path: Path, *, private_root: Path) -> Path:
    try:
        root = private_root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
        if (
            not path.is_absolute()
            or path.is_symlink()
            or resolved != path
            or not resolved.is_relative_to(root)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise OSError("private path differs")
        ancestor = resolved.parent
        while ancestor != root:
            if ancestor == ancestor.parent or not ancestor.is_relative_to(root):
                raise OSError("selected path escapes private root")
            if os.path.lexists(ancestor / PRIVATE_ROOT_SENTINEL):
                raise OSError("selected path belongs to a nested private root")
            ancestor = ancestor.parent
        return resolved
    except OSError:
        raise CausalCampaignExecutionError("selected_root_authentication") from None


def _read_private_regular(path: Path, *, maximum_bytes: int) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        named = path.lstat()
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            named.st_dev != opened.st_dev
            or named.st_ino != opened.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) & 0o077
            or not 0 < opened.st_size <= maximum_bytes
        ):
            raise OSError("private file differs")
        payload = os.read(descriptor, opened.st_size + 1)
        finished = os.fstat(descriptor)
        if (
            len(payload) != opened.st_size
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
        ):
            raise OSError("private file changed")
        return payload
    except OSError:
        raise RedLivingDexCausalInvocationError("selected_root_authentication") from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _failure(
    stage: str,
    *,
    meter: RedLivingDexSetupEffectMeter,
    invocation_returned: bool,
) -> dict[str, object]:
    checkpoint = meter.checkpoint()
    return {
        "automatic_retry_allowed": False,
        "causal_train_example_recorded": None,
        "controller_actions": checkpoint.controller_actions,
        "durable_result_unknown": not invocation_returned,
        "emulator_frames": checkpoint.emulator_frames,
        "model_fits": checkpoint.model_fits,
        "model_predictions": checkpoint.model_predictions,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "provider_executions": checkpoint.provider_executions,
        "result_schema": FAILURE_SCHEMA,
        "root_claims_metered_setup_only": checkpoint.root_claims,
        "stage": stage if re.fullmatch(r"[a-z0-9_]+", stage) else "unexpected_failure",
        "status": (
            "consumed_postcheck_failed_no_retry"
            if invocation_returned
            else "failed_closed_recovery_required_before_any_new_attempt"
        ),
        "teacher_queries": checkpoint.teacher_queries,
    }


def _encoded(value: dict[str, object]) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


if __name__ == "__main__":
    try:
        _EXIT_CODE = main()
    finally:
        if _RUNTIME_FINDER in sys.meta_path:
            sys.meta_path.remove(_RUNTIME_FINDER)
        if _RUNTIME_STAGE is not None:
            with suppress(BaseException):
                _RUNTIME_STAGE.close()
    raise SystemExit(_EXIT_CODE)
