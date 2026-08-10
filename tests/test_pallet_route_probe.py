from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion.gen1_maps import MapNode, Passage, PassageKind
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.observation import MapId
from pokemon_red_completion.pallet_route_probe import (
    PalletRouteProbeError,
    computed_route,
    oak_lab_warp,
)

RECORD = Path("docs/evidence/pallet-cartridge-route-probe-2026-08-10.json")


def _node(*passages: Passage) -> MapNode:
    return MapNode(map_id=MapId.PALLET_TOWN, height=2, width=2, passages=passages)


def _warp(destination: int, at: tuple[int, int]) -> Passage:
    return Passage(to_map=destination, kind=PassageKind.WARP, at=at)


def _terrain(*rows: tuple[bool, ...]) -> Terrain:
    return Terrain(
        map_id=MapId.PALLET_TOWN,
        tileset=0,
        walkable=rows,
        grass=tuple(tuple(False for _ in row) for row in rows),
        water=tuple(tuple(False for _ in row) for row in rows),
        tiles=tuple(tuple(1 if cell else 0 for cell in row) for row in rows),
    )


def test_the_lab_warp_is_selected_by_destination_not_position() -> None:
    unrelated = _warp(MapId.REDS_HOUSE_1F, (0, 0))
    lab = _warp(MapId.OAKS_LAB, (1, 1))

    assert oak_lab_warp(_node(unrelated, lab)) is lab


@pytest.mark.parametrize("count", (0, 2))
def test_the_probe_refuses_an_ambiguous_or_missing_lab_warp(count: int) -> None:
    node = _node(*(_warp(MapId.OAKS_LAB, (1, index)) for index in range(count)))

    with pytest.raises(PalletRouteProbeError, match=f"decoded {count}"):
        oak_lab_warp(node)


def test_the_computed_route_must_reach_the_decoded_warp() -> None:
    terrain = _terrain((True, True), (False, True))
    node = _node(_warp(MapId.OAKS_LAB, (1, 1)))

    assert computed_route(terrain, node, (0, 0)) == ((0, 0), (0, 1), (1, 1))

    with pytest.raises(PalletRouteProbeError, match="produced no route"):
        computed_route(_terrain((True, False), (False, True)), node, (0, 0))


def test_the_live_record_checks_each_computed_step_and_enters_the_lab() -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    route = [tuple(step) for step in record["computed_coordinates_yx"]]

    assert record["schema"] == "pallet-cartridge-route-probe-v1"
    assert record["status"] == "ok"
    assert route[0] == tuple(record["start_yx"]) == (6, 5)
    assert route[-1] == tuple(record["goal_warp_yx"]) == (11, 12)
    assert record["movement_steps"] == len(route) - 1 == 14
    assert record["verified_intermediate_coordinates"] == 13
    assert record["final_map"] == {"id": MapId.OAKS_LAB, "name": "OAKS_LAB"}
    assert record["controller_released"] is True
    assert record["rom_adjacent_artifacts_unchanged"] is True
    for before, after in zip(route, route[1:], strict=False):
        assert abs(before[0] - after[0]) + abs(before[1] - after[1]) == 1
