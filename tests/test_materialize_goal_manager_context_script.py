from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "materialize_goal_manager_context.py"


def test_materializer_uses_real_actions_and_never_edits_emulator_memory() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert "save_state" in attributes
    assert "write_u8" not in attributes
    assert "write_memory" not in attributes
    assert "record_goal_manager_context" not in source
    assert "begin_episode" not in source
    assert "load_state_bytes" in source


def test_materializer_help_declares_only_finite_uncounted_boundaries() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "blocked-dialogue" in result.stdout
    assert "damaged-center" in result.stdout
    assert "mansion" in result.stdout
    assert "--slot-id" not in result.stdout
    assert "--profile" not in result.stdout
