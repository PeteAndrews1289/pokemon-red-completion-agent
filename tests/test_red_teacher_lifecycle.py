"""Synthetic process/failed-closeout tests; no native process or emulator is launched."""

import hashlib
import importlib.util
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest


def helper(name):
    path = Path(__file__).parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def chain_fixture(tmp_path):
    root = tmp_path / "project"
    cap = root / "capacity"
    shared = cap / "teacher-v1"
    shared.mkdir(parents=True)
    guard = shared / "guard.py"
    guard.write_text("# synthetic guard\n")
    case = cap / "direct-synthetic"
    spec = dict(
        project_root=str(root),
        capacity_root=str(cap),
        case=str(case),
        phase="direct",
        python=str(root / "runtime/bin/python"),
        worker=str(shared / "run.py"),
        worker_sha256="a" * 64,
        plan=str(case / "PLAN.json"),
        plan_sha256="b" * 64,
        resource_plan=str(case / "RESOURCE.json"),
        resource_plan_sha256="c" * 64,
        supervisor=str(cap / "existing-supervisor.py"),
        linux_user="pokemon",
        distribution="PokemonRedUbuntu-20261016",
        wsl_executable="C:\\Windows\\System32\\wsl.exe",
        guard=str(guard),
        guard_sha256=hashlib.sha256(guard.read_bytes()).hexdigest(),
        guard_arguments=["--spec", str(case / "LAUNCH-SPECIFICATION.json")],
        mission=str(root / "MISSION.json"),
    )
    command = [
        spec["python"],
        "-I",
        "-B",
        spec["worker"],
        "--case",
        spec["case"],
        "--plan-sha256",
        spec["plan_sha256"],
        "--phase",
        "direct",
    ]
    spec["worker_command"] = command
    resource = dict(
        command=command,
        script_sha256=spec["worker_sha256"],
        outer_seconds=480,
        absolute_cutoff_utc="2026-10-24T04:00:00+00:00",
        cgroup_name="pokemon-capacity-synthetic",
    )
    setup = dict(
        command=command,
        script_sha256=spec["worker_sha256"],
        plan_sha256=spec["resource_plan_sha256"],
        actor_uid=1000,
        actor_user="pokemon",
        launcher_pid=101,
        absolute_cutoff_utc=resource["absolute_cutoff_utc"],
        hard_maximum_seconds=480,
        group="/sys/fs/cgroup/pokemon-capacity-synthetic",
    )
    root_exit = dict(
        plan_sha256=spec["resource_plan_sha256"],
        child_pid=102,
        actor_user="pokemon",
        absolute_cutoff_utc=resource["absolute_cutoff_utc"],
        hard_maximum_seconds=480,
        group=setup["group"],
    )
    supervisor_command = [
        spec["python"],
        "-I",
        "-B",
        spec["supervisor"],
        "--plan",
        spec["resource_plan"],
        "--plan-sha256",
        spec["resource_plan_sha256"],
        "--expected-script",
        spec["worker"],
    ]
    early = dict(
        plan_sha256=spec["plan_sha256"],
        worker_sha256=spec["worker_sha256"],
        processes=[
            dict(pid=103, parent_pid=102, start_ticks=9003, uid=1000, command=command),
            dict(
                pid=102,
                parent_pid=101,
                start_ticks=9002,
                uid=0,
                command=["runuser", "--user", "pokemon", "--", *command],
            ),
        ],
        supervisor=dict(
            pid=101, parent_pid=100, start_ticks=9001, uid=0, command=supervisor_command
        ),
    )
    expected = [
        "-d",
        spec["distribution"],
        "-u",
        "root",
        "--cd",
        spec["project_root"],
        "--",
        *supervisor_command,
    ]
    actual = dict(
        ProcessId=333,
        CreationDate="2026-10-24T02:00:00+00:00",
        CommandLine='"' + spec["wsl_executable"] + '" ' + " ".join(expected),
    )
    launch = dict(
        expected_arguments=expected,
        resource_plan_sha256=spec["resource_plan_sha256"],
        actual_process=actual,
        launch_process_id=333,
    )
    snapshot = dict(
        original_process=actual,
        actual_process=None,
        original_absent=True,
        original_live=False,
        observed_at_utc="2026-10-24T02:01:00+00:00",
    )
    return spec, resource, early, setup, root_exit, launch, snapshot


def test_exact_shared_entrypoint_chain_and_guard_contract(tmp_path):
    args = chain_fixture(tmp_path)
    result = helper("red_teacher_process_chain").validate_chain(
        *args, pokemon_uid=1000, now=datetime(2026, 10, 24, 2, 1, 10, tzinfo=UTC)
    )
    assert result["linux_parent_chain_exact"] and result["worker_command"][-1] == "direct"
    spec, resource, *_ = args
    plan = dict(
        case=spec["case"],
        native_execution_authorized=True,
        cutoff_utc=resource["absolute_cutoff_utc"],
        preflight_root_seconds=90,
        full_hold_seconds=480,
        mission=spec["mission"],
    )
    assert helper("guard_red_teacher_case").validate_guard_spec(spec, resource, plan) == Path(
        spec["case"]
    )
    plan["native_execution_authorized"] = False
    with pytest.raises(ValueError, match="native execution disabled"):
        helper("guard_red_teacher_case").validate_guard_spec(spec, resource, plan)


@pytest.mark.parametrize("active", [False, None, 1])
def test_released_or_missing_writer_claim_cannot_dispatch_old_case(active):
    validate = helper("guard_red_teacher_case").validate_source_claim
    claim = dict(
        source_writer_active=True,
        source_writer_mission="declared-mission",
        actual_running=False,
        all_native_workers_stopped=True,
        active_probe=None,
    )
    validate(claim, "declared-mission")
    if active is None:
        del claim["source_writer_active"]
    else:
        claim["source_writer_active"] = active
    with pytest.raises(ValueError, match="active mission/source claim"):
        validate(claim, "declared-mission")


@pytest.mark.parametrize(
    "mutation",
    [
        "worker_phase",
        "worker_uid",
        "parent_pid",
        "parent_command",
        "supervisor_pid",
        "supervisor_command",
        "supervisor_uid",
        "supervisor_ticks",
        "windows_command",
        "snapshot_identity",
        "stale_snapshot",
    ],
)
def test_exact_chain_rejects_identity_or_phase_drift(tmp_path, mutation):
    args = list(chain_fixture(tmp_path))
    spec, resource, early, setup, root_exit, launch, snapshot = args
    if mutation == "worker_phase":
        early["processes"][0]["command"] = [*early["processes"][0]["command"][:-1], "preflight"]
    elif mutation == "worker_uid":
        early["processes"][0]["uid"] = 0
    elif mutation == "parent_pid":
        early["processes"][1]["parent_pid"] = 999
    elif mutation == "parent_command":
        early["processes"][1]["command"] = ["unrelated"]
    elif mutation.startswith("supervisor_"):
        field = mutation.split("_", 1)[1]
        field = "start_ticks" if field == "ticks" else field
        early["supervisor"][field] = (
            ["unrelated"] if field == "command" else (0 if field == "start_ticks" else 999)
        )
    elif mutation == "windows_command":
        launch["actual_process"]["CommandLine"] += " --different"
    elif mutation == "snapshot_identity":
        snapshot["original_process"] = dict(snapshot["original_process"], ProcessId=999)
    else:
        snapshot["observed_at_utc"] = "2026-10-24T01:58:00+00:00"
    with pytest.raises(ValueError):
        helper("red_teacher_process_chain").validate_chain(
            *args, pokemon_uid=1000, now=datetime(2026, 10, 24, 2, 1, 10, tzinfo=UTC)
        )


def physical(attempt, constructed, load_attempt, loaded):
    return dict(
        construction_attempts=attempt,
        emulators_constructed=constructed,
        load_attempts=load_attempt,
        state_loads=loaded,
    )


@pytest.mark.parametrize(
    "counts,known", [(physical(0, 0, 0, 0), True), (physical(1, 0, 0, 0), False)]
)
def test_failed_prebind_or_constructor_can_close_without_fabricated_terminal(counts, known):
    result = dict(
        passed=False,
        physical_emulator_accounting=counts,
        error="retained failure",
        traceback="retained chain",
    )
    before = deepcopy(result)
    closed = helper("red_teacher_closeout").classify_closed_phase(
        result, phase="direct", processes_absent=True, cgroup_empty=True
    )
    assert closed["controls_released"] and not closed["terminal_available"]
    assert closed["native_costs_known"] is known and not closed["continuation_authority"]
    assert result == before


@pytest.mark.parametrize("actions,frames", [(0, 0), (13, 900)])
def test_loaded_and_postinput_failures_preserve_real_terminal_and_partial_cost(actions, frames):
    result = dict(
        passed=False,
        physical_emulator_accounting=physical(1, 1, 1, 1),
        controls_released=True,
        terminal_sha256="d" * 64,
        actions=actions,
        frames=frames,
        goal_attempts=0,
        heals=0,
        native_seconds=1.5,
        wild_battles=0,
        story_battles=0,
        error="retained failure",
    )
    closed = helper("red_teacher_closeout").classify_closed_phase(
        result, phase="direct", processes_absent=True, cgroup_empty=True, terminal_sha256="d" * 64
    )
    assert closed["terminal_available"] and closed["native_costs"]["actions"] == actions
    assert not closed["native_admission_authority"] and not closed["continuation_authority"]


def test_success_requires_native_release_and_exported_terminal():
    result = dict(passed=True, physical_emulator_accounting=physical(1, 1, 1, 1))
    with pytest.raises(ValueError, match="successful native"):
        helper("red_teacher_closeout").classify_closed_phase(
            result, phase="direct", processes_absent=True, cgroup_empty=True
        )


def test_closed_failure_cannot_release_live_process_or_unknown_dispatch():
    classify = helper("red_teacher_closeout").classify_closed_phase
    for kwargs in (
        dict(processes_absent=False, cgroup_empty=True),
        dict(processes_absent=True, cgroup_empty=False),
    ):
        with pytest.raises(ValueError, match="process closure"):
            classify(dict(passed=False, native_dispatch_entered=False), phase="direct", **kwargs)
    with pytest.raises(ValueError, match="physical accounting"):
        classify(
            dict(passed=False, native_dispatch_entered=True),
            phase="direct",
            processes_absent=True,
            cgroup_empty=True,
        )


def test_actual_engine_prebind_failure_retains_error_and_zero_physical_work(tmp_path):
    from pokemon_red_completion.red_teacher_direct import run_direct

    plan = dict(
        condition="synthetic",
        role="train_sampling",
        package=str(tmp_path / "manifest.json"),
        cutoff_utc="2099-01-01T00:00:00+00:00",
        pins={str(tmp_path / "missing-pin"): "0" * 64},
    )
    result = run_direct(
        plan,
        output=tmp_path,
        worker_path=tmp_path / "unused.py",
        loader_definitions={},
        started=0,
        write=lambda *args: (_ for _ in ()).throw(
            AssertionError("no receipt should be emitted before bind")
        ),
    )
    assert result["passed"] is False and result["error_type"] == "FileNotFoundError"
    assert result["physical_emulator_accounting"] == physical(0, 0, 0, 0)
    closed = helper("red_teacher_closeout").classify_closed_phase(
        result, phase="direct", processes_absent=True, cgroup_empty=True
    )
    assert closed["native_costs_known"] and not closed["terminal_available"]


def test_cli_rejects_case_mismatch_before_identity_or_output_write(tmp_path):
    plan = dict(case=str(tmp_path / "different-case"), native_execution_authorized=False)
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="case identity"):
        helper("run_red_teacher_case").main(
            [
                "--case",
                str(tmp_path),
                "--plan-sha256",
                hashlib.sha256(path.read_bytes()).hexdigest(),
                "--phase",
                "preflight",
            ]
        )
    assert [item.name for item in tmp_path.iterdir()] == ["PLAN.json"]


def test_cli_direct_phase_cannot_use_disabled_proposal(tmp_path):
    plan = dict(case=str(tmp_path), native_execution_authorized=False)
    path = tmp_path / "PLAN.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="native execution disabled"):
        helper("run_red_teacher_case").main(
            [
                "--case",
                str(tmp_path),
                "--plan-sha256",
                hashlib.sha256(path.read_bytes()).hexdigest(),
                "--phase",
                "direct",
            ]
        )
    assert [item.name for item in tmp_path.iterdir()] == ["PLAN.json"]


@pytest.mark.parametrize(
    "suffix,accepted", [(" ", True), ("\t", True), (" \t ", True), (" --different ", False)]
)
def test_windows_command_tail_keeps_exact_argument_identity(tmp_path, suffix, accepted):
    args = chain_fixture(tmp_path)
    args[5]["actual_process"]["CommandLine"] += suffix
    if accepted:
        result = helper("red_teacher_process_chain").validate_chain(
            *args, pokemon_uid=1000, now=datetime(2026, 10, 24, 2, 1, 10, tzinfo=UTC)
        )
        assert result["linux_parent_chain_exact"]
        assert args[5]["actual_process"]["CommandLine"].endswith(suffix)
    else:
        with pytest.raises(ValueError, match="Windows actual command differs"):
            helper("red_teacher_process_chain").validate_chain(
                *args, pokemon_uid=1000, now=datetime(2026, 10, 24, 2, 1, 10, tzinfo=UTC)
            )


@pytest.mark.parametrize(
    "fault", [None, "named_only", "censored", "wrong_order", "quest_gain", "nan", "bool"]
)
def test_partial_closeout_reads_real_public_outcome_schema(fault):
    from pokemon_red_completion.living_dex_option_value import (
        LivingDexObservedOutcome,
        LivingDexOutcomeStatus,
    )

    outcome = LivingDexObservedOutcome(
        LivingDexOutcomeStatus.SETTLED,
        True,
        0,
        0,
        0.1,
        0.1,
        0,
        0,
        0,
        0,
    ).public_dict()
    if fault == "named_only":
        outcome = {"verified_success": True}
    elif fault == "censored":
        outcome["status"] = "censored"
    elif fault == "wrong_order":
        outcome["target_names"].reverse()
    elif fault == "quest_gain":
        outcome["target_values"][1] = 1.0
    elif fault == "nan":
        outcome["target_values"][3] = float("nan")
    elif fault == "bool":
        outcome["target_values"][0] = True
    check = helper("authenticate_red_teacher_case").verify_partial_teacher_outcome
    if fault is None:
        check(outcome)
    else:
        with pytest.raises((AssertionError, KeyError)):
            check(outcome)


@pytest.mark.parametrize(
    "fault",
    [None, "development", "partial_cost", "copyback", "swapped_menu", "wrong_source", "fit"],
)
def test_venue_closeout_requires_real_bound_train_arm(fault):
    plan = dict(schema="pokemon.red.native-venue-geometry-TRAIN-case.v1", source_sha256="a" * 64)
    result = dict(
        teacher_selected=True,
        training_admission=True,
        new_fits=0,
        new_weights=0,
        copy_back=False,
        campaign_progress=False,
        frames=100,
        actions=10,
        terminal_sha256="b" * 64,
    )
    decision = dict(
        binding=dict(partition="train", initial_state_sha256="a" * 64),
        candidate_set={"rows": [1, 2]},
        teacher_forced_venue=True,
        outcomes_not_opened=True,
        assigned_index=0,
    )
    document = dict(
        fit_eligible=True,
        actual_progress=False,
        settled_native_attempt=True,
        controller_costs_are_full_native_totals=True,
        frames=100,
        actions=10,
        terminal_state_sha256="b" * 64,
        prospective_binding=deepcopy(decision["binding"]),
        candidate_set=deepcopy(decision["candidate_set"]),
        assigned_index=0,
    )
    if fault == "development":
        decision["binding"]["partition"] = "development"
    elif fault == "partial_cost":
        document["controller_costs_are_full_native_totals"] = False
    elif fault == "copyback":
        result["copy_back"] = True
    elif fault == "swapped_menu":
        document["candidate_set"] = {"rows": [2, 1]}
    elif fault == "wrong_source":
        plan["source_sha256"] = "c" * 64
    elif fault == "fit":
        result["new_fits"] = 1
    verify = helper("authenticate_red_teacher_case").verify_venue_teacher_outcome
    if fault is None:
        verify(plan, result, document, decision)
    else:
        with pytest.raises(AssertionError):
            verify(plan, result, document, decision)
