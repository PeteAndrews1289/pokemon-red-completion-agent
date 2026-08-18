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


def test_tracked_focus_is_canonical_and_reports_evidence_backed_learning_progress() -> None:
    state = load_product_focus()

    assert DEFAULT_FOCUS_CONFIG.read_bytes() == canonical_focus_json(state.document)
    assert DEFAULT_FOCUS_DOCUMENT.read_text(encoding="utf-8") == (
        render_product_focus_markdown(state)
    )
    assert state.active_lane["id"] == (
        "repeatable-goal-manager-development-qualification-v1"
    )
    assert state.active_lane["kind"] == "maintenance"
    assert len(state.retired_lanes) == 9
    assert focus_progress_fraction(state) == 0.0
    assert focus_scorecard(state) == ()
    assert state.progress["outcome_questions"] == {"development": 15, "train": 30}
    assert state.progress["model_fits"] == 3
    assert state.progress["unseen_comparisons"] == 3
    assert state.progress["development_episode_attempts"] == 0
    assert state.progress["verified_outcome_examples"] == 0
    assert state.progress["verified_composition_episodes"] == 0
    encoded = json.dumps(state.document, sort_keys=True)
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


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
        ("Development Episode · development", 0, 12),
        ("Verified Outcome Example · development", 0, 12),
        ("Verified Composition Episode · development", 0, 2),
    )


def test_maintenance_must_name_the_learning_experiment_it_unblocks() -> None:
    document = _document()
    lane = _active(document)
    lane["maintenance_unblocks"] = None

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
    assert public["stage_progress"] == 0.0
    assert public["actions"] == 0
    assert "Repeatable Red goal-manager development qualification" in public["stage"]
    assert public["experiment"]["zero_shot"] == {"completed": 0, "total": 0}  # type: ignore[index]
    assert public["experiment"]["adaptation"] == {"completed": 0, "total": 0}  # type: ignore[index]
    assert public["experiment"]["sealed_test"] == {"completed": 0, "total": 0}  # type: ignore[index]
    encoded = json.dumps(public, sort_keys=True)
    assert "Publish runner + green CI" in encoded
    assert "freeze 4 authenticated train roots" in encoded
    assert "root closed" in encoded
    assert "retry forbidden" in encoded
    assert "execution identity 0" in encoded
    assert "V3 preflight failed at action_free_admission" in encoded
    assert "Repeatable lane current" in encoded
    assert "frozen roots 0" in encoded
    assert "claimed trials 0" in encoded
    assert "advanced frames 0" in encoded
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded


def test_focus_dashboard_uses_a_separate_local_port() -> None:
    args = DASHBOARD["_parser"]().parse_args(["--no-browser", "--duration-seconds", "1"])

    assert args.port == 8768
    assert args.no_browser is True
    assert args.duration_seconds == 1
