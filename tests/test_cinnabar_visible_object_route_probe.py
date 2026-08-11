from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from pokemon_red_completion.gen1_traversal import MapObjectEvent
from pokemon_red_completion.local_router import LocalEdge, LocalGraph

SCRIPT = runpy.run_path(
    str(Path(__file__).parents[1] / "scripts" / "falsify_cinnabar_visible_object_route.py")
)
select_probe_goal = SCRIPT["select_probe_goal"]
RECORD = Path("docs/evidence/cinnabar-visible-object-route-probe-2026-08-10.json")
SOURCE_COMMIT = "1c6eb31fc61f40e440c8c33482f88bb3c0dd9fbe"
SOURCE_BUNDLE = "c106f581e47cfe9a1e35950f6235b526e260eb0ce9068b708ab13e0efbeeec4c"


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def graph() -> LocalGraph:
    return LocalGraph(
        {
            (0, 0): (
                LocalEdge((0, 1), action="right"),
                LocalEdge((1, 0), action="down"),
            ),
            (0, 1): (LocalEdge((0, 2), action="right"),),
            (1, 0): (LocalEdge((1, 1), action="right"),),
            (1, 1): (LocalEdge((1, 2), action="right"),),
            (1, 2): (LocalEdge((0, 2), action="up"),),
            (0, 2): (),
        }
    )


def event(*, movement: int = 0xFF) -> MapObjectEvent:
    return MapObjectEvent(
        map_id=8,
        sprite_id=11,
        y=0,
        x=1,
        movement=movement,
        direction_or_range=0xFF,
        text_id=2,
    )


def test_selection_proves_the_unblocked_candidate_crosses_an_avoidable_object() -> None:
    selected = select_probe_goal(graph(), (0, 0), (event(),))

    assert selected.blocker.at == (0, 1)
    assert selected.goal == (0, 2)
    assert selected.unblocked_path.coordinates == ((0, 0), (0, 1), (0, 2))
    assert selected.avoiding_path.coordinates == (
        (0, 0),
        (1, 0),
        (1, 1),
        (1, 2),
        (0, 2),
    )


def test_selection_does_not_mislabel_a_moving_object_as_the_fixed_control() -> None:
    with pytest.raises(RuntimeError, match="no stationary Cinnabar object"):
        select_probe_goal(graph(), (0, 0), (event(movement=0xFE),))


def test_live_record_is_bound_to_clean_authenticated_source() -> None:
    payload = record()

    assert payload["schema"] == "cinnabar-visible-object-route-probe-v1"
    assert payload["status"] == "ok"
    assert payload["source"] == {
        "git_commit": SOURCE_COMMIT,
        "worktree_dirty": False,
    }
    assert payload["executable_source_bundle_sha256"] == SOURCE_BUNDLE
    assert payload["private_capture_precondition"] == {
        "authenticated": True,
        "checkpoint_id": "portable_loop_defeat_blaine_terminal",
        "checkpoint_label": "Portable loop completed defeat_blaine",
        "required_verified_objective": "defeat_blaine",
    }


def test_live_route_did_not_receive_rom_object_positions_as_blockers() -> None:
    payload = record()
    selection = payload["selection"]
    initial_steps = payload["plans"]["outbound_initial"]["steps"]

    assert selection == {
        "start_yx": [12, 11],
        "goal_yx": [6, 13],
        "stationary_object_initial_yx": [6, 14],
        "unblocked_candidate_steps": 18,
        "avoiding_candidate_steps": 18,
        "unblocked_candidate_crosses_object": True,
        "rom_object_positions_used_as_planner_blockers": False,
    }
    assert {
        "source_map_id": 8,
        "source_yx": [6, 15],
        "action": "left",
        "expected_map_id": 8,
        "expected_yx": [6, 14],
        "kind": "walk",
    } in initial_steps


def test_visible_sprite_caused_one_replan_before_input() -> None:
    payload = record()
    outbound = payload["execution"]["outbound"]

    assert payload["visible_decision"] == {
        "player_yx": [6, 15],
        "occupied_yx": [[5, 12], [6, 14]],
        "sprite_index": 2,
        "picture_id": 11,
        "movement_status": 2,
        "image_index": 100,
        "object_yx": [6, 14],
        "input_sent_toward_occupied_square": False,
    }
    assert outbound["replans"] == [
        {
            "ordinal": 1,
            "map_id": 8,
            "at_yx": [6, 15],
            "candidate_blocker_yx": [6, 14],
            "replacement_steps": 4,
            "reason": "visible_object",
        }
    ]
    assert outbound["movement_requests"] == outbound["acknowledged_steps"] == 20


def test_probe_returned_exactly_and_published_no_private_path() -> None:
    payload = record()
    encoded = json.dumps(payload)

    assert all(stage["passed"] is True for stage in payload["execution"].values())
    assert sum(stage["movement_requests"] for stage in payload["execution"].values()) == 43
    assert sum(stage["acknowledged_steps"] for stage in payload["execution"].values()) == 43
    assert payload["actions_executed"] == 44
    assert payload["frames_executed"] == 1212
    assert payload["final"] == {"map_id": 8, "yx": [12, 11], "ready": True}
    assert payload["controller_released"] is True
    assert payload["rom_adjacent_artifacts_unchanged"] is True
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "PokemonRoms" not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
