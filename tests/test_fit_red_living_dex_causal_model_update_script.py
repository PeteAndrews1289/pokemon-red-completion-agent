from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from pokemon_red_completion.living_dex_causal_integration_fit import (
    LivingDexCausalIntegrationSource,
)

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts/fit_red_living_dex_causal_model_update.py"
)


def _module() -> dict[str, object]:
    return runpy.run_path(str(SCRIPT_PATH), run_name="causal_model_update_script_test")


def test_parser_exposes_only_source_and_private_store_inputs() -> None:
    parser = _module()["_parser"]()
    destinations = {action.dest for action in parser._actions}

    assert destinations == {
        "help",
        "private_root",
        "expected_source_commit",
        "expected_source_bundle_sha256",
        "exact_ci_run",
        "exact_ci_attempt",
    }
    assert not destinations.intersection(
        {
            "rom",
            "state",
            "development",
            "candidate",
            "teacher",
            "authority",
            "retry",
        }
    )


def test_main_emits_sanitized_failure_without_private_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main = _module()["main"]
    private = tmp_path / "secret-private-corpus"

    status = main(
        [
            "--private-root",
            str(private),
            "--expected-source-commit",
            "not-a-commit",
            "--expected-source-bundle-sha256",
            "b" * 64,
            "--exact-ci-run",
            "123",
            "--exact-ci-attempt",
            "1",
        ]
    )

    output = capsys.readouterr().out
    document = json.loads(output)
    assert status == 1
    assert document["status"] == "failed_closed"
    assert document["stage"] == "source_authentication"
    assert document["controller_actions"] == 0
    assert document["development_examples_read"] == 0
    assert document["fit_executions"] == 0
    assert str(private) not in output


def test_main_does_not_open_store_before_source_authentication(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()
    main = module["main"]
    opened = False

    def forbidden_open(*_args: object, **_kwargs: object) -> object:
        nonlocal opened
        opened = True
        raise AssertionError

    monkeypatch.setitem(main.__globals__, "open_private_root", forbidden_open)
    status = main(
        [
            "--private-root",
            "/private/corpus",
            "--expected-source-commit",
            "a" * 40,
            "--expected-source-bundle-sha256",
            "b" * 64,
            "--exact-ci-run",
            "123",
            "--exact-ci-attempt",
            "1",
        ]
    )

    document = json.loads(capsys.readouterr().out)
    assert status == 1
    assert not opened
    assert document["stage"] == "source_authentication"


def test_main_emits_only_the_public_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()
    main = module["main"]
    source = LivingDexCausalIntegrationSource(
        source_commit="a" * 40,
        source_bundle_sha256="b" * 64,
        exact_ci_run=123,
        exact_ci_attempt=1,
    )
    expected = {
        "schema": "pokemon.red.living-dex-causal-model-update-result.v1",
        "status": "train_only_causal_model_update_complete",
        "private_path_fields": 0,
    }
    monkeypatch.setitem(main.__globals__, "_authenticate_source", lambda _args: source)
    monkeypatch.setitem(main.__globals__, "open_private_root", lambda *_args, **_kwargs: object())
    monkeypatch.setitem(
        main.__globals__,
        "fit_living_dex_causal_model_update_from_store",
        lambda _store, *, source: SimpleResult(expected),
    )

    status = main(
        [
            "--private-root",
            "/private/corpus",
            "--expected-source-commit",
            "a" * 40,
            "--expected-source-bundle-sha256",
            "b" * 64,
            "--exact-ci-run",
            "123",
            "--exact-ci-attempt",
            "1",
        ]
    )

    assert status == 0
    assert json.loads(capsys.readouterr().out) == expected


class SimpleResult:
    def __init__(self, public: dict[str, object]) -> None:
        self._public = public

    def public_dict(self) -> dict[str, object]:
        return self._public
