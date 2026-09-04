"""Repeatable train-only updates for the causal living-Pokedex option model.

The first integration model intentionally froze after eight authentic examples.
Later Red collection added more immutable selected-arm outcomes, but the original
one-shot fitter could only reopen its eight-row artifact.  This module fits a new,
dataset-addressed model from the complete authenticated train corpus without
opening development data or granting gameplay authority.

Model fitting is deterministic and has no controller effects, so an interrupted
publication may safely resume from an identical durable claim.  Every published
model remains immutable and can be loaded by the existing bounded-player model
record loader.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from pokemon_red_completion.living_dex_causal_integration_fit import (
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
    LIVING_DEX_CAUSAL_INTEGRATION_MODEL_SCHEMA,
    LivingDexCausalIntegrationSource,
)
from pokemon_red_completion.living_dex_causal_journal import (
    LIVING_DEX_CAUSAL_COLLECTION_ID,
    load_living_dex_authenticated_causal_examples,
)
from pokemon_red_completion.living_dex_goal_policy import (
    DEFAULT_LIVING_DEX_GOAL_UTILITY,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OBJECTIVE,
    LivingDexObservedArmExample,
    LivingDexOptionValueModel,
    evaluate_living_dex_option_value,
    fit_living_dex_option_value,
    living_dex_option_train_dataset_sha256,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    PrivateSealedRecord,
)
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_CAUSAL_UPDATE_CLAIM_SCHEMA = (
    "pokemon.core.private-living-dex-causal-model-update-claim.v1"
)
LIVING_DEX_CAUSAL_UPDATE_RESULT_SCHEMA = (
    "pokemon.red.living-dex-causal-model-update-result.v1"
)
LIVING_DEX_CAUSAL_UPDATE_COLLECTION_ID = "living-dex-causal-model-update-v1"
LIVING_DEX_CAUSAL_UPDATE_CLAIM_KIND = "living_dex_causal_model_update_claim"
MINIMUM_CAUSAL_UPDATE_SETTLED_EXAMPLES = 9

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MODEL_RECORD_FIELDS = {
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
_DIAGNOSTIC_FIELDS = {
    "coefficient_count",
    "finite_coefficient_count",
    "normal_equation_condition_number",
}
_SOURCE_FIELDS = {
    "exact_ci_attempt",
    "exact_ci_run",
    "source_bundle_sha256",
    "source_commit",
}


class LivingDexCausalModelUpdateError(RuntimeError):
    """The train-only causal model update failed at a sanitized stage."""

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
class LivingDexCausalModelUpdateResult:
    """Aggregate result for one immutable corpus-addressed update."""

    source: LivingDexCausalIntegrationSource
    prior_model_sha256: str
    model_sha256: str
    model_record_sha256: str
    model_manifest_sha256: str
    total_examples: int
    settled_examples: int
    added_settled_examples: int
    successful_examples: int
    distinct_selected_feature_rows: int
    selected_kind_count: int
    policy_disagreements: int
    prior_training_mse: float
    updated_training_mse: float
    recovered_existing_artifact: bool

    def __post_init__(self) -> None:
        if not isinstance(self.source, LivingDexCausalIntegrationSource):
            raise TypeError("causal update result source differs")
        for value in (
            self.total_examples,
            self.settled_examples,
            self.added_settled_examples,
            self.successful_examples,
            self.distinct_selected_feature_rows,
            self.selected_kind_count,
            self.policy_disagreements,
        ):
            if type(value) is not int or value < 0:  # noqa: E721
                raise LivingDexCausalModelUpdateError("result_diagnostics")
        if (
            self.settled_examples < MINIMUM_CAUSAL_UPDATE_SETTLED_EXAMPLES
            or self.added_settled_examples <= 0
            or self.prior_model_sha256 == self.model_sha256
            or any(
                not isinstance(value, str) or _SHA256.fullmatch(value) is None
                for value in (
                    self.prior_model_sha256,
                    self.model_sha256,
                    self.model_record_sha256,
                    self.model_manifest_sha256,
                )
            )
            or any(
                not math.isfinite(value) or value < 0.0
                for value in (self.prior_training_mse, self.updated_training_mse)
            )
            or type(self.recovered_existing_artifact) is not bool  # noqa: E721
        ):
            raise LivingDexCausalModelUpdateError("result_diagnostics")

    def public_dict(self) -> dict[str, object]:
        """Return useful learning telemetry without corpus identities or paths."""

        return {
            "authority": "non_authoritative_shadow_only",
            "authority_promotions": 0,
            "controller_actions": 0,
            "counterfactual_targets": 0,
            "crystal_accesses": 0,
            "development_examples_read": 0,
            "distinct_selected_feature_rows": self.distinct_selected_feature_rows,
            "emulator_frames": 0,
            "fit_executions": 0 if self.recovered_existing_artifact else 1,
            "model": {
                "added_settled_examples": self.added_settled_examples,
                "manifest_sha256": self.model_manifest_sha256,
                "model_sha256": self.model_sha256,
                "prior_model_sha256": self.prior_model_sha256,
                "record_sha256": self.model_record_sha256,
                "settled_examples": self.settled_examples,
                "total_examples": self.total_examples,
            },
            "selected_arm_error_predictions": self.total_examples * 2,
            "objective": LIVING_DEX_OPTION_OBJECTIVE,
            "policy_disagreements_on_train_menus": self.policy_disagreements,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "recovered_existing_artifact": self.recovered_existing_artifact,
            "schema": LIVING_DEX_CAUSAL_UPDATE_RESULT_SCHEMA,
            "selected_kind_count": self.selected_kind_count,
            "source": self.source.public_dict(),
            "status": "train_only_causal_model_update_complete",
            "successful_examples": self.successful_examples,
            "teacher_queries": 0,
            "training_error": {
                "prior_weighted_mse": self.prior_training_mse,
                "updated_weighted_mse": self.updated_training_mse,
            },
            "transfer_claimed": False,
            "unselected_action_targets": 0,
        }


def fit_living_dex_causal_model_update_from_store(
    store: PrivateArtifactRoot,
    *,
    source: LivingDexCausalIntegrationSource,
) -> LivingDexCausalModelUpdateResult:
    """Fit or reopen the complete current causal train corpus."""

    if not isinstance(store, PrivateArtifactRoot):
        raise TypeError("causal update needs a private artifact root")
    if not isinstance(source, LivingDexCausalIntegrationSource):
        raise TypeError("causal update needs its source binding")
    fit_executions = 0
    private_fit_claims = 0
    try:
        with store.collection_session(LIVING_DEX_CAUSAL_COLLECTION_ID) as session:
            authenticated = load_living_dex_authenticated_causal_examples(
                store,
                collection_session=session,
            )
            rows = tuple(item.example for item in authenticated)
            prior_record = store.find_sealed_record(
                LIVING_DEX_CAUSAL_INTEGRATION_MODEL_ID,
                expected_kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
            )
            if prior_record is None:
                raise LivingDexCausalModelUpdateError("prior_model_absent")
            prior = _model_from_record(prior_record)
            settled_examples = sum(row.outcome.target_vector is not None for row in rows)
            if (
                any(row.partition != "train" for row in rows)
                or settled_examples < MINIMUM_CAUSAL_UPDATE_SETTLED_EXAMPLES
                or settled_examples <= prior.settled_examples
            ):
                raise LivingDexCausalModelUpdateError("corpus_not_extended")
            dataset_sha256 = living_dex_option_train_dataset_sha256(rows)
            if dataset_sha256 == prior.train_dataset_sha256:
                raise LivingDexCausalModelUpdateError("corpus_not_extended")
            readiness_sha256 = _readiness_sha256(
                rows,
                prior=prior,
                dataset_sha256=dataset_sha256,
            )
            claim_document = _claim_document(
                source=source,
                prior=prior,
                rows=rows,
                dataset_sha256=dataset_sha256,
                readiness_sha256=readiness_sha256,
            )
            claim_id = f"lc-update-claim-{dataset_sha256}"
            model_id = f"lc-update-model-{dataset_sha256}"
            with store.collection_session(LIVING_DEX_CAUSAL_UPDATE_COLLECTION_ID):
                claim = store.find_sealed_record(
                    claim_id,
                    expected_kind=LIVING_DEX_CAUSAL_UPDATE_CLAIM_KIND,
                )
                model_record = store.find_sealed_record(
                    model_id,
                    expected_kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
                )
                private_fit_claims = int(claim is not None)
                if model_record is not None and claim is None:
                    raise LivingDexCausalModelUpdateError("model_without_claim")
                if claim is not None and claim.read() != claim_document:
                    raise LivingDexCausalModelUpdateError("prior_update_claim_join")
                if claim is not None and model_record is not None:
                    return _result_from_records(
                        source=source,
                        prior=prior,
                        rows=rows,
                        claim=claim,
                        model_record=model_record,
                        readiness_sha256=readiness_sha256,
                        recovered=True,
                    )

                fit_executions = 1
                fit = fit_living_dex_option_value(rows)
                if (
                    fit.report.total_examples != len(rows)
                    or fit.report.settled_examples != settled_examples
                    or fit.report.train_dataset_sha256 != dataset_sha256
                    or fit.model.train_dataset_sha256 != dataset_sha256
                    or fit.model.model_sha256 == prior.model_sha256
                ):
                    raise LivingDexCausalModelUpdateError("complete_denominator_join")
                diagnostics = _model_diagnostics(fit.model, rows)
                if claim is None:
                    claim = store.publish_sealed_record(
                        claim_id,
                        kind=LIVING_DEX_CAUSAL_UPDATE_CLAIM_KIND,
                        record=claim_document,
                    )
                    private_fit_claims = 1
                model_document = _model_document(
                    source=source,
                    claim=claim,
                    model=fit.model,
                    diagnostics=diagnostics,
                    readiness_sha256=readiness_sha256,
                )
                model_record = store.publish_sealed_record(
                    model_id,
                    kind=LIVING_DEX_CAUSAL_INTEGRATION_MODEL_KIND,
                    record=model_document,
                )
                return _result_from_records(
                    source=source,
                    prior=prior,
                    rows=rows,
                    claim=claim,
                    model_record=model_record,
                    readiness_sha256=readiness_sha256,
                    recovered=False,
                )
    except LivingDexCausalModelUpdateError as error:
        if (
            error.fit_executions >= fit_executions
            and error.private_fit_claims >= private_fit_claims
        ):
            raise
        raise LivingDexCausalModelUpdateError(
            error.stage,
            fit_executions=max(error.fit_executions, fit_executions),
            private_fit_claims=max(error.private_fit_claims, private_fit_claims),
        ) from None
    except BaseException:
        raise LivingDexCausalModelUpdateError(
            "private_corpus_or_store",
            fit_executions=fit_executions,
            private_fit_claims=private_fit_claims,
        ) from None
    raise AssertionError("private collection sessions suppressed control flow")


def _model_from_record(record: PrivateSealedRecord) -> LivingDexOptionValueModel:
    document = record.read()
    model_document = document.get("model")
    model_sha256 = document.get("model_sha256")
    diagnostics = document.get("diagnostics")
    record_source = document.get("source")
    if (
        set(document) != _MODEL_RECORD_FIELDS
        or document.get("schema") != LIVING_DEX_CAUSAL_INTEGRATION_MODEL_SCHEMA
        or document.get("authority") != "non_authoritative_integration_only"
        or not isinstance(model_document, Mapping)
        or not isinstance(model_sha256, str)
        or _SHA256.fullmatch(model_sha256) is None
        or not isinstance(diagnostics, Mapping)
        or set(diagnostics) != _DIAGNOSTIC_FIELDS
        or not isinstance(record_source, Mapping)
        or set(record_source) != _SOURCE_FIELDS
        or not _record_digests_are_valid(document)
    ):
        raise LivingDexCausalModelUpdateError("model_record_schema")
    coefficient_count = diagnostics.get("coefficient_count")
    finite_count = diagnostics.get("finite_coefficient_count")
    condition_number = diagnostics.get("normal_equation_condition_number")
    if (
        type(coefficient_count) is not int  # noqa: E721
        or coefficient_count <= 0
        or type(finite_count) is not int  # noqa: E721
        or finite_count != coefficient_count
        or isinstance(condition_number, bool)
        or not isinstance(condition_number, (int, float))
        or not math.isfinite(float(condition_number))
        or float(condition_number) <= 0.0
    ):
        raise LivingDexCausalModelUpdateError("model_record_schema")
    try:
        model = LivingDexOptionValueModel.from_dict(model_document)
    except (TypeError, ValueError):
        raise LivingDexCausalModelUpdateError("model_record_schema") from None
    if (
        model.model_sha256 != model_sha256
        or model.train_dataset_sha256 != document.get("train_dataset_sha256")
    ):
        raise LivingDexCausalModelUpdateError("model_record_join")
    return model


def _record_digests_are_valid(document: Mapping[str, object]) -> bool:
    for field in (
        "claim_manifest_sha256",
        "claim_record_sha256",
        "readiness_result_sha256",
        "train_dataset_sha256",
    ):
        value = document.get(field)
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            return False
    return True


def _readiness_sha256(
    rows: tuple[LivingDexObservedArmExample, ...],
    *,
    prior: LivingDexOptionValueModel,
    dataset_sha256: str,
) -> str:
    settled = tuple(row for row in rows if row.outcome.target_vector is not None)
    return canonical_sha256(
        {
            "complete_denominator_included": True,
            "dataset_sha256": dataset_sha256,
            "development_examples": 0,
            "distinct_selected_feature_rows": len({row.selected_vector for row in settled}),
            "prior_model_sha256": prior.model_sha256,
            "schema": "pokemon.core.living-dex-causal-model-update-readiness.v1",
            "settled_examples": len(settled),
            "total_examples": len(rows),
        }
    )


def _claim_document(
    *,
    source: LivingDexCausalIntegrationSource,
    prior: LivingDexOptionValueModel,
    rows: tuple[LivingDexObservedArmExample, ...],
    dataset_sha256: str,
    readiness_sha256: str,
) -> dict[str, object]:
    return {
        "authority": "non_authoritative_integration_only",
        "complete_denominator_included": True,
        "development_examples": 0,
        "objective": LIVING_DEX_OPTION_OBJECTIVE,
        "prior_model_sha256": prior.model_sha256,
        "readiness_result_sha256": readiness_sha256,
        "schema": LIVING_DEX_CAUSAL_UPDATE_CLAIM_SCHEMA,
        "source": source.private_dict(),
        "train_dataset_sha256": dataset_sha256,
        "train_examples": len(rows),
    }


def _model_document(
    *,
    source: LivingDexCausalIntegrationSource,
    claim: PrivateSealedRecord,
    model: LivingDexOptionValueModel,
    diagnostics: Mapping[str, object],
    readiness_sha256: str,
) -> dict[str, object]:
    return {
        "authority": "non_authoritative_integration_only",
        "claim_manifest_sha256": claim.summary.manifest_sha256,
        "claim_record_sha256": claim.summary.record_sha256,
        "diagnostics": dict(diagnostics),
        "model": model.to_dict(),
        "model_sha256": model.model_sha256,
        "readiness_result_sha256": readiness_sha256,
        "schema": LIVING_DEX_CAUSAL_INTEGRATION_MODEL_SCHEMA,
        "source": source.private_dict(),
        "train_dataset_sha256": model.train_dataset_sha256,
    }


def _model_diagnostics(
    model: LivingDexOptionValueModel,
    rows: tuple[LivingDexObservedArmExample, ...],
) -> dict[str, object]:
    settled = tuple(row for row in rows if row.outcome.target_vector is not None)
    features = np.asarray([row.selected_vector for row in settled], dtype=np.float64)
    weights = np.asarray(
        [row.importance_weight(model.maximum_importance_weight) for row in settled],
        dtype=np.float64,
    )
    normalized = (features - model.feature_mean) / model.feature_scale
    design = np.column_stack((np.ones(len(settled), dtype=np.float64), normalized))
    penalty = np.eye(design.shape[1], dtype=np.float64)
    penalty[0, 0] = 0.0
    normal = design.T @ (design * weights[:, np.newaxis]) + model.ridge * penalty
    condition_number = float(np.linalg.cond(normal))
    coefficient_count = int(model.coefficients.size + model.intercept.size)
    finite_coefficient_count = int(
        np.count_nonzero(np.isfinite(model.coefficients))
        + np.count_nonzero(np.isfinite(model.intercept))
    )
    if (
        not math.isfinite(condition_number)
        or condition_number <= 0.0
        or finite_coefficient_count != coefficient_count
    ):
        raise LivingDexCausalModelUpdateError("fit_diagnostics")
    return {
        "coefficient_count": coefficient_count,
        "finite_coefficient_count": finite_coefficient_count,
        "normal_equation_condition_number": condition_number,
    }


def _result_from_records(
    *,
    source: LivingDexCausalIntegrationSource,
    prior: LivingDexOptionValueModel,
    rows: tuple[LivingDexObservedArmExample, ...],
    claim: PrivateSealedRecord,
    model_record: PrivateSealedRecord,
    readiness_sha256: str,
    recovered: bool,
) -> LivingDexCausalModelUpdateResult:
    document = model_record.read()
    model = _model_from_record(model_record)
    if (
        document.get("claim_manifest_sha256") != claim.summary.manifest_sha256
        or document.get("claim_record_sha256") != claim.summary.record_sha256
        or document.get("readiness_result_sha256") != readiness_sha256
        or document.get("source") != source.private_dict()
        or document.get("train_dataset_sha256")
        != living_dex_option_train_dataset_sha256(rows)
    ):
        raise LivingDexCausalModelUpdateError("model_record_join")
    prior_evaluation = evaluate_living_dex_option_value(
        prior,
        rows,
        expected_partition="train",
    )
    updated_evaluation = evaluate_living_dex_option_value(
        model,
        rows,
        expected_partition="train",
    )
    settled = tuple(row for row in rows if row.outcome.target_vector is not None)
    disagreements = sum(
        prior.select(row.menu, DEFAULT_LIVING_DEX_GOAL_UTILITY)
        != model.select(row.menu, DEFAULT_LIVING_DEX_GOAL_UTILITY)
        for row in rows
    )
    return LivingDexCausalModelUpdateResult(
        source=source,
        prior_model_sha256=prior.model_sha256,
        model_sha256=model.model_sha256,
        model_record_sha256=model_record.summary.record_sha256,
        model_manifest_sha256=model_record.summary.manifest_sha256,
        total_examples=len(rows),
        settled_examples=len(settled),
        added_settled_examples=len(settled) - prior.settled_examples,
        successful_examples=sum(bool(row.outcome.verified_success) for row in settled),
        distinct_selected_feature_rows=len({row.selected_vector for row in settled}),
        selected_kind_count=len(
            {
                row.menu.candidates[row.selected_candidate_index].features.kind
                for row in settled
            }
        ),
        policy_disagreements=disagreements,
        prior_training_mse=prior_evaluation.weighted_mse,
        updated_training_mse=updated_evaluation.weighted_mse,
        recovered_existing_artifact=recovered,
    )


__all__ = [
    "LIVING_DEX_CAUSAL_UPDATE_CLAIM_KIND",
    "LIVING_DEX_CAUSAL_UPDATE_CLAIM_SCHEMA",
    "LIVING_DEX_CAUSAL_UPDATE_COLLECTION_ID",
    "LIVING_DEX_CAUSAL_UPDATE_RESULT_SCHEMA",
    "MINIMUM_CAUSAL_UPDATE_SETTLED_EXAMPLES",
    "LivingDexCausalModelUpdateError",
    "LivingDexCausalModelUpdateResult",
    "fit_living_dex_causal_model_update_from_store",
]
