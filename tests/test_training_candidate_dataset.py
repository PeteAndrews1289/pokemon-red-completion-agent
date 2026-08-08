from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pokemon_red_completion.training_candidate_dataset import (
    TrainingCandidateDatasetError,
    audit_training_candidate_partitions,
    load_training_candidate_replay,
)
from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TRAINING_CANDIDATE_FEATURE_SCHEMA_ID,
    TrainingCandidate,
    TrainingCandidateDecision,
    TrainingCandidateSet,
    TrainingChoiceKind,
)


def _decision(index: int, kind: TrainingChoiceKind) -> dict[str, object]:
    rows = []
    for candidate_index in range(2):
        features = [0.0] * len(TRAINING_CANDIDATE_FEATURE_NAMES)
        features[0] = float(kind is TrainingChoiceKind.TRAINEE)
        features[candidate_index + 1] = 0.5
        rows.append(TrainingCandidate(candidate_index, tuple(features)))
    observation = TrainingCandidateSet(kind, tuple(rows))
    return TrainingCandidateDecision(index, 1, observation, "synthetic").public_dict()


def _write_replay(
    path: Path,
    *,
    lineage: str,
    partition: str,
    state: str,
    source: str = "a" * 40,
    dirty: bool = False,
) -> str:
    payload = {
        "schema": "pokemon-training-candidate-replay-v1",
        "status": "ok",
        "feature_schema_id": TRAINING_CANDIDATE_FEATURE_SCHEMA_ID,
        "feature_names": list(TRAINING_CANDIDATE_FEATURE_NAMES),
        "error": None,
        "provenance": {
            "lineage_id": lineage,
            "partition": partition,
            "source_commit": source,
            "source_dirty": dirty,
            "state_sha256": state * 64,
        },
        "segments": {
            "evolution": [_decision(0, TrainingChoiceKind.VENUE)],
            "balance": [_decision(0, TrainingChoiceKind.TRAINEE)],
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_loader_authenticates_and_summarizes_a_complete_lineage(tmp_path: Path) -> None:
    replay = tmp_path / "train.json"
    digest = _write_replay(
        replay,
        lineage="candidate-train-one",
        partition="train",
        state="1",
    )

    dataset = load_training_candidate_replay(replay, expected_sha256=digest)

    assert dataset.lineage_qualified
    assert dataset.choice_kinds == frozenset({"trainee", "venue"})
    summary = dataset.public_summary()
    assert summary["examples"] == 2
    assert summary["multi_candidate_decisions"] == 2
    assert summary["choice_kind_counts"] == {"trainee": 1, "venue": 1}


def test_loader_rejects_a_changed_candidate_artifact(tmp_path: Path) -> None:
    replay = tmp_path / "train.json"
    digest = _write_replay(
        replay,
        lineage="candidate-train-one",
        partition="train",
        state="1",
    )
    replay.write_text(replay.read_text() + " ")

    with pytest.raises(TrainingCandidateDatasetError, match="authentication"):
        load_training_candidate_replay(replay, expected_sha256=digest)


def test_partition_audit_requires_disjoint_roots_and_one_source(tmp_path: Path) -> None:
    paths = [tmp_path / name for name in ("train-one.json", "train-two.json", "validation.json")]
    specs = (
        ("candidate-train-one", "train", "1", "a" * 40),
        ("candidate-train-two", "train", "2", "a" * 40),
        ("candidate-validation", "validation", "3", "a" * 40),
    )
    datasets = []
    for path, (lineage, partition, state, source) in zip(paths, specs, strict=True):
        digest = _write_replay(
            path,
            lineage=lineage,
            partition=partition,
            state=state,
            source=source,
        )
        datasets.append(load_training_candidate_replay(path, expected_sha256=digest))

    audit = audit_training_candidate_partitions(datasets)

    assert audit.promotion_eligible
    assert audit.reasons == ()
    assert audit.state_overlap_count == 0

    validation_digest = _write_replay(
        paths[-1],
        lineage="candidate-validation",
        partition="validation",
        state="1",
        source="b" * 40,
    )
    datasets[-1] = load_training_candidate_replay(
        paths[-1], expected_sha256=validation_digest
    )
    rejected = audit_training_candidate_partitions(datasets)
    assert not rejected.promotion_eligible
    assert "duplicate_root_state" in rejected.reasons
    assert "state_overlap_across_partitions" in rejected.reasons
    assert "mixed_source_commit" in rejected.reasons
