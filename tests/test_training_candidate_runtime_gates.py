from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> str:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance(
    lineage_id: str, state_sha256: str, *, source_commit: str = "a" * 40
) -> dict[str, object]:
    return {
        "lineage_id": lineage_id,
        "partition": "unassigned",
        "source_commit": source_commit,
        "source_dirty": False,
        "state_sha256": state_sha256,
    }


def _run_gate(
    tmp_path: Path, *, disagreements: int
) -> subprocess.CompletedProcess[str]:
    model = tmp_path / "model.json"
    model.write_text("candidate-model")
    model_sha = hashlib.sha256(model.read_bytes()).hexdigest()
    offline_plan_sha = "9" * 64
    shadow_root = "1" * 64
    control_root = "2" * 64
    plan = tmp_path / "plan.json"
    plan_sha = _write_json(
        plan,
        {
            "schema": "pokemon-training-candidate-runtime-promotion-plan-v1",
            "offline_promotion_plan_sha256": offline_plan_sha,
            "required_offline_gate": {
                "offline_candidate_eligible": True,
                "shadow_may_start": True,
            },
            "lineages": {
                "shadow": {"lineage_id": "shadow-one", "root_sha256": shadow_root},
                "causal_control": {
                    "lineage_id": "control-one",
                    "root_sha256": control_root,
                },
            },
            "shadow_gates": {
                "required_status": "ok",
                "model_had_execution_authority": False,
                "required_choice_kinds": ["trainee", "venue"],
                "minimum_genuine_multi_candidate_decisions": 100,
                "minimum_genuine_accuracy": 0.9,
                "minimum_genuine_per_kind_accuracy": 0.85,
                "maximum_faints": 0,
                "required_final_party_levels": [55, 55, 55, 55, 55, 55],
            },
            "causal_gates": {
                "required_status": "ok",
                "authority_choice_kinds": ["trainee", "venue"],
                "teacher_fallback_on_model_disagreement": False,
                "minimum_controlled_genuine_decisions": 100,
                "minimum_model_teacher_disagreements": 1,
                "maximum_candidate_decisions": 1000,
                "maximum_battles": 1900,
                "maximum_healing_trips": 1150,
                "maximum_faints": 0,
                "required_final_party_levels": [55, 55, 55, 55, 55, 55],
            },
        },
    )
    offline = tmp_path / "offline.json"
    offline_sha = _write_json(
        offline,
        {
            "schema": "pokemon-training-candidate-offline-gate-evaluation-v1",
            "promotion_plan_sha256": offline_plan_sha,
            "candidate_model_file_sha256": model_sha,
            "offline_candidate_eligible": True,
            "shadow_may_start": True,
        },
    )

    def write_runtime(stem: str, lineage_id: str, root: str, *, authority: bool) -> tuple[str, str]:
        replay = tmp_path / f"{stem}-replay.json"
        provenance = _provenance(
            lineage_id,
            root,
            source_commit=("b" * 40 if authority else "a" * 40),
        )
        replay_sha = _write_json(
            replay,
            {
                "schema": "pokemon-training-candidate-replay-v1",
                "status": "ok",
                "error": None,
                "provenance": provenance,
                "outcome": {
                    "final_party_levels": [55, 55, 55, 55, 55, 55],
                    "final_fainted_count": 0,
                },
            },
        )
        audit = tmp_path / f"{stem}-audit.json"
        audit_sha = _write_json(
            audit,
            {
                "schema": "pokemon-training-candidate-runtime-audit-v1",
                "status": "ok",
                "error": None,
                "provenance": provenance,
                "model_artifact_sha256": model_sha,
                "candidate_replay_sha256": replay_sha,
                "model_had_execution_authority": authority,
                "authority_choice_kinds": ["trainee", "venue"] if authority else [],
                "teacher_fallback_on_model_disagreement": False if authority else None,
                "decisions": 200,
                "agreements": 200 - (disagreements if authority else 10),
                "disagreements": disagreements if authority else 10,
                "genuine_decisions": 180,
                "genuine_accuracy": 0.95,
                "genuine_kind_accuracy": {"trainee": 0.9, "venue": 1.0},
                "outcome": {
                    "final_party_levels": [55, 55, 55, 55, 55, 55],
                    "final_fainted_count": 0,
                },
                "execution": {
                    "total_battles": 1800,
                    "total_healing_trips": 1000,
                },
            },
        )
        return replay_sha, audit_sha

    shadow_replay_sha, shadow_audit_sha = write_runtime(
        "shadow", "shadow-one", shadow_root, authority=False
    )
    control_replay_sha, control_audit_sha = write_runtime(
        "control", "control-one", control_root, authority=True
    )
    return subprocess.run(
        [
            sys.executable,
            "scripts/check_training_candidate_runtime_gates.py",
            "--plan",
            str(plan),
            plan_sha,
            "--offline",
            str(offline),
            offline_sha,
            "--model",
            str(model),
            model_sha,
            "--shadow",
            str(tmp_path / "shadow-audit.json"),
            shadow_audit_sha,
            "--shadow-replay",
            str(tmp_path / "shadow-replay.json"),
            shadow_replay_sha,
            "--control",
            str(tmp_path / "control-audit.json"),
            control_audit_sha,
            "--control-replay",
            str(tmp_path / "control-replay.json"),
            control_replay_sha,
            "--out",
            str(tmp_path / "gate.json"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_runtime_gate_authenticates_shadow_and_causal_authority(tmp_path: Path) -> None:
    completed = _run_gate(tmp_path, disagreements=2)

    assert completed.returncode == 0, completed.stderr
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["shadow_eligible"] is True
    assert payload["causal_control_eligible"] is True
    assert payload["portable_training_loop_may_start"] is True


def test_runtime_gate_rejects_control_that_never_disagreed(tmp_path: Path) -> None:
    rejected = _run_gate(tmp_path, disagreements=0)

    assert rejected.returncode == 2, rejected.stderr
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["shadow_eligible"] is True
    assert payload["causal_control_eligible"] is False
    assert payload["causal_checks"]["model_teacher_disagreements"]["passed"] is False
