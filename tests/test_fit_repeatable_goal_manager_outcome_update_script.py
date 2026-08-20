from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path

import pytest

from pokemon_red_completion.goal_manager_outcome_learning import (
    outcome_update_configuration,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(
    str(PROJECT_ROOT / "scripts/fit_repeatable_goal_manager_outcome_update.py"),
    run_name="fit_repeatable_goal_manager_outcome_update_script_test",
)
FIT_PLAN = (
    PROJECT_ROOT
    / "docs/evidence/repeatable-goal-manager-outcome-fit-plan-v1-2026-08-18.json"
)


def test_fit_plan_freezes_the_single_update_before_decode() -> None:
    payload = json.loads(FIT_PLAN.read_bytes())

    assert payload["status"] == "frozen_before_target_decode"
    assert payload["eligible_targets"] == 2
    assert payload["complete_episodes"] == 1
    assert payload["independent_roots"] == 1
    assert payload["excluded_failed_prefix_choices"] == 19
    assert payload["configuration"] == outcome_update_configuration()
    assert payload["data_boundary"]["failed_artifact_target_decode"] == 0
    assert payload["decision"]["fail"].startswith("Reject this learner design")


def test_preflight_is_label_free_and_does_not_consume_identity(tmp_path: Path) -> None:
    claim = tmp_path / "claim.json"
    readiness = {
        "claim_path": claim,
        "fit_identity": "1" * 64,
        "base_sha256": "2" * 64,
        "campaign_sha256": "3" * 64,
        "receipt_sha256": "4" * 64,
        "fit_plan_sha256": "5" * 64,
    }

    result = SCRIPT["_preflight"](readiness)

    assert result["status"] == "ready_for_one_train_only_update"
    assert result["outcomes_decoded"] == 0
    assert result["model_predictions"] == 0
    assert result["model_fits"] == 0
    assert not claim.exists()


def test_fit_claim_is_durable_and_one_shot(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    claim_path = tmp_path / "claim.json"
    readiness = {
        "claim_path": claim_path,
        "fit_identity": "1" * 64,
        "base_sha256": "2" * 64,
        "campaign_sha256": "3" * 64,
        "receipt": {
            "admitted_evidence": {
                "complete_episode_manifest_sha256": "4" * 64,
            }
        },
        "fit_plan_sha256": "5" * 64,
        "receipt_sha256": "6" * 64,
        "runner_sha256": "7" * 64,
        "source_commit": "8" * 40,
    }

    payload = SCRIPT["_write_fit_claim"](readiness)

    assert claim_path.exists()
    assert claim_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(claim_path.read_bytes()) == payload
    assert hashlib.sha256(claim_path.read_bytes()).hexdigest()
    with pytest.raises(SCRIPT["GoalManagerOutcomeFitError"], match="consumed"):
        SCRIPT["_write_fit_claim"](readiness)


def test_private_outputs_must_be_new_and_inside_private_root(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    output = root / "candidate.json"

    assert SCRIPT["_new_private_output"](output, root, "output") == output
    output.write_text("occupied")
    with pytest.raises(SCRIPT["GoalManagerOutcomeFitError"]):
        SCRIPT["_new_private_output"](output, root, "output")
    with pytest.raises(SCRIPT["GoalManagerOutcomeFitError"]):
        SCRIPT["_new_private_output"](tmp_path / "outside.json", root, "output")
