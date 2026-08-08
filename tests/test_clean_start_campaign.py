from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from pokemon_red_completion.battle_plan import RED_BATTLE_PLAN_IDS
from pokemon_red_completion.clean_start_campaign import (
    ASSISTANCE_COUNTERS,
    CLEAN_START_OUTCOME_SCHEMA,
    REQUIRED_MODEL_ROLES,
    CleanStartCampaign,
    CleanStartCampaignError,
    CleanStartExecutionIdentity,
    ModelArtifactIdentity,
    build_clean_start_campaign,
    derive_initial_wait_frames,
    evaluate_clean_start_series,
    parse_clean_start_campaign,
    parse_clean_start_outcome,
)
from pokemon_red_completion.collection_protocol import (
    BATTLE_PLAN_ROSTER_SCHEMA,
    BATTLE_START_MAX_OFFSET_FRAMES,
    BATTLE_START_SCHEDULE_DERIVATION,
    BATTLE_START_SCHEDULE_SCHEMA,
    BattleStartSchedule,
    collection_document_sha256,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _schedule() -> BattleStartSchedule:
    roster_sha256 = collection_document_sha256(
        {
            "battle_plan_ids": list(RED_BATTLE_PLAN_IDS),
            "schema": BATTLE_PLAN_ROSTER_SCHEMA,
        }
    )
    return BattleStartSchedule(
        battle_plan_ids=RED_BATTLE_PLAN_IDS,
        battle_roster_sha256=roster_sha256,
        derivation=BATTLE_START_SCHEDULE_DERIVATION,
        max_offset_frames=BATTLE_START_MAX_OFFSET_FRAMES,
        schema=BATTLE_START_SCHEDULE_SCHEMA,
    )


def _execution() -> CleanStartExecutionIdentity:
    return CleanStartExecutionIdentity(
        source_commit="1" * 40,
        source_bundle_sha256="2" * 64,
        source_published=True,
        worktree_dirty=False,
        rom_sha1="3" * 40,
        rom_sha256="4" * 64,
        python_version="3.11.13",
        emulator_name="PyBoy",
        emulator_version="2.7.0",
        objective_graph_sha256="5" * 64,
        configuration_sha256="6" * 64,
        models=tuple(
            ModelArtifactIdentity(role, hashlib.sha256(role.encode("ascii")).hexdigest())
            for role in REQUIRED_MODEL_ROLES
        ),
    )


def _campaign_bytes() -> bytes:
    return build_clean_start_campaign(
        campaign_id="red-learned-clean-v1",
        recorded_on="2026-08-08",
        execution=_execution(),
        harness_seeds=tuple(range(2_000_001, 2_000_011)),
        schedule=_schedule(),
    )


def _campaign() -> CleanStartCampaign:
    return parse_clean_start_campaign(_campaign_bytes())


def _outcome_document(
    campaign: CleanStartCampaign,
    run_id: str,
    *,
    success: bool = True,
) -> dict[str, object]:
    assignment = campaign.assignment(run_id)
    run = assignment.run
    return {
        "assistance": {name: 0 for name in ASSISTANCE_COUNTERS},
        "authority": {
            "component_decisions": {name: 1 for name in REQUIRED_MODEL_ROLES},
            "fixed_dispatch_decisions": 0,
            "learned_choice_decisions": 36,
            "objective_dispatch_mode": "model_selected_specialists",
        },
        "campaign_id": campaign.campaign_id,
        "completion": {
            "champion_defeated": success,
            "checkpoints": 312 if success else 100,
            "hall_of_fame_entered": success,
            "objectives": 36 if success else 12,
        },
        "execution_sha256": assignment.execution_sha256,
        "private_report_sha256": "a" * 64,
        "registry_sha256": campaign.registry_sha256,
        "root": {
            "assignment_id": assignment.assignment_id,
            "ordinal": run.ordinal,
            "run_id": run.run_id,
        },
        "runtime": {
            "actions": 500_000,
            "battle_schedule_sha256": run.battle_schedule_sha256,
            "controller_released": True,
            "frames": 40_000_000,
            "human_input": False,
            "initial_wait_frames": run.initial_wait_frames,
            "save_state_loaded": False,
            "started_from_clean_power": True,
            "wall_time_seconds": 1_200.0,
        },
        "schema": CLEAN_START_OUTCOME_SCHEMA,
        "status": "complete" if success else "failed",
        "terminal_reason": "hall_of_fame_verified" if success else "battle_loss",
    }


def _outcome(
    campaign: CleanStartCampaign,
    run_id: str,
    *,
    success: bool = True,
):
    return parse_clean_start_outcome(
        _canonical(_outcome_document(campaign, run_id, success=success))
    )


def test_campaign_is_canonical_source_model_and_ten_root_bound() -> None:
    payload = _campaign_bytes()
    campaign = parse_clean_start_campaign(payload)

    assert payload == _canonical(json.loads(payload))
    assert campaign.registry_sha256 == hashlib.sha256(payload).hexdigest()
    assert campaign.execution.execution_sha256 == collection_document_sha256(
        campaign.execution.public_dict()
    )
    assert len(campaign.runs) == 10
    assert len({run.harness_seed for run in campaign.runs}) == 10
    assert len({run.battle_schedule_sha256 for run in campaign.runs}) == 10
    assert tuple(run.ordinal for run in campaign.runs) == tuple(range(1, 11))
    assert all(
        run.initial_wait_frames == derive_initial_wait_frames(run.harness_seed)
        for run in campaign.runs
    )
    assignments = tuple(campaign.assignment(run.run_id) for run in campaign.runs)
    assert len({assignment.assignment_id for assignment in assignments}) == 10
    assert "/" not in payload.decode("ascii")


def test_campaign_rejects_mutation_noncanonical_json_and_duplicate_keys() -> None:
    document = json.loads(_campaign_bytes())
    document["runs"][0]["initial_wait_frames"] += 1
    with pytest.raises(CleanStartCampaignError, match="initial wait derivation"):
        parse_clean_start_campaign(_canonical(document))

    with pytest.raises(CleanStartCampaignError, match="not canonical JSON"):
        parse_clean_start_campaign(json.dumps(json.loads(_campaign_bytes()), indent=2).encode())

    with pytest.raises(CleanStartCampaignError, match="duplicate JSON keys"):
        parse_clean_start_campaign(b'{"schema":"one","schema":"two"}\n')


def test_campaign_requires_every_model_role_and_clean_published_source() -> None:
    execution = _execution()
    with pytest.raises(CleanStartCampaignError, match="model roles"):
        CleanStartExecutionIdentity(
            source_commit=execution.source_commit,
            source_bundle_sha256=execution.source_bundle_sha256,
            source_published=True,
            worktree_dirty=False,
            rom_sha1=execution.rom_sha1,
            rom_sha256=execution.rom_sha256,
            python_version=execution.python_version,
            emulator_name=execution.emulator_name,
            emulator_version=execution.emulator_version,
            objective_graph_sha256=execution.objective_graph_sha256,
            configuration_sha256=execution.configuration_sha256,
            models=execution.models[:-1],
        )
    with pytest.raises(CleanStartCampaignError, match="clean and published"):
        CleanStartExecutionIdentity(
            source_commit=execution.source_commit,
            source_bundle_sha256=execution.source_bundle_sha256,
            source_published=False,
            worktree_dirty=False,
            rom_sha1=execution.rom_sha1,
            rom_sha256=execution.rom_sha256,
            python_version=execution.python_version,
            emulator_name=execution.emulator_name,
            emulator_version=execution.emulator_version,
            objective_graph_sha256=execution.objective_graph_sha256,
            configuration_sha256=execution.configuration_sha256,
            models=execution.models,
        )


def test_independent_series_gate_passes_exactly_eight_valid_successes() -> None:
    campaign = _campaign()
    outcomes = tuple(
        _outcome(campaign, run.run_id, success=run.ordinal <= 8) for run in campaign.runs
    )

    result = evaluate_clean_start_series(campaign, outcomes)

    assert result.counts == {"success": 8, "failure": 2, "invalid": 0, "pending": 0}
    assert result.series_complete
    assert result.threshold_met
    assert result.promotion_eligible
    assert result.public_dict()["status"] == "passed"


def test_series_gate_rejects_seven_successes_missing_slots_and_identity_mismatch() -> None:
    campaign = _campaign()
    seven = tuple(
        _outcome(campaign, run.run_id, success=run.ordinal <= 7) for run in campaign.runs
    )
    failed = evaluate_clean_start_series(campaign, seven)
    assert failed.counts["success"] == 7
    assert failed.series_complete
    assert not failed.threshold_met

    incomplete = evaluate_clean_start_series(campaign, seven[:-1])
    assert incomplete.counts["pending"] == 1
    assert not incomplete.series_complete

    alien = _outcome_document(campaign, campaign.runs[0].run_id)
    alien["execution_sha256"] = "b" * 64
    invalid_outcome = parse_clean_start_outcome(_canonical(alien))
    invalid = evaluate_clean_start_series(campaign, (invalid_outcome, *seven[1:]))
    assert invalid.counts["invalid"] == 1
    assert not invalid.series_complete
    assert invalid.assessments[0].reasons == ("execution_identity_mismatch",)


@pytest.mark.parametrize(
    ("mutator", "reason"),
    (
        (
            lambda document: document["assistance"].__setitem__("teacher_queries", 1),
            "assistance_teacher_queries_nonzero",
        ),
        (
            lambda document: document["authority"].__setitem__("fixed_dispatch_decisions", 36),
            "fixed_objective_dispatch_present",
        ),
        (
            lambda document: document["authority"]["component_decisions"].__setitem__(
                "battle_move", 0
            ),
            "component_battle_move_had_no_authority",
        ),
        (
            lambda document: document["runtime"].__setitem__("save_state_loaded", True),
            "save_state_loaded",
        ),
    ),
)
def test_success_gate_fails_closed_on_assistance_or_missing_authority(mutator, reason) -> None:
    campaign = _campaign()
    document = _outcome_document(campaign, campaign.runs[0].run_id)
    mutator(document)
    outcome = parse_clean_start_outcome(_canonical(document))

    result = evaluate_clean_start_series(campaign, (outcome,))

    assert result.assessments[0].classification == "failure"
    assert reason in result.assessments[0].reasons


def test_checker_cli_writes_machine_readable_result_and_fails_before_threshold(
    tmp_path: Path,
) -> None:
    campaign = _campaign()
    campaign_path = tmp_path / "campaign.json"
    campaign_path.write_bytes(_campaign_bytes())
    outcome_path = tmp_path / "outcome.json"
    outcome_path.write_bytes(_canonical(_outcome_document(campaign, campaign.runs[0].run_id)))
    output_path = tmp_path / "series.json"

    process = subprocess.run(
        [
            sys.executable,
            "scripts/check_clean_start_series.py",
            "--campaign",
            str(campaign_path),
            "--outcome",
            str(outcome_path),
            "--out",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 1
    report = json.loads(output_path.read_text(encoding="ascii"))
    assert report["counts"] == {"failure": 0, "invalid": 0, "pending": 9, "success": 1}
    assert report["promotion_eligible"] is False
    assert report["status"] == "incomplete_or_invalid"


def test_outcome_rejects_unknown_fields_and_duplicate_run_evidence() -> None:
    campaign = _campaign()
    document = _outcome_document(campaign, campaign.runs[0].run_id)
    mutated = deepcopy(document)
    mutated["private_path"] = "/private/example"
    with pytest.raises(CleanStartCampaignError, match="fields are invalid"):
        parse_clean_start_outcome(_canonical(mutated))

    outcome = parse_clean_start_outcome(_canonical(document))
    with pytest.raises(CleanStartCampaignError, match="multiple outcomes"):
        evaluate_clean_start_series(campaign, (outcome, outcome))
