from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pokemon_red_completion.battle_correction_audit import (
    BattleCorrectionAuditError,
    audit_battle_correction_artifact,
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
    root = tmp_path / "red-player-audit-test.failed.partial"
    root.mkdir()
    metadata = _line(
        {
            "battle_confidence_threshold": 0.5,
            "battle_feature_schema_id": CURRENT_BATTLE_FEATURE_SCHEMA_ID,
            "battle_model_sha256": "b" * 64,
            "record_type": "red_player_v1_shadow_run",
            "schema_version": 1,
            "source": {"git_commit": "a" * 64, "worktree_dirty": False},
        }
    )
    rows = []
    for correction_index, decision_index, confidence, objective in (
        (1, 2, 0.4, "train_team"),
        (2, 5, 0.8, "train_team"),
    ):
        rows.append(
            _line(
                {
                    "battle_plan_id": "battle-test",
                    "correction_index": correction_index,
                    "decision_index": decision_index,
                    "features": {
                        "candidate_vectors": [
                            [0.0] * len(FEATURE_NAMES),
                            [0.1] * len(FEATURE_NAMES),
                        ],
                        "current_pp": [10.0, 9.0],
                        "feature_names": list(FEATURE_NAMES),
                        "feature_schema_id": CURRENT_BATTLE_FEATURE_SCHEMA_ID,
                        "legal_mask": [True, True],
                        "slot_indices": [0, 1],
                    },
                    "model": {
                        "confidence": confidence,
                        "predicted_candidate_index": 1,
                    },
                    "objective_id": objective,
                    "policy_context": {
                        "goal": "win",
                        "move_policy": "any_usable",
                        "required_move_ref": None,
                    },
                    "reason": "teacher_disagreement",
                    "record_type": "battle_policy_correction",
                    "schema_version": 1,
                    "teacher": {"chosen_candidate_index": 0},
                }
            )
        )
    streams = {
        "metadata.jsonl": metadata,
        "corrections.jsonl": b"".join(rows),
    }
    entries = []
    for filename, payload in streams.items():
        (root / filename).write_bytes(payload)
        entries.append(
            {
                "bytes": len(payload),
                "filename": filename,
                "records": len(payload.splitlines()),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    (root / "manifest.json").write_bytes(
        _line(
            {
                "artifact_id": "red-player-audit-test",
                "files": sorted(entries, key=lambda item: str(item["filename"])),
                "format": "pokemon-red-completion-private-artifact-jsonl",
                "kind": "battle_corrections",
                "reason_code": "unhandled_exception",
                "schema_version": 1,
                "status": "failed",
                "totals": {
                    "bytes": sum(len(payload) for payload in streams.values()),
                    "files": 2,
                    "records": 3,
                },
            }
        )
    )
    return root


def test_audit_is_path_free_and_does_not_overclaim_corrections(tmp_path: Path) -> None:
    audit = audit_battle_correction_artifact(
        _artifact(tmp_path),
        total_decisions=6,
        model_executions=3,
        teacher_fallbacks=2,
    )
    result = audit.public_dict()

    assert result["decision_accounting"] == {
        "total_decisions": 6,
        "model_executions": 3,
        "teacher_fallbacks": 2,
        "unclassified_decisions": 1,
        "classified_decisions": 5,
        "accounting_complete": False,
    }
    assert result["corrections"]["records"] == 2  # type: ignore[index]
    assert result["corrections"]["objective_counts"] == {"train_team": 2}  # type: ignore[index]
    assert result["confidence"]["corrections_below_threshold"] == 1  # type: ignore[index]
    assert result["confidence"]["agreement_discrimination_auc"] is None  # type: ignore[index]
    assert result["promotion_eligible"] is False
    assert result["refit_eligible"] is False
    assert str(tmp_path) not in json.dumps(result, sort_keys=True)


def test_audit_rejects_tampered_or_impossible_evidence(tmp_path: Path) -> None:
    root = _artifact(tmp_path)
    stream = root / "corrections.jsonl"
    stream.write_bytes(stream.read_bytes() + b" ")
    with pytest.raises(BattleCorrectionAuditError, match="authentication|canonical"):
        audit_battle_correction_artifact(
            root,
            total_decisions=6,
            model_executions=3,
            teacher_fallbacks=2,
        )

    with pytest.raises(BattleCorrectionAuditError, match="exceed total"):
        audit_battle_correction_artifact(
            root,
            total_decisions=4,
            model_executions=3,
            teacher_fallbacks=2,
        )
