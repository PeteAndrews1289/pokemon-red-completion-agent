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

    assert module.main(_argv(tmp_path)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == public
    assert str(tmp_path) not in json.dumps(result)
