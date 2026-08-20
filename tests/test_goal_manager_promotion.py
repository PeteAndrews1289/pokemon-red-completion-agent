from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import pokemon_red_completion.goal_manager_promotion as promotion_module
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_model import (
    GOAL_MANAGER_FEATURE_NAMES,
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
    goal_manager_fit_configuration,
)
from pokemon_red_completion.goal_manager_promotion import (
    AuthenticatedGoalManagerCandidate,
    GoalManagerPromotionError,
    authenticate_goal_manager_candidate,
    authenticate_goal_manager_shadow_receipt,
    build_goal_manager_promotion_receipt,
    parse_goal_manager_promotion_plan,
)
from pokemon_red_completion.goal_manager_promotion_runtime import (
    GoalManagerPromotionContextResult,
    summarize_goal_manager_promotion_results,
)
from pokemon_red_completion.goal_manager_runtime import (
    GoalExecutionReport,
    GoalManagerExecutionResult,
    GoalVerification,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "configs" / "red-goal-manager-promotion-v1.json"


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


def _model() -> GoalManagerLinearModel:
    width = len(GOAL_MANAGER_FEATURE_NAMES)
    return GoalManagerLinearModel(
        weights=np.zeros(width, dtype=np.float64),
        feature_mean=np.zeros(width, dtype=np.float64),
        feature_scale=np.ones(width, dtype=np.float64),
        l2=0.02,
        training_epochs=800,
    )


def _fit_summary(plan) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "schema": "pokemon-core-goal-manager-development-fit-v1",
        "collection": {
            "collection_source_commit": plan.training_source_commit,
            "registry_sha256": plan.registry_sha256,
            "teacher_execution_sha256": plan.teacher_execution_sha256,
            "context_catalog_sha256": plan.context_catalog_sha256,
            "train_examples": 54,
            "validation_examples": 27,
            "collection_status": {
                "ready_for_training": True,
                "collected_slots": 81,
                "successful_teacher_slots": 81,
            },
            "curriculum_audit": {
                "ready_for_training": True,
                "train_validation_context_overlap_count": 0,
                "replicated_teacher_choice_example_count": 0,
            },
        },
        "feature_schema": {
            "candidate_scoring": "shared_per_candidate",
            "candidate_order_used_as_feature": False,
            "private_binding_identity_used_as_feature": False,
            "title_identity_used_as_feature": False,
            "feature_count": len(GOAL_MANAGER_FEATURE_NAMES),
            "feature_names": list(GOAL_MANAGER_FEATURE_NAMES),
        },
        "fit": goal_manager_fit_configuration(),
        "model": {
            "canonical_sha256": plan.model_canonical_sha256,
            "file_sha256": plan.model_file_sha256,
            "model_id": plan.model_id,
        },
        "training": {"examples": 54, "accuracy": 1.0},
        "validation": {
            "examples": 27,
            "accuracy": 1.0,
            "selected_kind_accuracy": {kind.value: 1.0 for kind in GoalKind},
        },
        "validation_gate": {"all_checks": True, "passed": True},
        "held_out_titles": {
            "evaluated": False,
            "next_environment": "pokemon.mainline:crystal",
            "opened": False,
        },
        "private_path_fields": 0,
    }


def _candidate(plan=None) -> AuthenticatedGoalManagerCandidate:  # type: ignore[no-untyped-def]
    selected_plan = plan or parse_goal_manager_promotion_plan(PLAN_PATH.read_bytes())
    slots = tuple(
        SimpleNamespace(slot_id=f"validation-slot-{index:02d}", partition="validation")
        for index in range(27)
    )
    registry = SimpleNamespace(
        registry_sha256=selected_plan.registry_sha256,
        execution=SimpleNamespace(
            source_commit=selected_plan.training_source_commit,
            source_bundle_sha256=selected_plan.training_source_bundle_sha256,
        ),
        slots=slots,
    )
    catalog = SimpleNamespace(catalog_sha256=selected_plan.context_catalog_sha256)
    return AuthenticatedGoalManagerCandidate(
        plan=selected_plan,
        registry=registry,
        catalog=catalog,
        model=_model(),
        fit_summary_sha256=selected_plan.fit_summary_file_sha256,
    )


def _context_result(
    index: int,
    *,
    mode: str,
    confidence: float = 0.9,
) -> GoalManagerPromotionContextResult:
    execution = GoalManagerExecutionResult(
        selected_kind=GoalKind.ADVANCE_STORY,
        selected_candidate_index=0,
        execution=GoalExecutionReport(1, 2, {}),
        verification=GoalVerification(GoalDecisionOutcome.SUCCEEDED),
        decision_recorded=False,
        outcome_recorded=False,
    )
    return GoalManagerPromotionContextResult(
        mode=mode,
        slot_id=f"validation-slot-{index:02d}",
        context_id=hashlib.sha256(f"context-{index}".encode()).hexdigest(),
        question_sha256=hashlib.sha256(f"question-{index}".encode()).hexdigest(),
        policy_context_sha256=hashlib.sha256(f"policy-{index}".encode()).hexdigest(),
        reference_candidate_index=0,
        reference_kind=GoalKind.ADVANCE_STORY,
        model_candidate_index=0,
        model_kind=GoalKind.ADVANCE_STORY,
        model_confidence=confidence,
        model_reference_agreement=True,
        model_had_execution_authority=mode == "causal",
        reference_had_execution_authority=mode == "shadow",
        execution=execution,
    )


def test_committed_plan_is_canonical_path_free_and_keeps_test_sealed() -> None:
    payload = PLAN_PATH.read_bytes()
    plan = parse_goal_manager_promotion_plan(payload)

    assert plan.plan_sha256 == hashlib.sha256(payload).hexdigest()
    assert plan.train_examples == 54
    assert plan.validation_examples == 27
    assert plan.minimum_live_confidence == 0.8
    assert plan.required_shadow_successes == 27
    assert plan.required_causal_successes == 27
    assert plan.sealed_test_captures == 12
    assert plan.sealed_test_captures_opened == 0
    assert "/" not in json.dumps(json.loads(payload))


def test_plan_parser_rejects_noncanonical_or_weakened_gates() -> None:
    document = json.loads(PLAN_PATH.read_text(encoding="ascii"))
    with pytest.raises(GoalManagerPromotionError, match="canonical"):
        parse_goal_manager_promotion_plan(json.dumps(document, indent=2).encode("ascii"))

    document["gates"]["maximum_teacher_fallbacks"] = 1
    with pytest.raises(GoalManagerPromotionError, match="counts differ"):
        parse_goal_manager_promotion_plan(_canonical(document))


def test_candidate_authentication_binds_model_summary_catalog_and_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = parse_goal_manager_promotion_plan(PLAN_PATH.read_bytes())
    model = _model()
    model_payload = _canonical(model.to_dict())
    model_path = tmp_path / "model.json"
    model_path.write_bytes(model_payload)
    plan = replace(
        base,
        model_file_sha256=hashlib.sha256(model_payload).hexdigest(),
        model_canonical_sha256=canonical_goal_manager_model_sha256(model),
        context_catalog_sha256=hashlib.sha256(b"catalog").hexdigest(),
    )
    summary = _fit_summary(plan)
    summary_payload = _canonical(summary)
    summary_path = tmp_path / "summary.json"
    summary_path.write_bytes(summary_payload)
    plan = replace(
        plan,
        fit_summary_file_sha256=hashlib.sha256(summary_payload).hexdigest(),
    )
    # The summary records the digest fixed in the final plan.
    summary = _fit_summary(plan)
    summary_payload = _canonical(summary)
    summary_path.write_bytes(summary_payload)
    plan = replace(
        plan,
        fit_summary_file_sha256=hashlib.sha256(summary_payload).hexdigest(),
    )
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_bytes(b"catalog")
    registry = SimpleNamespace(
        registry_sha256=plan.registry_sha256,
        execution=SimpleNamespace(
            source_commit=plan.training_source_commit,
            source_bundle_sha256=plan.training_source_bundle_sha256,
            teacher_execution_sha256=plan.teacher_execution_sha256,
        ),
    )
    catalog = SimpleNamespace(catalog_sha256=plan.context_catalog_sha256)
    monkeypatch.setattr(
        promotion_module,
        "load_committed_goal_manager_registry_at_revision",
        lambda *_args: registry,
    )
    monkeypatch.setattr(
        promotion_module,
        "parse_goal_manager_context_catalog",
        lambda *_args: catalog,
    )

    authenticated = authenticate_goal_manager_candidate(
        repository_root=tmp_path,
        plan=plan,
        context_catalog_path=catalog_path,
        model_path=model_path,
        fit_summary_path=summary_path,
    )

    assert authenticated.model.model_id == plan.model_id
    assert authenticated.public_dict()["private_path_fields"] == 0

    weakened = json.loads(summary_path.read_text(encoding="ascii"))
    weakened["held_out_titles"]["opened"] = True
    weakened_payload = _canonical(weakened)
    summary_path.write_bytes(weakened_payload)
    weakened_plan = replace(
        plan,
        fit_summary_file_sha256=hashlib.sha256(weakened_payload).hexdigest(),
    )
    with pytest.raises(GoalManagerPromotionError, match="held-out"):
        authenticate_goal_manager_candidate(
            repository_root=tmp_path,
            plan=weakened_plan,
            context_catalog_path=catalog_path,
            model_path=model_path,
            fit_summary_path=summary_path,
        )


def test_shadow_receipt_is_not_promotion_and_is_required_for_causal_control() -> None:
    candidate = _candidate()
    shadow_batch = summarize_goal_manager_promotion_results(
        mode="shadow",
        planned_contexts=27,
        results=tuple(_context_result(index, mode="shadow") for index in range(27)),
    )
    shadow = build_goal_manager_promotion_receipt(
        candidate=candidate,
        batch=shadow_batch,
        evaluation_source_commit="b" * 40,
        evaluation_source_bundle_sha256="c" * 64,
    )
    payload = _canonical(shadow)
    digest = hashlib.sha256(payload).hexdigest()

    assert shadow["gates"] == {
        "passed": True,
        "causal_may_start": True,
        "promotion_eligible": False,
    }
    assert authenticate_goal_manager_shadow_receipt(
        payload,
        expected_sha256=digest,
        candidate=candidate,
    ) == digest

    causal_batch = summarize_goal_manager_promotion_results(
        mode="causal",
        planned_contexts=27,
        results=tuple(_context_result(index, mode="causal") for index in range(27)),
    )
    causal = build_goal_manager_promotion_receipt(
        candidate=candidate,
        batch=causal_batch,
        evaluation_source_commit="d" * 40,
        evaluation_source_bundle_sha256="e" * 64,
        prior_shadow_receipt_sha256=digest,
        shadow_prerequisite_passed=True,
    )

    assert causal["gates"]["promotion_eligible"] is True
    assert causal["authority"]["model_had_execution_authority"] is True
    assert causal["authority"]["teacher_queries"] == 0
    assert causal["held_out_test"]["opened"] == 0


def test_live_confidence_floor_rejects_an_otherwise_complete_shadow() -> None:
    candidate = _candidate()
    results = tuple(
        _context_result(index, mode="shadow", confidence=0.79 if index == 0 else 0.9)
        for index in range(27)
    )
    batch = summarize_goal_manager_promotion_results(
        mode="shadow",
        planned_contexts=27,
        results=results,
    )
    receipt = build_goal_manager_promotion_receipt(
        candidate=candidate,
        batch=batch,
        evaluation_source_commit="b" * 40,
        evaluation_source_bundle_sha256="c" * 64,
    )

    assert receipt["checks"]["minimum_confidence"] is False
    assert receipt["gates"]["causal_may_start"] is False
