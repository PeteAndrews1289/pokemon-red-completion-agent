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


def _write_text(path: Path, payload: str) -> str:
    path.write_text(payload)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance(lineage_id: str, state_sha256: str) -> dict[str, object]:
    return {
        "lineage_id": lineage_id,
        "partition": "unassigned",
        "source_commit": "a" * 40,
        "source_dirty": False,
        "state_sha256": state_sha256,
    }


def _run_gate(tmp_path: Path, *, maximum_decisions: int) -> subprocess.CompletedProcess[str]:
    model_sha256 = "3" * 64
    model_file_sha256 = "4" * 64
    shadow_root = "1" * 64
    control_root = "2" * 64
    plan = tmp_path / "plan.json"
    plan_sha = _write_json(
        plan,
        {
            "schema": "pokemon-training-control-promotion-plan-v2",
            "source_commit": "a" * 40,
            "lineages": {
                "shadow": {
                    "lineage_id": "shadow-one",
                    "root_sha256": shadow_root,
                },
                "causal_control": {
                    "lineage_id": "control-one",
                    "root_sha256": control_root,
                },
            },
            "causal_gates": {
                "authority_phases": ["battle", "overworld"],
                "teacher_fallback_on_model_disagreement": False,
                "maximum_decisions": maximum_decisions,
                "maximum_battles": 20,
                "maximum_healing_trips": 10,
                "maximum_faints": 0,
                "required_final_party_levels": [55, 55, 55, 55, 55, 55],
            },
        },
    )
    candidate = tmp_path / "candidate.json"
    candidate_sha = _write_json(
        candidate,
        {
            "schema": "pokemon-training-control-candidate-summary-v1",
            "model_sha256": model_sha256,
            "private_model_file_sha256": model_file_sha256,
        },
    )
    offline = tmp_path / "offline.json"
    offline_sha = _write_json(
        offline,
        {
            "schema": "pokemon-training-control-offline-gate-evaluation-v1",
            "candidate_summary_sha256": candidate_sha,
            "model_sha256": model_sha256,
            "offline_validation_eligible": True,
            "shadow_may_start": True,
        },
    )
    shadow = tmp_path / "shadow.json"
    shadow_sha = _write_json(
        shadow,
        {
            "schema": "pokemon-training-control-shadow-summary-v1",
            "status": "ok",
            "error": None,
            "provenance": _provenance("shadow-one", shadow_root),
            "model_sha256": model_sha256,
            "model_artifact_sha256": model_file_sha256,
            "model_had_execution_authority": False,
            "authority_phases": [],
        },
    )
    decisions = tmp_path / "decisions.json"
    decisions_sha = _write_json(
        decisions,
        {
            "schema": "pokemon-training-control-replay-v2",
            "status": "ok",
            "error": None,
            "provenance": _provenance("control-one", control_root),
            "segments": {
                "evolution": [{"action": "fight"}],
                "balance": [
                    {
                        "action": "stop",
                        "observation": {
                            "phase": "overworld",
                            "candidate_actions": ["stop"],
                            "features": {
                                "party.fill_ratio": 1.0,
                                "party.fainted_ratio": 0.0,
                                "party.minimum_level": 0.55,
                                "party.level_spread": 0.0,
                            },
                        },
                    }
                ],
            },
        },
    )
    control = tmp_path / "control.json"
    control_sha = _write_json(
        control,
        {
            "schema": "pokemon-training-control-shadow-summary-v1",
            "status": "ok",
            "error": None,
            "provenance": _provenance("control-one", control_root),
            "model_sha256": model_sha256,
            "model_artifact_sha256": model_file_sha256,
            "model_had_execution_authority": True,
            "authority_phases": ["battle", "overworld"],
            "teacher_fallback_on_model_disagreement": False,
            "decisions": 2,
            "controlled_decisions": 2,
        },
    )
    log = tmp_path / "control.log"
    log_sha = _write_text(
        log,
        "finished: evolution_battles=3, evolution_healing_trips=2, "
        "balance_battles=9, balance_healing_trips=3, "
        "report=BalancedTeamReport(required_size=6, minimum_level=55, "
        "maximum_level_spread=40, observed_size=6, observed_minimum_level=55, "
        "observed_level_spread=0, fainted_count=0, exception_reasons=())\n",
    )
    return subprocess.run(
        [
            sys.executable,
            "scripts/check_training_control_causal_gates.py",
            "--plan",
            str(plan),
            plan_sha,
            "--candidate",
            str(candidate),
            candidate_sha,
            "--offline",
            str(offline),
            offline_sha,
            "--shadow",
            str(shadow),
            shadow_sha,
            "--decisions",
            str(decisions),
            decisions_sha,
            "--control",
            str(control),
            control_sha,
            "--log",
            str(log),
            log_sha,
            "--out",
            str(tmp_path / "gate.json"),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_causal_gate_authenticates_the_full_promotion_chain(tmp_path: Path) -> None:
    completed = _run_gate(tmp_path, maximum_decisions=2)

    assert completed.returncode == 0
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["causal_control_eligible"] is True
    assert payload["portable_loop_may_start"] is True
    assert payload["observed"] == {
        "battles": 12,
        "decisions": 2,
        "faints": 0,
        "final_party_levels": [55, 55, 55, 55, 55, 55],
        "healing_trips": 5,
    }


def test_causal_gate_returns_nonzero_when_an_operational_limit_fails(tmp_path: Path) -> None:
    rejected = _run_gate(tmp_path, maximum_decisions=1)

    assert rejected.returncode == 2
    payload = json.loads((tmp_path / "gate.json").read_text())
    assert payload["causal_control_eligible"] is False
    assert payload["portable_loop_may_start"] is False
    assert payload["checks"]["decisions"]["passed"] is False
