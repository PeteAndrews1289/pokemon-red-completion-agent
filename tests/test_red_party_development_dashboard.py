from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from pokemon_red_completion.progress_dashboard import ProgressDashboardError
from pokemon_red_completion.red_party_development_dashboard import (
    party_development_dashboard_snapshot,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULT_PATH = (
    PROJECT_ROOT / "docs" / "evidence" / "red-party-development-outcome-result-2026-08-14.json"
)


def _evidence() -> dict[str, object]:
    value = json.loads(RESULT_PATH.read_text(encoding="ascii"))
    assert isinstance(value, dict)
    return value


def test_party_outcome_dashboard_shows_descriptive_speed_and_rejected_target() -> None:
    snapshot = party_development_dashboard_snapshot(_evidence())
    public = snapshot.public_dict()

    assert public["run_status"] == "blocked"
    assert public["stage_progress"] == 1.0
    assert public["frame_count"] == 2_524_621
    assert public["actions"] == 54_223
    assert public["model"]["mode"] == "shadow"
    assert public["model"]["choice"] == "No target · recovery accounting ambiguous"
    assert public["model"]["teacher_queries"] == 0
    assert public["experiment"]["zero_shot"] == {"completed": 2, "total": 2}
    assert public["experiment"]["adaptation"] == {"completed": 0, "total": 1}
    assert public["learning_components"] == []
    events = "\n".join(public["events"])
    assert "103 battles" in events
    assert "68 battles" in events
    assert "42 Center routes" in events
    assert "42 aggregate Center routes" in events
    assert "Phase breakdown was not retained" in events
    assert public["private_path_fields"] == 0
    assert public["controller_endpoints"] == 0


def test_party_outcome_dashboard_rejects_recovery_or_authority_overclaims() -> None:
    invalid_recovery = deepcopy(_evidence())
    recovery = invalid_recovery["recovery_accounting"]
    assert isinstance(recovery, dict)
    recovery["observed_total_counted_center_routes"] = [13, 41]

    with pytest.raises(ProgressDashboardError, match="recovery accounting"):
        party_development_dashboard_snapshot(invalid_recovery)

    overclaim = deepcopy(_evidence())
    decision = overclaim["decision"]
    assert isinstance(decision, dict)
    decision["authority_promoted"] = True

    with pytest.raises(ProgressDashboardError, match="overclaims"):
        party_development_dashboard_snapshot(overclaim)
