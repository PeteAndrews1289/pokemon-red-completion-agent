# ruff: noqa: E402 -- the script module is deliberately outside the package bundle.

from __future__ import annotations

import json
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from public_execution_manifest import (
    PUBLIC_EXECUTION_MANIFEST_DIRECTORY,
    PublicExecutionManifestError,
)

SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/freeze_causal_execution_manifest.py"),
    run_name="freeze_causal_execution_manifest_script_test",
)


def _bindings() -> dict[str, str]:
    return {
        "source_commit": "a" * 40,
        "source_bundle_sha256": "1" * 64,
        "runner_sha256": "2" * 64,
        "dependency_sha256": "3" * 64,
        "runtime_sha256": "4" * 64,
        "numpy_runtime_sha256": "5" * 64,
        "skill_manifest_sha256": "6" * 64,
        "manifest_freezer_sha256": "7" * 64,
    }


def _arguments(manifest: Path, *, action: str) -> list[str]:
    values = [
        "--action",
        action,
        "--lane-id",
        "future-causal-lane-v2",
        "--runner",
        "scripts/future_causal_runner.py",
        "--dependency",
        "dependency=scripts/future_dependency.py",
        "--operation",
        "freeze",
        "--expected-context-plan-sha256",
        "b" * 64,
        "--expected-fit-result-receipt-sha256",
        "c" * 64,
        "--expected-prior-campaign-sha256",
        "d" * 64,
        "--manifest",
        str(manifest),
    ]
    return values


def test_freezes_and_validates_without_private_rom_or_claim_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    public_root = tmp_path / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
    public_root.mkdir()
    manifest = public_root / "manifest.json"
    monkeypatch.setitem(SCRIPT, "PUBLIC_MANIFEST_ROOT", public_root)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "PUBLIC_MANIFEST_ROOT",
        public_root,
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_current_public_bindings",
        lambda **kwargs: _bindings(),
    )

    assert SCRIPT["main"](_arguments(manifest, action="freeze")) == 0
    frozen = json.loads(capsys.readouterr().out)
    assert frozen["private_inputs_opened"] == 0
    assert frozen["rom_accesses"] == 0
    assert frozen["claim_registry_accesses"] == 0

    validate = _arguments(manifest, action="validate")
    validate.extend(("--expected-manifest-sha256", frozen["execution_manifest_sha256"]))
    assert SCRIPT["main"](validate) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["status"] == "future_lane_public_invocation_manifest_validated"


def test_real_freeze_then_validate_bootstraps_ignored_public_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    shutil.copytree(PROJECT_ROOT / "src", repository / "src")
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", repository / "pyproject.toml")
    shutil.copy2(PROJECT_ROOT / ".gitignore", repository / ".gitignore")
    scripts = repository / "scripts"
    scripts.mkdir()
    (scripts / "future_causal_runner.py").write_text("# future runner\n")
    (scripts / "future_dependency.py").write_text("# future dependency\n")
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "manifest-test@example.invalid")
    _git(repository, "config", "user.name", "Manifest Test")
    _git(repository, "add", ".")
    _git(repository, "commit", "-qm", "public source")
    _git(repository, "update-ref", "refs/remotes/origin/main", "HEAD")

    public_root = repository / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
    manifest = public_root / "future-lane.json"
    monkeypatch.setitem(SCRIPT["main"].__globals__, "PROJECT_ROOT", repository)
    monkeypatch.setitem(SCRIPT["main"].__globals__, "SCRIPTS_ROOT", scripts)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "PUBLIC_MANIFEST_ROOT",
        public_root,
    )

    assert not public_root.exists()
    assert SCRIPT["main"](_arguments(manifest, action="freeze")) == 0
    frozen = json.loads(capsys.readouterr().out)
    assert public_root.is_dir()
    assert _git(repository, "status", "--porcelain", "--untracked-files=all") == ""

    validate = _arguments(manifest, action="validate")
    validate.extend(("--expected-manifest-sha256", frozen["execution_manifest_sha256"]))
    assert SCRIPT["main"](validate) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["status"] == "future_lane_public_invocation_manifest_validated"
    assert checked["private_inputs_opened"] == 0
    assert checked["rom_accesses"] == 0
    assert checked["claim_registry_accesses"] == 0
    assert _git(repository, "status", "--porcelain", "--untracked-files=all") == ""


@pytest.mark.parametrize(
    ("lane", "runner"),
    (
        ("first-causal-goal-outcome-v1", "scripts/future_causal_runner.py"),
        ("future-causal-lane-v2", "scripts/run_single_root_causal_goal_outcome.py"),
    ),
)
def test_never_targets_retired_lane_or_runner(
    lane: str,
    runner: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        SCRIPT["_current_public_bindings"].__globals__,
        "detect_source_identity",
        lambda *args, **kwargs: pytest.fail("source opened after retired target"),
    )

    with pytest.raises(PublicExecutionManifestError):
        SCRIPT["_current_public_bindings"](
            lane_id=lane,
            runner=runner,
            dependencies=["dependency=scripts/future_dependency.py"],
        )


def test_failure_output_never_contains_destination_or_private_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    public_root = tmp_path / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
    public_root.mkdir()
    manifest = public_root / "sensitive-name.json"
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_current_public_bindings",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("/private/secret")),
    )

    assert SCRIPT["main"](_arguments(manifest, action="freeze")) == 1
    output = capsys.readouterr().out
    assert "/private/secret" not in output
    assert str(manifest) not in output
    assert json.loads(output)["failure_stage"] == "public_manifest_qualification"
    assert not manifest.exists()


def test_refuses_arbitrary_manifest_destination_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    public_root = tmp_path / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
    public_root.mkdir()
    outside = tmp_path / "outside.json"
    monkeypatch.setitem(
        SCRIPT["_write_public_manifest"].__globals__,
        "PUBLIC_MANIFEST_ROOT",
        public_root,
    )

    with pytest.raises(PublicExecutionManifestError, match="location"):
        SCRIPT["_write_public_manifest"](outside, b"{}\n")


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
