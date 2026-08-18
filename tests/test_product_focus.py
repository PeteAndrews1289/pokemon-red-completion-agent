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
    assert state.active_lane["id"] == "goal-manager-acquisition-successor-learning-v1"
    assert state.active_lane["kind"] == "learning"
    assert len(state.retired_lanes) == 21
    assert focus_progress_fraction(state) == pytest.approx(14 / 15)
    assert focus_scorecard(state) == (
        ("Outcome Question · train", 30, 30),
        ("Model Fit · train", 4, 5),
        ("Unseen Comparison · development", 3, 3),
    )
    assert state.progress["outcome_questions"] == {"development": 15, "train": 30}
    assert state.progress["model_fits"] == 4
    assert state.progress["unseen_comparisons"] == 3
    assert state.progress["development_episode_attempts"] == 14
    assert state.progress["verified_outcome_examples"] == 4
    assert state.progress["verified_composition_episodes"] == 1
    encoded = json.dumps(state.document, sort_keys=True)
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

    assert rows == (
        "Outcome Question · train: 30/30",
        "Model Fit · train: 4/5",
        "Unseen Comparison · development: 3/3",
    )


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
    assert public["stage_progress"] == pytest.approx(14 / 15)
    assert public["actions"] == 0
    assert "Goal-manager acquisition successor learning V1" in public["stage"]
    assert public["experiment"]["zero_shot"] == {"completed": 30, "total": 30}  # type: ignore[index]
    assert public["experiment"]["adaptation"] == {"completed": 4, "total": 5}  # type: ignore[index]
    assert public["experiment"]["sealed_test"] == {"completed": 3, "total": 3}  # type: ignore[index]
    encoded = json.dumps(public, sort_keys=True)
    assert "Shadow successor from candidate eb5c6515" in encoded
    assert "loss 1.2667" in encoded
    assert "action_free_root_inventory" in encoded
    assert "fresh acquisition targets 1" in encoded
    assert "evaluation-only anchors 2" in encoded
    assert "actions 244/244" in encoded
    assert "8 resettable train episodes" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_focus_dashboard_uses_a_separate_local_port() -> None:
    args = DASHBOARD["_parser"]().parse_args(["--no-browser", "--duration-seconds", "1"])

    assert args.port == 8768
    assert args.no_browser is True
    assert args.duration_seconds == 1
