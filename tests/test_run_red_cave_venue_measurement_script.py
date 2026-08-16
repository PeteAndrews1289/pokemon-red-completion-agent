from __future__ import annotations

import argparse
import ast
import hashlib
import runpy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_red_cave_venue_measurement.py"
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def test_cave_execution_requires_a_private_root(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="requires a private root"):
        SCRIPT["_run"](
            argparse.Namespace(
                execute=True,
                private_root=None,
                exact_ci_run=1,
            )
        )


def test_cave_execution_requires_an_exact_ci_run(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="exact green CI run identity"):
        SCRIPT["_run"](
            argparse.Namespace(
                execute=True,
                private_root=tmp_path,
                exact_ci_run=None,
            )
        )


@pytest.mark.parametrize("exact_ci_run", [0, -1])
def test_cave_execution_rejects_nonpositive_ci_run(
    tmp_path: Path,
    exact_ci_run: int,
) -> None:
    with pytest.raises(RuntimeError, match="CI run identity is invalid"):
        SCRIPT["_run"](
            argparse.Namespace(
                execute=True,
                private_root=tmp_path,
                exact_ci_run=exact_ci_run,
            )
        )


@pytest.mark.parametrize(
    "exact_ci_run",
    [True, False, 1.0],
    ids=["true", "false", "float"],
)
def test_cave_execution_requires_an_exact_integer_ci_run(
    tmp_path: Path,
    exact_ci_run: object,
) -> None:
    with pytest.raises(RuntimeError, match="CI run identity is invalid"):
        SCRIPT["_run"](
            argparse.Namespace(
                execute=True,
                private_root=tmp_path,
                exact_ci_run=exact_ci_run,
            )
        )


def test_cave_protected_input_guard_detects_byte_mutation(tmp_path: Path) -> None:
    protected = tmp_path / "protected.json"
    protected.write_bytes(b'{"value":1}\n')
    expected = {protected: hashlib.sha256(protected.read_bytes()).hexdigest()}

    SCRIPT["_require_protected_files_unchanged"](expected)
    protected.write_bytes(b'{"value":2}\n')

    with pytest.raises(RuntimeError, match="changed a protected input"):
        SCRIPT["_require_protected_files_unchanged"](expected)


def test_cave_rom_adjacent_guard_detects_preflight_sidecar(tmp_path: Path) -> None:
    rom = tmp_path / "pokemon.gb"
    rom.write_bytes(b"rom")
    expected = SCRIPT["rom_adjacent_artifacts"](rom)

    Path(f"{rom}.ram").write_bytes(b"sidecar")

    with pytest.raises(RuntimeError, match="preflight created a ROM-adjacent artifact"):
        SCRIPT["_require_rom_adjacent_unchanged"](
            rom,
            expected,
            operation="preflight",
        )


def test_cave_execution_root_must_contain_all_protected_inputs(tmp_path: Path) -> None:
    private_root = tmp_path / "private"
    protected = private_root / "inputs" / "capture.state"
    protected.parent.mkdir(parents=True)
    protected.write_bytes(b"state")

    assert SCRIPT["_require_designated_private_root"](
        private_root,
        protected_inputs=(protected,),
    ) == private_root.resolve()

    sibling = tmp_path / "sibling.state"
    sibling.write_bytes(b"state")
    with pytest.raises(RuntimeError, match="does not contain every authenticated"):
        SCRIPT["_require_designated_private_root"](
            private_root,
            protected_inputs=(protected, sibling),
        )


def test_cave_run_invokes_every_isolation_guard() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run"
    )
    calls = [
        node.func.id
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]

    assert calls.count("_validate_execution_request") == 1
    assert calls.count("_require_designated_private_root") == 1
    assert calls.count("_require_protected_files_unchanged") == 1
    assert calls.count("_require_rom_adjacent_unchanged") == 2

    writer_context = next(
        node
        for node in ast.walk(run_function)
        if isinstance(node, ast.With)
        and any(
            isinstance(item.context_expr, ast.Name)
            and item.context_expr.id == "writer"
            for item in node.items
        )
    )
    guarded_calls = {
        node.func.id
        for node in ast.walk(writer_context)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_require_protected_files_unchanged" in guarded_calls
    assert "_require_rom_adjacent_unchanged" in guarded_calls


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
