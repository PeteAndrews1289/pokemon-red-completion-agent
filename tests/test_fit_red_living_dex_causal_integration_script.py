# ruff: noqa: E402 -- standalone command is loaded after script-local path pinning.

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.living_dex_causal_integration_fit import (
    LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256,
    LivingDexCausalIntegrationFitError,
    LivingDexCausalIntegrationSource,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts/fit_red_living_dex_causal_integration.py"
SCRIPT = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="fit_red_living_dex_causal_integration_test",
)


def _arguments() -> list[str]:
    return [
        "--private-root",
        "/private/store",
        "--expected-source-commit",
        "a" * 40,
        "--expected-source-bundle-sha256",
        "b" * 64,
        "--exact-ci-run",
        "123",
        "--exact-ci-attempt",
        "1",
    ]


def _source() -> LivingDexCausalIntegrationSource:
    return LivingDexCausalIntegrationSource(
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        exact_ci_run=123,
        exact_ci_attempt=1,
    )


def test_parser_has_no_gameplay_development_selection_retry_or_output_surface() -> None:
    parsed = SCRIPT["_parser"]().parse_args(_arguments())

    assert parsed.private_root == Path("/private/store")
    assert parsed.expected_source_commit == "a" * 40
    for forbidden in (
        "rom",
        "state",
        "development",
        "candidate",
        "partition",
        "retry",
        "output",
        "teacher",
        "authority",
    ):
        assert not hasattr(parsed, forbidden)


def test_command_imports_no_emulator_teacher_controller_or_development_consumer() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    for forbidden in (
        "materialize_living_dex_causal_example",
        "run_red_living_dex_option_development",
        "CompletionFirstGoalTeacher",
        "build_red_living_dex_causal_scenario",
        "PokemonRedPyBoyEnv",
        ".press(",
        ".tick(",
        ".execute(",
    ):
        assert forbidden not in source


def test_published_readiness_proof_authenticates_exact_bytes() -> None:
    assert (
        SCRIPT["_authenticate_readiness_proof"]()
        == LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256
    )


def test_readiness_proof_rejects_a_changed_gate_implementation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_authenticate_readiness_proof"].__globals__
    changed = tmp_path / "changed-readiness.py"
    changed.write_text("def ready(): return True\n", encoding="ascii")
    monkeypatch.setitem(globals_, "READINESS_IMPLEMENTATION_PATH", changed)

    with pytest.raises(SCRIPT["IntegrationFitCommandError"], match="readiness_proof"):
        SCRIPT["_authenticate_readiness_proof"]()


def test_source_authentication_requires_clean_exact_main_and_green_push_ci(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    globals_ = SCRIPT["_authenticate_source"].__globals__
    commit = "a" * 40
    bundle = "b" * 64
    calls: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...]) -> bytes:
        calls.append(command)
        if command[:2] == ("git", "status"):
            return b""
        if command[0] == "git":
            return (commit + "\n").encode("ascii")
        assert command[:2] == ("gh", "api")
        return json.dumps(
            {
                "conclusion": "success",
                "event": "push",
                "head_branch": "main",
                "head_sha": commit,
                "html_url": (
                    "https://github.com/PeteAndrews1289/"
                    "pokemon-red-completion-agent/actions/runs/123"
                ),
                "id": 123,
                "name": "CI",
                "path": ".github/workflows/ci.yml",
                "repository": {
                    "full_name": "PeteAndrews1289/pokemon-red-completion-agent"
                },
                "run_attempt": 1,
                "status": "completed",
            }
        ).encode("utf-8")

    monkeypatch.setitem(globals_, "_run", run)
    monkeypatch.setitem(
        globals_,
        "committed_source_bundle_sha256",
        lambda *_args, **_kwargs: bundle,
    )
    args = SCRIPT["_parser"]().parse_args(_arguments())

    authenticated = SCRIPT["_authenticate_source"](args)

    assert authenticated == _source()
    assert any(command[:2] == ("gh", "api") for command in calls)
    assert ("git", "status", "--porcelain=v1", "--untracked-files=all") in calls


def test_main_emits_only_path_free_aggregate_fit_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    store = object()
    expected = {
        "artifact": {
            "model_sha256": "c" * 64,
            "record_sha256": "d" * 64,
            "reload_bytes_equal": True,
        },
        "complete_denominator_included": True,
        "controller_actions": 0,
        "development_examples_read": 0,
        "fit_executions": 1,
        "status": "non_authoritative_integration_fit_complete",
        "total_examples": 8,
    }
    monkeypatch.setitem(globals_, "_authenticate_source", lambda _args: _source())
    monkeypatch.setitem(
        globals_,
        "_authenticate_readiness_proof",
        lambda: LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256,
    )
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: store)

    def fit(opened: object, **kwargs: object) -> SimpleNamespace:
        assert opened is store
        assert kwargs == {
            "source": _source(),
            "readiness_result_sha256": (
                LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256
            ),
        }
        return SimpleNamespace(public_dict=lambda: expected)

    monkeypatch.setitem(
        globals_,
        "fit_living_dex_causal_integration_from_store",
        fit,
    )

    assert SCRIPT["main"](_arguments()) == 0
    result = json.loads(capsys.readouterr().out)

    assert result == expected
    assert "/private" not in json.dumps(result)


def test_failure_after_fit_preserves_effect_count_and_sanitizes_exception(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    globals_ = SCRIPT["main"].__globals__
    monkeypatch.setitem(globals_, "_authenticate_source", lambda _args: _source())
    monkeypatch.setitem(
        globals_,
        "_authenticate_readiness_proof",
        lambda: LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256,
    )
    monkeypatch.setitem(globals_, "open_private_root", lambda *_args, **_kwargs: object())

    def fail(*_args: object, **_kwargs: object) -> object:
        raise LivingDexCausalIntegrationFitError(
            "model_publication_or_reload",
            fit_executions=1,
            private_fit_claims=1,
        )

    monkeypatch.setitem(
        globals_,
        "fit_living_dex_causal_integration_from_store",
        fail,
    )

    assert SCRIPT["main"](_arguments()) == 1
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "failed_closed"
    assert result["stage"] == "model_publication_or_reload"
    assert result["fit_executions"] == 1
    assert result["private_fit_claims"] == 1
    assert result["controller_actions"] == 0
    assert result["development_examples_read"] == 0
    assert "/private" not in json.dumps(result)
