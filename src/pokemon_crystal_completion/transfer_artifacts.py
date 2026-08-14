"""Path-free catalogs, prediction commitments, and sealed Crystal scoring.

The transfer plan alone says what must happen.  This module makes the costly
ordering constraints executable before a private cartridge is available:

* each partition freezes exact unlabeled questions in a canonical catalog;
* every required prediction is durably committed while label/action counters
  are still zero; and
* the primary paired statistic is unavailable until all 27 sealed outcomes
  are present.

No function in this module opens a ROM, save state, capture, or filesystem
path.  Live tooling must hand it already-authenticated semantic records.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from pokemon_crystal_completion.transfer_protocol import (
    CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS,
    CRYSTAL_BASELINE_PREDICTOR_SHA256,
    CRYSTAL_RED_FROZEN_MODEL_SHA256,
    CRYSTAL_SEALED_PREDICTOR_IDS,
    CRYSTAL_ZERO_SHOT_PREDICTOR_IDS,
    CrystalTransferPlan,
    CrystalTransferSlot,
)
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
)
from pokemon_red_completion.provenance import canonical_sha256

CRYSTAL_TRANSFER_CONTEXT_SCHEMA = "pokemon.crystal.transfer-context.v1"
CRYSTAL_TRANSFER_CATALOG_SCHEMA = "pokemon.crystal.transfer-catalog.v1"
CRYSTAL_TRANSFER_PREDICTION_SCHEMA = "pokemon.crystal.transfer-prediction.v1"
CRYSTAL_TRANSFER_COMMITMENT_SCHEMA = "pokemon.crystal.prediction-commitment.v1"
CRYSTAL_TRANSFER_OUTCOME_SET_SCHEMA = "pokemon.crystal.transfer-outcome-set.v1"
CRYSTAL_TRANSFER_EVALUATION_SCHEMA = "pokemon.crystal.transfer-evaluation.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
_MULTIWAY_MINIMUM = {
    "zero_shot_probe": 6,
    "adaptation": 9,
    "sealed_test": 9,
}
_FAILURE_TAXONOMY = frozenset(
    {
        "source_identity_mismatch",
        "observation_unavailable",
        "catalog_stratum_mismatch",
        "availability_mask_error",
        "ranking_error",
        "binding_unavailable",
        "execution_failure",
        "verification_failure",
        "external_interruption",
    }
)


class CrystalTransferArtifactError(ValueError):
    """Raised when prospective transfer evidence is incomplete or ambiguous."""


@dataclass(frozen=True, slots=True)
class CrystalTransferContext:
    """One exact unlabeled Crystal question, represented only by safe digests."""

    slot_id: str
    partition: str
    goal_kind: GoalKind
    state_sha256: str
    envelope_sha256: str
    ordered_policy_input_sha256: str
    policy_context_sha256: str
    available_menu_sha256: str
    binding_manifest_sha256: str
    candidate_goal_kinds: tuple[GoalKind, ...]
    available_goal_kinds: tuple[GoalKind, ...]
    context_sha256: str

    def __post_init__(self) -> None:
        _safe_id(self.slot_id, subject="Crystal transfer slot identity")
        if self.partition not in {"zero_shot_probe", "adaptation", "sealed_test"}:
            raise CrystalTransferArtifactError("Crystal transfer partition is invalid")
        if not isinstance(self.goal_kind, GoalKind):
            raise CrystalTransferArtifactError("Crystal transfer focus kind is invalid")
        for value, subject in (
            (self.state_sha256, "state digest"),
            (self.envelope_sha256, "envelope digest"),
            (self.ordered_policy_input_sha256, "ordered policy-input digest"),
            (self.policy_context_sha256, "policy-context digest"),
            (self.available_menu_sha256, "available-menu digest"),
            (self.binding_manifest_sha256, "binding-manifest digest"),
            (self.context_sha256, "context digest"),
        ):
            _sha256(value, subject=subject)
        if (
            not isinstance(self.candidate_goal_kinds, tuple)
            or len(self.candidate_goal_kinds) != len(GoalKind)
            or set(self.candidate_goal_kinds) != set(GoalKind)
        ):
            raise CrystalTransferArtifactError(
                "Crystal context candidate order must contain every goal kind"
            )
        if (
            not isinstance(self.available_goal_kinds, tuple)
            or len(self.available_goal_kinds) < 2
            or any(kind not in self.candidate_goal_kinds for kind in self.available_goal_kinds)
            or len(set(self.available_goal_kinds)) != len(self.available_goal_kinds)
        ):
            raise CrystalTransferArtifactError(
                "Crystal context needs at least two unique available goal kinds"
            )
        expected_available_order = tuple(
            kind for kind in self.candidate_goal_kinds if kind in self.available_goal_kinds
        )
        if self.available_goal_kinds != expected_available_order:
            raise CrystalTransferArtifactError(
                "Crystal available goals must retain candidate order"
            )
        if self.goal_kind not in self.available_goal_kinds:
            raise CrystalTransferArtifactError("Crystal focus goal must be available")
        if self.available_menu_sha256 != _available_menu_sha256(
            self.available_goal_kinds
        ):
            raise CrystalTransferArtifactError("Crystal available-menu digest differs")
        if self.context_sha256 != _context_sha256(self._identity_dict()):
            raise CrystalTransferArtifactError("Crystal transfer context digest differs")

    @classmethod
    def build(
        cls,
        slot: CrystalTransferSlot,
        *,
        state_sha256: str,
        envelope_sha256: str,
        binding_manifest_sha256: str,
        question: GoalManagerQuestion,
    ) -> CrystalTransferContext:
        if not isinstance(slot, CrystalTransferSlot):
            raise TypeError("slot must be CrystalTransferSlot")
        if not isinstance(question, GoalManagerQuestion):
            raise TypeError("question must be GoalManagerQuestion")
        candidate_goal_kinds = tuple(item.kind for item in question.opportunities)
        available_goal_kinds = tuple(
            item.kind
            for item in question.opportunities
            if item.availability is GoalAvailability.AVAILABLE
        )
        identity: dict[str, object] = {
            "schema": CRYSTAL_TRANSFER_CONTEXT_SCHEMA,
            "slot_id": slot.slot_id,
            "partition": slot.partition,
            "goal_kind": slot.goal_kind.value,
            "state_sha256": state_sha256,
            "envelope_sha256": envelope_sha256,
            "ordered_policy_input_sha256": question.ordered_policy_input_sha256,
            "policy_context_sha256": question.policy_context_sha256,
            "available_menu_sha256": question.available_menu_sha256,
            "binding_manifest_sha256": binding_manifest_sha256,
            "candidate_goal_kinds": [kind.value for kind in candidate_goal_kinds],
            "available_goal_kinds": [kind.value for kind in available_goal_kinds],
        }
        return cls(
            slot_id=slot.slot_id,
            partition=slot.partition,
            goal_kind=slot.goal_kind,
            state_sha256=state_sha256,
            envelope_sha256=envelope_sha256,
            ordered_policy_input_sha256=question.ordered_policy_input_sha256,
            policy_context_sha256=question.policy_context_sha256,
            available_menu_sha256=question.available_menu_sha256,
            binding_manifest_sha256=binding_manifest_sha256,
            candidate_goal_kinds=candidate_goal_kinds,
            available_goal_kinds=available_goal_kinds,
            context_sha256=_context_sha256(identity),
        )

    @property
    def focus_candidate_index(self) -> int:
        return self.candidate_goal_kinds.index(self.goal_kind)

    @property
    def available_candidate_indices(self) -> tuple[int, ...]:
        return tuple(
            index
            for index, kind in enumerate(self.candidate_goal_kinds)
            if kind in self.available_goal_kinds
        )

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema": CRYSTAL_TRANSFER_CONTEXT_SCHEMA,
            "slot_id": self.slot_id,
            "partition": self.partition,
            "goal_kind": self.goal_kind.value,
            "state_sha256": self.state_sha256,
            "envelope_sha256": self.envelope_sha256,
            "ordered_policy_input_sha256": self.ordered_policy_input_sha256,
            "policy_context_sha256": self.policy_context_sha256,
            "available_menu_sha256": self.available_menu_sha256,
            "binding_manifest_sha256": self.binding_manifest_sha256,
            "candidate_goal_kinds": [kind.value for kind in self.candidate_goal_kinds],
            "available_goal_kinds": [kind.value for kind in self.available_goal_kinds],
        }

    def public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "context_sha256": self.context_sha256}


@dataclass(frozen=True, slots=True)
class CrystalTransferCatalog:
    """One complete path-free partition catalog."""

    catalog_sha256: str
    plan_sha256: str
    partition: str
    rom_sha256: str
    adapter_source_commit: str
    adapter_source_bundle_sha256: str
    entries: tuple[CrystalTransferContext, ...]

    def __post_init__(self) -> None:
        for value, subject in (
            (self.catalog_sha256, "catalog digest"),
            (self.plan_sha256, "plan digest"),
            (self.rom_sha256, "ROM digest"),
            (self.adapter_source_bundle_sha256, "adapter source-bundle digest"),
        ):
            _sha256(value, subject=subject)
        if (
            not isinstance(self.adapter_source_commit, str)
            or _GIT_COMMIT.fullmatch(self.adapter_source_commit) is None
        ):
            raise CrystalTransferArtifactError("adapter source commit is invalid")
        if not self.entries or any(
            not isinstance(entry, CrystalTransferContext) for entry in self.entries
        ):
            raise CrystalTransferArtifactError("Crystal catalog entries are invalid")
        if self.partition not in {"zero_shot_probe", "adaptation", "sealed_test"}:
            raise CrystalTransferArtifactError("Crystal catalog partition is invalid")

    def entry(self, slot_id: str) -> CrystalTransferContext:
        try:
            return next(entry for entry in self.entries if entry.slot_id == slot_id)
        except StopIteration as error:
            raise CrystalTransferArtifactError("Crystal catalog has no requested slot") from error

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.crystal.transfer-catalog-summary.v1",
            "catalog_sha256": self.catalog_sha256,
            "plan_sha256": self.plan_sha256,
            "partition": self.partition,
            "context_count": len(self.entries),
            "unique_policy_context_count": len(
                {entry.policy_context_sha256 for entry in self.entries}
            ),
            "multiway_context_count": sum(
                len(entry.available_goal_kinds) >= 3 for entry in self.entries
            ),
            "context_dependent_menu_count": _context_dependent_menu_count(self.entries),
            "distinct_focus_candidate_positions": len(
                {entry.focus_candidate_index for entry in self.entries}
            ),
            "private_path_fields": 0,
            "teacher_label_fields": 0,
            "prediction_fields": 0,
        }


def validate_crystal_transfer_catalog(
    plan: CrystalTransferPlan,
    catalog: CrystalTransferCatalog,
) -> None:
    """Reconstruct and authenticate one parsed catalog before consuming it."""

    if not isinstance(catalog, CrystalTransferCatalog):
        raise TypeError("catalog must be CrystalTransferCatalog")
    payload = build_crystal_transfer_catalog_payload(
        plan,
        partition=catalog.partition,
        rom_sha256=catalog.rom_sha256,
        adapter_source_commit=catalog.adapter_source_commit,
        adapter_source_bundle_sha256=catalog.adapter_source_bundle_sha256,
        entries=catalog.entries,
    )
    if hashlib.sha256(payload).hexdigest() != catalog.catalog_sha256:
        raise CrystalTransferArtifactError("Crystal catalog digest differs from its contents")


def build_crystal_transfer_catalog_payload(
    plan: CrystalTransferPlan,
    *,
    partition: str,
    rom_sha256: str,
    adapter_source_commit: str,
    adapter_source_bundle_sha256: str,
    entries: Iterable[CrystalTransferContext],
) -> bytes:
    """Freeze one complete unlabeled partition into canonical path-free bytes."""

    rows = tuple(entries)
    _validate_catalog_identity(
        plan,
        partition=partition,
        rom_sha256=rom_sha256,
        adapter_source_commit=adapter_source_commit,
        adapter_source_bundle_sha256=adapter_source_bundle_sha256,
    )
    _validate_catalog_entries(plan, partition=partition, entries=rows)
    return _canonical_line(
        {
            "schema": CRYSTAL_TRANSFER_CATALOG_SCHEMA,
            "plan_sha256": plan.plan_sha256,
            "partition": partition,
            "rom_sha256": rom_sha256,
            "adapter_source_commit": adapter_source_commit,
            "adapter_source_bundle_sha256": adapter_source_bundle_sha256,
            "entries": [entry.public_dict() for entry in rows],
        }
    )


def parse_crystal_transfer_catalog(
    payload: bytes,
    plan: CrystalTransferPlan,
) -> CrystalTransferCatalog:
    document = _canonical_document(payload, subject="Crystal transfer catalog")
    _exact_keys(
        document,
        {
            "schema",
            "plan_sha256",
            "partition",
            "rom_sha256",
            "adapter_source_commit",
            "adapter_source_bundle_sha256",
            "entries",
        },
        subject="Crystal transfer catalog",
    )
    if document.get("schema") != CRYSTAL_TRANSFER_CATALOG_SCHEMA:
        raise CrystalTransferArtifactError("Crystal transfer catalog schema differs")
    partition = _text(document["partition"], subject="catalog partition")
    entries_raw = document["entries"]
    if not isinstance(entries_raw, list):
        raise CrystalTransferArtifactError("Crystal catalog entries must be a list")
    entries = tuple(_parse_context(item) for item in entries_raw)
    rom_sha256 = _text(document["rom_sha256"], subject="catalog ROM digest")
    source_commit = _text(
        document["adapter_source_commit"], subject="catalog source commit"
    )
    source_bundle = _text(
        document["adapter_source_bundle_sha256"], subject="catalog source-bundle digest"
    )
    _validate_catalog_identity(
        plan,
        partition=partition,
        rom_sha256=rom_sha256,
        adapter_source_commit=source_commit,
        adapter_source_bundle_sha256=source_bundle,
    )
    if document.get("plan_sha256") != plan.plan_sha256:
        raise CrystalTransferArtifactError("Crystal catalog plan digest differs")
    _validate_catalog_entries(plan, partition=partition, entries=entries)
    return CrystalTransferCatalog(
        catalog_sha256=hashlib.sha256(payload).hexdigest(),
        plan_sha256=plan.plan_sha256,
        partition=partition,
        rom_sha256=rom_sha256,
        adapter_source_commit=source_commit,
        adapter_source_bundle_sha256=source_bundle,
        entries=entries,
    )


def validate_crystal_transfer_catalog_set(
    plan: CrystalTransferPlan,
    catalogs: Iterable[CrystalTransferCatalog],
) -> None:
    """Require exact partition coverage and zero semantic/capture overlap."""

    rows = tuple(catalogs)
    for catalog in rows:
        validate_crystal_transfer_catalog(plan, catalog)
    expected = tuple(partition.name for partition in plan.partitions)
    if tuple(catalog.partition for catalog in rows) != expected:
        raise CrystalTransferArtifactError("Crystal catalogs must use plan partition order")
    if any(catalog.plan_sha256 != plan.plan_sha256 for catalog in rows):
        raise CrystalTransferArtifactError("Crystal catalogs do not share the plan")
    if len({catalog.rom_sha256 for catalog in rows}) != 1:
        raise CrystalTransferArtifactError("Crystal catalogs do not share one ROM identity")
    if len({catalog.adapter_source_commit for catalog in rows}) != 1 or len(
        {catalog.adapter_source_bundle_sha256 for catalog in rows}
    ) != 1:
        raise CrystalTransferArtifactError("Crystal catalogs do not share one source identity")
    for attribute, subject in (
        ("state_sha256", "state"),
        ("envelope_sha256", "envelope"),
        ("policy_context_sha256", "policy context"),
        ("context_sha256", "context"),
    ):
        values = [
            getattr(entry, attribute) for catalog in rows for entry in catalog.entries
        ]
        if len(values) != len(set(values)):
            raise CrystalTransferArtifactError(
                f"Crystal catalog partitions overlap by {subject}"
            )


@dataclass(frozen=True, slots=True)
class CrystalTransferPrediction:
    """One label-free prediction bound to an exact catalog context."""

    slot_id: str
    context_sha256: str
    policy_context_sha256: str
    predictor_id: str
    predictor_sha256: str
    selected_candidate_index: int
    candidate_count: int
    confidence: float
    tied: bool
    prediction_sha256: str

    def __post_init__(self) -> None:
        _safe_id(self.slot_id, subject="prediction slot identity")
        _safe_id(self.predictor_id, subject="predictor identity")
        for value, subject in (
            (self.context_sha256, "prediction context digest"),
            (self.policy_context_sha256, "prediction policy-context digest"),
            (self.predictor_sha256, "predictor digest"),
            (self.prediction_sha256, "prediction digest"),
        ):
            _sha256(value, subject=subject)
        if type(self.candidate_count) is not int or self.candidate_count != len(GoalKind):
            raise CrystalTransferArtifactError("prediction candidate count is invalid")
        if (
            type(self.selected_candidate_index) is not int
            or not 0 <= self.selected_candidate_index < self.candidate_count
        ):
            raise CrystalTransferArtifactError("prediction candidate index is invalid")
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(float(self.confidence))
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise CrystalTransferArtifactError("prediction confidence is invalid")
        if not isinstance(self.tied, bool):
            raise CrystalTransferArtifactError("prediction tie flag is invalid")
        if self.prediction_sha256 != canonical_sha256(self._identity_dict()):
            raise CrystalTransferArtifactError("Crystal prediction digest differs")

    @classmethod
    def build(
        cls,
        context: CrystalTransferContext,
        *,
        predictor_id: str,
        predictor_sha256: str,
        selected_candidate_index: int,
        confidence: float,
        tied: bool,
    ) -> CrystalTransferPrediction:
        identity = {
            "schema": CRYSTAL_TRANSFER_PREDICTION_SCHEMA,
            "slot_id": context.slot_id,
            "context_sha256": context.context_sha256,
            "policy_context_sha256": context.policy_context_sha256,
            "predictor_id": predictor_id,
            "predictor_sha256": predictor_sha256,
            "selected_candidate_index": selected_candidate_index,
            "candidate_count": len(context.candidate_goal_kinds),
            "confidence": float(confidence),
            "tied": tied,
        }
        prediction = cls(
            slot_id=context.slot_id,
            context_sha256=context.context_sha256,
            policy_context_sha256=context.policy_context_sha256,
            predictor_id=predictor_id,
            predictor_sha256=predictor_sha256,
            selected_candidate_index=selected_candidate_index,
            candidate_count=len(context.candidate_goal_kinds),
            confidence=float(confidence),
            tied=tied,
            prediction_sha256=canonical_sha256(identity),
        )
        if selected_candidate_index not in context.available_candidate_indices:
            raise CrystalTransferArtifactError("prediction selects an unavailable candidate")
        return prediction

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema": CRYSTAL_TRANSFER_PREDICTION_SCHEMA,
            "slot_id": self.slot_id,
            "context_sha256": self.context_sha256,
            "policy_context_sha256": self.policy_context_sha256,
            "predictor_id": self.predictor_id,
            "predictor_sha256": self.predictor_sha256,
            "selected_candidate_index": self.selected_candidate_index,
            "candidate_count": self.candidate_count,
            "confidence": self.confidence,
            "tied": self.tied,
        }

    def public_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "prediction_sha256": self.prediction_sha256}


@dataclass(frozen=True, slots=True)
class CrystalPredictionCommitment:
    commitment_sha256: str
    plan_sha256: str
    catalog_sha256: str
    partition: str
    predictor_ids: tuple[str, ...]
    adapted_predictor_sha256: tuple[tuple[str, str], ...]
    predictions: tuple[CrystalTransferPrediction, ...]

    def __post_init__(self) -> None:
        _sha256(self.commitment_sha256, subject="prediction commitment digest")
        _sha256(self.plan_sha256, subject="prediction commitment plan digest")
        _sha256(self.catalog_sha256, subject="prediction commitment catalog digest")
        if self.predictor_ids != _predictor_ids_for_partition(self.partition):
            raise CrystalTransferArtifactError("prediction commitment predictor set differs")
        expected_adapted = (
            CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS
            if self.partition == "sealed_test"
            else ()
        )
        if tuple(key for key, _value in self.adapted_predictor_sha256) != expected_adapted:
            raise CrystalTransferArtifactError(
                "prediction commitment adapted predictor set differs"
            )
        for _predictor_id, digest in self.adapted_predictor_sha256:
            _sha256(digest, subject="adapted predictor digest")
        if not self.predictions:
            raise CrystalTransferArtifactError("prediction commitment is empty")

    def prediction(self, slot_id: str, predictor_id: str) -> CrystalTransferPrediction:
        try:
            return next(
                row
                for row in self.predictions
                if row.slot_id == slot_id and row.predictor_id == predictor_id
            )
        except StopIteration as error:
            raise CrystalTransferArtifactError("prediction commitment row is absent") from error

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.crystal.prediction-commitment-summary.v1",
            "commitment_sha256": self.commitment_sha256,
            "plan_sha256": self.plan_sha256,
            "catalog_sha256": self.catalog_sha256,
            "partition": self.partition,
            "predictor_ids": list(self.predictor_ids),
            "adapted_predictor_sha256": dict(self.adapted_predictor_sha256),
            "prediction_count": len(self.predictions),
            "teacher_labels_observed_at_commit": 0,
            "teacher_actions_executed_at_commit": 0,
            "private_path_fields": 0,
        }


def validate_crystal_prediction_commitment(
    plan: CrystalTransferPlan,
    catalog: CrystalTransferCatalog,
    commitment: CrystalPredictionCommitment,
) -> None:
    """Reconstruct a commitment so cloned dataclasses cannot bypass its digest."""

    if not isinstance(commitment, CrystalPredictionCommitment):
        raise TypeError("commitment must be CrystalPredictionCommitment")
    payload = build_crystal_prediction_commitment_payload(
        plan,
        catalog,
        commitment.predictions,
        teacher_labels_observed=0,
        teacher_actions_executed=0,
        adapted_predictor_sha256=dict(commitment.adapted_predictor_sha256),
    )
    if hashlib.sha256(payload).hexdigest() != commitment.commitment_sha256:
        raise CrystalTransferArtifactError(
            "Crystal prediction commitment digest differs from its contents"
        )


def build_crystal_prediction_commitment_payload(
    plan: CrystalTransferPlan,
    catalog: CrystalTransferCatalog,
    predictions: Iterable[CrystalTransferPrediction],
    *,
    teacher_labels_observed: int,
    teacher_actions_executed: int,
    adapted_predictor_sha256: Mapping[str, str] | None = None,
) -> bytes:
    """Commit complete predictions only while both teacher counters are zero."""

    if teacher_labels_observed != 0 or teacher_actions_executed != 0:
        raise CrystalTransferArtifactError(
            "Crystal predictions must commit before any teacher label or action"
        )
    rows = tuple(predictions)
    predictor_ids = _predictor_ids_for_partition(catalog.partition)
    adapted = _adapted_predictor_identity(
        catalog.partition,
        adapted_predictor_sha256,
    )
    _validate_prediction_rows(catalog, predictor_ids, rows, adapted)
    if catalog.plan_sha256 != plan.plan_sha256:
        raise CrystalTransferArtifactError("prediction catalog plan differs")
    return _canonical_line(
        {
            "schema": CRYSTAL_TRANSFER_COMMITMENT_SCHEMA,
            "plan_sha256": plan.plan_sha256,
            "catalog_sha256": catalog.catalog_sha256,
            "partition": catalog.partition,
            "predictor_ids": list(predictor_ids),
            "adapted_predictor_sha256": dict(adapted),
            "teacher_labels_observed_at_commit": 0,
            "teacher_actions_executed_at_commit": 0,
            "predictions": [row.public_dict() for row in rows],
        }
    )


def parse_crystal_prediction_commitment(
    payload: bytes,
    plan: CrystalTransferPlan,
    catalog: CrystalTransferCatalog,
    *,
    adapted_predictor_sha256: Mapping[str, str] | None = None,
) -> CrystalPredictionCommitment:
    document = _canonical_document(payload, subject="Crystal prediction commitment")
    _exact_keys(
        document,
        {
            "schema",
            "plan_sha256",
            "catalog_sha256",
            "partition",
            "predictor_ids",
            "adapted_predictor_sha256",
            "teacher_labels_observed_at_commit",
            "teacher_actions_executed_at_commit",
            "predictions",
        },
        subject="Crystal prediction commitment",
    )
    if document.get("schema") != CRYSTAL_TRANSFER_COMMITMENT_SCHEMA:
        raise CrystalTransferArtifactError("Crystal prediction commitment schema differs")
    if document.get("plan_sha256") != plan.plan_sha256:
        raise CrystalTransferArtifactError("Crystal prediction commitment plan differs")
    if document.get("catalog_sha256") != catalog.catalog_sha256:
        raise CrystalTransferArtifactError("Crystal prediction commitment catalog differs")
    if document.get("partition") != catalog.partition:
        raise CrystalTransferArtifactError("Crystal prediction commitment partition differs")
    if (
        document.get("teacher_labels_observed_at_commit") != 0
        or document.get("teacher_actions_executed_at_commit") != 0
    ):
        raise CrystalTransferArtifactError("Crystal commitment follows teacher access")
    expected_predictors = _predictor_ids_for_partition(catalog.partition)
    if document.get("predictor_ids") != list(expected_predictors):
        raise CrystalTransferArtifactError("Crystal commitment predictor set differs")
    expected_adapted = _adapted_predictor_identity(
        catalog.partition,
        adapted_predictor_sha256,
    )
    adapted_raw = document.get("adapted_predictor_sha256")
    if not isinstance(adapted_raw, dict) or adapted_raw != dict(expected_adapted):
        raise CrystalTransferArtifactError(
            "Crystal commitment adapted predictor identity differs"
        )
    predictions_raw = document.get("predictions")
    if not isinstance(predictions_raw, list):
        raise CrystalTransferArtifactError("Crystal commitment predictions must be a list")
    rows = tuple(_parse_prediction(item) for item in predictions_raw)
    _validate_prediction_rows(catalog, expected_predictors, rows, expected_adapted)
    return CrystalPredictionCommitment(
        commitment_sha256=hashlib.sha256(payload).hexdigest(),
        plan_sha256=plan.plan_sha256,
        catalog_sha256=catalog.catalog_sha256,
        partition=catalog.partition,
        predictor_ids=expected_predictors,
        adapted_predictor_sha256=expected_adapted,
        predictions=rows,
    )


class CrystalExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class CrystalPredictorExecution:
    predictor_id: str
    status: CrystalExecutionStatus
    independently_verified: bool
    failure_class: str | None = None

    def __post_init__(self) -> None:
        _safe_id(self.predictor_id, subject="execution predictor identity")
        if not isinstance(self.status, CrystalExecutionStatus):
            raise CrystalTransferArtifactError("Crystal execution status is invalid")
        if not isinstance(self.independently_verified, bool):
            raise CrystalTransferArtifactError("Crystal verification flag is invalid")
        if self.status is CrystalExecutionStatus.SUCCEEDED:
            if not self.independently_verified or self.failure_class is not None:
                raise CrystalTransferArtifactError(
                    "successful Crystal execution needs independent verification"
                )
        elif (
            self.independently_verified
            or self.failure_class not in _FAILURE_TAXONOMY
        ):
            raise CrystalTransferArtifactError(
                "unsuccessful Crystal execution needs one registered failure class"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "predictor_id": self.predictor_id,
            "status": self.status.value,
            "independently_verified": self.independently_verified,
            "failure_class": self.failure_class,
        }


@dataclass(frozen=True, slots=True)
class CrystalTransferCaseOutcome:
    """One opened sealed context after all predictions were committed."""

    slot_id: str
    context_sha256: str
    teacher_selected_candidate_index: int | None
    teacher_failure_class: str | None
    executions: tuple[CrystalPredictorExecution, ...]

    def __post_init__(self) -> None:
        _safe_id(self.slot_id, subject="outcome slot identity")
        _sha256(self.context_sha256, subject="outcome context digest")
        if self.teacher_selected_candidate_index is None:
            if self.teacher_failure_class not in _FAILURE_TAXONOMY:
                raise CrystalTransferArtifactError(
                    "missing Crystal teacher label needs one failure class"
                )
        else:
            if (
                type(self.teacher_selected_candidate_index) is not int
                or not 0 <= self.teacher_selected_candidate_index < len(GoalKind)
                or self.teacher_failure_class is not None
            ):
                raise CrystalTransferArtifactError("Crystal teacher label is invalid")
        if tuple(item.predictor_id for item in self.executions) != (
            CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS
        ):
            raise CrystalTransferArtifactError(
                "Crystal causal outcomes must cover every adapted model in fixed order"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "slot_id": self.slot_id,
            "context_sha256": self.context_sha256,
            "teacher_selected_candidate_index": self.teacher_selected_candidate_index,
            "teacher_failure_class": self.teacher_failure_class,
            "executions": [item.public_dict() for item in self.executions],
        }


@dataclass(frozen=True, slots=True)
class CrystalTransferOutcomeSet:
    """The complete, immutable result of opening the sealed partition once."""

    outcome_set_sha256: str
    plan_sha256: str
    catalog_sha256: str
    commitment_sha256: str
    outcomes: tuple[CrystalTransferCaseOutcome, ...]

    def __post_init__(self) -> None:
        for digest, subject in (
            (self.outcome_set_sha256, "outcome-set digest"),
            (self.plan_sha256, "outcome-set plan digest"),
            (self.catalog_sha256, "outcome-set catalog digest"),
            (self.commitment_sha256, "outcome-set commitment digest"),
        ):
            _sha256(digest, subject=subject)
        if len(self.outcomes) != 27 or any(
            not isinstance(item, CrystalTransferCaseOutcome) for item in self.outcomes
        ):
            raise CrystalTransferArtifactError(
                "Crystal outcome set must contain all 27 sealed outcomes"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.crystal.transfer-outcome-set-summary.v1",
            "outcome_set_sha256": self.outcome_set_sha256,
            "plan_sha256": self.plan_sha256,
            "catalog_sha256": self.catalog_sha256,
            "commitment_sha256": self.commitment_sha256,
            "outcome_count": len(self.outcomes),
            "missing_teacher_labels": sum(
                item.teacher_selected_candidate_index is None for item in self.outcomes
            ),
            "private_path_fields": 0,
        }


def validate_crystal_transfer_outcome_set(
    plan: CrystalTransferPlan,
    catalog: CrystalTransferCatalog,
    commitment: CrystalPredictionCommitment,
    outcome_set: CrystalTransferOutcomeSet,
) -> None:
    """Reconstruct a complete outcome set before any statistic is calculated."""

    if not isinstance(outcome_set, CrystalTransferOutcomeSet):
        raise TypeError("outcome_set must be CrystalTransferOutcomeSet")
    payload = build_crystal_transfer_outcome_set_payload(
        plan,
        catalog,
        commitment,
        outcome_set.outcomes,
    )
    if hashlib.sha256(payload).hexdigest() != outcome_set.outcome_set_sha256:
        raise CrystalTransferArtifactError(
            "Crystal outcome-set digest differs from its contents"
        )


def build_crystal_transfer_outcome_set_payload(
    plan: CrystalTransferPlan,
    catalog: CrystalTransferCatalog,
    commitment: CrystalPredictionCommitment,
    outcomes: Iterable[CrystalTransferCaseOutcome],
) -> bytes:
    """Freeze all sealed results together; partial result sets are not artifacts."""

    rows = tuple(outcomes)
    _validate_outcome_set(plan, catalog, commitment, rows)
    return _canonical_line(
        {
            "schema": CRYSTAL_TRANSFER_OUTCOME_SET_SCHEMA,
            "plan_sha256": plan.plan_sha256,
            "catalog_sha256": catalog.catalog_sha256,
            "commitment_sha256": commitment.commitment_sha256,
            "outcomes": [row.public_dict() for row in rows],
        }
    )


def parse_crystal_transfer_outcome_set(
    payload: bytes,
    plan: CrystalTransferPlan,
    catalog: CrystalTransferCatalog,
    commitment: CrystalPredictionCommitment,
) -> CrystalTransferOutcomeSet:
    document = _canonical_document(payload, subject="Crystal transfer outcome set")
    _exact_keys(
        document,
        {
            "schema",
            "plan_sha256",
            "catalog_sha256",
            "commitment_sha256",
            "outcomes",
        },
        subject="Crystal transfer outcome set",
    )
    if document.get("schema") != CRYSTAL_TRANSFER_OUTCOME_SET_SCHEMA:
        raise CrystalTransferArtifactError("Crystal transfer outcome-set schema differs")
    if (
        document.get("plan_sha256") != plan.plan_sha256
        or document.get("catalog_sha256") != catalog.catalog_sha256
        or document.get("commitment_sha256") != commitment.commitment_sha256
    ):
        raise CrystalTransferArtifactError("Crystal transfer outcome-set identity differs")
    raw = document.get("outcomes")
    if not isinstance(raw, list):
        raise CrystalTransferArtifactError("Crystal transfer outcomes must be a list")
    rows = tuple(_parse_outcome(item) for item in raw)
    _validate_outcome_set(plan, catalog, commitment, rows)
    return CrystalTransferOutcomeSet(
        outcome_set_sha256=hashlib.sha256(payload).hexdigest(),
        plan_sha256=plan.plan_sha256,
        catalog_sha256=catalog.catalog_sha256,
        commitment_sha256=commitment.commitment_sha256,
        outcomes=rows,
    )


@dataclass(frozen=True, slots=True)
class CrystalPredictorMetrics:
    predictor_id: str
    correct: int
    examples: int
    causal_verified_successes: int | None
    teacher_aligned_verified_successes: int | None

    @property
    def accuracy(self) -> float:
        return self.correct / self.examples

    def public_dict(self) -> dict[str, object]:
        return {
            "correct": self.correct,
            "examples": self.examples,
            "accuracy": self.accuracy,
            "causal_verified_successes": self.causal_verified_successes,
            "teacher_aligned_verified_successes": (
                self.teacher_aligned_verified_successes
            ),
        }


@dataclass(frozen=True, slots=True)
class CrystalPrimaryTransferResult:
    budget: int
    red_initialized_wins: int
    red_initialized_losses: int
    paired_two_sided_exact_p: float
    passed: bool

    def public_dict(self) -> dict[str, object]:
        return {
            "budget": self.budget,
            "red_initialized_wins": self.red_initialized_wins,
            "red_initialized_losses": self.red_initialized_losses,
            "paired_two_sided_exact_p": self.paired_two_sided_exact_p,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class CrystalTransferEvaluation:
    plan_sha256: str
    catalog_sha256: str
    commitment_sha256: str
    outcome_set_sha256: str
    examples: int
    missing_teacher_labels: int
    catalog_stratum_mismatches: int
    predictor_metrics: tuple[tuple[str, CrystalPredictorMetrics], ...]
    primary: CrystalPrimaryTransferResult

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": CRYSTAL_TRANSFER_EVALUATION_SCHEMA,
            "plan_sha256": self.plan_sha256,
            "catalog_sha256": self.catalog_sha256,
            "commitment_sha256": self.commitment_sha256,
            "outcome_set_sha256": self.outcome_set_sha256,
            "examples": self.examples,
            "missing_teacher_labels": self.missing_teacher_labels,
            "catalog_stratum_mismatches": self.catalog_stratum_mismatches,
            "predictors": {
                predictor_id: metrics.public_dict()
                for predictor_id, metrics in self.predictor_metrics
            },
            "primary_endpoint": self.primary.public_dict(),
            "intermediate_statistics_emitted": False,
            "private_path_fields": 0,
        }

    def canonical_bytes(self) -> bytes:
        """Return the complete deterministic public evaluation artifact."""

        return _canonical_line(self.public_dict())


def evaluate_crystal_sealed_transfer(
    plan: CrystalTransferPlan,
    catalog: CrystalTransferCatalog,
    commitment: CrystalPredictionCommitment,
    outcome_set: CrystalTransferOutcomeSet,
) -> CrystalTransferEvaluation:
    """Score only a complete sealed partition, preventing optional stopping."""

    if catalog.partition != "sealed_test" or commitment.partition != "sealed_test":
        raise CrystalTransferArtifactError("Crystal primary evaluation requires sealed test data")
    if (
        catalog.plan_sha256 != plan.plan_sha256
        or commitment.plan_sha256 != plan.plan_sha256
        or commitment.catalog_sha256 != catalog.catalog_sha256
        or outcome_set.plan_sha256 != plan.plan_sha256
        or outcome_set.catalog_sha256 != catalog.catalog_sha256
        or outcome_set.commitment_sha256 != commitment.commitment_sha256
    ):
        raise CrystalTransferArtifactError("Crystal evaluation identity differs")
    validate_crystal_transfer_outcome_set(plan, catalog, commitment, outcome_set)
    _validate_catalog_entries(plan, partition="sealed_test", entries=catalog.entries)
    if commitment.predictor_ids != CRYSTAL_SEALED_PREDICTOR_IDS:
        raise CrystalTransferArtifactError("Crystal sealed predictor set differs")
    _validate_prediction_rows(
        catalog,
        CRYSTAL_SEALED_PREDICTOR_IDS,
        commitment.predictions,
        commitment.adapted_predictor_sha256,
    )
    rows = outcome_set.outcomes
    _validate_outcome_set(plan, catalog, commitment, rows)
    expected_slots = tuple(entry.slot_id for entry in catalog.entries)
    if tuple(row.slot_id for row in rows) != expected_slots:
        raise CrystalTransferArtifactError(
            "Crystal evaluation requires every sealed outcome in catalog order"
        )
    if len(rows) != 27:
        raise CrystalTransferArtifactError("Crystal evaluation cannot emit intermediate results")

    correct_by_predictor = {predictor_id: 0 for predictor_id in commitment.predictor_ids}
    causal_successes = {predictor_id: 0 for predictor_id in CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS}
    aligned_successes = {predictor_id: 0 for predictor_id in CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS}
    primary_wins = 0
    primary_losses = 0
    missing_labels = 0
    stratum_mismatches = 0
    red_id = "red_initialized_budget_9"
    scratch_id = "scratch_budget_9"

    for context, outcome in zip(catalog.entries, rows, strict=True):
        if outcome.context_sha256 != context.context_sha256:
            raise CrystalTransferArtifactError("Crystal outcome context digest differs")
        label = outcome.teacher_selected_candidate_index
        if label is None:
            missing_labels += 1
        else:
            if label not in context.available_candidate_indices:
                raise CrystalTransferArtifactError("Crystal teacher selected a masked candidate")
            if context.candidate_goal_kinds[label] is not context.goal_kind:
                stratum_mismatches += 1
        hits: dict[str, bool] = {}
        for predictor_id in commitment.predictor_ids:
            prediction = commitment.prediction(context.slot_id, predictor_id)
            hit = label is not None and prediction.selected_candidate_index == label
            hits[predictor_id] = hit
            correct_by_predictor[predictor_id] += int(hit)
        primary_wins += int(hits[red_id] and not hits[scratch_id])
        primary_losses += int(hits[scratch_id] and not hits[red_id])
        for execution in outcome.executions:
            succeeded = (
                execution.status is CrystalExecutionStatus.SUCCEEDED
                and execution.independently_verified
            )
            causal_successes[execution.predictor_id] += int(succeeded)
            aligned_successes[execution.predictor_id] += int(
                succeeded and hits[execution.predictor_id]
            )

    p_value = _paired_two_sided_exact_p(primary_wins, primary_losses)
    primary = CrystalPrimaryTransferResult(
        budget=plan.primary_budget,
        red_initialized_wins=primary_wins,
        red_initialized_losses=primary_losses,
        paired_two_sided_exact_p=p_value,
        passed=(
            primary_wins >= plan.minimum_primary_wins
            and primary_losses <= plan.maximum_primary_losses
            and p_value < 0.05
        ),
    )
    metrics = tuple(
        (
            predictor_id,
            CrystalPredictorMetrics(
                predictor_id=predictor_id,
                correct=correct_by_predictor[predictor_id],
                examples=len(rows),
                causal_verified_successes=causal_successes.get(predictor_id),
                teacher_aligned_verified_successes=aligned_successes.get(predictor_id),
            ),
        )
        for predictor_id in commitment.predictor_ids
    )
    return CrystalTransferEvaluation(
        plan_sha256=plan.plan_sha256,
        catalog_sha256=catalog.catalog_sha256,
        commitment_sha256=commitment.commitment_sha256,
        outcome_set_sha256=outcome_set.outcome_set_sha256,
        examples=len(rows),
        missing_teacher_labels=missing_labels,
        catalog_stratum_mismatches=stratum_mismatches,
        predictor_metrics=metrics,
        primary=primary,
    )


def _validate_catalog_identity(
    plan: CrystalTransferPlan,
    *,
    partition: str,
    rom_sha256: str,
    adapter_source_commit: str,
    adapter_source_bundle_sha256: str,
) -> None:
    if not isinstance(plan, CrystalTransferPlan):
        raise TypeError("plan must be CrystalTransferPlan")
    if partition not in {row.name for row in plan.partitions}:
        raise CrystalTransferArtifactError("Crystal catalog partition is not preregistered")
    _sha256(rom_sha256, subject="catalog ROM digest")
    _sha256(adapter_source_bundle_sha256, subject="catalog source-bundle digest")
    if not isinstance(adapter_source_commit, str) or _GIT_COMMIT.fullmatch(
        adapter_source_commit
    ) is None:
        raise CrystalTransferArtifactError("catalog source commit is invalid")


def _validate_catalog_entries(
    plan: CrystalTransferPlan,
    *,
    partition: str,
    entries: tuple[CrystalTransferContext, ...],
) -> None:
    expected_slots = tuple(slot for slot in plan.slots if slot.partition == partition)
    if tuple(entry.slot_id for entry in entries) != tuple(
        slot.slot_id for slot in expected_slots
    ):
        raise CrystalTransferArtifactError(
            "Crystal catalog must contain every partition slot in frozen order"
        )
    for entry, slot in zip(entries, expected_slots, strict=True):
        if (
            entry.partition != slot.partition
            or entry.goal_kind is not slot.goal_kind
            or entry.candidate_goal_kinds != slot.candidate_goal_kinds
        ):
            raise CrystalTransferArtifactError("Crystal catalog slot semantics differ")
    for attribute, subject in (
        ("state_sha256", "state"),
        ("envelope_sha256", "envelope"),
        ("ordered_policy_input_sha256", "ordered question"),
        ("policy_context_sha256", "policy context"),
        ("binding_manifest_sha256", "binding manifest"),
        ("context_sha256", "context"),
    ):
        values = tuple(getattr(entry, attribute) for entry in entries)
        if len(values) != len(set(values)):
            raise CrystalTransferArtifactError(f"Crystal catalog repeats a {subject}")
    if sum(len(entry.available_goal_kinds) >= 3 for entry in entries) < _MULTIWAY_MINIMUM[
        partition
    ]:
        raise CrystalTransferArtifactError("Crystal catalog has too few multiway contexts")
    if _context_dependent_menu_count(entries) < 3:
        raise CrystalTransferArtifactError(
            "Crystal catalog lacks three context-dependent menu reversals"
        )
    if len({entry.focus_candidate_index for entry in entries}) < 8:
        raise CrystalTransferArtifactError("Crystal catalog focus positions lack diversity")


def _validate_prediction_rows(
    catalog: CrystalTransferCatalog,
    predictor_ids: tuple[str, ...],
    rows: tuple[CrystalTransferPrediction, ...],
    adapted_predictor_sha256: tuple[tuple[str, str], ...] = (),
) -> None:
    expected = tuple(
        (entry.slot_id, predictor_id)
        for entry in catalog.entries
        for predictor_id in predictor_ids
    )
    if tuple((row.slot_id, row.predictor_id) for row in rows) != expected:
        raise CrystalTransferArtifactError(
            "Crystal commitment needs exact slot/predictor coverage in frozen order"
        )
    predictor_digests: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        context = catalog.entry(row.slot_id)
        if (
            row.context_sha256 != context.context_sha256
            or row.policy_context_sha256 != context.policy_context_sha256
            or row.candidate_count != len(context.candidate_goal_kinds)
            or row.selected_candidate_index not in context.available_candidate_indices
        ):
            raise CrystalTransferArtifactError("Crystal prediction differs from its context")
        predictor_digests[row.predictor_id].add(row.predictor_sha256)
    if any(len(predictor_digests[predictor_id]) != 1 for predictor_id in predictor_ids):
        raise CrystalTransferArtifactError("Crystal predictor identity changes across contexts")
    fixed = {
        "red_frozen": CRYSTAL_RED_FROZEN_MODEL_SHA256,
        **dict(CRYSTAL_BASELINE_PREDICTOR_SHA256),
    }
    for predictor_id, expected_sha256 in fixed.items():
        if predictor_id in predictor_ids and predictor_digests[predictor_id] != {
            expected_sha256
        }:
            raise CrystalTransferArtifactError("Crystal fixed predictor identity differs")
    for predictor_id, expected_sha256 in adapted_predictor_sha256:
        if predictor_digests[predictor_id] != {expected_sha256}:
            raise CrystalTransferArtifactError("Crystal adapted predictor identity differs")


def _adapted_predictor_identity(
    partition: str,
    values: Mapping[str, str] | None,
) -> tuple[tuple[str, str], ...]:
    if partition == "zero_shot_probe":
        if values:
            raise CrystalTransferArtifactError(
                "zero-shot commitment cannot contain adapted predictors"
            )
        return ()
    if partition != "sealed_test":
        raise CrystalTransferArtifactError("Crystal prediction partition is invalid")
    if (
        not isinstance(values, Mapping)
        or len(values) != len(CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS)
        or set(values) != set(CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS)
    ):
        raise CrystalTransferArtifactError(
            "sealed commitment needs every fitted predictor identity in fixed order"
        )
    result = tuple(
        (predictor_id, values[predictor_id])
        for predictor_id in CRYSTAL_ADAPTED_MODEL_PREDICTOR_IDS
    )
    for _predictor_id, digest in result:
        _sha256(digest, subject="adapted predictor digest")
    return result


def _validate_outcome_set(
    plan: CrystalTransferPlan,
    catalog: CrystalTransferCatalog,
    commitment: CrystalPredictionCommitment,
    rows: tuple[CrystalTransferCaseOutcome, ...],
) -> None:
    validate_crystal_transfer_catalog(plan, catalog)
    validate_crystal_prediction_commitment(plan, catalog, commitment)
    if catalog.partition != "sealed_test" or commitment.partition != "sealed_test":
        raise CrystalTransferArtifactError("Crystal outcomes require the sealed partition")
    if (
        catalog.plan_sha256 != plan.plan_sha256
        or commitment.plan_sha256 != plan.plan_sha256
        or commitment.catalog_sha256 != catalog.catalog_sha256
    ):
        raise CrystalTransferArtifactError("Crystal outcome-set identity differs")
    if len(rows) != 27:
        raise CrystalTransferArtifactError(
            "Crystal outcome set must contain every sealed outcome"
        )
    expected_slots = tuple(entry.slot_id for entry in catalog.entries)
    if tuple(row.slot_id for row in rows) != expected_slots:
        raise CrystalTransferArtifactError(
            "Crystal outcome set must use frozen catalog order"
        )
    for context, row in zip(catalog.entries, rows, strict=True):
        if row.context_sha256 != context.context_sha256:
            raise CrystalTransferArtifactError("Crystal outcome context digest differs")
        label = row.teacher_selected_candidate_index
        if label is not None and label not in context.available_candidate_indices:
            raise CrystalTransferArtifactError("Crystal teacher selected a masked candidate")


def _parse_outcome(value: object) -> CrystalTransferCaseOutcome:
    if not isinstance(value, dict):
        raise CrystalTransferArtifactError("Crystal outcome record must be an object")
    _exact_keys(
        value,
        {
            "slot_id",
            "context_sha256",
            "teacher_selected_candidate_index",
            "teacher_failure_class",
            "executions",
        },
        subject="Crystal outcome record",
    )
    index = value["teacher_selected_candidate_index"]
    if index is not None and type(index) is not int:  # noqa: E721
        raise CrystalTransferArtifactError("Crystal teacher label is invalid")
    failure = value["teacher_failure_class"]
    if failure is not None and not isinstance(failure, str):
        raise CrystalTransferArtifactError("Crystal teacher failure class is invalid")
    executions = value["executions"]
    if not isinstance(executions, list):
        raise CrystalTransferArtifactError("Crystal executions must be a list")
    return CrystalTransferCaseOutcome(
        slot_id=_text(value["slot_id"], subject="outcome slot identity"),
        context_sha256=_text(value["context_sha256"], subject="outcome context digest"),
        teacher_selected_candidate_index=index,
        teacher_failure_class=failure,
        executions=tuple(_parse_execution(item) for item in executions),
    )


def _parse_execution(value: object) -> CrystalPredictorExecution:
    if not isinstance(value, dict):
        raise CrystalTransferArtifactError("Crystal execution record must be an object")
    _exact_keys(
        value,
        {"predictor_id", "status", "independently_verified", "failure_class"},
        subject="Crystal execution record",
    )
    raw_status = value["status"]
    verified = value["independently_verified"]
    failure = value["failure_class"]
    if not isinstance(raw_status, str) or not isinstance(verified, bool):
        raise CrystalTransferArtifactError("Crystal execution fields are invalid")
    if failure is not None and not isinstance(failure, str):
        raise CrystalTransferArtifactError("Crystal execution failure class is invalid")
    try:
        status = CrystalExecutionStatus(raw_status)
    except ValueError as error:
        raise CrystalTransferArtifactError("Crystal execution status is invalid") from error
    return CrystalPredictorExecution(
        predictor_id=_text(value["predictor_id"], subject="execution predictor identity"),
        status=status,
        independently_verified=verified,
        failure_class=failure,
    )


def _predictor_ids_for_partition(partition: str) -> tuple[str, ...]:
    if partition == "zero_shot_probe":
        return CRYSTAL_ZERO_SHOT_PREDICTOR_IDS
    if partition == "sealed_test":
        return CRYSTAL_SEALED_PREDICTOR_IDS
    raise CrystalTransferArtifactError(
        "adaptation labels are training rows, not a prediction commitment partition"
    )


def _parse_context(value: object) -> CrystalTransferContext:
    if not isinstance(value, dict):
        raise CrystalTransferArtifactError("Crystal context record must be an object")
    _exact_keys(
        value,
        {
            "schema",
            "slot_id",
            "partition",
            "goal_kind",
            "state_sha256",
            "envelope_sha256",
            "ordered_policy_input_sha256",
            "policy_context_sha256",
            "available_menu_sha256",
            "binding_manifest_sha256",
            "candidate_goal_kinds",
            "available_goal_kinds",
            "context_sha256",
        },
        subject="Crystal context record",
    )
    if value.get("schema") != CRYSTAL_TRANSFER_CONTEXT_SCHEMA:
        raise CrystalTransferArtifactError("Crystal context schema differs")
    return CrystalTransferContext(
        slot_id=_text(value["slot_id"], subject="context slot identity"),
        partition=_text(value["partition"], subject="context partition"),
        goal_kind=_goal_kind(value["goal_kind"]),
        state_sha256=_text(value["state_sha256"], subject="state digest"),
        envelope_sha256=_text(value["envelope_sha256"], subject="envelope digest"),
        ordered_policy_input_sha256=_text(
            value["ordered_policy_input_sha256"], subject="ordered policy-input digest"
        ),
        policy_context_sha256=_text(
            value["policy_context_sha256"], subject="policy-context digest"
        ),
        available_menu_sha256=_text(
            value["available_menu_sha256"], subject="available-menu digest"
        ),
        binding_manifest_sha256=_text(
            value["binding_manifest_sha256"], subject="binding-manifest digest"
        ),
        candidate_goal_kinds=_goal_kind_tuple(value["candidate_goal_kinds"]),
        available_goal_kinds=_goal_kind_tuple(value["available_goal_kinds"]),
        context_sha256=_text(value["context_sha256"], subject="context digest"),
    )


def _parse_prediction(value: object) -> CrystalTransferPrediction:
    if not isinstance(value, dict):
        raise CrystalTransferArtifactError("Crystal prediction record must be an object")
    _exact_keys(
        value,
        {
            "schema",
            "slot_id",
            "context_sha256",
            "policy_context_sha256",
            "predictor_id",
            "predictor_sha256",
            "selected_candidate_index",
            "candidate_count",
            "confidence",
            "tied",
            "prediction_sha256",
        },
        subject="Crystal prediction record",
    )
    if value.get("schema") != CRYSTAL_TRANSFER_PREDICTION_SCHEMA:
        raise CrystalTransferArtifactError("Crystal prediction schema differs")
    index = value["selected_candidate_index"]
    count = value["candidate_count"]
    confidence = value["confidence"]
    tied = value["tied"]
    if type(index) is not int or type(count) is not int:  # noqa: E721
        raise CrystalTransferArtifactError("Crystal prediction integers are invalid")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise CrystalTransferArtifactError("Crystal prediction confidence is invalid")
    if not isinstance(tied, bool):
        raise CrystalTransferArtifactError("Crystal prediction tie flag is invalid")
    return CrystalTransferPrediction(
        slot_id=_text(value["slot_id"], subject="prediction slot identity"),
        context_sha256=_text(value["context_sha256"], subject="prediction context digest"),
        policy_context_sha256=_text(
            value["policy_context_sha256"], subject="prediction policy-context digest"
        ),
        predictor_id=_text(value["predictor_id"], subject="predictor identity"),
        predictor_sha256=_text(value["predictor_sha256"], subject="predictor digest"),
        selected_candidate_index=index,
        candidate_count=count,
        confidence=float(confidence),
        tied=tied,
        prediction_sha256=_text(
            value["prediction_sha256"], subject="prediction digest"
        ),
    )


def _context_dependent_menu_count(
    entries: tuple[CrystalTransferContext, ...],
) -> int:
    focuses: dict[str, set[GoalKind]] = defaultdict(set)
    for entry in entries:
        focuses[entry.available_menu_sha256].add(entry.goal_kind)
    return sum(len(kinds) >= 2 for kinds in focuses.values())


def _available_menu_sha256(kinds: tuple[GoalKind, ...]) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.core.available-goal-menu.v1",
            "available_goal_kinds": sorted(kind.value for kind in kinds),
        }
    )


def _context_sha256(identity: dict[str, object]) -> str:
    return canonical_sha256(identity)


def _paired_two_sided_exact_p(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = min(wins, losses)
    probability = 2.0 * sum(
        math.comb(discordant, index) for index in range(tail + 1)
    ) / (2**discordant)
    return min(1.0, probability)


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


def _canonical_document(payload: bytes, *, subject: str) -> dict[str, object]:
    if not isinstance(payload, bytes) or not payload or len(payload) > _MAX_ARTIFACT_BYTES:
        raise CrystalTransferArtifactError(f"{subject} bytes are invalid")
    try:
        value = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except CrystalTransferArtifactError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise CrystalTransferArtifactError(f"{subject} is not valid JSON") from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise CrystalTransferArtifactError(f"{subject} is not canonical ASCII JSON")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CrystalTransferArtifactError("Crystal transfer artifact has duplicate keys")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    del value
    raise CrystalTransferArtifactError("Crystal transfer artifact contains non-finite numbers")


def _exact_keys(value: dict[str, object], expected: set[str], *, subject: str) -> None:
    if set(value) != expected:
        raise CrystalTransferArtifactError(f"{subject} fields differ")


def _sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise CrystalTransferArtifactError(f"{subject} is invalid")
    return value


def _safe_id(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise CrystalTransferArtifactError(f"{subject} is invalid")
    return value


def _text(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise CrystalTransferArtifactError(f"{subject} is invalid")
    return value


def _goal_kind(value: object) -> GoalKind:
    if not isinstance(value, str):
        raise CrystalTransferArtifactError("Crystal goal kind is invalid")
    try:
        return GoalKind(value)
    except (TypeError, ValueError) as error:
        raise CrystalTransferArtifactError("Crystal goal kind is invalid") from error


def _goal_kind_tuple(value: object) -> tuple[GoalKind, ...]:
    if not isinstance(value, list):
        raise CrystalTransferArtifactError("Crystal goal-kind collection must be a list")
    return tuple(_goal_kind(item) for item in value)


__all__ = [
    "CRYSTAL_TRANSFER_CATALOG_SCHEMA",
    "CRYSTAL_TRANSFER_COMMITMENT_SCHEMA",
    "CRYSTAL_TRANSFER_CONTEXT_SCHEMA",
    "CRYSTAL_TRANSFER_EVALUATION_SCHEMA",
    "CRYSTAL_TRANSFER_OUTCOME_SET_SCHEMA",
    "CRYSTAL_TRANSFER_PREDICTION_SCHEMA",
    "CrystalExecutionStatus",
    "CrystalPredictionCommitment",
    "CrystalPredictorExecution",
    "CrystalPredictorMetrics",
    "CrystalPrimaryTransferResult",
    "CrystalTransferArtifactError",
    "CrystalTransferCaseOutcome",
    "CrystalTransferCatalog",
    "CrystalTransferContext",
    "CrystalTransferEvaluation",
    "CrystalTransferOutcomeSet",
    "CrystalTransferPrediction",
    "build_crystal_prediction_commitment_payload",
    "build_crystal_transfer_catalog_payload",
    "build_crystal_transfer_outcome_set_payload",
    "evaluate_crystal_sealed_transfer",
    "parse_crystal_prediction_commitment",
    "parse_crystal_transfer_catalog",
    "parse_crystal_transfer_outcome_set",
    "validate_crystal_transfer_catalog",
    "validate_crystal_transfer_catalog_set",
    "validate_crystal_prediction_commitment",
    "validate_crystal_transfer_outcome_set",
]
