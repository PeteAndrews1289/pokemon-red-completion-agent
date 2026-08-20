from __future__ import annotations

import json
from pathlib import Path

from pokemon_red_completion.observation import MapId

RECORD = Path("docs/evidence/celadon-strategic-objective-route-probe-2026-08-11.json")
FAILURES = Path("docs/evidence/celadon-strategic-objective-route-failures-2026-08-11.json")


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="ascii"))
    assert isinstance(value, dict)
    return value


def test_celadon_teacher_rejects_the_unique_minimum_and_reaches_tower() -> None:
    evidence = _read(RECORD)
    strategic = evidence["strategic_navigation"]
    record = strategic["record"]
    decision = record["decision"]
    outcome = record["outcome"]

    assert evidence["schema"] == "celadon-strategic-objective-route-probe-v1"
    assert evidence["status"] == "ok"
    assert evidence["source"] == {
        "git_commit": "d3747f0758bd9a54b0c2ba2805b2bbf3b1fb38db",
        "worktree_dirty": False,
    }
    assert evidence["route_cost_baseline"] == {
        "unique_minimum_destination": "pokemon.red:destination:eevee_gift",
        "minimum_cost": 60,
        "teacher_selected_minimum": False,
        "teacher_selected_cost": 178,
        "selected_cost_above_minimum": 118,
    }
    candidates = decision["candidates"]
    assert [candidate["semantic_tags"] for candidate in candidates] == [
        ["remove_blocker", "story_progress"],
        ["acquire_party_member", "collection", "optional_reward"],
    ]
    assert [candidate["route_cost"] for candidate in candidates] == [178, 60]
    assert [candidate["route_steps"] for candidate in candidates] == [174, 55]
    assert decision["selected_index"] == 0
    assert evidence["candidate_plans"]["pokemon.red:destination:pokemon_tower"]["maps"] == [
        "CELADON_POKECENTER",
        "CELADON_CITY",
        "ROUTE_7",
        "UNDERGROUND_PATH_ROUTE_7",
        "UNDERGROUND_PATH_WEST_EAST",
        "UNDERGROUND_PATH_ROUTE_8",
        "ROUTE_8",
        "LAVENDER_TOWN",
        "POKEMON_TOWER_1F",
    ]
    execution = evidence["selected_execution"]
    assert execution["passed"] is True
    assert execution["movement_requests"] == 174
    assert execution["acknowledged_steps"] == 174
    assert execution["replans"] == []
    assert execution["interruptions"] == [
        {
            "kind": "trainer_engagement",
            "resumed_map_id": MapId.ROUTE_8,
            "resumed_yx": [6, 27],
            "details": {
                "battle_plan_id": "generated-route-map-19-trainer-1",
                "battle_started": True,
                "intro_pulses": 15,
                "verified": True,
            },
        }
    ]
    assert evidence["final_map"] == {
        "id": MapId.POKEMON_TOWER_1F,
        "name": "POKEMON_TOWER_1F",
    }
    assert evidence["final_yx"] == [17, 10]
    assert evidence["final_last_outside_map"] == {
        "id": MapId.LAVENDER_TOWN,
        "name": "LAVENDER_TOWN",
    }
    assert evidence["controller_released"] is True
    assert evidence["private_capture_unchanged"] is True
    assert evidence["rom_adjacent_artifacts_unchanged"] is True
    assert outcome["status"] == "succeeded"
    assert outcome["interruptions"] == [{"kind": "trainer_engagement", "outcome": "resumed"}]
    assert strategic["scope"] == (
        "unassigned non-cost-minimizing calibration; excluded from model development"
    )
    assert strategic["numeric_feature_schema_frozen"] is False
    assert strategic["promotion_eligible"] is False


def test_celadon_policy_projection_contains_no_route_or_destination_identity() -> None:
    strategic = _read(RECORD)["strategic_navigation"]
    decision = strategic["identity_free_trajectory_decision"]
    outcome = strategic["identity_free_trajectory_outcome"]
    projection = {
        "facts": decision["snapshot"]["facts"],
        "features": decision["snapshot"]["features"],
        "policy_input": decision["context"]["metadata"]["policy_input"],
        "action": decision["action"],
        "outcome": outcome["payload"],
    }
    encoded = json.dumps(projection, sort_keys=True)

    for forbidden in (
        "destination_ref",
        "origin_region_ref",
        "pokemon.red:destination",
        "celadon",
        "tower",
        "eevee",
        '"map_id"',
        '"coordinate"',
        '"direction"',
        '"left"',
        '"right"',
        '"up"',
        '"down"',
    ):
        assert forbidden not in encoded
    assert decision["action"] == {
        "kind": "select_destination",
        "selected_candidate_index": 0,
    }


def test_failed_attempts_are_public_negative_lineage_not_training_rows() -> None:
    evidence = _read(FAILURES)

    assert evidence["schema"] == ("celadon-strategic-objective-route-failure-lineage-v1")
    assert evidence["status"] == "closed_by_successful_replay"
    assert evidence["successful_source_commit"] == ("d3747f0758bd9a54b0c2ba2805b2bbf3b1fb38db")
    assert evidence["promotion_eligible"] is False
    attempts = evidence["failed_attempts"]
    assert len(attempts) == 6
    assert [attempt["category"] for attempt in attempts] == [
        "undeclared_staged_ledge",
        "composed_route_dropped_transient",
        "story_requirements_omitted",
        "trainer_script_interruption_unhandled",
        "defeated_trainer_dialogue_misclassified",
        "interruption_vocabulary_mismatch",
    ]
    assert "emitted no strategic training record" in evidence["scope"]
