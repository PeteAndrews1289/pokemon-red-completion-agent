"""Path-free identity of the interpreter and installed PyBoy runtime."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import platform
import re
import stat
import sys
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any

RUNTIME_IDENTITY_SCHEMA = "pokemon-red-runtime-identity-v1"
PYBOY_INVENTORY_SCHEMA = "python-distribution-file-inventory-v1"

_DISTRIBUTION_NAME = "pyboy"
_MAX_DISTRIBUTION_FILES = 10_000
_MAX_DISTRIBUTION_FILE_BYTES = 128 * 1024 * 1024
_MAX_DISTRIBUTION_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_EXECUTABLE_BYTES = 256 * 1024 * 1024
_READ_CHUNK_BYTES = 1024 * 1024
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._+~-]{0,254}\Z")
_SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+!-]{0,127}\Z")
_NORMALIZE_DISTRIBUTION = re.compile(r"[-_.]+")
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PYBOY_DIST_INFO = re.compile(
    r"pyboy-[A-Za-z0-9][A-Za-z0-9._+!-]{0,127}\.dist-info\Z"
)
_CONSOLE_SCRIPT_PARENT = re.compile(r"up-[1-9][0-9]*\Z")


class RuntimeIdentityError(RuntimeError):
    """Raised when the executable runtime cannot be frozen without ambiguity."""


def is_canonical_distribution_inventory_name(value: object) -> bool:
    """Return whether ``value`` is one canonical, PyBoy-scoped logical name."""

    if type(value) is not str:  # noqa: E721
        return False
    try:
        value.encode("ascii")
        canonical = _canonical_inventory_name(
            value,
            console_scripts=frozenset(),
        )
    except (RuntimeIdentityError, UnicodeEncodeError):
        return False
    if canonical != value:
        return False
    parts = value.split("/")
    root = parts[0].casefold()
    return (
        (root == "pyboy" and len(parts) >= 2)
        or (
            _PYBOY_DIST_INFO.fullmatch(root) is not None
            and len(parts) >= 2
        )
        or (
            root == "console_scripts"
            and len(parts) == 3
            and _CONSOLE_SCRIPT_PARENT.fullmatch(parts[1]) is not None
            and parts[2].casefold() in {"pyboy", "pyboy.exe"}
        )
    )


def is_runtime_identity_public_document(value: object) -> bool:
    """Validate the complete path-free runtime mapping accepted in metadata."""

    if not isinstance(value, Mapping) or set(value) != {"schema", "python", "pyboy"}:
        return False
    if value.get("schema") != RUNTIME_IDENTITY_SCHEMA:
        return False
    python = value.get("python")
    pyboy = value.get("pyboy")
    if (
        not isinstance(python, Mapping)
        or set(python) != {"implementation", "version", "executable_sha256"}
        or python.get("implementation") != "CPython"
        or type(python.get("version")) is not str  # noqa: E721
        or _SAFE_VERSION.fullmatch(python["version"]) is None
        or type(python.get("executable_sha256")) is not str  # noqa: E721
        or _HEX_SHA256.fullmatch(python["executable_sha256"]) is None
    ):
        return False
    if (
        not isinstance(pyboy, Mapping)
        or set(pyboy)
        != {
            "distribution_name",
            "distribution_version",
            "files",
            "inventory_sha256",
        }
        or pyboy.get("distribution_name") != _DISTRIBUTION_NAME
        or type(pyboy.get("distribution_version")) is not str  # noqa: E721
        or _SAFE_VERSION.fullmatch(pyboy["distribution_version"]) is None
        or type(pyboy.get("inventory_sha256")) is not str  # noqa: E721
        or _HEX_SHA256.fullmatch(pyboy["inventory_sha256"]) is None
    ):
        return False
    files = pyboy.get("files")
    if (
        not isinstance(files, list)
        or not files
        or len(files) > _MAX_DISTRIBUTION_FILES
    ):
        return False
    normalized_files: list[dict[str, object]] = []
    names: list[str] = []
    total_bytes = 0
    for file in files:
        if (
            not isinstance(file, Mapping)
            or set(file) != {"name", "bytes", "sha256"}
            or not is_canonical_distribution_inventory_name(file.get("name"))
            or type(file.get("bytes")) is not int  # noqa: E721
            or not 0 <= file["bytes"] <= _MAX_DISTRIBUTION_FILE_BYTES
            or type(file.get("sha256")) is not str  # noqa: E721
            or _HEX_SHA256.fullmatch(file["sha256"]) is None
        ):
            return False
        total_bytes += file["bytes"]
        if total_bytes > _MAX_DISTRIBUTION_TOTAL_BYTES:
            return False
        name = file["name"]
        names.append(name)
        normalized_files.append(
            {
                "name": name,
                "bytes": file["bytes"],
                "sha256": file["sha256"],
            }
        )
    if names != sorted(names) or len(set(names)) != len(names):
        return False
    inventory = {
        "schema": PYBOY_INVENTORY_SCHEMA,
        "distribution_name": _DISTRIBUTION_NAME,
        "distribution_version": pyboy["distribution_version"],
        "files": normalized_files,
    }
    return (
        hashlib.sha256(_canonical_json_line(inventory)).hexdigest()
        == str(pyboy["inventory_sha256"])
    )


@dataclass(frozen=True, slots=True)
class RuntimeFileIdentity:
    """One installed distribution file represented without its absolute location."""

    name: str
    size: int
    sha256: str

    def public_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "bytes": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """Canonical runtime identity suitable for a private campaign seal."""

    python_implementation: str
    python_version: str
    python_executable_sha256: str
    pyboy_distribution_name: str
    pyboy_distribution_version: str
    pyboy_files: tuple[RuntimeFileIdentity, ...]
    pyboy_inventory_sha256: str

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RUNTIME_IDENTITY_SCHEMA,
            "python": {
                "implementation": self.python_implementation,
                "version": self.python_version,
                "executable_sha256": self.python_executable_sha256,
            },
            "pyboy": {
                "distribution_name": self.pyboy_distribution_name,
                "distribution_version": self.pyboy_distribution_version,
                "files": [file.public_dict() for file in self.pyboy_files],
                "inventory_sha256": self.pyboy_inventory_sha256,
            },
        }

    def canonical_bytes(self) -> bytes:
        """Return the exact public mapping encoding covered by :attr:`sha256`."""

        return _canonical_json_line(self.public_dict())

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def build_runtime_identity() -> RuntimeIdentity:
    """Freeze the active CPython executable and installed PyBoy distribution."""

    try:
        distribution = metadata.distribution(_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        raise RuntimeIdentityError("PyBoy distribution is unavailable") from None
    try:
        module = importlib.import_module(_DISTRIBUTION_NAME)
    except ImportError:
        raise RuntimeIdentityError("PyBoy import is unavailable") from None
    if getattr(module, "PyBoy", None) is None:
        raise RuntimeIdentityError("PyBoy import surface is invalid")
    identity = build_runtime_identity_from(
        python_executable=Path(sys.executable),
        python_implementation=platform.python_implementation(),
        python_version=platform.python_version(),
        pyboy_distribution=distribution,
    )
    _require_pyboy_import_origins(distribution, identity)
    return identity


def require_pyboy_import_origins(identity: RuntimeIdentity) -> None:
    """Fail unless every loaded PyBoy module belongs to the frozen distribution."""

    if not isinstance(identity, RuntimeIdentity):
        raise TypeError("identity must be a RuntimeIdentity")
    try:
        distribution = metadata.distribution(_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        raise RuntimeIdentityError("PyBoy distribution is unavailable") from None
    if (
        _distribution_name(distribution) != identity.pyboy_distribution_name
        or _safe_version(
            getattr(distribution, "version", None),
            subject="PyBoy distribution version",
        )
        != identity.pyboy_distribution_version
        or _distribution_inventory(distribution) != identity.pyboy_files
    ):
        raise RuntimeIdentityError("loaded PyBoy distribution differs from runtime identity")
    _require_pyboy_import_origins(distribution, identity)


def _require_pyboy_import_origins(
    distribution: Any,
    identity: RuntimeIdentity,
) -> None:
    expected_files = _distribution_resolved_files(distribution)
    loaded_origins: list[Path] = []
    for name, module in tuple(sys.modules.items()):
        if name != _DISTRIBUTION_NAME and not name.startswith(f"{_DISTRIBUTION_NAME}."):
            continue
        raw = getattr(module, "__file__", None)
        if raw is None:
            continue
        if not isinstance(raw, str):
            raise RuntimeIdentityError("loaded PyBoy import origin is invalid")
        try:
            loaded_origins.append(Path(raw).resolve(strict=True))
        except OSError:
            raise RuntimeIdentityError("loaded PyBoy import origin is unavailable") from None
    if (
        not loaded_origins
        or any(origin not in expected_files for origin in loaded_origins)
        or _distribution_inventory(distribution) != identity.pyboy_files
    ):
        raise RuntimeIdentityError("loaded PyBoy import differs from its distribution")


def _distribution_resolved_files(distribution: Any) -> frozenset[Path]:
    raw_files = getattr(distribution, "files", None)
    if raw_files is None:
        raise RuntimeIdentityError("PyBoy distribution inventory is unavailable")
    try:
        entries = tuple(raw_files)
    except (TypeError, OSError):
        raise RuntimeIdentityError("PyBoy distribution inventory is unavailable") from None
    console_scripts = _console_script_names(distribution)
    resolved: set[Path] = set()
    for entry in entries:
        raw_name = _entry_text(entry)
        if _excluded_cache_entry(raw_name):
            continue
        _canonical_inventory_name(raw_name, console_scripts=console_scripts)
        try:
            resolved.add(Path(distribution.locate_file(entry)).resolve(strict=True))
        except (AttributeError, OSError, TypeError, ValueError):
            raise RuntimeIdentityError(
                "PyBoy distribution file cannot be located"
            ) from None
    return frozenset(resolved)


def build_runtime_identity_from(
    *,
    python_executable: str | os.PathLike[str],
    python_implementation: str,
    python_version: str,
    pyboy_distribution: Any,
) -> RuntimeIdentity:
    """Build an identity from explicit inputs, primarily for isolated verification."""

    implementation = _safe_scalar(
        python_implementation,
        subject="Python implementation",
    )
    if implementation != "CPython":
        raise RuntimeIdentityError("runtime identity requires CPython")
    version = _safe_version(python_version, subject="Python version")
    executable = _resolve_executable(python_executable)
    _, executable_sha256 = _hash_regular_file(
        executable,
        maximum_bytes=_MAX_EXECUTABLE_BYTES,
        subject="resolved Python executable",
    )

    distribution_name = _distribution_name(pyboy_distribution)
    distribution_version = _safe_version(
        getattr(pyboy_distribution, "version", None),
        subject="PyBoy distribution version",
    )
    files = _distribution_inventory(pyboy_distribution)
    inventory_payload = {
        "schema": PYBOY_INVENTORY_SCHEMA,
        "distribution_name": distribution_name,
        "distribution_version": distribution_version,
        "files": [file.public_dict() for file in files],
    }
    return RuntimeIdentity(
        python_implementation=implementation,
        python_version=version,
        python_executable_sha256=executable_sha256,
        pyboy_distribution_name=distribution_name,
        pyboy_distribution_version=distribution_version,
        pyboy_files=files,
        pyboy_inventory_sha256=hashlib.sha256(
            _canonical_json_line(inventory_payload)
        ).hexdigest(),
    )


def _distribution_inventory(distribution: Any) -> tuple[RuntimeFileIdentity, ...]:
    raw_files = getattr(distribution, "files", None)
    if raw_files is None:
        raise RuntimeIdentityError("PyBoy distribution inventory is unavailable")
    try:
        entries = tuple(raw_files)
    except (TypeError, OSError):
        raise RuntimeIdentityError("PyBoy distribution inventory is unavailable") from None
    if not entries or len(entries) > _MAX_DISTRIBUTION_FILES:
        raise RuntimeIdentityError("PyBoy distribution inventory size is invalid")

    console_scripts = _console_script_names(distribution)
    planned: list[tuple[object, str]] = []
    names: set[str] = set()
    for entry in entries:
        raw_name = _entry_text(entry)
        if _excluded_cache_entry(raw_name):
            continue
        name = _canonical_inventory_name(raw_name, console_scripts=console_scripts)
        if not is_canonical_distribution_inventory_name(name):
            raise RuntimeIdentityError(
                "PyBoy distribution inventory name is outside its logical namespace"
            )
        if name in names:
            raise RuntimeIdentityError("PyBoy distribution inventory contains duplicate names")
        names.add(name)
        planned.append((entry, name))
    if not planned:
        raise RuntimeIdentityError("PyBoy distribution inventory is empty")

    identities: list[RuntimeFileIdentity] = []
    total_bytes = 0
    for entry, name in planned:
        try:
            located = Path(distribution.locate_file(entry))
        except (AttributeError, OSError, TypeError, ValueError):
            raise RuntimeIdentityError("PyBoy distribution file cannot be located") from None
        if not located.is_absolute():
            raise RuntimeIdentityError(
                "PyBoy distribution file location is not absolute"
            )
        size, digest = _hash_regular_file(
            located,
            maximum_bytes=_MAX_DISTRIBUTION_FILE_BYTES,
            subject="PyBoy distribution file",
        )
        total_bytes += size
        if total_bytes > _MAX_DISTRIBUTION_TOTAL_BYTES:
            raise RuntimeIdentityError("PyBoy distribution exceeds the total size limit")
        identities.append(RuntimeFileIdentity(name=name, size=size, sha256=digest))
    identities.sort(key=lambda item: item.name)
    return tuple(identities)


def _distribution_name(distribution: Any) -> str:
    try:
        raw_name = distribution.metadata["Name"]
    except (AttributeError, KeyError, TypeError):
        raise RuntimeIdentityError("PyBoy distribution name is unavailable") from None
    safe_name = _safe_scalar(raw_name, subject="PyBoy distribution name")
    normalized = _NORMALIZE_DISTRIBUTION.sub("-", safe_name).casefold()
    if normalized != _DISTRIBUTION_NAME:
        raise RuntimeIdentityError("installed distribution is not PyBoy")
    return normalized


def _console_script_names(distribution: Any) -> frozenset[str]:
    try:
        entry_points = tuple(distribution.entry_points)
    except (AttributeError, TypeError):
        return frozenset()
    names: set[str] = set()
    for entry_point in entry_points:
        if getattr(entry_point, "group", None) != "console_scripts":
            continue
        name = _safe_scalar(
            getattr(entry_point, "name", None),
            subject="console script name",
        )
        if _SAFE_COMPONENT.fullmatch(name) is None:
            raise RuntimeIdentityError("console script name is unsafe")
        names.add(name)
    return frozenset(names)


def _entry_text(entry: object) -> str:
    try:
        value = str(entry)
        value.encode("ascii")
    except (UnicodeEncodeError, ValueError):
        raise RuntimeIdentityError("PyBoy distribution inventory name is unsafe") from None
    if not value or "\x00" in value or "\\" in value:
        raise RuntimeIdentityError("PyBoy distribution inventory name is unsafe")
    return value


def _excluded_cache_entry(name: str) -> bool:
    parts = name.split("/")
    lowered = name.casefold()
    return (
        any(part.casefold() == "__pycache__" for part in parts)
        or lowered.endswith((".pyc", ".pyo"))
    )


def _canonical_inventory_name(
    raw_name: str,
    *,
    console_scripts: frozenset[str],
) -> str:
    raw_parts = tuple(raw_name.split("/"))
    if any(part in {"", "."} for part in raw_parts):
        raise RuntimeIdentityError("PyBoy distribution inventory name is unsafe")
    path = PurePosixPath(raw_name)
    parts = raw_parts
    if path.is_absolute() or not parts:
        raise RuntimeIdentityError("PyBoy distribution inventory name is unsafe")
    if all(part not in {"", ".", ".."} for part in parts):
        _validate_inventory_parts(parts)
        return "/".join(parts)

    parent_count = 0
    while parent_count < len(parts) and parts[parent_count] == "..":
        parent_count += 1
    remainder = parts[parent_count:]
    if (
        parent_count > 0
        and len(remainder) == 2
        and remainder[0].casefold() in {"bin", "scripts"}
        and _is_declared_console_script(remainder[1], console_scripts)
    ):
        _validate_inventory_parts(remainder)
        return f"console_scripts/up-{parent_count}/{remainder[1]}"
    raise RuntimeIdentityError("PyBoy distribution inventory name is unsafe")


def _validate_inventory_parts(parts: tuple[str, ...]) -> None:
    for part in parts:
        if _SAFE_COMPONENT.fullmatch(part) is None:
            raise RuntimeIdentityError("PyBoy distribution inventory name is unsafe")


def _is_declared_console_script(name: str, scripts: frozenset[str]) -> bool:
    casefolded = name.casefold()
    return any(
        casefolded == script.casefold()
        or casefolded == f"{script.casefold()}.exe"
        for script in scripts
    )


def _resolve_executable(value: str | os.PathLike[str]) -> Path:
    try:
        path = Path(value)
    except TypeError:
        raise RuntimeIdentityError("Python executable is unavailable") from None
    if not path.is_absolute():
        raise RuntimeIdentityError("Python executable identity requires an absolute target")
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise RuntimeIdentityError("Python executable cannot be resolved") from None


def _hash_regular_file(
    path: Path,
    *,
    maximum_bytes: int,
    subject: str,
) -> tuple[int, str]:
    try:
        expected = path.lstat()
    except OSError:
        raise RuntimeIdentityError(f"{subject} is missing") from None
    if stat.S_ISLNK(expected.st_mode):
        raise RuntimeIdentityError(f"{subject} may not be a symbolic link")
    if not stat.S_ISREG(expected.st_mode):
        raise RuntimeIdentityError(f"{subject} must be a regular file")
    if expected.st_size < 0 or expected.st_size > maximum_bytes:
        raise RuntimeIdentityError(f"{subject} exceeds the size limit")

    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != expected.st_dev
            or opened.st_ino != expected.st_ino
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_size != expected.st_size
            or opened.st_mtime_ns != expected.st_mtime_ns
            or opened.st_ctime_ns != expected.st_ctime_ns
        ):
            raise RuntimeIdentityError(f"{subject} changed while opening")
        digest = hashlib.sha256()
        bytes_read = 0
        while True:
            chunk = os.read(
                descriptor,
                min(_READ_CHUNK_BYTES, maximum_bytes - bytes_read + 1),
            )
            if not chunk:
                break
            bytes_read += len(chunk)
            if bytes_read > maximum_bytes:
                raise RuntimeIdentityError(f"{subject} exceeds the size limit")
            digest.update(chunk)
        final = os.fstat(descriptor)
        if (
            final.st_dev != opened.st_dev
            or final.st_ino != opened.st_ino
            or final.st_size != bytes_read
            or final.st_mtime_ns != opened.st_mtime_ns
            or final.st_ctime_ns != opened.st_ctime_ns
        ):
            raise RuntimeIdentityError(f"{subject} changed during hashing")
        return bytes_read, digest.hexdigest()
    except RuntimeIdentityError:
        raise
    except OSError:
        raise RuntimeIdentityError(f"unable to hash the {subject}") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _safe_scalar(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeIdentityError(f"{subject} is unavailable")
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        raise RuntimeIdentityError(f"{subject} is not canonical ASCII") from None
    if (
        len(value) > 128
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value)
        or "/" in value
        or "\\" in value
    ):
        raise RuntimeIdentityError(f"{subject} is unsafe")
    return value


def _safe_version(value: object, *, subject: str) -> str:
    version = _safe_scalar(value, subject=subject)
    if _SAFE_VERSION.fullmatch(version) is None:
        raise RuntimeIdentityError(f"{subject} is unsafe")
    return version


def _canonical_json_line(value: object) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        raise RuntimeIdentityError("runtime identity cannot be encoded") from None
    return rendered.encode("ascii") + b"\n"
