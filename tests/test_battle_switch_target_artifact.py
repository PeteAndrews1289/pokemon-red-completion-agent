from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from pokemon_red_completion.battle_switch_target import (
    SWITCH_TARGET_FEATURE_NAMES,
    SWITCH_TARGET_FEATURE_SCHEMA_ID,
)
from pokemon_red_completion.battle_switch_target_model import (
    BattleSwitchTargetMLP,
    BattleSwitchTargetModelError,
    canonical_switch_target_model_sha256,
    load_battle_switch_target_model_artifact,
)


def _model() -> BattleSwitchTargetMLP:
    return BattleSwitchTargetMLP(
        weights1=np.ones((len(SWITCH_TARGET_FEATURE_NAMES), 1)),
        bias1=np.zeros(1),
        weights2=np.ones(1),
        feature_mean=np.zeros(len(SWITCH_TARGET_FEATURE_NAMES)),
        feature_scale=np.ones(len(SWITCH_TARGET_FEATURE_NAMES)),
        training_seed=7,
    )


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _write_artifact(tmp_path: Path) -> Path:
    root = tmp_path / "red-battle-switch-target-model-test"
    root.mkdir(parents=True)
    model = _model()
    model_sha256 = canonical_switch_target_model_sha256(model)
    records = {
        "model.jsonl": {
            "record_type": "battle_switch_target_model",
            "model": model.to_dict(),
            "model_sha256": model_sha256,
        },
        "training.jsonl": {
            "record_type": "battle_switch_target_training",
            "feature_schema_id": SWITCH_TARGET_FEATURE_SCHEMA_ID,
            "training_artifacts": [{"artifact_id": "training-a", "manifest_sha256": "a" * 64}],
            "validation_artifacts": [{"artifact_id": "validation-b", "manifest_sha256": "b" * 64}],
        },
        "qualification.jsonl": {
            "record_type": "battle_switch_target_qualification",
            "model_sha256": model_sha256,
            "prospective_test": {
                "artifact_id": "test-c",
                "manifest_sha256": "c" * 64,
                "examples": 17,
                "correct": 17,
            },
            "shadow_authority": True,
            "causal_trial_authority": True,
            "deployment_authority": False,
        },
    }
    files = []
    for filename, record in records.items():
        payload = _canonical(record)
        (root / filename).write_bytes(payload)
        files.append(
            {
                "filename": filename,
                "bytes": len(payload),
                "records": 1,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "format": "pokemon-red-completion-private-artifact-jsonl",
        "kind": "battle_switch_target_model",
        "schema_version": 1,
        "status": "complete",
        "artifact_id": root.name,
        "files": files,
    }
    (root / "manifest.json").write_bytes(_canonical(manifest))
    return root


def test_loader_authenticates_model_lineages_and_prospective_gate(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path)

    artifact = load_battle_switch_target_model_artifact(root)

    assert artifact.model_sha256 == canonical_switch_target_model_sha256(_model())
    assert artifact.training_artifact_ids == ("training-a",)
    assert artifact.validation_artifact_ids == ("validation-b",)
    assert artifact.source_manifest_sha256s == ("a" * 64, "b" * 64)
    assert artifact.prospective_test_artifact_id == "test-c"
    assert artifact.prospective_test_examples == artifact.prospective_test_correct == 17
    assert artifact.shadow_authority is True
    assert artifact.causal_trial_authority is True
    assert artifact.deployment_authority is False


def test_loader_rejects_stream_tampering_and_undeclared_files(tmp_path: Path) -> None:
    root = _write_artifact(tmp_path)
    (root / "model.jsonl").write_bytes((root / "model.jsonl").read_bytes() + b"\n")

    with pytest.raises(BattleSwitchTargetModelError, match="authentication"):
        load_battle_switch_target_model_artifact(root)

    root = _write_artifact(tmp_path / "second")
    (root / "unexpected.txt").write_text("no", encoding="ascii")
    with pytest.raises(BattleSwitchTargetModelError, match="undeclared"):
        load_battle_switch_target_model_artifact(root)
