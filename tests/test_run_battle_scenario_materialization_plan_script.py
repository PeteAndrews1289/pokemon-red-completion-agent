from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pokemon_red_completion.battle_scenario_materialization_run import (
    FAILED,
    STARTED,
    SUCCEEDED,
    fail_battle_scenario_materialization_assignment,
    initialize_battle_scenario_materialization_run,
    parse_battle_scenario_materialization_run,
    start_battle_scenario_materialization_assignment,
    succeed_battle_scenario_materialization_assignment,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition

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


@pytest.mark.parametrize(
    ("candidate_count", "supported_candidate_count"),
    ((2, 2), (3, 2), (3, 3), (4, 2), (4, 3), (4, 4)),
)
def test_materialization_accepts_the_learners_variable_candidate_cardinality(
    candidate_count: int,
    supported_candidate_count: int,
) -> None:
    assert SCRIPT["_battle_candidate_cardinality_is_supported"](
        candidate_count,
        supported_candidate_count,
    )


@pytest.mark.parametrize(
    ("candidate_count", "supported_candidate_count"),
    (
        (1, 1),
        (2, 1),
        (3, 4),
        (4, 5),
        (5, 2),
        (True, 2),
        (2, True),
        (2.0, 2),
        (2, 2.0),
    ),
)
def test_materialization_rejects_nonlearning_candidate_cardinality(
    candidate_count: object,
    supported_candidate_count: object,
) -> None:
    assert not SCRIPT["_battle_candidate_cardinality_is_supported"](
        candidate_count,
        supported_candidate_count,
    )


@pytest.mark.parametrize(
    "reason_code",
    (
        "materializer_candidate_cardinality_differs",
        "materialized_capture_candidate_cardinality_differs",
        "materialized_capture_observation_differs",
        "materialized_capture_party_binding_differs",
        "materialized_capture_policy_boundary_differs",
        "materialized_capture_reopen_crossed_controller_boundary",
    ),
)
def test_materialization_forensic_reasons_survive_public_sanitization(
    reason_code: str,
) -> None:
    error = SCRIPT["BattleScenarioMaterializationRunnerError"](reason_code)

    assert SCRIPT["_failure_reason"](error) == reason_code


def _materializer_receipt(
    *,
    candidate_count: object = 3,
    supported_candidate_count: object = 2,
    partition: ScenarioPartition = ScenarioPartition.TRAIN,
) -> tuple[object, dict[str, object]]:
    candidates = tuple(
        V2_HELPERS["_candidate"](index, partition=partition)
        for index in range(10)
    )
    plan = V2_HELPERS["_build"](candidates)
    assignment = plan.assignments[0]
    source = assignment.candidate.source
    venue = assignment.selected_venue
    return assignment, {
        "schema": "pokemon-private-battle-scenario-materialization-receipt-v2",
        "status": "ok",
        "capture_id": assignment.capture_id,
        "root_lineage_id": source.root_lineage_id,
        "partition": partition.value,
        "source_commit": plan.source_commit,
        "source_state_sha256": source.source_state_sha256,
        "source_slot_id": source.source_slot_id,
        "source_assignment_id": source.source_assignment_id,
        "source_context_id": source.source_context_id,
        "source_envelope_sha256": source.source_envelope_sha256,
        "root_consumption_sha256": source.root_consumption_sha256,
        "context_catalog_sha256": source.catalog_sha256,
        "registry_sha256": source.registry_sha256,
        "registry_source_commit": source.registry_source_commit,
        "state_sha256": "d" * 64,
        "manifest_sha256": "e" * 64,
        "venue_id": venue.venue_id,
        "venue_minimum_encounter_level": venue.minimum_encounter_level,
        "venue_maximum_encounter_level": venue.maximum_encounter_level,
        "source_location": venue.source_location,
        "party_slot": assignment.party_slot.party_slot,
        "candidate_count": candidate_count,
        "supported_candidate_count": supported_candidate_count,
        "teacher_queries": 0,
        "move_choices_executed": 0,
        "root_claims_created": 0,
        "caller_supplied_partition": False,
        "caller_supplied_lineage": False,
        "caller_supplied_source_location": False,
        "selected_reachable_venue_reauthenticated": True,
        "private_path_fields": 0,
    }


def test_materializer_receipt_accepts_three_candidates_with_two_supported() -> None:
    assignment, receipt = _materializer_receipt()

    SCRIPT["_require_materializer_receipt"](
        receipt,
        assignment=assignment,
        source_commit=receipt["source_commit"],
        state_sha256="d" * 64,
        manifest_sha256="e" * 64,
    )


def test_materializer_receipt_accepts_catalog_derived_development_partition() -> None:
    assignment, receipt = _materializer_receipt(
        partition=ScenarioPartition.DEVELOPMENT
    )

    SCRIPT["_require_materializer_receipt"](
        receipt,
        assignment=assignment,
        source_commit=receipt["source_commit"],
        state_sha256="d" * 64,
        manifest_sha256="e" * 64,
    )
    assert SCRIPT["_plan_partition"](
        V2_HELPERS["_build"](
            tuple(
                V2_HELPERS["_candidate"](
                    index,
                    partition=ScenarioPartition.DEVELOPMENT,
                )
                for index in range(10)
            )
        )
    ) is ScenarioPartition.DEVELOPMENT


def test_materializer_receipt_reports_candidate_cardinality_separately() -> None:
    assignment, receipt = _materializer_receipt(candidate_count=5)

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationRunnerError"],
        match="materializer_candidate_cardinality_differs",
    ):
        SCRIPT["_require_materializer_receipt"](
            receipt,
            assignment=assignment,
            source_commit=receipt["source_commit"],
            state_sha256="d" * 64,
            manifest_sha256="e" * 64,
        )


def test_v2_runner_reopens_exhausted_evidence_and_rejects_root_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = V2_HELPERS["_build"]()
    args = SimpleNamespace(
        excluded_plan=Path("old-plan.json"),
        excluded_run_journal=Path("old-journal.json"),
        predecessor_plan=None,
        predecessor_run_journal=None,
        predecessor_capture_directory=None,
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
    require(args, plan=plan, rom_path=Path("red.gb"))

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
        require(args, plan=plan, rom_path=Path("red.gb"))


def test_completion_runner_requires_both_exclusion_generations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = V2_HELPERS["_build_completion"]()
    args = SimpleNamespace(
        excluded_plan=Path("old-plan.json"),
        excluded_run_journal=Path("old-journal.json"),
        predecessor_plan=Path("predecessor-plan.json"),
        predecessor_run_journal=Path("predecessor-journal.json"),
        predecessor_capture_directory=Path("predecessor-captures"),
    )
    require = SCRIPT["_require_plan_exclusions"]
    globals_ = require.__globals__
    observed: list[tuple[Path, Path, Path]] = []

    def authenticate(*args: object, **kwargs: object) -> frozenset[str]:
        del args
        observed.append(
            (
                kwargs["earliest_plan_path"],
                kwargs["predecessor_plan_path"],
                kwargs["predecessor_capture_directory"],
            )
        )
        return frozenset(
            item.source_state_sha256 for item in plan.retained_successes
        )

    monkeypatch.setitem(globals_, "_require_completion_predecessor", authenticate)

    require(args, plan=plan, rom_path=Path("red.gb"))

    assert observed == [
        (
            Path("old-plan.json"),
            Path("predecessor-plan.json"),
            Path("predecessor-captures"),
        )
    ]


def test_completion_runner_rejects_attempted_source_in_new_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = V2_HELPERS["_build_completion"]()
    args = SimpleNamespace(
        excluded_plan=Path("old-plan.json"),
        excluded_run_journal=Path("old-journal.json"),
        predecessor_plan=Path("predecessor-plan.json"),
        predecessor_run_journal=Path("predecessor-journal.json"),
        predecessor_capture_directory=Path("predecessor-captures"),
    )
    require = SCRIPT["_require_plan_exclusions"]
    monkeypatch.setitem(
        require.__globals__,
        "_require_completion_predecessor",
        lambda *args, **kwargs: frozenset(
            {plan.inventory[0].source.source_state_sha256}
        ),
    )

    with pytest.raises(
        SCRIPT["BattleScenarioMaterializationRunnerError"],
        match="reuses an attempted source",
    ):
        require(args, plan=plan, rom_path=Path("red.gb"))


def test_runner_strictly_reopens_completion_plan(tmp_path: Path) -> None:
    plan = V2_HELPERS["_build_completion"]()
    path = tmp_path / "completion-plan.json"
    path.write_bytes(plan.canonical_bytes())
    path.chmod(0o600)

    assert SCRIPT["_read_plan"](path) == plan


def test_completion_predecessor_reauthenticates_only_successes_and_retains_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    predecessor_directory = tmp_path / "predecessor"
    predecessor_directory.mkdir(mode=0o700)
    predecessor_directory_sha256 = hashlib.sha256(
        str(predecessor_directory.resolve()).encode("utf-8")
    ).hexdigest()
    predecessor = V2_HELPERS["_build"]()
    predecessor = replace(
        predecessor,
        capture_directory_sha256=predecessor_directory_sha256,
    )
    identity = replace(
        HELPERS["_identity"](predecessor),
        source_commit=predecessor.source_commit,
    )
    journal = initialize_battle_scenario_materialization_run(
        predecessor,
        identity,
    )
    successful_ordinals = {0, 2, 4, 5, 6}
    for assignment in predecessor.assignments:
        journal = start_battle_scenario_materialization_assignment(
            journal,
            assignment.ordinal,
        )
        if assignment.ordinal in successful_ordinals:
            journal = succeed_battle_scenario_materialization_assignment(
                journal,
                assignment.ordinal,
                state_sha256=V2_HELPERS["_sha"](
                    f"retained-state-{assignment.ordinal}"
                ),
                manifest_sha256=V2_HELPERS["_sha"](
                    f"retained-manifest-{assignment.ordinal}"
                ),
            )
        else:
            journal = fail_battle_scenario_materialization_assignment(
                journal,
                assignment.ordinal,
                reason_code="materialized_capture_state_differs",
            )
    completion = V2_HELPERS["_build_completion"]()
    completion = replace(
        completion,
        predecessor_plan_sha256=predecessor.plan_sha256,
        predecessor_run_journal_sha256=journal.journal_sha256,
        predecessor_capture_directory_sha256=predecessor_directory_sha256,
    )
    function = SCRIPT["_require_completion_predecessor"]
    globals_ = function.__globals__
    historical = frozenset(f"historical-{index}" for index in range(7))
    observed_ordinals: list[int] = []
    monkeypatch.setitem(
        globals_,
        "_load_attempted_source_exclusions",
        lambda *args, **kwargs: historical,
    )
    monkeypatch.setitem(
        globals_,
        "_private_capture_directory",
        lambda *args, **kwargs: predecessor_directory.resolve(),
    )
    monkeypatch.setitem(
        globals_,
        "_private_existing_file",
        lambda path, **kwargs: path,
    )
    monkeypatch.setitem(globals_, "_read_plan", lambda path: predecessor)
    monkeypatch.setitem(globals_, "_read_journal", lambda path: journal)

    def authenticate(assignment, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        observed_ordinals.append(assignment.ordinal)
        entry = journal.entries[assignment.ordinal]
        return entry.state_sha256, entry.manifest_sha256

    monkeypatch.setitem(
        globals_,
        "_authenticate_assignment_outputs",
        authenticate,
    )

    attempted = function(
        completion,
        earliest_plan_path=Path("earliest-plan.json"),
        earliest_journal_path=Path("earliest-journal.json"),
        predecessor_plan_path=Path("predecessor-plan.json"),
        predecessor_journal_path=Path("predecessor-journal.json"),
        predecessor_capture_directory=predecessor_directory,
        rom_path=Path("red.gb"),
    )

    assert observed_ordinals == [0, 2, 4, 5, 6]
    assert len(attempted) == 14
    assert historical.issubset(attempted)


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
