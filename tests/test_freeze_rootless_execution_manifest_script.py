# ruff: noqa: E402 -- script is loaded as a standalone boundary.

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from public_execution_manifest import PUBLIC_EXECUTION_MANIFEST_DIRECTORY

SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/freeze_rootless_execution_manifest.py"),
    run_name="freeze_rootless_execution_manifest_script_test",
)


def _bindings() -> dict[str, str]:
    return {
        "source_commit": "a" * 40,
        "source_bundle_sha256": "1" * 64,
        "runner_sha256": "2" * 64,
        "core_sha256": "3" * 64,
        "manifest_freezer_sha256": "4" * 64,
        "runtime_sha256": "5" * 64,
    }


def _arguments(manifest: Path, action: str) -> list[str]:
    return [
        "--action",
        action,
        "--lane-id",
        "rootless-living-dex-dependency-curriculum-v1",
        "--operation",
        "preflight",
        "--runner",
        "scripts/run_rootless_living_dex_dependency_campaign.py",
        "--dependency",
        "core=src/pokemon_red_completion/living_dex_dependency_curriculum.py",
        "--semantic-binding",
        f"development_roster_sha256={'6' * 64}",
        "--private-input-role",
        "private_root",
        "--private-input-role",
        "claim_registry",
        "--manifest",
        str(manifest),
    ]


def test_freezes_and_validates_without_private_or_claim_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    public_root = tmp_path / PUBLIC_EXECUTION_MANIFEST_DIRECTORY
    public_root.mkdir()
    manifest = public_root / "rootless.json"
    for globals_dict in (SCRIPT, SCRIPT["main"].__globals__, SCRIPT["_write_manifest"].__globals__):
        monkeypatch.setitem(globals_dict, "PUBLIC_MANIFEST_ROOT", public_root)
    monkeypatch.setitem(SCRIPT["main"].__globals__, "PROJECT_ROOT", tmp_path)
    monkeypatch.setitem(
        SCRIPT["main"].__globals__,
        "_current_public_bindings",
        lambda **kwargs: _bindings(),
    )

    assert SCRIPT["main"](_arguments(manifest, "freeze")) == 0
    frozen = json.loads(capsys.readouterr().out)
    assert frozen["private_inputs_opened"] == 0
    assert frozen["claim_registry_accesses"] == 0
    assert frozen["synthetic_transitions"] == 0

    validate = _arguments(manifest, "validate")
    validate.extend(("--expected-manifest-sha256", frozen["execution_manifest_sha256"]))
    assert SCRIPT["main"](validate) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["status"] == "rootless_public_invocation_validated"


def test_argument_failure_is_path_free(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_looking = tmp_path / "secret" / "manifest.json"
    assert SCRIPT["main"](["--manifest", str(private_looking)]) == 1
    result = capsys.readouterr()
    assert str(tmp_path) not in result.out
    assert result.err == ""
    assert json.loads(result.out)["private_path_fields"] == 0
