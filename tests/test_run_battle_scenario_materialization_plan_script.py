from __future__ import annotations

import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_scenario_materialization_run import (
    FAILED,
    STARTED,
    SUCCEEDED,
    initialize_battle_scenario_materialization_run,
    parse_battle_scenario_materialization_run,
    start_battle_scenario_materialization_assignment,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts" / "run_battle_scenario_materialization_plan.py")
)
HELPERS = runpy.run_path(
    str(PROJECT_ROOT / "tests" / "test_battle_scenario_materialization_run.py")
)
V2_HELPERS = runpy.run_path(
    str(PROJECT_ROOT / "tests" / "test_battle_scenario_materialization_plan_v2.py")
)


def _journal():  # type: ignore[no-untyped-def]
    plan = HELPERS["_plan"]()
    return plan, initialize_battle_scenario_materialization_run(
        plan,
        HELPERS["_identity"](plan),
    )


def _execute(journal, assignment):  # type: ignore[no-untyped-def]
    return SCRIPT["_execute_pending_assignment"](
        journal,
        assignment=assignment,
        journal_path=Path("journal.json"),
        source_bytes=b"source",
        capture_directory=Path("captures"),
        context_catalog=Path("catalog.json"),
        registry_source_commit="a" * 40,
        expected_registry_sha256="b" * 64,
        expected_context_catalog_sha256="c" * 64,
        rom_path=Path("red.gb"),
        maximum_encounter_steps=512,
        watch=False,
        speed=None,
    )


def test_runner_accepts_only_the_frozen_plan_not_caller_selected_sources() -> None:
    options = SCRIPT["_parser"]()._option_string_actions

    assert "--plan" in options
    assert "--expected-plan-sha256" in options
    assert "--excluded-plan" in options
    assert "--excluded-run-journal" in options
    assert "--source-state" not in options
    assert "--party-slot" not in options
    assert "--capture-id" not in options
    assert "--venue" not in options


def _ci_document(*, event: str = "push", head_branch: str = "main") -> dict[str, object]:
    return {
        "attempt": 1,
        "conclusion": "success",
        "databaseId": 123,
        "event": event,
        "headBranch": head_branch,
        "headSha": "a" * 40,
        "status": "completed",
        "url": (
            "https://github.com/PeteAndrews1289/"
            "pokemon-red-completion-agent/actions/runs/123"
        ),
        "workflowName": "CI",
    }


def _patch_ci_response(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
) -> None:
    function = SCRIPT["_require_exact_green_ci_run"]
    monkeypatch.setitem(
        function.__globals__,
        "subprocess",
        SimpleNamespace(
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(document),
                stderr="",
            ),
            SubprocessError=subprocess.SubprocessError,
        ),
    )


def test_exact_ci_accepts_only_the_exact_main_push(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ci_response(monkeypatch, _ci_document())

    result = SCRIPT["_require_exact_green_ci_run"](
        123,
        1,
        source_commit="a" * 40,
    )

    assert result["event"] == "push"
    assert result["headBranch"] == "main"


@pytest.mark.parametrize(
    ("event", "head_branch"),
    (("pull_request", "feature"), ("push", "feature"), ("workflow_dispatch", "main")),
)
def test_exact_ci_rejects_non_main_pushes(
    monkeypatch: pytest.MonkeyPatch,
    event: str,
    head_branch: str,
) -> None:
    _patch_ci_response(
        monkeypatch,
        _ci_document(event=event, head_branch=head_branch),
    )

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationRunnerError"],
        match="exact_ci_differs",
    ):
        SCRIPT["_require_exact_green_ci_run"](
            123,
            1,
            source_commit="a" * 40,
        )


def test_exact_ci_failure_reason_survives_public_sanitization() -> None:
    error = SCRIPT["BattleScenarioMaterializationRunnerError"]("exact_ci_differs")

    assert SCRIPT["_failure_reason"](error) == "exact_ci_differs"


def test_v2_runner_reopens_exhausted_evidence_and_rejects_root_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = V2_HELPERS["_build"]()
    args = SimpleNamespace(
        excluded_plan=Path("old-plan.json"),
        excluded_run_journal=Path("old-journal.json"),
    )
    require = SCRIPT["_require_plan_exclusions"]
    globals_ = require.__globals__
    observed: list[tuple[str, str]] = []

    def load(*args: object, **kwargs: object) -> frozenset[str]:
        del args
        observed.append(
            (
                str(kwargs["expected_plan_sha256"]),
                str(kwargs["expected_journal_sha256"]),
            )
        )
        return frozenset()

    monkeypatch.setitem(globals_, "_load_attempted_source_exclusions", load)
    require(args, plan=plan)

    assert observed == [
        (plan.excluded_plan_sha256, plan.excluded_run_journal_sha256)
    ]
    monkeypatch.setitem(
        globals_,
        "_load_attempted_source_exclusions",
        lambda *args, **kwargs: frozenset(
            {plan.inventory[0].source.source_state_sha256}
        ),
    )
    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationRunnerError"],
        match="reuses an exhausted source",
    ):
        require(args, plan=plan)


def test_started_is_durable_before_controller_capable_materializer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, journal = _journal()
    observed: list[str] = []
    globals_ = SCRIPT["_execute_pending_assignment"].__globals__

    def replace_journal(path: Path, payload: bytes) -> None:
        del path
        observed.append(parse_battle_scenario_materialization_run(payload).entries[0].status)

    def interrupt(*args: object, **kwargs: object) -> object:
        del args, kwargs
        assert observed == [STARTED]
        raise KeyboardInterrupt

    monkeypatch.setitem(globals_, "_replace_journal", replace_journal)
    monkeypatch.setitem(globals_, "_materialize_assignment", interrupt)

    with pytest.raises(KeyboardInterrupt):
        _execute(journal, plan.assignments[0])

    assert observed == [STARTED]


def test_controlled_failure_is_terminal_and_never_requeued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, journal = _journal()
    observed: list[str] = []
    globals_ = SCRIPT["_execute_pending_assignment"].__globals__

    monkeypatch.setitem(
        globals_,
        "_replace_journal",
        lambda path, payload: observed.append(
            parse_battle_scenario_materialization_run(payload).entries[0].status
        ),
    )
    monkeypatch.setitem(
        globals_,
        "_materialize_assignment",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SCRIPT["BattleScenarioMaterializationRunnerError"](
                "materializer_process_failed"
            )
        ),
    )

    result = _execute(journal, plan.assignments[0])

    assert observed == [STARTED, FAILED]
    assert result.entries[0].status == FAILED
    assert result.entries[0].reason_code == "materializer_process_failed"


def test_child_failure_stage_survives_without_stderr_or_path_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan, _ = _journal()
    assignment = plan.assignments[0]
    globals_ = SCRIPT["_materialize_assignment"].__globals__
    payload = (
        b'{"move_choices_executed":0,"private_path_fields":0,'
        b'"reason_code":"source_relocation_failed","root_claims_created":0,'
        b'"schema":"pokemon-private-battle-scenario-materialization-failure-v1",'
        b'"status":"failed_closed","teacher_queries":0}'
    )
    monkeypatch.setitem(
        globals_,
        "subprocess",
        SimpleNamespace(
            run=lambda *args, **kwargs: subprocess.CompletedProcess(
                args=[], returncode=1, stdout=payload, stderr=b"/private/secret"
            )
        ),
    )

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationRunnerError"],
        match="source_relocation_failed",
    ):
        SCRIPT["_materialize_assignment"](
            assignment,
            source_bytes=b"source",
            capture_directory=tmp_path,
            context_catalog=tmp_path / "catalog.json",
            registry_source_commit="a" * 40,
            expected_registry_sha256="b" * 64,
            expected_context_catalog_sha256="c" * 64,
            rom_path=tmp_path / "red.gb",
            maximum_encounter_steps=1,
            watch=False,
            speed=None,
        )


def test_v2_runner_reopens_plan_and_passes_only_its_bound_venue_to_child(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = V2_HELPERS["_build"]()
    plan_path = tmp_path / "plan.json"
    plan_path.write_bytes(plan.canonical_bytes())
    plan_path.chmod(0o600)

    assert SCRIPT["_read_plan"](plan_path) == plan

    observed: list[list[str]] = []
    payload = (
        b'{"move_choices_executed":0,"private_path_fields":0,'
        b'"reason_code":"source_relocation_failed","root_claims_created":0,'
        b'"schema":"pokemon-private-battle-scenario-materialization-failure-v1",'
        b'"status":"failed_closed","teacher_queries":0}'
    )

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del kwargs
        observed.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=1,
            stdout=payload,
            stderr=b"",
        )

    globals_ = SCRIPT["_materialize_assignment"].__globals__
    monkeypatch.setitem(globals_, "subprocess", SimpleNamespace(run=run))
    assignment = plan.assignments[0]

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationRunnerError"],
        match="source_relocation_failed",
    ):
        SCRIPT["_materialize_assignment"](
            assignment,
            source_bytes=b"source",
            capture_directory=tmp_path,
            context_catalog=tmp_path / "catalog.json",
            registry_source_commit="a" * 40,
            expected_registry_sha256="b" * 64,
            expected_context_catalog_sha256="c" * 64,
            rom_path=tmp_path / "red.gb",
            maximum_encounter_steps=1,
            watch=False,
            speed=None,
        )

    venue_flag = observed[0].index("--expected-reachable-venue-id")
    assert observed[0][venue_flag + 1] == assignment.selected_venue.venue_id


def test_success_requires_independent_output_and_receipt_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, journal = _journal()
    observed: list[str] = []
    checked: list[str] = []
    globals_ = SCRIPT["_execute_pending_assignment"].__globals__

    monkeypatch.setitem(
        globals_,
        "_replace_journal",
        lambda path, payload: observed.append(
            parse_battle_scenario_materialization_run(payload).entries[0].status
        ),
    )
    monkeypatch.setitem(globals_, "_materialize_assignment", lambda *a, **k: {"ok": True})
    monkeypatch.setitem(
        globals_,
        "_authenticate_assignment_outputs",
        lambda *a, **k: ("d" * 64, "e" * 64),
    )
    monkeypatch.setitem(
        globals_,
        "_require_materializer_receipt",
        lambda *a, **k: checked.append("receipt"),
    )

    result = _execute(journal, plan.assignments[0])

    assert checked == ["receipt"]
    assert observed == [STARTED, SUCCEEDED]
    assert result.entries[0].state_sha256 == "d" * 64
    assert result.entries[0].manifest_sha256 == "e" * 64


def test_atomic_journal_replacement_round_trips_and_rejects_ambiguous_temp(
    tmp_path: Path,
) -> None:
    plan, journal = _journal()
    path = tmp_path / "journal.json"
    SCRIPT["_write_new"](path, journal.canonical_bytes())
    started = start_battle_scenario_materialization_assignment(journal, 0)

    SCRIPT["_replace_journal"](path, started.canonical_bytes())

    assert SCRIPT["_read_journal"](path) == started
    temporary = path.with_name(f".{path.name}.next")
    temporary.write_bytes(b"ambiguous")
    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationRunnerError"],
        match="ambiguous",
    ):
        SCRIPT["_replace_journal"](path, started.canonical_bytes())


def test_resume_reconciles_complete_started_output_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan, journal = _journal()
    journal = start_battle_scenario_materialization_assignment(journal, 0)
    assignment = plan.assignments[0]
    (tmp_path / assignment.state_filename).write_bytes(b"state")
    (tmp_path / assignment.manifest_filename).write_bytes(b"manifest")
    journal_path = tmp_path / "journal.json"
    SCRIPT["_write_new"](journal_path, journal.canonical_bytes())
    globals_ = SCRIPT["_reconcile_existing_entries"].__globals__
    monkeypatch.setitem(
        globals_,
        "_authenticate_assignment_outputs",
        lambda *a, **k: ("f" * 64, "1" * 64),
    )
    monkeypatch.setitem(
        globals_,
        "_require_pending_outputs_absent",
        lambda *a, **k: None,
    )

    reconciled = SCRIPT["_reconcile_existing_entries"](
        journal,
        plan=plan,
        capture_directory=tmp_path.resolve(),
        journal_path=journal_path,
        rom_path=Path("red.gb"),
    )

    assert reconciled.entries[0].status == SUCCEEDED
    assert reconciled.entries[0].attempt_count == 1
    assert SCRIPT["_read_journal"](journal_path) == reconciled
