"""Integrity-checked whole-lineage datasets for learned training control."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.training_control import (
    TRAINING_CONTROL_FEATURE_NAMES,
    TRAINING_CONTROL_FEATURE_SCHEMA_ID,
    TrainingControlAction,
    TrainingControlObservation,
    TrainingControlPhase,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,159}\Z")
_PARTITIONS = frozenset({"train", "validation", "test", "unassigned"})
_SEGMENTS = ("evolution", "balance")


class TrainingControlDatasetError(RuntimeError):
    """Raised when a private training-control lineage is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class TrainingControlExample:
    lineage_id: str
    segment: str
    decision_index: int
    action: TrainingControlAction
    observation: TrainingControlObservation
    reason: str


@dataclass(frozen=True, slots=True)
class TrainingControlDataset:
    lineage_id: str
    partition: str
    artifact_sha256: str
    state_sha256: str
    source_commit: str
    source_dirty: bool
    status: str
    error: str | None
    examples: tuple[TrainingControlExample, ...]

    @property
    def lineage_qualified(self) -> bool:
        return self.status == "ok" and not self.source_dirty

    @property
    def class_refs(self) -> frozenset[str]:
        return frozenset(example.action.value for example in self.examples)

    def public_summary(self) -> dict[str, object]:
        counts = Counter(example.action.value for example in self.examples)
        phases = Counter(example.observation.phase.value for example in self.examples)
        unique = {
            (example.action.value, example.observation.features) for example in self.examples
        }
        return {
            "schema": "pokemon-training-control-dataset-summary-v1",
            "lineage_id": self.lineage_id,
            "partition": self.partition,
            "artifact_sha256": self.artifact_sha256,
            "state_sha256": self.state_sha256,
            "source_commit": self.source_commit,
            "source_dirty": self.source_dirty,
            "status": self.status,
            "lineage_qualified": self.lineage_qualified,
            "examples": len(self.examples),
            "unique_action_feature_pairs": len(unique),
            "duplicate_action_feature_pairs": len(self.examples) - len(unique),
            "action_counts": dict(sorted(counts.items())),
            "phase_counts": dict(sorted(phases.items())),
            "promotion_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class TrainingControlPartitionAudit:
    lineage_count: int
    partition_counts: tuple[tuple[str, int], ...]
    state_overlap_count: int
    validation_classes_missing_from_training: tuple[str, ...]
    promotion_eligible: bool
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-training-control-partition-audit-v1",
            "lineage_count": self.lineage_count,
            "partition_counts": dict(self.partition_counts),
            "state_overlap_count": self.state_overlap_count,
            "validation_classes_missing_from_training": list(
                self.validation_classes_missing_from_training
            ),
            "promotion_eligible": self.promotion_eligible,
            "reasons": list(self.reasons),
        }


def load_training_control_replay(
    path: str | Path,
    *,
    expected_sha256: str,
) -> TrainingControlDataset:
    """Authenticate and decode one complete or failed private replay."""

    _digest(expected_sha256, subject="expected artifact digest")
    source = Path(path)
    try:
        metadata = source.lstat()
        payload = source.read_bytes()
    except OSError as error:
        raise TrainingControlDatasetError("training-control replay cannot be read") from error
    if source.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise TrainingControlDatasetError("training-control replay must be a regular file")
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise TrainingControlDatasetError("training-control replay failed authentication")
    try:
        root = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise TrainingControlDatasetError("training-control replay is invalid JSON") from error
    value = _mapping(root, subject="replay")
    feature_names = value.get("feature_names")
    if (
        value.get("schema") != "pokemon-training-control-replay-v2"
        or value.get("feature_schema_id") != TRAINING_CONTROL_FEATURE_SCHEMA_ID
        or not isinstance(feature_names, list)
        or tuple(feature_names) != TRAINING_CONTROL_FEATURE_NAMES
    ):
        raise TrainingControlDatasetError("training-control replay schema is incompatible")

    status = value.get("status")
    error_value = value.get("error")
    if status not in {"ok", "failed"}:
        raise TrainingControlDatasetError("training-control replay status is invalid")
    if status == "ok" and error_value is not None:
        raise TrainingControlDatasetError("successful training-control replay carries an error")
    if status == "failed" and (not isinstance(error_value, str) or not error_value.strip()):
        raise TrainingControlDatasetError("failed training-control replay lacks an error")

    provenance = _mapping(value.get("provenance"), subject="provenance")
    lineage_id = _safe_id(provenance.get("lineage_id"), subject="lineage identity")
    partition = provenance.get("partition")
    source_commit = provenance.get("source_commit")
    source_dirty = provenance.get("source_dirty")
    state_sha256 = provenance.get("state_sha256")
    if partition not in _PARTITIONS:
        raise TrainingControlDatasetError("training-control partition is invalid")
    if not isinstance(source_commit, str) or _GIT_COMMIT.fullmatch(source_commit) is None:
        raise TrainingControlDatasetError("training-control source commit is invalid")
    if type(source_dirty) is not bool:  # noqa: E721
        raise TrainingControlDatasetError("training-control dirty-source flag is invalid")
    if not isinstance(state_sha256, str):
        raise TrainingControlDatasetError("training-control state digest is invalid")
    _digest(state_sha256, subject="state digest")

    segments = _mapping(value.get("segments"), subject="segments")
    if set(segments) != set(_SEGMENTS):
        raise TrainingControlDatasetError("training-control segment roster is invalid")
    examples: list[TrainingControlExample] = []
    for segment in _SEGMENTS:
        rows = segments[segment]
        if not isinstance(rows, list):
            raise TrainingControlDatasetError("training-control segment is not a list")
        for expected_index, row in enumerate(rows):
            examples.append(_example(row, lineage_id, segment, expected_index))
    if not examples:
        raise TrainingControlDatasetError("training-control replay has no decisions")
    stops = [example for example in examples if example.action is TrainingControlAction.STOP]
    if status == "ok" and (
        len(stops) != 1
        or examples[-1] is not stops[0]
        or stops[0].segment != "balance"
    ):
        raise TrainingControlDatasetError("successful replay lacks one terminal balance stop")
    return TrainingControlDataset(
        lineage_id=lineage_id,
        partition=str(partition),
        artifact_sha256=actual_sha256,
        state_sha256=state_sha256,
        source_commit=source_commit,
        source_dirty=source_dirty,
        status=str(status),
        error=error_value if isinstance(error_value, str) else None,
        examples=tuple(examples),
    )


def audit_training_control_partitions(
    datasets: Iterable[TrainingControlDataset],
) -> TrainingControlPartitionAudit:
    """Fail promotion closed on lineage, state, class, or partition leakage."""

    rows = tuple(datasets)
    reasons: list[str] = []
    lineages = [dataset.lineage_id for dataset in rows]
    artifacts = [dataset.artifact_sha256 for dataset in rows]
    if len(set(lineages)) != len(lineages):
        reasons.append("duplicate_lineage_identity")
    if len(set(artifacts)) != len(artifacts):
        reasons.append("duplicate_artifact")
    if any(not dataset.lineage_qualified for dataset in rows):
        reasons.append("unqualified_lineage")
    if any(dataset.partition == "unassigned" for dataset in rows):
        reasons.append("unassigned_lineage")
    counts = Counter(dataset.partition for dataset in rows)
    if not counts.get("train") or not counts.get("validation"):
        reasons.append("missing_train_or_validation_partition")

    train_states = {
        dataset.state_sha256 for dataset in rows if dataset.partition == "train"
    }
    validation_states = {
        dataset.state_sha256 for dataset in rows if dataset.partition == "validation"
    }
    overlap = train_states & validation_states
    if overlap:
        reasons.append("state_overlap_across_partitions")
    train_classes = {
        class_ref
        for dataset in rows
        if dataset.partition == "train"
        for class_ref in dataset.class_refs
    }
    validation_classes = {
        class_ref
        for dataset in rows
        if dataset.partition == "validation"
        for class_ref in dataset.class_refs
    }
    missing = tuple(sorted(validation_classes - train_classes))
    if missing:
        reasons.append("validation_class_absent_from_training")
    return TrainingControlPartitionAudit(
        lineage_count=len(rows),
        partition_counts=tuple(sorted(counts.items())),
        state_overlap_count=len(overlap),
        validation_classes_missing_from_training=missing,
        promotion_eligible=not reasons,
        reasons=tuple(reasons),
    )


def _example(
    raw: object,
    lineage_id: str,
    segment: str,
    expected_index: int,
) -> TrainingControlExample:
    row = _mapping(raw, subject="decision")
    if (
        row.get("schema") != "pokemon-training-control-decision-v1"
        or row.get("decision_index") != expected_index
    ):
        raise TrainingControlDatasetError("training-control decision sequence is invalid")
    raw_action = row.get("action")
    try:
        action = TrainingControlAction(raw_action) if isinstance(raw_action, str) else None
    except (TypeError, ValueError) as error:
        raise TrainingControlDatasetError("training-control action is invalid") from error
    if action is None:
        raise TrainingControlDatasetError("training-control action is invalid")
    reason = row.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise TrainingControlDatasetError("training-control reason is invalid")
    raw_observation = _mapping(row.get("observation"), subject="observation")
    raw_features = _mapping(raw_observation.get("features"), subject="features")
    if set(raw_features) != set(TRAINING_CONTROL_FEATURE_NAMES):
        raise TrainingControlDatasetError("training-control feature roster is invalid")
    raw_phase = raw_observation.get("phase")
    raw_candidates = raw_observation.get("candidate_actions")
    if not isinstance(raw_phase, str) or not isinstance(raw_candidates, list):
        raise TrainingControlDatasetError("training-control observation is invalid")
    try:
        phase = TrainingControlPhase(raw_phase)
        candidates = tuple(
            TrainingControlAction(candidate)
            for candidate in raw_candidates
            if isinstance(candidate, str)
        )
        if len(candidates) != len(raw_candidates):
            raise ValueError("candidate action must be a string")
        features = tuple(
            _number(raw_features[name], subject="feature")
            for name in TRAINING_CONTROL_FEATURE_NAMES
        )
        observation = TrainingControlObservation(
            phase=phase,
            features=features,
            candidate_actions=candidates,
            feature_schema_id=str(raw_observation.get("feature_schema_id")),
        )
    except (TypeError, ValueError) as error:
        raise TrainingControlDatasetError("training-control observation is invalid") from error
    if action not in observation.candidate_actions:
        raise TrainingControlDatasetError("teacher action is illegal for its phase")
    return TrainingControlExample(
        lineage_id=lineage_id,
        segment=segment,
        decision_index=expected_index,
        action=action,
        observation=observation,
        reason=reason,
    )


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TrainingControlDatasetError(f"training-control {subject} must be an object")
    return value


def _digest(value: str, *, subject: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise TrainingControlDatasetError(f"training-control {subject} is invalid")
    return value


def _safe_id(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise TrainingControlDatasetError(f"training-control {subject} is invalid")
    return value


def _number(value: object, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TrainingControlDatasetError(f"training-control {subject} is invalid")
    return float(value)
