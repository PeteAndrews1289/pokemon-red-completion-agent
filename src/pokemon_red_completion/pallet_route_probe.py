"""Pure route-selection rules for the live Pallet Town falsification probe."""

from __future__ import annotations

from pokemon_red_completion.gen1_maps import MapNode, Passage
from pokemon_red_completion.gen1_terrain import Terrain, steps_between
from pokemon_red_completion.observation import MapId


class PalletRouteProbeError(RuntimeError):
    """Raised when cartridge data or the live game disproves the probe."""


def oak_lab_warp(node: MapNode) -> Passage:
    """The unique Pallet Town warp whose destination is Oak's Lab."""

    candidates = tuple(
        passage
        for passage in node.passages
        if passage.to_map == MapId.OAKS_LAB.value and passage.at is not None
    )
    if len(candidates) != 1:
        raise PalletRouteProbeError(
            f"expected one Pallet-to-lab warp, decoded {len(candidates)}"
        )
    return candidates[0]


def computed_route(
    terrain: Terrain, node: MapNode, start: tuple[int, int]
) -> tuple[tuple[int, int], ...]:
    """Compute and validate the route from live ``(y, x)`` to the lab warp."""

    passage = oak_lab_warp(node)
    assert passage.at is not None
    route = steps_between(terrain, start, passage.at)
    if len(route) < 2 or route[0] != start or route[-1] != passage.at:
        raise PalletRouteProbeError("the cartridge terrain produced no route to Oak's Lab")
    return route
