"""Exact, path-free authentication of the controller runtime dependency closure.

The frozen producer identity intentionally describes CPython plus PyBoy.  A
controller-capable consumer also executes PyBoy's transitive runtime imports,
so admitting an entire virtual-environment ``site-packages`` directory would
leave NumPy, SDL, and Pillow outside the one-shot trust boundary.  This module
authenticates the exact wheel inventories and installs a restrictive finder
that refuses every other import from that directory.

No distribution package is imported while the closure is inspected.  The
only metadata reader used here is :class:`importlib.metadata.PathDistribution`,
pointed at exact, already authenticated ``.dist-info`` directories.
"""

from __future__ import annotations

import hashlib
import importlib.abc
import importlib.machinery
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path, PurePosixPath
from types import ModuleType

EXECUTION_RUNTIME_CLOSURE_SCHEMA = "pokemon-red-execution-runtime-closure-v1"

# Filled from the canonical inventories below.  Updating any executable wheel
# is an executable-source change: regenerate this digest, review the diff, and
# republish before another one-shot campaign is authorized.
EXPECTED_EXECUTION_RUNTIME_CLOSURE_SHA256 = (
    "3dd2037389febcf59a9b45f1f9c705b54889eea0d2445c3a61a1f19600992c62"
)

_MAXIMUM_DISTRIBUTION_FILES = 4_096
_MAXIMUM_FILE_BYTES = 128 * 1024 * 1024
_MAXIMUM_TOTAL_BYTES = 1024 * 1024 * 1024
_MAXIMUM_METADATA_BYTES = 4 * 1024 * 1024
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9._+~-]{1,255}\Z")
_NORMALIZE_DISTRIBUTION = re.compile(r"[-_.]+")
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RUNTIME_STAGE_AUTHORITY = object()


class ExecutionRuntimeClosureError(RuntimeError):
    """The executable third-party closure differs from its reviewed bytes."""


@dataclass(frozen=True, slots=True)
class _DistributionSpec:
    name: str
    version: str
    metadata_directory: str
    import_roots: tuple[str, ...]
    external_files: tuple[str, ...] = ()

    @property
    def normalized_name(self) -> str:
        return _NORMALIZE_DISTRIBUTION.sub("-", self.name).casefold()


_DISTRIBUTIONS = (
    _DistributionSpec(
        "pyboy",
        "2.7.0",
        "pyboy-2.7.0.dist-info",
        ("pyboy",),
        ("../../../bin/pyboy",),
    ),
    _DistributionSpec(
        "numpy",
        "2.5.1",
        "numpy-2.5.1.dist-info",
        ("numpy",),
        ("../../../bin/f2py", "../../../bin/numpy-config"),
    ),
    _DistributionSpec(
        "pysdl2",
        "0.9.17",
        "PySDL2-0.9.17.dist-info",
        ("sdl2",),
    ),
    _DistributionSpec(
        "pysdl2-dll",
        "2.32.10",
        "pysdl2_dll-2.32.10.dist-info",
        ("sdl2dll",),
    ),
)


@dataclass(frozen=True, slots=True)
class RuntimeClosureFile:
    """One path-free distribution file identity."""

    distribution: str
    name: str
    size: int
    sha256: str
    resolved_path: Path = field(repr=False, compare=False)

    def public_dict(self) -> dict[str, object]:
        return {
            "bytes": self.size,
            "distribution": self.distribution,
            "name": self.name,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class ExecutionRuntimeClosure:
    """Authenticated dependency inventory plus its permitted import origins."""

    files: tuple[RuntimeClosureFile, ...]
    site_packages: Path = field(repr=False, compare=False)

    @property
    def sha256(self) -> str:
        payload = {
            "files": [item.public_dict() for item in self.files],
            "schema": EXECUTION_RUNTIME_CLOSURE_SCHEMA,
        }
        return hashlib.sha256(_canonical_json_line(payload)).hexdigest()

    @property
    def allowed_files(self) -> frozenset[Path]:
        return frozenset(item.resolved_path for item in self.files)

    @property
    def allowed_import_roots(self) -> frozenset[str]:
        return frozenset(root for spec in _DISTRIBUTIONS for root in spec.import_roots)


@dataclass(slots=True)
class AuthenticatedRuntimeStage:
    """Private clean copy of reviewed wheels, with no source-adjacent bytecode."""

    closure: ExecutionRuntimeClosure
    _temporary_root: Path = field(repr=False)
    _authority: object = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _device: int = field(default=-1, init=False, repr=False)
    _inode: int = field(default=-1, init=False, repr=False)

    def __post_init__(self) -> None:
        if self._authority is not _RUNTIME_STAGE_AUTHORITY:
            raise ExecutionRuntimeClosureError("runtime stage authority differs")
        metadata = _require_stage_root(self._temporary_root, self.closure)
        self._device = metadata.st_dev
        self._inode = metadata.st_ino

    def close(self) -> None:
        if self._closed:
            return
        metadata = _require_stage_root(self._temporary_root, self.closure)
        if metadata.st_dev != self._device or metadata.st_ino != self._inode:
            raise ExecutionRuntimeClosureError("runtime stage root changed")
        self._closed = True
        shutil.rmtree(self._temporary_root)

    def __enter__(self) -> AuthenticatedRuntimeStage:
        if self._closed:
            raise ExecutionRuntimeClosureError("runtime stage is already closed")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def inspect_execution_runtime_closure(site_packages: Path) -> ExecutionRuntimeClosure:
    """Read the exact dependency closure without importing any of its packages."""

    root = _require_directory(site_packages, subject="runtime site-packages")
    _reject_top_level_collisions(root)
    files: list[RuntimeClosureFile] = []
    expected_census: set[Path] = set()
    total_bytes = 0
    seen_paths: set[Path] = set()

    for spec in _DISTRIBUTIONS:
        distribution, metadata_root = _exact_distribution(root, spec)
        raw_files = getattr(distribution, "files", None)
        try:
            entries = tuple(raw_files) if raw_files is not None else ()
        except (OSError, TypeError):
            raise ExecutionRuntimeClosureError(
                "runtime distribution inventory is unavailable"
            ) from None
        if not entries or len(entries) > _MAXIMUM_DISTRIBUTION_FILES:
            raise ExecutionRuntimeClosureError("runtime distribution inventory size differs")
        logical_names: set[str] = set()
        allowed_roots = frozenset((*spec.import_roots, spec.metadata_directory))
        for entry in entries:
            logical_name = _entry_text(entry)
            if logical_name in logical_names:
                raise ExecutionRuntimeClosureError(
                    "runtime distribution inventory contains duplicates"
                )
            logical_names.add(logical_name)
            _require_inventory_scope(
                logical_name,
                allowed_roots=allowed_roots,
                external_files=frozenset(spec.external_files),
            )
            try:
                located = Path(str(distribution.locate_file(entry)))
                if located.is_symlink():
                    raise OSError("runtime distribution file is a symlink")
                canonical_location = located.resolve(strict=True)
            except (AttributeError, OSError, TypeError, ValueError):
                raise ExecutionRuntimeClosureError(
                    "runtime distribution file cannot be located"
                ) from None
            if not located.is_absolute():
                raise ExecutionRuntimeClosureError("runtime distribution path is not absolute")
            size, digest, resolved = _hash_regular_file(canonical_location)
            total_bytes += size
            if total_bytes > _MAXIMUM_TOTAL_BYTES or resolved in seen_paths:
                raise ExecutionRuntimeClosureError(
                    "runtime dependency closure size or alias differs"
                )
            seen_paths.add(resolved)
            if _is_inside_inventory_root(
                logical_name,
                allowed_roots=allowed_roots,
            ):
                expected_census.add(resolved)
            files.append(
                RuntimeClosureFile(
                    distribution=spec.normalized_name,
                    name=logical_name,
                    size=size,
                    sha256=digest,
                    resolved_path=resolved,
                )
            )
        import_roots = tuple(
            _require_directory(root / name, subject="runtime import root")
            for name in spec.import_roots
        )
        _require_tree_census(
            (*import_roots, metadata_root),
            expected_census=expected_census,
        )

    files.sort(key=lambda item: (item.distribution, item.name))
    return ExecutionRuntimeClosure(tuple(files), root)


def authenticate_execution_runtime_closure(
    site_packages: Path,
) -> ExecutionRuntimeClosure:
    """Require the reviewed closure digest and return its import allowlist."""

    closure = inspect_execution_runtime_closure(site_packages)
    if closure.sha256 != EXPECTED_EXECUTION_RUNTIME_CLOSURE_SHA256:
        raise ExecutionRuntimeClosureError("runtime dependency closure differs")
    return closure


def prepare_authenticated_runtime_stage(
    source_site_packages: Path,
) -> AuthenticatedRuntimeStage:
    """Copy reviewed files into a new cache-free, import-only runtime tree."""

    source = authenticate_execution_runtime_closure(source_site_packages)
    try:
        temporary_root = Path(tempfile.mkdtemp(prefix="pokemon-red-runtime-")).resolve(strict=True)
        os.chmod(temporary_root, 0o700)
        stage_site = temporary_root / "venv/lib/python3.14/site-packages"
        stage_site.mkdir(parents=True, mode=0o700)
        for directory in (
            temporary_root / "venv",
            temporary_root / "venv/lib",
            temporary_root / "venv/lib/python3.14",
            stage_site,
        ):
            os.chmod(directory, 0o700)
        for item in source.files:
            destination = _staged_destination(stage_site, item.name)
            _copy_authenticated_file(
                item,
                destination,
                stage_root=temporary_root / "venv",
            )
        staged = inspect_execution_runtime_closure(stage_site)
        if staged.sha256 != source.sha256:
            raise ExecutionRuntimeClosureError("staged runtime closure differs")
        return AuthenticatedRuntimeStage(
            staged,
            temporary_root,
            _RUNTIME_STAGE_AUTHORITY,
        )
    except BaseException:
        if "temporary_root" in locals():
            with suppress(OSError):
                shutil.rmtree(temporary_root)
        raise


class AuthenticatedRuntimeFinder(importlib.abc.MetaPathFinder):
    """Refuse imports from site-packages unless their origin was authenticated."""

    def __init__(self, closure: ExecutionRuntimeClosure) -> None:
        if not isinstance(closure, ExecutionRuntimeClosure):
            raise TypeError("runtime finder needs an authenticated closure")
        self._site_packages = closure.site_packages
        self._allowed_files = closure.allowed_files
        self._allowed_roots = closure.allowed_import_roots

    @property
    def site_packages(self) -> Path:
        return self._site_packages

    @property
    def closure_sha256(self) -> str:
        payload = {
            "files": sorted(str(path) for path in self._allowed_files),
            "site_packages": str(self._site_packages),
        }
        return hashlib.sha256(_canonical_json_line(payload)).hexdigest()

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ):  # type: ignore[no-untyped-def]
        del target
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None:
            return None
        origin = spec.origin
        if origin in {None, "built-in", "frozen"}:
            locations = spec.submodule_search_locations
            if locations is not None and any(
                _resolves_inside(Path(item), self._site_packages) for item in locations
            ):
                raise ImportError("unauthenticated site namespace")
            return None
        try:
            resolved = Path(origin).resolve(strict=True)
        except (OSError, TypeError, ValueError):
            return None
        if not resolved.is_relative_to(self._site_packages):
            return None
        top_level = fullname.partition(".")[0]
        if top_level not in self._allowed_roots or resolved not in self._allowed_files:
            raise ImportError("unauthenticated site import")
        return spec


@dataclass(slots=True)
class ActivatedAuthenticatedRuntimeStage:
    """One installed clean runtime stage with reversible interpreter state."""

    stage: AuthenticatedRuntimeStage
    finder: AuthenticatedRuntimeFinder
    _previous_sys_path: tuple[str, ...] = field(repr=False)
    _previous_meta_path: tuple[object, ...] = field(repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    @property
    def closure(self) -> ExecutionRuntimeClosure:
        return self.stage.closure

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        sys.path[:] = self._previous_sys_path
        sys.meta_path[:] = self._previous_meta_path  # type: ignore[assignment]
        self.stage.close()

    def __enter__(self) -> ActivatedAuthenticatedRuntimeStage:
        if self._closed:
            raise ExecutionRuntimeClosureError("activated runtime stage is already closed")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def activate_authenticated_runtime_stage(
    source_site_packages: Path,
) -> ActivatedAuthenticatedRuntimeStage:
    """Install only the reviewed third-party closure for later controller use.

    This is intentionally small enough for a command to call before importing
    any controller-capable project module.  The source virtual environment is
    removed from module search, the clean stage is installed behind one exact
    finder, and already-loaded third-party runtime modules are rejected.
    """

    source = _require_directory(source_site_packages, subject="runtime site-packages")
    if any(isinstance(item, AuthenticatedRuntimeFinder) for item in sys.meta_path):
        raise ExecutionRuntimeClosureError("authenticated runtime finder already exists")
    previous_path = tuple(sys.path)
    previous_meta_path = tuple(sys.meta_path)
    third_party_paths: list[Path] = []
    try:
        for item in previous_path:
            if not isinstance(item, str) or not item:
                continue
            candidate = Path(item)
            if not candidate.is_absolute() or candidate.name not in {
                "site-packages",
                "dist-packages",
            }:
                continue
            third_party_paths.append(candidate.resolve(strict=True))
        for module in tuple(sys.modules.values()):
            raw_origin = getattr(module, "__file__", None)
            if not isinstance(raw_origin, str) or not Path(raw_origin).is_absolute():
                continue
            try:
                origin = Path(raw_origin).resolve(strict=True)
            except OSError:
                raise ExecutionRuntimeClosureError(
                    "loaded third-party origin is unavailable"
                ) from None
            if any(origin.is_relative_to(root) for root in third_party_paths):
                raise ExecutionRuntimeClosureError("third-party module loaded before runtime stage")
        stage = prepare_authenticated_runtime_stage(source)
        finder = AuthenticatedRuntimeFinder(stage.closure)
        sys.path[:] = [
            item
            for item in previous_path
            if not (
                isinstance(item, str)
                and item
                and Path(item).is_absolute()
                and Path(item).name in {"site-packages", "dist-packages"}
            )
        ]
        sys.path.append(str(stage.closure.site_packages))
        sys.meta_path.insert(0, finder)
        require_authenticated_runtime_finder(stage.closure)
        require_loaded_runtime_origins(stage.closure)
        return ActivatedAuthenticatedRuntimeStage(
            stage,
            finder,
            previous_path,
            previous_meta_path,
        )
    except BaseException:
        sys.path[:] = previous_path
        sys.meta_path[:] = previous_meta_path  # type: ignore[assignment]
        if "stage" in locals():
            with suppress(BaseException):
                stage.close()
        raise


def require_authenticated_runtime_finder(
    closure: ExecutionRuntimeClosure,
) -> None:
    """Require the one active site finder to cover this exact staged closure."""

    expected = AuthenticatedRuntimeFinder(closure).closure_sha256
    finders = tuple(item for item in sys.meta_path if isinstance(item, AuthenticatedRuntimeFinder))
    if (
        len(finders) != 1
        or finders[0].site_packages != closure.site_packages
        or finders[0].closure_sha256 != expected
    ):
        raise ExecutionRuntimeClosureError("authenticated runtime finder differs")


def require_loaded_runtime_origins(closure: ExecutionRuntimeClosure) -> None:
    """Rehash the closure and prove every loaded site module came from it."""

    if not isinstance(closure, ExecutionRuntimeClosure):
        raise TypeError("runtime origin check needs an authenticated closure")
    current = authenticate_execution_runtime_closure(closure.site_packages)
    if current.sha256 != closure.sha256:
        raise ExecutionRuntimeClosureError("runtime dependency closure changed")
    allowed = current.allowed_files
    roots = current.allowed_import_roots
    for name, module in tuple(sys.modules.items()):
        top_level = name.partition(".")[0]
        raw_origin = getattr(module, "__file__", None)
        if not isinstance(raw_origin, str):
            if top_level in roots:
                raise ExecutionRuntimeClosureError(
                    "loaded runtime module has no authenticated origin"
                )
            continue
        raw_path = Path(raw_origin)
        if not raw_path.is_absolute():
            if top_level in roots:
                raise ExecutionRuntimeClosureError("loaded runtime origin is not absolute")
            continue
        try:
            origin = raw_path.resolve(strict=True)
        except OSError:
            if top_level in roots or raw_path.is_relative_to(current.site_packages):
                raise ExecutionRuntimeClosureError("loaded runtime origin is unavailable") from None
            continue
        if (origin.is_relative_to(current.site_packages) and origin not in allowed) or (
            top_level in roots and origin not in allowed
        ):
            raise ExecutionRuntimeClosureError("loaded runtime origin was not authenticated")
    if "sdl2" in sys.modules:
        dll_module = sys.modules.get("sdl2.dll")
        getter = getattr(dll_module, "get_dll_file", None)
        try:
            dll_path = Path(getter()).resolve(strict=True) if callable(getter) else None
        except (OSError, TypeError, ValueError):
            raise ExecutionRuntimeClosureError("loaded SDL binary origin is unavailable") from None
        expected_suffix = Path("sdl2dll/dll/SDL2.framework/Versions/A/SDL2")
        if (
            dll_path is None
            or dll_path not in allowed
            or not dll_path.is_relative_to(current.site_packages)
            or dll_path.relative_to(current.site_packages) != expected_suffix
        ):
            raise ExecutionRuntimeClosureError("loaded SDL binary origin was not authenticated")


def _exact_distribution(
    site_packages: Path,
    spec: _DistributionSpec,
) -> tuple[metadata.PathDistribution, Path]:
    candidates = {
        entry.name
        for entry in site_packages.iterdir()
        if entry.name.casefold().endswith(".dist-info")
        and _metadata_distribution_prefix(entry.name) == spec.normalized_name
    }
    if candidates != {spec.metadata_directory}:
        raise ExecutionRuntimeClosureError("runtime distribution metadata differs")
    metadata_root = _require_directory(
        site_packages / spec.metadata_directory,
        subject="runtime distribution metadata",
    )
    _hash_regular_file(
        metadata_root / "METADATA",
        maximum_bytes=_MAXIMUM_METADATA_BYTES,
    )
    _hash_regular_file(
        metadata_root / "RECORD",
        maximum_bytes=_MAXIMUM_METADATA_BYTES,
    )
    try:
        distribution = metadata.PathDistribution(metadata_root)
        name = distribution.metadata["Name"]
        version = distribution.version
    except BaseException:
        raise ExecutionRuntimeClosureError("runtime distribution metadata is unreadable") from None
    if (
        not isinstance(name, str)
        or _NORMALIZE_DISTRIBUTION.sub("-", name).casefold() != spec.normalized_name
        or version != spec.version
    ):
        raise ExecutionRuntimeClosureError("runtime distribution identity differs")
    return distribution, metadata_root


def _staged_destination(site_packages: Path, logical_name: str) -> Path:
    candidate = site_packages.joinpath(*logical_name.split("/"))
    resolved_parent = candidate.parent.resolve(strict=False)
    stage_root = site_packages.parents[2]
    if not resolved_parent.is_relative_to(stage_root):
        raise ExecutionRuntimeClosureError("staged runtime path escapes its root")
    return resolved_parent / candidate.name


def _copy_authenticated_file(
    item: RuntimeClosureFile,
    destination: Path,
    *,
    stage_root: Path,
) -> None:
    payload = _read_regular_bytes(item.resolved_path, maximum_bytes=_MAXIMUM_FILE_BYTES)
    if len(payload) != item.size or hashlib.sha256(payload).hexdigest() != item.sha256:
        raise ExecutionRuntimeClosureError("runtime source changed before staging")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent = destination.parent
    while True:
        if not parent.is_relative_to(stage_root):
            raise ExecutionRuntimeClosureError("staged runtime parent escapes")
        os.chmod(parent, 0o700)
        if parent == stage_root:
            break
        parent = parent.parent
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = -1
    try:
        source_mode = stat.S_IMODE(item.resolved_path.lstat().st_mode)
        mode = 0o700 if source_mode & 0o111 else 0o600
        descriptor = os.open(destination, flags, mode)
        os.fchmod(descriptor, mode)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("runtime staging write stalled")
            offset += written
        os.fsync(descriptor)
    except OSError:
        raise ExecutionRuntimeClosureError("runtime staging failed") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _metadata_distribution_prefix(name: str) -> str:
    stem = name[: -len(".dist-info")]
    try:
        distribution, _version = stem.rsplit("-", 1)
    except ValueError:
        return ""
    return _NORMALIZE_DISTRIBUTION.sub("-", distribution).casefold()


def _reject_top_level_collisions(site_packages: Path) -> None:
    expected_roots = {
        root.casefold(): root for spec in _DISTRIBUTIONS for root in spec.import_roots
    }
    expected_metadata = {spec.metadata_directory for spec in _DISTRIBUTIONS}
    for entry in site_packages.iterdir():
        lowered = entry.name.casefold()
        for casefolded, exact in expected_roots.items():
            if lowered == casefolded and entry.name != exact:
                raise ExecutionRuntimeClosureError("runtime import root case differs")
            if lowered in {
                f"{casefolded}.py",
                f"{casefolded}.pyc",
                f"{casefolded}.pyo",
                f"{casefolded}.so",
            }:
                raise ExecutionRuntimeClosureError("runtime shadow import exists")
            if lowered.startswith(f"{casefolded}.cpython-") and lowered.endswith((".so", ".pyc")):
                raise ExecutionRuntimeClosureError("runtime shadow import exists")
        if entry.name.casefold().endswith(".dist-info"):
            normalized = _metadata_distribution_prefix(entry.name)
            if normalized in {spec.normalized_name for spec in _DISTRIBUTIONS} and (
                entry.name not in expected_metadata
            ):
                raise ExecutionRuntimeClosureError("runtime distribution metadata collision exists")


def _require_tree_census(
    roots: tuple[Path, ...],
    *,
    expected_census: set[Path],
) -> None:
    actual: set[Path] = set()
    for root in roots:
        for path in root.rglob("*"):
            try:
                named = path.lstat()
            except OSError:
                raise ExecutionRuntimeClosureError("runtime tree changed") from None
            if stat.S_ISLNK(named.st_mode):
                raise ExecutionRuntimeClosureError("runtime tree contains a symlink")
            if stat.S_ISDIR(named.st_mode):
                if path.name == "__pycache__":
                    raise ExecutionRuntimeClosureError(
                        "runtime tree contains executable bytecode cache"
                    )
                if named.st_uid != os.getuid() or stat.S_IMODE(named.st_mode) & 0o022:
                    raise ExecutionRuntimeClosureError("runtime directory permissions differ")
                continue
            if path.suffix in {".pyc", ".pyo"}:
                raise ExecutionRuntimeClosureError(
                    "runtime tree contains executable bytecode cache"
                )
            if not stat.S_ISREG(named.st_mode):
                raise ExecutionRuntimeClosureError("runtime tree entry differs")
            actual.add(path.resolve(strict=True))
    scoped_expected = {
        path for path in expected_census if any(path.is_relative_to(root) for root in roots)
    }
    if actual != scoped_expected:
        raise ExecutionRuntimeClosureError("runtime tree census differs")


def _require_inventory_scope(
    name: str,
    *,
    allowed_roots: frozenset[str],
    external_files: frozenset[str],
) -> None:
    if name in external_files:
        return
    parts = tuple(name.split("/"))
    if (
        not parts
        or parts[0] not in allowed_roots
        or any(part in {".", ".."} or _SAFE_COMPONENT.fullmatch(part) is None for part in parts)
    ):
        raise ExecutionRuntimeClosureError("runtime distribution inventory escapes its namespace")


def _is_inside_inventory_root(
    name: str,
    *,
    allowed_roots: frozenset[str],
) -> bool:
    return name.split("/", 1)[0] in allowed_roots


def _entry_text(entry: object) -> str:
    try:
        value = str(entry)
        value.encode("ascii")
    except (UnicodeEncodeError, ValueError):
        raise ExecutionRuntimeClosureError(
            "runtime distribution inventory name is unsafe"
        ) from None
    if not value or "\x00" in value or "\\" in value or (PurePosixPath(value).is_absolute()):
        raise ExecutionRuntimeClosureError("runtime distribution inventory name is unsafe")
    return value


def _require_directory(path: Path, *, subject: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        named = path.lstat()
    except OSError:
        raise ExecutionRuntimeClosureError(f"{subject} is unavailable") from None
    if (
        not path.is_absolute()
        or path.is_symlink()
        or resolved != path
        or not stat.S_ISDIR(named.st_mode)
        or named.st_uid != os.getuid()
        or stat.S_IMODE(named.st_mode) & 0o022
    ):
        raise ExecutionRuntimeClosureError(f"{subject} differs")
    return resolved


def _require_stage_root(
    root: Path,
    closure: ExecutionRuntimeClosure,
) -> os.stat_result:
    try:
        temporary_parent = Path(tempfile.gettempdir()).resolve(strict=True)
        resolved = root.resolve(strict=True)
        metadata = root.lstat()
        expected_site = root / "venv/lib/python3.14/site-packages"
        if (
            not root.is_absolute()
            or root.is_symlink()
            or resolved != root
            or root.parent != temporary_parent
            or not root.name.startswith("pokemon-red-runtime-")
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
            or closure.site_packages != expected_site
        ):
            raise OSError("runtime stage root differs")
        return metadata
    except OSError:
        raise ExecutionRuntimeClosureError("runtime stage root differs") from None


def _hash_regular_file(
    path: Path,
    *,
    maximum_bytes: int = _MAXIMUM_FILE_BYTES,
) -> tuple[int, str, Path]:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        resolved = path.resolve(strict=True)
        named = path.lstat()
        if (
            path.is_symlink()
            or resolved != path
            or not stat.S_ISREG(named.st_mode)
            or named.st_nlink != 1
            or named.st_uid != os.getuid()
            or stat.S_IMODE(named.st_mode) & 0o022
            or not 0 <= named.st_size <= maximum_bytes
        ):
            raise OSError("runtime file differs")
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != named.st_dev
            or opened.st_ino != named.st_ino
            or opened.st_size != named.st_size
            or opened.st_mtime_ns != named.st_mtime_ns
            or opened.st_ctime_ns != named.st_ctime_ns
        ):
            raise OSError("runtime file changed")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise OSError("runtime file grew")
            digest.update(chunk)
        finished = os.fstat(descriptor)
        if (
            total != opened.st_size
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
        ):
            raise OSError("runtime file changed")
        return total, digest.hexdigest(), resolved
    except OSError:
        raise ExecutionRuntimeClosureError("runtime file authentication failed") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _read_regular_bytes(path: Path, *, maximum_bytes: int) -> bytes:
    descriptor = -1
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        named = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(named.st_mode)
            or named.st_nlink != 1
            or named.st_uid != os.getuid()
            or stat.S_IMODE(named.st_mode) & 0o022
            or not 0 <= named.st_size <= maximum_bytes
        ):
            raise OSError("runtime source differs")
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if (
            opened.st_dev != named.st_dev
            or opened.st_ino != named.st_ino
            or opened.st_size != named.st_size
            or opened.st_mtime_ns != named.st_mtime_ns
            or opened.st_ctime_ns != named.st_ctime_ns
        ):
            raise OSError("runtime source changed")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise OSError("runtime source grew")
        finished = os.fstat(descriptor)
        if (
            total != opened.st_size
            or finished.st_size != opened.st_size
            or finished.st_mtime_ns != opened.st_mtime_ns
            or finished.st_ctime_ns != opened.st_ctime_ns
        ):
            raise OSError("runtime source changed")
        return b"".join(chunks)
    except OSError:
        raise ExecutionRuntimeClosureError("runtime source changed") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _resolves_inside(path: Path, root: Path) -> bool:
    try:
        return path.resolve(strict=True).is_relative_to(root)
    except OSError:
        return False


def _canonical_json_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def require_sha256(value: object) -> str:
    """Validate a digest supplied by a sealed record without exposing it."""

    if not isinstance(value, str) or _HEX_SHA256.fullmatch(value) is None:
        raise ExecutionRuntimeClosureError("sealed runtime identity differs")
    return value


__all__ = [
    "ActivatedAuthenticatedRuntimeStage",
    "AuthenticatedRuntimeFinder",
    "AuthenticatedRuntimeStage",
    "ExecutionRuntimeClosure",
    "ExecutionRuntimeClosureError",
    "EXPECTED_EXECUTION_RUNTIME_CLOSURE_SHA256",
    "activate_authenticated_runtime_stage",
    "authenticate_execution_runtime_closure",
    "inspect_execution_runtime_closure",
    "prepare_authenticated_runtime_stage",
    "require_loaded_runtime_origins",
    "require_authenticated_runtime_finder",
    "require_sha256",
]
