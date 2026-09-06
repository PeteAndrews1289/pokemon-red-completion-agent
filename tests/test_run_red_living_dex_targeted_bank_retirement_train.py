from __future__ import annotations

import ast
import json
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_ROOT
    / "scripts"
    / "run_red_living_dex_targeted_bank_retirement_train.py"
)
RUNNER = runpy.run_path(
    str(SCRIPT),
    run_name="run_red_living_dex_targeted_bank_retirement_train_test",
)


def test_retired_bank_train_command_exposes_no_manual_slot_or_retry() -> None:
    source = SCRIPT.read_text()
    tree = ast.parse(source)

    assert tree is not None
    assert 'add_argument("--ordinal"' not in source
    assert 'add_argument("--retry"' not in source
    assert 'add_argument("--development' not in source
    assert 'add_argument("--reserve' not in source
    assert 'add_argument("--candidate' not in source
    assert "run_red_living_dex_targeted_train_campaign" in source
    assert "authenticate_red_living_dex_targeted_bank_retirement_plan" in source


def test_retired_bank_train_command_has_no_fit_teacher_or_crystal_entrypoint() -> None:
    source = SCRIPT.read_text().lower()

    for forbidden in (
        "fit_model",
        "model.fit",
        "run_teacher",
        "teacher_policy",
        "run_crystal",
        "pokemon_crystal",
    ):
        assert forbidden not in source
    assert '"development_slots_opened": 0' in source
    assert '"model_fits": 0' in source
    assert '"teacher_queries": 0' in source


def test_retired_bank_train_command_has_an_action_free_preflight() -> None:
    source = SCRIPT.read_text()

    assert 'add_argument("--preflight-only"' in source
    assert '"retired_bank_train_preflight_passed"' in source


def test_retired_bank_train_command_missing_arguments_fail_closed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert RUNNER["main"]([]) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed_closed"
    assert result["stage"] == "arguments"
    assert result["development_slots_opened"] == 0
    assert result["model_fits"] == 0
    assert result["model_predictions"] == 0
    assert result["teacher_queries"] == 0
