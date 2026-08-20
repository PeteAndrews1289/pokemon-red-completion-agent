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


def _write_replay(
    path: Path,
    *,
    add_identity: bool = False,
    lineage: str = "diagnostic-one",
    partition: str = "unassigned",
    state: str = "b",
) -> str:
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
            "lineage_id": lineage,
            "partition": partition,
            "source_commit": "a" * 40,
            "source_dirty": False,
            "state_sha256": state * 64,
        },
        "outcome": {
            "final_party_levels": [55, 55, 55, 55, 55, 55],
            "final_fainted_count": 0,
        },
        "sampling": {
            "evolution": {
                "method": "retain_first_and_per_kind_state_transitions",
                "observed_decisions": 1,
                "retained_decisions": 1,
                "consecutive_duplicate_decisions_removed": 0,
            },
            "balance": {
                "method": "retain_first_and_per_kind_state_transitions",
                "observed_decisions": 5,
                "retained_decisions": 2,
                "consecutive_duplicate_decisions_removed": 3,
            },
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
    assert payload["genuine_shape_only_majority_accuracy"] == 2 / 3
    assert payload["observed_decisions"] == 6
    assert payload["retained_decisions"] == 3
    assert payload["final_party_levels"] == [55, 55, 55, 55, 55, 55]
    assert payload["variable_choice_shapes"] == ["trainee/3"]
    assert payload["state_dependent_choice_demonstrated"] is True
    assert payload["promotion_eligible"] is False


def test_choice_audit_rejects_candidate_identity_fields(tmp_path: Path) -> None:
    rejected = _run_audit(tmp_path, add_identity=True)

    assert rejected.returncode == 2
    assert "unexpected field" in rejected.stderr


def test_selection_stays_training_only_then_fit_opens_validation(tmp_path: Path) -> None:
    train_one = tmp_path / "train-one.json"
    train_two = tmp_path / "train-two.json"
    validation = tmp_path / "validation.json"
    train_one_sha = _write_replay(
        train_one, lineage="train-one", partition="train", state="1"
    )
    train_two_sha = _write_replay(
        train_two, lineage="train-two", partition="train", state="2"
    )
    validation_sha = _write_replay(
        validation, lineage="validation-one", partition="validation", state="3"
    )
    selection = tmp_path / "selection.json"
    selected = subprocess.run(
        [
            sys.executable,
            "scripts/select_training_candidate_model.py",
            "--train",
            str(train_one),
            train_one_sha,
            "--train",
            str(train_two),
            train_two_sha,
            "--out",
            str(selection),
            "--epochs",
            "2",
            "--kind-balance-power",
            "0",
            "--kind-balance-power",
            "1",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert selected.returncode == 0, selected.stderr
    selection_payload = json.loads(selection.read_text())
    assert selection_payload["validation_opened"] is False
    assert len(selection_payload["trials"]) == 2
    assert "mean_genuine_accuracy" in selection_payload["trials"][0]

    model = tmp_path / "model.json"
    summary = tmp_path / "summary.json"
    fitted = subprocess.run(
        [
            sys.executable,
            "scripts/fit_training_candidate.py",
            "--train",
            str(train_one),
            train_one_sha,
            "--train",
            str(train_two),
            train_two_sha,
            "--validation",
            str(validation),
            validation_sha,
            "--out-model",
            str(model),
            "--out-summary",
            str(summary),
            "--epochs",
            "2",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert fitted.returncode == 0, fitted.stderr
    summary_payload = json.loads(summary.read_text())
    assert summary_payload["validation_opened"] is True
    assert summary_payload["partition_audit"]["promotion_eligible"] is True
    assert summary_payload["validation_lineages"] == ["validation-one"]
    assert "genuine_accuracy" in summary_payload["validation"]
    assert hashlib.sha256(model.read_bytes()).hexdigest() == summary_payload[
        "private_model_file_sha256"
    ]
