from __future__ import annotations

import ast
import hashlib
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "audit_party_development_exclusions.py"
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def test_private_loader_requires_external_exact_file(tmp_path: Path) -> None:
    path = tmp_path / "private.json"
    payload = b'{"schema":"private-test-v1"}\n'
    path.write_bytes(payload)

    assert SCRIPT["_load_private_json"](
        path,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        subject="test input",
    ) == {"schema": "private-test-v1"}
    with pytest.raises(RuntimeError, match="file digest differs"):
        SCRIPT["_load_private_json"](
            path,
            expected_sha256="0" * 64,
            subject="test input",
        )
    with pytest.raises(RuntimeError, match="outside the repository"):
        SCRIPT["_load_private_json"](
            PROJECT_ROOT / "private.json",
            expected_sha256="0" * 64,
            subject="test input",
        )


def test_audit_script_has_no_execution_answer_or_write_surface() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert not any(
        token in module
        for module in imported_modules
        for token in ("emulator", "executor", "teacher", "outcome")
    )
    assert called_names.isdisjoint(
        {
            "CountingExecutor",
            "FrameSafeExecutor",
            "run_red_team_balancing",
        }
    )
    assert called_attributes.isdisjoint(
        {
            "execute",
            "hold",
            "press",
            "release",
            "send_input",
            "tick",
            "write_bytes",
            "write_text",
        }
    )
    for closed_counter in (
        '"controller_actions": 0',
        '"teacher_queries": 0',
        '"model_predictions": 0',
        '"outcomes_opened": 0',
    ):
        assert closed_counter in (
            PROJECT_ROOT
            / "src"
            / "pokemon_red_completion"
            / "party_development_exclusion_audit.py"
        ).read_text(encoding="utf-8")
    assert "load_committed_goal_manager_registry_at_revision" in source
    assert "parse_goal_manager_context_catalog" in source
    assert "catalog_entry.authenticated_root_lineage_id" in source
    assert "registry.assignment(entry.checkpoint_id)" not in source
