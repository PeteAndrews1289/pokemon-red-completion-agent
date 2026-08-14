from __future__ import annotations

import ast
import json
import runpy
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "run_goal_manager_promotion.py"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _registry() -> SimpleNamespace:
    return SimpleNamespace(
        registry_sha256="a" * 64,
        execution=SimpleNamespace(source_commit="b" * 40),
        slots=(SimpleNamespace(slot_id="red-goal-v1-001-advance_story-train-01"),),
    )


def _plan(tmp_path: Path) -> dict[str, object]:
    return {
        "schema": "pokemon-red-private-goal-manager-context-plan-v1",
        "registry_sha256": "a" * 64,
        "source_commit": "b" * 40,
        "entries": [
            {
                "slot_id": "red-goal-v1-001-advance_story-train-01",
                "state": str(tmp_path / "one.state"),
                "envelope": str(tmp_path / "one.state.json"),
                "profile": str(tmp_path / "one.profile.json"),
            }
        ],
    }


def test_help_exposes_shadow_then_causal_without_collection_output() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "shadow" in result.stdout
    assert "causal" in result.stdout
    assert "--shadow-receipt-sha256" in result.stdout
    assert "--private-root" not in result.stdout


def test_script_has_no_teacher_or_episode_collection_authority() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "CompletionFirstGoalTeacher" not in imported
    assert "record_goal_manager_context" not in called
    assert "rehearse_goal_manager_context" not in called
    assert "evaluate_goal_manager_promotion_context" in called


def test_private_plan_stays_historical_canonical_and_external(tmp_path: Path) -> None:
    module = runpy.run_path(str(SCRIPT))
    destination = tmp_path / "plan.json"
    destination.write_bytes(_canonical(_plan(tmp_path)))

    entries = module["_load_private_plan"](destination, _registry())

    assert len(entries) == 1
    assert entries[0].slot_id == "red-goal-v1-001-advance_story-train-01"

    weakened = _plan(tmp_path)
    weakened["entries"][0]["state"] = "relative.state"
    destination.write_bytes(_canonical(weakened))
    with pytest.raises(
        module["GoalManagerPromotionRunError"],
        match="absolute and unique",
    ):
        module["_load_private_plan"](destination, _registry())


def test_receipt_writer_is_exclusive_private_and_canonical(tmp_path: Path) -> None:
    module = runpy.run_path(str(SCRIPT))
    destination = tmp_path / "receipt.json"
    payload = _canonical({"private_path_fields": 0, "schema": "test"})

    module["_write_exclusive"](destination, payload)

    assert destination.read_bytes() == payload
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        module["_write_exclusive"](destination, payload)
