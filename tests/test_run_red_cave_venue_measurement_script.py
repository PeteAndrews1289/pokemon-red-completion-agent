from __future__ import annotations

import ast
import hashlib
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_red_cave_venue_measurement.py"
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def test_private_input_loader_requires_exact_bytes(tmp_path: Path) -> None:
    path = tmp_path / "private-input.json"
    payload = b'{"schema":"private-test-v1"}\n'
    path.write_bytes(payload)

    assert SCRIPT["_load_private_json"](
        path,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        subject="private input",
    ) == {"schema": "private-test-v1"}
    with pytest.raises(RuntimeError, match="file digest differs"):
        SCRIPT["_load_private_json"](
            path,
            expected_sha256="0" * 64,
            subject="private input",
        )


def test_cave_runner_opens_immutable_artifact_before_execution() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run"
    )
    begin_line = min(
        node.lineno
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "begin_artifact"
    )
    execute_line = min(
        node.lineno
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_execute_measurement"
    )

    assert begin_line < execute_line


def test_cave_runner_has_one_fixed_venue_and_no_answer_authority() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    execute_function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_execute_measurement"
    )
    balancing_call = next(
        node
        for node in ast.walk(execute_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_red_team_balancing"
    )
    keywords = {item.arg: item.value for item in balancing_call.keywords}
    venues = keywords["venues"]

    assert isinstance(venues, ast.Tuple)
    assert len(venues.elts) == 1
    assert isinstance(venues.elts[0], ast.Name)
    assert venues.elts[0].id == "DIGLETTS_CAVE_TRAINING_VENUE"
    assert "candidate_decision_authority" not in keywords
    assert "decision_authority" not in keywords
    assert "candidate_decision_sink" in keywords
    assert "or candidate_decisions" in source


def test_cave_runner_preflight_returns_before_private_execution() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "if not args.execute:" in source
    assert source.index("if not args.execute:") < source.index("begin_artifact")
    assert '"candidate_menus_constructed": 0' in source
    assert '"learner_outcomes_opened": 0' in source
    assert "load_committed_goal_manager_registry_at_revision" in source
    assert "support_entry.authenticated_root_lineage_id" in source
    assert '"root_lineage_id": RED_CAVE_SUPPORT_CHECKPOINT_ID' not in source
