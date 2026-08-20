from __future__ import annotations

import json
import os
from pathlib import Path

RECORD = Path("docs/evidence/route1-cartridge-ledge-probe-2026-08-10.json")
SOURCE_COMMIT = "64625135fb114a9df978ab51f242b1931c1beb1e"
SOURCE_BUNDLE = "3b4d4f1a50fe2d229b42e348b6ac429505557538009c374274c65e2d6ec2fe39"
MOVES = {
    "down": (1, 0),
    "up": (-1, 0),
    "left": (0, -1),
    "right": (0, 1),
}


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_the_live_probe_is_bound_to_clean_committed_source() -> None:
    payload = record()

    assert payload["schema"] == "route1-cartridge-ledge-probe-v1"
    assert payload["status"] == "ok"
    assert payload["source"] == {
        "git_commit": SOURCE_COMMIT,
        "worktree_dirty": False,
    }
    assert payload["executable_source_bundle_sha256"] == SOURCE_BUNDLE
    assert payload["rom"] == {
        "title": "POKEMON RED",
        "size_bytes": 1_048_576,
        "sha1": "ea9bcae617fdf159b045185467ae58b2e4a48b9a",
        "sha256": "5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b",
    }


def test_every_generated_approach_input_names_the_observed_next_square() -> None:
    payload = record()
    coordinates = payload["approach_coordinates_yx"]
    inputs = payload["approach_inputs"]
    assert isinstance(coordinates, list)
    assert isinstance(inputs, list)
    assert len(inputs) == 13
    assert len(coordinates) == len(inputs) + 1
    assert coordinates[0] == payload["start_yx"] == [35, 10]
    assert coordinates[-1] == payload["ledge_source_yx"] == [26, 10]

    for before, action, after in zip(
        coordinates[:-1], inputs, coordinates[1:], strict=True
    ):
        assert isinstance(before, list)
        assert isinstance(after, list)
        assert isinstance(action, str)
        dy, dx = MOVES[action]
        assert after == [before[0] + dy, before[1] + dx]


def test_the_live_ledge_is_a_two_square_one_way_transition() -> None:
    payload = record()
    source = payload["ledge_source_yx"]
    landing = payload["ledge_landing_yx"]
    action = payload["ledge_input"]
    assert isinstance(source, list)
    assert isinstance(landing, list)
    assert isinstance(action, str)
    dy, dx = MOVES[action]

    assert payload["ledge_transition_kind"] == "ledge"
    assert landing == [source[0] + 2 * dy, source[1] + 2 * dx] == [28, 10]
    assert action == "down"
    assert payload["reverse_input"] == "up"
    assert payload["reverse_was_blocked"] is True
    assert payload["wild_flees"] == 0
    assert payload["movement_retries"] == 0


def test_the_probe_releases_control_without_publishing_private_artifacts() -> None:
    payload = record()
    encoded = json.dumps(payload)

    assert payload["frames_executed"] > 0
    assert payload["actions_executed_after_opening"] > 0
    assert payload["controller_released"] is True
    assert payload["rom_adjacent_artifacts_unchanged"] is True
    assert "/Users/" not in encoded
    rom_path = os.environ.get("POKEMON_RED_ROM")
    assert rom_path is None or rom_path not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
