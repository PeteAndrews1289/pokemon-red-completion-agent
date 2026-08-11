from __future__ import annotations

import json
from pathlib import Path

from pokemon_red_completion.observation import MapId

RECORD = Path(
    "docs/evidence/fuchsia-strategic-objective-route-probe-2026-08-11.json"
)


def _record() -> dict[str, object]:
    value = json.loads(RECORD.read_text(encoding="ascii"))
    assert isinstance(value, dict)
    return value


def test_genuine_fuchsia_branch_binds_two_progression_routes_to_one_live_outcome() -> None:
    evidence = _record()
    strategic = evidence["strategic_navigation"]
    record = strategic["record"]
    decision = record["decision"]
    outcome = record["outcome"]

    assert evidence["schema"] == "fuchsia-strategic-objective-route-probe-v1"
    assert evidence["status"] == "ok"
    assert evidence["source"] == {
        "git_commit": "ba2c224f89d621fca6ef45a88fcff2e0d0880738",
        "worktree_dirty": False,
    }
    assert evidence["executable_source_bundle_sha256"] == (
        "beb4bbd8151886588953f085d82dcc09423a02279fd0f6754b60656014f2e4c8"
    )
    capture = evidence["capture"]
    assert capture["checkpoint_id"] == "portable_loop_obtain_surf_terminal"
    assert capture["checkpoints_completed"] == 198
    assert {"reach_fuchsia", "obtain_surf"}.issubset(
        capture["verified_objective_ids"]
    )

    candidates = decision["candidates"]
    assert [candidate["semantic_tags"] for candidate in candidates] == [
        ["challenge", "story_progress"],
        ["acquire_resource", "story_progress"],
    ]
    assert [candidate["route_cost"] for candidate in candidates] == [21, 24]
    assert [candidate["route_steps"] for candidate in candidates] == [20, 23]
    assert decision["selected_index"] == 0
    assert evidence["selected_execution"]["passed"] is True
    assert evidence["selected_execution"]["movement_requests"] == 20
    assert evidence["selected_execution"]["acknowledged_steps"] == 20
    assert evidence["selected_execution"]["replans"] == []
    assert evidence["final_map"] == {
        "id": MapId.FUCHSIA_GYM,
        "name": "FUCHSIA_GYM",
    }
    assert evidence["final_yx"] == [17, 4]
    assert evidence["controller_released"] is True
    assert evidence["private_capture_unchanged"] is True
    assert evidence["rom_adjacent_artifacts_unchanged"] is True
    assert outcome["decision_id"] == decision["decision_id"]
    assert outcome["status"] == "succeeded"
    assert outcome["acknowledged_steps"] == candidates[0]["route_steps"]
    assert strategic["scope"] == (
        "unassigned genuine-branch calibration; excluded from model development"
    )
    assert strategic["numeric_feature_schema_frozen"] is False
    assert strategic["promotion_eligible"] is False


def test_fuchsia_policy_projection_contains_no_destination_or_route_identity() -> None:
    evidence = _record()
    strategic = evidence["strategic_navigation"]
    decision = strategic["identity_free_trajectory_decision"]
    outcome = strategic["identity_free_trajectory_outcome"]
    policy_projection = {
        "facts": decision["snapshot"]["facts"],
        "features": decision["snapshot"]["features"],
        "policy_input": decision["context"]["metadata"]["policy_input"],
        "action": decision["action"],
        "outcome": outcome["payload"],
    }
    encoded = json.dumps(policy_projection, sort_keys=True)

    for forbidden in (
        "destination_ref",
        "origin_region_ref",
        "pokemon.red:destination",
        "fuchsia",
        '"direction"',
        '"coordinate"',
        '"map_id"',
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
    assert outcome["payload"]["decision_id"] == decision["decision_id"]
