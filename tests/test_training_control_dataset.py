from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pokemon_red_completion.training_control import (
    TRAINING_CONTROL_FEATURE_NAMES,
    TRAINING_CONTROL_FEATURE_SCHEMA_ID,
    TrainingControlAction,
    TrainingControlDecision,
    TrainingControlObservation,
    TrainingControlPhase,
)
from pokemon_red_completion.training_control_dataset import (
    TrainingControlDatasetError,
    audit_training_control_partitions,
    load_training_control_replay,
)


def _observation(action: TrainingControlAction) -> TrainingControlObservation:
    battle = action in {TrainingControlAction.FIGHT, TrainingControlAction.FLEE}
    phase = TrainingControlPhase.BATTLE if battle else TrainingControlPhase.OVERWORLD
    candidates = (
        (TrainingControlAction.FIGHT, TrainingControlAction.FLEE)
        if battle
        else (
            TrainingControlAction.SEEK,
            TrainingControlAction.HEAL,
            TrainingControlAction.STOP,
        )
    )
    values = [0.0] * len(TRAINING_CONTROL_FEATURE_NAMES)
    values[0] = float(battle)
    return TrainingControlObservation(phase, tuple(values), candidates)


def _payload(
    *,
    status: str = "ok",
    dirty: bool = False,
    partition: str = "train",
    state_sha256: str = "b" * 64,
) -> dict[str, object]:
    actions = (
        TrainingControlAction.SEEK,
        TrainingControlAction.FIGHT,
        TrainingControlAction.FLEE,
        TrainingControlAction.HEAL,
        TrainingControlAction.STOP,
    )
    rows = [
        TrainingControlDecision(index, action, _observation(action), f"reason {action}")
        .public_dict()
        for index, action in enumerate(actions)
    ]
    if status == "failed":
        rows = rows[:-1]
    return {
        "schema": "pokemon-training-control-replay-v2",
        "status": status,
        "feature_schema_id": TRAINING_CONTROL_FEATURE_SCHEMA_ID,
        "feature_names": list(TRAINING_CONTROL_FEATURE_NAMES),
        "error": "bounded rehearsal failed" if status == "failed" else None,
        "provenance": {
            "lineage_id": "training-root-01",
            "partition": partition,
            "source_commit": "a" * 40,
            "source_dirty": dirty,
            "state_sha256": state_sha256,
        },
        "segments": {"evolution": [], "balance": rows},
    }


def _write(path: Path, payload: dict[str, object]) -> str:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def test_loader_authenticates_a_complete_whole_lineage(tmp_path: Path) -> None:
    path = tmp_path / "lineage.json"
    digest = _write(path, _payload())

    dataset = load_training_control_replay(path, expected_sha256=digest)

    assert dataset.lineage_qualified
    assert dataset.partition == "train"
    assert [example.action.value for example in dataset.examples] == [
        "seek",
        "fight",
        "flee",
        "heal",
        "stop",
    ]
    assert dataset.public_summary()["action_counts"] == {
        "fight": 1,
        "flee": 1,
        "heal": 1,
        "seek": 1,
        "stop": 1,
    }
    assert dataset.public_summary()["promotion_eligible"] is False


def test_loader_rejects_digest_or_terminal_tampering(tmp_path: Path) -> None:
    path = tmp_path / "lineage.json"
    payload = _payload()
    digest = _write(path, payload)

    with pytest.raises(TrainingControlDatasetError, match="authentication"):
        load_training_control_replay(path, expected_sha256="f" * 64)

    payload["segments"]["balance"].pop()  # type: ignore[index,union-attr]
    changed = _write(path, payload)
    assert changed != digest
    with pytest.raises(TrainingControlDatasetError, match="terminal balance stop"):
        load_training_control_replay(path, expected_sha256=changed)


def test_failed_and_dirty_lineages_remain_inspectable_but_unqualified(tmp_path: Path) -> None:
    failed_path = tmp_path / "failed.json"
    failed = load_training_control_replay(
        failed_path,
        expected_sha256=_write(failed_path, _payload(status="failed")),
    )
    dirty_path = tmp_path / "dirty.json"
    dirty = load_training_control_replay(
        dirty_path,
        expected_sha256=_write(dirty_path, _payload(dirty=True)),
    )

    assert failed.status == "failed" and not failed.lineage_qualified
    assert dirty.status == "ok" and not dirty.lineage_qualified


def test_partition_audit_detects_state_leakage_and_missing_classes(tmp_path: Path) -> None:
    train_path = tmp_path / "train.json"
    train = load_training_control_replay(
        train_path,
        expected_sha256=_write(train_path, _payload(partition="train")),
    )
    validation_path = tmp_path / "validation.json"
    validation_payload = _payload(partition="validation")
    validation_payload["provenance"]["lineage_id"] = "training-root-02"  # type: ignore[index]
    validation = load_training_control_replay(
        validation_path,
        expected_sha256=_write(validation_path, validation_payload),
    )

    leaked = audit_training_control_partitions((train, validation))

    assert not leaked.promotion_eligible
    assert leaked.state_overlap_count == 1
    assert "state_overlap_across_partitions" in leaked.reasons

    clean_validation = replace(
        validation,
        state_sha256="c" * 64,
        examples=tuple(
            example
            for example in validation.examples
            if example.action is TrainingControlAction.STOP
        ),
    )
    clean = audit_training_control_partitions((train, clean_validation))
    assert clean.promotion_eligible
    assert clean.state_overlap_count == 0


def test_partition_audit_requires_validation_classes_to_exist_in_training(
    tmp_path: Path,
) -> None:
    train_path = tmp_path / "train.json"
    train = load_training_control_replay(
        train_path,
        expected_sha256=_write(train_path, _payload(partition="train")),
    )
    train = replace(
        train,
        examples=tuple(
            example
            for example in train.examples
            if example.action is not TrainingControlAction.FLEE
        ),
    )
    validation_path = tmp_path / "validation.json"
    validation_payload = _payload(partition="validation", state_sha256="c" * 64)
    validation_payload["provenance"]["lineage_id"] = "training-root-02"  # type: ignore[index]
    validation = load_training_control_replay(
        validation_path,
        expected_sha256=_write(validation_path, validation_payload),
    )

    audit = audit_training_control_partitions((train, validation))

    assert not audit.promotion_eligible
    assert audit.validation_classes_missing_from_training == ("flee",)
