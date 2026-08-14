from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = PROJECT_ROOT / "scripts" / "preflight_goal_manager_context.py"
COLLECT = PROJECT_ROOT / "scripts" / "collect_goal_manager_context.py"


def _call_names(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.append(node.func.attr)
    return tuple(names)


def test_read_only_preflight_cannot_execute_or_save_a_context() -> None:
    calls = _call_names(PREFLIGHT)

    assert "load_state_bytes" in calls
    assert "preflight_goal_manager_context" in calls
    assert "build_goal_manager_preflight_payload" in calls
    assert "record_goal_manager_context" not in calls
    assert "save_state" not in calls
    assert "save_state_bytes" not in calls


def test_counted_collector_uses_frozen_runtime_and_never_saves_over_inputs() -> None:
    calls = _call_names(COLLECT)

    assert "load_committed_goal_manager_registry" in calls
    assert "parse_goal_manager_context_catalog" in calls
    assert "load_red_goal_context_profile" in calls
    assert "load_state_bytes" in calls
    assert "record_goal_manager_context" in calls
    assert "save_state" not in calls
    assert "save_state_bytes" not in calls


def test_goal_manager_context_commands_import_without_private_inputs() -> None:
    for script in (PREFLIGHT, COLLECT):
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "--slot-id" in result.stdout
        assert "--profile" in result.stdout
