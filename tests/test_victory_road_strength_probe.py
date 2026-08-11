from __future__ import annotations

import json
from pathlib import Path

from pokemon_red_completion.observation import MapId

RECORD = Path("docs/evidence/victory-road-strength-state-search-probe-2026-08-11.json")
SOURCE_COMMIT = "a3f95287f0b944926cadb2287488f4d662639031"
SOURCE_BUNDLE = "135d4ee9f3f3d090f423d55014b2ed2121917fdd631f1790c5bbbcac543bb116"


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_strength_probe_is_bound_to_authenticated_clean_source() -> None:
    payload = record()

    assert payload["schema"] == "victory-road-strength-state-search-probe-v1"
    assert payload["status"] == "ok"
    assert payload["source"] == {
        "git_commit": SOURCE_COMMIT,
        "source_bundle_sha256": SOURCE_BUNDLE,
    }
    assert payload["capture"] == {
        "checkpoint_id": "portable_loop_defeat_giovanni_terminal",
        "required_verified_objectives": ["defeat_giovanni", "obtain_strength"],
    }
    assert payload["boundary"] == {
        "map_id": MapId.VICTORY_ROAD_1F,
        "player_yx": [17, 8],
        "ready": True,
    }


def test_strength_probe_searched_all_boulders_and_acknowledged_every_step() -> None:
    payload = record()
    planner = payload["planner"]
    execution = payload["execution"]

    assert planner["algorithm"] == "bounded_dijkstra_player_and_all_boulders"
    assert planner["initial"] == {
        "player_yx": [17, 8],
        "boulders": [
            {"sprite_index": 5, "yx": [15, 5]},
            {"sprite_index": 6, "yx": [2, 14]},
            {"sprite_index": 7, "yx": [10, 2]},
        ],
    }
    assert planner["goal_boulder_yx"] == [13, 17]
    assert planner["terminal"]["boulders"][0] == {
        "sprite_index": 5,
        "yx": [13, 17],
    }
    assert planner["max_states"] == 100_000
    assert planner["explored_states"] == 3_845
    assert (planner["cost"], planner["steps"], planner["walks"], planner["pushes"]) == (
        75,
        57,
        39,
        18,
    )
    assert execution["passed"] is True
    assert execution["acknowledged_steps"] == execution["controller_inputs"] == 57
    assert execution["switch_event_set"] is True


def test_every_push_was_exact_stationary_and_privacy_safe() -> None:
    payload = record()
    execution = payload["execution"]
    pushes = execution["push_receipts"]
    encoded = json.dumps(payload)

    assert len(pushes) == 18
    assert all(receipt["boulder_index"] == 5 for receipt in pushes)
    assert all(receipt["player_stationary"] is True for receipt in pushes)
    assert all(receipt["pushed_flag_observed"] is True for receipt in pushes)
    assert all(receipt["engine_attempt_cost"] == 2 for receipt in pushes)
    assert pushes[-1]["boulder_after_yx"] == [13, 17]
    assert execution["actions_executed_after_boundary"] == 178
    assert execution["controller_released"] is True
    assert payload["rom_adjacent_artifacts_unchanged"] is True
    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    assert "PokemonRoms" not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
