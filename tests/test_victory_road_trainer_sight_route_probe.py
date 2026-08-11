from __future__ import annotations

import json
import os
import runpy
from pathlib import Path

from pokemon_red_completion.global_router import MacroGraph
from pokemon_red_completion.local_router import LocalEdge, LocalGraph
from pokemon_red_completion.route_executor import TraversalHazard
from pokemon_red_completion.route_plan import plan_route

SCRIPT = runpy.run_path(
    str(
        Path(__file__).parents[1]
        / "scripts"
        / "falsify_victory_road_trainer_sight_route.py"
    )
)
hazard_crossings = SCRIPT["hazard_crossings"]
RECORD = Path("docs/evidence/victory-road-trainer-sight-route-probe-2026-08-10.json")
SOURCE_COMMIT = "95e8b827668a165b6ca707dceb594460a5bf2d42"
SOURCE_BUNDLE = "07c2604cc9ed8e48c6536e271fa00d195eb9c8e08fd9f28e7fc09d36c4703c7e"


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_probe_selection_detects_semantic_lane_without_calling_it_occupancy() -> None:
    graph = LocalGraph(
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
    plan = plan_route(
        MacroGraph({1: ()}),
        {1: graph},
        1,
        (0, 0),
        1,
        goal_at=(0, 2),
    )

    assert hazard_crossings(
        plan,
        (
            TraversalHazard((0, 1), "trainer_sight"),
            TraversalHazard((1, 0), "lava"),
        ),
    ) == ((0, 1),)


def test_live_record_is_bound_to_the_corrected_clean_source() -> None:
    payload = record()

    assert payload["schema"] == "victory-road-trainer-sight-route-probe-v1"
    assert payload["status"] == "ok"
    assert payload["source"] == {
        "git_commit": SOURCE_COMMIT,
        "source_bundle_sha256": SOURCE_BUNDLE,
    }
    assert payload["capture"] == {
        "checkpoint_id": "portable_loop_defeat_giovanni_terminal",
        "required_verified_objectives": ["defeat_giovanni", "obtain_strength"],
    }


def test_live_record_uses_cartridge_facing_for_both_offscreen_trainers() -> None:
    female, male = record()["trainers"]

    assert female == {
        "sprite_index": 1,
        "trainer_class": 232,
        "trainer_set": 5,
        "trainer_yx": [5, 7],
        "facing": "right",
        "engage_distance_tiles": 2,
        "event_flag": 2321,
        "defeated": False,
        "visible_at_planning_boundary": False,
        "reserved_lane_yx": [[5, 8], [5, 9]],
    }
    assert male == {
        "sprite_index": 2,
        "trainer_class": 231,
        "trainer_set": 5,
        "trainer_yx": [2, 3],
        "facing": "down",
        "engage_distance_tiles": 2,
        "event_flag": 2322,
        "defeated": False,
        "visible_at_planning_boundary": False,
        "reserved_lane_yx": [[3, 3], [4, 3]],
    }


def test_live_unsafe_route_caused_one_zero_input_semantic_replan() -> None:
    payload = record()

    assert payload["selection"]["trainer_sight_crossings_yx"] == [[4, 3], [3, 3]]
    assert len(payload["selection"]["unprotected_plan"]["steps"]) == 50
    assert payload["execution"] == {
        "passed": True,
        "movement_requests": 50,
        "acknowledged_steps": 50,
        "wait_actions": 0,
        "interruptions": [],
        "replans": [
            {
                "ordinal": 1,
                "map_id": 108,
                "at_yx": [5, 3],
                "candidate_hazard_yx": [4, 3],
                "replacement_steps": 5,
                "reason": "trainer_sight",
            }
        ],
        "terminal_map_id": 108,
        "terminal_yx": [1, 2],
        "terminal_ready": True,
    }
    assert payload["decision"] == {
        "hazard_yx": [4, 3],
        "hazard_kind": "trainer_sight",
        "input_sent_toward_hazard": False,
        "trainer_engagement_observed": False,
        "battle_observed": False,
    }


def test_live_record_preserves_private_boundaries_and_releases_control() -> None:
    payload = record()
    encoded = json.dumps(payload)

    assert payload["controller_released"] is True
    assert payload["rom_adjacent_artifacts_unchanged"] is True
    assert payload["strength_boundary"] == {
        "initial_yx": [17, 8],
        "planned_terminal_yx": [12, 17],
        "plan_steps": 58,
        "explored_states": 3934,
        "execution_passed": True,
        "switch_event_set": True,
    }
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    rom_path = os.environ.get("POKEMON_RED_ROM")
    assert rom_path is None or rom_path not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
