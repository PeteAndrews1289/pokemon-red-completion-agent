"""Cartridge-derived reversible encounter corridors for living-dex lessons.

The option learner chooses a semantic source, never a direction sequence.  A
Red provider still needs a small, bounded local mechanic for seeking an
encounter.  This module derives that mechanic from the cartridge's grass grid
and directed traversal graph: two adjacent grass squares with plain walk edges
in both directions.  No root, slot, policy choice, outcome, or teacher route
participates in the derivation.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from pokemon_red_completion.actions import MacroActionKind
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.local_router import Coordinate, LocalEdge, LocalGraph
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG
from pokemon_red_completion.red_living_dex_multifamily_curriculum import (
    map_id_for_wild_source,
)
from pokemon_red_completion.red_living_dex_provider_curriculum import (
    RedEncounterSourceTarget,
)

RED_LIVING_DEX_WILD_CORRIDOR_SCHEMA = (
    "pokemon.red.private-living-dex-wild-corridor.v1"
)


class RedLivingDexWildCorridorError(ValueError):
    """A source cannot supply a reversible cartridge-derived encounter lane."""


@dataclass(frozen=True, slots=True)
class RedLivingDexWildCorridor:
    """One two-tile, bidirectional grass lane used by an existing provider."""

    source_id: str
    map_id: int
    origin_at: Coordinate
    terminal_at: Coordinate
    forward_directions: tuple[str, ...] = ("up",)
    starting_endpoint: str = "south"
    maximum_legs: int = 64
    maximum_seek_steps: int = 256
    maximum_encounters: int = 32

    def __post_init__(self) -> None:
        target = RedEncounterSourceTarget(self.source_id)
        if int(map_id_for_wild_source(target.source_id)) != self.map_id:
            raise RedLivingDexWildCorridorError(
                "encounter corridor map differs from its wild source"
            )
        if (
            self.origin_at[0] - 1 != self.terminal_at[0]
            or self.origin_at[1] != self.terminal_at[1]
            or self.forward_directions != ("up",)
            or self.starting_endpoint != "south"
        ):
            raise RedLivingDexWildCorridorError(
                "encounter corridor is not the canonical north-south pair"
            )
        for value, subject in (
            (self.maximum_legs, "legs"),
            (self.maximum_seek_steps, "seek steps"),
            (self.maximum_encounters, "encounters"),
        ):
            if type(value) is not int or value <= 0:  # noqa: E721
                raise RedLivingDexWildCorridorError(
                    f"encounter corridor {subject} bound differs"
                )

    @property
    def binding_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def private_dict(self) -> dict[str, object]:
        return {
            "forward_directions": list(self.forward_directions),
            "map_id": self.map_id,
            "maximum_encounters": self.maximum_encounters,
            "maximum_legs": self.maximum_legs,
            "maximum_seek_steps": self.maximum_seek_steps,
            "origin_at": list(self.origin_at),
            "schema": RED_LIVING_DEX_WILD_CORRIDOR_SCHEMA,
            "source_id": self.source_id,
            "starting_endpoint": self.starting_endpoint,
            "terminal_at": list(self.terminal_at),
        }

    def profile_parameters(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "label": "cartridge-derived reversible encounter corridor",
            "map_id": self.map_id,
            "player_x": self.origin_at[1],
            "player_y": self.origin_at[0],
            "forward_directions": list(self.forward_directions),
            "starting_endpoint": self.starting_endpoint,
            "maximum_legs": self.maximum_legs,
            "maximum_seek_steps": self.maximum_seek_steps,
            "maximum_encounters": self.maximum_encounters,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "bidirectional_walk_edges": 2,
            "cartridge_derived": True,
            "encounter_tiles": 2,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_local_direction_steps": len(self.forward_directions),
            "raw_teacher_direction_steps": 0,
            "schema": RED_LIVING_DEX_WILD_CORRIDOR_SCHEMA,
            "teacher_route": False,
        }


def derive_red_living_dex_wild_corridor(
    target: RedEncounterSourceTarget,
    terrain: Terrain,
    graph: LocalGraph,
    *,
    excluded: Collection[Coordinate] = (),
) -> RedLivingDexWildCorridor:
    """Choose a deterministic safe pair from real grass and traversal edges."""

    if not isinstance(target, RedEncounterSourceTarget):
        raise TypeError("wild corridor derivation needs an encounter target")
    if not isinstance(terrain, Terrain) or not isinstance(graph, LocalGraph):
        raise TypeError("wild corridor derivation needs cartridge terrain and graph")
    map_id = int(map_id_for_wild_source(target.source_id))
    if terrain.map_id != map_id:
        raise RedLivingDexWildCorridorError(
            "wild corridor terrain differs from its source map"
        )
    if not any(
        method.source_id == target.source_id
        for method in RED_ACQUISITION_CATALOG.methods
    ):
        raise RedLivingDexWildCorridorError(
            "wild corridor source has no Red acquisition method"
        )
    blocked = frozenset(excluded)
    if any(
        not isinstance(coordinate, tuple)
        or len(coordinate) != 2
        or any(type(value) is not int or value < 0 for value in coordinate)  # noqa: E721
        for coordinate in blocked
    ):
        raise RedLivingDexWildCorridorError(
            "wild corridor exclusions contain an invalid coordinate"
        )

    candidates: list[tuple[int, int, int, Coordinate, Coordinate]] = []
    for south_y in range(1, terrain.height):
        for x in range(terrain.width):
            south = (south_y, x)
            north = (south_y - 1, x)
            if (
                south in blocked
                or north in blocked
                or not terrain.grass[south[0]][south[1]]
                or not terrain.grass[north[0]][north[1]]
                or not _plain_land_walk(graph, south, north, "up")
                or not _plain_land_walk(graph, north, south, "down")
            ):
                continue
            perimeter_clearance = min(
                north[0],
                terrain.height - 1 - south[0],
                x,
                terrain.width - 1 - x,
            )
            exclusion_clearance = min(
                (
                    abs(south[0] - other[0]) + abs(south[1] - other[1])
                    for other in blocked
                ),
                default=terrain.height + terrain.width,
            )
            candidates.append(
                (
                    -perimeter_clearance,
                    -exclusion_clearance,
                    south_y,
                    south,
                    north,
                )
            )
    if not candidates:
        raise RedLivingDexWildCorridorError(
            "wild source has no unobstructed reversible grass pair"
        )
    _clearance, _excluded_clearance, _row, south, north = min(candidates)
    return RedLivingDexWildCorridor(
        source_id=target.source_id,
        map_id=map_id,
        origin_at=south,
        terminal_at=north,
    )


def _plain_land_walk(
    graph: LocalGraph,
    source: Coordinate,
    target: Coordinate,
    action: str,
) -> bool:
    return any(
        _is_plain_land_walk(edge, target, action)
        for edge in graph.neighbors(source)
    )


def _is_plain_land_walk(edge: LocalEdge, target: Coordinate, action: str) -> bool:
    return (
        edge.target == target
        and edge.action == action
        and edge.kind == "walk"
        and not edge.requirements
        and edge.action_kind is MacroActionKind.MOVE
        and edge.required_mode in {None, "land"}
        and edge.result_mode is None
        and edge.transient is None
    )


__all__ = [
    "RED_LIVING_DEX_WILD_CORRIDOR_SCHEMA",
    "RedLivingDexWildCorridor",
    "RedLivingDexWildCorridorError",
    "derive_red_living_dex_wild_corridor",
]
