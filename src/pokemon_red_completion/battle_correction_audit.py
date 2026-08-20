"""Path-free diagnostics for a retained battle-correction rollout.

Correction streams contain only teacher disagreements or low-confidence
fallbacks.  They do not contain successful model decisions or action outcomes,
so this audit deliberately reports distribution and coverage without calling a
teacher disagreement a model error.
"""

from __future__ import annotations

import hashlib
import json
import math
import stat
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.battle_model import CURRENT_BATTLE_FEATURE_SCHEMA_ID
from pokemon_red_completion.battle_semantics import FEATURE_NAMES
from pokemon_red_completion.provenance import canonical_sha256


class BattleCorrectionAuditError(RuntimeError):
    """Raised when private correction evidence cannot support a safe audit."""


@dataclass(frozen=True, slots=True)
class BattleCorrectionAudit:
    """Authenticated, deliberately path-free correction diagnostics."""

    manifest_sha256: str
    source_commit: str
    source_model_sha256: str
    confidence_threshold: float
    total_decisions: int
    model_executions: int
    teacher_fallbacks: int
    unclassified_decisions: int
    correction_records: int
    minimum_correction_decision_index: int
    maximum_correction_decision_index: int
    unique_correction_decision_indices: int
    reason_counts: tuple[tuple[str, int], ...]
    objective_counts: tuple[tuple[str, int], ...]
    battle_plan_count: int
    candidate_count_distribution: tuple[tuple[int, int], ...]
    model_teacher_confusion: tuple[tuple[str, int], ...]
    confidence_minimum: float
    confidence_median: float
    confidence_mean: float
    confidence_maximum: float
    corrections_below_threshold: int
    confidence_bucket_counts: tuple[tuple[str, int], ...]
    exact_feature_projection_clusters: int
    quantized_semantic_clusters: int
    largest_quantized_cluster_sizes: tuple[int, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-battle-correction-diagnostic-audit-v1",
            "claim": (
                "Authenticated disagreement records were audited for coverage and distribution; "
                "no disagreement is labelled a model error without a causal outcome."
            ),
            "source": {
                "git_commit": self.source_commit,
                "battle_model_sha256": self.source_model_sha256,
                "artifact_manifest_sha256": self.manifest_sha256,
            },
            "decision_accounting": {
                "total_decisions": self.total_decisions,
                "model_executions": self.model_executions,
                "teacher_fallbacks": self.teacher_fallbacks,
                "unclassified_decisions": self.unclassified_decisions,
                "classified_decisions": (
                    self.model_executions + self.teacher_fallbacks
                ),
                "accounting_complete": self.unclassified_decisions == 0,
            },
            "corrections": {
                "records": self.correction_records,
                "unique_decision_indices": self.unique_correction_decision_indices,
                "minimum_decision_index": self.minimum_correction_decision_index,
                "maximum_decision_index": self.maximum_correction_decision_index,
                "reason_counts": dict(self.reason_counts),
                "objective_counts": dict(self.objective_counts),
                "battle_plan_count": self.battle_plan_count,
                "candidate_count_distribution": {
                    str(count): records
                    for count, records in self.candidate_count_distribution
                },
                "model_teacher_candidate_confusion": dict(self.model_teacher_confusion),
            },
            "confidence": {
                "selection_threshold": self.confidence_threshold,
                "minimum": self.confidence_minimum,
                "median": self.confidence_median,
                "mean": self.confidence_mean,
                "maximum": self.confidence_maximum,
                "corrections_below_threshold": self.corrections_below_threshold,
                "correction_only_bucket_counts": dict(self.confidence_bucket_counts),
                "agreement_discrimination_auc": None,
            },
            "clusters": {
                "exact_feature_projection_count": self.exact_feature_projection_clusters,
                "quantized_semantic_count": self.quantized_semantic_clusters,
                "largest_quantized_cluster_sizes": list(
                    self.largest_quantized_cluster_sizes
                ),
            },
            "limitations": [
                "The artifact records corrections, not all model proposals.",
                "The thirteen unclassified decisions cannot be typed from this artifact.",
                (
                    "Agreement confidence and confidence AUC cannot be computed without "
                    "agreement records."
                ),
                (
                    "Teacher-disagreed model actions were not executed, so comparative "
                    "outcomes are absent."
                ),
                (
                    "Feature projections omit raw species and moveset identities; clusters "
                    "are semantic approximations."
                ),
            ],
            "promotion_eligible": False,
            "refit_eligible": False,
            "private_path_fields": 0,
        }


def audit_battle_correction_artifact(
    artifact_directory: str | Path,
    *,
    total_decisions: int,
    model_executions: int,
    teacher_fallbacks: int,
) -> BattleCorrectionAudit:
    """Authenticate a correction artifact and derive bounded diagnostics."""

    for name, value in (
        ("total decisions", total_decisions),
        ("model executions", model_executions),
        ("teacher fallbacks", teacher_fallbacks),
    ):
        if type(value) is not int or value < 0:  # noqa: E721
            raise BattleCorrectionAuditError(f"{name} must be a non-negative integer")
    classified = model_executions + teacher_fallbacks
    if classified > total_decisions:
        raise BattleCorrectionAuditError("classified decisions exceed total decisions")

    root = Path(artifact_directory)
    manifest_payload, streams = _authenticated_streams(root)
    metadata_rows = _records(streams["metadata.jsonl"])
    correction_rows = _records(streams["corrections.jsonl"])
    if len(metadata_rows) != 1 or not correction_rows:
        raise BattleCorrectionAuditError("correction artifact record counts are invalid")
    metadata = metadata_rows[0]
    source = _mapping(metadata.get("source"), "source")
    source_commit = source.get("git_commit")
    model_sha256 = metadata.get("battle_model_sha256")
    threshold = metadata.get("battle_confidence_threshold")
    if (
        metadata.get("record_type") != "red_player_v1_shadow_run"
        or metadata.get("schema_version") != 1
        or metadata.get("battle_feature_schema_id")
        != CURRENT_BATTLE_FEATURE_SCHEMA_ID
        or not _sha256(model_sha256)
        or not _git_commit(source_commit)
        or not _unit_float(threshold)
    ):
        raise BattleCorrectionAuditError("correction artifact metadata is incompatible")

    reasons: Counter[str] = Counter()
    objectives: Counter[str] = Counter()
    plans: set[str] = set()
    candidate_counts: Counter[int] = Counter()
    confusion: Counter[str] = Counter()
    confidence_buckets: Counter[str] = Counter()
    confidences: list[float] = []
    exact_clusters: set[str] = set()
    quantized_clusters: Counter[str] = Counter()
    decision_indices: list[int] = []

    previous_decision = 0
    for correction_index, row in enumerate(correction_rows, start=1):
        decision_index = row.get("decision_index")
        if (
            row.get("record_type") != "battle_policy_correction"
            or row.get("schema_version") != 1
            or row.get("correction_index") != correction_index
            or type(decision_index) is not int  # noqa: E721
            or decision_index <= previous_decision
            or decision_index > total_decisions
        ):
            raise BattleCorrectionAuditError("correction sequence is invalid")
        previous_decision = decision_index
        decision_indices.append(decision_index)

        reason = row.get("reason")
        objective = row.get("objective_id")
        plan = row.get("battle_plan_id")
        if reason not in {"teacher_disagreement", "low_confidence"}:
            raise BattleCorrectionAuditError("correction reason is invalid")
        if not isinstance(objective, str) or not objective:
            raise BattleCorrectionAuditError("correction objective is invalid")
        if not isinstance(plan, str) or not plan:
            raise BattleCorrectionAuditError("correction battle plan is invalid")
        reasons[reason] += 1
        objectives[objective] += 1
        plans.add(plan)

        features = _mapping(row.get("features"), "features")
        names = features.get("feature_names")
        vectors = features.get("candidate_vectors")
        legal_mask = features.get("legal_mask")
        slot_indices = features.get("slot_indices")
        if (
            features.get("feature_schema_id") != CURRENT_BATTLE_FEATURE_SCHEMA_ID
            or not isinstance(names, list)
            or tuple(names) != FEATURE_NAMES
            or not isinstance(vectors, list)
            or not isinstance(legal_mask, list)
            or not isinstance(slot_indices, list)
            or not vectors
            or len(vectors) != len(legal_mask)
            or len(vectors) != len(slot_indices)
        ):
            raise BattleCorrectionAuditError("correction feature batch is invalid")
        for vector in vectors:
            if (
                not isinstance(vector, list)
                or len(vector) != len(FEATURE_NAMES)
                or any(not _finite_number(value) for value in vector)
            ):
                raise BattleCorrectionAuditError("correction feature vector is invalid")
        candidate_counts[len(vectors)] += 1

        model = _mapping(row.get("model"), "model")
        teacher = _mapping(row.get("teacher"), "teacher")
        predicted = model.get("predicted_candidate_index")
        chosen = teacher.get("chosen_candidate_index")
        confidence = model.get("confidence")
        if (
            type(predicted) is not int  # noqa: E721
            or type(chosen) is not int  # noqa: E721
            or not 0 <= predicted < len(vectors)
            or not 0 <= chosen < len(vectors)
            or not _unit_float(confidence)
        ):
            raise BattleCorrectionAuditError("correction choice is invalid")
        assert isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
        confidence_value = float(confidence)
        confidences.append(confidence_value)
        confusion[f"model_{predicted}_to_teacher_{chosen}"] += 1
        confidence_buckets[_confidence_bucket(confidence_value)] += 1
        exact_clusters.add(canonical_sha256(features))
        quantized_clusters[
            _quantized_cluster_sha256(
                row,
                vectors=vectors,
                legal_mask=legal_mask,
                predicted=predicted,
                chosen=chosen,
            )
        ] += 1

    if len(correction_rows) > teacher_fallbacks:
        raise BattleCorrectionAuditError("corrections exceed teacher fallbacks")
    assert isinstance(source_commit, str)
    assert isinstance(model_sha256, str)
    assert isinstance(threshold, (int, float)) and not isinstance(threshold, bool)
    cluster_sizes = sorted(quantized_clusters.values(), reverse=True)
    return BattleCorrectionAudit(
        manifest_sha256=hashlib.sha256(manifest_payload).hexdigest(),
        source_commit=source_commit,
        source_model_sha256=model_sha256,
        confidence_threshold=float(threshold),
        total_decisions=total_decisions,
        model_executions=model_executions,
        teacher_fallbacks=teacher_fallbacks,
        unclassified_decisions=total_decisions - classified,
        correction_records=len(correction_rows),
        minimum_correction_decision_index=min(decision_indices),
        maximum_correction_decision_index=max(decision_indices),
        unique_correction_decision_indices=len(set(decision_indices)),
        reason_counts=tuple(sorted(reasons.items())),
        objective_counts=tuple(
            sorted(objectives.items(), key=lambda item: (-item[1], item[0]))
        ),
        battle_plan_count=len(plans),
        candidate_count_distribution=tuple(sorted(candidate_counts.items())),
        model_teacher_confusion=tuple(
            sorted(confusion.items(), key=lambda item: (-item[1], item[0]))
        ),
        confidence_minimum=min(confidences),
        confidence_median=statistics.median(confidences),
        confidence_mean=statistics.fmean(confidences),
        confidence_maximum=max(confidences),
        corrections_below_threshold=sum(
            confidence < float(threshold) for confidence in confidences
        ),
        confidence_bucket_counts=tuple(
            (f"{index / 10:.1f}-{(index + 1) / 10:.1f}", confidence_buckets.get(
                f"{index / 10:.1f}-{(index + 1) / 10:.1f}", 0
            ))
            for index in range(10)
        ),
        exact_feature_projection_clusters=len(exact_clusters),
        quantized_semantic_clusters=len(quantized_clusters),
        largest_quantized_cluster_sizes=tuple(cluster_sizes[:20]),
    )


def _authenticated_streams(root: Path) -> tuple[bytes, dict[str, bytes]]:
    if root.is_symlink() or not root.is_dir():
        raise BattleCorrectionAuditError("correction artifact must be a regular directory")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise BattleCorrectionAuditError("correction manifest is absent")
    try:
        manifest_payload = manifest_path.read_bytes()
        manifest = json.loads(manifest_payload.decode("ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BattleCorrectionAuditError("correction manifest cannot be read") from error
    if not isinstance(manifest, Mapping):
        raise BattleCorrectionAuditError("correction manifest is invalid")
    if (
        manifest.get("format") != "pokemon-red-completion-private-artifact-jsonl"
        or manifest.get("kind") != "battle_corrections"
        or manifest.get("schema_version") != 1
        or manifest.get("status") != "failed"
        or manifest.get("reason_code") != "unhandled_exception"
    ):
        raise BattleCorrectionAuditError("correction artifact terminal identity is invalid")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise BattleCorrectionAuditError("correction stream inventory is absent")
    entries: dict[str, Mapping[str, object]] = {}
    for entry in files:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("filename"), str):
            raise BattleCorrectionAuditError("correction stream inventory is invalid")
        entries[str(entry["filename"])] = entry
    if set(entries) != {"metadata.jsonl", "corrections.jsonl"}:
        raise BattleCorrectionAuditError("correction stream roster is invalid")
    payloads: dict[str, bytes] = {}
    for filename, entry in entries.items():
        path = root / filename
        try:
            metadata = path.lstat()
            payload = path.read_bytes()
        except OSError as error:
            raise BattleCorrectionAuditError("correction stream cannot be read") from error
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            raise BattleCorrectionAuditError("correction stream is unsafe")
        records = _records(payload)
        if (
            entry.get("bytes") != len(payload)
            or entry.get("records") != len(records)
            or entry.get("sha256") != hashlib.sha256(payload).hexdigest()
        ):
            raise BattleCorrectionAuditError("correction stream failed authentication")
        payloads[filename] = payload
    return manifest_payload, payloads


def _records(payload: bytes) -> list[dict[str, object]]:
    try:
        text = payload.decode("ascii")
    except UnicodeError as error:
        raise BattleCorrectionAuditError("correction stream is not ASCII") from error
    if not text.endswith("\n"):
        raise BattleCorrectionAuditError("correction stream is not canonical JSONL")
    records: list[dict[str, object]] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise BattleCorrectionAuditError("correction stream contains invalid JSON") from error
        if not isinstance(value, dict):
            raise BattleCorrectionAuditError("correction record is not an object")
        canonical = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        if canonical != line:
            raise BattleCorrectionAuditError("correction record is not canonical")
        records.append(value)
    return records


def _quantized_cluster_sha256(
    row: Mapping[str, object],
    *,
    vectors: Sequence[object],
    legal_mask: Sequence[object],
    predicted: int,
    chosen: int,
) -> str:
    state_indices = tuple(
        index for index, name in enumerate(FEATURE_NAMES) if name.startswith("state.")
    )
    action_indices = tuple(
        index
        for index, name in enumerate(FEATURE_NAMES)
        if name.startswith(("move.", "interaction.", "constraint."))
    )
    first = vectors[0]
    assert isinstance(first, list)
    candidate_profiles: list[list[float]] = []
    for vector in vectors:
        assert isinstance(vector, list)
        candidate_profiles.append([round(float(vector[index]), 1) for index in action_indices])
    return canonical_sha256(
        {
            "policy_context": row.get("policy_context"),
            "state_buckets": [round(float(first[index]), 1) for index in state_indices],
            "candidate_profiles": candidate_profiles,
            "legal_mask": list(legal_mask),
            "predicted_candidate_index": predicted,
            "teacher_candidate_index": chosen,
        }
    )


def _confidence_bucket(value: float) -> str:
    index = min(int(value * 10), 9)
    return f"{index / 10:.1f}-{(index + 1) / 10:.1f}"


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BattleCorrectionAuditError(f"correction {subject} is invalid")
    return value


def _sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _git_commit(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) in {40, 64}
        and all(character in "0123456789abcdef" for character in value)
    )


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _unit_float(value: object) -> bool:
    if not _finite_number(value):
        return False
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    return 0.0 <= float(value) <= 1.0


__all__ = [
    "BattleCorrectionAudit",
    "BattleCorrectionAuditError",
    "audit_battle_correction_artifact",
]
