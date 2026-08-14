from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from pokemon_red_completion.progress_dashboard import ProgressDashboardError
from pokemon_red_completion.red_battle_outcome_dashboard import (
    battle_outcome_dashboard_snapshot,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-battle-outcome-learning-cycle-2026-08-14.json"
)


def _evidence() -> dict[str, object]:
    value = json.loads(EVIDENCE_PATH.read_text(encoding="ascii"))
    assert isinstance(value, dict)
    return value


def test_first_real_outcome_result_projects_without_overclaiming() -> None:
    snapshot = battle_outcome_dashboard_snapshot(_evidence())
    payload = snapshot.public_dict()

    assert snapshot.run_status == "paused"
    assert snapshot.actions == 86
    assert snapshot.frame_count == 20_260
    assert snapshot.model.decisions == 8
    assert snapshot.model.teacher_queries == 0
    assert snapshot.experiment.phase == "blocked"
    assert snapshot.experiment.sealed_completed == 0
    assert snapshot.experiment.sealed_total == 200
    assert len(snapshot.learning_components) == 1
    component = snapshot.learning_components[0]
    assert component.status == "blocked"
    assert component.authority == "shadow_only"
    assert component.validation_correct == 0
    assert component.baseline_correct == 1
    assert payload["private_path_fields"] == 0
    assert payload["controller_endpoints"] == 0


def test_rejected_outcome_dashboard_requires_a_real_regression() -> None:
    evidence = deepcopy(_evidence())
    learner = evidence["learner_update"]
    assert isinstance(learner, dict)
    learner["updated_development_correct"] = 1

    with pytest.raises(ProgressDashboardError, match="does not reproduce regression"):
        battle_outcome_dashboard_snapshot(evidence)
