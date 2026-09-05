from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/inspect_repeatable_red_living_dex_development_batch.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "inspect_repeatable_red_living_dex_development_batch_script",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _argv(private_root: Path) -> list[str]:
    labels = (
        "historical-10",
        "historical-11",
        "supplement-0",
        "supplement-1",
        "supplement-2",
    )
    result = ["--private-root", str(private_root)]
    for label in labels:
        result.extend(("--development-root", f"{label}={private_root / f'{label}.state'}"))
    return result


def test_command_reports_storage_collision_before_private_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()
    opened = False
    monkeypatch.setattr(
        module,
        "source_private_storage_is_separate",
        lambda *_args: False,
    )

    def forbidden_open(*_args: object, **_kwargs: object) -> object:
        nonlocal opened
        opened = True
        raise AssertionError("private root opened after storage rejection")

    monkeypatch.setattr(module, "open_private_root", forbidden_open)

    assert module.main(_argv(tmp_path)) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["stage"] == "source_private_storage_separation"
    assert result["root_claims"] == 0
    assert result["model_predictions"] == 0
    assert opened is False


def test_command_emits_path_free_repeatable_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()
    public = {
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "schema": "pokemon.red.living-dex-development-batch-input-readiness.v1",
        "status": "five_development_inputs_ready_without_runtime_or_effects",
    }
    monkeypatch.setattr(
        module,
        "source_private_storage_is_separate",
        lambda *_args: True,
    )
    monkeypatch.setattr(module, "open_private_root", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        module,
        "load_red_living_dex_development_batch_assignments",
        lambda *_args, **_kwargs: tuple(range(5)),
    )
    monkeypatch.setattr(
        module,
        "inspect_red_living_dex_development_batch_inputs",
        lambda *_args, **_kwargs: SimpleNamespace(public_dict=lambda: public),
    )
    monkeypatch.setattr(
        module,
        "_execution_inventory",
        lambda *_args: {
            "cases_remaining": 3,
            "claims_available": 3,
            "incomplete_claims": 0,
            "terminals_retained": 2,
        },
    )

    assert module.main(_argv(tmp_path)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "cases_remaining": 3,
        "claims_available": 3,
        "incomplete_claims": 0,
        "private_identity_fields": 0,
        "private_path_fields": 0,
        "schema": "pokemon.red.repeatable-development-input-readiness.v2",
        "status": "five_development_inputs_joined_with_execution_inventory",
        "terminals_retained": 2,
    }
    assert str(tmp_path) not in json.dumps(result)


def test_execution_inventory_distinguishes_terminals_available_and_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    assignments = tuple(
        SimpleNamespace(
            ordinal=index,
            root=SimpleNamespace(
                root_consumption_sha256=f"logical-{index}",
                physical_root_sha256=f"physical-{index}",
            ),
        )
        for index in range(5)
    )
    monkeypatch.setattr(module, "fixed_account_claim_registry_root", lambda: object())
    monkeypatch.setattr(
        module,
        "find_red_living_dex_development_run_terminal",
        lambda _store, assignment: object() if assignment.ordinal < 2 else None,
    )
    monkeypatch.setattr(
        module,
        "observe_claim_first_pair_availability",
        lambda _registry, logical, _physical: logical in {
            "logical-2",
            "logical-3",
        },
    )

    assert module._execution_inventory(object(), assignments) == {
        "cases_remaining": 3,
        "claims_available": 2,
        "incomplete_claims": 1,
        "terminals_retained": 2,
    }


def test_execution_inventory_rejects_terminal_with_available_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    assignment = SimpleNamespace(
        root=SimpleNamespace(
            root_consumption_sha256="logical",
            physical_root_sha256="physical",
        )
    )
    monkeypatch.setattr(module, "fixed_account_claim_registry_root", lambda: object())
    monkeypatch.setattr(
        module,
        "find_red_living_dex_development_run_terminal",
        lambda *_args: object(),
    )
    monkeypatch.setattr(
        module,
        "observe_claim_first_pair_availability",
        lambda *_args: True,
    )

    with pytest.raises(Exception, match="terminal_claim_state"):
        module._execution_inventory(object(), (assignment,))
