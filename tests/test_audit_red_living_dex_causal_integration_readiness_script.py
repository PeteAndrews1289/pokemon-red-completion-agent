# ruff: noqa: E402 -- standalone command is loaded after script-local path pinning.

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts/audit_red_living_dex_causal_integration_readiness.py"
)
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="audit_red_living_dex_causal_integration_readiness_test",
)


def test_parser_exposes_only_the_private_read_root() -> None:
    parsed = SCRIPT["_parser"]().parse_args(["--private-root", "/private/store"])

    assert parsed.private_root == Path("/private/store")
    for forbidden in (
        "rom",
        "state",
        "development",
        "fit",
        "predict",
        "retry",
        "output",
        "teacher",
    ):
        assert not hasattr(parsed, forbidden)


def test_command_has_no_gameplay_claim_teacher_prediction_fit_or_publication_surface() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "materialize_living_dex_causal_example",
        "fit_living_dex_option_value",
        "publish_sealed_record",
        "claim_first_pair_registry",
        "CompletionFirstGoalTeacher",
        "build_red_living_dex_causal_scenario",
        ".press(",
        ".tick(",
        ".execute(",
    ):
        assert forbidden not in source


def test_main_emits_only_the_path_free_aggregate_audit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    store = object()
    rows = (object(),) * 8
    audit = SimpleNamespace(
        ready=True,
        public_dict=lambda: {
            "authentic_examples": 8,
            "distinct_lineages": 8,
            "integration_fit_allowed": True,
            "fit_executions": 0,
            "controller_actions": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
        },
    )
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: store)
    monkeypatch.setitem(
        globals_,
        "load_living_dex_authenticated_causal_examples",
        lambda opened: rows if opened is store else (),
    )
    monkeypatch.setitem(
        globals_,
        "audit_living_dex_causal_integration_readiness",
        lambda examples: audit if examples is rows else None,
    )

    assert SCRIPT["main"](["--private-root", "/private/store"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "authenticated_train_only_integration_ready"
    assert result["authentic_examples"] == 8
    assert result["integration_fit_allowed"] is True
    assert result["fit_executions"] == 0
    assert result["controller_actions"] == 0
    assert result["private_identity_fields"] == 0
    assert "/private" not in json.dumps(result)


def test_failure_receipt_sanitizes_private_exception_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__

    def fail(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("/private/store/secret-record")

    monkeypatch.setitem(globals_, "open_private_root", fail)

    assert SCRIPT["main"](["--private-root", "/private/store"]) == 1
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "failed_closed"
    assert result["stage"] == "private_root_authentication"
    assert result["fit_executions"] == 0
    assert result["model_predictions"] == 0
    assert result["controller_actions"] == 0
    assert result["teacher_queries"] == 0
    assert "/private" not in json.dumps(result)
