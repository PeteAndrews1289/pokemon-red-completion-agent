# ruff: noqa: E402 -- standalone script is loaded after its source-path setup.

from __future__ import annotations

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.private_artifacts import (
    PrivateArtifactError,
    PrivateArtifactRecovery,
    PrivateArtifactSummary,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "reconcile_private_typed_artifact.py"),
    run_name="reconcile_private_typed_artifact_test",
)


def _recovery() -> PrivateArtifactRecovery:
    return PrivateArtifactRecovery(
        summary=PrivateArtifactSummary(
            artifact_id="bo-cycle-plan",
            kind="battle_outcome_cycle",
            status="failed",
            stream_records=(("claims", 1),),
            total_records=1,
            total_bytes=27,
            manifest_sha256="a" * 64,
        ),
        disposition="sealed_interrupted",
        reason_code="process_interrupted",
    )


def test_run_reports_only_reconciliation_and_zero_experiment_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str]] = []

    class Store:
        def reconcile_interrupted_artifact(
            self,
            artifact_id: str,
            *,
            expected_kind: str,
        ) -> PrivateArtifactRecovery:
            calls.append((artifact_id, expected_kind))
            return _recovery()

    monkeypatch.setitem(
        SCRIPT["_run"].__globals__,
        "open_private_root",
        lambda *args, **kwargs: Store(),
    )
    result = SCRIPT["_run"](
        SimpleNamespace(
            private_root=tmp_path / "private",
            artifact_id="bo-cycle-plan",
            expected_kind="battle_outcome_cycle",
        )
    )

    assert calls == [("bo-cycle-plan", "battle_outcome_cycle")]
    assert result["status"] == "complete"
    assert result["recovery"]["disposition"] == "sealed_interrupted"
    assert result["emulator_inputs"] == 0
    assert result["outcome_reads"] == 0
    assert result["predictions"] == 0
    assert result["model_fits"] == 0
    assert result["root_retries"] == 0
    assert "path" not in json.dumps(result, sort_keys=True).casefold()


def test_main_failure_is_sanitized_and_path_free(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    private = tmp_path / "private"

    def fail(*args, **kwargs):
        del args, kwargs
        raise PrivateArtifactError(f"failed at {private}")

    monkeypatch.setitem(SCRIPT["_run"].__globals__, "open_private_root", fail)
    result = SCRIPT["main"](
        [
            "--private-root",
            str(private),
            "--artifact-id",
            "bo-cycle-plan",
            "--expected-kind",
            "battle_outcome_cycle",
        ]
    )

    assert result == 2
    output = capsys.readouterr().out
    assert str(tmp_path) not in output
    assert json.loads(output) == {
        "reason_code": "reconciliation",
        "schema": "pokemon.private-typed-artifact-reconciliation.v1",
        "status": "failed",
    }


def test_main_rejects_missing_arguments_without_echoing_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = SCRIPT["main"](["--artifact-id", "bo-cycle-plan"])

    assert result == 2
    output = capsys.readouterr().out
    assert json.loads(output)["reason_code"] == "arguments"
