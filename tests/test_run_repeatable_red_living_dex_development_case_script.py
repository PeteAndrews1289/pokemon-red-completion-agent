from __future__ import annotations

import runpy
from contextlib import AbstractContextManager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_red_living_dex_clustered_development_execution import _model_record
from test_red_living_dex_development_batch import _assignments

from pokemon_red_completion.progress_dashboard import DashboardSnapshot
from pokemon_red_completion.red_living_dex_causal_invocation import (
    RedLivingDexCausalInvocationError,
)
from pokemon_red_completion.red_living_dex_development_batch import (
    RedLivingDexDevelopmentBatchError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_repeatable_red_living_dex_development_case.py"
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def test_runner_exposes_no_case_selection_or_mutable_limit_argument() -> None:
    parser = SCRIPT["_parser"]()
    actions = {action.dest for action in parser._actions}

    assert "development_root" in actions
    assert "rom" in actions
    assert "case" not in actions
    assert "ordinal" not in actions
    assert "maximum_controller_actions" not in actions
    assert "maximum_emulator_frames" not in actions
    assert SCRIPT["MAXIMUM_CONTROLLER_ACTIONS"] == 20_000
    assert SCRIPT["MAXIMUM_EMULATOR_FRAMES"] == 2_000_000


def test_runner_prioritizes_first_incomplete_case_for_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignments, expected, _historical, _supplement = _assignments()
    opened: list[tuple[str, int]] = []

    def load(_store: object, ordinal: int, *, binding: Any) -> tuple[Any, dict]:
        key = (binding.private_plan_sha256, ordinal)
        selection, _root = expected[key]
        opened.append(key)
        return selection, {}

    availability = iter((False, True, True, False, True))
    globals_ = SCRIPT["_first_pending"].__globals__
    monkeypatch.setitem(globals_, "fixed_account_claim_registry_root", lambda: tmp_path)
    monkeypatch.setitem(globals_, "load_red_living_dex_development_selection", load)
    monkeypatch.setitem(
        globals_,
        "observe_claim_first_pair_availability",
        lambda *_args: next(availability),
    )
    monkeypatch.setitem(
        globals_,
        "find_red_living_dex_development_run_terminal",
        lambda *_args: None,
    )

    selected, count, recovering = SCRIPT["_first_pending"](object(), assignments)

    assert selected is assignments[0]
    assert count == 5
    assert recovering is True
    assert len(opened) == 5


def test_runner_skips_retained_terminals_without_replaying_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignments, expected, _historical, _supplement = _assignments()
    globals_ = SCRIPT["_first_pending"].__globals__

    def load(_store: object, ordinal: int, *, binding: Any) -> tuple[Any, dict]:
        return expected[(binding.private_plan_sha256, ordinal)][0], {}

    monkeypatch.setitem(globals_, "fixed_account_claim_registry_root", lambda: tmp_path)
    monkeypatch.setitem(globals_, "load_red_living_dex_development_selection", load)
    monkeypatch.setitem(
        globals_,
        "observe_claim_first_pair_availability",
        lambda *_args: True,
    )
    monkeypatch.setitem(
        globals_,
        "find_red_living_dex_development_run_terminal",
        lambda _store, assignment: object() if assignment is assignments[0] else None,
    )

    selected, count, recovering = SCRIPT["_first_pending"](object(), assignments)

    assert selected is assignments[1]
    assert count == 4
    assert recovering is False


def test_runner_root_loader_rejects_a_substituted_selection() -> None:
    assignments, _expected, _historical, _supplement = _assignments()
    selected = assignments[0]
    wrong = SimpleNamespace(
        ordinal=selected.ordinal + 1,
        private_plan_sha256=selected.binding.private_plan_sha256,
    )

    with pytest.raises(RedLivingDexDevelopmentBatchError, match="another root"):
        SCRIPT["_root_loader"](selected)(wrong)


def test_runner_source_contains_no_teacher_or_fitting_interface() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "teacher_choice" not in source
    assert "model.fit(" not in source
    assert "--case" not in source
    assert "--ordinal" not in source
    assert 'training_targets_emitted": 0' in source


def test_runner_activates_authenticated_runtime_before_controller_imports() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert source.index("activate_authenticated_runtime_stage(") < source.index(
        "from pokemon_red_completion.claim_first_admission"
    )


def test_runner_forwards_immutable_bounds_and_stops_after_one_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assignments, _expected, _historical, _supplement = _assignments()
    record = _model_record()
    calls: list[dict[str, object]] = []
    globals_ = SCRIPT["main"].__globals__

    class Server(AbstractContextManager[Any]):
        url = "http://127.0.0.1:8769/"

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> Server:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class Receipt:
        development = None

        def public_dict(self) -> dict[str, object]:
            return {"status": "typed_setup_terminal"}

    def snapshot(**_kwargs: object) -> DashboardSnapshot:
        return DashboardSnapshot(
            game="Pokémon Red",
            run_status="waiting",
            stage="Test",
            message="Test snapshot.",
            collection_target=151,
        )

    def execute(*_args: object, **kwargs: object) -> Receipt:
        calls.append(dict(kwargs))
        return Receipt()

    monkeypatch.setitem(globals_, "ProgressDashboardServer", Server)
    monkeypatch.setitem(globals_, "red_living_dex_development_dashboard_snapshot", snapshot)
    monkeypatch.setitem(globals_, "source_private_storage_is_separate", lambda *_args: True)
    monkeypatch.setitem(
        globals_,
        "detect_source_identity",
        lambda *_args: SimpleNamespace(git_commit="a" * 40),
    )
    monkeypatch.setitem(globals_, "require_clean_source", lambda *_args: None)
    monkeypatch.setitem(globals_, "require_published_source", lambda *_args: None)
    monkeypatch.setitem(globals_, "working_source_bundle_sha256", lambda *_args: "b" * 64)
    monkeypatch.setitem(
        globals_,
        "authenticate_red_living_dex_current_consumer",
        lambda *_args: object(),
    )
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: object())
    monkeypatch.setitem(
        globals_,
        "load_red_living_dex_development_batch_assignments",
        lambda *_args, **_kwargs: assignments,
    )
    monkeypatch.setitem(
        globals_,
        "_first_pending",
        lambda *_args: (assignments[0], 5, False),
    )
    monkeypatch.setitem(
        globals_,
        "load_red_living_dex_development_model",
        lambda *_args, **_kwargs: record,
    )
    monkeypatch.setitem(globals_, "execute_red_living_dex_development_assignment", execute)
    monkeypatch.setitem(
        globals_,
        "retain_red_living_dex_development_run_terminal",
        lambda *_args: object(),
    )
    monkeypatch.setitem(globals_, "_hold", lambda *_args: None)

    root_arguments = [
        value
        for label in globals_["RED_LIVING_DEX_DEVELOPMENT_INPUT_LABELS"]
        for value in ("--development-root", f"{label}={tmp_path / f'{label}.state'}")
    ]
    exit_code = SCRIPT["main"](
        [
            "--private-root",
            str(tmp_path / "private"),
            *root_arguments,
            "--rom",
            str(tmp_path / "red.gb"),
            "--exact-ci-run",
            "123",
            "--no-browser",
            "--hold-seconds",
            "0",
        ]
    )

    assert exit_code == 0
    assert len(calls) == 1
    limits = calls[0]["runtime_limits"]
    assert limits.maximum_controller_actions == 20_000  # type: ignore[attr-defined]
    assert limits.maximum_emulator_frames == 2_000_000  # type: ignore[attr-defined]
    assert calls[0]["ordinal"] == assignments[0].ordinal


def test_runner_surfaces_exact_sanitized_runtime_failure_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assignments, _expected, _historical, _supplement = _assignments()
    globals_ = SCRIPT["main"].__globals__

    class Server(AbstractContextManager[Any]):
        url = "http://127.0.0.1:8769/"

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> Server:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setitem(globals_, "ProgressDashboardServer", Server)
    monkeypatch.setitem(globals_, "source_private_storage_is_separate", lambda *_args: True)
    monkeypatch.setitem(
        globals_, "detect_source_identity", lambda *_args: SimpleNamespace(git_commit="a" * 40)
    )
    monkeypatch.setitem(globals_, "require_clean_source", lambda *_args: None)
    monkeypatch.setitem(globals_, "require_published_source", lambda *_args: None)
    monkeypatch.setitem(globals_, "working_source_bundle_sha256", lambda *_args: "b" * 64)
    monkeypatch.setitem(
        globals_, "authenticate_red_living_dex_current_consumer", lambda *_args: object()
    )
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: object())
    monkeypatch.setitem(
        globals_,
        "load_red_living_dex_development_batch_assignments",
        lambda *_args, **_kwargs: assignments,
    )
    monkeypatch.setitem(globals_, "_first_pending", lambda *_args: (assignments[0], 5, False))
    monkeypatch.setitem(
        globals_, "load_red_living_dex_development_model", lambda *_args, **_kwargs: _model_record()
    )
    monkeypatch.setitem(
        globals_,
        "execute_red_living_dex_development_assignment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RedLivingDexCausalInvocationError("runtime_identity_authentication")
        ),
    )
    monkeypatch.setitem(globals_, "_hold", lambda *_args: None)
    roots = [
        value
        for label in globals_["RED_LIVING_DEX_DEVELOPMENT_INPUT_LABELS"]
        for value in ("--development-root", f"{label}={tmp_path / f'{label}.state'}")
    ]

    exit_code = SCRIPT["main"](
        [
            "--private-root",
            str(tmp_path / "private"),
            *roots,
            "--rom",
            str(tmp_path / "red.gb"),
            "--exact-ci-run",
            "123",
            "--no-browser",
            "--hold-seconds",
            "0",
        ]
    )

    assert exit_code == 2
    assert '"stage":"runtime_identity_authentication"' in capsys.readouterr().out
