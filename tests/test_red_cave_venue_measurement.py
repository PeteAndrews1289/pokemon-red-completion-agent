from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion.red_cave_venue_measurement import (
    RED_CAVE_SUPPORT_CHECKPOINT_ID,
    RED_CAVE_SUPPORT_ROOT_LINEAGE_ID,
    RedCaveVenueMeasurementError,
    load_red_cave_venue_measurement_plan,
    red_cave_venue_binding_sha256,
    red_cave_venue_measurement_plan_document,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-venue-measurement-plan-v2-2026-08-15.json"
)
FAILURE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-cave-venue-measurement-failed-v1-2026-08-15.json"
)


def test_tracked_cave_measurement_plan_matches_its_source_contract() -> None:
    loaded, file_sha256 = load_red_cave_venue_measurement_plan(PLAN_PATH)

    assert loaded == red_cave_venue_measurement_plan_document()
    assert len(file_sha256) == 64
    assert loaded["status"] == "prospective_unexecuted"
    assert loaded["private_path_fields"] == 0
    encoded = json.dumps(loaded, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_cave_measurement_plan_is_single_venue_and_not_a_training_example() -> None:
    plan = red_cave_venue_measurement_plan_document()

    authenticated_root = plan["authenticated_root"]
    assert isinstance(authenticated_root, dict)
    assert (
        authenticated_root["root_lineage_id"]
        == RED_CAVE_SUPPORT_ROOT_LINEAGE_ID
    )
    assert (
        authenticated_root["root_lineage_id"]
        != RED_CAVE_SUPPORT_CHECKPOINT_ID
    )

    assert plan["venue"] == {
        "venue_binding_sha256": red_cave_venue_binding_sha256(),
        "single_fixed_venue": True,
        "candidate_menu_constructed": False,
        "venue_identity_exposed_to_model": False,
        "species_identity_exposed_to_model": False,
        "party_slot_exposed_to_model": False,
    }
    execution = plan["execution"]
    assert isinstance(execution, dict)
    assert execution["execute_exactly_once"] is True
    assert execution["retry_after_any_controller_input"] is False
    assert execution["teacher_queries"] == 0
    assert execution["model_predictions"] == 0
    assert execution["learner_outcomes_opened"] == 0
    interpretation = plan["interpretation"]
    assert isinstance(interpretation, dict)
    assert interpretation["training_example_created"] is False
    assert interpretation["authority_promotion"] is False
    assert interpretation["predecessor_v1_status"] == "failed_consumed_not_reusable"
    independence = plan["independence"]
    assert isinstance(independence, dict)
    assert independence["checkpoint_inventory_entry_count"] == 81
    assert independence["support_semantics_authenticated"] is True
    execution = plan["execution"]
    assert isinstance(execution, dict)
    assert execution["plan_record_durable_before_controller_entry"] is True
    assert execution["terminal_attempt_durable_after_controller_return"] is True
    assert execution["terminal_attempt_durable_before_acceptance"] is True
    assert execution["path_free_failure_durable_before_execution_abort"] is True
    assert execution["mid_controller_power_loss_can_end_with_plan_only"] is True
    assert execution["plan_or_finalization_io_failure_is_not_an_execution_abort"] is True


def test_cave_measurement_plan_rejects_a_semantic_mutation(tmp_path: Path) -> None:
    plan = red_cave_venue_measurement_plan_document()
    acceptance = plan["acceptance"]
    assert isinstance(acceptance, dict)
    acceptance["candidate_decisions"] = 1
    path = tmp_path / "mutated-plan.json"
    path.write_text(json.dumps(plan), encoding="ascii")

    with pytest.raises(RedCaveVenueMeasurementError, match="differs"):
        load_red_cave_venue_measurement_plan(path)


def test_v1_failure_receipt_is_path_free_and_cannot_claim_evidence() -> None:
    receipt = json.loads(FAILURE_PATH.read_text(encoding="ascii"))

    assert receipt["status"] == "failed_consumed"
    assert receipt["private_path_fields"] == 0
    assert receipt["artifact"]["measurement_records"] == 0
    assert receipt["artifact"]["terminal_attempt_records"] == 0
    assert receipt["interpretation"] == {
        "authority_promoted": False,
        "learner_outcomes_opened": 0,
        "measurement_accepted": False,
        "model_fit": False,
        "model_predictions": 0,
        "retry_or_root_copy_allowed": False,
        "teacher_queries": 0,
        "training_example_created": False,
        "v1_attempt_consumed": True,
        "venue_prior_entries_added": 0,
    }
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
