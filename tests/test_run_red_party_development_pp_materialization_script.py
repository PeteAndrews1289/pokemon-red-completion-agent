from __future__ import annotations

import ast
import hashlib
import runpy
from collections.abc import Mapping
from pathlib import Path

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.executor import ControllerTiming

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "run_red_party_development_pp_materialization.py"
)
SCRIPT = runpy.run_path(str(SCRIPT_PATH))


def test_pp_runner_execution_request_is_explicit_and_exact(
    tmp_path: Path,
) -> None:
    assert (
        SCRIPT["_validate_execution_request"](
            execute=False,
            private_root=None,
            out_state=None,
            exact_ci_run=None,
        )
        is None
    )
    with pytest.raises(RuntimeError, match="read-only PP preflight"):
        SCRIPT["_validate_execution_request"](
            execute=False,
            private_root=tmp_path,
            out_state=None,
            exact_ci_run=None,
        )
    with pytest.raises(RuntimeError, match="requires private root"):
        SCRIPT["_validate_execution_request"](
            execute=True,
            private_root=None,
            out_state=tmp_path / "out.state",
            exact_ci_run=1,
        )
    with pytest.raises(RuntimeError, match="CI run identity is invalid"):
        SCRIPT["_validate_execution_request"](
            execute=True,
            private_root=tmp_path,
            out_state=tmp_path / "out.state",
            exact_ci_run=True,
        )
    assert SCRIPT["_validate_execution_request"](
        execute=True,
        private_root=tmp_path,
        out_state=tmp_path / "out.state",
        exact_ci_run=123,
    ) == (tmp_path, tmp_path / "out.state", 123)


def test_pp_runner_requires_an_existing_private_output_directory(
    tmp_path: Path,
) -> None:
    output = tmp_path / "captures" / "out.state"
    with pytest.raises(RuntimeError, match="must already be a writable"):
        SCRIPT["_require_output_boundary"](output)

    output.parent.mkdir()
    SCRIPT["_require_output_boundary"](output)


def test_pp_runner_output_claim_is_exclusive_owner_only_and_durable(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out.state"
    payload = SCRIPT["_OUTPUT_STATE_CLAIM"]

    digest = SCRIPT["_write_exclusive"](output, payload)

    assert digest == hashlib.sha256(payload).hexdigest()
    assert output.read_bytes() == payload
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        SCRIPT["_write_exclusive"](output, payload)


class _FrameCounter:
    frame_count = 100


class _Executor:
    def __init__(self, frames: _FrameCounter, timing: ControllerTiming) -> None:
        self.frames = frames
        self.timing = timing
        self.calls = 0

    def execute(self, action: MacroAction) -> object:
        self.calls += 1
        self.frames.frame_count += action.repeat * (
            self.timing.wait_frames
            if action.kind is MacroActionKind.WAIT
            else self.timing.press_frames + self.timing.release_frames
        )
        return action


def test_pp_runner_refuses_the_action_that_would_cross_a_hard_bound() -> None:
    timing = ControllerTiming(press_frames=2, release_frames=3, wait_frames=4)
    frames = _FrameCounter()
    delegate = _Executor(frames, timing)
    executor = SCRIPT["_HardBoundedCountingExecutor"](
        delegate,
        emulator=frames,
        timing=timing,
        start_frame=100,
        maximum_actions=2,
        maximum_frames=9,
    )

    executor.execute(MacroAction(MacroActionKind.WAIT, repeat=2))
    assert frames.frame_count == 108
    assert delegate.calls == 1
    with pytest.raises(RuntimeError, match="beyond its frozen bound"):
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
    assert frames.frame_count == 108
    assert delegate.calls == 1


def test_pp_runner_refuses_the_action_after_the_exact_action_cap() -> None:
    timing = ControllerTiming(press_frames=2, release_frames=3, wait_frames=4)
    frames = _FrameCounter()
    delegate = _Executor(frames, timing)
    executor = SCRIPT["_HardBoundedCountingExecutor"](
        delegate,
        emulator=frames,
        timing=timing,
        start_frame=100,
        maximum_actions=1,
        maximum_frames=1_000,
    )

    executor.execute(MacroAction(MacroActionKind.CONFIRM))
    assert executor.actions_executed == 1
    assert delegate.calls == 1
    with pytest.raises(RuntimeError, match="beyond its frozen bound"):
        executor.execute(MacroAction(MacroActionKind.CONFIRM))
    assert executor.actions_executed == 1
    assert delegate.calls == 1


def test_pp_runner_protected_input_and_rom_guards_detect_changes(
    tmp_path: Path,
) -> None:
    protected = tmp_path / "protected.json"
    protected.write_bytes(b'{"value":1}\n')
    expected = {protected: hashlib.sha256(protected.read_bytes()).hexdigest()}
    SCRIPT["_require_protected_files_unchanged"](expected)
    protected.write_bytes(b'{"value":2}\n')
    with pytest.raises(RuntimeError, match="changed an authenticated"):
        SCRIPT["_require_protected_files_unchanged"](expected)

    rom = tmp_path / "red.gb"
    rom.write_bytes(b"rom")
    adjacent = SCRIPT["rom_adjacent_artifacts"](rom)
    Path(f"{rom}.ram").write_bytes(b"sidecar")
    with pytest.raises(RuntimeError, match="created a ROM-adjacent artifact"):
        SCRIPT["_require_rom_adjacent_unchanged"](
            rom,
            adjacent,
            operation="test",
        )


class _RecordingWriter:
    def __init__(self) -> None:
        self.records: list[tuple[str, Mapping[str, object]]] = []

    def append(
        self,
        stream: str,
        record: Mapping[str, object],
        *,
        durable: bool = False,
    ) -> None:
        assert durable is True
        self.records.append((stream, record))


def test_pp_runner_retains_path_free_failure_after_progress() -> None:
    writer = _RecordingWriter()

    def fail(progress_sink: object) -> dict[str, object]:
        assert callable(progress_sink)
        progress_sink({"battles_completed": 1})
        raise RuntimeError("failed beside /private/root/source.state")

    with pytest.raises(RuntimeError, match="failed beside"):
        SCRIPT["_execute_with_retention"](writer, fail)

    assert [stream for stream, _record in writer.records] == [
        "progress",
        "failure",
    ]
    failure = writer.records[-1][1]
    assert failure["exception_message"] == "failed beside [private-path]"
    assert failure["exception_message_redacted"] is True
    assert failure["private_path_fields"] == 0


def test_pp_runner_commits_the_capture_only_after_all_postconditions() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    run_function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run"
    )
    closure = next(
        node
        for node in ast.walk(run_function)
        if isinstance(node, ast.FunctionDef)
        and node.name == "execute_and_validate"
    )
    call_lines: dict[str, list[int]] = {}
    for node in ast.walk(closure):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            call_lines.setdefault(node.func.id, []).append(node.lineno)
    protected_lines = sorted(call_lines["_require_protected_files_unchanged"])
    execute_line = min(call_lines["_execute_preparation"])
    authenticate_line = min(call_lines["_authenticate_materialized_output"])
    publish_line = min(call_lines["_publish_output_envelope"])

    assert len(protected_lines) == 2
    assert execute_line < protected_lines[0] < authenticate_line
    assert authenticate_line < protected_lines[1] < publish_line


def test_pp_runner_claims_once_before_controller_and_has_no_learning_actor() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    run_function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_run"
    )
    calls = [
        (node.func.id, node.lineno)
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    lines_by_name: dict[str, list[int]] = {}
    for name, line in calls:
        lines_by_name.setdefault(name, []).append(line)

    plan_append = next(
        node
        for node in ast.walk(run_function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "plan"
    )
    claim_line = next(
        line
        for line in lines_by_name["_write_exclusive"]
        if line > plan_append.lineno
    )
    execute_line = min(lines_by_name["_execute_preparation"])

    assert plan_append.lineno < claim_line < execute_line
    assert source.count("_execute_preparation(") == 2
    assert "transient_zero_pp_main_is_dialogue=False" in source
    assert "active_party_index != 0" in source
    assert "active_party_species_id\n                        != entry.target_species_id" in source
    assert "teacher" not in {
        (node.module or "").split(".")[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "candidate_menu" not in {
        (node.module or "").split(".")[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }


def test_pp_runner_read_only_preflight_returns_before_attempt_claim() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert source.index("if execution_request is None:") < source.index(
        "begin_artifact"
    )
    assert '"controller_actions": 0' in source
    assert '"learner_outcomes_opened": 0' in source
    assert '"model_predictions": 0' in source
    assert '"teacher_queries": 0' in source
