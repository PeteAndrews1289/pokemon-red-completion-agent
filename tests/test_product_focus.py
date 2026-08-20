from __future__ import annotations

import json
import runpy
import sys
from copy import deepcopy
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from product_focus import (  # noqa: E402
    DEFAULT_FOCUS_CONFIG,
    DEFAULT_FOCUS_DOCUMENT,
    ProductFocusError,
    canonical_focus_json,
    focus_progress_fraction,
    focus_scorecard,
    load_product_focus,
    render_product_focus_markdown,
    validate_product_focus_document,
)

CHECKER = runpy.run_path(str(SCRIPTS / "check_product_focus.py"))
CHECK_DOCS = runpy.run_path(str(SCRIPTS / "check_docs.py"))
DASHBOARD = runpy.run_path(str(SCRIPTS / "run_product_focus_dashboard.py"))
COMPOSITION_DESIGN = (
    PROJECT_ROOT / "docs/evidence/fresh-goal-manager-composition-design-v2-2026-08-17.json"
)
COMPOSITION_V1_FAILURE = (
    PROJECT_ROOT
    / "docs/evidence"
    / "fresh-goal-manager-composition-execution-qualification-v1-static-failure-2026-08-17.json"
)
COMPOSITION_V2_FAILURE = (
    PROJECT_ROOT
    / "docs/evidence"
    / "fresh-goal-manager-composition-execution-preflight-v2-failure-2026-08-17.json"
)
COMPOSITION_V3_DESIGN = (
    PROJECT_ROOT / "docs/evidence/fresh-goal-manager-composition-design-v3-2026-08-17.json"
)
COMPOSITION_V3_FAILURE = (
    PROJECT_ROOT
    / "docs/evidence"
    / "fresh-goal-manager-composition-execution-preflight-v3-failure-2026-08-17.json"
)
COMPOSITION_V4_DESIGN = (
    PROJECT_ROOT / "docs/evidence/fresh-goal-manager-composition-design-v4-2026-08-17.json"
)
PREFLIGHT_OBSERVABILITY = (
    PROJECT_ROOT / "docs/evidence/generic-fresh-root-preflight-observability-v1-2026-08-17.json"
)
FIRST_CAUSAL_FREEZE_FAILURE = (
    PROJECT_ROOT / "docs/evidence" / "first-causal-goal-outcome-freeze-failure-v1-2026-08-18.json"
)
FIRST_DEVELOP_TEAM_FREEZE_FAILURE = (
    PROJECT_ROOT
    / "docs/evidence"
    / "first-develop-team-causal-goal-outcome-freeze-failure-v1-2026-08-18.json"
)
CAUSAL_READINESS_MANIFEST_QUALIFICATION = (
    PROJECT_ROOT / "docs/evidence" / "causal-readiness-manifest-qualification-v1-2026-08-18.json"
)
CAUSAL_BOOTSTRAP_ORIGIN_QUALIFICATION = (
    PROJECT_ROOT / "docs/evidence" / "causal-bootstrap-origin-qualification-v1-2026-08-18.json"
)
ROOTLESS_DEPENDENCY_CAMPAIGN_RESULT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-campaign-result-v1-2026-08-20.json"
)
ROOTLESS_DEPENDENCY_FIT_RESULT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-fit-result-v1-2026-08-20.json"
)
ROOTLESS_DEPENDENCY_COMPARISON_PREFLIGHT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-comparison-preflight-v1-2026-08-20.json"
)
ROOTLESS_DEPENDENCY_COMPARISON_INTEGRITY_FAILURE = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-comparison-integrity-failure-v1-2026-08-20.json"
)
ROOTLESS_DEPENDENCY_EVALUATION_INTEGRITY_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-evaluation-integrity-qualification-v1-2026-08-20.json"
)
REPEATABLE_FOCUS_INVENTORY = (
    PROJECT_ROOT
    / "docs/evidence/repeatable-goal-manager-development-focus-inventory-v1-2026-08-18.json"
)
REPEATABLE_INFRASTRUCTURE_INVALID = (
    PROJECT_ROOT
    / "docs/evidence"
    / "repeatable-goal-manager-development-infrastructure-invalid-v1-2026-08-18.json"
)
REPEATABLE_PREFLIGHT_V2 = (
    PROJECT_ROOT
    / "docs/evidence"
    / "repeatable-goal-manager-development-preflight-v2-2026-08-18.json"
)
REPEATABLE_RESULT_V2 = (
    PROJECT_ROOT / "docs/evidence" / "repeatable-goal-manager-development-result-v2-2026-08-18.json"
)
REPEATABLE_OUTCOME_FIT_PLAN = (
    PROJECT_ROOT / "docs/evidence" / "repeatable-goal-manager-outcome-fit-plan-v1-2026-08-18.json"
)
REPEATABLE_OUTCOME_FIT_RESULT = (
    PROJECT_ROOT / "docs/evidence" / "repeatable-goal-manager-outcome-fit-result-v1-2026-08-18.json"
)
PAIRED_SCREEN_DESIGN = (
    PROJECT_ROOT
    / "docs/evidence"
    / "paired-red-goal-manager-outcome-screen-design-v1-2026-08-18.json"
)
PAIRED_EXECUTION_PREFLIGHT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "paired-red-goal-manager-execution-preflight-v1-2026-08-18.json"
)
PAIRED_SCREEN_RESULT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "paired-red-goal-manager-outcome-screen-result-v1-2026-08-18.json"
)
ACQUISITION_REPLANNING_DESIGN = (
    PROJECT_ROOT / "docs/evidence" / "acquisition-replanning-curriculum-design-v1-2026-08-18.json"
)
ACQUISITION_REPLANNING_CONTEXT_PLAN_BUILD = (
    PROJECT_ROOT / "docs/evidence" / "acquisition-replanning-context-plan-build-v1-2026-08-18.json"
)
ENCOUNTER_DEVELOPMENT_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "title-neutral-encounter-development-capability-v1-2026-08-18.json"
)
ENCOUNTER_DEVELOPMENT_EXECUTION_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-encounter-development-execution-qualification-v1-2026-08-18.json"
)
RESETTABLE_MULTIROOT_IMPLEMENTATION_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "resettable-goal-manager-multiroot-implementation-qualification-v1-2026-08-18.json"
)
RESETTABLE_MULTIROOT_CONTEXT_ROLLOVER_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "resettable-goal-manager-multiroot-context-rollover-qualification-v1-2026-08-18.json"
)
RESETTABLE_MULTIROOT_FREEZE_FAILURE = (
    PROJECT_ROOT
    / "docs/evidence"
    / "resettable-goal-manager-multiroot-freeze-failure-v1-2026-08-18.json"
)
COLLISION_POSTMORTEM = (
    PROJECT_ROOT / "docs/evidence/protocol-party-collision-postmortem-v1-2026-08-17.json"
)
COMPOSITION_CORE_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence/fresh-goal-manager-composition-core-qualification-v1-2026-08-17.json"
)


def _document() -> dict[str, object]:
    return json.loads(DEFAULT_FOCUS_CONFIG.read_text(encoding="ascii"))


def _active(document: dict[str, object]) -> dict[str, object]:
    lanes = document["lanes"]
    assert isinstance(lanes, list)
    active = [lane for lane in lanes if isinstance(lane, dict) and lane.get("status") == "active"]
    assert len(active) == 1
    return active[0]


def test_repeatable_focus_inventory_replaces_only_the_dead_story_stratum() -> None:
    receipt = json.loads(REPEATABLE_FOCUS_INVENTORY.read_text(encoding="ascii"))

    assert receipt["status"] == "action_free_inventory_complete_focus_correction_required"
    assert receipt["inventory"]["advance_story"]["eligible_multi_choice_roots"] == 0
    assert receipt["inventory"]["develop_team"] == {
        "eligible_multi_choice_roots": 6,
        "historically_open_roots": 6,
        "story_candidate_present_in_every_eligible_menu": True,
        "train_focus_roots": 6,
    }
    assert receipt["campaign_effect"] == {
        "campaign_plan_created": False,
        "focus_stratum_replaced": "advance_story",
        "replacement_focus_stratum": "develop_team",
        "root_lineages_frozen": 0,
        "trials_claimed": 0,
    }
    assert set(receipt["zero_effects"].values()) == {0}
    assert set(receipt["counter_treatment"].values()) == {0}


def test_tracked_focus_is_canonical_and_reports_evidence_backed_learning_progress() -> None:
    state = load_product_focus()

    assert DEFAULT_FOCUS_CONFIG.read_bytes() == canonical_focus_json(state.document)
    assert DEFAULT_FOCUS_DOCUMENT.read_text(encoding="utf-8") == (
        render_product_focus_markdown(state)
    )
    assert state.active_lane["id"] == "rootless-living-dex-dependency-fresh-evaluation-design-v2"
    assert state.active_lane["kind"] == "maintenance"
    assert state.active_lane["maintenance_unblocks"] == (
        "rootless-living-dex-dependency-fresh-evaluation-qualification-v2"
    )
    assert len(state.retired_lanes) == 34
    assert focus_progress_fraction(state) == 0.0
    assert focus_scorecard(state) == ()
    assert state.progress["outcome_questions"] == {"development": 15, "train": 30}
    assert state.progress["model_fits"] == 4
    assert state.progress["unseen_comparisons"] == 3
    assert state.progress["development_episode_attempts"] == 14
    assert state.progress["verified_outcome_examples"] == 4
    assert state.progress["verified_composition_episodes"] == 1
    assert state.progress["causal_train_examples"] == 0
    assert state.progress["synthetic_rootless_train_outcomes"] == 8
    assert state.progress["synthetic_rootless_atomic_goal_episodes"] == 8
    assert state.progress["synthetic_rootless_model_fits"] == 1
    assert state.progress["synthetic_rootless_unseen_comparisons"] == 0
    encoded = json.dumps(state.document, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_campaign_result_is_balanced_and_scoped() -> None:
    receipt = json.loads(ROOTLESS_DEPENDENCY_CAMPAIGN_RESULT.read_text(encoding="ascii"))

    assert receipt["status"] == (
        "eight_balanced_synthetic_train_outcomes_admitted_fit_not_started"
    )
    assert receipt["outcome"] == {
        "interrupted_outcomes": 0,
        "negative_outcomes": 4,
        "positive_outcomes": 4,
        "settled_outcomes": 8,
        "status": "admitted",
        "train_admission_record_sha256": (
            "acf32bb8e5a910ded570ec2f0aa686bf810b18f202c51cf9f1a12063abad9254"
        ),
        "train_dataset_sha256": (
            "8207eb89a430a5bbb6bca7bd960e000c728710fded2bceef027dd4179e385f37"
        ),
    }
    assert receipt["counter_treatment"]["synthetic_rootless_train_outcomes_added"] == 8
    assert (
        receipt["counter_treatment"]["synthetic_rootless_atomic_goal_episodes_added"] == 8
    )
    assert {
        value
        for key, value in receipt["counter_treatment"].items()
        if not key.startswith("synthetic_rootless_")
    } == {0}
    assert receipt["campaign"]["global_one_shot_identities_consumed"] == 12
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_fit_result_remains_counted_but_not_evaluation_evidence() -> None:
    receipt = json.loads(ROOTLESS_DEPENDENCY_FIT_RESULT.read_text(encoding="ascii"))

    assert receipt["status"] == "completed_train_only_fit_development_remains_sealed"
    assert receipt["fit"]["train_accuracy"] == 1.0
    assert receipt["fit"]["fitted_cross_entropy"] < receipt["fit"][
        "baseline_cross_entropy"
    ]
    assert receipt["counter_treatment"]["synthetic_rootless_model_fits_added"] == 1
    assert receipt["counter_treatment"]["historical_gameplay_model_fits_added"] == 0
    assert receipt["counter_treatment"]["synthetic_rootless_unseen_comparisons_added"] == 0
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_comparison_preflight_is_historical_and_unconsumed() -> None:
    receipt = json.loads(
        ROOTLESS_DEPENDENCY_COMPARISON_PREFLIGHT.read_text(encoding="ascii")
    )

    assert receipt["status"] == (
        "sealed_comparison_ready_development_remains_unopened"
    )
    assert receipt["preflight"] == {
        "claim_registry_access": "read_only",
        "comparison_identity_available": True,
        "comparison_identity_consumed": False,
        "development_commitments_authenticated": 4,
        "development_opening_payloads_disclosed_to_stage": 0,
        "status": "sealed_comparison_ready",
    }
    assert receipt["execution_manifest"]["operation"] == "preflight-compare"
    assert receipt["review"] == {
        "antigravity_post_result_verdict": "go_no_p0_or_p1_blocker",
        "antigravity_pre_execution_verdict": "go_no_p0_or_p1_blocker",
        "claude_available": False,
    }
    assert set(receipt["counter_treatment"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_integrity_failure_retires_fit_and_openings() -> None:
    receipt = json.loads(
        ROOTLESS_DEPENDENCY_COMPARISON_INTEGRITY_FAILURE.read_text(encoding="ascii")
    )

    assert receipt["status"] == (
        "integrity_audit_failed_comparison_not_run_old_fit_and_openings_retired"
    )
    assert receipt["audit"] == {
        "audit_private_inputs_opened": 0,
        "development_row_contents_published": 0,
        "distinct_development_opening_records_decoded_by_affected_inventory": 4,
        "loaded_fit_semantically_closed_to_manifest_pins": False,
        "scope": "public_source_and_public_receipts_only",
        "zero_disclosure_claim_valid": False,
    }
    assert receipt["comparison"]["execution_started"] is False
    assert receipt["comparison"]["identity_consumed"] is False
    assert receipt["comparison"]["identity_eligible"] is False
    assert receipt["comparison"]["comparison_result_published"] is False
    assert receipt["retirement"] == {
        "old_comparison_identity_eligible": False,
        "old_development_openings_reusable": False,
        "old_fit_evaluation_eligible": False,
        "old_fit_remains_counted": True,
        "old_fit_retry_allowed": False,
        "old_lane_retired": True,
        "old_model_reusable": False,
    }
    assert set(receipt["counter_treatment"].values()) == {0}
    assert receipt["boards_after"] == {
        "atomic_goal_episodes": 0,
        "causal_train_examples": 0,
        "development_v2": "14/4/0/1/1",
        "legacy": "30/15/4/3/0/0",
        "synthetic_rootless": "8/8/1/0",
    }
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_evaluation_integrity_is_public_only_and_counter_neutral() -> None:
    receipt = json.loads(
        ROOTLESS_DEPENDENCY_EVALUATION_INTEGRITY_QUALIFICATION.read_text(encoding="ascii")
    )

    assert receipt["status"] == "public_evaluation_integrity_boundary_published_and_qualified"
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32425750185,
        "source_commit": "c0f7894b222dcf44490915a7ae7ebeed664096ea",
    }
    metadata = receipt["qualification"]["metadata_only_inspector"]
    assert metadata["payload_files_opened_per_inspection"] == 0
    assert metadata["payload_files_read_per_inspection"] == 0
    assert metadata["payload_bytes_hashed_per_inspection"] == 0
    assert metadata["payload_bytes_decoded_per_inspection"] == 0
    assert metadata["declared_payload_integrity_reported_as_unverified"] is True
    assert set(receipt["qualification"]["fit_bundle_join"].values()) == {True}
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_acquisition_replanning_design_is_action_free_and_product_bounded() -> None:
    receipt = json.loads(ACQUISITION_REPLANNING_DESIGN.read_text(encoding="ascii"))

    assert receipt["status"] == (
        "design_frozen_existing_contexts_insufficient_capability_work_required"
    )
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32129847455,
        "source_commit": "96379e8074373c5a9ba981f171ee75aa7080ff4a",
    }
    design = receipt["design"]
    assert design["design_sha256"] == (
        "76c36119848a2bf68e084851816a258982c51299d66208c129acf8b0a88e5241"
    )
    assert design["behavior"]["planned_episodes"] == 16
    assert design["behavior"]["first_decision_is_model_prediction"] is False
    assert design["behavior"]["learned_choice_decisions_after_intervention"] == 1
    assert design["inventory"]["unused_roots"] == 4
    assert design["inventory"]["authenticated_post_acquisition_captures"] == 0
    assert design["evidence_gate"]["minimum_verified_distinct_goal_replans"] == 4
    assert design["evidence_gate"]["minimum_root_lineages_with_verified_replan"] == 3
    assert set(receipt["counter_treatment"].values()) == {0}


def test_acquisition_replanning_context_plan_build_is_mechanical_and_zero_effect() -> None:
    receipt = json.loads(ACQUISITION_REPLANNING_CONTEXT_PLAN_BUILD.read_text(encoding="ascii"))

    assert receipt["status"] == (
        "private_context_plan_built_campaign_freeze_and_preflight_required"
    )
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32141939995,
        "source_commit": "343cadf921af2b82e79c352163c18d54b3d72d78",
    }
    assert receipt["source_bindings"] == {
        "builder_sha256": ("918b6ea7aa0dff5fafe937cc2b0271a95316858c3ae3c03cc22e6b26301c08db"),
        "context_catalog_sha256": (
            "f913158ffc3fd9d9c9cfd89ee42abe819a9bc3139901df603a017182df6f3959"
        ),
        "source_bundle_sha256": (
            "d323ec89e92c34de160294e848aae08b5771c0d74701f9d189240dba4c693076"
        ),
        "source_profile_manifest_sha256": (
            "adf671bfb8780fb6470ad3b15fd7632f8cd3eed06e33dc308384d3701e5012a6"
        ),
    }
    assert receipt["build"] == {
        "completed_battles_per_development_dose": 4,
        "context_catalog_sha256": (
            "f913158ffc3fd9d9c9cfd89ee42abe819a9bc3139901df603a017182df6f3959"
        ),
        "contexts": 81,
        "excluded_used_acquisition_roots": 2,
        "extended_unused_acquisition_roots": 4,
        "output_plan_sha256": ("09af29ba008ea24e16be75b64a8ff91e69ee4b32abc767bf01a90f937d45ff51"),
        "profile_lineage_manifest_sha256": (
            "db660df20ffcadb8e1520f50861093dcc1cb7e1f8a24687fac44cf1350db6324"
        ),
        "profile_set_sha256": ("792a0b548f58f19937b54dd7c0aca795c2b8d4617647fb15f10fbf9846f16c02"),
        "source_profile_manifest_sha256": (
            "adf671bfb8780fb6470ad3b15fd7632f8cd3eed06e33dc308384d3701e5012a6"
        ),
    }
    assert set(receipt["zero_effects"].values()) == {0}
    assert set(receipt["counter_treatment"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_encounter_development_qualification_stops_before_gameplay() -> None:
    receipt = json.loads(ENCOUNTER_DEVELOPMENT_QUALIFICATION.read_text(encoding="ascii"))

    assert receipt["status"] == ("rom_free_capability_qualified_execution_integration_required")
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32132328658,
        "source_commit": "6d028ea2003a4520b93a47d0607f5af01f8969e4",
    }
    assert receipt["qualification"]["action_free_offer"] is True
    assert receipt["qualification"]["execution_integrated"] is False
    assert receipt["qualification"]["gameplay_authorized"] is False
    assert set(receipt["zero_effects"].values()) == {0}
    assert set(receipt["counter_treatment"].values()) == {0}


def test_red_encounter_development_execution_is_qualified_without_gameplay() -> None:
    receipt = json.loads(ENCOUNTER_DEVELOPMENT_EXECUTION_QUALIFICATION.read_text(encoding="ascii"))

    assert receipt["status"] == ("red_execution_binding_qualified_campaign_preflight_required")
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32135801933,
        "source_commit": "944fdc5b79aa240fb42084e47913f9446883e739",
    }
    binding = receipt["execution_binding"]
    assert binding["completed_battle_dose"] == 4
    assert binding["healing_trips_allowed"] == 0
    assert binding["travel_transitions_allowed"] == 0
    assert binding["hard_action_limiter_required"] is True
    assert binding["hard_frame_limiter_required"] is True
    assert binding["unsafe_or_fainted_party_admitted"] is False
    assert set(receipt["zero_effects"].values()) == {0}
    assert set(receipt["counter_treatment"].values()) == {0}


def test_resettable_multiroot_implementation_is_qualified_without_gameplay() -> None:
    receipt = json.loads(
        RESETTABLE_MULTIROOT_IMPLEMENTATION_QUALIFICATION.read_text(encoding="ascii")
    )

    assert receipt["status"] == (
        "published_implementation_qualified_action_free_freeze_and_preflight_required"
    )
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32163666327,
        "source_bundle_sha256": (
            "a55a35d54e943d3e35dd43f0ffaafd77685ba9a11e569be575b98057be8a2b17"
        ),
        "source_commit": "113aa605a298337fb362f2e0b7d56e5c755b7380",
        "worktree_dirty": False,
    }
    assert receipt["campaign_contract"]["train_roots"] == 4
    assert receipt["campaign_contract"]["development_roots"] == 2
    assert receipt["campaign_contract"]["maximum_decisions_per_reset"] == 1
    assert receipt["remaining_gate"] == {
        "campaign_plan_created": False,
        "campaign_plan_sha256": None,
        "campaign_preflight_passed": False,
        "claims_consumed": 0,
        "development_roots_frozen": 0,
        "next": (
            "Run one exact-head action-free freeze; if successful, run one exact-plan "
            "preflight and stop before execution."
        ),
        "train_roots_frozen": 0,
        "trials_frozen": 0,
    }
    assert set(receipt["zero_effects"].values()) == {0}
    assert set(receipt["counter_treatment"].values()) == {0}


def test_multiroot_context_rollover_is_exclusion_only_and_zero_effect() -> None:
    receipt = json.loads(
        RESETTABLE_MULTIROOT_CONTEXT_ROLLOVER_QUALIFICATION.read_text(encoding="ascii")
    )

    assert receipt["status"] == (
        "published_context_rollover_repair_qualified_actual_freeze_not_started"
    )
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32165489924,
        "source_bundle_sha256": (
            "a55a35d54e943d3e35dd43f0ffaafd77685ba9a11e569be575b98057be8a2b17"
        ),
        "source_commit": "2cb18bf2e72362dd405a2198414ce946790e1f5f",
        "worktree_dirty": False,
    }
    exclusion = receipt["historical_exclusion_contract"]
    assert exclusion["historical_data_consumed"] == [
        "root_lineage_id",
        "state_sha256",
        "envelope_sha256",
    ]
    assert exclusion["public_paired_runner_remains_strict"] is True
    assert receipt["readiness_history"]["root_inventory_attempts"] == 0
    assert receipt["readiness_history"]["root_inspections"] == 0
    assert set(receipt["zero_effects"].values()) == {0}
    assert set(receipt["counter_treatment"].values()) == {0}


def test_multiroot_freeze_failure_closes_lane_without_inferred_cause() -> None:
    receipt = json.loads(RESETTABLE_MULTIROOT_FREEZE_FAILURE.read_text(encoding="ascii"))

    assert receipt["status"] == "sole_action_free_freeze_failed_closed_campaign_retired"
    assert receipt["execution"] == {
        "campaign_plan_created": False,
        "effects_attested_by_runner": False,
        "failure_stage": "unexpected_failure",
        "process_running_after_return": False,
        "retry_allowed": False,
        "runner_status": "failed_closed",
    }
    assert set(receipt["counter_treatment"].values()) == {0}
    assert "does not identify" in receipt["claim_boundary"]["unsupported"]
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_paired_screen_design_is_action_free_and_nonpromoting() -> None:
    receipt = json.loads(PAIRED_SCREEN_DESIGN.read_text(encoding="ascii"))

    assert receipt["status"] == "design_frozen_action_free_execution_not_implemented"
    assert receipt["root_admission"]["development_outcome_unused"] is True
    assert receipt["root_admission"]["guard_only_exposure_allowed"] is True
    assert receipt["root_admission"]["initial_available_goal_count"] == 3
    assert receipt["paired_contract"]["maximum_decisions_per_arm"] == 3
    assert receipt["paired_contract"]["primary_endpoint"] == "safe_retained_acquisition"
    assert receipt["paired_contract"]["adjudication_results"] == [
        "win",
        "loss",
        "tie",
        "uninterpretable",
    ]
    assert receipt["paired_contract"]["unseen_comparison"] is False
    assert receipt["paired_contract"]["promotion_authorized"] is False
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}


def test_paired_execution_preflight_is_zero_action_and_unclaimed() -> None:
    receipt = json.loads(PAIRED_EXECUTION_PREFLIGHT.read_text(encoding="ascii"))

    assert receipt["status"] == "paired_execution_ready_without_prediction_or_action"
    assert receipt["execution_qualification"]["pair_identity_available"] is True
    assert receipt["execution_qualification"]["arm_identities_available"] == 2
    assert receipt["execution_qualification"]["hard_maximum_decisions_per_arm"] == 3
    assert receipt["execution_qualification"]["strict_offline_admission_implemented"] is True
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}


def test_paired_screen_result_is_a_tie_without_composition_or_promotion() -> None:
    receipt = json.loads(PAIRED_SCREEN_RESULT.read_text(encoding="ascii"))

    assert receipt["adjudication"]["result"] == "tie"
    assert receipt["adjudication"]["base_safe_retained_acquisition"] is True
    assert receipt["adjudication"]["candidate_safe_retained_acquisition"] is True
    assert [arm["composition"] for arm in receipt["arms"]] == [False, False]
    assert [arm["verified_outcomes"] for arm in receipt["arms"]] == [1, 1]
    assert receipt["counter_treatment"]["development_episode_attempts_added"] == 2
    assert receipt["counter_treatment"]["verified_outcome_examples_added"] == 2
    assert receipt["counter_treatment"]["verified_composition_episodes_added"] == 0
    assert receipt["counter_treatment"]["authority_promotions_added"] == 0


def test_repeatable_infrastructure_invalid_is_retired_without_learning_output() -> None:
    receipt = json.loads(REPEATABLE_INFRASTRUCTURE_INVALID.read_text(encoding="ascii"))

    assert receipt["status"] == "old_campaign_durably_retired_repair_published"
    assert receipt["campaign_retirement"]["infrastructure_invalid_claims"] == 1
    assert receipt["campaign_retirement"]["retired_unexecuted_trials"] == 11
    assert receipt["campaign_retirement"]["failed_root_closed_account_wide"] is True
    assert receipt["failure"]["recorded_decisions"] == 0
    assert receipt["failure"]["recorded_outcomes"] == 0
    assert set(receipt["zero_effects"].values()) == {0}


def test_repeatable_replacement_preflight_is_ready_without_learning_output() -> None:
    receipt = json.loads(REPEATABLE_PREFLIGHT_V2.read_text(encoding="ascii"))

    assert receipt["status"] == "training_ready"
    assert receipt["campaign"]["available_trials"] == 12
    assert receipt["campaign"]["failed_v1_root_absent"] is True
    contract = receipt["next_execution_contract"]
    assert contract["second_predecision_protocol_failure_closes_architecture"] is True
    assert set(receipt["zero_effects"].values()) == {0}
    assert set(receipt["counter_treatment"].values()) == {0}


def test_repeatable_result_and_fit_plan_keep_the_diagnostic_boundary() -> None:
    result = json.loads(REPEATABLE_RESULT_V2.read_text(encoding="ascii"))
    plan = json.loads(REPEATABLE_OUTCOME_FIT_PLAN.read_text(encoding="ascii"))

    assert result["fixed_denominator"]["planned_trials"] == 12
    assert result["fixed_denominator"]["complete_episodes"] == 1
    assert result["fixed_denominator"]["invalid_trials"] == 11
    assert result["admitted_evidence"]["verified_outcomes"] == 2
    assert result["admitted_evidence"]["verified_composition_episodes"] == 1
    assert result["admitted_evidence"]["successful_retained_acquisitions"] == 0
    assert result["nonadmitted_diagnostics"]["use_as_fit_targets"] is False
    assert plan["eligible_targets"] == 2
    assert plan["one_shot"]["claim_before_target_decode"] is True
    assert plan["data_boundary"]["failed_artifact_target_decode"] == 0
    assert plan["claim_boundary"]["unsupported"].endswith("living-Pokedex ability.")


def test_outcome_fit_result_records_one_shadow_update_without_promotion() -> None:
    result = json.loads(REPEATABLE_OUTCOME_FIT_RESULT.read_text(encoding="ascii"))

    assert result["status"] == "diagnostic_candidate_fit_complete"
    assert result["training_data"] == {
        "complete_episodes": 1,
        "eligible_targets": 2,
        "excluded_failed_prefix_choices": 19,
        "failed_artifact_targets_decoded": 0,
        "independent_roots": 1,
        "negative_targets": 0,
        "positive_targets": 2,
        "test_examples": 0,
        "validation_examples": 0,
    }
    assert result["update"]["training_loss_after"] < result["update"]["training_loss_before"]
    assert result["guards"]["protected_winner_flips"] == 0
    assert result["guards"]["maximum_train_menu_kl"] < 0.01
    assert result["counter_treatment"]["model_fits_added"] == 1
    assert result["model"]["promotion_authorized"] is False
    assert result["evaluation"] is None


def test_collision_result_and_next_composition_design_preserve_the_product_boundary() -> None:
    collision = json.loads(COLLISION_POSTMORTEM.read_text(encoding="ascii"))
    design = json.loads(COMPOSITION_DESIGN.read_text(encoding="ascii"))

    result = collision["result"]
    assert result["contradictory_pairwise_relationships"] == 28
    assert result["exact_raw_semantic_conflicting_relationships"] == 28
    assert result["exact_projected_conflicting_relationships"] == 28
    assert result["classification_cluster_counts"] == {
        "frozen_projection_compression": 0,
        "raw_semantics_aliased_or_outcome_instability": 6,
        "tolerance_only_projected_near_collision": 0,
    }
    assert collision["counter_treatment"] == {
        "authority_promotions_added": 0,
        "model_fits_added": 0,
        "outcome_questions_added": 0,
        "transfer_results_added": 0,
        "unseen_comparisons_added": 0,
    }

    assert design["implementation_status"] == (
        "v2_contract_frozen_runner_under_review_no_root_access_no_execution"
    )
    assert design["bounds"]["decisions"] == 3
    assert design["admission"]["prediction_before_root_freeze"] is False
    assert design["pass_rule"]["available_goal_minimum_each_decision"] == 2
    assert design["pass_rule"]["selected_goal_kinds_exact"] == [
        "acquire_species",
        "explore",
        "restore_team",
    ]
    assert design["pass_rule"]["required_retained_specimens_acquired_minimum"] == 1
    assert design["pass_rule"]["available_menu_changes_minimum"] == 1
    assert design["execution_prerequisites"]["root_safe_runner_required"] is True
    assert design["authority"]["teacher_fallback_allowed"] is False
    assert design["authority"]["confidence_floor"] == 0.8

    v1_failure = json.loads(COMPOSITION_V1_FAILURE.read_text(encoding="ascii"))
    assert v1_failure["decision"]["status"] == "close_v1_before_root_access"
    assert v1_failure["failure"]["status"] == "static_contract_impossibility"
    assert v1_failure["zero_effects"]["roots_inspected"] == 0
    assert v1_failure["zero_effects"]["model_predictions"] == 0
    assert v1_failure["zero_effects"]["controller_actions"] == 0

    core = json.loads(COMPOSITION_CORE_QUALIFICATION.read_text(encoding="ascii"))
    assert core["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32076494276,
        "source_commit": "c4d8c7294a4c68ce0b9c506cf978a389c88a222f",
    }
    assert core["zero_effects"]["roots_admitted"] == 0
    assert core["zero_effects"]["model_predictions"] == 0
    assert core["zero_effects"]["controller_actions"] == 0
    assert not any(core["remaining_execution_prerequisites"].values())


def test_failed_v2_preflight_closes_only_the_root_and_no_learning_counter() -> None:
    receipt = json.loads(COMPOSITION_V2_FAILURE.read_text(encoding="ascii"))

    assert receipt["status"] == "zero_action_preflight_failed_no_execution_root_closed"
    assert receipt["failure"]["admission_completed"] == "not_attested"
    assert receipt["failure"]["runner_success_preflight_receipt_emitted"] is False
    assert receipt["failure"]["root_closed"] is True
    assert receipt["root_disposition"]["fixed_account_root_closure_recorded"] is True
    assert receipt["root_disposition"]["retry_allowed"] is False
    assert receipt["root_disposition"]["execution_identity_authorized"] is False
    assert set(receipt["zero_effects"].values()) == {0}
    assert set(receipt["counter_treatment"].values()) == {0}


def test_observability_result_and_v3_design_preserve_the_training_boundary() -> None:
    observability = json.loads(PREFLIGHT_OBSERVABILITY.read_text(encoding="ascii"))
    design = json.loads(COMPOSITION_V3_DESIGN.read_text(encoding="ascii"))

    assert observability["status"] == "complete_published_green_no_root_access"
    assert observability["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32089092868,
        "source_commit": "af04830fa51cc624a3047822d9fa582163444bea",
    }
    assert observability["implementation"]["allowlisted_failure_stages"] == [
        "action_free_admission",
        "execution_authorization",
        "readiness_authentication",
        "success_receipt_construction",
    ]
    assert set(observability["counter_treatment"].values()) == {0}
    assert set(observability["zero_effects"].values()) == {0}

    assert design["schema"] == "pokemon.red.fresh-goal-manager-composition-design.v3"
    assert design["admission"]["closed_v2_root_allowed"] is False
    assert design["admission"]["fixed_account_collision_check_before_private_input_read"] is True
    assert design["admission"]["required_initial_available_goal_kinds"] == [
        "acquire_species",
        "explore",
        "restore_team",
    ]
    assert design["episode_contract"]["selected_goal_kinds_exact"] == [
        "acquire_species",
        "explore",
        "restore_team",
    ]
    assert design["zero_effects_before_preflight"]["new_root_inspections"] == 0


def test_v3_failure_and_v4_design_preserve_the_training_boundary() -> None:
    failure = json.loads(COMPOSITION_V3_FAILURE.read_text(encoding="ascii"))
    design = json.loads(COMPOSITION_V4_DESIGN.read_text(encoding="ascii"))

    assert failure["status"] == (
        "zero_action_preflight_failed_at_action_free_admission_root_closed"
    )
    assert failure["failure"] == {
        "admission_completed": False,
        "failed_gate": "action_free_admission",
        "root_closed": True,
        "runner_success_preflight_receipt_emitted": False,
        "sanitized_failure_receipt_emitted": True,
    }
    assert failure["root_disposition"]["fixed_account_root_closure_recorded"] is True
    assert failure["root_disposition"]["retry_allowed"] is False
    assert failure["root_disposition"]["execution_identity_authorized"] is False
    assert set(failure["zero_effects"].values()) == {0}
    assert set(failure["counter_treatment"].values()) == {0}

    assert design["schema"] == "pokemon.red.fresh-goal-manager-composition-design.v4"
    assert design["admission"]["closed_v2_or_v3_root_allowed"] is False
    assert design["admission"]["required_initial_available_goal_kinds"] == [
        "advance_story",
        "manage_storage",
        "restore_team",
    ]
    assert design["admission"]["historical_preflight_role"] == (
        "authenticate_origin_capture_and_root_lineage_only"
    )
    assert design["binding_freeze"] == {
        "cross_source_historical_binding_equality_required": False,
        "current_published_source_binding_manifest_frozen_by_action_free_admission": True,
        "execution_identity_binds_current_binding_manifest": True,
        "rationale": (
            "Historical binding bytes authenticate an older executable and are not the "
            "execution contract for a new published runner. V4 authenticates root origin "
            "and lineage historically, then freezes the exact current-source menu before "
            "prediction."
        ),
    }
    assert design["episode_contract"]["selected_goal_kinds_exact"] == [
        "advance_story",
        "manage_storage",
        "restore_team",
    ]
    assert design["episode_contract"]["specimen_multiset_preserved_exactly"] is True
    assert design["episode_contract"]["required_storage_headroom_gain_minimum"] == 1
    assert design["episode_contract"]["teacher_queries"] == 0
    assert design["episode_contract"]["teacher_fallbacks"] == 0
    assert design["zero_effects_before_preflight"]["new_root_inspections"] == 0


def test_checker_binds_discovery_docs_and_pull_request_mission_check() -> None:
    rows = CHECKER["check_product_focus"]()

    assert rows == ()


def test_existing_ci_documentation_gate_invokes_the_focus_checker() -> None:
    main = CHECK_DOCS["main"]
    calls = 0

    def checked() -> tuple[str, ...]:
        nonlocal calls
        calls += 1
        return ()

    original = main.__globals__["check_product_focus"]
    main.__globals__["check_product_focus"] = checked
    try:
        assert main() == 0
    finally:
        main.__globals__["check_product_focus"] = original

    assert calls == 1


def test_focus_requires_exactly_one_active_lane() -> None:
    document = _document()
    lanes = document["lanes"]
    assert isinstance(lanes, list)
    retired = lanes[1]
    assert isinstance(retired, dict)
    retired["status"] = "active"

    with pytest.raises(ProductFocusError, match="fields|exactly one"):
        validate_product_focus_document(document)


def test_learning_lane_requires_a_complete_legacy_or_development_contract() -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "learning"
    lane["maintenance_unblocks"] = None
    lane["measurable_outputs"] = [
        {"kind": "outcome_question", "minimum": 1, "partition": "train"},
        {"kind": "unseen_comparison", "minimum": 1, "partition": "development"},
    ]

    with pytest.raises(ProductFocusError, match="legacy fit/evaluation outputs"):
        validate_product_focus_document(document)


def test_learning_lane_accepts_honest_model_led_development_outputs() -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "learning"
    lane["maintenance_unblocks"] = None
    lane["measurable_outputs"] = [
        {"kind": "development_episode", "minimum": 12, "partition": "development"},
        {
            "kind": "verified_outcome_example",
            "minimum": 12,
            "partition": "development",
        },
        {
            "kind": "verified_composition_episode",
            "minimum": 2,
            "partition": "development",
        },
    ]

    state = validate_product_focus_document(document)

    assert focus_scorecard(state) == (
        ("Development Episode · development", 14, 12),
        ("Verified Outcome Example · development", 4, 12),
        ("Verified Composition Episode · development", 1, 2),
    )


def test_learning_lane_accepts_one_honest_causal_train_example() -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "learning"
    lane["maintenance_unblocks"] = None
    lane["measurable_outputs"] = [
        {"kind": "causal_train_example", "minimum": 1, "partition": "train"}
    ]
    state = validate_product_focus_document(document)

    assert focus_scorecard(state) == (("Causal Train Example · train", 0, 1),)


def test_causal_train_example_cannot_be_mislabeled_as_development() -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "learning"
    lane["maintenance_unblocks"] = None
    lane["measurable_outputs"] = [
        {"kind": "causal_train_example", "minimum": 1, "partition": "train"}
    ]
    outputs = lane["measurable_outputs"]
    assert isinstance(outputs, list)
    output = outputs[0]
    assert isinstance(output, dict)
    output["partition"] = "development"

    with pytest.raises(ProductFocusError, match="causal train example must use"):
        validate_product_focus_document(document)


def test_learning_lane_accepts_paired_synthetic_rootless_outputs() -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "learning"
    lane["maintenance_unblocks"] = None
    lane["measurable_outputs"] = [
        {
            "kind": "synthetic_rootless_train_outcome",
            "minimum": 8,
            "partition": "train",
        },
        {
            "kind": "synthetic_rootless_atomic_goal_episode",
            "minimum": 8,
            "partition": "train",
        },
    ]

    state = validate_product_focus_document(document)

    assert focus_scorecard(state) == (
        ("Synthetic Rootless Train Outcome · train", 8, 8),
        ("Synthetic Rootless Atomic Goal Episode · train", 8, 8),
    )


def test_learning_lanes_accept_scoped_rootless_fit_and_comparison() -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "learning"
    lane["maintenance_unblocks"] = None
    lane["measurable_outputs"] = [
        {"kind": "synthetic_rootless_model_fit", "minimum": 1, "partition": "train"}
    ]

    state = validate_product_focus_document(document)

    assert focus_scorecard(state) == (("Synthetic Rootless Model Fit · train", 1, 1),)

    lane["measurable_outputs"] = [
        {
            "kind": "synthetic_rootless_unseen_comparison",
            "minimum": 1,
            "partition": "development",
        }
    ]
    state = validate_product_focus_document(document)
    assert focus_scorecard(state) == (
        ("Synthetic Rootless Unseen Comparison · development", 0, 1),
    )


@pytest.mark.parametrize(
    ("kind", "partition", "match"),
    (
        ("synthetic_rootless_model_fit", "development", "synthetic rootless output"),
        (
            "synthetic_rootless_unseen_comparison",
            "train",
            "synthetic rootless unseen comparison",
        ),
    ),
)
def test_scoped_rootless_fit_and_comparison_require_honest_partitions(
    kind: str,
    partition: str,
    match: str,
) -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "learning"
    lane["maintenance_unblocks"] = None
    lane["measurable_outputs"] = [
        {"kind": kind, "minimum": 1, "partition": partition}
    ]

    with pytest.raises(ProductFocusError, match=match):
        validate_product_focus_document(document)


@pytest.mark.parametrize("mutation", ("missing_pair", "wrong_partition", "unequal_minimum"))
def test_synthetic_rootless_outputs_cannot_inflate_gameplay_counters(mutation: str) -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "learning"
    lane["maintenance_unblocks"] = None
    outputs = [
        {
            "kind": "synthetic_rootless_train_outcome",
            "minimum": 8,
            "partition": "train",
        },
        {
            "kind": "synthetic_rootless_atomic_goal_episode",
            "minimum": 8,
            "partition": "train",
        },
    ]
    lane["measurable_outputs"] = outputs
    if mutation == "missing_pair":
        outputs.pop()
    elif mutation == "wrong_partition":
        outputs[0]["partition"] = "development"
    else:
        outputs[1]["minimum"] = 7

    with pytest.raises(ProductFocusError):
        validate_product_focus_document(document)


def test_maintenance_must_name_the_learning_experiment_it_unblocks() -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "maintenance"
    lane["maintenance_unblocks"] = None
    lane["measurable_outputs"] = []

    with pytest.raises(ProductFocusError, match="must name the learning lane"):
        validate_product_focus_document(document)


def test_development_cannot_silently_open_a_protected_action() -> None:
    document = _document()
    lane = _active(document)
    lane["rigor"] = "development"
    prohibited = lane["prohibited_actions"]
    assert isinstance(prohibited, list)
    prohibited.remove("full_game_replay")

    with pytest.raises(ProductFocusError, match="protected-action prohibition"):
        validate_product_focus_document(document)


@pytest.mark.parametrize(
    ("section", "key", "value", "match"),
    (
        ("alarms", "maximum_sessions_without_measured_learning_output", 2, "one session"),
        ("alarms", "maximum_full_replays_during_active_lane", 1, "full replay"),
        ("session_budget_percent", "maintenance_and_docs", 30, "sum to 100"),
    ),
)
def test_focus_rejects_weakened_alarms_or_learning_budget(
    section: str,
    key: str,
    value: object,
    match: str,
) -> None:
    document = _document()
    target = document[section]
    assert isinstance(target, dict)
    target[key] = value

    with pytest.raises(ProductFocusError, match=match):
        validate_product_focus_document(document)


def test_nonzero_progress_requires_a_tracked_path_free_evidence_file() -> None:
    document = _document()
    lane = _active(document)
    progress = lane["progress"]
    assert isinstance(progress, dict)
    outcomes = progress["outcome_questions"]
    assert isinstance(outcomes, dict)
    outcomes["train"] = 1
    progress["evidence"] = []

    with pytest.raises(ProductFocusError, match="requires tracked evidence"):
        validate_product_focus_document(document)


def test_latest_reorientation_can_bind_noncounting_qualification_evidence() -> None:
    document = _document()
    lane = _active(document)
    reorientation = lane["latest_reorientation"]
    assert isinstance(reorientation, dict)
    reorientation["evidence"] = {
        "kind": "qualification",
        "path": "docs/evidence/example-qualification.json",
        "sha256": "e" * 64,
    }

    validate_product_focus_document(document)

    evidence = reorientation["evidence"]
    assert isinstance(evidence, dict)
    evidence["path"] = "../private.json"

    with pytest.raises(ProductFocusError, match="reorientation evidence path is unsafe"):
        validate_product_focus_document(document)


def test_loader_rejects_duplicate_keys_and_noncanonical_bytes(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_bytes(b'{"schema":"a","schema":"b"}\n')
    with pytest.raises(ProductFocusError, match="invalid JSON"):
        load_product_focus(duplicate, project_root=tmp_path)

    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(json.dumps(_document()), encoding="ascii")
    with pytest.raises(ProductFocusError, match="not canonical"):
        load_product_focus(noncanonical, project_root=tmp_path)


def test_contract_is_title_neutral_enough_for_a_later_game_lane() -> None:
    document = deepcopy(_document())
    lane = _active(document)
    lane["id"] = "repeatable-party-transfer-learning-v1"
    lane["name"] = "Repeatable party transfer learning"
    lane["capability"] = "Choose portable party actions in an unseen title."
    lane["cheapest_falsifier"] = "Compare transferred and zero-initialized policies."
    lane["transfer_test"] = "Evaluate the same semantic contract in a later title."
    lane["next_decision"] = "Decide whether the shared representation transfers."

    state = validate_product_focus_document(document)

    assert state.active_lane["id"] == "repeatable-party-transfer-learning-v1"


def test_focus_dashboard_is_view_only_and_does_not_overclaim_training() -> None:
    state = load_product_focus()
    snapshot = DASHBOARD["product_focus_dashboard_snapshot"](state)
    public = snapshot.public_dict()

    assert public["run_status"] == "waiting"
    assert public["stage_progress"] == 0.0
    assert public["actions"] == 0
    assert "Fresh rootless living-Dex evaluation design V2" in public["stage"]
    assert public["experiment"]["zero_shot"] == {"completed": 8, "total": 8}  # type: ignore[index]
    assert public["experiment"]["adaptation"] == {"completed": 1, "total": 1}  # type: ignore[index]
    assert public["experiment"]["sealed_test"] == {"completed": 0, "total": 0}  # type: ignore[index]
    encoded = json.dumps(public, sort_keys=True)
    assert "Evaluation integrity is qualified" in encoded
    assert "actions 244/244" in encoded
    assert "V1 retired" in encoded
    assert "V2 public design only" in encoded
    assert "payload files opened 0" in encoded
    assert "exact fit join" in encoded
    assert "fit 1 counted/evaluation-ineligible" in encoded
    assert "comparisons 0" in encoded
    assert "Rootless board" in encoded
    assert "logical atomic 0" in encoded
    assert "6077173" in encoded
    assert "32177113545/1" in encoded
    assert "d77d9f9d" in encoded
    assert "aa65504" in encoded
    assert "32179177930/1" in encoded
    assert "preloads 0" in encoded
    assert "readiness_authentication" in encoded
    assert "effects not attested" in encoded
    assert "retry 0" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_develop_team_freeze_failure_is_path_free_and_closes_the_exact_lane() -> None:
    receipt = json.loads(FIRST_DEVELOP_TEAM_FREEZE_FAILURE.read_text(encoding="ascii"))

    assert receipt["schema"] == (
        "pokemon.red.first-develop-team-causal-goal-outcome-freeze-failure-receipt.v1"
    )
    assert receipt["source_verification"] == {
        "github_ci_attempt": 1,
        "github_ci_conclusion": "success",
        "github_ci_run": 32177113545,
        "source_commit": "6077173618bf9fce9fb57804a6a1ce82249c9cee",
        "worktree_dirty_before_execution": False,
    }
    assert receipt["observed_failure_envelope"] == {
        "development_labels_opened": 0,
        "effects": "not_attested_on_failure",
        "failure_stage": "readiness_authentication",
        "invocation_model_fits": 0,
        "private_path_fields": 0,
        "schema": "pokemon.red.develop-team-causal-goal-outcome-failure.v1",
        "status": "failed_closed",
        "teacher_queries": 0,
    }
    assert receipt["execution"]["retry_allowed"] is False
    assert receipt["execution"]["effects_attested_by_runner"] is False
    assert receipt["execution"]["campaign_plan_present_after_return"] is False
    assert receipt["public_source_postmortem"]["historical_effects_upgraded"] is False
    assert set(receipt["counter_treatment"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_first_causal_freeze_failure_is_path_free_and_does_not_attest_effects() -> None:
    receipt = json.loads(FIRST_CAUSAL_FREEZE_FAILURE.read_text(encoding="ascii"))

    assert receipt["schema"] == ("pokemon.red.first-causal-goal-outcome-freeze-failure-receipt.v1")
    assert receipt["source_verification"] == {
        "github_ci_attempt": 1,
        "github_ci_conclusion": "success",
        "github_ci_run": 32171116652,
        "source_commit": "61f9b44b7dadcbe8e70bcd641f8d532ed2c8337a",
        "worktree_dirty_before_execution": False,
    }
    assert receipt["execution"] == {
        "campaign_plan_created": False,
        "effects_attested_by_runner": False,
        "failure_stage": "readiness_authentication",
        "historical_failure_cause": "not_attested",
        "process_running_after_return": False,
        "retry_allowed": False,
        "runner_status": "failed_closed",
    }
    assert receipt["public_invocation_audit"] == {
        "historical_cause_inference_allowed": False,
        "manual_expected_paired_runner_binding_matched_published_bytes": False,
        "purpose": (
            "Record a public invocation inconsistency for future tooling without upgrading the "
            "runner's non-attested historical failure envelope."
        ),
    }
    assert set(receipt["counter_treatment"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_causal_readiness_manifest_qualification_is_public_only_and_zero_effect() -> None:
    receipt = json.loads(CAUSAL_READINESS_MANIFEST_QUALIFICATION.read_text(encoding="ascii"))

    assert receipt["schema"] == ("pokemon.core.causal-readiness-manifest-qualification-receipt.v1")
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32174872005,
        "source_commit": "ece32d81a1bd7ad3de037ba14361ef2f00849e35",
    }
    assert receipt["qualification"]["focused_tests_passed"] == 24
    assert receipt["qualification"]["future_lane_manifest_frozen"] is False
    assert receipt["qualification"]["future_lane_private_readiness_authorized"] is False
    assert receipt["qualification"]["retired_lane_and_runner_rejected"] is True
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_causal_bootstrap_origin_qualification_is_public_only_and_zero_effect() -> None:
    receipt = json.loads(CAUSAL_BOOTSTRAP_ORIGIN_QUALIFICATION.read_text(encoding="ascii"))

    assert receipt["schema"] == ("pokemon.core.causal-bootstrap-origin-qualification-receipt.v1")
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32179177930,
        "source_commit": "aa65504899f51cf73aa28bfdb725abffeeec7d0a",
    }
    qualification = receipt["qualification"]
    assert qualification["preloaded_project_modules"] == 0
    assert qualification["development_bootstrap_loaded_first"] is True
    assert qualification["isolated_process_origin_guard_passed"] is True
    assert qualification["retired_lane_changed_or_retried"] is False
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_focus_dashboard_uses_a_separate_local_port() -> None:
    args = DASHBOARD["_parser"]().parse_args(["--no-browser", "--duration-seconds", "1"])

    assert args.port == 8768
    assert args.no_browser is True
    assert args.duration_seconds == 1
