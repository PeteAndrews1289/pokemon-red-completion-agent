from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from pokemon_red_completion.training_candidate_rank import (
    TRAINING_CANDIDATE_FEATURE_NAMES,
    TRAINING_CANDIDATE_FEATURE_SCHEMA_ID,
    TrainingCandidate,
    TrainingCandidateDecision,
    TrainingCandidateSet,
    TrainingChoiceKind,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _decision(
    index: int,
    kind: TrainingChoiceKind,
    candidate_count: int,
    selected: int,
) -> dict[str, object]:
    candidates = []
    for candidate_index in range(candidate_count):
        features = [0.0] * len(TRAINING_CANDIDATE_FEATURE_NAMES)
        features[0] = float(kind is TrainingChoiceKind.TRAINEE)
        features[1] = candidate_index / max(1, candidate_count)
        candidates.append(TrainingCandidate(candidate_index, tuple(features)))
    observation = TrainingCandidateSet(kind, tuple(candidates))
    return TrainingCandidateDecision(index, selected, observation, "synthetic").public_dict()


def _write_replay(path: Path, *, add_identity: bool = False) -> str:
    evolution = [_decision(0, TrainingChoiceKind.VENUE, 2, 1)]
    balance = [
        _decision(0, TrainingChoiceKind.TRAINEE, 3, 0),
        _decision(1, TrainingChoiceKind.TRAINEE, 3, 1),
    ]
    if add_identity:
        candidate = balance[0]["observation"]["candidates"][0]  # type: ignore[index]
        candidate["species_id"] = 25  # type: ignore[index]
    payload = {
        "schema": "pokemon-training-candidate-replay-v1",
        "status": "ok",
        "feature_schema_id": TRAINING_CANDIDATE_FEATURE_SCHEMA_ID,
        "feature_names": list(TRAINING_CANDIDATE_FEATURE_NAMES),
        "error": None,
        "provenance": {
            "lineage_id": "diagnostic-one",
            "partition": "unassigned",
            "source_commit": "a" * 40,
            "source_dirty": False,
            "state_sha256": "b" * 64,
        },
        "segments": {"evolution": evolution, "balance": balance},
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_audit(tmp_path: Path, *, add_identity: bool = False) -> subprocess.CompletedProcess[str]:
    replay = tmp_path / "replay.json"
    replay_sha = _write_replay(replay, add_identity=add_identity)
    return subprocess.run(
        [
            sys.executable,
            "scripts/audit_training_candidate_choices.py",
            "--replay",
            str(replay),
            replay_sha,
            "--out",
            str(tmp_path / "audit.json"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_choice_audit_detects_labels_that_choice_shape_cannot_determine(
    tmp_path: Path,
) -> None:
    completed = _run_audit(tmp_path)

    assert completed.returncode == 0
    payload = json.loads((tmp_path / "audit.json").read_text())
    assert payload["decisions"] == 3
    assert payload["shape_only_majority_accuracy"] == 2 / 3
    assert payload["variable_choice_shapes"] == ["trainee/3"]
    assert payload["state_dependent_choice_demonstrated"] is True
    assert payload["promotion_eligible"] is False


def test_choice_audit_rejects_candidate_identity_fields(tmp_path: Path) -> None:
    rejected = _run_audit(tmp_path, add_identity=True)

    assert rejected.returncode == 2
    assert "unexpected identity" in rejected.stderr
