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
    _validate_battle_cycle_projection,
    _validate_calibration_player_partial_projection,
    _validate_calibration_player_recovery_projection,
    _validate_model106_measured_fishing_projection,
    _validate_model107_measured_fishing_failure_projection,
    _validate_model108_adaptive_fishing_projection,
    _validate_model112_automatic_fishing_failure_projection,
    _validate_model123_heterogeneous_evolution_fit_projection,
    _validate_paired_bounded_player_projection,
    _validate_repeatable_living_dex_calibration_audit_projection,
    _validate_repeatable_living_dex_first_two_projection,
    _validate_repeatable_living_dex_supplement_projection,
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


def test_current_dashboard_receipt_passes_the_real_native_training_boundary():
    # Validate the published pointer too, not just a hand-built dashboard fixture.
    # Support episodes must not replace the last fit's admitted episode binding.
    evidence = DASHBOARD["_load_learning_evidence"]()
    training, _ = DASHBOARD["_native_training_projection"](evidence)
    assert training.samples_after > 0
    if "latest_support_episode" in evidence:
        assert evidence["latest_support_episode"]["admitted_examples"] == 0
        assert evidence["latest_support_episode"]["sampled_choices"] == 0
        assert evidence["completed_episode"]["admitted_examples"] > 0


BATTLE_OUTCOME_CYCLE_RESULT = (
    PROJECT_ROOT / "docs/evidence/red-battle-outcome-cycle-v1-pair-01-result-2026-08-31.json"
)
PAIRED_BOUNDED_PLAYER_RESULT = (
    PROJECT_ROOT / "docs/evidence/red-paired-bounded-player-result-2026-09-03.json"
)
CALIBRATION_PLAYER_PARTIAL_RESULT = (
    PROJECT_ROOT / "docs/evidence/red-calibration-player-pair-005-partial-result-2026-09-04.json"
)
CALIBRATION_PLAYER_RECOVERY_RESULT = (
    PROJECT_ROOT / "docs/evidence/red-calibration-player-pair-006-result-2026-09-04.json"
)
REPEATABLE_LIVING_DEX_FIRST_TWO_RESULT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-repeatable-living-dex-development-first-two-results-v1-2026-09-05.json"
)
REPEATABLE_LIVING_DEX_SUPPLEMENT_RESULT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-repeatable-living-dex-development-supplement-results-v1-2026-09-05.json"
)
REPEATABLE_LIVING_DEX_CALIBRATION_AUDIT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-repeatable-living-dex-five-case-calibration-audit-v1-2026-09-05.json"
)
MODEL106_MEASURED_FISHING_RESULT = (
    PROJECT_ROOT / "docs/evidence/red-model106-measured-fishing-capture-2026-09-12.json"
)
MODEL107_MEASURED_FISHING_FAILURE = (
    PROJECT_ROOT / "docs/evidence/red-model107-measured-fishing-failure-2026-09-12.json"
)
MODEL108_ADAPTIVE_FISHING_LOOP = (
    PROJECT_ROOT / "docs/evidence/red-model108-adaptive-fishing-loop-2026-09-12.json"
)
MODEL112_AUTOMATIC_FISHING_FAILURE = (
    PROJECT_ROOT / "docs/evidence/red-model112-automatic-fishing-failure-learning-2026-09-13.json"
)
MODEL123_HETEROGENEOUS_EVOLUTION_FIT = (
    PROJECT_ROOT / "docs/evidence/red-model123-heterogeneous-evolution-fit-2026-09-15.json"
)
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
    PROJECT_ROOT / "docs/evidence" / "rootless-living-dex-dependency-fit-result-v1-2026-08-20.json"
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
ROOTLESS_DEPENDENCY_FRESH_EVALUATION_DESIGN_V2_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-fresh-evaluation-design-v2-qualification-2026-08-20.json"
)
ROOTLESS_DEPENDENCY_FRESH_EVALUATION_IMPLEMENTATION_V2_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / (
        "rootless-living-dex-dependency-fresh-evaluation-implementation-v2-qualification-"
        "2026-08-20.json"
    )
)
ROOTLESS_DEPENDENCY_V2_PRIVATE_PROVISION_RESULT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-v2-private-provision-result-2026-08-20.json"
)
ROOTLESS_DEPENDENCY_V2_COMPLIANCE_FIT_RESULT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-v2-compliance-fit-result-2026-08-20.json"
)
ROOTLESS_DEPENDENCY_V2_COMPARISON_PREFLIGHT_RESULT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-v2-comparison-preflight-result-2026-08-21.json"
)
ROOTLESS_DEPENDENCY_V2_COMPARISON_EXECUTION_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-v2-comparison-execution-qualification-2026-08-21.json"
)
ROOTLESS_DEPENDENCY_V2_COMPARISON_RESULT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "rootless-living-dex-dependency-v2-comparison-result-2026-08-21.json"
)
RED_DEPENDENCY_ADAPTER_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-dependency-observation-adapter-qualification-v1-2026-08-21.json"
)
RED_DEPENDENCY_SHADOW_DESIGN_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-dependency-shadow-decision-design-qualification-v1-2026-08-21.json"
)
RED_DEPENDENCY_SHADOW_RUNNER_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-dependency-shadow-runner-qualification-v1-2026-08-21.json"
)
RED_DEPENDENCY_SHADOW_PREFLIGHT_RESULT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-living-dex-dependency-shadow-preflight-result-v1-2026-08-21.json"
)
RED_DUAL_CAPABILITY_DESIGN_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-dual-capability-dependency-curriculum-design-qualification-v1-2026-08-21.json"
)
RED_DUAL_CAPABILITY_RUNTIME_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-dual-capability-curriculum-runtime-qualification-v1-2026-08-21.json"
)
RED_DUAL_CAPABILITY_PREFLIGHT_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-dual-capability-action-free-preflight-qualification-v1-2026-08-21.json"
)
RED_DUAL_CAPABILITY_PREFLIGHT_ANTIGRAVITY_AUDIT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-dual-capability-action-free-preflight-antigravity-audit-v1-2026-08-21.json"
)
RED_DUAL_CAPABILITY_PREFLIGHT_V1_FAILURE = (
    PROJECT_ROOT
    / "docs/evidence"
    / "red-dual-capability-action-free-preflight-v1-failure-2026-08-21.json"
)
TRACKED_PUBLIC_EVIDENCE_READER_QUALIFICATION = (
    PROJECT_ROOT
    / "docs/evidence"
    / "tracked-public-evidence-reader-qualification-v1-2026-08-21.json"
)
TRACKED_PUBLIC_EVIDENCE_READER_ANTIGRAVITY_AUDIT = (
    PROJECT_ROOT
    / "docs/evidence"
    / "tracked-public-evidence-reader-antigravity-audit-v1-2026-08-21.json"
)
RED_LIVING_DEX_OPTION_DEVELOPMENT_RESULT = (
    PROJECT_ROOT / "docs/evidence/red-living-dex-option-development-result-v1-2026-08-25.json"
)
ROOTLESS_DEPENDENCY_V2_PUBLIC_DESIGN = (
    PROJECT_ROOT / "configs/rootless-living-dex-dependency-evaluation-v2.json"
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


def test_tracked_focus_is_canonical_and_preserves_learning_during_scope_migration() -> None:
    state = load_product_focus()

    assert DEFAULT_FOCUS_CONFIG.read_bytes() == canonical_focus_json(state.document)
    assert DEFAULT_FOCUS_DOCUMENT.read_text(encoding="utf-8") == (
        render_product_focus_markdown(state)
    )
    # Scoped learning/reuse does not retire the lane or claim final autonomy.
    # Current learning is separate from the unchanged protected earned baseline.
    # Isolated packaging/startup does not imply a new fitted-model advantage.
    # The completed collection and all original diagnostic receipts stay closed.
    assert state.active_lane["time_box"] == {"maximum_hours": 3, "maximum_sessions": 1}
    assert state.active_lane["next_decision"].strip()
    reorientation = state.active_lane["latest_reorientation"]
    # The human-authorized seven-goal mission remains active after local repairs.
    assert reorientation["status"] == "active"
    assert reorientation["next_session_goal"].strip()
    assert reorientation["stop_condition"].strip()
    assert reorientation["decision"].strip()
    # Engineering qualification may support this learning lane without being
    # mislabeled as a newly executed or fitted learning episode.
    assert reorientation["evidence"]["kind"] in {"development_episode", "qualification"}
    latest = json.loads((PROJECT_ROOT / reorientation["evidence"]["path"]).read_bytes())
    if reorientation["evidence"]["kind"] == "qualification":
        assert latest["native_episode"] is False
        assert latest["fit_allowed"] is False
        assert latest["models_adopted"] == latest["new_fits"] == 0
    assert latest["session"] == reorientation["session_id"]
    assert latest["partition"] == "development"


def test_koga_fly_checkpoint_separates_comparative_choices_support_and_learning() -> None:
    evidence = json.loads(
        (PROJECT_ROOT / "docs/evidence/red-koga-fly-continuation-2026-10-13.json").read_bytes()
    )
    assert evidence["status"] == "closed_all_requested_outcomes_complete"
    assert evidence["partition"] == "development"
    assert evidence["worker_stopped"] and evidence["released"] and evidence["field_ready"]
    assert evidence["original_six_restored"] and evidence["whole_party_restored"]
    assert evidence["no_restart"] and not evidence["copied_progress_imported"]
    assert evidence["manual_actual_goal_substitutions"] == 0
    assert evidence["actual_model_comparative_choices"] == 58
    assert evidence["automatic_singleton_support"] == 46
    assert evidence["flat_outcomes"] == evidence["new_actual_costs"]["decisions"] == 104
    assert sum(evidence["goal_modes"].values()) == 104
    assert evidence["registrations_before"] == 64 and evidence["registrations_after"] == 71
    added = {s for row in evidence["new_registrations"] for s in row["species"]}
    assert len(added) == 7
    assert evidence["badges_before"] == 5 and evidence["badges_after"] == 6
    assert (
        evidence["cash_before"]
        + evidence["cash_rewards"]
        - evidence["new_actual_costs"]["cash_debits"]
        == evidence["cash_after"]
        == 460
    )
    assert evidence["native_execution_errors"] == []
    assert evidence["training_rows_added"] == evidence["fits"] == evidence["parameter_updates"] == 0
    assert evidence["goal_model_unchanged"] and evidence["runtime_llm_calls"] == 0
    assert (
        evidence["fly_obtained_and_taught"] and evidence["native_flight_verified_on_related_copy"]
    )
    assert evidence["actual_ancestry_flights"] == 0
    assert evidence["cold_proof"]["inputs"] == evidence["cold_proof"]["frames"] == 0
    assert evidence["final_fresh_completion_gates"] == "0/5"


def test_historical_isolated_package_keeps_original_acceptance_and_failures() -> None:
    # The October9 packet remains frozen evidence, not today's dispatch target.
    # Preserve every detailed assertion below against that original artifact.
    state = load_product_focus()
    latest = json.loads(
        (PROJECT_ROOT / "docs/evidence/red-isolated-player-package-2026-10-09.json").read_bytes()
    )
    assert latest["status"] == "closed_isolated_package_and_fresh_handoff_verified"
    assert latest["partition"] == "development" and not latest["independent_evaluation"]
    assert latest["model_examples"] == 151
    assert set(latest["learning"].values()) == {0}
    package = latest["package"]
    assert package["version"] == "v8" and package["frozen_files"] == 7158
    assert package["private_helper_files"] == 170 and package["private_data_inputs"] == 6231
    assert package["shared_environment_pins"] == 4512
    assert (
        package["private_data_bytes_unchanged"]
        and package["path_relocation_ast_equivalence_verified"]
    )
    assert package["mutable_checkout_imports"] == 0
    assert package["shared_environment_not_independently_distributed"]
    assert not package["untrusted_code_security_sandbox_claimed"]
    inspection = latest["inspection"]
    assert inspection["inputs"] == inspection["frames"] == 0
    assert inspection["menu_json_equal"] and inspection["choice_json_equal"]
    assert inspection["state_configuration_model_cost_search_and_party_equal"]
    assert inspection["ordered_mechanic_profiles_equal"]
    assert not inspection["raw_binding_refs_identical"]
    assert inspection["original_binding_refs_sha256"] != inspection["frozen_binding_refs_sha256"]
    outcome, rows = latest["outcome"], latest["native_rows"]
    assert outcome["fresh_power_on"] and outcome["one_live_emulator"]
    assert outcome["native_segments"] == 2
    assert outcome["goal_attempts"] == outcome["successful_verifications"] == len(rows) == 4
    assert outcome["model_selected"] == sum(row["model_selected"] for row in rows) == 3
    assert outcome["support_selected"] == sum(row["support_role"] is not None for row in rows) == 1
    assert all(row["verification"] == "succeeded" and row["error_type"] is None for row in rows)
    assert outcome["learned_battle_decisions"] == sum(row["battle_decisions"] for row in rows) == 8
    assert rows[0]["support_role"] == "forced_singleton" and rows[0]["battle_outcome"] == "won"
    assert outcome["pokedex_received"] and rows[1]["objective_completed"]
    assert not outcome["reach_pewter_completed"]
    assert all(not row["objective_completed"] for row in rows[2:])
    assert (
        outcome["costs"]["actions"]
        == outcome["startup_actions"] + sum(row["actions"] for row in rows)
        == 664
    )
    assert (
        outcome["costs"]["frames"]
        == outcome["startup_frames"] + sum(row["frames"] for row in rows)
        == 56005
    )
    assert outcome["state_loads"] == outcome["unexpected_execution_errors"] == 0
    assert (
        outcome["fresh_registrations"] == 1
        and outcome["stop_reason"] == "declared_budget_exhausted"
    )
    battle = latest["battle_log"]
    assert battle["complete"] and battle["events"] == 35
    assert battle["started_decisions"] == battle["completed_decisions"] == 8
    assert battle["incomplete_decisions"] == battle["failed_runs"] == 0
    assert battle["invalid_actions"] == battle["failed_move_executions"] == 0
    assert (
        battle["teacher_queries"] == battle["teacher_interventions"] == battle["memory_writes"] == 0
    )
    verification = latest["verification"]
    assert set(verification["readiness"].values()) == {True}
    assert verification["protected_pins_verified"] == 38
    assert verification["baseline_main_registrations"] == 32
    assert verification["completed_reference_registrations"] == 124
    assert (
        not verification["native_worker_running"] and verification["fresh_process_returncode"] == 0
    )
    assert verification["adapter_closed"] and verification["buttons_released"]
    attempts = latest["attempt_treatment"]
    assert (
        attempts["fresh_smoke_versions"] == [4, 5, 8]
        and attempts["accepted_readiness_version"] == 8
    )
    assert (
        attempts["version4_false_positive_original_retained"]
        and attempts["version5_partial_progress_retained"]
    )
    assert not attempts["failed_receipts_rewritten"]
    next_launch = latest["next_launch"]
    assert next_launch["prepared"] and not next_launch["claimed"] and not next_launch["launched"]
    assert (
        not next_launch["official_campaign_allowed"] and next_launch["partition"] == "development"
    )
    assert not latest["scope"]["development_fitting"] and latest["scope"]["runtime_llm_calls"] == 0
    assert latest["scope"]["save_edits"] == latest["scope"]["teacher_combat_decisions"] == 0
    assert not latest["scope"]["copy_back"] and not latest["scope"]["full_game_campaign_started"]
    assert latest["scope"]["fresh_red_gates_advanced"] == 0
    # Preserve the preceding durable recovery/capture proof, not overwrite it.
    latest = json.loads(
        (PROJECT_ROOT / "docs/evidence/red-durable-route-recovery-2026-10-09.json").read_bytes()
    )
    assert (
        latest["status"] == "closed_durable_quote_recovery_and_useful_dependency_capture_verified"
    )
    assert latest["partition"] == "development" and not latest["independent_evaluation"]
    assert latest["model_examples"] == 151
    assert set(latest["learning"].values()) == {0}
    engineering = latest["engineering"]
    assert engineering["version1_identity_preserved"] and engineering["version2_explicit_quote"]
    assert engineering["indoor_and_fly_quote_connected"]
    assert engineering["source_binding_before_import"] and engineering["loaded_source_path_checks"]
    assert engineering["private_source_files"] == 170
    assert engineering["private_source_basis"] == "conservative_static_import_superset"
    assert latest["configuration_sha256"] != latest["previous_configuration_sha256"]
    outcome, rows = latest["outcome"], latest["native_rows"]
    assert outcome["native_segments"] == 4
    assert outcome["goal_attempts"] == len(rows) == 8
    assert outcome["model_selected"] == sum(row["model_selected"] for row in rows) == 7
    assert outcome["support_selected"] == sum(row["support_role"] is not None for row in rows) == 1
    assert outcome["successful"] == sum(row["verification"] == "succeeded" for row in rows) == 7
    assert (
        outcome["intentional_interruptions"] == 1
        and outcome["unexpected_native_execution_errors"] == 0
    )
    interrupted = [row for row in rows if row["error_type"] is not None]
    assert len(interrupted) == 1
    assert interrupted[0]["kind"] == "restore_team" and interrupted[0]["model_selected"]
    assert interrupted[0]["error_type"] == "ControllerActionBudgetExhausted"
    assert (
        interrupted[0]["verification"] is None and interrupted[0]["observed_cost"]["actions"] == 1
    )
    assert outcome["registrations_before"] == outcome["registrations_after"] == 32
    assert outcome["registration_delta"] == 0 and outcome["physical_dependency_delta"] == 1
    capture = outcome["capture"]
    assert capture["model_selected"] and capture["verification"] == "succeeded"
    assert capture["new_registrations"] == []
    assert capture["physical_gloom_before"] == 1 and capture["physical_gloom_after"] == 2
    assert capture["capture_survey"]["captures"] == 1
    assert (
        outcome["costs"]["actions"] == sum(row["observed_cost"]["actions"] for row in rows) == 2419
    )
    assert (
        outcome["costs"]["frames"] == sum(row["observed_cost"]["frames"] for row in rows) == 127494
    )
    assert outcome["costs"]["decisions"] == 8 and outcome["costs"]["cash_debits"] == 1000
    terminal = latest["terminal"]
    assert terminal["exact_reload"] and terminal["reload_inputs"] == terminal["reload_frames"] == 0
    assert terminal["all_originals_active"] and terminal["whole_party_restored"]
    assert terminal["master_balls"] == 1 and terminal["search_memory_entries"] == 1
    assert terminal["earlier_search_history_unknown"]
    assert len(latest["inspections"]) == 5
    quotes = latest["inspections"][1]["quotes"]
    assert any(
        row["source_id"] == "wild:Route11:grass" and row["ordinary_trainers_crossed"] == 3
        for row in quotes
    )
    assert all(
        not row["enemy_rosters_used"]
        and not row["scripted_battles_quoted"]
        and not row["risk_is_probability"]
        for row in quotes
    )
    assert latest["verification"]["protected_pins_verified"] == 34
    assert latest["verification"]["baseline_main_registrations"] == 32
    assert latest["verification"]["completed_reference_registrations"] == 124
    assert not latest["verification"]["native_worker_running"]
    assert not latest["scope"]["development_fitting"] and latest["scope"]["runtime_llm_calls"] == 0
    assert latest["scope"]["save_edits"] == latest["scope"]["full_game_replays"] == 0
    assert not latest["scope"]["copy_back"] and latest["scope"]["fresh_red_gates_advanced"] == 0
    # Preserve the preceding rejected163 fit and native tie as historical evidence.
    latest = json.loads(
        (PROJECT_ROOT / "docs/evidence/red-route-combat-learning-2026-10-09.json").read_bytes()
    )
    assert (
        latest["status"] == "closed_route_information_useful_parameter_advantage_not_demonstrated"
    )
    learning = latest["learning"]
    assert (
        learning["parent_examples"] + learning["admitted_train_delta"]
        == learning["candidate_examples"]
        == 163
    )
    assert (
        learning["actual_train_attempts"]
        == learning["admitted_train_delta"] + learning["quarantined_train_attempts"]
        == 14
    )
    assert (
        learning["admitted_train_delta"]
        == sum(
            learning[key]
            for key in (
                "successful_admitted_captures",
                "successful_admitted_restorations",
                "failed_admitted_captures",
            )
        )
        == 12
    )
    assert learning["retained_all151_fingerprints"] and learning["fit_delta"] == 1
    assert (
        not learning["deployed"]
        and learning["adoption_delta"] == learning["authority_promotions"] == 0
    )
    assert learning["new_train_mse_after"] < learning["new_train_mse_before"]
    assert learning["actual_train_actions"] == sum(row["actions"] for row in latest["train_arms"])
    assert learning["actual_train_frames"] == sum(row["frames"] for row in latest["train_arms"])
    quote = latest["engineering"]["prospective_ordinary_sight_quote"]
    assert quote["wild:Route4:grass"]["ordinary_trainers_crossed"] == 0
    assert quote["wild:Route24:grass"]["ordinary_trainers_crossed"] == 6
    assert quote["wild:Route25:grass"]["ordinary_trainers_crossed"] == 5
    assert all(
        not row["enemy_rosters_used"]
        and not row["scripted_battles_quoted"]
        and not row["risk_is_probability"]
        for row in quote.values()
    )
    comparison = latest["comparison"]
    assert len(comparison["arms"]) == 4 and comparison["all_four_terminal_bytes_identical"]
    assert (
        comparison["all_four_choices_identical"]
        and comparison["all_four_action_frame_costs_identical"]
    )
    assert not comparison["accepted_model_improvement"]
    assert (
        comparison["successful_selected_capture_goals"] == 8
        and comparison["useful_capture_in_each_arm"]
    )
    assert comparison["unique_related_target_registrations"] == [21, 23]
    assert not comparison["partial_evolution_is_registration"]
    assert len({row["terminal_sha256"] for row in comparison["arms"]}) == 1
    for row in comparison["arms"]:
        assert row["source_unchanged"] and row["field_ready"] and row["buttons_released"]
        assert row["learned_battles"] == 0 and row["new_registrations"] == [21, 23]
        assert row["successful_selected_capture_goals"] == 2
        assert row["stop_reason"] == "verification_failed"
        assert row["costs"]["actions_attempted"] == 5356 and row["costs"]["frames"] == 355064
        partial = row["partial_evolution"]
        assert partial["evolution_partial"] and partial["completed_training_battles"] == 32
        xp = partial["retained_xp_and_level_changes"][0]["experience"]
        assert xp["after"] - xp["before"] == 2001
    assert latest["verification"]["protected_pins_verified"] == 29
    assert latest["verification"]["main_registrations"] == 32
    assert latest["verification"]["completed_registrations"] == 124
    assert not latest["verification"]["native_worker_running"]
    assert not latest["scope"]["development_fitting"] and latest["scope"]["runtime_llm_calls"] == 0
    # Preserve the preceding rejected162 batch as independent historical evidence.
    latest = json.loads(
        (
            PROJECT_ROOT / "docs/evidence/red-informative-collection-learning-2026-10-09.json"
        ).read_bytes()
    )
    assert latest["status"] == "closed_useful_choice_improvement_not_demonstrated"
    learning = latest["learning"]
    assert (
        learning["parent_examples"] + learning["admitted_train_delta"]
        == learning["candidate_examples"]
        == 162
    )
    assert (
        learning["actual_train_attempts"]
        == learning["admitted_train_delta"] + learning["quarantined_train_attempts"]
        == 16
    )
    assert (
        learning["admitted_train_delta"]
        == sum(
            learning[key]
            for key in (
                "successful_admitted_captures",
                "successful_admitted_restorations",
                "failed_admitted_captures",
            )
        )
        == 11
    )
    assert learning["retained_all151_fingerprints"] and learning["fit_delta"] == 1
    assert (
        not learning["deployed"]
        and learning["adoption_delta"] == learning["authority_promotions"] == 0
    )
    assert learning["new_train_mse_after"] < learning["new_train_mse_before"]
    assert learning["actual_train_actions"] == sum(row["actions"] for row in latest["train_arms"])
    assert learning["actual_train_frames"] == sum(row["frames"] for row in latest["train_arms"])
    comparison = latest["comparison"]
    assert len(comparison["arms"]) == 4 and comparison["all_four_terminal_bytes_identical"]
    assert not comparison["accepted_model_improvement"]
    assert comparison["successful_selected_capture_goals"] == 0
    assert not comparison["incidental_raticate_is_capture_success"]
    assert len({row["terminal_sha256"] for row in comparison["arms"]}) == 1
    for row in comparison["arms"]:
        assert row["source_unchanged"] and row["field_ready"] and row["buttons_released"]
        assert row["learned_battles"] == 7 and row["capture_attempts"] == 0
        assert row["capture_stop"] == "safety_check_failed"
    assert latest["verification"]["protected_pins_verified"] == 26
    assert latest["verification"]["main_registrations"] == 32
    assert latest["verification"]["completed_registrations"] == 124
    assert not latest["verification"]["native_worker_running"]
    assert not latest["scope"]["development_fitting"] and latest["scope"]["runtime_llm_calls"] == 0
    # Preserve the preceding zero-input instrumentation closure separately.
    diagnostic = json.loads(
        (PROJECT_ROOT / "docs/evidence/red-player-data-gap-completion-2026-10-09.json").read_bytes()
    )
    assert diagnostic["status"] == "closed_rom_free_observational_wiring_no_new_run"
    assert diagnostic["verification"][
        "recording_parity_in_fixture_choices_inputs_verdicts_and_costs"
    ]
    assert diagnostic["verification"]["action_free_menu_state_guard_preserved"]
    assert diagnostic["verification"]["protected_pins_verified"] == 21
    assert diagnostic["verification"]["protected_pin_mismatches"] == 0
    assert not diagnostic["verification"]["completed_terminal_changed"]
    assert not diagnostic["verification"]["protected_main_changed"]
    assert not diagnostic["verification"]["native_worker_running"]
    assert not diagnostic["scope"]["native_cartridge_qualification_this_session"]
    assert not diagnostic["scope"]["new_logging_subsystem"]
    assert not diagnostic["scope"]["new_policy_privileged_features"]
    assert diagnostic["learning"]["native_gameplay_inputs"] == 0
    assert diagnostic["learning"]["native_gameplay_frames"] == 0
    assert diagnostic["learning"]["registration_delta"] == 0
    assert diagnostic["learning"]["admitted_train_delta"] == 0
    assert diagnostic["learning"]["fit_delta"] == 0
    assert diagnostic["learning"]["model_adoption_delta"] == 0
    assert not diagnostic["learning"]["development_fitting"]
    assert diagnostic["retained_terminal"]["registrations"] == 124
    assert diagnostic["retained_terminal"]["model_examples"] == 151
    assert diagnostic["retained_terminal"]["protected_main_registrations"] == 32
    # Completed earned coverage is not fresh autonomous acceptance or training.
    # The prior eight-hour receipt stays historical and its costs remain carried.
    block = json.loads(
        (
            PROJECT_ROOT / "docs/evidence/red-earned-collection-completion-2026-10-09.json"
        ).read_bytes()
    )
    assert block["status"] == "closed_earned_native_collection_and_data_audit"
    assert block["partition"] == "development"
    assert block["correlated_continuation"] and not block["independent_evaluation"]
    assert not block["final_autonomy"]
    delta = block["registration_delta"]
    assert delta["total"] == delta["during_model_owned_goals"] + delta["during_singleton_support"]
    assert (
        block["source"]["initial_registrations"] + delta["total"]
        == block["terminal"]["registrations"]
    )
    assert (
        block["terminal"]["registrations"]
        + block["terminal"]["remaining_native_route_registrations"]
        == 124
    )
    assert block["terminal"]["registrations"] == 124
    combined = delta["combined_previous_and_current_blocks"]
    assert combined["total"] == 91
    assert combined["during_model_owned_goals"] + combined["during_singleton_support"] == 91
    assert delta["physical_poliwhirl_reacquisition"]["new_registrations"] == 0
    assert delta["physical_poliwhirl_reacquisition"]["physical_acquisitions"] == 1
    counts = block["outcomes"]
    assert counts["executed_goals"] == counts["model_owned_goals"] + counts["support_goals"]
    assert counts["executed_goals"] == sum(
        counts[key]
        for key in (
            "successes",
            "ordinary_failed_verifications",
            "other_failed_verifications",
            "execution_errors",
        )
    )
    assert counts["all_original_failures_and_costs_retained"]
    assert block["terminal"]["worker_stopped"] and block["terminal"]["controls_released"]
    assert block["verification"]["exact_terminal_reload_passed"]
    assert block["verification"]["reload_inputs"] == block["verification"]["reload_frames"] == 0
    assert not block["verification"]["protected_main_changed"]
    assert not block["verification"]["copy_back"]
    assert block["verification"]["all_four_physical_legendary_specimens"]
    assert block["verification"]["original_roster_retained_and_restored"]
    assert block["verification"]["protected_main_registrations"] == 32
    ancestry = block["verification"]["champion_hof_ancestry"]
    assert ancestry["authenticated_nodes"] == ancestry["verified_parent_links"] + 1 == 90
    assert ancestry["concurrent_champion_and_hall_of_fame"]
    assert ancestry["all_source_states_match_authenticated_parent"]
    assert ancestry["all_lifetime_costs_monotonic"]
    assert block["audit"]["combined_goal_outcomes"] == 434
    assert block["audit"]["current_acquisition_selected_arm"][
        "scores_are_not_calibrated_probabilities"
    ]
    assert block["learning"]["admitted_train_delta"] == block["learning"]["fit_delta"] == 0
    assert (
        block["learning"]["runtime_llm_calls"]
        == block["learning"]["official_authority_promotions"]
        == 0
    )
    assert not block["learning"]["development_fitting"]
    # Preserve the prior learning evidence rather than relabeling new gameplay.
    evidence = json.loads(
        (
            PROJECT_ROOT / "docs/evidence/red-checkpoint-recovery-learning-2026-10-08.json"
        ).read_bytes()
    )
    assert evidence["status"] == "closed_scoped_native_improvement_and_durable_development_reuse"
    assert evidence["checkpoint_inventory"]["count"] == 4
    assert evidence["checkpoint_inventory"]["zero_input_reloads"] == 4
    assert evidence["checkpoint_inventory"]["development_copies_are_train"] is False
    assert evidence["model"]["settled_examples"] == 151
    assert evidence["model"]["retained_prior_examples"] == 147
    assert evidence["model"]["retained_all_prior_fingerprints"] is True
    assert evidence["model"]["admitted_train_delta"] == 4
    assert evidence["model"]["fit_delta"] == 1
    assert evidence["model"]["battler_fit_delta"] == 0
    assert evidence["model"]["development_inputs"] == 0
    assert evidence["model"]["configured_development_artifact_selected"] is True
    assert evidence["model"]["protected_main_model_replaced"] is False
    assert evidence["model"]["official_authority_promotions"] == 0
    assert evidence["model"]["runtime_llm_calls"] == 0
    assert evidence["reserved_conditions"]["original_failures_preserved"] is True
    assert evidence["reserved_conditions"]["pure_paired_model_improvement_claim"] is False
    assert evidence["adaptive_early_continuation"]["useful_model_selected_captures"] == [16, 43]
    assert evidence["adaptive_early_continuation"]["original_comparison_stays_failed"] is True
    assert (
        evidence["adaptive_early_continuation"]["incidental_registration_is_capture_success"]
        is False
    )
    assert evidence["adaptive_early_continuation"]["worker_stopped"] is True
    copy = evidence["configured_development_copy"]
    assert (copy["initial_registrations"], copy["final_registrations"]) == (32, 33)
    assert copy["new_registrations"] == [78]
    assert copy["failed_partial_third_goal_preserved"] is True
    assert copy["zero_input_reloads"] == 2
    assert copy["reload_inputs"] == copy["reload_frames"] == 0
    assert copy["inherited_spent_retained"] and copy["original_roster_restored"]
    assert copy["worker_stopped"] and copy["copy_back"] is False
    assert evidence["protected_earned_save"]["registrations"] == 32
    assert evidence["protected_earned_save"]["registration_delta"] == 0
    assert evidence["protected_earned_save"]["unchanged"] is True
    assert evidence["protected_earned_save"]["copy_back"] is False
    # Preserve the preceding zero-fit diagnostic's exact historical claims.
    prior = json.loads(
        (PROJECT_ROOT / "docs/evidence/red-player-data-observability-2026-10-08.json").read_bytes()
    )
    assert prior["status"] == "closed_diagnostics_verified_native_capture_not_demonstrated"
    assert prior["model"]["settled_examples"] == 147
    assert prior["model"]["admitted_train_delta"] == prior["model"]["fit_delta"] == 0
    assert prior["diagnostic_episode"]["survey_captures"] == 0
    assert prior["diagnostic_episode"]["incidental_registration_is_capture_success"] is False
    # The earlier genuine TRAIN pilot remains historical evidence; diagnostics
    # must neither erase those lessons nor count them again as today's learning.
    evidence = json.loads(
        (
            PROJECT_ROOT / "docs/evidence/red-teacher-assisted-collection-2026-10-08.json"
        ).read_bytes()
    )
    assert evidence["status"] == "closed_native_improvement_not_demonstrated"
    assert evidence["learning"]["admitted_train_examples"] == 6
    assert evidence["learning"]["model_fits"] == 2
    assert evidence["learning"]["retained_prior_examples"] == 141
    assert evidence["learning"]["child_settled_examples"] == 147
    assert evidence["learning"]["retained_all_prior_row_hashes"] is True
    assert evidence["learning"]["deployed_models"] == 0
    assert evidence["learning"]["runtime_llm_calls"] == 0
    assert evidence["comparison"]["paired_improvement_accepted"] is False
    assert evidence["comparison"]["successful_selected_goal_arms"] == 0
    assert evidence["adaptive_execution_repair"]["new_registrations"] == 0
    assert evidence["adaptive_execution_repair"]["worker_stopped"] is True
    assert evidence["earned_save"]["registrations"] == 32
    assert evidence["earned_save"]["unchanged"] is True
    assert evidence["earned_save"]["copy_back"] is False
    assert "| Time box | 1 session / 3 hours |" in DEFAULT_FOCUS_DOCUMENT.read_text(
        encoding="utf-8"
    )
    assert state.active_lane["id"] == "cross-title-authenticated-scenario-curriculum-v1"
    assert state.active_lane["kind"] == "learning"
    assert state.active_lane["maintenance_unblocks"] is None
    prohibited = set(state.active_lane["prohibited_actions"])
    assert "unexecuted_counterfactual_target" in prohibited
    assert "unmeasured_action_target" in prohibited
    assert "counterfactual_target" not in prohibited
    assert "unselected_action_target" not in prohibited
    assert {"full_game_replay", "teacher_choice_or_fallback", "promotion_from_pilot"}.isdisjoint(
        prohibited
    )
    assert set(state.active_lane["development_permissions"].values()) == {True}
    assert state.active_lane["measurable_outputs"] == [
        {"kind": "registered_train_example", "minimum": 4, "partition": "train"},
        {"kind": "model_fit", "minimum": 1, "partition": "train"},
        {"kind": "unseen_comparison", "minimum": 1, "partition": "development"},
    ]
    assert len(state.retired_lanes) == 60
    # This legacy fraction is not pilot acceptance or full-product completion.
    # The unchanged historical counters exclude this pilot's new corpus.
    assert focus_progress_fraction(state) == 1.0
    assert focus_scorecard(state) == (
        ("Registered Train Example · train", 135, 4),
        ("Model Fit · train", 16, 1),
        ("Unseen Comparison · development", 9, 1),
    )
    rendered = render_product_focus_markdown(state)
    assert "### Historical cross-family counter snapshot" in rendered
    assert "Legacy minimum, not current acceptance" in rendered
    assert "excludes newer native-player batches" in rendered
    assert state.progress["outcome_questions"] == {"development": 61, "train": 103}
    assert state.progress["model_fits"] == 16
    assert state.progress["composition_attempts"] == 6
    assert state.progress["unseen_comparisons"] == 9
    assert state.progress["development_episode_attempts"] == 30
    assert state.progress["verified_outcome_examples"] == 67
    assert state.progress["verified_composition_episodes"] == 4
    assert state.progress["causal_train_examples"] == 112
    assert state.progress["synthetic_rootless_train_outcomes"] == 8
    assert state.progress["synthetic_rootless_atomic_goal_episodes"] == 8
    assert state.progress["synthetic_rootless_model_fits"] == 1
    assert state.progress["synthetic_rootless_unseen_comparisons"] == 1
    encoded = json.dumps(state.document, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


@pytest.mark.parametrize(
    "field",
    (
        "fitted_training_examples",
        "registered_species_after",
        "controller_actions_observed",
        "teacher_labels",
        "authority_promotions",
        "independent_evaluation",
        "durable_restart_published",
        "model_sha256",
    ),
)
def test_measured_fishing_projection_rejects_claim_drift(field: str) -> None:
    receipt = json.loads(MODEL106_MEASURED_FISHING_RESULT.read_text(encoding="ascii"))
    _validate_model106_measured_fishing_projection(receipt)

    changed = deepcopy(receipt)
    value = changed[field]
    changed[field] = not value if isinstance(value, bool) else 999
    with pytest.raises(ProductFocusError, match="measured fishing"):
        _validate_model106_measured_fishing_projection(changed)


@pytest.mark.parametrize(
    "field",
    (
        "fitted_training_examples",
        "registered_species_after",
        "failure_stage",
        "automatic_retry",
        "teacher_labels",
        "model_sha256",
    ),
)
def test_measured_fishing_failure_projection_rejects_claim_drift(field: str) -> None:
    receipt = json.loads(MODEL107_MEASURED_FISHING_FAILURE.read_text(encoding="ascii"))
    _validate_model107_measured_fishing_failure_projection(receipt)

    changed = deepcopy(receipt)
    value = changed[field]
    changed[field] = not value if isinstance(value, bool) else 999
    with pytest.raises(ProductFocusError, match="measured fishing failure"):
        _validate_model107_measured_fishing_failure_projection(changed)


def test_measured_fishing_failure_recovery_cannot_claim_learning() -> None:
    receipt = json.loads(MODEL107_MEASURED_FISHING_FAILURE.read_text(encoding="ascii"))
    changed = deepcopy(receipt)
    changed["recovery"]["training_examples"] = 1
    with pytest.raises(ProductFocusError, match="failure recovery"):
        _validate_model107_measured_fishing_failure_projection(changed)


@pytest.mark.parametrize(
    "field",
    (
        "fitted_training_examples",
        "selection_changed_after_failure",
        "registered_species_after",
        "controller_actions_observed",
        "teacher_labels",
        "independent_evaluation",
        "model_sha256",
    ),
)
def test_adaptive_fishing_projection_rejects_claim_drift(field: str) -> None:
    receipt = json.loads(MODEL108_ADAPTIVE_FISHING_LOOP.read_text(encoding="ascii"))
    _validate_model108_adaptive_fishing_projection(receipt)

    changed = deepcopy(receipt)
    value = changed[field]
    changed[field] = not value if isinstance(value, bool) else 999
    with pytest.raises(ProductFocusError, match="adaptive fishing"):
        _validate_model108_adaptive_fishing_projection(changed)


@pytest.mark.parametrize(
    ("section", "field"),
    (
        (None, "teacher_labels"),
        (None, "authority_promotions"),
        ("collection", "registered_species"),
        ("menu", "candidate_count"),
        ("menu", "second_policy_query"),
        ("execution", "controller_actions"),
        ("execution", "retry_allowed"),
        ("learning", "settled_examples"),
        ("learning", "independent_evaluation"),
        ("qualification", "github_ci_attempt"),
        ("recovery", "input_ready"),
        ("validation", "future_scripted_dialogue_budget"),
    ),
)
def test_automatic_fishing_failure_projection_rejects_claim_drift(
    section: str | None, field: str
) -> None:
    receipt = json.loads(MODEL112_AUTOMATIC_FISHING_FAILURE.read_text(encoding="ascii"))
    _validate_model112_automatic_fishing_failure_projection(receipt)

    changed = deepcopy(receipt)
    target = changed if section is None else changed[section]
    value = target[field]
    target[field] = not value if isinstance(value, bool) else 999
    with pytest.raises(ProductFocusError, match="automatic fishing failure"):
        _validate_model112_automatic_fishing_failure_projection(changed)


@pytest.mark.parametrize(
    ("section", "field"),
    (
        (None, "model_sha256"),
        ("fit", "settled_examples_after"),
        ("fit", "prior_rows_retained"),
        ("frozen_menu_replay", "selected_after_fit"),
        ("frozen_menu_replay", "support_decreased"),
        ("outcome", "registered_species_after"),
        ("outcome", "teacher_labels"),
        ("verifier_recovery", "fit_rerun"),
        ("verifier_recovery", "gameplay_replayed"),
    ),
)
def test_model123_heterogeneous_fit_projection_rejects_claim_drift(
    section: str | None, field: str
) -> None:
    receipt = json.loads(MODEL123_HETEROGENEOUS_EVOLUTION_FIT.read_text(encoding="ascii"))
    _validate_model123_heterogeneous_evolution_fit_projection(receipt)

    changed = deepcopy(receipt)
    target = changed if section is None else changed[section]
    value = target[field]
    target[field] = not value if isinstance(value, bool) else 999
    with pytest.raises(ProductFocusError, match="Model123"):
        _validate_model123_heterogeneous_evolution_fit_projection(changed)


def test_paired_player_projection_rejects_counter_or_arm_drift() -> None:
    receipt = json.loads(PAIRED_BOUNDED_PLAYER_RESULT.read_text(encoding="ascii"))

    _validate_paired_bounded_player_projection(receipt)
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_calibration_player_partial_projection_rejects_false_comparison() -> None:
    receipt = json.loads(CALIBRATION_PLAYER_PARTIAL_RESULT.read_text(encoding="ascii"))

    _validate_calibration_player_partial_projection(receipt)
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded

    changed = deepcopy(receipt)
    changed["comparison"]["paired_verdict"] = "learned_advantage"
    with pytest.raises(ProductFocusError, match="partial comparison"):
        _validate_calibration_player_partial_projection(changed)

    changed_counter = deepcopy(receipt)
    changed_counter["counter_treatment"]["development_episode_attempts_added"] = 2
    with pytest.raises(ProductFocusError, match="partial counters differ"):
        _validate_calibration_player_partial_projection(changed_counter)

    changed_arm = deepcopy(receipt)
    changed_arm["challenger_arm"]["frames"] = 4511
    with pytest.raises(ProductFocusError, match="partial arm differs"):
        _validate_calibration_player_partial_projection(changed_arm)


def test_calibration_player_recovery_projection_binds_progress_and_typed_stop() -> None:
    receipt = json.loads(CALIBRATION_PLAYER_RECOVERY_RESULT.read_text(encoding="ascii"))

    _validate_calibration_player_recovery_projection(receipt)
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded

    changed = deepcopy(receipt)
    changed["comparison"]["verdict"] = "learned_advantage"
    with pytest.raises(ProductFocusError, match="recovery comparison differs"):
        _validate_calibration_player_recovery_projection(changed)

    changed_counter = deepcopy(receipt)
    changed_counter["counter_treatment"]["authority_promotions_added"] = 1
    with pytest.raises(ProductFocusError, match="recovery counters differ"):
        _validate_calibration_player_recovery_projection(changed_counter)

    changed_arm = deepcopy(receipt)
    changed_arm["arms"]["calibration_model"]["decisions"][2]["failure_reason"] = None
    with pytest.raises(ProductFocusError, match="recovery decisions differ"):
        _validate_calibration_player_recovery_projection(changed_arm)


def test_repeatable_living_dex_first_two_projection_binds_both_outcomes() -> None:
    receipt = json.loads(REPEATABLE_LIVING_DEX_FIRST_TWO_RESULT.read_text(encoding="ascii"))

    _validate_repeatable_living_dex_first_two_projection(receipt)
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded

    changed_success = deepcopy(receipt)
    changed_success["cases"][0]["verified_success"] = False
    with pytest.raises(ProductFocusError, match="first result differs"):
        _validate_repeatable_living_dex_first_two_projection(changed_success)

    changed_failure = deepcopy(receipt)
    changed_failure["cases"][1]["completion_gain"] = 1.0
    with pytest.raises(ProductFocusError, match="second result differs"):
        _validate_repeatable_living_dex_first_two_projection(changed_failure)

    changed_counter = deepcopy(receipt)
    changed_counter["counter_treatment"]["composition_attempts_added"] = 2
    with pytest.raises(ProductFocusError, match="counters differ"):
        _validate_repeatable_living_dex_first_two_projection(changed_counter)


def test_repeatable_living_dex_supplement_projection_binds_three_outcomes() -> None:
    receipt = json.loads(REPEATABLE_LIVING_DEX_SUPPLEMENT_RESULT.read_text(encoding="ascii"))

    _validate_repeatable_living_dex_supplement_projection(receipt)
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded

    changed_acquisition = deepcopy(receipt)
    changed_acquisition["cases"][0]["living_collection_after"] = 13
    with pytest.raises(ProductFocusError, match="supplement cases differ"):
        _validate_repeatable_living_dex_supplement_projection(changed_acquisition)

    changed_calibration = deepcopy(receipt)
    changed_calibration["cases"][1]["predicted_verified_success"] = 1.0
    with pytest.raises(ProductFocusError, match="supplement cases differ"):
        _validate_repeatable_living_dex_supplement_projection(changed_calibration)

    changed_counter = deepcopy(receipt)
    changed_counter["counter_treatment"]["authority_promotions_added"] = 1
    with pytest.raises(ProductFocusError, match="supplement counters differ"):
        _validate_repeatable_living_dex_supplement_projection(changed_counter)


def test_repeatable_living_dex_calibration_audit_binds_metrics_and_boundary() -> None:
    receipt = json.loads(REPEATABLE_LIVING_DEX_CALIBRATION_AUDIT.read_text(encoding="ascii"))

    _validate_repeatable_living_dex_calibration_audit_projection(receipt)
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded

    changed_metric = deepcopy(receipt)
    changed_metric["diagnostic"]["overall"]["brier_score"] = 0.1
    with pytest.raises(ProductFocusError, match="calibration metrics differ"):
        _validate_repeatable_living_dex_calibration_audit_projection(changed_metric)

    changed_effect = deepcopy(receipt)
    changed_effect["effects"]["model_fits"] = 1
    with pytest.raises(ProductFocusError, match="calibration effects differ"):
        _validate_repeatable_living_dex_calibration_audit_projection(changed_effect)

    changed_control = deepcopy(receipt)
    changed_control["post_hoc_constant_rate_diagnostic"]["eligible_for_advantage_claim"] = True
    with pytest.raises(ProductFocusError, match="post-hoc comparator differs"):
        _validate_repeatable_living_dex_calibration_audit_projection(changed_control)

    changed_gate = deepcopy(receipt)
    changed_gate["next_gate"]["evaluation"]["timing_or_rng_siblings_create_independence"] = True
    with pytest.raises(ProductFocusError, match="calibration next gate differs"):
        _validate_repeatable_living_dex_calibration_audit_projection(changed_gate)


@pytest.mark.parametrize(
    "counter",
    (
        "causal_train_examples",
        "model_fits",
        "unseen_comparisons",
        "authority_promotions",
        "transfer_results",
    ),
)
def test_active_dashboard_counters_cannot_out_run_their_evidence_projection(
    counter: str,
) -> None:
    document = _document()
    lane = _active(document)
    progress = lane["progress"]
    assert isinstance(progress, dict)
    progress[counter] = 999

    with pytest.raises(ProductFocusError, match="typed evidence projection"):
        validate_product_focus_document(document)


def test_active_evidence_prefix_cannot_change_without_a_counter_projection() -> None:
    document = _document()
    lane = _active(document)
    progress = lane["progress"]
    assert isinstance(progress, dict)
    evidence = progress["evidence"]
    assert isinstance(evidence, list)
    evidence.append(dict(evidence[-1]))
    appended = evidence[-1]
    assert isinstance(appended, dict)
    appended["path"] = "docs/evidence/unprojected-result.json"

    with pytest.raises(ProductFocusError, match="supported counter projection"):
        validate_product_focus_document(document)


def test_battle_cycle_projection_counts_learning_but_rejects_advantage() -> None:
    receipt = json.loads(BATTLE_OUTCOME_CYCLE_RESULT.read_text(encoding="ascii"))

    assert receipt["status"] == "rejected_no_development_discordance"
    assert receipt["execution"] == {
        "activated_candidate_targets": 6,
        "candidate_claims_created": 6,
        "development_candidate_outcomes": 3,
        "measured_candidate_outcomes": 6,
        "root_claims_created": 2,
        "teacher_choice_targets": 0,
        "teacher_queries": 0,
        "train_candidate_outcomes": 3,
        "unexecuted_counterfactual_targets": 0,
        "unmeasured_action_targets": 0,
    }
    assert receipt["counter_treatment"] == {
        "authority_promotions_added": 0,
        "causal_train_examples_added": 1,
        "development_episode_attempts_added": 1,
        "model_fits_added": 1,
        "transfer_results_added": 0,
        "unseen_comparisons_added": 0,
        "verified_outcome_examples_added": 1,
    }
    assert receipt["development_comparison"]["discordant_examples"] == 0
    assert receipt["development_comparison"]["candidate_advantage_observed"] is False


def test_battle_cycle_projection_rejects_counter_treatment_tampering() -> None:
    tampered = deepcopy(json.loads(BATTLE_OUTCOME_CYCLE_RESULT.read_text()))
    tampered["counter_treatment"]["authority_promotions_added"] = 1

    with pytest.raises(ProductFocusError, match="counter treatment differs"):
        _validate_battle_cycle_projection(tampered)


def test_active_lane_rename_cannot_bypass_the_counter_projection() -> None:
    document = _document()
    lane = _active(document)
    lane["id"] = "renamed-dashboard-lane"
    progress = lane["progress"]
    assert isinstance(progress, dict)
    progress["causal_train_examples"] = 999

    with pytest.raises(ProductFocusError, match="typed evidence projection"):
        validate_product_focus_document(document)


def test_first_authentic_red_collection_choice_is_tracked_without_overclaim() -> None:
    receipt = json.loads(RED_LIVING_DEX_OPTION_DEVELOPMENT_RESULT.read_text(encoding="ascii"))

    assert receipt["status"] == "one_authentic_model_selected_red_collection_option_settled"
    assert receipt["episode"]["status"] == (
        "model_selected_option_settled_and_independently_verified"
    )
    assert receipt["episode"]["model_decision"] == {
        "model_predictions": 1,
        "score_margin": 1.2777899345444856,
        "selected_candidate_index": 0,
        "selected_candidate_probability": 0.7820733395566392,
        "selected_goal_kind": "acquire_species",
    }
    assert receipt["episode"]["outcome"] == {
        "dependency_distance_after": 1,
        "dependency_distance_before": 2,
        "exact_selected_transition": True,
        "required_living_preserved": True,
        "reward": 1,
        "status": "settled",
        "unrelated_species_preserved": True,
    }
    assert receipt["root_disposition"]["retry_allowed"] is False
    assert receipt["zero_effects"]["authority_promotions"] == 0
    assert receipt["zero_effects"]["crystal_accesses"] == 0
    assert receipt["zero_effects"]["teacher_choices"] == 0
    assert receipt["counter_treatment"]["development_episode_attempts_added"] == 1
    assert receipt["counter_treatment"]["verified_outcome_examples_added"] == 1
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_product_focus_renderer_uses_singular_hour_with_plural_sessions() -> None:
    document = deepcopy(_document())
    lane = _active(document)
    time_box = lane["time_box"]
    assert isinstance(time_box, dict)
    time_box["maximum_sessions"] = 2
    time_box["maximum_hours"] = 1

    rendered = render_product_focus_markdown(validate_product_focus_document(document))

    assert "| Time box | 2 sessions / 1 hour |" in rendered


def test_red_dependency_shadow_design_qualification_is_zero_effect_and_exact_head() -> None:
    receipt = json.loads(RED_DEPENDENCY_SHADOW_DESIGN_QUALIFICATION.read_text(encoding="ascii"))

    assert receipt["status"] == (
        "published_shadow_decision_design_qualified_runner_not_implemented"
    )
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_deselected": 3,
        "ci_passed": 4537,
        "ci_run_id": 32453057425,
        "ci_skipped": 1,
        "ci_xfailed": 1,
        "source_commit": "8afb1db0b345c9cdd83323585f54a1352fb31618",
    }
    assert receipt["design_bindings"]["design_sha256"] == (
        "5fbe527b3c1d126d376c5aae29ff10e47e9222b23cc408c4c37ad76b53e0f1dd"
    )
    assert receipt["antigravity_review"]["verdict"] == "go"
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_red_dependency_shadow_runner_qualification_is_zero_effect_and_exact_head() -> None:
    receipt = json.loads(RED_DEPENDENCY_SHADOW_RUNNER_QUALIFICATION.read_text(encoding="ascii"))

    assert receipt["status"] == "published_runner_qualified_no_live_preflight_or_prediction"
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_deselected": 3,
        "ci_passed": 4566,
        "ci_run_id": 32457709720,
        "ci_skipped": 1,
        "ci_xfailed": 1,
        "pull_request": 26,
        "source_commit": "d4955fb69fff9a763e14a9b5b19601f834fc0c5f",
    }
    assert receipt["antigravity_review"] == {
        "exact_bytes_verified": True,
        "focused_tests_passed": 32,
        "p0_blockers": 0,
        "p1_blockers": 0,
        "p2_findings": 0,
        "private_or_runtime_accesses": 0,
        "verdict": "go",
    }
    assert receipt["runner_bindings"]["runner_sha256"] == (
        "e633b9e1f115f437de337242d44a92d70c764da0f63795e64beec1bf2318af3b"
    )
    assert receipt["qualification"]["provenance"]["manifest_before_private_access"] is True
    assert receipt["qualification"]["execution_boundary"] == {
        "controller_actions_maximum": 0,
        "encounter_harvest_logging_forbidden": True,
        "emulator_frames_advanced_maximum": 0,
        "maximum_model_predictions": 1,
        "model_update_allowed": False,
        "teacher_queries": 0,
    }
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_red_dependency_shadow_preflight_stops_without_prediction_or_action() -> None:
    receipt = json.loads(RED_DEPENDENCY_SHADOW_PREFLIGHT_RESULT.read_text(encoding="ascii"))

    assert receipt["status"] == "preflight_completed_no_eligible_opportunity_context_closed"
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_deselected": 3,
        "ci_passed": 4567,
        "ci_run_id": 32458785817,
        "ci_skipped": 1,
        "ci_xfailed": 1,
        "pull_request": 27,
        "runner_sha256": ("e633b9e1f115f437de337242d44a92d70c764da0f63795e64beec1bf2318af3b"),
        "source_bundle_sha256": (
            "5ca24b648357ebc7799eee64bdd52cc2f779470835a68387c15f37f62e3f1892"
        ),
        "source_commit": "8d559d230fc06fa83edc8015bb245df531600e16",
    }
    assert receipt["preflight"] == {
        "candidate_count": 0,
        "context_replacement_allowed": False,
        "controller_actions": 0,
        "emulator_frames_advanced": 0,
        "execution_identity_consumed": False,
        "global_claim_writes": 0,
        "identity_fields_public": 0,
        "local_episode_writes": 0,
        "model_predictions": 0,
        "preflight_output_sha256": (
            "c98a315d4f13b2181dedd95c0988cb89188d71948b58ba141790dbd3b9246e56"
        ),
        "retry_allowed": False,
        "score_margin": None,
        "selected_candidate_kind": None,
        "selected_candidate_probability": None,
        "status": "no_eligible_opportunity_zero_prediction_zero_action",
        "teacher_queries": 0,
    }
    assert receipt["protected_access"]["nonsealed_red_contexts_opened"] == 1
    assert receipt["protected_access"]["claim_registry_checked_read_only"] is True
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_red_dual_capability_design_is_qualified_without_runtime_effect() -> None:
    receipt = json.loads(RED_DUAL_CAPABILITY_DESIGN_QUALIFICATION.read_text(encoding="ascii"))

    assert receipt["status"] == "published_public_design_qualified_no_binding_or_execution"
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_deselected": 3,
        "ci_passed": 4580,
        "ci_run_id": 32462322717,
        "ci_skipped": 1,
        "ci_xfailed": 1,
        "source_commit": "09e9b04bc2bb09b1d793a0484dca3898e010688b",
    }
    assert receipt["antigravity_review"]["final_verdict"] == "go"
    assert receipt["antigravity_review"]["resolved_finding_count"] == 1
    assert receipt["qualification"]["capability_contract"] == {
        "candidate_count": 2,
        "candidate_order": ["acquire_species", "evolve_species"],
        "generic_semantic_venue_entry_required": True,
        "independent_live_availability_required": True,
        "profile_or_curriculum_direction_sequences_allowed": False,
        "same_reset_state_sha256_required": True,
    }
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_campaign_result_is_balanced_and_scoped() -> None:
    receipt = json.loads(ROOTLESS_DEPENDENCY_CAMPAIGN_RESULT.read_text(encoding="ascii"))

    assert receipt["status"] == ("eight_balanced_synthetic_train_outcomes_admitted_fit_not_started")
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
    assert receipt["counter_treatment"]["synthetic_rootless_atomic_goal_episodes_added"] == 8
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
    assert receipt["fit"]["fitted_cross_entropy"] < receipt["fit"]["baseline_cross_entropy"]
    assert receipt["counter_treatment"]["synthetic_rootless_model_fits_added"] == 1
    assert receipt["counter_treatment"]["historical_gameplay_model_fits_added"] == 0
    assert receipt["counter_treatment"]["synthetic_rootless_unseen_comparisons_added"] == 0
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_v2_compliance_fit_is_clean_and_zero_credit() -> None:
    receipt = json.loads(ROOTLESS_DEPENDENCY_V2_COMPLIANCE_FIT_RESULT.read_text(encoding="ascii"))

    assert receipt["status"] == "completed_clean_v2_compliance_replacement_fit"
    assert receipt["fit"]["status"] == "completed_compliance_replacement_fit"
    assert receipt["fit"]["fit_claim_consumed"] is True
    assert receipt["fit"]["development_payloads_opened"] == 0
    assert receipt["fit"]["development_payloads_decoded"] == 0
    assert receipt["design"]["development_manifest_rows_authenticated"] == 4
    assert receipt["antigravity_review"] == {
        "development_payloads_or_private_claims_accessed_during_review": False,
        "overclaim_detected": False,
        "p0_or_p1_blockers": 0,
        "scope": (
            "public_fit_bundle_counter_boundary_next_comparison_preflight_and_mission_alignment"
        ),
        "verdict": "go",
    }
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_v2_comparison_preflight_keeps_openings_sealed() -> None:
    receipt = json.loads(
        ROOTLESS_DEPENDENCY_V2_COMPARISON_PREFLIGHT_RESULT.read_text(encoding="ascii")
    )

    assert receipt["status"] == "ready_identity_unclaimed_development_remains_sealed"
    assert receipt["comparison"] == {
        "comparison_claim_consumed": False,
        "comparison_claim_sha256": (
            "ed906f0660381b5420777d9a4890e1137ef824f9c001bb68db9b1294c2be0583"
        ),
        "comparison_execution_identity_sha256": (
            "34e741cbfd192eb7019a83042a854179c9260487bb41f36dac74746ba8a95e25"
        ),
        "comparison_execution_supported_by_current_runner": False,
        "development_manifest_rows_authenticated": 4,
        "development_payloads_decoded": 0,
        "development_payloads_opened": 0,
        "fit_bundle_authenticated": True,
        "status": "ready_identity_unclaimed",
    }
    assert receipt["execution_manifest"]["execution_manifest_sha256"] == (
        "583050da59fff94f3bcba6018533fa1eb77b94cd6754d2775b71a75bfcf423d1"
    )
    assert receipt["antigravity_review"]["verdict"] == "go"
    assert receipt["antigravity_review"]["p0_or_p1_blockers"] == 0
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_v2_execution_qualification_is_zero_effect_and_superseded() -> None:
    receipt = json.loads(
        ROOTLESS_DEPENDENCY_V2_COMPARISON_EXECUTION_QUALIFICATION.read_text(encoding="ascii")
    )

    assert receipt["status"] == "qualification_complete_execution_reorientation_required"
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32447962527,
        "source_bundle_sha256": (
            "46c2f7aa73d4d262afde2d8d11e41e3f85759af4af185d299367dfc94c84af29"
        ),
        "source_commit": "96ef8a1bd105e399963ec8656f3a81cb850742b9",
    }
    assert receipt["comparison"]["comparison_claim_consumed"] is False
    assert receipt["comparison"]["development_payloads_opened"] == 0
    assert receipt["comparison"]["development_payloads_decoded"] == 0
    assert receipt["comparison"]["identity_status"] == (
        "valid_qualification_identity_superseded_for_execution_after_reorientation_commit"
    )
    assert receipt["procedural_ordering"] == {
        "claim_or_payload_effect": False,
        "finding": (
            "The metadata-only preflight ran after runner publication but one reorientation "
            "earlier than the active product lane permitted."
        ),
        "remedy": (
            "Track this zero-effect qualification transparently, activate the execution lane, "
            "publish that reorientation, then freeze and run a new exact-head preflight before "
            "comparison."
        ),
        "root_or_semantic_claim_invalidation_required": False,
        "scientific_contamination": False,
    }
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_v2_comparison_result_is_aggregate_only_and_counted_once() -> None:
    receipt = json.loads(ROOTLESS_DEPENDENCY_V2_COMPARISON_RESULT.read_text(encoding="ascii"))

    assert receipt["status"] == "completed_descriptive_comparison_reorientation_required"
    assert receipt["comparison"]["comparison_claim_consumed"] is True
    assert receipt["comparison"]["retry_allowed"] is False
    assert receipt["comparison"]["development_payloads_opened"] == 4
    assert receipt["comparison"]["development_payloads_decoded"] == 4
    assert receipt["aggregate"] == {
        "baseline_correct": 2,
        "baseline_cross_entropy": 0.6931471805599453,
        "baseline_mean_winner_probability": 0.5,
        "candidate_correct": 4,
        "candidate_cross_entropy": 0.2056356330860733,
        "candidate_mean_winner_probability": 0.8147866408745148,
        "descriptive_gate_passed": True,
        "development_rows_disclosed": 0,
        "family_count": 2,
        "row_count": 4,
    }
    assert receipt["counter_treatment"]["synthetic_rootless_unseen_comparisons_added"] == 1
    assert receipt["counter_treatment"]["unseen_comparisons_added"] == 1
    assert {
        value
        for key, value in receipt["counter_treatment"].items()
        if key not in {"synthetic_rootless_unseen_comparisons_added", "unseen_comparisons_added"}
    } == {0}
    assert receipt["antigravity_review"]["verdict"] == "go"
    assert receipt["antigravity_review"]["p0_or_p1_blockers"] == 0
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_red_dependency_adapter_qualification_is_public_only_and_zero_effect() -> None:
    receipt = json.loads(RED_DEPENDENCY_ADAPTER_QUALIFICATION.read_text(encoding="ascii"))

    assert receipt["status"] == "qualified_for_separate_shadow_observation_design"
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32451757975,
        "source_bundle_sha256": (
            "3beb7ce9039422f84bfc470913b8054e6b4259f4d05daabb6bc02ba8038c8a8e"
        ),
        "source_commit": "6fe9a677f76c06c5da74e50f8a2ad5c391bfa1a3",
    }
    assert receipt["qualification"]["canonical_transformation_edges"] == 26
    assert receipt["qualification"]["model_supported_incomplete_edges_on_empty_fixture"] == 22
    assert receipt["qualification"]["unsupported_zero_reserve_edges"] == 4
    assert receipt["qualification"]["policy_identity_leaks"] == 0
    assert receipt["qualification"]["public_synthetic_adapter_tests_passed"] == 11
    assert receipt["antigravity_review"] == {
        "exact_head_verified": True,
        "p0_blockers": 0,
        "p1_blockers": 0,
        "p2_findings": 0,
        "private_or_rom_accesses": 0,
        "verdict": "go",
    }
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_rootless_dependency_comparison_preflight_is_historical_and_unconsumed() -> None:
    receipt = json.loads(ROOTLESS_DEPENDENCY_COMPARISON_PREFLIGHT.read_text(encoding="ascii"))

    assert receipt["status"] == ("sealed_comparison_ready_development_remains_unopened")
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


def test_fresh_rootless_v2_design_is_public_only_and_counter_neutral() -> None:
    receipt = json.loads(
        ROOTLESS_DEPENDENCY_FRESH_EVALUATION_DESIGN_V2_QUALIFICATION.read_text(encoding="ascii")
    )

    assert receipt["status"] == "fresh_v2_public_evaluation_design_published_and_qualified"
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32437096447,
        "source_commit": "5ade045859ff00601b2acfd34a6dad9d769f0859",
    }
    assert receipt["antigravity_review"]["post_implementation"]["p0_or_p1_blockers"] == 0
    assert receipt["blueprint"]["development_commitments"] == 4
    assert receipt["blueprint"]["nonce_bytes_inside_private_payload"] == 32
    assert receipt["blueprint"]["v1_fit_model_or_opening_reuse_allowed"] is False
    assert (
        receipt["qualification"]["counter_semantics"][
            "future_clean_compliance_refit_learning_counter_delta"
        ]
        == 0
    )
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_fresh_rootless_v2_implementation_is_qualified_and_counter_neutral() -> None:
    receipt = json.loads(
        ROOTLESS_DEPENDENCY_FRESH_EVALUATION_IMPLEMENTATION_V2_QUALIFICATION.read_text(
            encoding="ascii"
        )
    )

    assert receipt["status"] == (
        "fresh_v2_public_evaluation_implementation_published_and_qualified"
    )
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32442269879,
        "source_commit": "26e353bee5d96b98c54244845f9a7457b726f842",
    }
    assert receipt["antigravity_review"]["exact_delta"]["p0_or_p1_blockers"] == 0
    provisioning = receipt["qualification"]["provisioning"]
    assert provisioning["exact_private_store_bound_into_execution_identity"] is True
    assert provisioning["replacement_allowed"] is False
    assert provisioning["resume_against_another_private_store_rejected"] is True
    assert receipt["qualification"]["fit"]["development_payloads_opened"] == 0
    assert receipt["qualification"]["comparison_preflight"]["development_payloads_opened"] == 0
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_fresh_rootless_v2_provision_is_sealed_and_counter_neutral() -> None:
    from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
        RootlessDependencyEvaluationDesignV2,
    )

    receipt = json.loads(
        ROOTLESS_DEPENDENCY_V2_PRIVATE_PROVISION_RESULT.read_text(encoding="ascii")
    )
    design = json.loads(ROOTLESS_DEPENDENCY_V2_PUBLIC_DESIGN.read_text(encoding="ascii"))

    assert receipt["status"] == "four_fresh_v2_openings_provisioned_once"
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_run_id": 32442951504,
        "pull_request": 15,
        "source_commit": "ec4c17018d3a2b569d776e220f3a3b5b32f202bb",
    }
    assert receipt["antigravity_review"]["verdict"] == "go"
    assert receipt["antigravity_review"]["p0_or_p1_blockers"] == 0
    assert receipt["provision"]["development_openings_provisioned"] == 4
    assert receipt["provision"]["development_payloads_disclosed_publicly"] == 0
    assert receipt["provision"]["global_claim_consumed"] is True
    assert receipt["provision"]["replacement_allowed"] is False
    parsed_design = RootlessDependencyEvaluationDesignV2.from_dict(design)
    assert receipt["design"]["design_sha256"] == parsed_design.design_sha256
    roster = design["development_roster"]
    assert roster["row_count"] == 4
    assert roster["payloads_opened"] == 0
    assert roster["payloads_decoded"] == 0
    assert set(receipt["counter_treatment"].values()) == {0}
    roster_encoded = json.dumps(roster, sort_keys=True)
    assert "nonce" not in roster_encoded
    assert "family_id" not in roster_encoded
    assert "assigned_action" not in roster_encoded
    encoded = json.dumps({"design": design, "receipt": receipt}, sort_keys=True)
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

    # Learning restores a scorecard, without rewriting historical counters or
    # presenting their completed quota as this pilot's acceptance.
    assert rows == (
        "Registered Train Example · train: 135/4",
        "Model Fit · train: 16/1",
        "Unseen Comparison · development: 9/1",
    )
    assert "Legacy minimum, not current acceptance" in DEFAULT_FOCUS_DOCUMENT.read_text(
        encoding="utf-8"
    )


def test_maintenance_page_does_not_show_a_stale_learning_quota() -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "maintenance"
    lane["maintenance_unblocks"] = "red-readiness-consequence-learning"
    lane["measurable_outputs"] = []
    state = validate_product_focus_document(document)
    text = render_product_focus_markdown(state)
    assert state.progress["registered_train_examples"] == 135
    assert "This maintenance block has no lesson-count quota" in text
    assert "Minimum for the next decision" not in text
    assert "Legacy minimum, not current acceptance" not in text
    assert "| Registered Train Example" not in text


@pytest.mark.parametrize(
    "goal",
    [
        "Build a living Pokedex across mainline games.",
        "Build a registered Pokedex in Red alone.",
    ],
)
def test_product_rejects_superseded_or_single_game_objective(goal: str) -> None:
    document = _document()
    document["product"]["goal"] = goal
    with pytest.raises(ProductFocusError, match="cross-game registered Pokedex"):
        validate_product_focus_document(document)


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
    retired = next(
        lane for lane in lanes if isinstance(lane, dict) and lane.get("status") == "retired"
    )
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
        ("Development Episode · development", 30, 12),
        ("Verified Outcome Example · development", 67, 12),
        ("Verified Composition Episode · development", 4, 2),
    )


def test_learning_lane_accepts_evidence_backed_causal_train_examples() -> None:
    document = _document()
    lane = _active(document)
    lane["kind"] = "learning"
    lane["maintenance_unblocks"] = None
    lane["measurable_outputs"] = [
        {"kind": "causal_train_example", "minimum": 1, "partition": "train"}
    ]
    state = validate_product_focus_document(document)

    assert focus_scorecard(state) == (("Causal Train Example · train", 112, 1),)


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
    assert focus_scorecard(state) == (("Synthetic Rootless Unseen Comparison · development", 1, 1),)


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
    lane["measurable_outputs"] = [{"kind": kind, "minimum": 1, "partition": partition}]

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


@pytest.mark.parametrize(
    "protected_action",
    (
        "cloned_or_rehashed_root_independence",
        "retired_frozen_trial_reissue",
        "crystal_execution",
        "assisted_completion_as_autonomous",
        "final_actor_cheat",
        "model_fit_on_development",
        "routine_clean_power_teacher_factory",
        "sealed_red_evaluation",
        "teacher_route_hardening",
        "unauthorized_publication",
        "unexecuted_counterfactual_target",
        "unmeasured_action_target",
    ),
)
def test_development_cannot_silently_open_a_protected_action(
    protected_action: str,
) -> None:
    document = _document()
    lane = _active(document)
    lane["rigor"] = "development"
    prohibited = lane["prohibited_actions"]
    assert isinstance(prohibited, list)
    prohibited.remove(protected_action)

    with pytest.raises(ProductFocusError, match="protected-action prohibition"):
        validate_product_focus_document(document)


@pytest.mark.parametrize(
    "forward_action",
    (
        "Launch a clean-power factory for more rows.",
        "Perform teacher route hardening before training.",
    ),
)
def test_active_forward_plan_cannot_schedule_its_prohibited_maintenance(
    forward_action: str,
) -> None:
    document = _document()
    lane = _active(document)
    lane["next_decision"] = forward_action

    with pytest.raises(ProductFocusError, match="active forward plan"):
        validate_product_focus_document(document)


def test_development_contract_allows_batches_assistance_and_exploratory_campaigns() -> None:
    document = _document()
    lane = _active(document)
    lane["next_decision"] = (
        "Run one exploratory full-game replay for the sustained integration question, "
        "with disclosed assistance and several lesson/fit iterations."
    )
    state = validate_product_focus_document(document)
    assert state.active_lane["development_permissions"] == {
        "adaptive_preparation": True,
        "batch_lessons_and_fits": True,
        "compact_verification": True,
        "development_campaigns": True,
        "provisional_integration": True,
        "teacher_controlled_fixtures": True,
    }
    assert len(state.retired_lanes) == 60
    rendered = render_product_focus_markdown(state)
    assert "## Development permissions" in rendered
    assert "All60retired lane identities remain closed" in rendered
    assert "mandatory user pauses" in rendered


@pytest.mark.parametrize(
    "contradiction",
    ("full_game_replay", "teacher_choice_or_fallback", "promotion_from_pilot"),
)
def test_development_permissions_reject_conflicting_prohibitions(contradiction: str) -> None:
    document = _document()
    lane = _active(document)
    lane["prohibited_actions"].append(contradiction)
    with pytest.raises(ProductFocusError, match="permissions conflict"):
        validate_product_focus_document(document)


def test_development_permissions_do_not_authorize_benchmark_execution() -> None:
    document = _document()
    _active(document)["rigor"] = "benchmark"
    with pytest.raises(ProductFocusError, match="cannot authorize evaluation"):
        validate_product_focus_document(document)


@pytest.mark.parametrize("value", (1, "yes", None))
def test_development_permissions_require_explicit_booleans(value: object) -> None:
    document = _document()
    _active(document)["development_permissions"]["provisional_integration"] = value
    with pytest.raises(ProductFocusError):
        validate_product_focus_document(document)


def test_superseded_focus_schema_is_not_silently_used_as_current_authority() -> None:
    document = _document()
    document["schema"] = "pokemon.product-focus.v4"
    with pytest.raises(ProductFocusError, match="schema is unsupported"):
        validate_product_focus_document(document)


@pytest.mark.parametrize(
    ("section", "key", "value", "match"),
    (
        ("alarms", "maximum_sessions_without_measured_learning_output", 2, "one session"),
        ("alarms", "maximum_redundant_full_replays_for_local_question", 1, "redundant full replay"),
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


def test_red_dual_capability_runtime_qualification_is_counter_neutral() -> None:
    receipt = json.loads(RED_DUAL_CAPABILITY_RUNTIME_QUALIFICATION.read_text(encoding="ascii"))

    assert receipt["status"] == (
        "published_runtime_qualified_action_free_scenario_preflight_required"
    )
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_deselected": 3,
        "ci_passed": 4588,
        "ci_run_id": 32465536131,
        "ci_skipped": 1,
        "ci_xfailed": 1,
        "source_commit": "c946e8dba00ca246d3720b115f81691a1a8cdc91",
    }
    assert receipt["antigravity_review"]["verdict"] == "go"
    assert receipt["qualification"]["semantic_route_execution_required"] is True
    assert receipt["qualification"]["controller_direction_sequences_accepted"] is False
    assert receipt["qualification"]["same_reset_required"] is True
    assert receipt["qualification"]["selected_binding_only"] is True
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}


def test_red_dual_capability_preflight_qualification_is_counter_neutral() -> None:
    receipt = json.loads(RED_DUAL_CAPABILITY_PREFLIGHT_QUALIFICATION.read_text(encoding="ascii"))

    assert receipt["status"] == ("published_preflight_runner_qualified_private_preflight_not_run")
    assert receipt["publication"] == {
        "ci_attempt": 1,
        "ci_conclusion": "success",
        "ci_deselected": 3,
        "ci_passed": 4603,
        "ci_run_id": 32470280542,
        "ci_skipped": 1,
        "ci_xfailed": 1,
        "pull_request": 31,
        "source_commit": "c3e07d261545df03b519f5ba270ff0591e43bbe4",
    }
    assert receipt["independent_code_audits"]["mission_verdict"] == "go"
    assert receipt["independent_code_audits"]["safety_verdict"].startswith("go_")
    assert receipt["independent_code_audits"]["third_party_antigravity_review"] == (
        "go_exact_public_invocation_may_be_frozen"
    )
    antigravity = json.loads(
        RED_DUAL_CAPABILITY_PREFLIGHT_ANTIGRAVITY_AUDIT.read_text(encoding="ascii")
    )
    assert antigravity["status"] == "go_exact_public_invocation_may_be_frozen"
    assert antigravity["audit"]["verdict"] == "go"
    assert antigravity["audit"]["p0_blockers"] == 0
    assert antigravity["audit"]["p1_findings"] == 0
    assert antigravity["audit"]["p2_findings"] == 0
    assert set(antigravity["zero_effects"].values()) == {0}
    assert receipt["qualification"]["action_free_preflight_executed"] is False
    assert receipt["qualification"]["model_scoring_available_in_runner"] is False
    assert receipt["qualification"]["route_metrics_are_aggregate_only"] is True
    assert receipt["qualification"]["one_shot_identity_consumed"] is False
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}


def test_red_dual_capability_preflight_v1_failure_is_zero_effect_and_nonretryable() -> None:
    receipt = json.loads(RED_DUAL_CAPABILITY_PREFLIGHT_V1_FAILURE.read_text(encoding="ascii"))

    assert receipt["status"] == "failed_closed_before_private_access_v1_retired"
    assert receipt["failure"] == {
        "effect_status": "verified_zero",
        "execution_result_emitted": False,
        "failure_output_sha256": (
            "292c2ba4e1ac654cc7df1ccd2ec3a6479512689ab533c486b130bcf27827b9d8"
        ),
        "failure_stage": "public_evidence_authentication",
        "protected_access_status": "verified_absent",
        "sanitized_failure_receipt_emitted": True,
    }
    assert receipt["root_disposition"]["retry_allowed"] is False
    assert receipt["root_disposition"]["physical_root_inspected"] is False
    assert receipt["root_disposition"]["physical_root_claimed"] is False
    assert receipt["diagnosis"]["root_or_capability_diagnosed"] is False
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    encoded = json.dumps(receipt, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_tracked_public_evidence_reader_is_qualified_without_protected_effects() -> None:
    receipt = json.loads(TRACKED_PUBLIC_EVIDENCE_READER_QUALIFICATION.read_text(encoding="ascii"))
    audit = json.loads(TRACKED_PUBLIC_EVIDENCE_READER_ANTIGRAVITY_AUDIT.read_text(encoding="ascii"))

    assert receipt["status"] == "qualified_public_reader_v1_complete"
    assert receipt["publication"]["exact_published_main"] == (
        "50c64f1c9cbb0d73d0a3aad0210e326a4005c3de"
    )
    assert receipt["publication"]["ci_run_id"] == 32475789328
    assert receipt["implementation"]["reader_sha256"] == (
        "ecb93c440883ce717569ebd6c6a0b7590fdb560179ff9deac6a858299fa21af2"
    )
    assert receipt["v1_disposition"] == {
        "failure_receipt_sha256": (
            "b09ef67e3cae93ce5033a80fcaf85fae5680e9f22886bc021ab98202f60c6d09"
        ),
        "reopen_allowed": False,
        "retry_allowed": False,
        "selected_context_reuse_allowed": False,
    }
    assert set(receipt["counter_treatment"].values()) == {0}
    assert set(receipt["zero_effects"].values()) == {0}
    assert audit["audit"]["verdict"] == "go"
    assert audit["audit"]["p0_blockers"] == 0
    assert audit["audit"]["p1_blockers"] == 0
    assert audit["v1_disposition"]["retry_allowed"] is False
    assert set(audit["zero_effects"].values()) == {0}
    encoded = json.dumps({"audit": audit, "qualification": receipt}, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_focus_dashboard_is_view_only_and_does_not_overclaim_training() -> None:
    state = load_product_focus()
    # This is the historical 29-to-31 fixture, not whichever model the live
    # dashboard happens to reference after the next real training session.
    evidence = json.loads(
        (
            PROJECT_ROOT / "docs/evidence" / "red-native-player-learning-result-2026-09-06.json"
        ).read_text()
    )
    public = DASHBOARD["product_focus_dashboard_snapshot"](state, evidence=evidence).public_dict()
    assert public["run_status"] == "waiting"
    assert public["actions"] == 0
    assert public["stage_progress"] == 0
    assert public["model"]["decisions"] == 0
    assert public["model"]["teacher_queries"] == 0
    assert public["model"]["fallbacks"] == 0
    assert public["model"]["mode"] == "shadow"
    assert public["collection"]["observed"] is False
    assert public["training"]["samples_before"] == 29
    assert public["training"]["samples_after"] == 31
    assert public["training"]["newly_collected"] == 2
    assert public["training"]["previously_unfitted"] == 0
    assert public["training"]["setup_censors"] == 0
    assert public["training"]["held_out_claim"] is False
    assert public["experiment"]["predictions_committed"] is False
    assert public["learning_components"][0]["validation_examples"] == 0
    assert public["learning_components"][0]["model_sha256"] == (
        "95f62eaafc55a053cf65e23a8dcbf99955360040b85ef56ad8eff3e925edb472"
    )
    encoded = json.dumps(public, sort_keys=True, ensure_ascii=False)
    assert "31-example living-Pokédex goal scorer" in encoded
    assert "Registered-objective outcomes" in encoded
    assert "supply validation before training" not in encoded
    assert "10 untouched" not in encoded
    assert "Brier 0.397811" not in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_dashboard_projects_saved_negative_search_fit_without_a_gameplay_claim() -> None:
    evidence = json.loads(
        (
            PROJECT_ROOT / "docs/evidence" / "red-saved-endpoint-learning-result-2026-09-06.json"
        ).read_text()
    )
    public = DASHBOARD["product_focus_dashboard_snapshot"](
        load_product_focus(),
        evidence=evidence,
    ).public_dict()
    assert public["training"]["samples_before"] == 31
    assert public["training"]["samples_after"] == 32
    assert public["training"]["newly_collected"] == 1
    assert public["training"]["held_out_claim"] is False
    assert public["model"]["decisions"] == public["actions"] == 0
    assert public["learning_components"][0]["model_sha256"] == (
        "5b92e48c39a7eff724d9ed0ddb32ed2460997e95cdaecdc16ac5ec603b4683bc"
    )


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
