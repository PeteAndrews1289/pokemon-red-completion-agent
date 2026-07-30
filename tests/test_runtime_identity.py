from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from pokemon_red_completion import runtime_identity as runtime_identity_module
from pokemon_red_completion.runtime_identity import (
    PYBOY_INVENTORY_SCHEMA,
    RUNTIME_IDENTITY_SCHEMA,
    RuntimeIdentityError,
    build_runtime_identity,
    build_runtime_identity_from,
    is_canonical_distribution_inventory_name,
    is_runtime_identity_public_document,
)


@dataclass(frozen=True)
class _EntryPoint:
    name: str
    group: str = "console_scripts"


class _Distribution:
    def __init__(
        self,
        root: Path,
        files: list[str] | None,
        *,
        name: str = "pyboy",
        version: str = "2.7.0",
        entry_points: tuple[_EntryPoint, ...] = (),
        locations: dict[str, Path] | None = None,
    ) -> None:
        self._root = root
        self.files = files
        self.metadata = {"Name": name}
        self.version = version
        self.entry_points = entry_points
        self._locations = locations or {}

    def locate_file(self, entry: object) -> Path:
        name = str(entry)
        return self._locations.get(name, self._root / name)


def _executable(tmp_path: Path, payload: bytes = b"python executable") -> Path:
    executable = tmp_path / "python"
    executable.write_bytes(payload)
    executable.chmod(0o700)
    return executable


def _file(root: Path, name: str, payload: bytes) -> None:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _identity_from(
    tmp_path: Path,
    distribution: _Distribution,
):
    return build_runtime_identity_from(
        python_executable=_executable(tmp_path),
        python_implementation="CPython",
        python_version="3.14.3",
        pyboy_distribution=distribution,
    )


def test_active_runtime_identity_is_path_free_canonical_and_content_addressed() -> None:
    identity = build_runtime_identity()
    payload = identity.public_dict()
    canonical = identity.canonical_bytes()
    serialized = canonical.decode("ascii")

    assert payload["schema"] == RUNTIME_IDENTITY_SCHEMA
    assert payload["python"]["implementation"] == "CPython"
    assert payload["pyboy"]["distribution_name"] == "pyboy"
    assert payload["pyboy"]["distribution_version"] == "2.7.0"
    assert identity.pyboy_files
    assert is_runtime_identity_public_document(payload) is True
    missing_schema = dict(payload)
    del missing_schema["schema"]
    assert is_runtime_identity_public_document(missing_schema) is False
    assert identity.sha256 == hashlib.sha256(canonical).hexdigest()
    assert canonical.endswith(b"\n")
    assert canonical == (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    assert "/Users/" not in serialized
    assert str(Path(os.sys.executable).resolve()) not in serialized
    assert all(not file.name.startswith("/") for file in identity.pyboy_files)
    assert all(".." not in file.name.split("/") for file in identity.pyboy_files)
    assert all("__pycache__" not in file.name for file in identity.pyboy_files)
    assert all(not file.name.casefold().endswith((".pyc", ".pyo")) for file in identity.pyboy_files)


@pytest.mark.parametrize(
    "name",
    (
        "pyboy/api/constants.py",
        "pyboy-2.7.0.dist-info/licenses/LICENSE.md",
        "console_scripts/up-3/pyboy",
    ),
)
def test_canonical_distribution_inventory_name_accepts_safe_logical_names(
    name: str,
) -> None:
    assert is_canonical_distribution_inventory_name(name) is True


@pytest.mark.parametrize(
    "name",
    (
        "/Users/example/pyboy.py",
        r"C:\Users\example\pyboy.py",
        "~/pyboy.py",
        "file:pyboy/runtime.py",
        "../pyboy/runtime.py",
        "pyboy/../runtime.py",
        "pyboy/./runtime.py",
        "pyboy//runtime.py",
        r"pyboy\private.py",
        "pyboy/runtimé.py",
        "Users/example/Downloads/private.gb",
        "private/api-token.txt",
        b"pyboy/runtime.py",
    ),
)
def test_canonical_distribution_inventory_name_rejects_location_or_traversal(
    name: object,
) -> None:
    assert is_canonical_distribution_inventory_name(name) is False


def test_explicit_identity_sorts_files_excludes_caches_and_hashes_exact_bytes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "site"
    _file(root, "pyboy/z.py", b"z")
    _file(root, "pyboy/a.py", b"alpha")
    distribution = _Distribution(
        root,
        [
            "pyboy/z.py",
            "pyboy/__pycache__/z.cpython-314.pyc",
            "pyboy/a.py",
            "pyboy/a.pyo",
        ],
    )
    identity = _identity_from(tmp_path, distribution)

    assert [file.name for file in identity.pyboy_files] == [
        "pyboy/a.py",
        "pyboy/z.py",
    ]
    assert identity.pyboy_files[0].size == 5
    assert identity.pyboy_files[0].sha256 == hashlib.sha256(b"alpha").hexdigest()
    inventory = {
        "schema": PYBOY_INVENTORY_SCHEMA,
        "distribution_name": "pyboy",
        "distribution_version": "2.7.0",
        "files": [file.public_dict() for file in identity.pyboy_files],
    }
    expected = (
        json.dumps(
            inventory,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    assert identity.pyboy_inventory_sha256 == hashlib.sha256(expected).hexdigest()


def test_python_executable_symlink_resolves_to_and_hashes_exact_target(
    tmp_path: Path,
) -> None:
    target = _executable(tmp_path, b"exact interpreter bytes")
    link = tmp_path / "python-link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    root = tmp_path / "site"
    _file(root, "pyboy/runtime.py", b"runtime")
    identity = build_runtime_identity_from(
        python_executable=link,
        python_implementation="CPython",
        python_version="3.14.3",
        pyboy_distribution=_Distribution(root, ["pyboy/runtime.py"]),
    )

    assert identity.python_executable_sha256 == hashlib.sha256(
        b"exact interpreter bytes"
    ).hexdigest()


def test_declared_console_launcher_gets_a_safe_logical_inventory_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "site"
    launcher = tmp_path / "bin" / "pyboy"
    launcher.parent.mkdir()
    launcher.write_bytes(b"launcher")
    raw_name = "../../../bin/pyboy"
    distribution = _Distribution(
        root,
        [raw_name],
        entry_points=(_EntryPoint("pyboy"),),
        locations={raw_name: launcher},
    )

    identity = _identity_from(tmp_path, distribution)

    assert [file.name for file in identity.pyboy_files] == [
        "console_scripts/up-3/pyboy"
    ]


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "/absolute/runtime.py",
        "../runtime.py",
        "pyboy/../runtime.py",
        "pyboy/./runtime.py",
        "pyboy//runtime.py",
        "pyboy\\runtime.py",
        "pyboy/runtimé.py",
    ],
)
def test_inventory_rejects_unsafe_relative_names(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    distribution = _Distribution(tmp_path / "site", [unsafe_name])

    with pytest.raises(RuntimeIdentityError, match="inventory name is unsafe"):
        _identity_from(tmp_path, distribution)


def test_inventory_rejects_duplicate_names_before_reading_files(tmp_path: Path) -> None:
    distribution = _Distribution(
        tmp_path / "site",
        ["pyboy/runtime.py", "pyboy/runtime.py"],
    )

    with pytest.raises(RuntimeIdentityError, match="duplicate names"):
        _identity_from(tmp_path, distribution)


@pytest.mark.parametrize("case", ["missing", "directory", "symlink"])
def test_inventory_rejects_missing_nonregular_and_symlink_files(
    tmp_path: Path,
    case: str,
) -> None:
    root = tmp_path / "site"
    target = root / "pyboy" / "runtime.py"
    target.parent.mkdir(parents=True)
    if case == "directory":
        target.mkdir()
    elif case == "symlink":
        source = root / "source.py"
        source.write_bytes(b"source")
        try:
            target.symlink_to(source)
        except OSError:
            pytest.skip("symbolic links are unavailable")
    distribution = _Distribution(root, ["pyboy/runtime.py"])

    with pytest.raises(RuntimeIdentityError) as error:
        _identity_from(tmp_path, distribution)

    assert str(root) not in str(error.value)
    assert (
        "missing" in str(error.value)
        or "regular file" in str(error.value)
        or "symbolic link" in str(error.value)
    )


def test_inventory_streams_in_bounded_chunks_and_enforces_size_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "site"
    _file(root, "pyboy/runtime.bin", b"0123456789")
    distribution = _Distribution(root, ["pyboy/runtime.bin"])
    real_read = runtime_identity_module.os.read
    requested: list[int] = []

    def bounded_read(descriptor: int, size: int) -> bytes:
        requested.append(size)
        return real_read(descriptor, size)

    monkeypatch.setattr(runtime_identity_module, "_READ_CHUNK_BYTES", 3)
    monkeypatch.setattr(runtime_identity_module.os, "read", bounded_read)
    identity = _identity_from(tmp_path, distribution)

    assert identity.pyboy_files[0].size == 10
    assert requested
    assert max(requested) <= 3

    monkeypatch.setattr(runtime_identity_module, "_MAX_DISTRIBUTION_FILE_BYTES", 9)
    with pytest.raises(RuntimeIdentityError, match="size limit"):
        _identity_from(tmp_path, distribution)


def test_runtime_identity_rejects_wrong_or_incomplete_distribution_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "site"
    _file(root, "pyboy/runtime.py", b"runtime")

    with pytest.raises(RuntimeIdentityError, match="not PyBoy"):
        _identity_from(
            tmp_path,
            _Distribution(root, ["pyboy/runtime.py"], name="different"),
        )
    with pytest.raises(RuntimeIdentityError, match="inventory is unavailable"):
        _identity_from(tmp_path, _Distribution(root, None))
    with pytest.raises(RuntimeIdentityError, match="requires CPython"):
        build_runtime_identity_from(
            python_executable=_executable(tmp_path),
            python_implementation="PyPy",
            python_version="3.11.0",
            pyboy_distribution=_Distribution(root, ["pyboy/runtime.py"]),
        )
