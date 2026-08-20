from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion import strategic_navigation_sealed_evaluation as sealed
from pokemon_red_completion.private_artifacts import initialize_private_root
from pokemon_red_completion.strategic_navigation_sealed_evaluation import (
    StrategicSealedAuthorization,
    StrategicSealedCaseOutcome,
    StrategicSealedEvaluationCase,
    StrategicSealedEvaluationError,
    StrategicSealedEvaluationPlan,
    StrategicSealedExternalAuditReceipt,
    StrategicSealedNonTestQualificationReceipt,
    StrategicSealedPrediction,
    StrategicSealedProgress,
    StrategicSealedRuntimeGrant,
    StrategicSealedTeacherResult,
    build_strategic_sealed_authorization,
    build_strategic_sealed_external_audit_receipt,
    build_strategic_sealed_non_test_qualification_receipt,
    execute_strategic_sealed_evaluation,
    load_strategic_sealed_evaluation_plan,
    parse_strategic_sealed_authorization,
    parse_strategic_sealed_external_audit_receipt,
    parse_strategic_sealed_non_test_qualification_receipt,
    require_strategic_sealed_runtime_preflight,
    score_strategic_sealed_evaluation,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_COMMIT = "1" * 40
CASE_CATALOG_SHA256 = "2" * 64
EXTERNAL_AUDIT_EVIDENCE_SHA256 = "3" * 64
NON_TEST_ADAPTER_QUALIFICATION_EVIDENCE_SHA256 = "4" * 64


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


class _NoopAbort:
    def abort(self, case: StrategicSealedEvaluationCase) -> None:
        del case


def _store(tmp_path: Path):
    repository = tmp_path / "repository"
    private = tmp_path / "private"
    repository.mkdir()
    private.mkdir()
    store = initialize_private_root(
        private,
        repository_root=repository,
        allow_same_device=True,
        git_worktree_probe=lambda path: False,
    )
    return private, store


def _receipts(
    plan: StrategicSealedEvaluationPlan,
    *,
    source_commit: str = SOURCE_COMMIT,
    audit_verdict: str = "approved_for_authorization",
    qualification_verdict: str = "passed",
    suffix: str = "v1",
) -> tuple[
    StrategicSealedExternalAuditReceipt,
    StrategicSealedNonTestQualificationReceipt,
]:
    audit = parse_strategic_sealed_external_audit_receipt(
        build_strategic_sealed_external_audit_receipt(
            plan,
            receipt_id=f"external-audit-{suffix}",
            issued_by="independent-auditor",
            issued_on="2026-08-13",
            source_commit=source_commit,
            evidence_sha256=EXTERNAL_AUDIT_EVIDENCE_SHA256,
            verdict=audit_verdict,
        ),
        plan=plan,
        source_commit=source_commit,
    )
    qualification = parse_strategic_sealed_non_test_qualification_receipt(
        build_strategic_sealed_non_test_qualification_receipt(
            plan,
            receipt_id=f"non-test-qualification-{suffix}",
            issued_by="qualification-runner",
            issued_on="2026-08-13",
            source_commit=source_commit,
            evidence_sha256=NON_TEST_ADAPTER_QUALIFICATION_EVIDENCE_SHA256,
            verdict=qualification_verdict,
        ),
        plan=plan,
        source_commit=source_commit,
    )
    return audit, qualification


def _protocol():
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    audit, qualification = _receipts(plan)
    payload = build_strategic_sealed_authorization(
        plan,
        authorization_id="peter-one-shot-v1",
        authorized_by="peterandrews",
        authorized_on="2026-08-13",
        source_commit=SOURCE_COMMIT,
        case_catalog_sha256=CASE_CATALOG_SHA256,
        external_audit_receipt=audit,
        non_test_adapter_qualification_receipt=qualification,
    )
    authorization = parse_strategic_sealed_authorization(
        payload,
        plan=plan,
        external_audit_receipt=audit,
        non_test_adapter_qualification_receipt=qualification,
    )
    grant = require_strategic_sealed_runtime_preflight(
        plan,
        authorization,
        source_commit=SOURCE_COMMIT,
        source_bundle_sha256=plan.execution_source_bundle_sha256,
        source_clean=True,
        source_published=True,
        model_canonical_sha256=plan.model_canonical_sha256,
        model_file_sha256=plan.model_file_sha256,
        teacher_execution_sha256=plan.teacher_execution_sha256,
        case_catalog_sha256=CASE_CATALOG_SHA256,
        external_audit_receipt=audit,
        non_test_adapter_qualification_receipt=qualification,
    )
    return plan, payload, authorization, grant


def _success(
    case: StrategicSealedEvaluationCase,
    *,
    model_correct: bool = True,
    baseline_correct: bool = False,
) -> StrategicSealedCaseOutcome:
    return StrategicSealedCaseOutcome(
        case_id=case.case_id,
        case_sha256=case.case_sha256,
        ordinal=case.ordinal,
        candidate_count=case.candidate_count,
        execution_status="succeeded",
        teacher_target_index=0,
        model_prediction_index=0 if model_correct else 1,
        baseline_prediction_index=0 if baseline_correct else 1,
        policy_input_sha256=hashlib.sha256(f"policy:{case.case_id}".encode("ascii")).hexdigest(),
        episode_manifest_sha256=hashlib.sha256(
            f"episode:{case.case_id}".encode("ascii")
        ).hexdigest(),
    )


def _prediction(
    case: StrategicSealedEvaluationCase,
    *,
    baseline_correct: bool,
) -> StrategicSealedPrediction:
    return StrategicSealedPrediction(
        case_id=case.case_id,
        case_sha256=case.case_sha256,
        ordinal=case.ordinal,
        candidate_count=case.candidate_count,
        model_prediction_index=0,
        model_prediction_tied=False,
        baseline_prediction_index=0 if baseline_correct else 1,
        baseline_prediction_tied=False,
        policy_input_sha256=hashlib.sha256(f"policy:{case.case_id}".encode("ascii")).hexdigest(),
    )


def _teacher(case: StrategicSealedEvaluationCase) -> StrategicSealedTeacherResult:
    return StrategicSealedTeacherResult(
        case_id=case.case_id,
        case_sha256=case.case_sha256,
        ordinal=case.ordinal,
        candidate_count=case.candidate_count,
        execution_status="succeeded",
        teacher_target_index=0,
        episode_manifest_sha256=hashlib.sha256(
            f"episode:{case.case_id}".encode("ascii")
        ).hexdigest(),
    )


def _passing_outcomes(plan) -> tuple[StrategicSealedCaseOutcome, ...]:
    return tuple(
        _success(
            case,
            baseline_correct=not case.challenge,
        )
        for case in plan.cases
    )


def test_authorization_is_canonical_and_bound_to_every_frozen_identity() -> None:
    plan, payload, authorization, _ = _protocol()
    audit, qualification = _receipts(plan)

    assert payload == (
        json.dumps(
            json.loads(payload.decode("ascii")),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )
    assert authorization.plan_sha256 == plan.plan_sha256
    assert authorization.execution_source_bundle_sha256 == (plan.execution_source_bundle_sha256)
    assert authorization.model_canonical_sha256 == plan.model_canonical_sha256
    assert authorization.model_file_sha256 == plan.model_file_sha256
    assert authorization.teacher_execution_sha256 == plan.teacher_execution_sha256
    assert authorization.external_audit_receipt_sha256 == audit.receipt_sha256
    assert authorization.non_test_adapter_qualification_receipt_sha256 == (
        qualification.receipt_sha256
    )
    assert authorization.authorization_sha256 == hashlib.sha256(payload).hexdigest()

    changed = json.loads(payload.decode("ascii"))
    changed["acknowledgements"]["publish_regardless_of_outcome"] = False
    changed_payload = (
        json.dumps(changed, separators=(",", ":"), sort_keys=True).encode("ascii") + b"\n"
    )
    with pytest.raises(StrategicSealedEvaluationError, match="incomplete"):
        parse_strategic_sealed_authorization(
            changed_payload,
            plan=plan,
            external_audit_receipt=audit,
            non_test_adapter_qualification_receipt=qualification,
        )

    with pytest.raises(StrategicSealedEvaluationError, match="canonical loader"):
        StrategicSealedEvaluationPlan(
            plan_sha256=plan.plan_sha256,
            payload_bytes=plan.payload_bytes,
            evaluation_id=plan.evaluation_id,
            execution_source_bundle_sha256=plan.execution_source_bundle_sha256,
            model_canonical_sha256=plan.model_canonical_sha256,
            model_file_sha256=plan.model_file_sha256,
            source_scenario_registry_sha256=plan.source_scenario_registry_sha256,
            teacher_execution_sha256=plan.teacher_execution_sha256,
            cases=plan.cases,
            _validation_token=object(),
        )
    with pytest.raises(StrategicSealedEvaluationError, match="canonical parser"):
        StrategicSealedAuthorization(
            authorization_sha256=authorization.authorization_sha256,
            authorization_id=authorization.authorization_id,
            authorized_by=authorization.authorized_by,
            authorized_on=authorization.authorized_on,
            source_commit=authorization.source_commit,
            plan_sha256=authorization.plan_sha256,
            execution_source_bundle_sha256=(authorization.execution_source_bundle_sha256),
            model_canonical_sha256=authorization.model_canonical_sha256,
            model_file_sha256=authorization.model_file_sha256,
            teacher_execution_sha256=authorization.teacher_execution_sha256,
            case_catalog_sha256=authorization.case_catalog_sha256,
            external_audit_receipt_sha256=(authorization.external_audit_receipt_sha256),
            non_test_adapter_qualification_receipt_sha256=(
                authorization.non_test_adapter_qualification_receipt_sha256
            ),
            _validation_token=object(),
        )
    with pytest.raises((TypeError, ValueError), match="InitVar"):
        replace(plan, plan_sha256="f" * 64)
    with pytest.raises((TypeError, ValueError), match="InitVar"):
        replace(authorization, case_catalog_sha256="e" * 64)
    with pytest.raises(StrategicSealedEvaluationError, match="canonical parser"):
        StrategicSealedExternalAuditReceipt(
            receipt_sha256=audit.receipt_sha256,
            receipt_id=audit.receipt_id,
            issued_by=audit.issued_by,
            issued_on=audit.issued_on,
            source_commit=audit.source_commit,
            plan_sha256=audit.plan_sha256,
            execution_source_bundle_sha256=(audit.execution_source_bundle_sha256),
            evidence_sha256=audit.evidence_sha256,
            verdict=audit.verdict,
            _validation_token=object(),
        )
    with pytest.raises(StrategicSealedEvaluationError, match="canonical parser"):
        StrategicSealedNonTestQualificationReceipt(
            receipt_sha256=qualification.receipt_sha256,
            receipt_id=qualification.receipt_id,
            issued_by=qualification.issued_by,
            issued_on=qualification.issued_on,
            source_commit=qualification.source_commit,
            plan_sha256=qualification.plan_sha256,
            execution_source_bundle_sha256=(qualification.execution_source_bundle_sha256),
            evidence_sha256=qualification.evidence_sha256,
            verdict=qualification.verdict,
            sealed_test_cases_opened=qualification.sealed_test_cases_opened,
            _validation_token=object(),
        )
    with pytest.raises((TypeError, ValueError), match="InitVar"):
        replace(audit, verdict="changes_required")
    with pytest.raises((TypeError, ValueError), match="InitVar"):
        replace(qualification, verdict="failed")


def test_typed_evidence_receipts_reject_unfavorable_or_stale_claims() -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    approved_audit, passed_qualification = _receipts(plan)
    live_only_audit, _ = _receipts(
        plan,
        audit_verdict="approved_for_live_qualification",
        suffix="live-only",
    )
    _, failed_qualification = _receipts(
        plan,
        qualification_verdict="failed",
        suffix="failed",
    )
    approved_payload = build_strategic_sealed_authorization(
        plan,
        authorization_id="approved-control",
        authorized_by="test-owner",
        authorized_on="2026-08-13",
        source_commit=SOURCE_COMMIT,
        case_catalog_sha256=CASE_CATALOG_SHA256,
        external_audit_receipt=approved_audit,
        non_test_adapter_qualification_receipt=passed_qualification,
    )

    with pytest.raises(
        StrategicSealedEvaluationError,
        match="did not approve authorization",
    ):
        build_strategic_sealed_authorization(
            plan,
            authorization_id="must-refuse-live-only-audit",
            authorized_by="test-owner",
            authorized_on="2026-08-13",
            source_commit=SOURCE_COMMIT,
            case_catalog_sha256=CASE_CATALOG_SHA256,
            external_audit_receipt=live_only_audit,
            non_test_adapter_qualification_receipt=passed_qualification,
        )
    with pytest.raises(
        StrategicSealedEvaluationError,
        match="did not pass cleanly",
    ):
        build_strategic_sealed_authorization(
            plan,
            authorization_id="must-refuse-failed-qualification",
            authorized_by="test-owner",
            authorized_on="2026-08-13",
            source_commit=SOURCE_COMMIT,
            case_catalog_sha256=CASE_CATALOG_SHA256,
            external_audit_receipt=approved_audit,
            non_test_adapter_qualification_receipt=failed_qualification,
        )
    with pytest.raises(
        StrategicSealedEvaluationError,
        match="did not approve authorization",
    ):
        parse_strategic_sealed_authorization(
            approved_payload,
            plan=plan,
            external_audit_receipt=live_only_audit,
            non_test_adapter_qualification_receipt=passed_qualification,
        )

    stale_payload = build_strategic_sealed_external_audit_receipt(
        plan,
        receipt_id="stale-external-audit",
        issued_by="independent-auditor",
        issued_on="2026-08-13",
        source_commit="9" * 40,
        evidence_sha256=EXTERNAL_AUDIT_EVIDENCE_SHA256,
        verdict="approved_for_authorization",
    )
    with pytest.raises(StrategicSealedEvaluationError, match="source commit differs"):
        parse_strategic_sealed_external_audit_receipt(
            stale_payload,
            plan=plan,
            source_commit=SOURCE_COMMIT,
        )

    invalid_verdict = json.loads(stale_payload.decode("ascii"))
    invalid_verdict["source_commit"] = SOURCE_COMMIT
    invalid_verdict["verdict"] = "approved"
    with pytest.raises(StrategicSealedEvaluationError, match="verdict is invalid"):
        parse_strategic_sealed_external_audit_receipt(
            _canonical(invalid_verdict),
            plan=plan,
            source_commit=SOURCE_COMMIT,
        )

    opened_test = json.loads(
        build_strategic_sealed_non_test_qualification_receipt(
            plan,
            receipt_id="non-test-qualification-zero",
            issued_by="qualification-runner",
            issued_on="2026-08-13",
            source_commit=SOURCE_COMMIT,
            evidence_sha256=NON_TEST_ADAPTER_QUALIFICATION_EVIDENCE_SHA256,
            verdict="passed",
        ).decode("ascii")
    )
    opened_test["sealed_test_cases_opened"] = 1
    with pytest.raises(StrategicSealedEvaluationError, match="opened a test case"):
        parse_strategic_sealed_non_test_qualification_receipt(
            _canonical(opened_test),
            plan=plan,
            source_commit=SOURCE_COMMIT,
        )


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("schema", "wrong-schema", "schema differs"),
        ("evaluation_id", "wrong-evaluation", "evaluation differs"),
        ("plan_sha256", "d" * 64, "plan differs"),
        ("execution_source_bundle_sha256", "e" * 64, "source bundle differs"),
    ),
)
def test_external_audit_receipt_parser_refuses_identity_drift(
    field: str,
    replacement: str,
    message: str,
) -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    payload = json.loads(
        build_strategic_sealed_external_audit_receipt(
            plan,
            receipt_id="external-audit-identity-control",
            issued_by="independent-auditor",
            issued_on="2026-08-13",
            source_commit=SOURCE_COMMIT,
            evidence_sha256=EXTERNAL_AUDIT_EVIDENCE_SHA256,
            verdict="approved_for_authorization",
        ).decode("ascii")
    )
    payload[field] = replacement

    with pytest.raises(StrategicSealedEvaluationError, match=message):
        parse_strategic_sealed_external_audit_receipt(
            _canonical(payload),
            plan=plan,
            source_commit=SOURCE_COMMIT,
        )


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("schema", "wrong-schema", "schema differs"),
        ("evaluation_id", "wrong-evaluation", "evaluation differs"),
        ("plan_sha256", "d" * 64, "plan differs"),
        ("execution_source_bundle_sha256", "e" * 64, "source bundle differs"),
        ("production_path", "alternate-path", "production path differs"),
    ),
)
def test_non_test_qualification_receipt_parser_refuses_identity_drift(
    field: str,
    replacement: str,
    message: str,
) -> None:
    plan = load_strategic_sealed_evaluation_plan(PROJECT_ROOT)
    payload = json.loads(
        build_strategic_sealed_non_test_qualification_receipt(
            plan,
            receipt_id="non-test-qualification-identity-control",
            issued_by="qualification-runner",
            issued_on="2026-08-13",
            source_commit=SOURCE_COMMIT,
            evidence_sha256=NON_TEST_ADAPTER_QUALIFICATION_EVIDENCE_SHA256,
            verdict="passed",
        ).decode("ascii")
    )
    payload[field] = replacement

    with pytest.raises(StrategicSealedEvaluationError, match=message):
        parse_strategic_sealed_non_test_qualification_receipt(
            _canonical(payload),
            plan=plan,
            source_commit=SOURCE_COMMIT,
        )


def test_runtime_grant_cannot_be_forged_or_issued_for_a_preflight_mismatch() -> None:
    plan, _, authorization, grant = _protocol()
    audit, qualification = _receipts(plan)

    with pytest.raises(StrategicSealedEvaluationError, match="come from the preflight"):
        StrategicSealedRuntimeGrant(
            plan_sha256=plan.plan_sha256,
            authorization_sha256=authorization.authorization_sha256,
            source_commit=SOURCE_COMMIT,
            teacher_execution_sha256=plan.teacher_execution_sha256,
            case_catalog_sha256=CASE_CATALOG_SHA256,
            external_audit_receipt_sha256=audit.receipt_sha256,
            non_test_adapter_qualification_receipt_sha256=(qualification.receipt_sha256),
            _validation_token=object(),
        )
    with pytest.raises((TypeError, ValueError), match="InitVar"):
        replace(grant, source_commit="b" * 40)
    assert grant.external_audit_receipt_sha256 == audit.receipt_sha256
    assert grant.non_test_adapter_qualification_receipt_sha256 == (qualification.receipt_sha256)
    with pytest.raises(StrategicSealedEvaluationError, match="case catalog differs"):
        require_strategic_sealed_runtime_preflight(
            plan,
            authorization,
            source_commit=SOURCE_COMMIT,
            source_bundle_sha256=plan.execution_source_bundle_sha256,
            source_clean=True,
            source_published=True,
            model_canonical_sha256=plan.model_canonical_sha256,
            model_file_sha256=plan.model_file_sha256,
            teacher_execution_sha256=plan.teacher_execution_sha256,
            case_catalog_sha256="3" * 64,
            external_audit_receipt=audit,
            non_test_adapter_qualification_receipt=qualification,
        )
    with pytest.raises(
        StrategicSealedEvaluationError,
        match="external audit receipt differs",
    ):
        require_strategic_sealed_runtime_preflight(
            plan,
            authorization,
            source_commit=SOURCE_COMMIT,
            source_bundle_sha256=plan.execution_source_bundle_sha256,
            source_clean=True,
            source_published=True,
            model_canonical_sha256=plan.model_canonical_sha256,
            model_file_sha256=plan.model_file_sha256,
            teacher_execution_sha256=plan.teacher_execution_sha256,
            case_catalog_sha256=CASE_CATALOG_SHA256,
            external_audit_receipt=_receipts(plan, suffix="v2")[0],
            non_test_adapter_qualification_receipt=qualification,
        )
    with pytest.raises(
        StrategicSealedEvaluationError,
        match="non-test adapter qualification receipt differs",
    ):
        require_strategic_sealed_runtime_preflight(
            plan,
            authorization,
            source_commit=SOURCE_COMMIT,
            source_bundle_sha256=plan.execution_source_bundle_sha256,
            source_clean=True,
            source_published=True,
            model_canonical_sha256=plan.model_canonical_sha256,
            model_file_sha256=plan.model_file_sha256,
            teacher_execution_sha256=plan.teacher_execution_sha256,
            case_catalog_sha256=CASE_CATALOG_SHA256,
            external_audit_receipt=audit,
            non_test_adapter_qualification_receipt=(_receipts(plan, suffix="v2")[1]),
        )
    with pytest.raises(StrategicSealedEvaluationError, match="clean published"):
        require_strategic_sealed_runtime_preflight(
            plan,
            authorization,
            source_commit=SOURCE_COMMIT,
            source_bundle_sha256=plan.execution_source_bundle_sha256,
            source_clean=False,
            source_published=True,
            model_canonical_sha256=plan.model_canonical_sha256,
            model_file_sha256=plan.model_file_sha256,
            teacher_execution_sha256=plan.teacher_execution_sha256,
            case_catalog_sha256=CASE_CATALOG_SHA256,
            external_audit_receipt=audit,
            non_test_adapter_qualification_receipt=qualification,
        )


def test_executor_requires_the_prepared_session_abort_boundary_before_start(
    tmp_path: Path,
) -> None:
    _, store = _store(tmp_path)
    plan, _, authorization, grant = _protocol()
    calls: list[str] = []

    class MissingAbort:
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            calls.append(case.case_id)
            return _prediction(case, baseline_correct=False)

        def execute_teacher(
            self, case: StrategicSealedEvaluationCase
        ) -> StrategicSealedTeacherResult:
            return _teacher(case)

    with pytest.raises(TypeError, match="runner is incomplete"):
        execute_strategic_sealed_evaluation(
            store,
            plan=plan,
            authorization=authorization,
            runtime_grant=grant,
            runner=MissingAbort(),
        )

    assert calls == []
    namespace = sealed._execution_namespace(plan)
    assert (
        store.find_sealed_record(
            sealed._record_id("start", namespace),
            expected_kind="strategic_sealed_start",
        )
        is None
    )


def test_scorer_refuses_every_incomplete_series_without_computing_a_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, _, authorization, _ = _protocol()
    calls: list[tuple[int, int]] = []

    def reject_early_metric(wins: int, losses: int) -> float:
        calls.append((wins, losses))
        raise AssertionError("an incomplete evaluation computed a statistic")

    monkeypatch.setattr(sealed, "_paired_two_sided_exact_p", reject_early_metric)

    rows = _passing_outcomes(plan)
    for size in range(sealed.SEALED_EVALUATION_CASES):
        with pytest.raises(StrategicSealedEvaluationError, match="no metric is available"):
            score_strategic_sealed_evaluation(
                plan,
                rows[:size],
                authorization=authorization,
                halt_observed=False,
            )
    with pytest.raises(StrategicSealedEvaluationError, match="no metric is available"):
        score_strategic_sealed_evaluation(
            plan,
            (*rows, rows[0]),
            authorization=authorization,
            halt_observed=False,
        )
    assert calls == []


def test_scorer_uses_only_challenges_for_primary_and_reports_safety_separately() -> None:
    plan, _, authorization, _ = _protocol()
    rows = list(_passing_outcomes(plan))
    first_safety = next(case for case in plan.cases if not case.challenge)
    rows[first_safety.ordinal - 1] = _success(
        first_safety,
        model_correct=False,
        baseline_correct=True,
    )

    result = score_strategic_sealed_evaluation(
        plan,
        rows,
        authorization=authorization,
        halt_observed=False,
    ).public_dict()

    assert result["primary"] == {
        "both_correct": 0,
        "both_wrong": 0,
        "capability_floor_met": True,
        "cases": 10,
        "losses": 0,
        "measured_teacher_baseline_disagreements": 10,
        "model_better_direction_met": True,
        "successful_teacher_cases": 10,
        "significance_threshold": 0.05,
        "significant": True,
        "two_sided_exact_p": 0.001953125,
        "wins": 10,
    }
    assert result["safety"] == {
        "cases": 2,
        "model_incorrect_baseline_correct": 1,
        "passed": False,
        "successful_teacher_cases": 2,
    }
    assert result["offline_gate_passed"] is False
    assert result["live_authority"] == {
        "blocked": True,
        "granted_by_this_result": False,
    }
    candidate_results = result["candidate_count_results"]
    case_results = result["case_results"]
    assert isinstance(candidate_results, list)
    assert all(isinstance(row, dict) for row in candidate_results)
    assert isinstance(case_results, list)
    assert [row["cases"] for row in candidate_results] == [
        6,
        4,
        1,
        1,
    ]
    assert len(case_results) == 12


def test_unsuccessful_teacher_case_can_never_create_a_favorable_gate() -> None:
    plan, _, authorization, _ = _protocol()
    rows = list(_passing_outcomes(plan))
    challenge = next(case for case in plan.cases if case.challenge)
    rows[challenge.ordinal - 1] = sealed.failed_strategic_sealed_case_outcome(
        challenge,
        status="failed",
    )

    result = score_strategic_sealed_evaluation(
        plan,
        rows,
        authorization=authorization,
        halt_observed=False,
    ).public_dict()

    protocol = result["protocol"]
    primary = result["primary"]
    assert isinstance(protocol, dict)
    assert isinstance(primary, dict)
    assert protocol["valid"] is False
    assert "primary_case_without_successful_teacher_target" in protocol["protocol_failure_reasons"]
    assert primary["successful_teacher_cases"] == 9
    assert result["offline_gate_passed"] is False
    assert result["status"] == "protocol_failure"


def test_executor_claims_before_access_and_never_emits_intermediate_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, store = _store(tmp_path)
    plan, _, authorization, grant = _protocol()
    namespace = sealed._execution_namespace(plan)
    seen: list[str] = []
    progress: list[dict[str, object]] = []
    statistic_calls: list[tuple[int, int]] = []
    exact_test = sealed._paired_two_sided_exact_p

    def observe_exact_test(wins: int, losses: int) -> float:
        assert len(seen) == 12
        statistic_calls.append((wins, losses))
        return exact_test(wins, losses)

    monkeypatch.setattr(sealed, "_paired_two_sided_exact_p", observe_exact_test)

    class Runner(_NoopAbort):
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            claim = store.find_sealed_record(
                sealed._case_record_id("claim", case.ordinal, namespace),
                expected_kind="strategic_sealed_claim",
            )
            assert claim is not None
            assert claim.read()["private_input_access_may_begin"] is True
            seen.append(case.case_id)
            return _prediction(case, baseline_correct=not case.challenge)

        def execute_teacher(
            self, case: StrategicSealedEvaluationCase
        ) -> StrategicSealedTeacherResult:
            commitment = store.find_sealed_record(
                sealed._case_record_id("prediction", case.ordinal, namespace),
                expected_kind="strategic_sealed_prediction",
            )
            assert commitment is not None
            return _teacher(case)

    def observe_progress(item: StrategicSealedProgress) -> None:
        assert statistic_calls == []
        progress.append(item.public_dict())

    result = execute_strategic_sealed_evaluation(
        store,
        plan=plan,
        authorization=authorization,
        runtime_grant=grant,
        runner=Runner(),
        progress=observe_progress,
    ).public_dict()

    assert seen == list(plan.case_order)
    assert progress == [
        {
            "consumed_cases": ordinal,
            "declared_cases": 12,
            "metrics_available": False,
            "schema": "strategic-sealed-evaluation-progress-v1",
        }
        for ordinal in range(1, 13)
    ]
    assert result["status"] == "passed"
    protocol = result["protocol"]
    assert isinstance(protocol, dict)
    assert protocol["intermediate_metrics_emitted"] is False
    assert statistic_calls == [(10, 0)]


def test_executor_aborts_prepared_sessions_for_every_caught_runner_failure(
    tmp_path: Path,
) -> None:
    _, store = _store(tmp_path)
    plan, _, authorization, grant = _protocol()
    aborted: list[int] = []

    class Runner:
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            if case.ordinal == 1:
                raise sealed.StrategicSealedCandidateUnavailableError(
                    "synthetic unavailable candidate"
                )
            if case.ordinal == 2:
                raise RuntimeError("synthetic preparation failure")
            return _prediction(case, baseline_correct=not case.challenge)

        def execute_teacher(
            self, case: StrategicSealedEvaluationCase
        ) -> StrategicSealedTeacherResult:
            if case.ordinal == 3:
                raise RuntimeError("synthetic teacher failure")
            return _teacher(case)

        def abort(self, case: StrategicSealedEvaluationCase) -> None:
            aborted.append(case.ordinal)

    result = execute_strategic_sealed_evaluation(
        store,
        plan=plan,
        authorization=authorization,
        runtime_grant=grant,
        runner=Runner(),
    ).public_dict()

    assert aborted == [1, 2, 3]
    case_results = result["case_results"]
    assert isinstance(case_results, list)
    assert [row["execution_status"] for row in case_results[:3]] == [
        "candidate_unavailable",
        "failed",
        "failed",
    ]
    assert result["status"] == "protocol_failure"

    rerun_calls: list[str] = []

    class RejectRerun(_NoopAbort):
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            rerun_calls.append(case.case_id)
            return _prediction(case, baseline_correct=False)

        def execute_teacher(
            self, case: StrategicSealedEvaluationCase
        ) -> StrategicSealedTeacherResult:
            rerun_calls.append(case.case_id)
            return _teacher(case)

    repeated = execute_strategic_sealed_evaluation(
        store,
        plan=plan,
        authorization=authorization,
        runtime_grant=grant,
        runner=RejectRerun(),
    ).public_dict()
    assert rerun_calls == []
    assert repeated == result


def test_second_authorization_cannot_create_a_fresh_ledger_for_the_same_plan(
    tmp_path: Path,
) -> None:
    _, store = _store(tmp_path)
    plan, _, authorization, grant = _protocol()

    class Finish(_NoopAbort):
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            return _prediction(case, baseline_correct=not case.challenge)

        def execute_teacher(
            self, case: StrategicSealedEvaluationCase
        ) -> StrategicSealedTeacherResult:
            return _teacher(case)

    execute_strategic_sealed_evaluation(
        store,
        plan=plan,
        authorization=authorization,
        runtime_grant=grant,
        runner=Finish(),
    )

    audit, qualification = _receipts(plan)
    second_payload = build_strategic_sealed_authorization(
        plan,
        authorization_id="peter-one-shot-v2",
        authorized_by="peterandrews",
        authorized_on="2026-08-14",
        source_commit=SOURCE_COMMIT,
        case_catalog_sha256=CASE_CATALOG_SHA256,
        external_audit_receipt=audit,
        non_test_adapter_qualification_receipt=qualification,
    )
    second = parse_strategic_sealed_authorization(
        second_payload,
        plan=plan,
        external_audit_receipt=audit,
        non_test_adapter_qualification_receipt=qualification,
    )
    second_grant = require_strategic_sealed_runtime_preflight(
        plan,
        second,
        source_commit=SOURCE_COMMIT,
        source_bundle_sha256=plan.execution_source_bundle_sha256,
        source_clean=True,
        source_published=True,
        model_canonical_sha256=plan.model_canonical_sha256,
        model_file_sha256=plan.model_file_sha256,
        teacher_execution_sha256=plan.teacher_execution_sha256,
        case_catalog_sha256=CASE_CATALOG_SHA256,
        external_audit_receipt=audit,
        non_test_adapter_qualification_receipt=qualification,
    )
    calls: list[str] = []

    class RejectSecondRun(Finish):
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            calls.append(case.case_id)
            return super().prepare(case)

    with pytest.raises(StrategicSealedEvaluationError, match="start record differs"):
        execute_strategic_sealed_evaluation(
            store,
            plan=plan,
            authorization=second,
            runtime_grant=second_grant,
            runner=RejectSecondRun(),
        )
    assert calls == []


def test_crash_consumes_open_case_and_restart_never_reopens_it(tmp_path: Path) -> None:
    _, store = _store(tmp_path)
    plan, _, authorization, grant = _protocol()
    opened: list[str] = []

    class Crash(_NoopAbort):
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            opened.append(case.case_id)
            return _prediction(case, baseline_correct=not case.challenge)

        def execute_teacher(
            self, case: StrategicSealedEvaluationCase
        ) -> StrategicSealedTeacherResult:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        execute_strategic_sealed_evaluation(
            store,
            plan=plan,
            authorization=authorization,
            runtime_grant=grant,
            runner=Crash(),
        )
    assert opened == [plan.case_order[0]]

    resumed: list[str] = []

    class Finish(_NoopAbort):
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            resumed.append(case.case_id)
            return _prediction(case, baseline_correct=not case.challenge)

        def execute_teacher(
            self, case: StrategicSealedEvaluationCase
        ) -> StrategicSealedTeacherResult:
            return _teacher(case)

    result = execute_strategic_sealed_evaluation(
        store,
        plan=plan,
        authorization=authorization,
        runtime_grant=grant,
        runner=Finish(),
    ).public_dict()

    assert resumed == list(plan.case_order[1:])
    case_results = result["case_results"]
    live_authority = result["live_authority"]
    assert isinstance(case_results, list)
    assert all(isinstance(row, dict) for row in case_results)
    assert isinstance(live_authority, dict)
    assert case_results[0]["execution_status"] == "interrupted"
    assert result["protocol"] == {
        "all_cases_consumed_before_scoring": True,
        "halt_observed": True,
        "intermediate_metrics_emitted": False,
        "protocol_failure_reasons": ["executor_halted_after_case_open"],
        "valid": False,
    }
    assert result["status"] == "protocol_failure"
    assert live_authority["blocked"] is True


def test_crash_before_the_first_claim_consumes_no_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, store = _store(tmp_path)
    plan, _, authorization, grant = _protocol()
    namespace = sealed._execution_namespace(plan)
    original_publish_claim = sealed._publish_claim
    attempts = 0

    def crash_once(*args, **kwargs) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise KeyboardInterrupt
        original_publish_claim(*args, **kwargs)

    monkeypatch.setattr(sealed, "_publish_claim", crash_once)
    opened: list[str] = []

    class Finish(_NoopAbort):
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            opened.append(case.case_id)
            return _prediction(case, baseline_correct=not case.challenge)

        def execute_teacher(
            self, case: StrategicSealedEvaluationCase
        ) -> StrategicSealedTeacherResult:
            return _teacher(case)

    with pytest.raises(KeyboardInterrupt):
        execute_strategic_sealed_evaluation(
            store,
            plan=plan,
            authorization=authorization,
            runtime_grant=grant,
            runner=Finish(),
        )
    assert opened == []
    assert not sealed._has_halt(
        store,
        plan=plan,
        authorization=authorization,
        namespace=namespace,
    )

    result = execute_strategic_sealed_evaluation(
        store,
        plan=plan,
        authorization=authorization,
        runtime_grant=grant,
        runner=Finish(),
    ).public_dict()
    assert opened == list(plan.case_order)
    assert result["status"] == "passed"


def test_runner_identity_mismatch_is_consumed_and_forces_protocol_failure(
    tmp_path: Path,
) -> None:
    _, store = _store(tmp_path)
    plan, _, authorization, grant = _protocol()
    aborted: list[str] = []

    class WrongCase(_NoopAbort):
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            wrong = plan.cases[case.ordinal % len(plan.cases)]
            return _prediction(wrong, baseline_correct=False)

        def execute_teacher(
            self, case: StrategicSealedEvaluationCase
        ) -> StrategicSealedTeacherResult:
            return _teacher(case)

        def abort(self, case: StrategicSealedEvaluationCase) -> None:
            aborted.append(case.case_id)

    with pytest.raises(StrategicSealedEvaluationError, match="prediction differs"):
        execute_strategic_sealed_evaluation(
            store,
            plan=plan,
            authorization=authorization,
            runtime_grant=grant,
            runner=WrongCase(),
        )
    assert aborted == [plan.case_order[0]]

    resumed: list[str] = []

    class Finish(_NoopAbort):
        def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
            resumed.append(case.case_id)
            return _prediction(case, baseline_correct=not case.challenge)

        def execute_teacher(
            self, case: StrategicSealedEvaluationCase
        ) -> StrategicSealedTeacherResult:
            return _teacher(case)

    result = execute_strategic_sealed_evaluation(
        store,
        plan=plan,
        authorization=authorization,
        runtime_grant=grant,
        runner=Finish(),
    ).public_dict()
    assert resumed == list(plan.case_order[1:])
    case_results = result["case_results"]
    assert isinstance(case_results, list)
    assert all(isinstance(row, dict) for row in case_results)
    assert case_results[0]["execution_status"] == "interrupted"
    assert result["status"] == "protocol_failure"
