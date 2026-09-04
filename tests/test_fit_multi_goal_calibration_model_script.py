from __future__ import annotations

import json
import runpy
import stat
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/fit_multi_goal_calibration_model.py"),
    run_name="fit_multi_goal_calibration_model_script_test",
)
SCRIPT_GLOBALS = SCRIPT["_run"].__globals__


def _argv(root: Path) -> list[str]:
    digest = "1" * 64
    return [
        "--context-plan",
        str(root / "context-plan.json"),
        "--context-catalog",
        str(root / "catalog.json"),
        "--model",
        str(root / "base-model.json"),
        "--fit-summary",
        str(root / "base-summary.json"),
        "--expected-source-commit",
        "2" * 40,
        "--expected-source-bundle-sha256",
        digest,
        "--expected-fit-runner-sha256",
        digest,
        "--expected-trial-runner-sha256",
        digest,
        "--expected-freezer-sha256",
        digest,
        "--expected-development-runner-sha256",
        digest,
        "--expected-runtime-sha256",
        digest,
        "--expected-numpy-runtime-sha256",
        digest,
        "--expected-skill-manifest-sha256",
        digest,
        "--expected-context-plan-sha256",
        digest,
        "--expected-inventory-result-sha256",
        digest,
        "--expected-campaign-sha256",
        digest,
        "--private-root",
        str(root),
        "--campaign-plan",
        str(root / "campaign.json"),
        "--out-model",
        str(root / "candidate.json"),
        "--out-summary",
        str(root / "summary.json"),
    ]


def test_cli_exposes_one_fit_without_gameplay_or_partition_selection() -> None:
    destinations = {action.dest for action in SCRIPT["_parser"]()._actions}

    assert "out_model" in destinations
    assert "out_summary" in destinations
    assert "trial_ordinal" not in destinations
    assert "mode" not in destinations
    assert "watch" not in destinations
    assert "seed" not in destinations
    assert "controller" not in destinations


def test_private_outputs_must_be_new_direct_children(tmp_path: Path) -> None:
    destination = tmp_path / "candidate.json"
    assert SCRIPT["_new_private_output"](destination, tmp_path) == destination

    destination.write_text("occupied", encoding="ascii")
    with pytest.raises(SCRIPT["MultiGoalCalibrationFitRunError"], match="private_output"):
        SCRIPT["_new_private_output"](destination, tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    with pytest.raises(SCRIPT["MultiGoalCalibrationFitRunError"], match="private_output"):
        SCRIPT["_new_private_output"](nested / "candidate.json", tmp_path)


def test_private_publication_is_exclusive_and_mode_0600(tmp_path: Path) -> None:
    destination = tmp_path / "candidate.json"

    SCRIPT["_publish_private"](destination, b"candidate\n")

    assert destination.read_bytes() == b"candidate\n"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with pytest.raises(SCRIPT["MultiGoalCalibrationFitRunError"], match="private_output"):
        SCRIPT["_publish_private"](destination, b"replacement\n")
    assert destination.read_bytes() == b"candidate\n"


def test_failure_receipt_is_path_free_and_claims_no_fit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = str(tmp_path / "private-secret")
    monkeypatch.setitem(
        SCRIPT_GLOBALS,
        "_run",
        lambda _args: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert SCRIPT["main"](_argv(tmp_path)) == 1

    output = capsys.readouterr().out
    result = json.loads(output)
    assert result == {
        "schema": "pokemon.red.multi-goal-calibration-fit-failure.v1",
        "status": "failed_closed",
        "failure_stage": "unexpected_failure",
        "model_fits": 0,
        "authority_delta": 0,
        "private_path_fields": 0,
    }
    assert secret not in output
