from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pokemon_red_completion.battle_corrections import (
    BattleCorrectionError,
    load_battle_correction_artifact,
)
from pokemon_red_completion.battle_model import CURRENT_BATTLE_FEATURE_SCHEMA_ID
from pokemon_red_completion.battle_semantics import FEATURE_NAMES


def _line(value: object) -> bytes:
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


def _artifact(tmp_path: Path) -> Path:
    root = tmp_path / "red-battle-corrections-test"
    root.mkdir()
    streams = {
        "metadata.jsonl": _line(
            {
                "record_type": "battle_correction_run",
                "schema_version": 1,
                "model_id": "pokemon.core.battle.masked-linear-ranker.v1",
                "model_sha256": "a" * 64,
                "feature_schema_id": CURRENT_BATTLE_FEATURE_SCHEMA_ID,
                "feature_count": len(FEATURE_NAMES),
                "confidence_threshold": 0.5,
                "teacher_agreement_required": True,
            }
        ),
        "corrections.jsonl": _line(
            {
                "record_type": "battle_policy_correction",
                "schema_version": 1,
                "decision_index": 7,
                "correction_index": 1,
                "reason": "teacher_disagreement",
                "objective_id": "test_battle",
                "battle_plan_id": "battle-test",
                "policy_context": {
                    "goal": "win",
                    "move_policy": "any_usable",
                    "required_move_ref": None,
                },
                "features": {
                    "feature_schema_id": CURRENT_BATTLE_FEATURE_SCHEMA_ID,
                    "feature_names": list(FEATURE_NAMES),
                    "candidate_vectors": [
                        [0.0] * len(FEATURE_NAMES),
                        [0.0] * len(FEATURE_NAMES),
                    ],
                    "legal_mask": [True, True],
                    "current_pp": [10.0, 10.0],
                    "slot_indices": [0, 2],
                },
                "model": {
                    "predicted_candidate_index": 1,
                    "confidence": 0.75,
                },
                "teacher": {"chosen_candidate_index": 0},
            }
        ),
        "summary.jsonl": _line(
            {
                "record_type": "battle_correction_summary",
                "schema_version": 1,
                "battle_policy": {"correction_records": 1},
                "game_complete": True,
            }
        ),
    }
    entries = []
    for filename, payload in streams.items():
        (root / filename).write_bytes(payload)
        entries.append(
            {
                "bytes": len(payload),
                "filename": filename,
                "records": 1,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    (root / "manifest.json").write_bytes(
        _line(
            {
                "artifact_id": root.name,
                "files": sorted(entries, key=lambda entry: str(entry["filename"])),
                "format": "pokemon-red-completion-private-artifact-jsonl",
                "kind": "battle_corrections",
                "schema_version": 1,
                "status": "complete",
                "totals": {
                    "bytes": sum(len(value) for value in streams.values()),
                    "files": 3,
                    "records": 3,
                },
            }
        )
    )
    return root


def test_loader_authenticates_and_decodes_correction_examples(tmp_path: Path) -> None:
    root = _artifact(tmp_path)

    dataset = load_battle_correction_artifact(root)

    assert dataset.artifact_id == root.name
    assert dataset.source_model_sha256 == "a" * 64
    assert dataset.reason_counts == (("teacher_disagreement", 1),)
    assert dataset.game_complete is True
    assert dataset.rollout_status == "game_complete"
    assert len(dataset.examples) == 1
    example = dataset.examples[0]
    assert example.features.slot_indices == (0, 2)
    assert example.chosen_candidate_index == 0
    assert example.policy_context is not None
    assert example.policy_context.goal == "win"


def test_loader_rejects_tampered_correction_stream(tmp_path: Path) -> None:
    root = _artifact(tmp_path)
    target = root / "corrections.jsonl"
    target.write_bytes(target.read_bytes() + b" ")

    with pytest.raises(BattleCorrectionError, match="authentication"):
        load_battle_correction_artifact(root)


def test_loader_admits_authenticated_failed_learner_rollout(tmp_path: Path) -> None:
    complete = _artifact(tmp_path)
    manifest_path = complete / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    (complete / "summary.jsonl").unlink()
    manifest["files"] = [
        entry for entry in manifest["files"] if entry["filename"] != "summary.jsonl"
    ]
    manifest["status"] = "failed"
    manifest["reason_code"] = "unhandled_exception"
    manifest["totals"]["files"] = 2
    manifest["totals"]["records"] = 2
    manifest["totals"]["bytes"] = sum(entry["bytes"] for entry in manifest["files"])
    manifest_path.write_bytes(_line(manifest))
    failed = complete.with_name(f"{complete.name}.failed.partial")
    complete.rename(failed)

    dataset = load_battle_correction_artifact(failed)

    assert dataset.game_complete is False
    assert dataset.rollout_status == "learner_failure"
    assert len(dataset.examples) == 1
