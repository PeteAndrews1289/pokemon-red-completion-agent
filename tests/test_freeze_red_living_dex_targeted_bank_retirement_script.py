# ruff: noqa: E402 -- standalone script is loaded after its local path setup.

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts/freeze_red_living_dex_targeted_bank_retirement.py"
)
FREEZER = runpy.run_path(
    str(SCRIPT_PATH),
    run_name="freeze_red_living_dex_targeted_bank_retirement_test",
)


def _args(tmp_path: Path) -> list[str]:
    return [
        "--expected-source-commit",
        "a" * 40,
        "--expected-source-bundle-sha256",
        "b" * 64,
        "--registry-source-commit",
        "c" * 40,
        "--expected-registry-sha256",
        "d" * 64,
        "--context-catalog",
        str(tmp_path / "catalog.json"),
        "--expected-context-catalog-sha256",
        "e" * 64,
        "--context-plan",
        str(tmp_path / "plan.json"),
        "--expected-context-plan-sha256",
        "f" * 64,
        "--private-root",
        str(tmp_path / "private"),
        "--rom",
        str(tmp_path / "red.gb"),
        "--expected-model-sha256",
        "1" * 64,
        "--expected-model-record-sha256",
        "2" * 64,
        "--plan-out",
        str(tmp_path / "retirement.json"),
    ]


def test_parser_exposes_only_action_free_authentication_and_plan_inputs(
    tmp_path: Path,
) -> None:
    parsed = FREEZER["_parser"]().parse_args(_args(tmp_path))

    assert parsed.plan_out == tmp_path / "retirement.json"
    for field in (
        "action",
        "candidate_index",
        "execute",
        "fit",
        "retry",
        "speed",
        "teacher",
        "watch",
    ):
        assert not hasattr(parsed, field)


def test_missing_arguments_fail_closed_with_zero_effects(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert FREEZER["main"]([]) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed_closed"
    assert result["stage"] == "arguments"
    for field in (
        "controller_actions",
        "emulator_frames",
        "model_fits",
        "model_predictions",
        "outcomes_opened",
        "root_claims",
        "teacher_queries",
    ):
        assert result[field] == 0


def test_script_has_no_gameplay_teacher_model_fit_or_outcome_interface() -> None:
    source = SCRIPT_PATH.read_text()

    for forbidden in (
        "controller_executor",
        "emulator.tick",
        "model.fit",
        "run_teacher",
        "teacher_policy",
        "materialize_living_dex_causal_example",
    ):
        assert forbidden not in source
