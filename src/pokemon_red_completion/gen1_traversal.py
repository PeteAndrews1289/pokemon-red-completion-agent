"""Generation I traversal rules read from cartridge data.

This module deliberately separates four different facts that a flat walkable
grid cannot express:

* ledges are directed actions that jump over the adjacent tile;
* some otherwise-passable tile pairs cannot be crossed because their elevation
  differs;
* Cut replaces one map block with another; and
* Strength boulders are object events whose position changes during play.

Only the first two are projected into a static local graph here. Cut and
Strength are extracted and reported, but their state transitions are not
pretended into existence. Surf likewise changes movement mode; its exceptional
tile-pair table is decoded, while water-mode routing remains future work.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.gen1_cartridge import (
    MAP_ID_LIMIT,
    CartridgeReadError,
    bank_offset,
)
from pokemon_red_completion.gen1_maps import (
    CONNECTION_FLAG_LIMIT,
    CONNECTION_FLAGS_OFFSET,
    CONNECTION_STRUCT_BYTES,
    MAP_HEADER_BANKS,
    MAP_HEADER_POINTERS,
    WARP_COUNT_LIMIT,
    WARP_STRUCT_BYTES,
)
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.local_router import LocalEdge, LocalGraph

LEDGE_TABLE = 0x1A6CF
LAND_PAIR_COLLISION_TABLE = 0x0C7E
WATER_PAIR_COLLISION_TABLE = 0x0CA0
CUT_BLOCK_SWAP_TABLE = 0x0F100

LEDGE_ENTRY_BYTES = 4
LEDGE_RULE_COUNT = 8
PAIR_COLLISION_ENTRY_BYTES = 3
LAND_PAIR_COLLISION_COUNT = 11
WATER_PAIR_COLLISION_COUNT = 3
CUT_BLOCK_SWAP_COUNT = 9

TILESET_COUNT = 24
OVERWORLD_TILESET = 0
OBJECT_EVENT_LIMIT = 16
BACKGROUND_EVENT_BYTES = 3
SPRITE_BOULDER = 0x3F
STRENGTH_BOULDER_MOVEMENT = 0x10
TRAINER_TEXT_BIT = 0x40
ITEM_TEXT_BIT = 0x80


class Direction(StrEnum):
    DOWN = "down"
    UP = "up"
    LEFT = "left"
    RIGHT = "right"

    @property
    def delta(self) -> tuple[int, int]:
        return {
            Direction.DOWN: (1, 0),
            Direction.UP: (-1, 0),
            Direction.LEFT: (0, -1),
            Direction.RIGHT: (0, 1),
        }[self]


_DIRECTION_BYTES = {
    (0x00, 0x80): Direction.DOWN,
    (0x04, 0x40): Direction.UP,
    (0x08, 0x20): Direction.LEFT,
    (0x0C, 0x10): Direction.RIGHT,
}


@dataclass(frozen=True, slots=True)
class LedgeRule:
    direction: Direction
    standing_tile: int
    ledge_tile: int


@dataclass(frozen=True, slots=True)
class TilePairRestriction:
    tileset: int
    first_tile: int
    second_tile: int

    def blocks(self, tileset: int, first: int, second: int) -> bool:
        return self.tileset == tileset and {self.first_tile, self.second_tile} == {
            first,
            second,
        }


@dataclass(frozen=True, slots=True)
class CutBlockSwap:
    before: int
    after: int


@dataclass(frozen=True, slots=True)
class MapObjectEvent:
    map_id: int
    sprite_id: int
    y: int
    x: int
    movement: int
    direction_or_range: int
    text_id: int

    @property
    def at(self) -> tuple[int, int]:
        return self.y, self.x

    @property
    def is_boulder(self) -> bool:
        return self.sprite_id == SPRITE_BOULDER

    @property
    def is_strength_boulder(self) -> bool:
        return self.is_boulder and self.direction_or_range == STRENGTH_BOULDER_MOVEMENT


@dataclass(frozen=True, slots=True)
class TraversalRules:
    ledges: tuple[LedgeRule, ...]
    land_pair_restrictions: tuple[TilePairRestriction, ...]
    water_pair_restrictions: tuple[TilePairRestriction, ...]
    cut_block_swaps: tuple[CutBlockSwap, ...]
    boulders: tuple[MapObjectEvent, ...]


def ledge_rules(rom: bytes) -> tuple[LedgeRule, ...]:
    """Decode the complete direction/tile table used by the ledge engine."""

    found: list[LedgeRule] = []
    cursor = LEDGE_TABLE
    while rom[cursor] != 0xFF:
        if len(found) == LEDGE_RULE_COUNT:
            raise CartridgeReadError("the ledge table does not end after eight rules")
        facing, standing, ledge, joypad = rom[cursor : cursor + LEDGE_ENTRY_BYTES]
        try:
            direction = _DIRECTION_BYTES[(facing, joypad)]
        except KeyError as error:
            raise CartridgeReadError(
                f"ledge rule {len(found)} has incompatible facing/input bytes"
            ) from error
        found.append(LedgeRule(direction, standing, ledge))
        cursor += LEDGE_ENTRY_BYTES
    if len(found) != LEDGE_RULE_COUNT or len(set(found)) != LEDGE_RULE_COUNT:
        raise CartridgeReadError("the ledge table is incomplete or contains duplicate rules")
    return tuple(found)


def _pair_restrictions(
    rom: bytes, offset: int, expected: int, label: str
) -> tuple[TilePairRestriction, ...]:
    found: list[TilePairRestriction] = []
    cursor = offset
    while rom[cursor] != 0xFF:
        if len(found) == expected:
            raise CartridgeReadError(f"the {label} tile-pair table does not end")
        tileset, first, second = rom[cursor : cursor + PAIR_COLLISION_ENTRY_BYTES]
        if tileset >= TILESET_COUNT or first == second:
            raise CartridgeReadError(f"the {label} tile-pair table contains an invalid rule")
        found.append(TilePairRestriction(tileset, first, second))
        cursor += PAIR_COLLISION_ENTRY_BYTES
    if len(found) != expected or len(set(found)) != expected:
        raise CartridgeReadError(f"the {label} tile-pair table is incomplete or duplicated")
    return tuple(found)


def land_pair_restrictions(rom: bytes) -> tuple[TilePairRestriction, ...]:
    return _pair_restrictions(
        rom,
        LAND_PAIR_COLLISION_TABLE,
        LAND_PAIR_COLLISION_COUNT,
        "land",
    )


def water_pair_restrictions(rom: bytes) -> tuple[TilePairRestriction, ...]:
    return _pair_restrictions(
        rom,
        WATER_PAIR_COLLISION_TABLE,
        WATER_PAIR_COLLISION_COUNT,
        "water",
    )


def cut_block_swaps(rom: bytes) -> tuple[CutBlockSwap, ...]:
    """Decode each block replacement performed by Cut."""

    found: list[CutBlockSwap] = []
    cursor = CUT_BLOCK_SWAP_TABLE
    while rom[cursor] != 0xFF:
        if len(found) == CUT_BLOCK_SWAP_COUNT:
            raise CartridgeReadError("the Cut block-swap table does not end")
        before, after = rom[cursor : cursor + 2]
        if before == after:
            raise CartridgeReadError("a Cut block swap cannot replace a block with itself")
        found.append(CutBlockSwap(before, after))
        cursor += 2
    if len(found) != CUT_BLOCK_SWAP_COUNT or len(set(found)) != CUT_BLOCK_SWAP_COUNT:
        raise CartridgeReadError("the Cut block-swap table is incomplete or duplicated")
    return tuple(found)


def map_object_events(
    rom: bytes, map_ids: Collection[int]
) -> tuple[MapObjectEvent, ...]:
    """Decode initial object events for the requested real maps."""

    found: list[MapObjectEvent] = []
    for map_id in sorted(set(map_ids)):
        if not 0 <= map_id < MAP_ID_LIMIT:
            raise CartridgeReadError(f"map id {map_id} is outside the header table")
        found.extend(_objects_for_map(rom, map_id))
    return tuple(found)


def boulder_events(rom: bytes, map_ids: Collection[int]) -> tuple[MapObjectEvent, ...]:
    return tuple(event for event in map_object_events(rom, map_ids) if event.is_boulder)


def _objects_for_map(rom: bytes, map_id: int) -> tuple[MapObjectEvent, ...]:
    bank = rom[MAP_HEADER_BANKS + map_id]
    pointer_at = MAP_HEADER_POINTERS + 2 * map_id
    address = int.from_bytes(rom[pointer_at : pointer_at + 2], "little")
    if not 0x4000 <= address <= 0x7FFF or bank * 0x4000 >= len(rom):
        raise CartridgeReadError(f"map {map_id} has no readable header")
    header = bank_offset(bank, address)
    flags = rom[header + CONNECTION_FLAGS_OFFSET]
    if flags > CONNECTION_FLAG_LIMIT:
        raise CartridgeReadError(f"map {map_id} has invalid connection flags")
    object_pointer_at = (
        header
        + CONNECTION_FLAGS_OFFSET
        + 1
        + flags.bit_count() * CONNECTION_STRUCT_BYTES
    )
    object_address = int.from_bytes(
        rom[object_pointer_at : object_pointer_at + 2], "little"
    )
    if not 0x4000 <= object_address <= 0x7FFF:
        raise CartridgeReadError(f"map {map_id} has no readable object block")
    cursor = bank_offset(bank, object_address) + 1  # border block

    warp_count = rom[cursor]
    if warp_count > WARP_COUNT_LIMIT:
        raise CartridgeReadError(f"map {map_id} has too many warp events")
    cursor += 1 + warp_count * WARP_STRUCT_BYTES

    background_count = rom[cursor]
    cursor += 1 + background_count * BACKGROUND_EVENT_BYTES
    object_count = rom[cursor]
    cursor += 1
    if object_count > OBJECT_EVENT_LIMIT:
        raise CartridgeReadError(f"map {map_id} has too many object events")

    events: list[MapObjectEvent] = []
    for _ in range(object_count):
        sprite, stored_y, stored_x, movement, direction, text_id = rom[cursor : cursor + 6]
        if stored_y < 4 or stored_x < 4:
            raise CartridgeReadError(f"map {map_id} has an object outside its coordinate frame")
        events.append(
            MapObjectEvent(
                map_id=map_id,
                sprite_id=sprite,
                y=stored_y - 4,
                x=stored_x - 4,
                movement=movement,
                direction_or_range=direction,
                text_id=text_id,
            )
        )
        cursor += 6
        if text_id & TRAINER_TEXT_BIT:
            cursor += 2
        elif text_id & ITEM_TEXT_BIT:
            cursor += 1
    return tuple(events)


def traversal_rules(rom: bytes, map_ids: Collection[int]) -> TraversalRules:
    return TraversalRules(
        ledges=ledge_rules(rom),
        land_pair_restrictions=land_pair_restrictions(rom),
        water_pair_restrictions=water_pair_restrictions(rom),
        cut_block_swaps=cut_block_swaps(rom),
        boulders=boulder_events(rom, map_ids),
    )


def local_graph(
    terrain: Terrain,
    rules: TraversalRules,
    *,
    blocked: Collection[tuple[int, int]] = (),
) -> LocalGraph:
    """Project truthful static land movement for one decoded map.

    Dynamic objects can be supplied as blocked coordinates. Strength boulders
    are not opened merely because a capability exists: pushing one changes the
    state of the puzzle and requires a state-space planner, not an edge flag.
    """

    unavailable = frozenset(blocked)
    ledges = {
        (rule.direction, rule.standing_tile, rule.ledge_tile): rule
        for rule in rules.ledges
    }
    edges: dict[tuple[int, int], tuple[LocalEdge, ...]] = {}
    for y in range(terrain.height):
        for x in range(terrain.width):
            source = (y, x)
            if source in unavailable or not terrain.can_stand(y, x):
                continue
            outgoing: list[LocalEdge] = []
            for direction in Direction:
                dy, dx = direction.delta
                adjacent = (y + dy, x + dx)
                if not _inside(terrain, adjacent):
                    continue
                source_tile = terrain.tiles[y][x]
                adjacent_tile = terrain.tiles[adjacent[0]][adjacent[1]]
                if (
                    terrain.tileset == OVERWORLD_TILESET
                    and (direction, source_tile, adjacent_tile) in ledges
                ):
                    landing = (y + 2 * dy, x + 2 * dx)
                    if landing not in unavailable and terrain.can_stand(*landing):
                        outgoing.append(
                            LocalEdge(
                                target=landing,
                                action=direction.value,
                                kind="ledge",
                            )
                        )
                    continue
                if adjacent in unavailable or not terrain.can_stand(*adjacent):
                    continue
                if any(
                    rule.blocks(terrain.tileset, source_tile, adjacent_tile)
                    for rule in rules.land_pair_restrictions
                ):
                    continue
                outgoing.append(
                    LocalEdge(target=adjacent, action=direction.value, kind="walk")
                )
            edges[source] = tuple(outgoing)
    return LocalGraph(edges)


def _inside(terrain: Terrain, coordinate: tuple[int, int]) -> bool:
    y, x = coordinate
    return 0 <= y < terrain.height and 0 <= x < terrain.width
