from __future__ import annotations

import json
import os
from pathlib import Path

from pokemon_red_completion.observation import MapId

RECORD = Path("docs/evidence/joint-route-pricing-audit-2026-08-11.json")
SOURCE_COMMIT = "758ab6dedc8fd492c641a174f9da4376d3656ca6"
SOURCE_BUNDLE = "c415ffaeee59010255acc15aa90f072c9840d81beb98dd1708d8cf2054b9539e"
TOPOLOGY_MAPS = [
    MapId.PALLET_TOWN,
    MapId.ROUTE_1,
    MapId.VIRIDIAN_CITY,
    MapId.ROUTE_2,
    MapId.PEWTER_CITY,
]
JOINT_MAPS = [
    MapId.PALLET_TOWN,
    MapId.ROUTE_1,
    MapId.VIRIDIAN_CITY,
    MapId.ROUTE_2,
    MapId.VIRIDIAN_FOREST_SOUTH_GATE,
    MapId.VIRIDIAN_FOREST,
    MapId.VIRIDIAN_FOREST_NORTH_GATE,
    MapId.ROUTE_2,
    MapId.PEWTER_CITY,
]


def record() -> dict[str, object]:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_joint_pricing_record_is_bound_to_clean_source_and_static_scope() -> None:
    payload = record()

    assert payload["schema"] == "joint-route-pricing-audit-v1"
    assert payload["status"] == "ok"
    assert payload["source"] == {
        "git_commit": SOURCE_COMMIT,
        "worktree_dirty": False,
    }
    assert payload["executable_source_bundle_sha256"] == SOURCE_BUNDLE
    assert payload["scope"] == {
        "start_map_id": MapId.PALLET_TOWN,
        "start_yx": [12, 12],
        "goal_map_id": MapId.PEWTER_CITY,
        "terrain": "cartridge_initial",
        "capabilities": [],
        "dynamic_blockers": "not_projected",
        "live_execution_authority": False,
    }


def test_topology_only_fails_where_joint_pricing_uses_viridian_forest() -> None:
    payload = record()

    for cartridge in payload["cartridges"]:
        assert cartridge["topology_only"] == {
            "map_ids": TOPOLOGY_MAPS,
            "map_names": [map_id.name for map_id in TOPOLOGY_MAPS],
            "composable": False,
            "failure": "no decoded connection coordinate is locally reachable",
        }
        joint = cartridge["joint"]
        assert joint["map_ids"] == JOINT_MAPS
        assert joint["map_names"] == [map_id.name for map_id in JOINT_MAPS]
        assert joint["combined_cost"] == 317
        assert joint["acknowledgement_contract_steps"] == 314
        assert sum(
            segment["local_approach_cost"] + segment["passage_cost"]
            for segment in joint["segments"]
        ) == joint["combined_cost"]
        assert [segment["passage_kind"] for segment in joint["segments"]] == [
            "connection",
            "connection",
            "connection",
            "warp",
            "warp",
            "warp",
            "return",
            "connection",
        ]


def test_red_and_blue_agree_without_hiding_their_distinct_identities() -> None:
    payload = record()
    cartridges = payload["cartridges"]

    assert payload["red_blue_route_facts_identical"] is True
    assert [cartridge["title_ref"] for cartridge in cartridges] == ["red", "blue"]
    assert [cartridge["rom"]["title"] for cartridge in cartridges] == [
        "POKEMON RED",
        "POKEMON BLUE",
    ]
    assert cartridges[0]["rom"]["sha256"] != cartridges[1]["rom"]["sha256"]


def test_joint_pricing_record_contains_no_private_path() -> None:
    encoded = json.dumps(record())

    assert "/Users/" not in encoded
    assert "/Volumes/" not in encoded
    rom_path = os.environ.get("POKEMON_RED_ROM")
    assert rom_path is None or rom_path not in encoded
    assert ".gb" not in encoded
    assert ".state" not in encoded
