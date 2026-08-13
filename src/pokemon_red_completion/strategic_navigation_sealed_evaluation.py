"""Fail-closed orchestration and final-only scoring for the strategic test.

The public plan fixes case order, scoring, and authority before any private
test state is opened.  This module supplies the state machine that makes those
declarations operational:

* every case is durably claimed before its private input is touched;
* a claimed case can never be reopened, including after process restart;
* a restart after case one marks the whole evaluation as a protocol failure;
* no statistic exists until all twelve case outcomes are present; and
* the two safety cases never enter the ten-case primary paired test.

Private case measurements live in immutable sealed records.  Only the final
aggregate is public.  The runner callback is deliberately injected so the
ROM-free protocol can be attacked independently from the emulator adapter.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import InitVar, dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol

from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    PrivateSealedRecord,
)
from pokemon_red_completion.provenance import canonical_sha256

SEALED_EVALUATION_PLAN_RELATIVE_PATH = "configs/red-strategic-navigation-sealed-evaluation-v1.json"
SEALED_EVALUATION_PLAN_DIGEST_RELATIVE_PATH = (
    "configs/red-strategic-navigation-sealed-evaluation-v1.digest.json"
)
SEALED_EVALUATION_PLAN_SCHEMA = "pokemon-strategic-navigation-sealed-evaluation-plan-v8"
SEALED_EVALUATION_PLAN_DIGEST_SCHEMA = (
    "pokemon-strategic-navigation-sealed-evaluation-plan-digest-v8"
)
SEALED_EVALUATION_AUTHORIZATION_SCHEMA = (
    "pokemon-strategic-navigation-sealed-evaluation-authorization-v3"
)
SEALED_EVALUATION_EXTERNAL_AUDIT_RECEIPT_SCHEMA = (
    "pokemon-strategic-navigation-sealed-external-audit-receipt-v1"
)
SEALED_EVALUATION_NON_TEST_QUALIFICATION_RECEIPT_SCHEMA = (
    "pokemon-strategic-navigation-sealed-non-test-qualification-receipt-v1"
)
SEALED_EVALUATION_CASE_OUTCOME_SCHEMA = "pokemon-strategic-navigation-sealed-case-outcome-v1"
SEALED_EVALUATION_PREDICTION_SCHEMA = "pokemon-strategic-navigation-sealed-prediction-v1"
SEALED_EVALUATION_RESULT_SCHEMA = "pokemon-strategic-navigation-sealed-evaluation-result-v1"
SEALED_EVALUATION_ID = "red-strategic-navigation-sealed-evaluation-v1"
SEALED_EVALUATION_CASES = 12
SEALED_EVALUATION_PRIMARY_CASES = 10
SEALED_EVALUATION_SAFETY_CASES = 2
SEALED_EVALUATION_MINIMUM_DISAGREEMENTS = 6

_MAX_PLAN_BYTES = 1024 * 1024
_MAX_AUTHORIZATION_BYTES = 64 * 1024
_MAX_EVIDENCE_RECEIPT_BYTES = 64 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_DATE = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]\Z")
_PLAN_VALIDATION_TOKEN = object()
_EXTERNAL_AUDIT_RECEIPT_VALIDATION_TOKEN = object()
_NON_TEST_QUALIFICATION_RECEIPT_VALIDATION_TOKEN = object()
_AUTHORIZATION_VALIDATION_TOKEN = object()
_PREFLIGHT_VALIDATION_TOKEN = object()


class StrategicSealedEvaluationError(RuntimeError):
    """Raised when a sealed-test action would weaken the frozen protocol."""


class StrategicSealedCandidateUnavailableError(StrategicSealedEvaluationError):
    """Report a genuine unavailable frontier only after its case was claimed."""


@dataclass(frozen=True, slots=True)
class StrategicSealedEvaluationCase:
    """One public, ordered case identity from the frozen plan."""

    case_id: str
    case_sha256: str
    source_scenario_id: str
    source_scenario_sha256: str
    origin_region: str
    challenge: bool
    challenged_non_teacher_objective_id: str | None
    candidate_count: int
    ordinal: int


@dataclass(frozen=True, slots=True)
class StrategicSealedEvaluationPlan:
    """The exact public contract consumed by the executor and scorer."""

    plan_sha256: str
    payload_bytes: int
    evaluation_id: str
    execution_source_bundle_sha256: str
    model_canonical_sha256: str
    model_file_sha256: str
    source_scenario_registry_sha256: str
    teacher_execution_sha256: str
    cases: tuple[StrategicSealedEvaluationCase, ...]
    _validation_token: InitVar[object]

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _PLAN_VALIDATION_TOKEN:
            raise StrategicSealedEvaluationError(
                "sealed evaluation plans must come from the canonical loader"
            )

    @property
    def case_order(self) -> tuple[str, ...]:
        return tuple(case.case_id for case in self.cases)

    @property
    def primary_cases(self) -> tuple[StrategicSealedEvaluationCase, ...]:
        return tuple(case for case in self.cases if case.challenge)

    @property
    def safety_cases(self) -> tuple[StrategicSealedEvaluationCase, ...]:
        return tuple(case for case in self.cases if not case.challenge)

    def case(self, case_id: str) -> StrategicSealedEvaluationCase:
        matches = tuple(case for case in self.cases if case.case_id == case_id)
        if len(matches) != 1:
            raise StrategicSealedEvaluationError("sealed evaluation case is unavailable")
        return matches[0]


@dataclass(frozen=True, slots=True)
class StrategicSealedExternalAuditReceipt:
    """Typed audit verdict bound to the exact source proposed for authorization."""

    receipt_sha256: str
    receipt_id: str
    issued_by: str
    issued_on: str
    source_commit: str
    plan_sha256: str
    execution_source_bundle_sha256: str
    evidence_sha256: str
    verdict: str
    _validation_token: InitVar[object]

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _EXTERNAL_AUDIT_RECEIPT_VALIDATION_TOKEN:
            raise StrategicSealedEvaluationError(
                "sealed external audit receipts must come from the canonical parser"
            )


@dataclass(frozen=True, slots=True)
class StrategicSealedNonTestQualificationReceipt:
    """Typed production-adapter verdict proven without opening a sealed test case."""

    receipt_sha256: str
    receipt_id: str
    issued_by: str
    issued_on: str
    source_commit: str
    plan_sha256: str
    execution_source_bundle_sha256: str
    evidence_sha256: str
    verdict: str
    sealed_test_cases_opened: int
    _validation_token: InitVar[object]

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _NON_TEST_QUALIFICATION_RECEIPT_VALIDATION_TOKEN:
            raise StrategicSealedEvaluationError(
                "sealed non-test qualification receipts must come from the canonical parser"
            )


@dataclass(frozen=True, slots=True)
class StrategicSealedAuthorization:
    """Owner acknowledgement bound to one plan, source, model, and input catalog."""

    authorization_sha256: str
    authorization_id: str
    authorized_by: str
    authorized_on: str
    source_commit: str
    plan_sha256: str
    execution_source_bundle_sha256: str
    model_canonical_sha256: str
    model_file_sha256: str
    teacher_execution_sha256: str
    case_catalog_sha256: str
    external_audit_receipt_sha256: str
    non_test_adapter_qualification_receipt_sha256: str
    _validation_token: InitVar[object]

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _AUTHORIZATION_VALIDATION_TOKEN:
            raise StrategicSealedEvaluationError(
                "sealed authorizations must come from the canonical parser"
            )


@dataclass(frozen=True, slots=True)
class StrategicSealedRuntimeGrant:
    """Opaque proof that every public refusal ran before case one."""

    plan_sha256: str
    authorization_sha256: str
    source_commit: str
    teacher_execution_sha256: str
    case_catalog_sha256: str
    external_audit_receipt_sha256: str
    non_test_adapter_qualification_receipt_sha256: str
    _validation_token: InitVar[object]
    _issued_token: object = field(init=False, repr=False, compare=False)

    def __post_init__(self, _validation_token: object) -> None:
        if _validation_token is not _PREFLIGHT_VALIDATION_TOKEN:
            raise StrategicSealedEvaluationError(
                "sealed runtime grants must come from the preflight"
            )
        object.__setattr__(self, "_issued_token", _validation_token)


@dataclass(frozen=True, slots=True)
class StrategicSealedPrediction:
    """Model and baseline choices committed before the teacher may act."""

    case_id: str
    case_sha256: str
    ordinal: int
    candidate_count: int
    model_prediction_index: int | None
    model_prediction_tied: bool
    baseline_prediction_index: int | None
    baseline_prediction_tied: bool
    policy_input_sha256: str

    def __post_init__(self) -> None:
        _safe_id(self.case_id, subject="sealed prediction case identity")
        _sha256(self.case_sha256, subject="sealed prediction case digest")
        _integer(
            self.ordinal,
            minimum=1,
            maximum=SEALED_EVALUATION_CASES,
            subject="sealed prediction case ordinal",
        )
        _integer(
            self.candidate_count,
            minimum=2,
            maximum=5,
            subject="sealed prediction candidate count",
        )
        _validate_prediction_choice(
            self.model_prediction_index,
            tied=self.model_prediction_tied,
            candidate_count=self.candidate_count,
            subject="sealed model prediction",
        )
        _validate_prediction_choice(
            self.baseline_prediction_index,
            tied=self.baseline_prediction_tied,
            candidate_count=self.candidate_count,
            subject="sealed baseline prediction",
        )
        _sha256(self.policy_input_sha256, subject="sealed policy input")

    def private_dict(self) -> dict[str, object]:
        return {
            "baseline_prediction_index": self.baseline_prediction_index,
            "baseline_prediction_tied": self.baseline_prediction_tied,
            "candidate_count": self.candidate_count,
            "case_id": self.case_id,
            "case_sha256": self.case_sha256,
            "model_prediction_index": self.model_prediction_index,
            "model_prediction_tied": self.model_prediction_tied,
            "ordinal": self.ordinal,
            "policy_input_sha256": self.policy_input_sha256,
            "schema": SEALED_EVALUATION_PREDICTION_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class StrategicSealedTeacherResult:
    """Teacher evidence produced only after the prediction commitment exists."""

    case_id: str
    case_sha256: str
    ordinal: int
    candidate_count: int
    execution_status: str
    teacher_target_index: int | None = None
    episode_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        _safe_id(self.case_id, subject="sealed teacher case identity")
        _sha256(self.case_sha256, subject="sealed teacher case digest")
        _integer(
            self.ordinal,
            minimum=1,
            maximum=SEALED_EVALUATION_CASES,
            subject="sealed teacher case ordinal",
        )
        _integer(
            self.candidate_count,
            minimum=2,
            maximum=5,
            subject="sealed teacher candidate count",
        )
        if self.execution_status not in {"succeeded", "failed"}:
            raise StrategicSealedEvaluationError("sealed teacher result status is invalid")
        if self.execution_status == "succeeded":
            _integer(
                self.teacher_target_index,
                minimum=0,
                maximum=self.candidate_count - 1,
                subject="sealed teacher target",
            )
            _sha256(
                self.episode_manifest_sha256,
                subject="sealed episode manifest",
            )
        elif self.teacher_target_index is not None or self.episode_manifest_sha256 is not None:
            raise StrategicSealedEvaluationError(
                "failed sealed teacher result must not expose partial evidence"
            )


@dataclass(frozen=True, slots=True)
class StrategicSealedCaseOutcome:
    """One private result; failed cases intentionally retain no prediction."""

    case_id: str
    case_sha256: str
    ordinal: int
    candidate_count: int
    execution_status: str
    teacher_target_index: int | None = None
    model_prediction_index: int | None = None
    model_prediction_tied: bool = False
    baseline_prediction_index: int | None = None
    baseline_prediction_tied: bool = False
    policy_input_sha256: str | None = None
    episode_manifest_sha256: str | None = None

    def __post_init__(self) -> None:
        _safe_id(self.case_id, subject="sealed case identity")
        _sha256(self.case_sha256, subject="sealed case digest")
        _integer(
            self.ordinal,
            minimum=1,
            maximum=SEALED_EVALUATION_CASES,
            subject="sealed case ordinal",
        )
        _integer(
            self.candidate_count,
            minimum=2,
            maximum=5,
            subject="sealed case candidate count",
        )
        if self.execution_status not in {
            "succeeded",
            "failed",
            "interrupted",
            "candidate_unavailable",
        }:
            raise StrategicSealedEvaluationError("sealed case status is invalid")
        for name, tie_value in (
            ("model prediction tie", self.model_prediction_tied),
            ("baseline prediction tie", self.baseline_prediction_tied),
        ):
            if not isinstance(tie_value, bool):
                raise StrategicSealedEvaluationError(f"{name} must be boolean")
        if self.execution_status == "succeeded":
            for name, prediction_value in (
                ("teacher target", self.teacher_target_index),
                ("model prediction", self.model_prediction_index),
                ("baseline prediction", self.baseline_prediction_index),
            ):
                if prediction_value is None:
                    if name == "model prediction" and self.model_prediction_tied:
                        continue
                    if name == "baseline prediction" and self.baseline_prediction_tied:
                        continue
                    raise StrategicSealedEvaluationError(f"successful sealed case lacks {name}")
                _integer(
                    prediction_value,
                    minimum=0,
                    maximum=self.candidate_count - 1,
                    subject=name,
                )
            if self.model_prediction_tied and self.model_prediction_index is not None:
                raise StrategicSealedEvaluationError(
                    "tied model prediction must not select a candidate"
                )
            if self.baseline_prediction_tied and self.baseline_prediction_index is not None:
                raise StrategicSealedEvaluationError(
                    "tied baseline prediction must not select a candidate"
                )
            _sha256(self.policy_input_sha256, subject="sealed policy input")
            _sha256(self.episode_manifest_sha256, subject="sealed episode manifest")
        elif (
            any(
                value is not None
                for value in (
                    self.teacher_target_index,
                    self.model_prediction_index,
                    self.baseline_prediction_index,
                    self.policy_input_sha256,
                    self.episode_manifest_sha256,
                )
            )
            or self.model_prediction_tied
            or self.baseline_prediction_tied
        ):
            raise StrategicSealedEvaluationError(
                "unsuccessful sealed case must not expose a partial prediction"
            )

    @property
    def model_correct(self) -> bool:
        return (
            self.execution_status == "succeeded"
            and not self.model_prediction_tied
            and self.model_prediction_index == self.teacher_target_index
        )

    @property
    def baseline_correct(self) -> bool:
        return (
            self.execution_status == "succeeded"
            and not self.baseline_prediction_tied
            and self.baseline_prediction_index == self.teacher_target_index
        )

    def private_dict(self) -> dict[str, object]:
        return {
            "baseline_prediction_index": self.baseline_prediction_index,
            "baseline_prediction_tied": self.baseline_prediction_tied,
            "candidate_count": self.candidate_count,
            "case_id": self.case_id,
            "case_sha256": self.case_sha256,
            "episode_manifest_sha256": self.episode_manifest_sha256,
            "execution_status": self.execution_status,
            "model_prediction_index": self.model_prediction_index,
            "model_prediction_tied": self.model_prediction_tied,
            "ordinal": self.ordinal,
            "policy_input_sha256": self.policy_input_sha256,
            "schema": SEALED_EVALUATION_CASE_OUTCOME_SCHEMA,
            "teacher_target_index": self.teacher_target_index,
        }


@dataclass(frozen=True, slots=True)
class StrategicSealedProgress:
    """The only allowed intermediate signal; it contains no result information."""

    consumed_cases: int
    declared_cases: int = SEALED_EVALUATION_CASES

    def __post_init__(self) -> None:
        _integer(
            self.consumed_cases,
            minimum=1,
            maximum=SEALED_EVALUATION_CASES,
            subject="sealed progress",
        )
        if self.declared_cases != SEALED_EVALUATION_CASES:
            raise StrategicSealedEvaluationError("sealed progress total differs")

    def public_dict(self) -> dict[str, object]:
        return {
            "consumed_cases": self.consumed_cases,
            "declared_cases": self.declared_cases,
            "metrics_available": False,
            "schema": "strategic-sealed-evaluation-progress-v1",
        }


@dataclass(frozen=True, slots=True)
class StrategicSealedEvaluationResult:
    """The only metric-bearing object, constructible after all cases exist."""

    document: Mapping[str, object]

    def public_dict(self) -> dict[str, object]:
        return json.loads(_canonical_line(self.document).decode("ascii"))


class StrategicSealedCaseRunner(Protocol):
    """Adapter boundary that makes prediction-before-teacher order explicit."""

    def prepare(self, case: StrategicSealedEvaluationCase) -> StrategicSealedPrediction:
        """Open the claimed input and return both frozen predictions."""

    def execute_teacher(
        self,
        case: StrategicSealedEvaluationCase,
    ) -> StrategicSealedTeacherResult:
        """Execute the teacher only after the executor commits predictions."""

    def abort(self, case: StrategicSealedEvaluationCase) -> None:
        """Release a prepared input when commitment or orchestration fails."""


StrategicSealedProgressCallback = Callable[[StrategicSealedProgress], None]


def load_strategic_sealed_evaluation_plan(
    repository_root: str | Path,
) -> StrategicSealedEvaluationPlan:
    """Load the canonical plan and its independent sidecar digest."""

    root = Path(repository_root)
    plan_path = root / SEALED_EVALUATION_PLAN_RELATIVE_PATH
    digest_path = root / SEALED_EVALUATION_PLAN_DIGEST_RELATIVE_PATH
    try:
        payload = plan_path.read_bytes()
        digest_payload = digest_path.read_bytes()
    except OSError as error:
        raise StrategicSealedEvaluationError("sealed evaluation plan is unavailable") from error
    return parse_strategic_sealed_evaluation_plan(payload, digest_payload=digest_payload)


def parse_strategic_sealed_evaluation_plan(
    payload: bytes,
    *,
    digest_payload: bytes,
) -> StrategicSealedEvaluationPlan:
    """Authenticate every executor-relevant clause, not only the whole-file hash."""

    document = _decode_canonical(
        payload,
        maximum_bytes=_MAX_PLAN_BYTES,
        subject="sealed evaluation plan",
    )
    digest = _decode_canonical(
        digest_payload,
        maximum_bytes=4096,
        subject="sealed evaluation plan digest",
    )
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if digest != {
        "bytes": len(payload),
        "schema": SEALED_EVALUATION_PLAN_DIGEST_SCHEMA,
        "sha256": actual_sha256,
    }:
        raise StrategicSealedEvaluationError("sealed evaluation plan digest differs")
    _exact_keys(
        document,
        {
            "access_policy",
            "adapter_policy",
            "amendments",
            "attempt_policy",
            "baseline",
            "cases",
            "endpoint_policy",
            "evaluation_id",
            "execution_policy",
            "execution_source_bundle_sha256",
            "frozen_model",
            "minimum_challenge_hypotheses",
            "preregistered_challenge_hypotheses",
            "schema",
            "scoring_policy",
            "source_scenario_registry_sha256",
            "teacher_execution",
            "training_development_receipt_sha256",
        },
        subject="sealed evaluation plan",
    )
    if document["schema"] != SEALED_EVALUATION_PLAN_SCHEMA:
        raise StrategicSealedEvaluationError("sealed evaluation plan schema differs")
    if document["evaluation_id"] != SEALED_EVALUATION_ID:
        raise StrategicSealedEvaluationError("sealed evaluation identity differs")
    if document["access_policy"] != {
        "private_test_inputs_opened_at_freeze": 0,
        "requires_clean_published_exact_source": True,
        "requires_external_audit": (
            "typed_approved_for_authorization_receipt_bound_to_plan_source_bundle_and_commit"
        ),
        "requires_non_test_adapter_qualification": (
            "typed_passed_zero_test_access_receipt_bound_to_plan_source_bundle_and_commit"
        ),
        "requires_owner_authorization": True,
    }:
        raise StrategicSealedEvaluationError("sealed access policy differs")
    if document["adapter_policy"] != {
        "candidate_order": "source_bound_assignment_hash_v1",
        "candidate_planning": "after_authenticated_challenge_relocation",
        "case_catalog_schema": ("pokemon-strategic-navigation-sealed-case-catalog-v1"),
        "challenge_relocation": (
            "after_claim_deterministic_route_to_declared_origin_with_zero_objective_delta"
        ),
        "catalog_contains_private_paths": False,
        "catalog_contains_route_costs_or_answers": False,
        "input_representation": "unlabeled_identity_free_policy_question",
        "non_test_qualification_failure": (
            "typed_failed_receipt_zero_test_access_and_nonzero_exit"
        ),
        "private_case_open": "only_after_durable_case_claim",
        "teacher_execution": "only_after_durable_prediction_commitment",
    }:
        raise StrategicSealedEvaluationError("sealed adapter policy differs")
    if document["attempt_policy"] != {
        "attempts_per_case": 1,
        "failed_attempt_is_consumed": True,
        "omission_allowed": False,
        "publish_every_case": True,
        "rerun_allowed": False,
    }:
        raise StrategicSealedEvaluationError("sealed attempt policy differs")
    if document["baseline"] != {
        "policy_id": "unique-minimum-route-cost-v1",
        "prediction_tie": "incorrect",
    }:
        raise StrategicSealedEvaluationError("sealed baseline policy differs")
    if document["minimum_challenge_hypotheses"] != 6:
        raise StrategicSealedEvaluationError("sealed challenge minimum differs")
    if document["preregistered_challenge_hypotheses"] != (SEALED_EVALUATION_PRIMARY_CASES):
        raise StrategicSealedEvaluationError("sealed challenge count differs")
    _validate_amendments(document["amendments"])
    _validate_endpoint_policy(document["endpoint_policy"])
    _validate_scoring_policy(document["scoring_policy"])

    source_bundle = _sha256(
        document["execution_source_bundle_sha256"],
        subject="sealed execution source bundle",
    )
    source_registry = _sha256(
        document["source_scenario_registry_sha256"],
        subject="sealed source scenario registry",
    )
    teacher_execution = _mapping(document["teacher_execution"], subject="sealed teacher execution")
    _exact_keys(
        teacher_execution,
        {
            "behavior_configuration_sha256",
            "decision_contract_sha256",
            "objective_graph_sha256",
            "source_bundle_sha256",
            "teacher_execution_sha256",
        },
        subject="sealed teacher execution",
    )
    behavior_sha256 = _sha256(
        teacher_execution["behavior_configuration_sha256"],
        subject="sealed teacher behavior",
    )
    decision_contract_sha256 = _sha256(
        teacher_execution["decision_contract_sha256"],
        subject="sealed teacher decision contract",
    )
    objective_graph_sha256 = _sha256(
        teacher_execution["objective_graph_sha256"],
        subject="sealed teacher objective graph",
    )
    if teacher_execution["source_bundle_sha256"] != source_bundle:
        raise StrategicSealedEvaluationError("sealed teacher source differs")
    teacher_execution_sha256 = _sha256(
        teacher_execution["teacher_execution_sha256"],
        subject="sealed teacher execution digest",
    )
    expected_teacher_execution_sha256 = hashlib.sha256(
        _canonical_line(
            {
                "actor": "deterministic_teacher",
                "adapter_id": "pokemon.red.gb.us.rev0.v1",
                "behavior_configuration_sha256": behavior_sha256,
                "collection_id": "red-strategic-navigation-v1",
                "decision_contract_sha256": decision_contract_sha256,
                "game_id": "pokemon.mainline:red:gb:us:rev0",
                "objective_graph_sha256": objective_graph_sha256,
                "ontology_id": "pokemon.core.v1",
                "policy_id": "qualified-completion-order-v1",
                "schema": "pokemon-strategic-navigation-teacher-execution-v1",
                "source_bundle_sha256": source_bundle,
            }
        )
    ).hexdigest()
    if teacher_execution_sha256 != expected_teacher_execution_sha256:
        raise StrategicSealedEvaluationError("sealed teacher execution differs")
    _sha256(
        document["training_development_receipt_sha256"],
        subject="sealed development receipt",
    )
    model = _mapping(document["frozen_model"], subject="sealed frozen model")
    _exact_keys(
        model,
        {
            "canonical_sha256",
            "enabled_feature_names",
            "feature_schema_id",
            "feature_set_id",
            "l2",
            "model_id",
            "parameter_count",
            "private_file_sha256",
            "training_epochs",
        },
        subject="sealed frozen model",
    )
    if (
        model.get("model_id") != ("pokemon.core.strategic-navigation.destination-ranker.linear.v1")
        or model.get("feature_schema_id")
        != ("pokemon.core.strategic-navigation.destination-ranker.v1")
        or model.get("feature_set_id") != "relative_route"
    ):
        raise StrategicSealedEvaluationError("sealed model identity differs")
    if model.get("enabled_feature_names") != [
        "candidate.route_cost.relative_rank",
        "candidate.route_steps.relative_rank",
        "candidate.map_transitions.relative_rank",
        "candidate.field_actions.relative_rank",
        "candidate.mode_changes.relative_rank",
    ]:
        raise StrategicSealedEvaluationError("sealed model feature set differs")
    if (
        model.get("parameter_count") != 5
        or model.get("l2") != 0.1
        or model.get("training_epochs") != 600
    ):
        raise StrategicSealedEvaluationError("sealed model training contract differs")
    model_sha256 = _sha256(model.get("canonical_sha256"), subject="sealed model canonical digest")
    model_file_sha256 = _sha256(
        model.get("private_file_sha256"), subject="sealed model file digest"
    )

    raw_cases = document["cases"]
    if not isinstance(raw_cases, list) or len(raw_cases) != SEALED_EVALUATION_CASES:
        raise StrategicSealedEvaluationError("sealed case count differs")
    execution = _mapping(document["execution_policy"], subject="sealed execution policy")
    candidate_counts = execution.get("candidate_counts_by_case")
    if not isinstance(candidate_counts, dict):
        raise StrategicSealedEvaluationError("sealed candidate counts differ")
    cases = tuple(
        _parse_case(value, ordinal=ordinal, candidate_counts=candidate_counts)
        for ordinal, value in enumerate(raw_cases, start=1)
    )
    if len({case.case_id for case in cases}) != len(cases):
        raise StrategicSealedEvaluationError("sealed case identity is duplicated")
    if len({case.case_sha256 for case in cases}) != len(cases):
        raise StrategicSealedEvaluationError("sealed case digest is duplicated")
    if sum(case.challenge for case in cases) != SEALED_EVALUATION_PRIMARY_CASES:
        raise StrategicSealedEvaluationError("sealed primary case count differs")
    if sum(not case.challenge for case in cases) != SEALED_EVALUATION_SAFETY_CASES:
        raise StrategicSealedEvaluationError("sealed safety case count differs")
    _validate_execution_policy(execution, cases)
    return StrategicSealedEvaluationPlan(
        plan_sha256=actual_sha256,
        payload_bytes=len(payload),
        evaluation_id=SEALED_EVALUATION_ID,
        execution_source_bundle_sha256=source_bundle,
        model_canonical_sha256=model_sha256,
        model_file_sha256=model_file_sha256,
        source_scenario_registry_sha256=source_registry,
        teacher_execution_sha256=teacher_execution_sha256,
        cases=cases,
        _validation_token=_PLAN_VALIDATION_TOKEN,
    )


def build_strategic_sealed_external_audit_receipt(
    plan: StrategicSealedEvaluationPlan,
    *,
    receipt_id: str,
    issued_by: str,
    issued_on: str,
    source_commit: str,
    evidence_sha256: str,
    verdict: str,
) -> bytes:
    """Build a canonical audit attestation for an independent reviewer to issue."""

    if not isinstance(plan, StrategicSealedEvaluationPlan):
        raise TypeError("plan must be a sealed evaluation plan")
    _safe_id(receipt_id, subject="sealed external audit receipt identity")
    _safe_id(issued_by, subject="sealed external audit issuer identity")
    _require_iso_date(issued_on, subject="sealed external audit issue date")
    if _GIT_OID.fullmatch(source_commit) is None:
        raise StrategicSealedEvaluationError("sealed external audit source commit is invalid")
    _sha256(evidence_sha256, subject="sealed external audit evidence")
    _external_audit_verdict(verdict)
    return _canonical_line(
        {
            "evaluation_id": plan.evaluation_id,
            "evidence_sha256": evidence_sha256,
            "execution_source_bundle_sha256": (plan.execution_source_bundle_sha256),
            "issued_by": issued_by,
            "issued_on": issued_on,
            "plan_sha256": plan.plan_sha256,
            "receipt_id": receipt_id,
            "schema": SEALED_EVALUATION_EXTERNAL_AUDIT_RECEIPT_SCHEMA,
            "scope": "sealed_evaluation_authorization_readiness",
            "source_commit": source_commit,
            "verdict": verdict,
        }
    )


def parse_strategic_sealed_external_audit_receipt(
    payload: bytes,
    *,
    plan: StrategicSealedEvaluationPlan,
    source_commit: str,
) -> StrategicSealedExternalAuditReceipt:
    """Parse an audit verdict and reject stale or non-allowlisted attestations."""

    if not isinstance(plan, StrategicSealedEvaluationPlan):
        raise TypeError("plan must be a sealed evaluation plan")
    if _GIT_OID.fullmatch(source_commit) is None:
        raise StrategicSealedEvaluationError("sealed external audit expected commit is invalid")
    document = _decode_canonical(
        payload,
        maximum_bytes=_MAX_EVIDENCE_RECEIPT_BYTES,
        subject="sealed external audit receipt",
    )
    _exact_keys(
        document,
        {
            "evaluation_id",
            "evidence_sha256",
            "execution_source_bundle_sha256",
            "issued_by",
            "issued_on",
            "plan_sha256",
            "receipt_id",
            "schema",
            "scope",
            "source_commit",
            "verdict",
        },
        subject="sealed external audit receipt",
    )
    if document["schema"] != SEALED_EVALUATION_EXTERNAL_AUDIT_RECEIPT_SCHEMA:
        raise StrategicSealedEvaluationError("sealed external audit receipt schema differs")
    if document["scope"] != "sealed_evaluation_authorization_readiness":
        raise StrategicSealedEvaluationError("sealed external audit receipt scope differs")
    _validate_receipt_plan_binding(
        document,
        plan=plan,
        source_commit=source_commit,
        subject="sealed external audit receipt",
    )
    return StrategicSealedExternalAuditReceipt(
        receipt_sha256=hashlib.sha256(payload).hexdigest(),
        receipt_id=_safe_id(
            document["receipt_id"],
            subject="sealed external audit receipt identity",
        ),
        issued_by=_safe_id(
            document["issued_by"],
            subject="sealed external audit issuer identity",
        ),
        issued_on=_require_iso_date(
            document["issued_on"],
            subject="sealed external audit issue date",
        ),
        source_commit=source_commit,
        plan_sha256=plan.plan_sha256,
        execution_source_bundle_sha256=plan.execution_source_bundle_sha256,
        evidence_sha256=_sha256(
            document["evidence_sha256"],
            subject="sealed external audit evidence",
        ),
        verdict=_external_audit_verdict(document["verdict"]),
        _validation_token=_EXTERNAL_AUDIT_RECEIPT_VALIDATION_TOKEN,
    )


def build_strategic_sealed_non_test_qualification_receipt(
    plan: StrategicSealedEvaluationPlan,
    *,
    receipt_id: str,
    issued_by: str,
    issued_on: str,
    source_commit: str,
    evidence_sha256: str,
    verdict: str,
    sealed_test_cases_opened: int = 0,
) -> bytes:
    """Build a canonical adapter qualification attestation for non-test states."""

    if not isinstance(plan, StrategicSealedEvaluationPlan):
        raise TypeError("plan must be a sealed evaluation plan")
    _safe_id(receipt_id, subject="sealed non-test qualification receipt identity")
    _safe_id(issued_by, subject="sealed non-test qualification issuer identity")
    _require_iso_date(issued_on, subject="sealed non-test qualification issue date")
    if _GIT_OID.fullmatch(source_commit) is None:
        raise StrategicSealedEvaluationError(
            "sealed non-test qualification source commit is invalid"
        )
    _sha256(evidence_sha256, subject="sealed non-test qualification evidence")
    _non_test_qualification_verdict(verdict)
    if sealed_test_cases_opened != 0:
        raise StrategicSealedEvaluationError("sealed non-test qualification opened a test case")
    return _canonical_line(
        {
            "evaluation_id": plan.evaluation_id,
            "evidence_sha256": evidence_sha256,
            "execution_source_bundle_sha256": (plan.execution_source_bundle_sha256),
            "issued_by": issued_by,
            "issued_on": issued_on,
            "plan_sha256": plan.plan_sha256,
            "production_path": ("authenticate_relocate_plan_close_without_teacher"),
            "receipt_id": receipt_id,
            "schema": SEALED_EVALUATION_NON_TEST_QUALIFICATION_RECEIPT_SCHEMA,
            "scope": "production_adapter_non_test_cartridge_states",
            "sealed_test_cases_opened": sealed_test_cases_opened,
            "source_commit": source_commit,
            "verdict": verdict,
        }
    )


def parse_strategic_sealed_non_test_qualification_receipt(
    payload: bytes,
    *,
    plan: StrategicSealedEvaluationPlan,
    source_commit: str,
) -> StrategicSealedNonTestQualificationReceipt:
    """Parse a qualification verdict and prove it used no sealed test case."""

    if not isinstance(plan, StrategicSealedEvaluationPlan):
        raise TypeError("plan must be a sealed evaluation plan")
    if _GIT_OID.fullmatch(source_commit) is None:
        raise StrategicSealedEvaluationError(
            "sealed non-test qualification expected commit is invalid"
        )
    document = _decode_canonical(
        payload,
        maximum_bytes=_MAX_EVIDENCE_RECEIPT_BYTES,
        subject="sealed non-test qualification receipt",
    )
    _exact_keys(
        document,
        {
            "evaluation_id",
            "evidence_sha256",
            "execution_source_bundle_sha256",
            "issued_by",
            "issued_on",
            "plan_sha256",
            "production_path",
            "receipt_id",
            "schema",
            "scope",
            "sealed_test_cases_opened",
            "source_commit",
            "verdict",
        },
        subject="sealed non-test qualification receipt",
    )
    if document["schema"] != SEALED_EVALUATION_NON_TEST_QUALIFICATION_RECEIPT_SCHEMA:
        raise StrategicSealedEvaluationError("sealed non-test qualification receipt schema differs")
    if document["scope"] != "production_adapter_non_test_cartridge_states":
        raise StrategicSealedEvaluationError("sealed non-test qualification receipt scope differs")
    if document["production_path"] != ("authenticate_relocate_plan_close_without_teacher"):
        raise StrategicSealedEvaluationError(
            "sealed non-test qualification production path differs"
        )
    if document["sealed_test_cases_opened"] != 0:
        raise StrategicSealedEvaluationError("sealed non-test qualification opened a test case")
    _validate_receipt_plan_binding(
        document,
        plan=plan,
        source_commit=source_commit,
        subject="sealed non-test qualification receipt",
    )
    return StrategicSealedNonTestQualificationReceipt(
        receipt_sha256=hashlib.sha256(payload).hexdigest(),
        receipt_id=_safe_id(
            document["receipt_id"],
            subject="sealed non-test qualification receipt identity",
        ),
        issued_by=_safe_id(
            document["issued_by"],
            subject="sealed non-test qualification issuer identity",
        ),
        issued_on=_require_iso_date(
            document["issued_on"],
            subject="sealed non-test qualification issue date",
        ),
        source_commit=source_commit,
        plan_sha256=plan.plan_sha256,
        execution_source_bundle_sha256=plan.execution_source_bundle_sha256,
        evidence_sha256=_sha256(
            document["evidence_sha256"],
            subject="sealed non-test qualification evidence",
        ),
        verdict=_non_test_qualification_verdict(document["verdict"]),
        sealed_test_cases_opened=0,
        _validation_token=_NON_TEST_QUALIFICATION_RECEIPT_VALIDATION_TOKEN,
    )


def build_strategic_sealed_authorization(
    plan: StrategicSealedEvaluationPlan,
    *,
    authorization_id: str,
    authorized_by: str,
    authorized_on: str,
    source_commit: str,
    case_catalog_sha256: str,
    external_audit_receipt: StrategicSealedExternalAuditReceipt,
    non_test_adapter_qualification_receipt: (StrategicSealedNonTestQualificationReceipt),
) -> bytes:
    """Create the receipt only after the owner explicitly authorizes one-shot access."""

    if not isinstance(plan, StrategicSealedEvaluationPlan):
        raise TypeError("plan must be a sealed evaluation plan")
    _safe_id(authorization_id, subject="sealed authorization identity")
    _safe_id(authorized_by, subject="sealed authorizer identity")
    _require_iso_date(authorized_on, subject="sealed authorization date")
    if _GIT_OID.fullmatch(source_commit) is None:
        raise StrategicSealedEvaluationError("sealed authorization commit is invalid")
    _sha256(case_catalog_sha256, subject="sealed case catalog")
    _validate_authorizing_receipts(
        plan,
        source_commit=source_commit,
        external_audit_receipt=external_audit_receipt,
        non_test_adapter_qualification_receipt=(non_test_adapter_qualification_receipt),
    )
    return _canonical_line(
        {
            "acknowledgements": {
                "authorize_private_test_access": True,
                "external_audit_approved": True,
                "non_test_adapter_qualification_passed": True,
                "one_shot_no_reruns": True,
                "predictions_committed_before_teacher_action": True,
                "publish_protocol_failure_after_any_post_open_halt": True,
                "publish_regardless_of_outcome": True,
            },
            "authorization_id": authorization_id,
            "authorized_by": authorized_by,
            "authorized_on": authorized_on,
            "case_catalog_sha256": case_catalog_sha256,
            "evaluation_id": plan.evaluation_id,
            "execution_source_bundle_sha256": plan.execution_source_bundle_sha256,
            "external_audit_receipt_sha256": (external_audit_receipt.receipt_sha256),
            "model": {
                "canonical_sha256": plan.model_canonical_sha256,
                "private_file_sha256": plan.model_file_sha256,
            },
            "plan_sha256": plan.plan_sha256,
            "non_test_adapter_qualification_receipt_sha256": (
                non_test_adapter_qualification_receipt.receipt_sha256
            ),
            "schema": SEALED_EVALUATION_AUTHORIZATION_SCHEMA,
            "source_commit": source_commit,
            "teacher_execution_sha256": plan.teacher_execution_sha256,
        }
    )


def parse_strategic_sealed_authorization(
    payload: bytes,
    *,
    plan: StrategicSealedEvaluationPlan,
    external_audit_receipt: StrategicSealedExternalAuditReceipt,
    non_test_adapter_qualification_receipt: (StrategicSealedNonTestQualificationReceipt),
) -> StrategicSealedAuthorization:
    """Reject vague, stale, or selectively publishable owner authorization."""

    if not isinstance(plan, StrategicSealedEvaluationPlan):
        raise TypeError("plan must be a sealed evaluation plan")
    document = _decode_canonical(
        payload,
        maximum_bytes=_MAX_AUTHORIZATION_BYTES,
        subject="sealed evaluation authorization",
    )
    _exact_keys(
        document,
        {
            "acknowledgements",
            "authorization_id",
            "authorized_by",
            "authorized_on",
            "case_catalog_sha256",
            "evaluation_id",
            "execution_source_bundle_sha256",
            "external_audit_receipt_sha256",
            "model",
            "non_test_adapter_qualification_receipt_sha256",
            "plan_sha256",
            "schema",
            "source_commit",
            "teacher_execution_sha256",
        },
        subject="sealed evaluation authorization",
    )
    if document["schema"] != SEALED_EVALUATION_AUTHORIZATION_SCHEMA:
        raise StrategicSealedEvaluationError("sealed authorization schema differs")
    if document["evaluation_id"] != plan.evaluation_id:
        raise StrategicSealedEvaluationError("sealed authorization evaluation differs")
    if document["plan_sha256"] != plan.plan_sha256:
        raise StrategicSealedEvaluationError("sealed authorization plan differs")
    if document["execution_source_bundle_sha256"] != (plan.execution_source_bundle_sha256):
        raise StrategicSealedEvaluationError("sealed authorization source differs")
    if document["model"] != {
        "canonical_sha256": plan.model_canonical_sha256,
        "private_file_sha256": plan.model_file_sha256,
    }:
        raise StrategicSealedEvaluationError("sealed authorization model differs")
    if document["teacher_execution_sha256"] != plan.teacher_execution_sha256:
        raise StrategicSealedEvaluationError("sealed authorization teacher execution differs")
    if document["acknowledgements"] != {
        "authorize_private_test_access": True,
        "external_audit_approved": True,
        "non_test_adapter_qualification_passed": True,
        "one_shot_no_reruns": True,
        "predictions_committed_before_teacher_action": True,
        "publish_protocol_failure_after_any_post_open_halt": True,
        "publish_regardless_of_outcome": True,
    }:
        raise StrategicSealedEvaluationError("sealed authorization is incomplete")
    authorization_id = _safe_id(
        document["authorization_id"], subject="sealed authorization identity"
    )
    authorized_by = _safe_id(document["authorized_by"], subject="sealed authorizer identity")
    authorized_on = _require_iso_date(
        document["authorized_on"], subject="sealed authorization date"
    )
    source_commit = _text(document["source_commit"], subject="sealed authorization commit")
    if _GIT_OID.fullmatch(source_commit) is None:
        raise StrategicSealedEvaluationError("sealed authorization commit is invalid")
    _validate_authorizing_receipts(
        plan,
        source_commit=source_commit,
        external_audit_receipt=external_audit_receipt,
        non_test_adapter_qualification_receipt=(non_test_adapter_qualification_receipt),
    )
    external_audit_receipt_sha256 = _sha256(
        document["external_audit_receipt_sha256"],
        subject="sealed external audit receipt",
    )
    non_test_adapter_qualification_receipt_sha256 = _sha256(
        document["non_test_adapter_qualification_receipt_sha256"],
        subject="sealed non-test adapter qualification receipt",
    )
    if external_audit_receipt_sha256 != external_audit_receipt.receipt_sha256:
        raise StrategicSealedEvaluationError("sealed external audit receipt differs")
    if non_test_adapter_qualification_receipt_sha256 != (
        non_test_adapter_qualification_receipt.receipt_sha256
    ):
        raise StrategicSealedEvaluationError(
            "sealed non-test adapter qualification receipt differs"
        )
    return StrategicSealedAuthorization(
        authorization_sha256=hashlib.sha256(payload).hexdigest(),
        authorization_id=authorization_id,
        authorized_by=authorized_by,
        authorized_on=authorized_on,
        source_commit=source_commit,
        plan_sha256=plan.plan_sha256,
        execution_source_bundle_sha256=plan.execution_source_bundle_sha256,
        model_canonical_sha256=plan.model_canonical_sha256,
        model_file_sha256=plan.model_file_sha256,
        teacher_execution_sha256=plan.teacher_execution_sha256,
        case_catalog_sha256=_sha256(document["case_catalog_sha256"], subject="sealed case catalog"),
        external_audit_receipt_sha256=external_audit_receipt_sha256,
        non_test_adapter_qualification_receipt_sha256=(
            non_test_adapter_qualification_receipt_sha256
        ),
        _validation_token=_AUTHORIZATION_VALIDATION_TOKEN,
    )


def require_strategic_sealed_runtime_preflight(
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    *,
    source_commit: str,
    source_bundle_sha256: str,
    source_clean: bool,
    source_published: bool,
    model_canonical_sha256: str,
    model_file_sha256: str,
    teacher_execution_sha256: str,
    case_catalog_sha256: str,
    external_audit_receipt: StrategicSealedExternalAuditReceipt,
    non_test_adapter_qualification_receipt: (StrategicSealedNonTestQualificationReceipt),
) -> StrategicSealedRuntimeGrant:
    """Perform every identity refusal before the first case claim."""

    if not isinstance(plan, StrategicSealedEvaluationPlan) or not isinstance(
        authorization, StrategicSealedAuthorization
    ):
        raise TypeError("sealed preflight requires a plan and authorization")
    _validate_authorization_binding(plan, authorization)
    if source_clean is not True or source_published is not True:
        raise StrategicSealedEvaluationError("sealed evaluation requires clean published source")
    _validate_authorizing_receipts(
        plan,
        source_commit=source_commit,
        external_audit_receipt=external_audit_receipt,
        non_test_adapter_qualification_receipt=(non_test_adapter_qualification_receipt),
    )
    checks = (
        (source_commit, authorization.source_commit, "source commit"),
        (source_bundle_sha256, plan.execution_source_bundle_sha256, "source bundle"),
        (model_canonical_sha256, plan.model_canonical_sha256, "model canonical digest"),
        (model_file_sha256, plan.model_file_sha256, "model file digest"),
        (
            teacher_execution_sha256,
            plan.teacher_execution_sha256,
            "teacher execution",
        ),
        (case_catalog_sha256, authorization.case_catalog_sha256, "case catalog"),
        (
            external_audit_receipt.receipt_sha256,
            authorization.external_audit_receipt_sha256,
            "external audit receipt",
        ),
        (
            non_test_adapter_qualification_receipt.receipt_sha256,
            authorization.non_test_adapter_qualification_receipt_sha256,
            "non-test adapter qualification receipt",
        ),
    )
    for actual, expected, subject in checks:
        if actual != expected:
            raise StrategicSealedEvaluationError(f"sealed {subject} differs")
    return StrategicSealedRuntimeGrant(
        plan_sha256=plan.plan_sha256,
        authorization_sha256=authorization.authorization_sha256,
        source_commit=authorization.source_commit,
        teacher_execution_sha256=authorization.teacher_execution_sha256,
        case_catalog_sha256=authorization.case_catalog_sha256,
        external_audit_receipt_sha256=(authorization.external_audit_receipt_sha256),
        non_test_adapter_qualification_receipt_sha256=(
            authorization.non_test_adapter_qualification_receipt_sha256
        ),
        _validation_token=_PREFLIGHT_VALIDATION_TOKEN,
    )


def failed_strategic_sealed_case_outcome(
    case: StrategicSealedEvaluationCase,
    *,
    status: str,
) -> StrategicSealedCaseOutcome:
    """Create symmetric incorrect evidence without leaking a partial prediction."""

    if status not in {"failed", "interrupted", "candidate_unavailable"}:
        raise StrategicSealedEvaluationError("sealed failure status is invalid")
    return StrategicSealedCaseOutcome(
        case_id=case.case_id,
        case_sha256=case.case_sha256,
        ordinal=case.ordinal,
        candidate_count=case.candidate_count,
        execution_status=status,
    )


def score_strategic_sealed_evaluation(
    plan: StrategicSealedEvaluationPlan,
    outcomes: Sequence[StrategicSealedCaseOutcome],
    *,
    authorization: StrategicSealedAuthorization,
    halt_observed: bool,
) -> StrategicSealedEvaluationResult:
    """Compute the first statistic only when all twelve ordered outcomes exist."""

    if not isinstance(plan, StrategicSealedEvaluationPlan):
        raise TypeError("plan must be a sealed evaluation plan")
    if not isinstance(authorization, StrategicSealedAuthorization):
        raise TypeError("authorization must be a sealed evaluation authorization")
    _validate_authorization_binding(plan, authorization)
    rows = tuple(outcomes)
    if len(rows) != SEALED_EVALUATION_CASES:
        raise StrategicSealedEvaluationError(
            "sealed evaluation is incomplete; no metric is available"
        )
    if not isinstance(halt_observed, bool):
        raise StrategicSealedEvaluationError("sealed halt status must be boolean")
    for case, outcome in zip(plan.cases, rows, strict=True):
        if (
            outcome.case_id,
            outcome.case_sha256,
            outcome.ordinal,
            outcome.candidate_count,
        ) != (
            case.case_id,
            case.case_sha256,
            case.ordinal,
            case.candidate_count,
        ):
            raise StrategicSealedEvaluationError("sealed outcome order or identity differs")

    assessments = tuple(
        {
            "baseline_correct": outcome.baseline_correct,
            "baseline_prediction_tied": outcome.baseline_prediction_tied,
            "candidate_count": case.candidate_count,
            "case_id": case.case_id,
            "challenge_case": case.challenge,
            "execution_status": outcome.execution_status,
            "model_correct": outcome.model_correct,
            "model_prediction_tied": outcome.model_prediction_tied,
            "ordinal": case.ordinal,
        }
        for case, outcome in zip(plan.cases, rows, strict=True)
    )
    primary_pairs = tuple(
        (outcome.model_correct, outcome.baseline_correct)
        for case, outcome in zip(plan.cases, rows, strict=True)
        if case.challenge
    )
    wins = sum(model_ok and not baseline_ok for model_ok, baseline_ok in primary_pairs)
    losses = sum(not model_ok and baseline_ok for model_ok, baseline_ok in primary_pairs)
    both_correct = sum(model_ok and baseline_ok for model_ok, baseline_ok in primary_pairs)
    both_wrong = sum(not model_ok and not baseline_ok for model_ok, baseline_ok in primary_pairs)
    measured_disagreements = sum(
        outcome.execution_status == "succeeded" and not outcome.baseline_correct
        for case, outcome in zip(plan.cases, rows, strict=True)
        if case.challenge
    )
    primary_execution_failures = sum(
        outcome.execution_status != "succeeded"
        for case, outcome in zip(plan.cases, rows, strict=True)
        if case.challenge
    )
    p_value = _paired_two_sided_exact_p(wins, losses)
    capability_met = measured_disagreements >= SEALED_EVALUATION_MINIMUM_DISAGREEMENTS
    protocol_failure_reasons = []
    if halt_observed:
        protocol_failure_reasons.append("executor_halted_after_case_open")
    if primary_execution_failures:
        protocol_failure_reasons.append("primary_case_without_successful_teacher_target")
    if not capability_met:
        protocol_failure_reasons.append("insufficient_measured_baseline_disagreements")
    protocol_valid = not protocol_failure_reasons
    primary_significant = protocol_valid and wins > losses and p_value < 0.05
    safety_pairs = tuple(
        (outcome.model_correct, outcome.baseline_correct)
        for case, outcome in zip(plan.cases, rows, strict=True)
        if not case.challenge
    )
    safety_failures = sum(not model_ok and baseline_ok for model_ok, baseline_ok in safety_pairs)
    safety_execution_failures = sum(
        outcome.execution_status != "succeeded"
        for case, outcome in zip(plan.cases, rows, strict=True)
        if not case.challenge
    )
    safety_passed = safety_failures == 0 and safety_execution_failures == 0
    offline_gate_passed = primary_significant and safety_passed
    model_correct_all = sum(outcome.model_correct for outcome in rows)
    baseline_correct_all = sum(outcome.baseline_correct for outcome in rows)
    candidate_count_results = []
    for candidate_count in sorted({case.candidate_count for case in plan.cases}):
        count_rows = tuple(
            outcome
            for case, outcome in zip(plan.cases, rows, strict=True)
            if case.candidate_count == candidate_count
        )
        candidate_count_results.append(
            {
                "candidate_count": candidate_count,
                "cases": len(count_rows),
                "model_accuracy": (
                    sum(outcome.model_correct for outcome in count_rows) / len(count_rows)
                ),
                "model_correct": sum(outcome.model_correct for outcome in count_rows),
                "route_cost_baseline_accuracy": (
                    sum(outcome.baseline_correct for outcome in count_rows) / len(count_rows)
                ),
                "route_cost_baseline_correct": sum(
                    outcome.baseline_correct for outcome in count_rows
                ),
            }
        )
    document: dict[str, object] = {
        "all_case_accuracy": {
            "cases": SEALED_EVALUATION_CASES,
            "model_accuracy": model_correct_all / SEALED_EVALUATION_CASES,
            "model_correct": model_correct_all,
            "route_cost_baseline_accuracy": (baseline_correct_all / SEALED_EVALUATION_CASES),
            "route_cost_baseline_correct": baseline_correct_all,
        },
        "authorization_sha256": authorization.authorization_sha256,
        "candidate_count_results": candidate_count_results,
        "case_results": list(assessments),
        "case_catalog_sha256": authorization.case_catalog_sha256,
        "evaluation_id": plan.evaluation_id,
        "external_audit_receipt_sha256": (authorization.external_audit_receipt_sha256),
        "live_authority": {
            "blocked": not offline_gate_passed,
            "granted_by_this_result": False,
        },
        "offline_gate_passed": offline_gate_passed,
        "non_test_adapter_qualification_receipt_sha256": (
            authorization.non_test_adapter_qualification_receipt_sha256
        ),
        "plan_sha256": plan.plan_sha256,
        "primary": {
            "both_correct": both_correct,
            "both_wrong": both_wrong,
            "capability_floor_met": capability_met,
            "cases": SEALED_EVALUATION_PRIMARY_CASES,
            "losses": losses,
            "measured_teacher_baseline_disagreements": measured_disagreements,
            "model_better_direction_met": wins > losses,
            "successful_teacher_cases": (
                SEALED_EVALUATION_PRIMARY_CASES - primary_execution_failures
            ),
            "significance_threshold": 0.05,
            "significant": primary_significant,
            "two_sided_exact_p": p_value,
            "wins": wins,
        },
        "protocol": {
            "all_cases_consumed_before_scoring": True,
            "halt_observed": halt_observed,
            "intermediate_metrics_emitted": False,
            "protocol_failure_reasons": protocol_failure_reasons,
            "valid": protocol_valid,
        },
        "safety": {
            "cases": SEALED_EVALUATION_SAFETY_CASES,
            "model_incorrect_baseline_correct": safety_failures,
            "passed": safety_passed,
            "successful_teacher_cases": (
                SEALED_EVALUATION_SAFETY_CASES - safety_execution_failures
            ),
        },
        "schema": SEALED_EVALUATION_RESULT_SCHEMA,
        "source_commit": authorization.source_commit,
        "teacher_execution_sha256": plan.teacher_execution_sha256,
        "status": (
            "protocol_failure"
            if not protocol_valid
            else ("passed" if offline_gate_passed else "not_passed")
        ),
    }
    document["result_sha256"] = canonical_sha256(document)
    return StrategicSealedEvaluationResult(document)


def execute_strategic_sealed_evaluation(
    private_root: PrivateArtifactRoot,
    *,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    runtime_grant: StrategicSealedRuntimeGrant,
    runner: StrategicSealedCaseRunner,
    progress: StrategicSealedProgressCallback | None = None,
) -> StrategicSealedEvaluationResult:
    """Run or resume every case in fixed order and emit metrics only at the end."""

    if not isinstance(private_root, PrivateArtifactRoot):
        raise TypeError("private_root must be a validated private artifact root")
    if not isinstance(plan, StrategicSealedEvaluationPlan) or not isinstance(
        authorization, StrategicSealedAuthorization
    ):
        raise TypeError("sealed execution requires a plan and authorization")
    if not isinstance(runtime_grant, StrategicSealedRuntimeGrant):
        raise TypeError("sealed execution requires a validated runtime grant")
    if (
        not callable(getattr(runner, "prepare", None))
        or not callable(getattr(runner, "execute_teacher", None))
        or not callable(getattr(runner, "abort", None))
    ):
        raise TypeError("sealed case runner is incomplete")
    if progress is not None and not callable(progress):
        raise TypeError("sealed execution callbacks must be callable")
    _validate_authorization_binding(plan, authorization)
    _validate_runtime_grant(plan, authorization, runtime_grant)
    namespace = _execution_namespace(plan)
    collection_id = f"red-sealed-{namespace[:48]}"
    with private_root.collection_session(collection_id):
        final_record = private_root.find_sealed_record(
            _record_id("final", namespace),
            expected_kind="strategic_sealed_final",
        )
        if final_record is not None:
            start = private_root.find_sealed_record(
                _record_id("start", namespace),
                expected_kind="strategic_sealed_start",
            )
            if start is None:
                raise StrategicSealedEvaluationError("sealed final record exists without a start")
            _validate_start_record(start, plan=plan, authorization=authorization)
            outcomes, claimed = _load_ledger(
                private_root,
                plan=plan,
                authorization=authorization,
                namespace=namespace,
            )
            if claimed != SEALED_EVALUATION_CASES:
                raise StrategicSealedEvaluationError(
                    "sealed final record exists before every case was consumed"
                )
            expected_result = score_strategic_sealed_evaluation(
                plan,
                outcomes,
                authorization=authorization,
                halt_observed=_has_halt(
                    private_root,
                    plan=plan,
                    authorization=authorization,
                    namespace=namespace,
                ),
            )
            return _result_from_final_record(
                final_record,
                plan=plan,
                authorization=authorization,
                expected_result=expected_result,
            )

        start_id = _record_id("start", namespace)
        start = private_root.find_sealed_record(
            start_id,
            expected_kind="strategic_sealed_start",
        )
        if start is None:
            preexisting_outcomes, preexisting_claims = _load_ledger(
                private_root,
                plan=plan,
                authorization=authorization,
                namespace=namespace,
            )
            if (
                preexisting_claims
                or preexisting_outcomes
                or _has_halt(
                    private_root,
                    plan=plan,
                    authorization=authorization,
                    namespace=namespace,
                )
            ):
                raise StrategicSealedEvaluationError("sealed case ledger exists without a start")
            private_root.publish_sealed_record(
                start_id,
                kind="strategic_sealed_start",
                record={
                    "authorization_sha256": authorization.authorization_sha256,
                    "case_order_sha256": canonical_sha256(list(plan.case_order)),
                    "case_catalog_sha256": authorization.case_catalog_sha256,
                    "evaluation_id": plan.evaluation_id,
                    "execution_source_bundle_sha256": (plan.execution_source_bundle_sha256),
                    "external_audit_receipt_sha256": (authorization.external_audit_receipt_sha256),
                    "model_canonical_sha256": plan.model_canonical_sha256,
                    "model_file_sha256": plan.model_file_sha256,
                    "non_test_adapter_qualification_receipt_sha256": (
                        authorization.non_test_adapter_qualification_receipt_sha256
                    ),
                    "plan_sha256": plan.plan_sha256,
                    "schema": "strategic-sealed-evaluation-start-v1",
                    "source_commit": authorization.source_commit,
                    "status": "started",
                    "teacher_execution_sha256": plan.teacher_execution_sha256,
                },
            )
            resumed = False
        else:
            _validate_start_record(start, plan=plan, authorization=authorization)
            resumed = True

        outcomes, claimed = _load_ledger(
            private_root,
            plan=plan,
            authorization=authorization,
            namespace=namespace,
        )
        halt_observed = _has_halt(
            private_root,
            plan=plan,
            authorization=authorization,
            namespace=namespace,
        )
        if resumed and claimed:
            _publish_halt(
                private_root,
                plan=plan,
                authorization=authorization,
                namespace=namespace,
            )
            halt_observed = True
        if claimed and len(outcomes) < claimed:
            interrupted_case = plan.cases[claimed - 1]
            interrupted = failed_strategic_sealed_case_outcome(
                interrupted_case,
                status="interrupted",
            )
            _publish_outcome(
                private_root,
                namespace=namespace,
                plan=plan,
                authorization=authorization,
                outcome=interrupted,
            )
            outcomes.append(interrupted)

        for case in plan.cases[len(outcomes) :]:
            try:
                _publish_claim(
                    private_root,
                    namespace=namespace,
                    plan=plan,
                    authorization=authorization,
                    case=case,
                )
                try:
                    prediction = runner.prepare(case)
                except StrategicSealedCandidateUnavailableError:
                    _abort_runner_case(runner, case)
                    outcome = failed_strategic_sealed_case_outcome(
                        case,
                        status="candidate_unavailable",
                    )
                except Exception:
                    _abort_runner_case(runner, case)
                    outcome = failed_strategic_sealed_case_outcome(
                        case,
                        status="failed",
                    )
                else:
                    _require_prediction_matches_case(prediction, case)
                    _publish_prediction(
                        private_root,
                        namespace=namespace,
                        plan=plan,
                        authorization=authorization,
                        prediction=prediction,
                    )
                    try:
                        teacher = runner.execute_teacher(case)
                    except Exception:
                        _abort_runner_case(runner, case)
                        outcome = failed_strategic_sealed_case_outcome(
                            case,
                            status="failed",
                        )
                    else:
                        _require_teacher_result_matches_case(teacher, case)
                        outcome = _outcome_from_prediction_and_teacher(
                            prediction,
                            teacher,
                        )
                _require_outcome_matches_case(outcome, case)
                _publish_outcome(
                    private_root,
                    namespace=namespace,
                    plan=plan,
                    authorization=authorization,
                    outcome=outcome,
                )
                outcomes.append(outcome)
                if progress is not None:
                    progress(StrategicSealedProgress(consumed_cases=case.ordinal))
            except BaseException:
                _abort_runner_case(runner, case)
                if _claim_exists(
                    private_root,
                    plan=plan,
                    authorization=authorization,
                    namespace=namespace,
                    case=case,
                ):
                    try:
                        _consume_open_case_as_interrupted(
                            private_root,
                            plan=plan,
                            authorization=authorization,
                            namespace=namespace,
                            case=case,
                        )
                    finally:
                        _publish_halt(
                            private_root,
                            plan=plan,
                            authorization=authorization,
                            namespace=namespace,
                        )
                raise

        result = score_strategic_sealed_evaluation(
            plan,
            outcomes,
            authorization=authorization,
            halt_observed=halt_observed
            or _has_halt(
                private_root,
                plan=plan,
                authorization=authorization,
                namespace=namespace,
            ),
        )
        final = private_root.publish_sealed_record(
            _record_id("final", namespace),
            kind="strategic_sealed_final",
            record={
                "authorization_sha256": authorization.authorization_sha256,
                "plan_sha256": plan.plan_sha256,
                "result": result.public_dict(),
                "schema": "strategic-sealed-evaluation-final-record-v1",
            },
        )
        return _result_from_final_record(
            final,
            plan=plan,
            authorization=authorization,
            expected_result=result,
        )
    raise AssertionError("sealed collection session suppressed an exception")


def _abort_runner_case(
    runner: StrategicSealedCaseRunner,
    case: StrategicSealedEvaluationCase,
) -> None:
    """Best-effort private-session cleanup without replacing the real failure."""

    abort = getattr(runner, "abort", None)
    if not callable(abort):
        return
    with suppress(BaseException):
        abort(case)


def _load_ledger(
    private_root: PrivateArtifactRoot,
    *,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    namespace: str,
) -> tuple[list[StrategicSealedCaseOutcome], int]:
    outcomes: list[StrategicSealedCaseOutcome] = []
    claimed = 0
    gap_seen = False
    open_seen = False
    for case in plan.cases:
        claim = private_root.find_sealed_record(
            _case_record_id("claim", case.ordinal, namespace),
            expected_kind="strategic_sealed_claim",
        )
        outcome_record = private_root.find_sealed_record(
            _case_record_id("outcome", case.ordinal, namespace),
            expected_kind="strategic_sealed_outcome",
        )
        prediction_record = private_root.find_sealed_record(
            _case_record_id("prediction", case.ordinal, namespace),
            expected_kind="strategic_sealed_prediction",
        )
        if claim is None:
            gap_seen = True
            if outcome_record is not None or prediction_record is not None:
                raise StrategicSealedEvaluationError(
                    "sealed case evidence exists without its durable claim"
                )
            continue
        if gap_seen:
            raise StrategicSealedEvaluationError("sealed case claims are not contiguous")
        if open_seen:
            raise StrategicSealedEvaluationError("sealed ledger continued beyond an open case")
        _validate_claim_record(
            claim,
            case=case,
            plan=plan,
            authorization=authorization,
        )
        claimed += 1
        prediction = (
            _prediction_from_record(
                prediction_record,
                plan=plan,
                authorization=authorization,
            )
            if prediction_record is not None
            else None
        )
        if prediction is not None:
            _require_prediction_matches_case(prediction, case)
        if outcome_record is None:
            if case.ordinal != claimed or len(outcomes) != claimed - 1:
                raise StrategicSealedEvaluationError("sealed open case order differs")
            open_seen = True
            continue
        outcome = _outcome_from_record(
            outcome_record,
            plan=plan,
            authorization=authorization,
        )
        _require_outcome_matches_case(outcome, case)
        _require_prediction_consistent_with_outcome(
            prediction,
            outcome,
        )
        outcomes.append(outcome)
    if claimed - len(outcomes) not in {0, 1}:
        raise StrategicSealedEvaluationError("sealed ledger has multiple open cases")
    return outcomes, claimed


def _publish_claim(
    private_root: PrivateArtifactRoot,
    *,
    namespace: str,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    case: StrategicSealedEvaluationCase,
) -> None:
    existing_outcomes, claimed = _load_ledger(
        private_root,
        plan=plan,
        authorization=authorization,
        namespace=namespace,
    )
    if claimed != len(existing_outcomes) or case.ordinal != claimed + 1:
        raise StrategicSealedEvaluationError("sealed case cannot be claimed out of order")
    private_root.publish_sealed_record(
        _case_record_id("claim", case.ordinal, namespace),
        kind="strategic_sealed_claim",
        record={
            "authorization_sha256": authorization.authorization_sha256,
            "case_id": case.case_id,
            "case_sha256": case.case_sha256,
            "ordinal": case.ordinal,
            "plan_sha256": plan.plan_sha256,
            "private_input_access_may_begin": True,
            "schema": "strategic-sealed-evaluation-case-claim-v1",
            "status": "claimed",
        },
    )


def _claim_exists(
    private_root: PrivateArtifactRoot,
    *,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    namespace: str,
    case: StrategicSealedEvaluationCase,
) -> bool:
    record = private_root.find_sealed_record(
        _case_record_id("claim", case.ordinal, namespace),
        expected_kind="strategic_sealed_claim",
    )
    if record is None:
        return False
    _validate_claim_record(
        record,
        case=case,
        plan=plan,
        authorization=authorization,
    )
    return True


def _publish_prediction(
    private_root: PrivateArtifactRoot,
    *,
    namespace: str,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    prediction: StrategicSealedPrediction,
) -> None:
    case = plan.cases[prediction.ordinal - 1]
    _require_prediction_matches_case(prediction, case)
    claim = private_root.find_sealed_record(
        _case_record_id("claim", case.ordinal, namespace),
        expected_kind="strategic_sealed_claim",
    )
    if claim is None:
        raise StrategicSealedEvaluationError("sealed prediction commitment lacks a claim")
    _validate_claim_record(
        claim,
        case=case,
        plan=plan,
        authorization=authorization,
    )
    if (
        private_root.find_sealed_record(
            _case_record_id("outcome", case.ordinal, namespace),
            expected_kind="strategic_sealed_outcome",
        )
        is not None
    ):
        raise StrategicSealedEvaluationError("sealed prediction cannot replace a consumed outcome")
    private_root.publish_sealed_record(
        _case_record_id("prediction", case.ordinal, namespace),
        kind="strategic_sealed_prediction",
        record={
            "authorization_sha256": authorization.authorization_sha256,
            "plan_sha256": plan.plan_sha256,
            "prediction": prediction.private_dict(),
            "schema": "strategic-sealed-evaluation-prediction-record-v1",
        },
    )


def _consume_open_case_as_interrupted(
    private_root: PrivateArtifactRoot,
    *,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    namespace: str,
    case: StrategicSealedEvaluationCase,
) -> None:
    record = private_root.find_sealed_record(
        _case_record_id("outcome", case.ordinal, namespace),
        expected_kind="strategic_sealed_outcome",
    )
    if record is not None:
        outcome = _outcome_from_record(
            record,
            plan=plan,
            authorization=authorization,
        )
        _require_outcome_matches_case(outcome, case)
        return
    _publish_outcome(
        private_root,
        namespace=namespace,
        plan=plan,
        authorization=authorization,
        outcome=failed_strategic_sealed_case_outcome(
            case,
            status="interrupted",
        ),
    )


def _publish_outcome(
    private_root: PrivateArtifactRoot,
    *,
    namespace: str,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    outcome: StrategicSealedCaseOutcome,
) -> None:
    case = plan.cases[outcome.ordinal - 1]
    _require_outcome_matches_case(outcome, case)
    claim = private_root.find_sealed_record(
        _case_record_id("claim", case.ordinal, namespace),
        expected_kind="strategic_sealed_claim",
    )
    if claim is None:
        raise StrategicSealedEvaluationError("sealed case outcome lacks a claim")
    _validate_claim_record(
        claim,
        case=case,
        plan=plan,
        authorization=authorization,
    )
    prediction_record = private_root.find_sealed_record(
        _case_record_id("prediction", case.ordinal, namespace),
        expected_kind="strategic_sealed_prediction",
    )
    prediction = (
        _prediction_from_record(
            prediction_record,
            plan=plan,
            authorization=authorization,
        )
        if prediction_record is not None
        else None
    )
    _require_prediction_consistent_with_outcome(prediction, outcome)
    private_root.publish_sealed_record(
        _case_record_id("outcome", case.ordinal, namespace),
        kind="strategic_sealed_outcome",
        record={
            "authorization_sha256": authorization.authorization_sha256,
            "outcome": outcome.private_dict(),
            "plan_sha256": plan.plan_sha256,
            "schema": "strategic-sealed-evaluation-outcome-record-v1",
        },
    )


def _publish_halt(
    private_root: PrivateArtifactRoot,
    *,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    namespace: str,
) -> None:
    private_root.publish_sealed_record(
        _record_id("halt", namespace),
        kind="strategic_sealed_halt",
        record={
            "authorization_sha256": authorization.authorization_sha256,
            "plan_sha256": plan.plan_sha256,
            "reason": "executor_halted_after_case_open",
            "schema": "strategic-sealed-evaluation-halt-v1",
            "status": "protocol_failure",
        },
    )


def _has_halt(
    private_root: PrivateArtifactRoot,
    *,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    namespace: str,
) -> bool:
    record = private_root.find_sealed_record(
        _record_id("halt", namespace),
        expected_kind="strategic_sealed_halt",
    )
    if record is None:
        return False
    if record.read() != {
        "authorization_sha256": authorization.authorization_sha256,
        "plan_sha256": plan.plan_sha256,
        "reason": "executor_halted_after_case_open",
        "schema": "strategic-sealed-evaluation-halt-v1",
        "status": "protocol_failure",
    }:
        raise StrategicSealedEvaluationError("sealed halt record differs")
    return True


def _result_from_final_record(
    record: PrivateSealedRecord,
    *,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    expected_result: StrategicSealedEvaluationResult,
) -> StrategicSealedEvaluationResult:
    raw = record.read()
    if (
        set(raw)
        != {
            "authorization_sha256",
            "plan_sha256",
            "result",
            "schema",
        }
        or raw.get("schema") != "strategic-sealed-evaluation-final-record-v1"
    ):
        raise StrategicSealedEvaluationError("sealed final record differs")
    if (
        raw.get("plan_sha256") != plan.plan_sha256
        or raw.get("authorization_sha256") != authorization.authorization_sha256
    ):
        raise StrategicSealedEvaluationError("sealed final identity differs")
    result = _mapping(raw.get("result"), subject="sealed final result")
    if result.get("schema") != SEALED_EVALUATION_RESULT_SCHEMA:
        raise StrategicSealedEvaluationError("sealed final result schema differs")
    digest = result.get("result_sha256")
    unsigned = dict(result)
    unsigned.pop("result_sha256", None)
    if digest != canonical_sha256(unsigned):
        raise StrategicSealedEvaluationError("sealed final result digest differs")
    if result != expected_result.document:
        raise StrategicSealedEvaluationError(
            "sealed final result differs from the immutable case ledger"
        )
    return StrategicSealedEvaluationResult(result)


def _validate_start_record(
    record: PrivateSealedRecord,
    *,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
) -> None:
    if record.read() != {
        "authorization_sha256": authorization.authorization_sha256,
        "case_catalog_sha256": authorization.case_catalog_sha256,
        "case_order_sha256": canonical_sha256(list(plan.case_order)),
        "evaluation_id": plan.evaluation_id,
        "execution_source_bundle_sha256": plan.execution_source_bundle_sha256,
        "external_audit_receipt_sha256": (authorization.external_audit_receipt_sha256),
        "model_canonical_sha256": plan.model_canonical_sha256,
        "model_file_sha256": plan.model_file_sha256,
        "non_test_adapter_qualification_receipt_sha256": (
            authorization.non_test_adapter_qualification_receipt_sha256
        ),
        "plan_sha256": plan.plan_sha256,
        "schema": "strategic-sealed-evaluation-start-v1",
        "source_commit": authorization.source_commit,
        "status": "started",
        "teacher_execution_sha256": plan.teacher_execution_sha256,
    }:
        raise StrategicSealedEvaluationError("sealed start record differs")


def _validate_claim_record(
    record: PrivateSealedRecord,
    *,
    case: StrategicSealedEvaluationCase,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
) -> None:
    if record.read() != {
        "authorization_sha256": authorization.authorization_sha256,
        "case_id": case.case_id,
        "case_sha256": case.case_sha256,
        "ordinal": case.ordinal,
        "plan_sha256": plan.plan_sha256,
        "private_input_access_may_begin": True,
        "schema": "strategic-sealed-evaluation-case-claim-v1",
        "status": "claimed",
    }:
        raise StrategicSealedEvaluationError("sealed case claim differs")


def _prediction_from_record(
    record: PrivateSealedRecord,
    *,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
) -> StrategicSealedPrediction:
    raw = record.read()
    if (
        set(raw)
        != {
            "authorization_sha256",
            "plan_sha256",
            "prediction",
            "schema",
        }
        or raw.get("schema") != "strategic-sealed-evaluation-prediction-record-v1"
    ):
        raise StrategicSealedEvaluationError("sealed prediction commitment record differs")
    if (
        raw.get("plan_sha256") != plan.plan_sha256
        or raw.get("authorization_sha256") != authorization.authorization_sha256
    ):
        raise StrategicSealedEvaluationError("sealed prediction commitment identity differs")
    row = _mapping(raw.get("prediction"), subject="sealed prediction commitment")
    _exact_keys(
        row,
        {
            "baseline_prediction_index",
            "baseline_prediction_tied",
            "candidate_count",
            "case_id",
            "case_sha256",
            "model_prediction_index",
            "model_prediction_tied",
            "ordinal",
            "policy_input_sha256",
            "schema",
        },
        subject="sealed prediction commitment",
    )
    if row["schema"] != SEALED_EVALUATION_PREDICTION_SCHEMA:
        raise StrategicSealedEvaluationError("sealed prediction commitment schema differs")
    return StrategicSealedPrediction(
        case_id=_text(row["case_id"], subject="sealed prediction case identity"),
        case_sha256=_text(row["case_sha256"], subject="sealed prediction case digest"),
        ordinal=_integer(
            row["ordinal"],
            minimum=1,
            maximum=SEALED_EVALUATION_CASES,
            subject="sealed prediction case ordinal",
        ),
        candidate_count=_integer(
            row["candidate_count"],
            minimum=2,
            maximum=5,
            subject="sealed prediction candidate count",
        ),
        model_prediction_index=_optional_integer(row["model_prediction_index"]),
        model_prediction_tied=_boolean(
            row["model_prediction_tied"], subject="sealed model prediction tie"
        ),
        baseline_prediction_index=_optional_integer(row["baseline_prediction_index"]),
        baseline_prediction_tied=_boolean(
            row["baseline_prediction_tied"],
            subject="sealed baseline prediction tie",
        ),
        policy_input_sha256=_text(row["policy_input_sha256"], subject="sealed policy input"),
    )


def _outcome_from_record(
    record: PrivateSealedRecord,
    *,
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
) -> StrategicSealedCaseOutcome:
    raw = record.read()
    if (
        set(raw)
        != {
            "authorization_sha256",
            "outcome",
            "plan_sha256",
            "schema",
        }
        or raw.get("schema") != "strategic-sealed-evaluation-outcome-record-v1"
    ):
        raise StrategicSealedEvaluationError("sealed case outcome record differs")
    if (
        raw.get("plan_sha256") != plan.plan_sha256
        or raw.get("authorization_sha256") != authorization.authorization_sha256
    ):
        raise StrategicSealedEvaluationError("sealed case outcome identity differs")
    row = _mapping(raw.get("outcome"), subject="sealed case outcome")
    _exact_keys(
        row,
        {
            "baseline_prediction_index",
            "baseline_prediction_tied",
            "candidate_count",
            "case_id",
            "case_sha256",
            "episode_manifest_sha256",
            "execution_status",
            "model_prediction_index",
            "model_prediction_tied",
            "ordinal",
            "policy_input_sha256",
            "schema",
            "teacher_target_index",
        },
        subject="sealed case outcome",
    )
    if row["schema"] != SEALED_EVALUATION_CASE_OUTCOME_SCHEMA:
        raise StrategicSealedEvaluationError("sealed case outcome schema differs")
    return StrategicSealedCaseOutcome(
        case_id=_text(row["case_id"], subject="sealed case identity"),
        case_sha256=_text(row["case_sha256"], subject="sealed case digest"),
        ordinal=_integer(
            row["ordinal"],
            minimum=1,
            maximum=SEALED_EVALUATION_CASES,
            subject="sealed case ordinal",
        ),
        candidate_count=_integer(
            row["candidate_count"],
            minimum=2,
            maximum=5,
            subject="sealed candidate count",
        ),
        execution_status=_text(row["execution_status"], subject="sealed execution status"),
        teacher_target_index=_optional_integer(row["teacher_target_index"]),
        model_prediction_index=_optional_integer(row["model_prediction_index"]),
        model_prediction_tied=_boolean(row["model_prediction_tied"], subject="sealed model tie"),
        baseline_prediction_index=_optional_integer(row["baseline_prediction_index"]),
        baseline_prediction_tied=_boolean(
            row["baseline_prediction_tied"], subject="sealed baseline tie"
        ),
        policy_input_sha256=_optional_text(row["policy_input_sha256"]),
        episode_manifest_sha256=_optional_text(row["episode_manifest_sha256"]),
    )


def _require_outcome_matches_case(
    outcome: StrategicSealedCaseOutcome,
    case: StrategicSealedEvaluationCase,
) -> None:
    if not isinstance(outcome, StrategicSealedCaseOutcome):
        raise StrategicSealedEvaluationError("sealed runner returned an invalid outcome")
    if (
        outcome.case_id,
        outcome.case_sha256,
        outcome.ordinal,
        outcome.candidate_count,
    ) != (
        case.case_id,
        case.case_sha256,
        case.ordinal,
        case.candidate_count,
    ):
        raise StrategicSealedEvaluationError("sealed runner outcome differs from its case")


def _require_prediction_matches_case(
    prediction: StrategicSealedPrediction,
    case: StrategicSealedEvaluationCase,
) -> None:
    if not isinstance(prediction, StrategicSealedPrediction):
        raise StrategicSealedEvaluationError(
            "sealed runner returned an invalid prediction commitment"
        )
    if (
        prediction.case_id,
        prediction.case_sha256,
        prediction.ordinal,
        prediction.candidate_count,
    ) != (
        case.case_id,
        case.case_sha256,
        case.ordinal,
        case.candidate_count,
    ):
        raise StrategicSealedEvaluationError("sealed runner prediction differs from its case")


def _require_teacher_result_matches_case(
    teacher: StrategicSealedTeacherResult,
    case: StrategicSealedEvaluationCase,
) -> None:
    if not isinstance(teacher, StrategicSealedTeacherResult):
        raise StrategicSealedEvaluationError("sealed runner returned an invalid teacher result")
    if (
        teacher.case_id,
        teacher.case_sha256,
        teacher.ordinal,
        teacher.candidate_count,
    ) != (
        case.case_id,
        case.case_sha256,
        case.ordinal,
        case.candidate_count,
    ):
        raise StrategicSealedEvaluationError("sealed runner teacher result differs from its case")


def _outcome_from_prediction_and_teacher(
    prediction: StrategicSealedPrediction,
    teacher: StrategicSealedTeacherResult,
) -> StrategicSealedCaseOutcome:
    if teacher.execution_status != "succeeded":
        return StrategicSealedCaseOutcome(
            case_id=teacher.case_id,
            case_sha256=teacher.case_sha256,
            ordinal=teacher.ordinal,
            candidate_count=teacher.candidate_count,
            execution_status="failed",
        )
    return StrategicSealedCaseOutcome(
        case_id=teacher.case_id,
        case_sha256=teacher.case_sha256,
        ordinal=teacher.ordinal,
        candidate_count=teacher.candidate_count,
        execution_status="succeeded",
        teacher_target_index=teacher.teacher_target_index,
        model_prediction_index=prediction.model_prediction_index,
        model_prediction_tied=prediction.model_prediction_tied,
        baseline_prediction_index=prediction.baseline_prediction_index,
        baseline_prediction_tied=prediction.baseline_prediction_tied,
        policy_input_sha256=prediction.policy_input_sha256,
        episode_manifest_sha256=teacher.episode_manifest_sha256,
    )


def _require_prediction_consistent_with_outcome(
    prediction: StrategicSealedPrediction | None,
    outcome: StrategicSealedCaseOutcome,
) -> None:
    if outcome.execution_status == "succeeded":
        if prediction is None:
            raise StrategicSealedEvaluationError(
                "successful sealed outcome lacks a prediction commitment"
            )
        if (
            outcome.case_id,
            outcome.case_sha256,
            outcome.ordinal,
            outcome.candidate_count,
            outcome.model_prediction_index,
            outcome.model_prediction_tied,
            outcome.baseline_prediction_index,
            outcome.baseline_prediction_tied,
            outcome.policy_input_sha256,
        ) != (
            prediction.case_id,
            prediction.case_sha256,
            prediction.ordinal,
            prediction.candidate_count,
            prediction.model_prediction_index,
            prediction.model_prediction_tied,
            prediction.baseline_prediction_index,
            prediction.baseline_prediction_tied,
            prediction.policy_input_sha256,
        ):
            raise StrategicSealedEvaluationError(
                "sealed outcome differs from its prediction commitment"
            )
    elif outcome.execution_status == "candidate_unavailable" and prediction is not None:
        raise StrategicSealedEvaluationError(
            "unavailable sealed case must precede prediction commitment"
        )


def _validate_receipt_plan_binding(
    document: Mapping[str, object],
    *,
    plan: StrategicSealedEvaluationPlan,
    source_commit: str,
    subject: str,
) -> None:
    if document["evaluation_id"] != plan.evaluation_id:
        raise StrategicSealedEvaluationError(f"{subject} evaluation differs")
    if document["plan_sha256"] != plan.plan_sha256:
        raise StrategicSealedEvaluationError(f"{subject} plan differs")
    if document["execution_source_bundle_sha256"] != (plan.execution_source_bundle_sha256):
        raise StrategicSealedEvaluationError(f"{subject} source bundle differs")
    if document["source_commit"] != source_commit:
        raise StrategicSealedEvaluationError(f"{subject} source commit differs")


def _external_audit_verdict(value: object) -> str:
    verdict = _text(value, subject="sealed external audit verdict")
    if verdict not in {
        "approved_for_live_qualification",
        "approved_for_authorization",
        "changes_required",
    }:
        raise StrategicSealedEvaluationError("sealed external audit verdict is invalid")
    return verdict


def _non_test_qualification_verdict(value: object) -> str:
    verdict = _text(value, subject="sealed non-test qualification verdict")
    if verdict not in {"passed", "failed"}:
        raise StrategicSealedEvaluationError("sealed non-test qualification verdict is invalid")
    return verdict


def _validate_authorizing_receipts(
    plan: StrategicSealedEvaluationPlan,
    *,
    source_commit: str,
    external_audit_receipt: StrategicSealedExternalAuditReceipt,
    non_test_adapter_qualification_receipt: (StrategicSealedNonTestQualificationReceipt),
) -> None:
    if not isinstance(
        external_audit_receipt, StrategicSealedExternalAuditReceipt
    ) or not isinstance(
        non_test_adapter_qualification_receipt,
        StrategicSealedNonTestQualificationReceipt,
    ):
        raise TypeError("sealed authorization requires typed evidence receipts")
    _sha256(
        external_audit_receipt.receipt_sha256,
        subject="sealed external audit receipt",
    )
    _sha256(
        non_test_adapter_qualification_receipt.receipt_sha256,
        subject="sealed non-test adapter qualification receipt",
    )
    for receipt, subject in (
        (external_audit_receipt, "sealed external audit receipt"),
        (
            non_test_adapter_qualification_receipt,
            "sealed non-test qualification receipt",
        ),
    ):
        if receipt.plan_sha256 != plan.plan_sha256:
            raise StrategicSealedEvaluationError(f"{subject} plan differs")
        if receipt.execution_source_bundle_sha256 != (plan.execution_source_bundle_sha256):
            raise StrategicSealedEvaluationError(f"{subject} source bundle differs")
        if receipt.source_commit != source_commit:
            raise StrategicSealedEvaluationError(f"{subject} source commit differs")
    if external_audit_receipt.verdict != "approved_for_authorization":
        raise StrategicSealedEvaluationError("sealed external audit did not approve authorization")
    if (
        non_test_adapter_qualification_receipt.verdict != "passed"
        or non_test_adapter_qualification_receipt.sealed_test_cases_opened != 0
    ):
        raise StrategicSealedEvaluationError(
            "sealed non-test adapter qualification did not pass cleanly"
        )


def _validate_authorization_binding(
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
) -> None:
    _sha256(
        authorization.authorization_sha256,
        subject="sealed authorization digest",
    )
    _safe_id(
        authorization.authorization_id,
        subject="sealed authorization identity",
    )
    _safe_id(authorization.authorized_by, subject="sealed authorizer identity")
    _require_iso_date(
        authorization.authorized_on,
        subject="sealed authorization date",
    )
    if _GIT_OID.fullmatch(authorization.source_commit) is None:
        raise StrategicSealedEvaluationError("sealed authorization commit is invalid")
    _sha256(authorization.case_catalog_sha256, subject="sealed case catalog")
    _sha256(
        authorization.external_audit_receipt_sha256,
        subject="sealed external audit receipt",
    )
    _sha256(
        authorization.non_test_adapter_qualification_receipt_sha256,
        subject="sealed non-test adapter qualification receipt",
    )
    if (
        authorization.plan_sha256 != plan.plan_sha256
        or authorization.execution_source_bundle_sha256 != plan.execution_source_bundle_sha256
        or authorization.model_canonical_sha256 != plan.model_canonical_sha256
        or authorization.model_file_sha256 != plan.model_file_sha256
        or authorization.teacher_execution_sha256 != plan.teacher_execution_sha256
    ):
        raise StrategicSealedEvaluationError("sealed execution authorization differs")


def _validate_runtime_grant(
    plan: StrategicSealedEvaluationPlan,
    authorization: StrategicSealedAuthorization,
    runtime_grant: StrategicSealedRuntimeGrant,
) -> None:
    if runtime_grant._issued_token is not _PREFLIGHT_VALIDATION_TOKEN:
        raise StrategicSealedEvaluationError("sealed runtime grant is invalid")
    if (
        runtime_grant.plan_sha256 != plan.plan_sha256
        or runtime_grant.authorization_sha256 != authorization.authorization_sha256
        or runtime_grant.source_commit != authorization.source_commit
        or runtime_grant.teacher_execution_sha256 != authorization.teacher_execution_sha256
        or runtime_grant.case_catalog_sha256 != authorization.case_catalog_sha256
        or runtime_grant.external_audit_receipt_sha256
        != authorization.external_audit_receipt_sha256
        or runtime_grant.non_test_adapter_qualification_receipt_sha256
        != authorization.non_test_adapter_qualification_receipt_sha256
    ):
        raise StrategicSealedEvaluationError("sealed runtime grant differs")


def _validate_amendments(value: object) -> None:
    expected = [
        {
            "amended_before_private_access": True,
            "change": "primary_endpoint_restricted_to_preregistered_challenge_cases",
            "reason": (
                "independent_power_audit_found_non_challenge_cases_asymmetric_for_primary_pairing"
            ),
            "supersedes_plan_sha256": (
                "ef9f823e6f5e0e766b071cf8a98bb5ff743af11bcf6bcb0eb3ec160344b7331b"
            ),
        },
        {
            "amended_before_private_access": True,
            "change": "bind_fail_closed_executor_and_optional_stopping_contract",
            "reason": ("external_audit_required_durable_claim_before_private_case_access"),
            "supersedes_plan_sha256": (
                "230c90aa7120cd6badef8e933ccf014639889781fa1e32ecb4a486a6a2ef5537"
            ),
        },
        {
            "amended_before_private_access": True,
            "change": "bind_case_catalog_and_cartridge_adapter_contract",
            "reason": (
                "complete_prediction_first_private_input_adapter_before_"
                "external_audit_and_owner_authorization"
            ),
            "supersedes_plan_sha256": (
                "f4429dce83b99c4c5dce05785b2222e590c6d670adc0966d8f6b86e5c88d4fec"
            ),
        },
        {
            "amended_before_private_access": True,
            "change": "bind_authenticated_challenge_relocation_contract",
            "reason": (
                "independent_adapter_audit_found_source_and_declared_challenge_origins_differ"
            ),
            "supersedes_plan_sha256": (
                "63b3855463fcf8834ee8ae7635df1726b78fcde52257b0c7c5a3ecb26de131d7"
            ),
        },
        {
            "amended_before_private_access": True,
            "change": "bind_readiness_receipts_and_unforgeable_runtime_objects",
            "reason": (
                "self_audit_found_descriptive_gates_and_copyable_"
                "validation_tokens_were_not_sufficient"
            ),
            "supersedes_plan_sha256": (
                "2f7ec30b096655d23626a7a98107df770fe7e9a26943240a45f5887e72a5cba6"
            ),
        },
        {
            "amended_before_private_access": True,
            "change": ("bind_typed_receipt_verdicts_and_shared_non_test_production_qualification"),
            "reason": (
                "external_audit_found_bare_receipt_digests_could_not_"
                "distinguish_unfavorable_verdicts"
            ),
            "supersedes_plan_sha256": (
                "9df65487806d80b7d37e074c6f1ecf0ddf615e9853f7615e5681975e461ff440"
            ),
        },
        {
            "amended_before_private_access": True,
            "change": (
                "bind_directional_warp_arrival_and_durable_failed_qualification_receipts"
            ),
            "reason": (
                "live_non_test_saffron_cinnabar_qualification_exposed_"
                "directional_door_arrival_mismatch"
            ),
            "supersedes_plan_sha256": (
                "d5ade0bf749b24f5d266f568daa7da96b715b166bd05c41c473f6d91722f582a"
            ),
        },
    ]
    if value != expected:
        raise StrategicSealedEvaluationError("sealed amendment chain differs")


def _validate_endpoint_policy(value: object) -> None:
    if value != {
        "all_case_accuracy": {
            "case_filter": "all_registered_cases",
            "expected_case_count": 12,
            "metrics": ["model_accuracy", "route_cost_baseline_accuracy"],
            "role": "mandatory_descriptive_report",
        },
        "candidate_count_accuracy": {
            "case_filter": "all_registered_cases",
            "group_by": "candidate_count",
            "metrics": ["model_accuracy", "route_cost_baseline_accuracy"],
            "role": "mandatory_descriptive_report",
        },
        "primary": {
            "case_filter": "cost_baseline_challenge_hypothesis_true",
            "expected_case_count": 10,
            "minimum_measured_teacher_baseline_disagreements": 6,
            "paired_test": "two_sided_exact_mcnemar_on_discordant_correctness",
            "primary_unit": "one_unique_scenario",
            "required_direction": "model_paired_wins_exceed_losses",
            "required_successful_teacher_cases": 10,
            "significance_threshold": 0.05,
        },
        "safety": {
            "case_filter": "cost_baseline_challenge_hypothesis_false",
            "criterion": ("all_cases_succeed_and_zero_model_incorrect_baseline_correct"),
            "expected_case_count": 2,
            "failure_effect": ("block_live_authority_and_report_without_changing_primary_test"),
            "role": "preregistered_baseline_favorable_non_regression",
        },
    }:
        raise StrategicSealedEvaluationError("sealed endpoint policy differs")


def _validate_scoring_policy(value: object) -> None:
    if value != {
        "candidate_unavailable_after_claim": ("case_consumed_model_and_baseline_incorrect"),
        "failed_or_interrupted_after_claim": ("case_consumed_model_and_baseline_incorrect"),
        "incomplete_episode": "case_consumed_model_and_baseline_incorrect",
        "missing_case": "publish_incomplete_evaluation_as_protocol_failure",
        "model_prediction_tie": "incorrect",
        "preclaim_identity_or_catalog_failure": ("open_zero_cases_and_refuse_execution"),
        "teacher_target": "successful_deterministic_teacher_choice_only",
    }:
        raise StrategicSealedEvaluationError("sealed scoring policy differs")


def _validate_execution_policy(
    value: Mapping[str, object],
    cases: tuple[StrategicSealedEvaluationCase, ...],
) -> None:
    _exact_keys(
        value,
        {
            "candidate_counts_by_case",
            "case_claim",
            "case_order",
            "case_order_frozen",
            "halt_after_first_claim",
            "intermediate_case_results",
            "intermediate_statistics",
            "prediction_commit",
            "prepared_session_abort",
            "reopen_consumed_case",
            "restart_after_claim",
            "score_after_consumed_cases",
            "single_continuous_invocation_required",
        },
        subject="sealed execution policy",
    )
    expected_order = [case.case_id for case in cases]
    expected_counts = {case.case_id: case.candidate_count for case in cases}
    if value != {
        "candidate_counts_by_case": expected_counts,
        "case_claim": "durable_before_any_private_case_input_access",
        "case_order": expected_order,
        "case_order_frozen": True,
        "halt_after_first_claim": "publish_protocol_failure",
        "intermediate_case_results": "forbidden",
        "intermediate_statistics": "forbidden",
        "prediction_commit": "durable_before_deterministic_teacher_action",
        "prepared_session_abort": (
            "close_without_teacher_action_on_commitment_or_orchestration_failure"
        ),
        "reopen_consumed_case": False,
        "restart_after_claim": (
            "consume_open_case_as_both_incorrect_continue_next_mark_protocol_failure"
        ),
        "score_after_consumed_cases": SEALED_EVALUATION_CASES,
        "single_continuous_invocation_required": True,
    }:
        raise StrategicSealedEvaluationError("sealed execution policy differs")


def _parse_case(
    value: object,
    *,
    ordinal: int,
    candidate_counts: Mapping[str, object],
) -> StrategicSealedEvaluationCase:
    row = _mapping(value, subject="sealed evaluation case")
    _exact_keys(
        row,
        {
            "case_id",
            "case_sha256",
            "challenged_non_teacher_objective_id",
            "cost_baseline_challenge_hypothesis",
            "origin_region",
            "schema",
            "source_scenario_id",
            "source_scenario_sha256",
        },
        subject="sealed evaluation case",
    )
    if row["schema"] != "pokemon-strategic-navigation-sealed-evaluation-case-v1":
        raise StrategicSealedEvaluationError("sealed case schema differs")
    case_id = _safe_id(row["case_id"], subject="sealed case identity")
    if case_id != f"red-strategic-sealed-v1-{ordinal:03d}-test":
        raise StrategicSealedEvaluationError("sealed case order differs")
    payload = dict(row)
    case_sha256 = _sha256(payload.pop("case_sha256"), subject="sealed case digest")
    if case_sha256 != canonical_sha256(payload):
        raise StrategicSealedEvaluationError("sealed case digest differs")
    challenge = _boolean(row["cost_baseline_challenge_hypothesis"], subject="sealed challenge flag")
    challenged = row["challenged_non_teacher_objective_id"]
    if challenged is not None:
        challenged = _safe_id(challenged, subject="sealed challenged objective")
    if challenge != (challenged is not None):
        raise StrategicSealedEvaluationError("sealed challenge identity differs")
    if set(candidate_counts) != {
        f"red-strategic-sealed-v1-{index:03d}-test"
        for index in range(1, SEALED_EVALUATION_CASES + 1)
    }:
        raise StrategicSealedEvaluationError("sealed candidate count identities differ")
    candidate_count = _integer(
        candidate_counts.get(case_id),
        minimum=2,
        maximum=5,
        subject="sealed candidate count",
    )
    return StrategicSealedEvaluationCase(
        case_id=case_id,
        case_sha256=case_sha256,
        source_scenario_id=_safe_id(row["source_scenario_id"], subject="sealed source scenario"),
        source_scenario_sha256=_sha256(
            row["source_scenario_sha256"], subject="sealed source scenario digest"
        ),
        origin_region=_safe_id(row["origin_region"], subject="sealed origin region"),
        challenge=challenge,
        challenged_non_teacher_objective_id=challenged,
        candidate_count=candidate_count,
        ordinal=ordinal,
    )


def _execution_namespace(
    plan: StrategicSealedEvaluationPlan,
) -> str:
    return canonical_sha256(
        {
            "evaluation_id": plan.evaluation_id,
            "plan_sha256": plan.plan_sha256,
            "schema": "strategic-sealed-evaluation-private-namespace-v2",
        }
    )


def _record_id(kind: str, namespace: str) -> str:
    return f"red-seal-{kind}-{namespace[:48]}"


def _case_record_id(kind: str, ordinal: int, namespace: str) -> str:
    return f"red-seal-{kind}-{ordinal:02d}-{namespace[:44]}"


def _paired_two_sided_exact_p(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(min(wins, losses) + 1))
    return min(1.0, 2.0 * tail / math.pow(2.0, discordant))


def _decode_canonical(
    payload: bytes,
    *,
    maximum_bytes: int,
    subject: str,
) -> dict[str, object]:
    if not isinstance(payload, bytes) or not payload or len(payload) > maximum_bytes:
        raise StrategicSealedEvaluationError(f"{subject} size is invalid")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StrategicSealedEvaluationError(f"{subject} is invalid JSON") from error
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise StrategicSealedEvaluationError(f"{subject} is not canonical JSON")
    return value


def _canonical_line(value: object) -> bytes:
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


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrategicSealedEvaluationError("JSON object key is duplicated")
        result[key] = value
    return result


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise StrategicSealedEvaluationError(f"{subject} must be an object")
    return value


def _exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    *,
    subject: str,
) -> None:
    if set(value) != expected:
        raise StrategicSealedEvaluationError(f"{subject} fields differ")


def _text(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise StrategicSealedEvaluationError(f"{subject} must be non-empty text")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value, subject="optional sealed text")


def _safe_id(value: object, *, subject: str) -> str:
    result = _text(value, subject=subject)
    if _SAFE_ID.fullmatch(result) is None:
        raise StrategicSealedEvaluationError(f"{subject} is invalid")
    return result


def _sha256(value: object, *, subject: str) -> str:
    result = _text(value, subject=subject)
    if _SHA256.fullmatch(result) is None:
        raise StrategicSealedEvaluationError(f"{subject} is invalid")
    return result


def _integer(
    value: object,
    *,
    minimum: int,
    maximum: int,
    subject: str,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:  # noqa: E721
        raise StrategicSealedEvaluationError(f"{subject} is invalid")
    return value


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    return _integer(
        value,
        minimum=0,
        maximum=4,
        subject="optional sealed candidate index",
    )


def _validate_prediction_choice(
    value: int | None,
    *,
    tied: bool,
    candidate_count: int,
    subject: str,
) -> None:
    if not isinstance(tied, bool):
        raise StrategicSealedEvaluationError(f"{subject} tie must be boolean")
    if tied:
        if value is not None:
            raise StrategicSealedEvaluationError(f"tied {subject} must not select a candidate")
        return
    if value is None:
        raise StrategicSealedEvaluationError(f"{subject} lacks a candidate")
    _integer(
        value,
        minimum=0,
        maximum=candidate_count - 1,
        subject=subject,
    )


def _boolean(value: object, *, subject: str) -> bool:
    if not isinstance(value, bool):
        raise StrategicSealedEvaluationError(f"{subject} must be boolean")
    return value


def _require_iso_date(value: object, *, subject: str) -> str:
    result = _text(value, subject=subject)
    if _DATE.fullmatch(result) is None:
        raise StrategicSealedEvaluationError(f"{subject} is invalid")
    try:
        date.fromisoformat(result)
    except ValueError as error:
        raise StrategicSealedEvaluationError(f"{subject} is invalid") from error
    return result
