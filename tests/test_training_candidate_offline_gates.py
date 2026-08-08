from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = "a" * 40


def _write(path: Path, payload: object) -> str:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_gate(
    tmp_path: Path,
    *,
    validation_shape_accuracy: float = 0.5,
    validation_opened_during_selection: bool = False,
) -> subprocess.CompletedProcess[str]:
    identities = {
        "train-one": ("train", "1" * 64, "4" * 64),
        "train-two": ("train", "2" * 64, "5" * 64),
        "validation-one": ("validation", "3" * 64, "6" * 64),
    }
    plan = tmp_path / "plan.json"
    plan_sha = _write(
        plan,
        {
            "schema": "pokemon-training-candidate-promotion-plan-v1",
            "source_commit": SOURCE,
            "lineages": {
                "training": [
                    {"lineage_id": name, "root_sha256": root}
                    for name, (partition, root, _artifact) in identities.items()
                    if partition == "train"
                ],
                "sealed_validation": {
                    "lineage_id": "validation-one",
                    "root_sha256": identities["validation-one"][1],
                },
            },
            "collection_gates": {
                "required_status": "ok",
                "maximum_faints": 0,
                "required_final_party_levels": [55, 55, 55, 55, 55, 55],
                "required_choice_kinds": ["trainee", "venue"],
                "minimum_multi_candidate_decisions": 100,
                "sampling_method": "retain_first_and_per_kind_state_transitions",
                "identity_fields_present": False,
            },
            "offline_validation_gates": {
                "state_dependent_choice_demonstrated": True,
                "maximum_genuine_shape_only_majority_accuracy": 0.99,
                "minimum_genuine_heldout_model_margin_over_shape_baseline": 0.02,
                "minimum_genuine_heldout_accuracy": 0.9,
                "minimum_genuine_per_kind_accuracy": 0.85,
                "validation_opened_during_selection": False,
            },
        },
    )
    hyperparameters = {
        "hidden_units": 16,
        "epochs": 300,
        "learning_rate": 0.01,
        "l2": 0.0001,
        "seed": 20260808,
    }
    selection = tmp_path / "selection.json"
    selection_sha = _write(
        selection,
        {
            "schema": "pokemon-training-candidate-selection-v1",
            "training_lineages": [
                {
                    "lineage_id": name,
                    "artifact_sha256": artifact,
                    "state_sha256": root,
                    "source_commit": SOURCE,
                    "source_dirty": False,
                }
                for name, (partition, root, artifact) in identities.items()
                if partition == "train"
            ],
            "validation_opened": validation_opened_during_selection,
            "hyperparameters": hyperparameters,
            "selected_kind_balance_power": 0.5,
        },
    )
    model = tmp_path / "model.json"
    model.write_text("{}\n")
    model_sha = hashlib.sha256(model.read_bytes()).hexdigest()
    summary = tmp_path / "summary.json"
    summary_sha = _write(
        summary,
        {
            "schema": "pokemon-training-candidate-model-summary-v1",
            "private_model_file_sha256": model_sha,
            "lineage_roots": [
                {
                    "lineage_id": name,
                    "partition": partition,
                    "state_sha256": root,
                    "artifact_sha256": artifact,
                    "source_commit": SOURCE,
                    "source_dirty": False,
                }
                for name, (partition, root, artifact) in identities.items()
            ],
            "partition_audit": {"promotion_eligible": True},
            "hyperparameters": {**hyperparameters, "kind_balance_power": 0.5},
            "validation": {
                "genuine_accuracy": 0.96,
                "genuine_shape_baseline_accuracy": 0.5,
                "genuine_kind_accuracy": {"trainee": 0.95, "venue": 0.97},
            },
            "validation_opened": True,
        },
    )
    audit_args: list[str] = []
    for name, (partition, root, artifact) in identities.items():
        audit = tmp_path / f"{name}-audit.json"
        audit_sha = _write(
            audit,
            {
                "schema": "pokemon-training-candidate-choice-audit-v1",
                "replay_sha256": artifact,
                "provenance": {
                    "lineage_id": name,
                    "partition": partition,
                    "state_sha256": root,
                    "source_commit": SOURCE,
                    "source_dirty": False,
                },
                "status": "ok",
                "lineage_qualified": True,
                "final_party_levels": [55, 55, 55, 55, 55, 55],
                "final_fainted_count": 0,
                "kind_counts": {"trainee": 60, "venue": 60},
                "multi_candidate_decisions": 120,
                "observed_decisions": 150,
                "retained_decisions": 120,
                "identity_fields_present": False,
                "genuine_shape_only_majority_accuracy": (
                    validation_shape_accuracy if partition == "validation" else 0.5
                ),
                "state_dependent_choice_demonstrated": (
                    validation_shape_accuracy < 1.0
                ),
            },
        )
        audit_args.extend(("--audit", str(audit), audit_sha))
    return subprocess.run(
        [
            sys.executable,
            "scripts/check_training_candidate_offline_gates.py",
            "--plan",
            str(plan),
            plan_sha,
            "--selection",
            str(selection),
            selection_sha,
            "--summary",
            str(summary),
            summary_sha,
            "--model",
            str(model),
            model_sha,
            *audit_args,
            "--out",
            str(tmp_path / "gate.json"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_offline_gate_authenticates_and_qualifies_genuine_choices(tmp_path: Path) -> None:
    completed = _run_gate(tmp_path)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["offline_candidate_eligible"] is True
    assert payload["shadow_may_start"] is True
    assert payload["causal_control_may_start"] is False
    assert payload["observed"]["genuine_model_margin"] == 0.45999999999999996


def test_offline_gate_rejects_shape_determined_validation(tmp_path: Path) -> None:
    rejected = _run_gate(tmp_path, validation_shape_accuracy=1.0)

    assert rejected.returncode == 2
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["offline_candidate_eligible"] is False
    assert payload["offline_validation_checks"]["state_dependent_choices"]["passed"] is False
    assert payload["offline_validation_checks"][
        "validation_shape_baseline_below_ceiling"
    ]["passed"] is False


def test_offline_gate_rejects_selection_that_opened_validation(tmp_path: Path) -> None:
    rejected = _run_gate(tmp_path, validation_opened_during_selection=True)

    assert rejected.returncode == 2
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["selection_checks"]["selection_declares_validation_closed"]["passed"] is False
    assert payload["offline_validation_checks"]["validation_closed_during_selection"][
        "passed"
    ] is False
