from __future__ import annotations

import ast
import hashlib
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = (
    PROJECT_ROOT / "scripts" / "preflight_red_party_development_questions.py"
)
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def test_private_json_loader_requires_the_exact_file_digest(tmp_path: Path) -> None:
    path = tmp_path / "private.json"
    payload = b'{"schema":"private-test-v1"}\n'
    path.write_bytes(payload)

    loaded = SCRIPT["_load_json"](
        path,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        subject="private test",
    )

    assert loaded == {"schema": "private-test-v1"}
    with pytest.raises(RuntimeError, match="file digest differs"):
        SCRIPT["_load_json"](
            path,
            expected_sha256="0" * 64,
            subject="private test",
        )


def test_question_paths_require_one_complete_external_capture_triplet(
    tmp_path: Path,
) -> None:
    root = tmp_path / "catalog"
    (root / "captures").mkdir(parents=True)
    (root / "profiles").mkdir()
    checkpoint = "red-goal-v1-001-example-train-01"
    state = root / "captures" / f"{checkpoint}.state"
    envelope = state.with_suffix(".state.json")
    profile = root / "profiles" / f"{checkpoint}.json"
    for path in (state, envelope, profile):
        path.write_text("{}\n", encoding="ascii")

    assert SCRIPT["_question_paths"](root, checkpoint) == (
        state,
        envelope,
        profile,
    )
    profile.unlink()
    with pytest.raises(RuntimeError, match="missing its capture"):
        SCRIPT["_question_paths"](root, checkpoint)


def test_preflight_refuses_private_inputs_inside_the_repository() -> None:
    with pytest.raises(RuntimeError, match="outside the repository"):
        SCRIPT["_require_external"](
            PROJECT_ROOT / "must-not-be-private.json",
            subject="test input",
        )


def test_preflight_script_has_read_only_emulator_surface_and_no_answer_actor() -> None:
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
        for token in ("executor", "teacher", "outcome_learning")
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
    assert "load_committed_goal_manager_registry_at_revision" in source
    assert "parse_goal_manager_context_catalog" in source
    assert "catalog_entry.authenticated_root_lineage_id" in source
    assert "canonical_root_bindings_resolved" in source
    assert "candidate_menus_durably_frozen" in source
