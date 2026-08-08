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


def _run_gate(
    tmp_path: Path, *, controlled_decisions: int = 25
) -> subprocess.CompletedProcess[str]:
    identity = {
        "lineage_id": "train-one",
        "partition": "train",
        "artifact_sha256": "1" * 64,
        "state_sha256": "2" * 64,
        "source_commit": "a" * 40,
        "source_dirty": False,
    }
    candidate = tmp_path / "candidate.json"
    candidate_sha = _write_json(
        candidate,
        {
            "schema": "pokemon-training-control-candidate-summary-v1",
            "model_sha256": "3" * 64,
            "private_model_file_sha256": "4" * 64,
            "lineage_roots": [identity],
            "validation": {"genuine_accuracy": 1.0},
        },
    )
    causal = tmp_path / "causal.json"
    causal_sha = _write_json(
        causal,
        {
            "schema": "pokemon-training-control-causal-gate-evaluation-v1",
            "candidate_summary_sha256": candidate_sha,
            "model_sha256": "3" * 64,
            "causal_control_eligible": True,
            "portable_loop_may_start": True,
        },
    )
    choice = tmp_path / "choice.json"
    choice_sha = _write_json(
        choice,
        {
            "schema": "pokemon-training-control-choice-diversity-audit-v1",
            "lineages": [identity],
            "validation_genuine_candidate_only_accuracy": 1.0,
            "candidate_only_baseline_saturates_validation": True,
            "state_dependent_choice_demonstrated": False,
        },
    )
    portable = tmp_path / "portable.json"
    portable_sha = _write_json(
        portable,
        {
            "schema": "pokemon-model-selected-objective-execution-v3",
            "status": "ok",
            "source": {"git_commit": "b" * 40, "worktree_dirty": False},
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
                        },
                    },
                }
            ],
            "assistance": {
                "teacher_fallbacks": 0,
                "expected_route_label_provided": False,
                "mechanic_execution": "teacher_authored_bounded_skill",
            },
            "training_control": {
                "model_sha256": "3" * 64,
                "model_file_sha256": "4" * 64,
                "authority_phases": ["battle", "overworld"],
                "model_had_execution_authority": controlled_decisions > 0,
                "teacher_fallback_on_model_disagreement": False,
                "controlled_decisions": controlled_decisions,
                "decisions": 25,
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
            "scripts/check_training_control_portable_gates.py",
            "--candidate",
            str(candidate),
            candidate_sha,
            "--causal",
            str(causal),
            causal_sha,
            "--choice",
            str(choice),
            choice_sha,
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


def test_portable_gate_separates_authority_from_feature_value(tmp_path: Path) -> None:
    completed = _run_gate(tmp_path)

    assert completed.returncode == 0
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["portable_authority_integration_eligible"] is True
    assert payload["state_dependent_policy_evidence_eligible"] is False
    assert payload["verified_claims"] == ["portable_captured_state_training_authority"]
    assert payload["unsupported_claims"] == ["state_dependent_training_policy"]
    assert payload["promotion_eligible"] is False


def test_portable_gate_fails_when_not_every_decision_was_model_controlled(
    tmp_path: Path,
) -> None:
    rejected = _run_gate(tmp_path, controlled_decisions=24)

    assert rejected.returncode == 2
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["portable_authority_integration_eligible"] is False
    assert payload["authority_integration_checks"]["full_training_authority"]["passed"] is False
