from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from pokemon_red_completion.training_control import (
    TRAINING_CONTROL_FEATURE_NAMES,
    TRAINING_CONTROL_FEATURE_SCHEMA_ID,
    TrainingControlAction,
    TrainingControlDecision,
    TrainingControlObservation,
    TrainingControlPhase,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_lineage(path: Path, lineage: str, partition: str, state: str) -> str:
    actions = tuple(TrainingControlAction)
    rows = []
    for index, action in enumerate(actions):
        battle = action in {TrainingControlAction.FIGHT, TrainingControlAction.FLEE}
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
        values[index + 1] = 0.5
        observation = TrainingControlObservation(
            TrainingControlPhase.BATTLE if battle else TrainingControlPhase.OVERWORLD,
            tuple(values),
            candidates,
        )
        rows.append(TrainingControlDecision(index, action, observation, "synthetic").public_dict())
    payload = {
        "schema": "pokemon-training-control-replay-v2",
        "status": "ok",
        "feature_schema_id": TRAINING_CONTROL_FEATURE_SCHEMA_ID,
        "feature_names": list(TRAINING_CONTROL_FEATURE_NAMES),
        "error": None,
        "provenance": {
            "lineage_id": lineage,
            "partition": partition,
            "source_commit": "a" * 40,
            "source_dirty": False,
            "state_sha256": state * 64,
        },
        "segments": {"evolution": [], "balance": rows},
    }
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def test_selection_and_fit_scripts_keep_validation_in_its_own_stage(tmp_path: Path) -> None:
    train_one = tmp_path / "train-one.json"
    train_two = tmp_path / "train-two.json"
    validation = tmp_path / "validation.json"
    train_one_sha = _write_lineage(train_one, "train-one", "train", "1")
    train_two_sha = _write_lineage(train_two, "train-two", "train", "2")
    validation_sha = _write_lineage(validation, "validation-one", "validation", "3")
    selection = tmp_path / "selection.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/select_training_control_balance.py",
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
            "--class-balance-power",
            "0",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    selection_payload = json.loads(selection.read_text())
    assert selection_payload["validation_opened"] is False
    assert selection_payload["selected_class_balance_power"] == 0.0

    model = tmp_path / "model.json"
    summary = tmp_path / "summary.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/fit_training_control.py",
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
            "--class-balance-power",
            "0",
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    summary_payload = json.loads(summary.read_text())
    assert summary_payload["validation_lineages"] == ["validation-one"]
    assert summary_payload["partition_audit"]["promotion_eligible"] is True
    assert hashlib.sha256(model.read_bytes()).hexdigest() == summary_payload[
        "private_model_file_sha256"
    ]
