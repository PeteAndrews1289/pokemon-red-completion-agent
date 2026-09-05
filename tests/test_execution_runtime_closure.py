from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pokemon_red_completion import execution_runtime_closure as runtime


def _write_record(path: Path, names: tuple[str, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for name in names:
            writer.writerow((name, "", ""))


def _fake_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    extra_record_names: tuple[str, ...] = (),
) -> Path:
    site = (tmp_path / "site-packages").resolve()
    package = site / "pyboy"
    metadata = site / "pyboy-1.0.dist-info"
    package.mkdir(parents=True)
    metadata.mkdir()
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="ascii")
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: pyboy\nVersion: 1.0\n",
        encoding="ascii",
    )
    record_names = (
        "pyboy/__init__.py",
        "pyboy-1.0.dist-info/METADATA",
        "pyboy-1.0.dist-info/RECORD",
        *extra_record_names,
    )
    _write_record(metadata / "RECORD", record_names)
    monkeypatch.setattr(
        runtime,
        "_DISTRIBUTIONS",
        (
            runtime._DistributionSpec(
                "pyboy",
                "1.0",
                "pyboy-1.0.dist-info",
                ("pyboy",),
            ),
        ),
    )
    return site


def test_mutated_distribution_byte_fails_exact_closure_authentication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _fake_site(tmp_path, monkeypatch)
    expected = runtime.inspect_execution_runtime_closure(site).sha256
    monkeypatch.setattr(
        runtime,
        "EXPECTED_EXECUTION_RUNTIME_CLOSURE_SHA256",
        expected,
    )

    assert runtime.authenticate_execution_runtime_closure(site).sha256 == expected
    (site / "pyboy/__init__.py").write_text("VALUE = 2\n", encoding="ascii")

    with pytest.raises(
        runtime.ExecutionRuntimeClosureError,
        match="closure differs",
    ):
        runtime.authenticate_execution_runtime_closure(site)


def test_explicit_additional_reviewed_closure_is_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _fake_site(tmp_path, monkeypatch)
    alternate = runtime.inspect_execution_runtime_closure(site).sha256
    monkeypatch.setattr(
        runtime,
        "EXPECTED_EXECUTION_RUNTIME_CLOSURE_SHA256",
        "0" * 64,
    )
    monkeypatch.setattr(
        runtime,
        "ADDITIONAL_EXECUTION_RUNTIME_CLOSURE_SHA256S",
        (alternate,),
    )

    assert runtime.authenticate_execution_runtime_closure(site).sha256 == alternate

    (site / "pyboy/__init__.py").write_text("VALUE = 2\n", encoding="ascii")
    with pytest.raises(
        runtime.ExecutionRuntimeClosureError,
        match="closure differs",
    ):
        runtime.authenticate_execution_runtime_closure(site)


@pytest.mark.parametrize(
    "relative",
    ("pyboy.py", "pyboy/hidden.py", "pyboy/__pycache__/poison.pyc"),
)
def test_shadow_unlisted_and_bytecode_files_fail_the_runtime_census(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
) -> None:
    site = _fake_site(tmp_path, monkeypatch)
    unexpected = site / relative
    unexpected.parent.mkdir(parents=True, exist_ok=True)
    unexpected.write_bytes(b"unreviewed")

    with pytest.raises(runtime.ExecutionRuntimeClosureError):
        runtime.inspect_execution_runtime_closure(site)


def test_record_parent_escape_is_rejected_before_outside_file_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _fake_site(
        tmp_path,
        monkeypatch,
        extra_record_names=("../outside.py",),
    )
    outside = site.parent / "outside.py"
    outside.write_text("raise RuntimeError\n", encoding="ascii")
    opened: list[Path] = []
    original = runtime._hash_regular_file

    def observe(path: Path, **kwargs: object):  # type: ignore[no-untyped-def]
        opened.append(path.resolve(strict=True))
        return original(path, **kwargs)

    monkeypatch.setattr(runtime, "_hash_regular_file", observe)

    with pytest.raises(
        runtime.ExecutionRuntimeClosureError,
        match="escapes its namespace",
    ):
        runtime.inspect_execution_runtime_closure(site)
    assert outside.resolve() not in opened


def test_clean_stage_omits_unrelated_optional_packages_and_caches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _fake_site(tmp_path, monkeypatch)
    optional = site / "OpenGL/__init__.py"
    optional.parent.mkdir()
    optional.write_text("raise RuntimeError('must not import')\n", encoding="ascii")
    expected = runtime.inspect_execution_runtime_closure(site).sha256
    monkeypatch.setattr(
        runtime,
        "EXPECTED_EXECUTION_RUNTIME_CLOSURE_SHA256",
        expected,
    )

    with runtime.prepare_authenticated_runtime_stage(site) as stage:
        stage_root = stage.closure.site_packages.parents[3]
        assert stage.closure.sha256 == expected
        assert not (stage.closure.site_packages / "OpenGL").exists()
        assert not tuple(stage.closure.site_packages.rglob("__pycache__"))
        assert not tuple(stage.closure.site_packages.rglob("*.pyc"))
    assert not stage_root.exists()


@pytest.mark.parametrize("attack", ("symlink", "hardlink", "writable"))
def test_alias_or_mutable_runtime_file_fails_before_authentication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    site = _fake_site(tmp_path, monkeypatch)
    package_file = site / "pyboy/__init__.py"
    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 1\n", encoding="ascii")
    if attack == "symlink":
        package_file.unlink()
        package_file.symlink_to(outside)
    elif attack == "hardlink":
        package_file.unlink()
        os.link(outside, package_file)
    else:
        package_file.chmod(0o666)

    with pytest.raises(runtime.ExecutionRuntimeClosureError):
        runtime.inspect_execution_runtime_closure(site)


def test_authenticated_finder_and_postcheck_reject_out_of_closure_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _fake_site(tmp_path, monkeypatch)
    expected = runtime.inspect_execution_runtime_closure(site).sha256
    monkeypatch.setattr(
        runtime,
        "EXPECTED_EXECUTION_RUNTIME_CLOSURE_SHA256",
        expected,
    )

    with runtime.prepare_authenticated_runtime_stage(site) as stage:
        hidden = stage.closure.site_packages / "pyboy/hidden.py"
        hidden.write_text("VALUE = 2\n", encoding="ascii")
        finder = runtime.AuthenticatedRuntimeFinder(stage.closure)
        with pytest.raises(ImportError, match="unauthenticated site import"):
            finder.find_spec("pyboy.hidden", [str(hidden.parent)])
        hidden.unlink()

        foreign = ModuleType("pyboy.foreign")
        foreign.__file__ = str((tmp_path / "foreign.py").resolve())
        Path(foreign.__file__).write_text("VALUE = 3\n", encoding="ascii")
        monkeypatch.setitem(sys.modules, "pyboy.foreign", foreign)
        with pytest.raises(runtime.ExecutionRuntimeClosureError):
            runtime.require_loaded_runtime_origins(stage.closure)


def test_runtime_postcheck_detects_staged_byte_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _fake_site(tmp_path, monkeypatch)
    expected = runtime.inspect_execution_runtime_closure(site).sha256
    monkeypatch.setattr(
        runtime,
        "EXPECTED_EXECUTION_RUNTIME_CLOSURE_SHA256",
        expected,
    )

    with runtime.prepare_authenticated_runtime_stage(site) as stage:
        package_file = stage.closure.site_packages / "pyboy/__init__.py"
        package_file.write_text("VALUE = 9\n", encoding="ascii")
        with pytest.raises(
            runtime.ExecutionRuntimeClosureError,
            match="closure differs",
        ):
            runtime.require_loaded_runtime_origins(stage.closure)


def test_runtime_stage_cannot_be_constructed_over_an_arbitrary_directory(
    tmp_path: Path,
) -> None:
    site = (tmp_path / "venv/lib/python3.14/site-packages").resolve()
    site.mkdir(parents=True)
    closure = runtime.ExecutionRuntimeClosure((), site)

    with pytest.raises(
        runtime.ExecutionRuntimeClosureError,
        match="stage root differs",
    ):
        runtime.AuthenticatedRuntimeStage(
            closure,
            tmp_path.resolve(),
            runtime._RUNTIME_STAGE_AUTHORITY,
        )


def test_activation_replaces_only_source_site_and_restores_interpreter_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _fake_site(tmp_path, monkeypatch)
    expected = runtime.inspect_execution_runtime_closure(site).sha256
    monkeypatch.setattr(runtime, "EXPECTED_EXECUTION_RUNTIME_CLOSURE_SHA256", expected)
    project_path = str((tmp_path / "project").resolve())
    monkeypatch.setattr(runtime.sys, "path", [project_path, str(site)])
    previous_meta_path = list(runtime.sys.meta_path)

    active = runtime.activate_authenticated_runtime_stage(site)
    staged_site = active.closure.site_packages

    assert runtime.sys.path == [project_path, str(staged_site)]
    assert runtime.sys.meta_path[0] is active.finder
    runtime.require_authenticated_runtime_finder(active.closure)
    active.close()

    assert runtime.sys.path == [project_path, str(site)]
    assert runtime.sys.meta_path == previous_meta_path
    assert not staged_site.parents[3].exists()


def test_activation_rejects_an_additional_third_party_search_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _fake_site(tmp_path, monkeypatch)
    foreign = tmp_path / "foreign/site-packages"
    foreign.mkdir(parents=True)
    foreign_module = ModuleType("foreign_runtime")
    foreign_module.__file__ = str(foreign / "foreign_runtime.py")
    Path(foreign_module.__file__).write_text("VALUE = 1\n", encoding="ascii")
    monkeypatch.setitem(sys.modules, "foreign_runtime", foreign_module)
    monkeypatch.setattr(runtime.sys, "path", [str(site), str(foreign)])

    with pytest.raises(runtime.ExecutionRuntimeClosureError, match="module loaded before"):
        runtime.activate_authenticated_runtime_stage(site)

    assert runtime.sys.path == [str(site), str(foreign)]
