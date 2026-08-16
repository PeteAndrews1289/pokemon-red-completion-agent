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
    / "red-cave-venue-measurement-plan-2026-08-15.json"
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


def test_cave_measurement_plan_rejects_a_semantic_mutation(tmp_path: Path) -> None:
    plan = red_cave_venue_measurement_plan_document()
    acceptance = plan["acceptance"]
    assert isinstance(acceptance, dict)
    acceptance["candidate_decisions"] = 1
    path = tmp_path / "mutated-plan.json"
    path.write_text(json.dumps(plan), encoding="ascii")

    with pytest.raises(RedCaveVenueMeasurementError, match="differs"):
        load_red_cave_venue_measurement_plan(path)
