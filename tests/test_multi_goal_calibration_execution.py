from __future__ import annotations

import json
from copy import deepcopy

import pytest

from pokemon_red_completion.goal_manager_composition_qualification import (
    root_consumption_sha256,
)
from pokemon_red_completion.multi_goal_calibration_execution import (
    CAMPAIGN_CONSUMPTION_SCHEMA,
    CAMPAIGN_SCHEMA,
    TRIAL_CLAIM_SCHEMA,
    MultiGoalCalibrationExecutionError,
    parse_multi_goal_calibration_campaign,
)
from pokemon_red_completion.multi_goal_calibration_plan import (
    MULTI_GOAL_CALIBRATION_SCHEDULE_SCHEMA,
)
from pokemon_red_completion.provenance import canonical_sha256


def _root(index: int, menu: list[str]) -> dict[str, object]:
    assignment = f"{index + 1:064x}"
    record: dict[str, object] = {
        "assignment_id": assignment,
        "available_goal_kinds": menu,
        "available_menu_sha256": f"{index + 11:064x}",
        "binding_manifest_sha256": f"{index + 21:064x}",
        "capture_id": f"red-goal-v1-{index:03d}",
        "entry_index": index,
        "envelope_file_sha256": f"{index + 31:064x}",
        "envelope_sha256": f"{index + 41:064x}",
        "focus_kind": menu[0],
        "policy_context_sha256": f"{index + 51:064x}",
        "profile_file_sha256": f"{index + 61:064x}",
        "question_sha256": f"{index + 71:064x}",
        "root_lineage_id": f"red-goal-root-{assignment}",
        "state_file_sha256": f"{index + 81:064x}",
        "state_sha256": f"{index + 91:064x}",
    }
    return {
        "partition": "train",
        "physical_root_sha256": root_consumption_sha256(
            state_sha256=record["state_sha256"],
            envelope_sha256=record["envelope_sha256"],
        ),
        "root": record,
    }


def _document() -> dict[str, object]:
    roots = [
        _root(0, ["develop_team", "advance_story"]),
        _root(1, ["evolve_species", "advance_story"]),
        _root(2, ["manage_storage", "advance_story"]),
        _root(3, ["manage_storage", "develop_team"]),
    ]
    bare_trials: list[dict[str, object]] = []
    for root_ordinal, root in enumerate(roots):
        record = root["root"]
        assert isinstance(record, dict)
        menu = record["available_goal_kinds"]
        assert isinstance(menu, list)
        for selected_candidate_index, selected_goal_kind in enumerate(menu):
            bare_trials.append(
                {
                    "maximum_decisions": 1,
                    "root_ordinal": root_ordinal,
                    "selected_candidate_index": selected_candidate_index,
                    "selected_goal_kind": selected_goal_kind,
                    "trial_ordinal": len(bare_trials),
                }
            )
    schedule_sha256 = canonical_sha256(
        {
            "root_slot_ids": [root["root"]["capture_id"] for root in roots],
            "schema": MULTI_GOAL_CALIBRATION_SCHEDULE_SCHEMA,
            "trials": bare_trials,
        }
    )
    identity: dict[str, object] = {
        "candidate": {"model_file_sha256": "a" * 64},
        "context_plan_sha256": "b" * 64,
        "development_runner_sha256": "c" * 64,
        "inventory_result_sha256": "d" * 64,
        "numpy_runtime_sha256": "e" * 64,
        "outcome_objective": "selected-semantic-option-multioutcome-calibration-v1",
        "private_root_identity_sha256": "f" * 64,
        "roots": roots,
        "runner_sha256": "1" * 64,
        "runtime_sha256": "2" * 64,
        "schedule_sha256": schedule_sha256,
        "schema": CAMPAIGN_SCHEMA,
        "skill_manifest_sha256": "4" * 64,
        "source_bundle_sha256": "5" * 64,
        "source_commit": "6" * 40,
        "trials": bare_trials,
    }
    campaign_id = canonical_sha256(identity)
    return {
        **identity,
        "campaign_id": campaign_id,
        "campaign_consumption_sha256": canonical_sha256(
            {"campaign_id": campaign_id, "schema": CAMPAIGN_CONSUMPTION_SCHEMA}
        ),
        "trials": [
            {
                **trial,
                "episode_id": (
                    f"red-multigoal-cal-{campaign_id[:32]}-{index:02d}"
                ),
                "trial_claim_sha256": canonical_sha256(
                    {
                        "campaign_id": campaign_id,
                        "schema": TRIAL_CLAIM_SCHEMA,
                        "trial_ordinal": index,
                    }
                ),
            }
            for index, trial in enumerate(bare_trials)
        ],
    }


def _payload(document: dict[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def test_parser_authenticates_campaign_and_execution_identities() -> None:
    campaign = parse_multi_goal_calibration_campaign(_payload(_document()))

    assert len(campaign.roots) == 4
    assert len(campaign.trials) == 8
    assert campaign.trials[2].selected_goal_kind.value == "evolve_species"
    assert campaign.root_reservation_execution_identity("7" * 64) != (
        campaign.trial_execution_identity(0, "7" * 64)
    )
    assert campaign.trial_execution_identity(0, "7" * 64) != (
        campaign.trial_execution_identity(1, "7" * 64)
    )


def test_parser_rejects_noncanonical_json() -> None:
    payload = json.dumps(_document(), indent=2).encode("ascii")

    with pytest.raises(MultiGoalCalibrationExecutionError, match="layout differs"):
        parse_multi_goal_calibration_campaign(payload)


def test_parser_rejects_a_mutated_trial() -> None:
    document = _document()
    trials = document["trials"]
    assert isinstance(trials, list)
    assert isinstance(trials[0], dict)
    trials[0]["selected_goal_kind"] = "advance_story"

    with pytest.raises(MultiGoalCalibrationExecutionError, match="identity differs"):
        parse_multi_goal_calibration_campaign(_payload(document))


def test_parser_rejects_duplicate_physical_roots() -> None:
    document = deepcopy(_document())
    roots = document["roots"]
    assert isinstance(roots, list)
    assert isinstance(roots[0], dict)
    assert isinstance(roots[1], dict)
    roots[1]["physical_root_sha256"] = roots[0]["physical_root_sha256"]

    with pytest.raises(MultiGoalCalibrationExecutionError, match="identity differs"):
        parse_multi_goal_calibration_campaign(_payload(document))


def test_parser_rejects_an_uncontrolled_safety_goal() -> None:
    document = _document()
    trials = document["trials"]
    roots = document["roots"]
    assert isinstance(trials, list) and isinstance(trials[0], dict)
    assert isinstance(roots, list) and isinstance(roots[0], dict)
    record = roots[0]["root"]
    assert isinstance(record, dict)
    menu = record["available_goal_kinds"]
    assert isinstance(menu, list)
    menu[0] = "restore_team"
    record["focus_kind"] = "restore_team"
    trials[0]["selected_goal_kind"] = "restore_team"

    with pytest.raises(MultiGoalCalibrationExecutionError, match="identity differs"):
        parse_multi_goal_calibration_campaign(_payload(document))
