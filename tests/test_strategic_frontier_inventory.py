from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audit_strategic_frontier_inventory import PROJECT_ROOT, _run  # noqa: E402

from pokemon_red_completion.captured_progress import (  # noqa: E402
    CapturedProgressEnvelope,
    CapturedProgressError,
)
from pokemon_red_completion.strategic_frontier_inventory import (  # noqa: E402
    strategic_frontier_inventory,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    load_strategic_navigation_scenario_registry,
)


def _capture(
    checkpoint_id: str,
    objective_ids: tuple[str, ...],
) -> CapturedProgressEnvelope:
    return CapturedProgressEnvelope(
        state_sha256="a" * 64,
        checkpoint_id=checkpoint_id,
        checkpoint_label=checkpoint_id,
        checkpoints_completed=1,
        checkpoints_total=1,
        verified_objective_ids=objective_ids,
    )


def test_inventory_reports_exact_and_one_skill_coverage_without_capture_ids() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario_001 = registry.scenario("red-strategic-scenario-v2-001-train")
    scenario_002 = registry.scenario("red-strategic-scenario-v2-002-train")
    capture = _capture("private-checkpoint", scenario_001.completed_objective_ids)

    payload = strategic_frontier_inventory((capture,), registry)

    assert payload["authenticated_capture_envelopes"] == 1
    assert payload["exact_learning_scenario_ids"] == [scenario_001.scenario_id]
    assert payload["missing_learning_scenario_count"] == 35
    assert {
        item["target_scenario_id"]: item
        for item in payload["logical_one_skill_targets"]
    }[scenario_002.scenario_id] == {
        "target_scenario_id": scenario_002.scenario_id,
        "already_exact": False,
        "objective_ids": ["help_bill"],
        "authenticated_source_envelopes": 1,
        "unique_source_frontiers": 1,
    }
    assert "private-checkpoint" not in json_text(payload)
    assert payload["claim_boundary"] == {
        "live_skill_availability_checked": False,
        "target_origin_checked": False,
        "fresh_terminal_frontier_checked": False,
        "test_scenarios_opened": 0,
    }


def test_inventory_counts_duplicate_envelopes_without_inflating_frontiers() -> None:
    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = registry.scenario("red-strategic-scenario-v2-001-train")
    captures = (
        _capture("first", scenario.completed_objective_ids),
        _capture("second", scenario.completed_objective_ids),
    )

    payload = strategic_frontier_inventory(captures, registry)

    assert payload["authenticated_capture_envelopes"] == 2
    assert payload["unique_authenticated_frontiers"] == 1
    target = next(
        item
        for item in payload["logical_one_skill_targets"]
        if item["target_scenario_id"] == "red-strategic-scenario-v2-002-train"
    )
    assert target["authenticated_source_envelopes"] == 2
    assert target["unique_source_frontiers"] == 1


def test_private_inventory_root_must_remain_outside_repository(tmp_path: Path) -> None:
    with pytest.raises(CapturedProgressError, match="private directory"):
        _run(PROJECT_ROOT)
    with pytest.raises(CapturedProgressError, match="private directory"):
        _run(tmp_path / "missing")


def json_text(value: object) -> str:
    import json

    return json.dumps(value, sort_keys=True)
