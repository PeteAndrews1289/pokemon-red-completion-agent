"""Authenticated whole-lineage datasets for strategic training choices."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TRAINING_CANDIDATE_FEATURE_SCHEMA_ID,
    TrainingCandidate,
    TrainingCandidateDecision,
    TrainingCandidateSet,
    TrainingChoiceKind,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._:-]{0,159}\Z")
_PARTITIONS = frozenset({"train", "validation", "test", "unassigned"})
_SEGMENTS = ("evolution", "balance")


class TrainingCandidateDatasetError(RuntimeError):
    """Raised when a strategic-choice lineage is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class TrainingCandidateExample:
    lineage_id: str
    segment: str
    decision_index: int
    selected_candidate_index: int
    observation: TrainingCandidateSet
    reason: str


@dataclass(frozen=True, slots=True)
class TrainingCandidateDataset:
    lineage_id: str
    partition: str
    artifact_sha256: str
    state_sha256: str
    source_commit: str
    source_dirty: bool
    status: str
    error: str | None
    final_party_levels: tuple[int, ...]
    final_fainted_count: int
    observed_decisions: int
    retained_decisions: int
    examples: tuple[TrainingCandidateExample, ...]

    @property
    def lineage_qualified(self) -> bool:
        return self.status == "ok" and not self.source_dirty

    @property
    def choice_kinds(self) -> frozenset[str]:
        return frozenset(example.observation.kind.value for example in self.examples)

    def public_summary(self) -> dict[str, object]:
        kinds = Counter(example.observation.kind.value for example in self.examples)
        candidate_counts = Counter(
            len(example.observation.candidates) for example in self.examples
        )
        selected = Counter(
            f"{example.observation.kind.value}/{len(example.observation.candidates)}"
            f" -> {example.selected_candidate_index}"
            for example in self.examples
        )
        multi = sum(len(example.observation.candidates) > 1 for example in self.examples)
        unique = {
            (
                example.observation.kind.value,
                tuple(candidate.features for candidate in example.observation.candidates),
                example.selected_candidate_index,
            )
            for example in self.examples
        }
        return {
            "schema": "pokemon-training-candidate-dataset-summary-v1",
            "lineage_id": self.lineage_id,
            "partition": self.partition,
            "artifact_sha256": self.artifact_sha256,
            "state_sha256": self.state_sha256,
            "source_commit": self.source_commit,
            "source_dirty": self.source_dirty,
            "status": self.status,
            "lineage_qualified": self.lineage_qualified,
            "final_party_levels": list(self.final_party_levels),
            "final_fainted_count": self.final_fainted_count,
            "observed_decisions": self.observed_decisions,
            "retained_decisions": self.retained_decisions,
            "consecutive_duplicate_decisions_removed": (
                self.observed_decisions - self.retained_decisions
            ),
            "examples": len(self.examples),
            "unique_choice_feature_label_tuples": len(unique),
            "duplicate_choice_feature_label_tuples": len(self.examples) - len(unique),
            "choice_kind_counts": dict(sorted(kinds.items())),
            "candidate_count_counts": {
                str(count): examples for count, examples in sorted(candidate_counts.items())
            },
            "selected_index_counts": dict(sorted(selected.items())),
            "multi_candidate_decisions": multi,
            "singleton_decisions": len(self.examples) - multi,
            "promotion_eligible": False,
        }


@dataclass(frozen=True, slots=True)
class TrainingCandidatePartitionAudit:
    lineage_count: int
    partition_counts: tuple[tuple[str, int], ...]
    state_overlap_count: int
    validation_kinds_missing_from_training: tuple[str, ...]
    promotion_eligible: bool
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-training-candidate-partition-audit-v1",
            "lineage_count": self.lineage_count,
            "partition_counts": dict(self.partition_counts),
            "state_overlap_count": self.state_overlap_count,
            "validation_kinds_missing_from_training": list(
                self.validation_kinds_missing_from_training
            ),
            "promotion_eligible": self.promotion_eligible,
            "reasons": list(self.reasons),
        }


def load_training_candidate_replay(
    path: str | Path,
    *,
    expected_sha256: str,
) -> TrainingCandidateDataset:
    """Authenticate and decode one complete or failed strategic replay."""

    _digest(expected_sha256, subject="expected artifact digest")
    source = Path(path)
    try:
        metadata = source.lstat()
        payload = source.read_bytes()
    except OSError as error:
        raise TrainingCandidateDatasetError("candidate replay cannot be read") from error
    if source.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise TrainingCandidateDatasetError("candidate replay must be a regular file")
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise TrainingCandidateDatasetError("candidate replay failed authentication")
    try:
        root = json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise TrainingCandidateDatasetError("candidate replay is invalid JSON") from error
    value = _mapping(root, subject="replay")
    feature_names = value.get("feature_names")
    if (
        value.get("schema") != "pokemon-training-candidate-replay-v1"
        or value.get("feature_schema_id") != TRAINING_CANDIDATE_FEATURE_SCHEMA_ID
        or not isinstance(feature_names, list)
        or tuple(feature_names) != TRAINING_CANDIDATE_FEATURE_NAMES
    ):
        raise TrainingCandidateDatasetError("candidate replay schema is incompatible")

    status = value.get("status")
    error_value = value.get("error")
    if status not in {"ok", "failed"}:
        raise TrainingCandidateDatasetError("candidate replay status is invalid")
    if status == "ok" and error_value is not None:
        raise TrainingCandidateDatasetError("successful candidate replay carries an error")
    if status == "failed" and (not isinstance(error_value, str) or not error_value.strip()):
        raise TrainingCandidateDatasetError("failed candidate replay lacks an error")

    provenance = _mapping(value.get("provenance"), subject="provenance")
    lineage_id = _safe_id(provenance.get("lineage_id"), subject="lineage identity")
    partition = provenance.get("partition")
    source_commit = provenance.get("source_commit")
    source_dirty = provenance.get("source_dirty")
    state_sha256 = provenance.get("state_sha256")
    if partition not in _PARTITIONS:
        raise TrainingCandidateDatasetError("candidate partition is invalid")
    if not isinstance(source_commit, str) or _GIT_COMMIT.fullmatch(source_commit) is None:
        raise TrainingCandidateDatasetError("candidate source commit is invalid")
    if type(source_dirty) is not bool:  # noqa: E721
        raise TrainingCandidateDatasetError("candidate dirty-source flag is invalid")
    if not isinstance(state_sha256, str):
        raise TrainingCandidateDatasetError("candidate state digest is invalid")
    _digest(state_sha256, subject="state digest")

    outcome = _mapping(value.get("outcome"), subject="candidate outcome")
    raw_levels = outcome.get("final_party_levels")
    raw_faints = outcome.get("final_fainted_count")
    if (
        not isinstance(raw_levels, list)
        or not 1 <= len(raw_levels) <= 6
        or not all(
            type(level) is int and 1 <= level <= 100 for level in raw_levels  # noqa: E721
        )
        or type(raw_faints) is not int  # noqa: E721
        or not 0 <= raw_faints <= len(raw_levels)
    ):
        raise TrainingCandidateDatasetError("candidate terminal outcome is invalid")
    final_party_levels = tuple(raw_levels)
    final_fainted_count = raw_faints

    segments = _mapping(value.get("segments"), subject="segments")
    if set(segments) != set(_SEGMENTS):
        raise TrainingCandidateDatasetError("candidate segment roster is invalid")
    sampling = _mapping(value.get("sampling"), subject="candidate sampling")
    if set(sampling) != set(_SEGMENTS):
        raise TrainingCandidateDatasetError("candidate sampling roster is invalid")
    examples: list[TrainingCandidateExample] = []
    observed_decisions = 0
    retained_decisions = 0
    for segment in _SEGMENTS:
        rows = segments[segment]
        if not isinstance(rows, list):
            raise TrainingCandidateDatasetError("candidate segment is not a list")
        observed, retained = _sampling_counts(sampling[segment], len(rows))
        observed_decisions += observed
        retained_decisions += retained
        for expected_index, row in enumerate(rows):
            examples.append(_example(row, lineage_id, segment, expected_index))
    if not examples:
        raise TrainingCandidateDatasetError("candidate replay has no decisions")
    return TrainingCandidateDataset(
        lineage_id=lineage_id,
        partition=str(partition),
        artifact_sha256=actual_sha256,
        state_sha256=state_sha256,
        source_commit=source_commit,
        source_dirty=source_dirty,
        status=str(status),
        error=error_value if isinstance(error_value, str) else None,
        final_party_levels=final_party_levels,
        final_fainted_count=final_fainted_count,
        observed_decisions=observed_decisions,
        retained_decisions=retained_decisions,
        examples=tuple(examples),
    )


def audit_training_candidate_partitions(
    datasets: Iterable[TrainingCandidateDataset],
) -> TrainingCandidatePartitionAudit:
    """Fail promotion closed on lineage, root, source, kind, or partition leakage."""

    rows = tuple(datasets)
    reasons: list[str] = []
    lineages = [dataset.lineage_id for dataset in rows]
    artifacts = [dataset.artifact_sha256 for dataset in rows]
    states = [dataset.state_sha256 for dataset in rows]
    if len(set(lineages)) != len(lineages):
        reasons.append("duplicate_lineage_identity")
    if len(set(artifacts)) != len(artifacts):
        reasons.append("duplicate_artifact")
    if len(set(states)) != len(states):
        reasons.append("duplicate_root_state")
    if len({dataset.source_commit for dataset in rows}) > 1:
        reasons.append("mixed_source_commit")
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
    train_kinds = {
        kind
        for dataset in rows
        if dataset.partition == "train"
        for kind in dataset.choice_kinds
    }
    validation_kinds = {
        kind
        for dataset in rows
        if dataset.partition == "validation"
        for kind in dataset.choice_kinds
    }
    missing = tuple(sorted(validation_kinds - train_kinds))
    if missing:
        reasons.append("validation_choice_kind_absent_from_training")
    return TrainingCandidatePartitionAudit(
        lineage_count=len(rows),
        partition_counts=tuple(sorted(counts.items())),
        state_overlap_count=len(overlap),
        validation_kinds_missing_from_training=missing,
        promotion_eligible=not reasons,
        reasons=tuple(reasons),
    )


def _example(
    raw: object,
    lineage_id: str,
    segment: str,
    expected_index: int,
) -> TrainingCandidateExample:
    row = _mapping(raw, subject="decision")
    if (
        row.get("schema") != "pokemon-training-candidate-decision-v1"
        or row.get("decision_index") != expected_index
    ):
        raise TrainingCandidateDatasetError("candidate decision sequence is invalid")
    reason = row.get("reason")
    selected = row.get("selected_candidate_index")
    if not isinstance(reason, str) or not reason.strip():
        raise TrainingCandidateDatasetError("candidate decision reason is invalid")
    if type(selected) is not int:  # noqa: E721
        raise TrainingCandidateDatasetError("selected candidate index is invalid")
    raw_observation = _mapping(row.get("observation"), subject="observation")
    if raw_observation.get("schema") != "pokemon-training-candidate-set-v1":
        raise TrainingCandidateDatasetError("candidate-set schema is invalid")
    raw_kind = raw_observation.get("kind")
    raw_candidates = raw_observation.get("candidates")
    if not isinstance(raw_kind, str) or not isinstance(raw_candidates, list):
        raise TrainingCandidateDatasetError("candidate observation is invalid")
    try:
        kind = TrainingChoiceKind(raw_kind)
        candidates = tuple(
            _candidate(raw_candidate, expected_index=index)
            for index, raw_candidate in enumerate(raw_candidates)
        )
        observation = TrainingCandidateSet(kind, candidates)
        decision = TrainingCandidateDecision(
            expected_index,
            selected,
            observation,
            reason,
        )
    except (TypeError, ValueError) as error:
        raise TrainingCandidateDatasetError("candidate observation is invalid") from error
    return TrainingCandidateExample(
        lineage_id=lineage_id,
        segment=segment,
        decision_index=expected_index,
        selected_candidate_index=decision.selected_candidate_index,
        observation=observation,
        reason=reason,
    )


def _sampling_counts(raw: object, row_count: int) -> tuple[int, int]:
    sampling = _mapping(raw, subject="candidate segment sampling")
    observed = sampling.get("observed_decisions")
    retained = sampling.get("retained_decisions")
    removed = sampling.get("consecutive_duplicate_decisions_removed")
    if (
        sampling.get("method") != "retain_first_and_per_kind_state_transitions"
        or type(observed) is not int  # noqa: E721
        or type(retained) is not int  # noqa: E721
        or type(removed) is not int  # noqa: E721
        or observed < retained
        or retained != row_count
        or removed != observed - retained
    ):
        raise TrainingCandidateDatasetError("candidate sampling counts are invalid")
    return observed, retained


def _candidate(raw: object, *, expected_index: int) -> TrainingCandidate:
    row = _mapping(raw, subject="candidate")
    if set(row) != {"candidate_index", "feature_schema_id", "features"}:
        raise TrainingCandidateDatasetError("candidate contains an unexpected field")
    raw_features = _mapping(row.get("features"), subject="features")
    if set(raw_features) != set(TRAINING_CANDIDATE_FEATURE_NAMES):
        raise TrainingCandidateDatasetError("candidate feature roster is invalid")
    return TrainingCandidate(
        candidate_index=expected_index if row.get("candidate_index") == expected_index else -1,
        features=tuple(
            _number(raw_features[name], subject="feature")
            for name in TRAINING_CANDIDATE_FEATURE_NAMES
        ),
        feature_schema_id=str(row.get("feature_schema_id")),
    )


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TrainingCandidateDatasetError(f"candidate {subject} must be an object")
    return value


def _digest(value: str, *, subject: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise TrainingCandidateDatasetError(f"candidate {subject} is invalid")
    return value


def _safe_id(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise TrainingCandidateDatasetError(f"candidate {subject} is invalid")
    return value


def _number(value: object, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TrainingCandidateDatasetError(f"candidate {subject} is invalid")
    return float(value)
