from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from test_red_living_dex_claim_first_invocation import _fixture

from pokemon_red_completion.red_living_dex_claim_first_invocation import (
    RedLivingDexClaimFirstInvocationError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/preflight_red_living_dex_claim_first_invocation.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "preflight_red_living_dex_claim_first_invocation_script_test",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_nonisolated_cli_fails_before_project_import_with_a_path_free_receipt() -> None:
    completed = subprocess.run(
        (sys.executable, str(SCRIPT_PATH)),
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 1
    receipt = json.loads(completed.stdout)
    assert receipt["stage"] == "bootstrap_source_authentication"
    assert receipt["root_claims"] == 0
    assert receipt["controller_actions"] == 0
    assert receipt["emulator_frames"] == 0
    assert receipt["private_identity_fields"] == 0
    assert receipt["private_path_fields"] == 0
    assert str(PROJECT_ROOT) not in completed.stdout
    assert completed.stderr == ""


def test_parser_is_preflight_only_and_has_no_runtime_capability() -> None:
    module = _load_script()
    actions = {action.dest for action in module._parser()._actions}
    assert "rom" not in actions
    assert "rom_path" not in actions
    assert "execute" not in actions
    assert "mode" not in actions
    assert "store" not in actions
    assert "meter" not in actions
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "execute_red_living_dex_claim_first_invocation" not in source
    assert "RedLivingDexProductionSetupResolver" not in source
    assert "PyBoy" not in source


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("head_sha", "e" * 40),
        ("id", 124),
        ("run_attempt", 2),
        ("status", "queued"),
        ("conclusion", "failure"),
        ("event", "pull_request"),
        ("name", "Other"),
        ("path", ".github/workflows/other.yml"),
        ("html_url", "https://example.invalid/run"),
        ("repository", {"full_name": "other/repository"}),
    ),
)
def test_bootstrap_rejects_wrong_ci_before_project_import(
    field: str,
    value: object,
) -> None:
    module = _load_script()
    document: dict[str, object] = {
        "conclusion": "success",
        "event": "push",
        "head_sha": "c" * 40,
        "html_url": (
            "https://github.com/PeteAndrews1289/pokemon-red-completion-agent/"
            "actions/runs/123"
        ),
        "id": 123,
        "name": "CI",
        "path": ".github/workflows/ci.yml",
        "repository": {"full_name": "PeteAndrews1289/pokemon-red-completion-agent"},
        "run_attempt": 1,
        "status": "completed",
    }
    document[field] = value
    with pytest.raises(module._BootstrapError):
        module._require_exact_green_ci_document(
            document,
            commit="c" * 40,
            exact_ci_run=123,
            exact_ci_attempt=1,
        )


def test_selected_loader_reopens_one_record_and_reads_only_the_selected_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    _plan, store, _record, producer, root = _fixture(tmp_path, ordinal=4)
    private_root = tmp_path / "private"
    state_path = private_root / "selected.state"
    envelope_path = private_root / "selected.state.json"
    state_path.write_bytes(root.state_bytes)
    envelope_path.write_bytes(root.envelope_bytes)
    state_path.chmod(0o600)
    envelope_path.chmod(0o600)
    sibling = private_root / "never-read.state"
    sibling.write_bytes(b"poison")
    sibling.chmod(0o600)
    arguments = SimpleNamespace(
        selected_state=state_path,
        selected_envelope=envelope_path,
        private_root=private_root,
        expected_selected_physical_root_sha256=root.physical_root_sha256,
    )
    reads: list[Path] = []
    original = module._read_regular

    def read(path: Path, **kwargs: object) -> bytes:
        reads.append(path)
        return original(path, **kwargs)

    monkeypatch.setattr(module, "_read_regular", read)
    loader = module._selected_loader(arguments, store)

    first = loader(producer.ordinal)
    second = loader(producer.ordinal)

    assert first.record is not second.record
    assert first.root == second.root == root
    assert reads == [state_path, envelope_path, state_path, envelope_path]
    assert sibling not in reads


def test_selected_loader_rejects_a_wrong_physical_root_without_disclosure(
    tmp_path: Path,
) -> None:
    module = _load_script()
    _plan, store, _record, producer, root = _fixture(tmp_path, ordinal=2)
    private_root = tmp_path / "private"
    state_path = private_root / "selected.state"
    envelope_path = private_root / "selected.state.json"
    state_path.write_bytes(root.state_bytes)
    envelope_path.write_bytes(root.envelope_bytes)
    state_path.chmod(0o600)
    envelope_path.chmod(0o600)
    arguments = SimpleNamespace(
        selected_state=state_path,
        selected_envelope=envelope_path,
        private_root=private_root,
        expected_selected_physical_root_sha256="f" * 64,
    )

    with pytest.raises(
        RedLivingDexClaimFirstInvocationError,
        match="selected_root_authentication",
    ) as caught:
        module._selected_loader(arguments, store)(producer.ordinal)
    assert str(tmp_path) not in str(caught.value)


def test_main_emits_only_the_core_public_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    source_commit = "c" * 40
    source_bundle = "d" * 64
    module._BOOTSTRAP_IDENTITY = (source_commit, source_bundle, 123, 1)
    monkeypatch.setattr(module, "_require_no_third_party_execution", lambda: None)
    monkeypatch.setattr(module, "_open_store", lambda _path: object())
    monkeypatch.setattr(module, "_selected_loader", lambda *_args: object())
    public = {
        "controller_actions": 0,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "root_claims": 0,
        "status": "one_slot_ready_before_claim_or_runtime",
    }
    monkeypatch.setattr(
        module,
        "preflight_red_living_dex_claim_first_invocation",
        lambda *_args, **_kwargs: SimpleNamespace(public_dict=lambda: public),
    )
    private_root = tmp_path / "private"
    state = tmp_path / "state"
    envelope = tmp_path / "envelope"
    argv = [
        "--expected-source-commit",
        source_commit,
        "--expected-source-bundle-sha256",
        source_bundle,
        "--exact-ci-run",
        "123",
        "--exact-ci-attempt",
        "1",
        "--private-root",
        str(private_root),
        "--expected-producer-plan-sha256",
        "a" * 64,
        "--expected-producer-private-plan-sha256",
        "b" * 64,
        "--expected-producer-manifest-sha256",
        "e" * 64,
        "--ordinal",
        "4",
        "--selected-state",
        str(state),
        "--selected-envelope",
        str(envelope),
        "--expected-selected-physical-root-sha256",
        "f" * 64,
    ]

    assert module.main(argv) == 0
    assert json.loads(capsys.readouterr().out) == public


@pytest.mark.parametrize(
    "token",
    ("--rom", "--execute", "--mode", "--resolver", "--retry"),
)
def test_unknown_execution_arguments_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    token: str,
) -> None:
    module = _load_script()
    module._BOOTSTRAP_IDENTITY = ("c" * 40, "d" * 64, 123, 1)
    monkeypatch.setattr(module, "_require_no_third_party_execution", lambda: None)
    assert module.main([token, str(tmp_path)]) == 1
    receipt: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert receipt["stage"] == "arguments"
    assert receipt["root_claims"] == 0
    assert receipt["resolver_constructions"] == 0
