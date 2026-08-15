from __future__ import annotations

import json
from pathlib import Path

from pokemon_red_completion.scenario_outcome_adapters import BATTLE_TURN_OBJECTIVE

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLAN_V1 = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-battle-learning-curve-plan-2026-08-14.json"
)
PLAN_V2 = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-battle-learning-curve-plan-v2-2026-08-14.json"
)
ATTEMPT_V1 = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-battle-learning-curve-v1-attempt-2026-08-14.json"
)
RESULT_V2 = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-battle-learning-curve-v2-result-2026-08-14.json"
)


def test_curve_plan_freezes_the_smallest_complete_prefix_design() -> None:
    payload = json.loads(PLAN_V2.read_text(encoding="utf-8"))

    assert payload["schema"] == "pokemon-red-battle-learning-curve-plan-v2"
    assert payload["status"] == "prospective_unmaterialized"
    assert payload["outcome_objective"]["objective_id"] == (
        BATTLE_TURN_OBJECTIVE.objective_id
    )
    assert payload["outcome_objective"]["objective_sha256"] == (
        BATTLE_TURN_OBJECTIVE.objective_sha256
    )
    assert payload["catalog"]["train_contexts"] == 4
    assert payload["catalog"]["development_contexts"] == 4
    assert payload["catalog"]["training_prefix_sizes"] == [1, 2, 4]
    assert payload["catalog"]["required_unique_root_lineages"] == 8
    assert payload["collection"]["replace_after_observing_opponent_or_outcome"] is False
    assert payload["collection"]["repartition_after_observing_outcome"] is False
    assert payload["collection"]["append_each_candidate_outcome_immediately"] is True
    assert payload["catalog"]["v1_development_contexts_reused"] is False
    assert payload["learner"]["restart_from_same_prior_at_each_prefix"] is True
    assert payload["evaluation"]["inferential_claim"] is False
    assert payload["evaluation"]["promotion_decision"] is False
    assert (
        payload["after_result"][
            "scale_or_stratify_battle_catalog_before_three_family_check"
        ]
        is False
    )
    assert set(payload["protected_access"].values()) == {0}
    assert payload["private_path_fields"] == 0


def test_curve_plan_does_not_embed_a_private_machine_location() -> None:
    encoded = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PLAN_V1, PLAN_V2, ATTEMPT_V1, RESULT_V2)
    )

    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "file://" not in encoded


def test_v1_attempt_records_the_stop_without_claiming_a_fit() -> None:
    payload = json.loads(ATTEMPT_V1.read_text(encoding="utf-8"))

    assert payload["status"] == "stopped_before_fit"
    assert payload["stop"]["fit_started"] is False
    assert payload["stop"]["model_written"] is False
    assert payload["audit_finding"]["development_catalog_reusable_for_future_evaluation"] is False
    assert set(payload["protected_access"].values()) == {0}


def test_v2_result_records_a_real_curve_without_claiming_improvement() -> None:
    payload = json.loads(RESULT_V2.read_text(encoding="utf-8"))

    assert payload["status"] == "descriptive_curve_complete_no_authority"
    assert payload["prospective_bindings"]["runner_executions"] == 1
    assert payload["catalog"]["unique_root_lineages"] == 8
    assert payload["catalog"]["future_unseen_evaluation_eligible"] is False
    assert payload["counterfactual_collection"]["candidate_outcomes"] == 32
    assert payload["counterfactual_collection"]["flat_contexts"] == 3
    assert payload["learning_curve"]["base_development_correct"] == 4
    assert [
        point["updated_development_correct"]
        for point in payload["learning_curve"]["points"]
    ] == [4, 4, 4]
    assert all(
        point["paired_updated_wins"] == 0
        and point["paired_prior_wins"] == 0
        and point["paired_equivalent_choices"] == 4
        for point in payload["learning_curve"]["points"]
    )
    assert payload["decision"]["training_pipeline_validated"] is True
    assert payload["decision"]["battle_generalization_improvement_demonstrated"] is False
    assert payload["decision"]["authority_promoted"] is False
    assert set(payload["protected_access"].values()) == {0}
