"""Authenticated learner-intervention corpora for iterative battle training."""

from __future__ import annotations

import hashlib
import json
import math
import stat
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.battle_dataset import BattleDecisionExample
from pokemon_red_completion.battle_model import CURRENT_BATTLE_FEATURE_SCHEMA_ID
from pokemon_red_completion.battle_semantics import (
    FEATURE_NAMES,
    BattleFeatureBatch,
    BattleMovePolicyContext,
)
from pokemon_red_completion.trajectory import canonical_sha256


class BattleCorrectionError(RuntimeError):
    """Raised when a correction artifact is unsafe, invalid, or inconsistent."""


@dataclass(frozen=True, slots=True)
class BattleCorrectionDataset:
    """Verified teacher labels emitted by one model-assisted completion."""

    artifact_id: str
    manifest_sha256: str
    source_model_sha256: str
    examples: tuple[BattleDecisionExample, ...]
    reason_counts: tuple[tuple[str, int], ...]
    game_complete: bool
    rollout_status: str

    def public_summary(self) -> dict[str, object]:
        return {
            "schema": "battle-correction-dataset-summary-v1",
            "artifact_id": self.artifact_id,
            "manifest_sha256": self.manifest_sha256,
            "source_model_sha256": self.source_model_sha256,
            "decisions": len(self.examples),
            "groups": len({example.group_id for example in self.examples}),
            "reason_counts": dict(self.reason_counts),
            "game_complete": self.game_complete,
            "rollout_status": self.rollout_status,
        }


def load_battle_correction_artifact(
    artifact_directory: str | Path,
) -> BattleCorrectionDataset:
    """Authenticate all streams and decode a private correction artifact."""

    root = Path(artifact_directory)
    if root.is_symlink() or not root.is_dir():
        raise BattleCorrectionError("battle correction artifact must be a regular directory")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise BattleCorrectionError("battle correction manifest is absent")
    try:
        manifest_payload = manifest_path.read_bytes()
        manifest = json.loads(manifest_payload.decode("ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BattleCorrectionError("battle correction manifest cannot be read") from error
    if not isinstance(manifest, Mapping):
        raise BattleCorrectionError("battle correction manifest is invalid")
    if (
        manifest.get("format") != "pokemon-red-completion-private-artifact-jsonl"
        or manifest.get("kind") != "battle_corrections"
        or manifest.get("schema_version") != 1
        or manifest.get("status") not in {"complete", "failed"}
    ):
        raise BattleCorrectionError("battle correction artifact is not complete and typed")
    artifact_id = manifest.get("artifact_id")
    status = str(manifest.get("status"))
    expected_directory_name = (
        artifact_id if status == "complete" else f"{artifact_id}.failed.partial"
    )
    if not isinstance(artifact_id, str) or root.name != expected_directory_name:
        raise BattleCorrectionError("battle correction artifact identity does not match")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise BattleCorrectionError("battle correction file inventory is absent")
    expected_streams = {"metadata.jsonl", "corrections.jsonl"}
    if status == "complete":
        expected_streams.add("summary.jsonl")
    elif manifest.get("reason_code") != "unhandled_exception":
        raise BattleCorrectionError("failed correction artifact has an invalid terminal reason")
    entries: dict[str, Mapping[str, object]] = {}
    payloads: dict[str, bytes] = {}
    for value in files:
        if not isinstance(value, Mapping):
            raise BattleCorrectionError("battle correction file inventory is invalid")
        filename = value.get("filename")
        if not isinstance(filename, str) or filename in entries:
            raise BattleCorrectionError("battle correction stream identity is invalid")
        entries[filename] = value
    if set(entries) != expected_streams:
        raise BattleCorrectionError("battle correction stream roster is incomplete")
    visible_files = {
        child.name
        for child in root.iterdir()
        if child.name != "manifest.json"
    }
    if visible_files != expected_streams:
        raise BattleCorrectionError("battle correction directory contains undeclared entries")
    for filename, entry in entries.items():
        path = root / filename
        try:
            metadata = path.lstat()
            payload = path.read_bytes()
        except OSError as error:
            raise BattleCorrectionError("battle correction stream cannot be read") from error
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            raise BattleCorrectionError("battle correction stream is unsafe")
        if (
            entry.get("bytes") != len(payload)
            or entry.get("sha256") != hashlib.sha256(payload).hexdigest()
        ):
            raise BattleCorrectionError("battle correction stream failed authentication")
        records = _records(payload)
        if entry.get("records") != len(records):
            raise BattleCorrectionError("battle correction stream failed authentication")
        payloads[filename] = payload

    metadata_rows = _records(payloads["metadata.jsonl"])
    correction_rows = _records(payloads["corrections.jsonl"])
    summary_rows = (
        _records(payloads["summary.jsonl"])
        if "summary.jsonl" in payloads
        else []
    )
    if (
        len(metadata_rows) != 1
        or (status == "complete" and len(summary_rows) != 1)
        or not correction_rows
    ):
        raise BattleCorrectionError("battle correction record counts are invalid")
    header = metadata_rows[0]
    if (
        header.get("record_type") != "battle_correction_run"
        or header.get("schema_version") != 1
        or header.get("feature_schema_id") != CURRENT_BATTLE_FEATURE_SCHEMA_ID
        or header.get("feature_count") != len(FEATURE_NAMES)
    ):
        raise BattleCorrectionError("battle correction metadata is incompatible")
    source_model_sha256 = header.get("model_sha256")
    if not isinstance(source_model_sha256, str) or len(source_model_sha256) != 64:
        raise BattleCorrectionError("battle correction source model identity is invalid")

    examples: list[BattleDecisionExample] = []
    reasons: Counter[str] = Counter()
    previous_decision = 0
    for expected_index, row in enumerate(correction_rows, start=1):
        if (
            row.get("record_type") != "battle_policy_correction"
            or row.get("schema_version") != 1
            or row.get("correction_index") != expected_index
        ):
            raise BattleCorrectionError("battle correction sequence is invalid")
        decision_index = row.get("decision_index")
        if (
            type(decision_index) is not int  # noqa: E721
            or decision_index <= previous_decision
        ):
            raise BattleCorrectionError("battle correction decisions are not ordered")
        previous_decision = decision_index
        reason = row.get("reason")
        if reason not in {"low_confidence", "teacher_disagreement"}:
            raise BattleCorrectionError("battle correction reason is invalid")
        reasons[str(reason)] += 1
        features = _mapping(row.get("features"), "features")
        if (
            features.get("feature_schema_id") != CURRENT_BATTLE_FEATURE_SCHEMA_ID
            or tuple(features.get("feature_names", ())) != FEATURE_NAMES
        ):
            raise BattleCorrectionError("battle correction feature schema changed")
        batch = BattleFeatureBatch(
            feature_names=FEATURE_NAMES,
            candidate_vectors=tuple(
                tuple(float(item) for item in vector)
                for vector in _list(features.get("candidate_vectors"), "candidate vectors")
            ),
            legal_mask=tuple(
                _bool(item, "legal mask")
                for item in _list(features.get("legal_mask"), "legal mask")
            ),
            current_pp=tuple(
                _finite_float(item, "current PP")
                for item in _list(features.get("current_pp"), "current PP")
            ),
            slot_indices=tuple(
                _integer(item, "slot index")
                for item in _list(features.get("slot_indices"), "slot indices")
            ),
        )
        model = _mapping(row.get("model"), "model prediction")
        predicted = _integer(model.get("predicted_candidate_index"), "model candidate")
        confidence = _finite_float(model.get("confidence"), "model confidence")
        if not 0.0 <= confidence <= 1.0 or not 0 <= predicted < len(batch.slot_indices):
            raise BattleCorrectionError("battle correction prediction is invalid")
        teacher = _mapping(row.get("teacher"), "teacher label")
        chosen = _integer(teacher.get("chosen_candidate_index"), "teacher candidate")
        context = _policy_context(row.get("policy_context"))
        battle_plan_id = row.get("battle_plan_id")
        if not isinstance(battle_plan_id, str) or not battle_plan_id:
            raise BattleCorrectionError("battle correction group identity is absent")
        snapshot_sha256 = canonical_sha256(features)
        group_id = canonical_sha256({"battle_plan_id": battle_plan_id})
        examples.append(
            BattleDecisionExample(
                decision_id=f"{artifact_id}:{expected_index}",
                snapshot_sha256=snapshot_sha256,
                step_index=decision_index,
                group_id=group_id,
                group_source="explicit_battle_instance",
                features=batch,
                chosen_candidate_index=chosen,
                policy_goal_observed=context is not None,
                policy_context=context,
            )
        )

    game_complete = False
    if status == "complete":
        summary = summary_rows[0]
        policy = _mapping(summary.get("battle_policy"), "battle policy summary")
        game_complete = summary.get("game_complete") is True
        if (
            summary.get("record_type") != "battle_correction_summary"
            or summary.get("schema_version") != 1
            or not game_complete
            or policy.get("correction_records") != len(examples)
        ):
            raise BattleCorrectionError("battle correction terminal summary does not match")
    return BattleCorrectionDataset(
        artifact_id=artifact_id,
        manifest_sha256=hashlib.sha256(manifest_payload).hexdigest(),
        source_model_sha256=source_model_sha256,
        examples=tuple(examples),
        reason_counts=tuple(sorted(reasons.items())),
        game_complete=game_complete,
        rollout_status=("game_complete" if game_complete else "learner_failure"),
    )


def _records(payload: bytes) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        text = payload.decode("ascii")
    except UnicodeError as error:
        raise BattleCorrectionError("battle correction stream is not ASCII JSONL") from error
    if not text.endswith("\n"):
        raise BattleCorrectionError("battle correction stream is not canonical JSONL")
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise BattleCorrectionError("battle correction stream contains invalid JSON") from error
        if not isinstance(value, dict):
            raise BattleCorrectionError("battle correction record is not an object")
        canonical = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        if canonical != line:
            raise BattleCorrectionError("battle correction record is not canonical")
        rows.append(value)
    return rows


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BattleCorrectionError(f"battle correction {subject} is invalid")
    return value


def _list(value: object, subject: str) -> list[object]:
    if not isinstance(value, list):
        raise BattleCorrectionError(f"battle correction {subject} is invalid")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise BattleCorrectionError(f"battle correction {subject} is invalid")
    return value


def _bool(value: object, subject: str) -> bool:
    if not isinstance(value, bool):
        raise BattleCorrectionError(f"battle correction {subject} is invalid")
    return value


def _finite_float(value: object, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BattleCorrectionError(f"battle correction {subject} is invalid")
    result = float(value)
    if not math.isfinite(result):
        raise BattleCorrectionError(f"battle correction {subject} is invalid")
    return result


def _policy_context(value: object) -> BattleMovePolicyContext | None:
    if value is None:
        return None
    context = _mapping(value, "policy context")
    goal = context.get("goal")
    move_policy = context.get("move_policy")
    required_move_ref = context.get("required_move_ref")
    if not isinstance(goal, str) or not isinstance(move_policy, str):
        raise BattleCorrectionError("battle correction policy context is invalid")
    if required_move_ref is not None and not isinstance(required_move_ref, str):
        raise BattleCorrectionError("battle correction required move is invalid")
    return BattleMovePolicyContext(
        goal=goal,
        move_policy=move_policy,
        required_move_ref=required_move_ref,
    )
