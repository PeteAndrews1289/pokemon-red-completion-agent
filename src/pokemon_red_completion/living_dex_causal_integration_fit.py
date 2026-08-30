"""One claim-first, non-authoritative fit over the authentic Red causal corpus.

This is the deliberately small bridge between the first eight authentic
selected-arm lessons and the later powered experiment.  It holds the causal
collection lock while it loads the complete family, requires the published
readiness proof, claims the one V1 fit identity before invoking the learner,
and publishes one immutable private model record.  It never opens development,
scores a gameplay menu, constructs an emulator, queries a teacher, or promotes
authority.

The fit is an integration proof, not evidence that the model generalizes or can
play Pokemon.  Its public result intentionally omits targets, coefficients,
losses, causal identities, lineages, paths, and private record contents.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from pokemon_red_completion.living_dex_causal_integration_readiness import (
    LivingDexCausalIntegrationReadiness,
    require_living_dex_causal_integration_ready,
)
from pokemon_red_completion.living_dex_causal_journal import (
    LIVING_DEX_CAUSAL_COLLECTION_ID,
    load_living_dex_authenticated_causal_examples,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OBJECTIVE,
    LivingDexObservedArmExample,
    LivingDexOptionValueModel,
    fit_living_dex_option_value,
    living_dex_option_train_dataset_sha256,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    PrivateSealedRecord,
)

LIVING_DEX_CAUSAL_INTEGRATION_FIT_RESULT_SCHEMA = (
    "pokemon.red.living-dex-causal-integration-fit-result.v1"
)
LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_SCHEMA = (
    "pokemon.core.private-living-dex-causal-integration-fit-claim.v1"
)
LIVING_DEX_CAUSAL_INTEGRATION_MODEL_SCHEMA = (
    "pokemon.core.private-living-dex-causal-integration-model.v1"
)
LIVING_DEX_CAUSAL_INTEGRATION_FIT_COLLECTION_ID = (
    "living-dex-causal-integration-fit-v1"
)
LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_ID = "lc-integration-fit-claim-v1"
LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID = "lc-integration-model-v1"
LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_KIND = (
    "living_dex_causal_integration_fit_claim"
)
LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND = "living_dex_causal_integration_model"
LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256 = (
    "d0fcaeb7bde027d4320d2c6b4a119b98a0bf84f2d4a4d56f2104bd24f76f5bff"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class LivingDexCausalIntegrationFitError(RuntimeError):
    """The one integration fit failed closed at a path-free stage."""

    def __init__(
        self,
        stage: str,
        *,
        fit_executions: int = 0,
        private_fit_claims: int = 0,
    ) -> None:
        self.stage = stage
        self.fit_executions = fit_executions
        self.private_fit_claims = private_fit_claims
        super().__init__(stage)


@dataclass(frozen=True, slots=True)
class LivingDexCausalIntegrationSource:
    """Published source and green-CI identity retained with the private model."""

    source_commit: str
    source_bundle_sha256: str
    exact_ci_run: int
    exact_ci_attempt: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_commit, str)
            or _GIT_COMMIT.fullmatch(self.source_commit) is None
            or not isinstance(self.source_bundle_sha256, str)
            or _SHA256.fullmatch(self.source_bundle_sha256) is None
            or type(self.exact_ci_run) is not int  # noqa: E721
            or self.exact_ci_run <= 0
            or type(self.exact_ci_attempt) is not int  # noqa: E721
            or self.exact_ci_attempt <= 0
        ):
            raise LivingDexCausalIntegrationFitError("source_binding")

    def private_dict(self) -> dict[str, object]:
        return {
            "exact_ci_attempt": self.exact_ci_attempt,
            "exact_ci_run": self.exact_ci_run,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "exact_ci_attempt": self.exact_ci_attempt,
            "exact_ci_run": self.exact_ci_run,
            "source_bundle_sha256": self.source_bundle_sha256,
            "source_commit": self.source_commit,
            "source_published": True,
            "worktree_dirty": False,
        }


@dataclass(frozen=True, slots=True)
class LivingDexCausalIntegrationFitResult:
    """Path-free diagnostics for the one completed plumbing fit."""

    source: LivingDexCausalIntegrationSource
    authentic_examples: int
    settled_examples: int
    candidate_feature_rows: int
    supported_candidate_feature_rows: int
    distinct_selected_feature_rows: int
    variable_target_heads: int
    normal_equation_condition_number: float
    finite_coefficient_count: int
    coefficient_count: int
    model_sha256: str
    model_record_sha256: str
    model_manifest_sha256: str
    reload_bytes_equal: bool
    reload_model_equal: bool
    recovered_existing_artifact: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source, LivingDexCausalIntegrationSource):
            raise TypeError("integration fit result source differs")
        for value in (
            self.authentic_examples,
            self.settled_examples,
            self.candidate_feature_rows,
            self.supported_candidate_feature_rows,
            self.distinct_selected_feature_rows,
            self.variable_target_heads,
            self.finite_coefficient_count,
            self.coefficient_count,
        ):
            if type(value) is not int or value < 0:  # noqa: E721
                raise LivingDexCausalIntegrationFitError("fit_diagnostics")
        if (
            not math.isfinite(self.normal_equation_condition_number)
            or self.normal_equation_condition_number <= 0.0
            or self.finite_coefficient_count != self.coefficient_count
            or any(
                not isinstance(value, str) or _SHA256.fullmatch(value) is None
                for value in (
                    self.model_sha256,
                    self.model_record_sha256,
                    self.model_manifest_sha256,
                )
            )
            or self.reload_bytes_equal is not True
            or self.reload_model_equal is not True
            or type(self.recovered_existing_artifact) is not bool  # noqa: E721
        ):
            raise LivingDexCausalIntegrationFitError("fit_diagnostics")

    def public_dict(self) -> dict[str, object]:
        """Expose only provenance, aggregate fit health, and zero-effect counters."""

        return {
            "artifact": {
                "manifest_sha256": self.model_manifest_sha256,
                "model_sha256": self.model_sha256,
                "record_sha256": self.model_record_sha256,
                "reload_bytes_equal": self.reload_bytes_equal,
                "reload_model_equal": self.reload_model_equal,
            },
            "authority_promotions": 0,
            "candidate_feature_rows": self.candidate_feature_rows,
            "censored_examples": self.authentic_examples - self.settled_examples,
            "coefficient_finiteness": {
                "all_finite": True,
                "coefficients": self.coefficient_count,
                "finite_coefficients": self.finite_coefficient_count,
            },
            "complete_denominator_included": True,
            "conditioning": {
                "matrix": "ridge-regularized-weighted-normal-equation",
                "number": self.normal_equation_condition_number,
            },
            "controller_actions": 0,
            "counterfactual_targets": 0,
            "crystal_accesses": 0,
            "development_examples_read": 0,
            "emulator_frames": 0,
            "fit_authority": "non-authoritative-integration-only",
            "fit_executions": 1,
            "gameplay_model_predictions": 0,
            "private_causal_identity_fields": 0,
            "private_fit_claims": 1,
            "private_path_fields": 0,
            "recovered_existing_artifact": self.recovered_existing_artifact,
            "root_claims": 0,
            "schema": LIVING_DEX_CAUSAL_INTEGRATION_FIT_RESULT_SCHEMA,
            "selected_outcome_details": 0,
            "settled_examples": self.settled_examples,
            "source": self.source.public_dict(),
            "status": "non_authoritative_integration_fit_complete",
            "supported_candidate_feature_rows": self.supported_candidate_feature_rows,
            "teacher_queries": 0,
            "total_examples": self.authentic_examples,
            "train_examples": self.authentic_examples,
            "transfer_claimed": False,
            "unselected_action_targets": 0,
            "variable_target_heads": self.variable_target_heads,
        }


def fit_living_dex_causal_integration_from_store(
    store: PrivateArtifactRoot,
    *,
    source: LivingDexCausalIntegrationSource,
    readiness_result_sha256: str,
) -> LivingDexCausalIntegrationFitResult:
    """Claim, fit, publish, and byte-reload the complete authentic corpus once."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("integration fit needs a private artifact root")
    if not isinstance(source, LivingDexCausalIntegrationSource):
        raise TypeError("integration fit needs its source binding")
    if readiness_result_sha256 != LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256:
        raise LivingDexCausalIntegrationFitError("readiness_proof")

    fit_executions = 0
    private_fit_claims = 0
    try:
        with store.collection_session(LIVING_DEX_CAUSAL_COLLECTION_ID) as causal_session:
            examples = load_living_dex_authenticated_causal_examples(
                store,
                collection_session=causal_session,
            )
            readiness = require_living_dex_causal_integration_ready(examples)
            rows = tuple(row.example for row in examples)
            dataset_sha256 = living_dex_option_train_dataset_sha256(rows)
            claim_document = _claim_document(
                source=source,
                readiness=readiness,
                readiness_result_sha256=readiness_result_sha256,
                train_dataset_sha256=dataset_sha256,
            )
            with store.collection_session(
                LIVING_DEX_CAUSAL_INTEGRATION_FIT_COLLECTION_ID
            ):
                existing_claim = store.find_sealed_record(
                    LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_ID,
                    expected_kind=LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_KIND,
                )
                existing_model = store.find_sealed_record(
                    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
                    expected_kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
                )
                if existing_claim is not None or existing_model is not None:
                    private_fit_claims = int(existing_claim is not None)
                    if existing_claim is None or existing_model is None:
                        raise LivingDexCausalIntegrationFitError(
                            "incomplete_prior_fit_claim",
                            private_fit_claims=private_fit_claims,
                        )
                    return _reload_existing_result(
                        claim=existing_claim,
                        model_record=existing_model,
                        expected_claim=claim_document,
                        source=source,
                        readiness=readiness,
                        rows=rows,
                    )

                claim = store.publish_sealed_record(
                    LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_ID,
                    kind=LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_KIND,
                    record=claim_document,
                )
                private_fit_claims = 1
                try:
                    fit_executions = 1
                    fit = fit_living_dex_option_value(rows)
                except BaseException:
                    raise LivingDexCausalIntegrationFitError(
                        "model_fit",
                        fit_executions=1,
                        private_fit_claims=1,
                    ) from None
                try:
                    if (
                        fit.report.total_examples != len(rows)
                        or fit.report.settled_examples != len(rows)
                        or fit.report.censored_examples != 0
                        or fit.report.train_dataset_sha256 != dataset_sha256
                        or fit.model.train_dataset_sha256 != dataset_sha256
                    ):
                        raise LivingDexCausalIntegrationFitError(
                            "complete_denominator_join",
                            fit_executions=1,
                            private_fit_claims=1,
                        )
                    diagnostics = _private_diagnostics(fit.model, rows)
                    model_document = _model_document(
                        source=source,
                        claim=claim,
                        readiness_result_sha256=readiness_result_sha256,
                        train_dataset_sha256=dataset_sha256,
                        model=fit.model,
                        diagnostics=diagnostics,
                    )
                    published = store.publish_sealed_record(
                        LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
                        kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
                        record=model_document,
                    )
                    reopened = store.find_sealed_record(
                        LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
                        expected_kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
                    )
                    if reopened is None:
                        raise LivingDexCausalIntegrationFitError(
                            "model_reload",
                            fit_executions=1,
                            private_fit_claims=1,
                        )
                    return _result_from_model_record(
                        source=source,
                        readiness=readiness,
                        rows=rows,
                        expected_claim=claim_document,
                        claim=claim,
                        published=published,
                        reopened=reopened,
                        recovered_existing_artifact=False,
                    )
                except LivingDexCausalIntegrationFitError as error:
                    if error.fit_executions == 1:
                        raise
                    raise LivingDexCausalIntegrationFitError(
                        error.stage,
                        fit_executions=1,
                        private_fit_claims=1,
                    ) from None
                except BaseException:
                    raise LivingDexCausalIntegrationFitError(
                        "model_publication_or_reload",
                        fit_executions=1,
                        private_fit_claims=1,
                    ) from None
    except LivingDexCausalIntegrationFitError as error:
        if (
            error.fit_executions >= fit_executions
            and error.private_fit_claims >= private_fit_claims
        ):
            raise
        raise LivingDexCausalIntegrationFitError(
            error.stage,
            fit_executions=max(error.fit_executions, fit_executions),
            private_fit_claims=max(error.private_fit_claims, private_fit_claims),
        ) from None
    except BaseException:
        raise LivingDexCausalIntegrationFitError(
            "private_corpus_or_store",
            fit_executions=fit_executions,
            private_fit_claims=private_fit_claims,
        ) from None
    raise AssertionError("private collection sessions suppressed control flow")


def _claim_document(
    *,
    source: LivingDexCausalIntegrationSource,
    readiness: LivingDexCausalIntegrationReadiness,
    readiness_result_sha256: str,
    train_dataset_sha256: str,
) -> dict[str, object]:
    return {
        "authority": "non_authoritative_integration_only",
        "complete_denominator_included": True,
        "objective": LIVING_DEX_OPTION_OBJECTIVE,
        "readiness_result_sha256": readiness_result_sha256,
        "schema": LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_SCHEMA,
        "settled_examples": readiness.settled_examples,
        "source": source.private_dict(),
        "train_dataset_sha256": train_dataset_sha256,
        "train_examples": readiness.train_examples,
    }


def _model_document(
    *,
    source: LivingDexCausalIntegrationSource,
    claim: PrivateSealedRecord,
    readiness_result_sha256: str,
    train_dataset_sha256: str,
    model: LivingDexOptionValueModel,
    diagnostics: Mapping[str, object],
) -> dict[str, object]:
    return {
        "authority": "non_authoritative_integration_only",
        "claim_manifest_sha256": claim.summary.manifest_sha256,
        "claim_record_sha256": claim.summary.record_sha256,
        "diagnostics": dict(diagnostics),
        "model": model.to_dict(),
        "model_sha256": model.model_sha256,
        "readiness_result_sha256": readiness_result_sha256,
        "schema": LIVING_DEX_CAUSAL_INTEGRATION_MODEL_SCHEMA,
        "source": source.private_dict(),
        "train_dataset_sha256": train_dataset_sha256,
    }


def _private_diagnostics(
    model: LivingDexOptionValueModel,
    rows: tuple[LivingDexObservedArmExample, ...],
) -> dict[str, object]:
    ordered = tuple(sorted(rows, key=lambda row: row.decision_sha256))
    features = np.asarray([row.selected_vector for row in ordered], dtype=np.float64)
    weights = np.asarray(
        [row.importance_weight(model.maximum_importance_weight) for row in ordered],
        dtype=np.float64,
    )
    normalized = (features - model.feature_mean) / model.feature_scale
    design = np.column_stack((np.ones(len(ordered), dtype=np.float64), normalized))
    penalty = np.eye(design.shape[1], dtype=np.float64)
    penalty[0, 0] = 0.0
    normal = design.T @ (design * weights[:, np.newaxis]) + model.ridge * penalty
    condition_number = float(np.linalg.cond(normal))
    coefficients = (model.coefficients, model.intercept)
    normalizers = (model.feature_mean, model.feature_scale)
    coefficient_count = sum(int(value.size) for value in coefficients)
    finite_coefficient_count = sum(
        int(np.count_nonzero(np.isfinite(value))) for value in coefficients
    )
    if (
        not math.isfinite(condition_number)
        or condition_number <= 0.0
        or finite_coefficient_count != coefficient_count
        or not all(np.all(np.isfinite(value)) for value in normalizers)
    ):
        raise LivingDexCausalIntegrationFitError(
            "fit_diagnostics",
            fit_executions=1,
            private_fit_claims=1,
        )
    return {
        "coefficient_count": coefficient_count,
        "finite_coefficient_count": finite_coefficient_count,
        "normal_equation_condition_number": condition_number,
    }


def _reload_existing_result(
    *,
    claim: PrivateSealedRecord,
    model_record: PrivateSealedRecord,
    expected_claim: Mapping[str, object],
    source: LivingDexCausalIntegrationSource,
    readiness: LivingDexCausalIntegrationReadiness,
    rows: tuple[LivingDexObservedArmExample, ...],
) -> LivingDexCausalIntegrationFitResult:
    if claim.read() != dict(expected_claim):
        raise LivingDexCausalIntegrationFitError("prior_fit_claim_join")
    return _result_from_model_record(
        source=source,
        readiness=readiness,
        rows=rows,
        expected_claim=expected_claim,
        claim=claim,
        published=model_record,
        reopened=model_record,
        recovered_existing_artifact=True,
    )


def _result_from_model_record(
    *,
    source: LivingDexCausalIntegrationSource,
    readiness: LivingDexCausalIntegrationReadiness,
    rows: tuple[LivingDexObservedArmExample, ...],
    expected_claim: Mapping[str, object],
    claim: PrivateSealedRecord,
    published: PrivateSealedRecord,
    reopened: PrivateSealedRecord,
    recovered_existing_artifact: bool,
) -> LivingDexCausalIntegrationFitResult:
    if claim.read() != dict(expected_claim):
        raise LivingDexCausalIntegrationFitError("fit_claim_join")
    document = reopened.read()
    expected_keys = {
        "authority",
        "claim_manifest_sha256",
        "claim_record_sha256",
        "diagnostics",
        "model",
        "model_sha256",
        "readiness_result_sha256",
        "schema",
        "source",
        "train_dataset_sha256",
    }
    if set(document) != expected_keys:
        raise LivingDexCausalIntegrationFitError("model_record_schema")
    model_payload = document.get("model")
    diagnostics = document.get("diagnostics")
    if not isinstance(model_payload, Mapping) or not isinstance(diagnostics, Mapping):
        raise LivingDexCausalIntegrationFitError("model_record_schema")
    reloaded_model = LivingDexOptionValueModel.from_dict(model_payload)
    expected_dataset = living_dex_option_train_dataset_sha256(rows)
    model_sha256 = reloaded_model.model_sha256
    if (
        document.get("schema") != LIVING_DEX_CAUSAL_INTEGRATION_MODEL_SCHEMA
        or document.get("authority") != "non_authoritative_integration_only"
        or document.get("claim_manifest_sha256") != claim.summary.manifest_sha256
        or document.get("claim_record_sha256") != claim.summary.record_sha256
        or document.get("readiness_result_sha256")
        != LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256
        or document.get("source") != source.private_dict()
        or document.get("train_dataset_sha256") != expected_dataset
        or document.get("model_sha256") != model_sha256
        or reloaded_model.train_dataset_sha256 != expected_dataset
    ):
        raise LivingDexCausalIntegrationFitError("model_record_join")
    condition_number = diagnostics.get("normal_equation_condition_number")
    finite_coefficient_count = diagnostics.get("finite_coefficient_count")
    coefficient_count = diagnostics.get("coefficient_count")
    if (
        isinstance(condition_number, bool)
        or not isinstance(condition_number, (int, float))
        or type(finite_coefficient_count) is not int  # noqa: E721
        or type(coefficient_count) is not int  # noqa: E721
    ):
        raise LivingDexCausalIntegrationFitError("model_record_diagnostics")
    published_bytes = published.read_bytes()
    reopened_bytes = reopened.read_bytes()
    bytes_equal = published_bytes == reopened_bytes
    semantic_equal = reloaded_model.to_dict() == model_payload
    if not bytes_equal or not semantic_equal:
        raise LivingDexCausalIntegrationFitError("model_reload_equality")
    return LivingDexCausalIntegrationFitResult(
        source=source,
        authentic_examples=len(rows),
        settled_examples=readiness.settled_examples,
        candidate_feature_rows=readiness.candidate_feature_rows,
        supported_candidate_feature_rows=readiness.supported_candidate_feature_rows,
        distinct_selected_feature_rows=readiness.distinct_selected_feature_rows,
        variable_target_heads=readiness.variable_target_heads,
        normal_equation_condition_number=float(condition_number),
        finite_coefficient_count=finite_coefficient_count,
        coefficient_count=coefficient_count,
        model_sha256=model_sha256,
        model_record_sha256=reopened.summary.record_sha256,
        model_manifest_sha256=reopened.summary.manifest_sha256,
        reload_bytes_equal=bytes_equal,
        reload_model_equal=semantic_equal,
        recovered_existing_artifact=recovered_existing_artifact,
    )


__all__ = [
    "LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_ID",
    "LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_KIND",
    "LIVING_DEX_CAUSAL_INTEGRATION_FIT_CLAIM_SCHEMA",
    "LIVING_DEX_CAUSAL_INTEGRATION_FIT_COLLECTION_ID",
    "LIVING_DEX_CAUSAL_INTEGRATION_FIT_RESULT_SCHEMA",
    "LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID",
    "LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND",
    "LIVING_DEX_CAUSAL_INTEGRATION_MODEL_SCHEMA",
    "LIVING_DEX_CAUSAL_INTEGRATION_READINESS_RESULT_SHA256",
    "LivingDexCausalIntegrationFitError",
    "LivingDexCausalIntegrationFitResult",
    "LivingDexCausalIntegrationSource",
    "fit_living_dex_causal_integration_from_store",
]
