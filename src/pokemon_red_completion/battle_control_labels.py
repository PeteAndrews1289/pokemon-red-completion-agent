"""Authenticated full-battle control labels collected from the routed teacher."""

from __future__ import annotations

import hashlib
import json
import stat
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pokemon_red_completion.battle_actions import BattleAction


class BattleControlLabelError(RuntimeError):
    """Raised when a private control-label artifact is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class BattleControlLabel:
    decision_index: int
    battle_plan_id: str
    objective_id: str
    observation: Mapping[str, object]
    teacher_action: BattleAction


@dataclass(frozen=True, slots=True)
class BattleControlDataset:
    artifact_id: str
    manifest_sha256: str
    source_model_sha256: str
    labels: tuple[BattleControlLabel, ...]
    game_complete: bool

    def public_summary(self) -> dict[str, object]:
        counts = Counter(label.teacher_action.semantic_ref for label in self.labels)
        return {
            "schema": "battle-control-dataset-summary-v1",
            "artifact_id": self.artifact_id,
            "manifest_sha256": self.manifest_sha256,
            "source_model_sha256": self.source_model_sha256,
            "labels": len(self.labels),
            "battle_groups": len({label.battle_plan_id for label in self.labels}),
            "action_counts": dict(sorted(counts.items())),
            "game_complete": self.game_complete,
        }


def load_battle_control_artifact(
    artifact_directory: str | Path,
) -> BattleControlDataset:
    """Authenticate and decode one completed private control-label artifact."""

    root = Path(artifact_directory)
    if root.is_symlink() or not root.is_dir():
        raise BattleControlLabelError("battle control artifact must be a regular directory")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise BattleControlLabelError("battle control manifest is absent")
    try:
        manifest_payload = manifest_path.read_bytes()
        manifest = json.loads(manifest_payload.decode("ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BattleControlLabelError("battle control manifest cannot be read") from error
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("format") != "pokemon-red-completion-private-artifact-jsonl"
        or manifest.get("kind") != "battle_control_labels"
        or manifest.get("schema_version") != 1
        or manifest.get("status") != "complete"
    ):
        raise BattleControlLabelError("battle control artifact is not complete and typed")
    artifact_id = manifest.get("artifact_id")
    if not isinstance(artifact_id, str) or artifact_id != root.name:
        raise BattleControlLabelError("battle control artifact identity does not match")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise BattleControlLabelError("battle control file inventory is absent")
    expected = {"metadata.jsonl", "labels.jsonl", "summary.jsonl"}
    entries = {
        str(entry.get("filename")): entry
        for entry in files
        if isinstance(entry, Mapping) and isinstance(entry.get("filename"), str)
    }
    if set(entries) != expected or len(entries) != len(files):
        raise BattleControlLabelError("battle control stream roster is invalid")
    visible = {child.name for child in root.iterdir() if child.name != "manifest.json"}
    if visible != expected:
        raise BattleControlLabelError("battle control directory contains undeclared entries")
    records: dict[str, list[Mapping[str, object]]] = {}
    for filename, entry in entries.items():
        path = root / filename
        try:
            metadata = path.lstat()
            payload = path.read_bytes()
        except OSError as error:
            raise BattleControlLabelError("battle control stream cannot be read") from error
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or entry.get("bytes") != len(payload)
            or entry.get("sha256") != hashlib.sha256(payload).hexdigest()
        ):
            raise BattleControlLabelError("battle control stream failed authentication")
        rows = _records(payload)
        if entry.get("records") != len(rows):
            raise BattleControlLabelError("battle control stream failed authentication")
        records[filename] = rows
    if (
        len(records["metadata.jsonl"]) != 1
        or not records["labels.jsonl"]
        or len(records["summary.jsonl"]) != 1
    ):
        raise BattleControlLabelError("battle control record counts are invalid")
    header = records["metadata.jsonl"][0]
    source_model_sha256 = header.get("model_sha256")
    if (
        header.get("record_type") != "battle_control_run"
        or header.get("schema_version") != 1
        or header.get("action_schema") != "pokemon.core.battle.action.v1"
        or not isinstance(source_model_sha256, str)
        or len(source_model_sha256) != 64
    ):
        raise BattleControlLabelError("battle control metadata is incompatible")
    labels: list[BattleControlLabel] = []
    previous_decision = 0
    for expected_index, row in enumerate(records["labels.jsonl"], start=1):
        decision_index = row.get("decision_index")
        battle_plan_id = row.get("battle_plan_id")
        objective_id = row.get("objective_id")
        observation = row.get("observation")
        if (
            row.get("record_type") != "battle_control_label"
            or row.get("schema_version") != 1
            or row.get("label_index") != expected_index
            or type(decision_index) is not int  # noqa: E721
            or decision_index <= previous_decision
            or not isinstance(battle_plan_id, str)
            or not battle_plan_id
            or not isinstance(objective_id, str)
            or not objective_id
            or not isinstance(observation, Mapping)
            or observation.get("schema_version") != 1
            or observation.get("mode") != "battle"
        ):
            raise BattleControlLabelError("battle control label sequence is invalid")
        try:
            action = BattleAction.from_dict(_mapping(row.get("teacher_action")))
        except (TypeError, ValueError) as error:
            raise BattleControlLabelError("battle control action is invalid") from error
        previous_decision = decision_index
        labels.append(
            BattleControlLabel(
                decision_index=decision_index,
                battle_plan_id=battle_plan_id,
                objective_id=objective_id,
                observation=observation,
                teacher_action=action,
            )
        )
    summary = records["summary.jsonl"][0]
    policy = summary.get("battle_policy")
    if (
        summary.get("record_type") != "battle_control_summary"
        or summary.get("schema_version") != 1
        or summary.get("game_complete") is not True
        or not isinstance(policy, Mapping)
        or policy.get("control_records") != len(labels)
    ):
        raise BattleControlLabelError("battle control summary does not match labels")
    return BattleControlDataset(
        artifact_id=artifact_id,
        manifest_sha256=hashlib.sha256(manifest_payload).hexdigest(),
        source_model_sha256=source_model_sha256,
        labels=tuple(labels),
        game_complete=True,
    )


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise BattleControlLabelError("battle control value must be a mapping")
    return value


def _records(payload: bytes) -> list[Mapping[str, object]]:
    try:
        text = payload.decode("ascii")
    except UnicodeError as error:
        raise BattleControlLabelError("battle control stream is not ASCII JSONL") from error
    if not text or not text.endswith("\n"):
        raise BattleControlLabelError("battle control stream is not canonical JSONL")
    rows: list[Mapping[str, object]] = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise BattleControlLabelError("battle control record is invalid") from error
        if not isinstance(value, Mapping):
            raise BattleControlLabelError("battle control record must be an object")
        canonical = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        if line != canonical:
            raise BattleControlLabelError("battle control record is not canonical")
        rows.append(value)
    return rows
