from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
from types import ModuleType

import pytest

from pokemon_red_completion.red_living_dex_development_batch import (
    RED_LIVING_DEX_DEVELOPMENT_BATCH_PREFLIGHT_SCHEMA,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/preflight_red_living_dex_development_batch.py"
TRAIN_SCRIPT_PATH = PROJECT_ROOT / "scripts/run_red_living_dex_causal_campaign.py"
_COMMIT = "a" * 40
_DIGEST = "b" * 64


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "preflight_red_living_dex_development_batch_script", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_path(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _arguments(tmp_path: Path) -> list[str]:
    result = [
        "--private-root",
        str(tmp_path),
        "--expected-source-commit",
        _COMMIT,
        "--expected-source-bundle-sha256",
        _DIGEST,
        "--exact-ci-run",
        "123",
        "--exact-ci-attempt",
        "1",
    ]
    for label in (
        "historical-10",
        "historical-11",
        "supplement-0",
        "supplement-1",
        "supplement-2",
    ):
        result.extend(["--development-root", f"{label}={tmp_path / f'{label}.state'}"])
    return result


class _Receipt:
    def public_dict(self) -> dict[str, object]:
        return {
            "cases_ready": 5,
            "controller_actions": 0,
            "development_outcomes_opened": 0,
            "emulator_frames": 0,
            "historical_cases_ready": 2,
            "model_fits": 0,
            "model_predictions": 0,
            "model_record_sha256": "c" * 64,
            "model_sha256": "d" * 64,
            "partition": "development",
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_claims": 0,
            "schema": RED_LIVING_DEX_DEVELOPMENT_BATCH_PREFLIGHT_SCHEMA,
            "status": "five_development_roots_ready_without_effects",
            "supplement_cases_ready": 3,
            "teacher_queries": 0,
            "training_targets_emitted": 0,
        }


def test_command_exposes_only_exact_action_free_batch_arguments() -> None:
    module = _load_script()
    actions = {action.dest for action in module._parser()._actions}
    assert actions == {
        "help",
        "private_root",
        "expected_source_commit",
        "expected_source_bundle_sha256",
        "exact_ci_run",
        "exact_ci_attempt",
        "development_root",
    }
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for forbidden in (
        'add_argument("--rom"',
        'add_argument("--ordinal"',
        'add_argument("--retry"',
        "model.predict(",
        "controller.step(",
    ):
        assert forbidden not in source
    bootstrap = source.index("_BOOTSTRAP_IDENTITY = _authenticate_current_source")
    project_import = source.index(
        "from pokemon_red_completion.execution_runtime_closure import"
    )
    runtime_stage = source.index(
        "_RUNTIME_STAGE = prepare_authenticated_runtime_stage"
    )
    assert bootstrap < project_import < runtime_stage
    assert (
        'SCRIPT_RELATIVE_PATH = "scripts/preflight_red_living_dex_development_batch.py"'
        in source
    )


def test_successor_reuses_the_qualified_train_bootstrap_without_weakening_it() -> None:
    successor = _load_script()
    historical = _load_path(TRAIN_SCRIPT_PATH, "qualified_historical_train_script")
    functions = (
        "_minimal_git_environment",
        "_read_regular",
        "_require_interpreter",
        "_require_environment",
        "_tracked_source_inventory",
        "_committed_red_source_bundle_sha256",
        "_require_exact_green_ci",
        "_require_source_state",
        "_authenticate_current_source",
        "_install_numpy_sentinel",
        "_require_project_import_boundary",
        "_enable_authenticated_project",
        "_enable_authenticated_third_party_search",
        "_remove_numpy_sentinel_for_postclaim_runtime",
    )
    for name in functions:
        assert inspect.getsource(getattr(successor, name)) == inspect.getsource(
            getattr(historical, name)
        )
    constants = (
        "_BOOTSTRAP_PYTHON",
        "_BOOTSTRAP_PYTHON_SHA256",
        "_BOOTSTRAP_GIT",
        "_BOOTSTRAP_GIT_SHA256",
        "_BOOTSTRAP_CA_BUNDLE",
        "_BOOTSTRAP_CA_BUNDLE_SHA256",
        "_GITHUB_REPOSITORY",
        "_CI_WORKFLOW_NAME",
        "_CI_WORKFLOW_PATH",
    )
    for name in constants:
        assert getattr(successor, name) == getattr(historical, name)


@pytest.mark.parametrize(
    "mutation",
    ("missing", "duplicate", "unknown", "relative"),
)
def test_exact_five_root_labels_are_required(tmp_path: Path, mutation: str) -> None:
    module = _load_script()
    values = [
        f"historical-10={tmp_path / 'a'}",
        f"historical-11={tmp_path / 'b'}",
        f"supplement-0={tmp_path / 'c'}",
        f"supplement-1={tmp_path / 'd'}",
        f"supplement-2={tmp_path / 'e'}",
    ]
    if mutation == "missing":
        values.pop()
    elif mutation == "duplicate":
        values[-1] = values[0]
    elif mutation == "unknown":
        values[-1] = f"supplement-3={tmp_path / 'e'}"
    else:
        values[-1] = "supplement-2=relative.state"
    with pytest.raises(module.DevelopmentBatchCommandError, match="arguments"):
        module._parse_roots(values)


def test_main_authenticates_then_preflights_without_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    calls: list[str] = []
    sentinel_store = object()
    sentinel_assignments = tuple(object() for _ in range(5))

    def open_root(*_args: object, **_kwargs: object) -> object:
        calls.append("store")
        return sentinel_store

    def assignments(*_args: object, **_kwargs: object) -> tuple[object, ...]:
        calls.append("roots")
        return sentinel_assignments

    def preflight(*args: object, **kwargs: object) -> _Receipt:
        calls.append("preflight")
        assert args[1] is sentinel_store
        assert kwargs["assignments"] is sentinel_assignments
        return _Receipt()

    monkeypatch.setattr(module, "_BOOTSTRAP_IDENTITY", (_COMMIT, _DIGEST, 123, 1))
    monkeypatch.setattr(module, "open_private_root", open_root)
    monkeypatch.setattr(module, "_assignments", assignments)
    monkeypatch.setattr(module, "preflight_red_living_dex_development_batch", preflight)
    monkeypatch.setattr(module, "_require_source_state", lambda **_kwargs: None)

    assert module.main(_arguments(tmp_path)) == 0
    result = json.loads(capsys.readouterr().out)
    assert calls == ["store", "roots", "preflight"]
    assert result["cases_ready"] == 5
    assert result["status"] == "five_development_roots_ready_without_effects"
    assert result["controller_actions"] == 0
    assert result["model_predictions"] == 0


def test_source_failure_cannot_open_private_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()

    monkeypatch.setattr(module, "_BOOTSTRAP_IDENTITY", None)
    monkeypatch.setattr(
        module,
        "open_private_root",
        lambda *_args, **_kwargs: pytest.fail("private store opened"),
    )
    assert module.main(_arguments(tmp_path)) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["stage"] == "bootstrap_source_authentication"
    assert result["controller_actions"] == 0
    assert result["model_predictions"] == 0
