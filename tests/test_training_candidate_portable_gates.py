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


def _run_gate(tmp_path: Path, *, disagreements: int = 4) -> subprocess.CompletedProcess[str]:
    model = tmp_path / "model.json"
    model.write_text("{}\n")
    model_sha = hashlib.sha256(model.read_bytes()).hexdigest()
    runtime = tmp_path / "runtime.json"
    runtime_sha = _write_json(
        runtime,
        {
            "schema": "pokemon-training-candidate-runtime-receipt-v1",
            "status": "runtime_qualified",
            "candidate_model_file_sha256": model_sha,
            "candidate_model_canonical_sha256": "c" * 64,
            "portable_training_loop_may_start": True,
        },
    )
    plan = tmp_path / "plan.json"
    plan_sha = _write_json(
        plan,
        {
            "schema": "pokemon-training-candidate-portable-plan-v1",
            "runtime_qualification_receipt_sha256": runtime_sha,
            "root": {
                "state_sha256": "a" * 64,
                "checkpoint_id": "portable_loop_obtain_secret_key_terminal",
            },
            "models": {
                "training_candidate": {
                    "model_file_sha256": model_sha,
                    "canonical_model_sha256": "c" * 64,
                }
            },
        },
    )
    portable = tmp_path / "portable.json"
    portable_sha = _write_json(
        portable,
        {
            "schema": "pokemon-model-selected-objective-execution-v3",
            "status": "ok",
            "source": {"git_commit": "b" * 40, "worktree_dirty": False},
            "capture": {
                "state_sha256": "a" * 64,
                "checkpoint_id": "portable_loop_obtain_secret_key_terminal",
            },
            "before": {"available_objectives": ["defeat_blaine"]},
            "after": {
                "completed_objectives": ["defeat_blaine"],
                "facts_added": ["badge:volcano"],
                "available_objectives": ["defeat_giovanni"],
            },
            "decisions_and_executions": [
                {
                    "objective_id": "defeat_blaine",
                    "kind": "skill_completed",
                    "skill_evidence": {
                        "objective": "defeat_blaine",
                        "status": "ok",
                        "team_development": {
                            "final_forms_complete": True,
                            "levels": [60, 55, 55, 55, 55, 55],
                            "battles": 1803,
                            "healing_trips": 1048,
                        },
                        "terminal": {
                            "party_hp": [10, 11, 12, 13, 14, 15],
                            "party_max_hp": [10, 11, 12, 13, 14, 15],
                            "party_status": [0, 0, 0, 0, 0, 0],
                        },
                    },
                }
            ],
            "assistance": {
                "teacher_fallbacks": 0,
                "expected_route_label_provided": False,
                "mechanic_execution": "teacher_authored_bounded_skill",
                "branching_model_decisions": 0,
                "singleton_dispatches": 1,
            },
            "training_candidate_control": {
                "model_file_sha256": model_sha,
                "model_sha256": "c" * 64,
                "authority_choice_kinds": ["trainee", "venue"],
                "model_had_execution_authority": True,
                "teacher_fallback_on_model_disagreement": False,
                "controlled_decisions": 120,
                "decisions": 120,
                "disagreements": disagreements,
                "genuine_accuracy": 0.99,
            },
        },
    )
    state = tmp_path / "terminal.state"
    state.write_bytes(b"private state")
    state_sha = hashlib.sha256(state.read_bytes()).hexdigest()
    envelope = tmp_path / "terminal.state.json"
    envelope_sha = _write_json(
        envelope,
        {
            "schema": "pokemon-private-captured-progress-v1",
            "state_sha256": state_sha,
            "checkpoint_id": "portable_loop_defeat_blaine_terminal",
            "verified_objective_ids": ["defeat_blaine"],
        },
    )
    return subprocess.run(
        [
            sys.executable,
            "scripts/check_training_candidate_portable_gates.py",
            "--plan",
            str(plan),
            plan_sha,
            "--runtime",
            str(runtime),
            runtime_sha,
            "--model",
            str(model),
            model_sha,
            "--portable",
            str(portable),
            portable_sha,
            "--state",
            str(state),
            "--envelope",
            str(envelope),
            envelope_sha,
            "--out",
            str(tmp_path / "gate.json"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_candidate_portable_gate_accepts_causal_objective_integration(tmp_path: Path) -> None:
    completed = _run_gate(tmp_path)

    assert completed.returncode == 0
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["portable_strategic_authority_eligible"] is True
    assert payload["checks"]["live_candidate_authority"]["passed"] is True
    assert payload["promotion_eligible"] is False


def test_candidate_portable_gate_rejects_agreement_only_run(tmp_path: Path) -> None:
    rejected = _run_gate(tmp_path, disagreements=0)

    assert rejected.returncode == 2
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["portable_strategic_authority_eligible"] is False
    assert payload["checks"]["live_candidate_authority"]["passed"] is False
