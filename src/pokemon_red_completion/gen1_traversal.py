"""Generation I traversal rules read from cartridge data.

This module deliberately separates four different facts that a flat walkable
grid cannot express:

* ledges are directed actions that jump over the adjacent tile;
* some otherwise-passable tile pairs cannot be crossed because their elevation
  differs;
* Cut replaces one map block with another; and
* Strength boulders are object events whose position changes during play.

Only the first two are projected into the default static local graph here. Cut
and Strength are extracted and reported, but their state transitions are not
pretended into existence. ``surf_local_graph`` is the explicit stateful
alternative: land and water remain different search modes, and only a living
party move plus Soul Badge permits the field transitions between them.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.actions import MacroActionKind
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
from pokemon_red_completion.observation import Badge, RawGameState

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
SURF_MOVE_ID = 0x39
SURF_CAPABILITY = "move:surf"
CUT_MOVE_ID = 0x0F
CUT_CAPABILITY = "move:cut"
LAND_MODE = "land"
WATER_MODE = "water"
SURF_MODE_CHANGE_COST = 4


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


def map_object_events(rom: bytes, map_ids: Collection[int]) -> tuple[MapObjectEvent, ...]:
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
        header + CONNECTION_FLAGS_OFFSET + 1 + flags.bit_count() * CONNECTION_STRUCT_BYTES
    )
    object_address = int.from_bytes(rom[object_pointer_at : object_pointer_at + 2], "little")
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

    return _local_graph(terrain, rules, blocked=blocked, include_surf=False)


def surf_local_graph(
    terrain: Terrain,
    rules: TraversalRules,
    *,
    blocked: Collection[tuple[int, int]] = (),
) -> LocalGraph:
    """Project land, water, boarding and disembarking as distinct modes."""

    return _local_graph(terrain, rules, blocked=blocked, include_surf=True)


def surf_capabilities(
    raw: RawGameState,
    *,
    surf_allowed: bool,
) -> frozenset[str]:
    """Derive field Surf from permission, badge and a living move holder.

    ``surf_allowed`` has no optimistic default.  The title adapter must first
    rule out forced cycling and story-specific restrictions; cartridge
    topology alone is deliberately insufficient to open a water edge.
    """

    if not surf_allowed or not (int(raw.badge_bits or 0) & int(Badge.SOUL)):
        return frozenset()
    hp = raw.party_hp or ()
    moves = raw.party_moves or ()
    if raw.party_count is None or raw.party_count != len(hp) or len(hp) != len(moves):
        return frozenset()
    if any(
        current_hp > 0 and SURF_MOVE_ID in known
        for current_hp, known in zip(hp, moves, strict=True)
    ):
        return frozenset({SURF_CAPABILITY})
    return frozenset()


def cut_capabilities(raw: RawGameState) -> frozenset[str]:
    """Derive field Cut from Cascade Badge and a living observed holder."""

    if not (int(raw.badge_bits or 0) & int(Badge.CASCADE)):
        return frozenset()
    hp = raw.party_hp or ()
    moves = raw.party_moves or ()
    if raw.party_count is None or raw.party_count != len(hp) or len(hp) != len(moves):
        return frozenset()
    if any(
        current_hp > 0 and CUT_MOVE_ID in known
        for current_hp, known in zip(hp, moves, strict=True)
    ):
        return frozenset({CUT_CAPABILITY})
    return frozenset()


def _local_graph(
    terrain: Terrain,
    rules: TraversalRules,
    *,
    blocked: Collection[tuple[int, int]],
    include_surf: bool,
) -> LocalGraph:
    unavailable = frozenset(blocked)
    ledges = {(rule.direction, rule.standing_tile, rule.ledge_tile): rule for rule in rules.ledges}
    edges: dict[tuple[int, int], tuple[LocalEdge, ...]] = {}
    for y in range(terrain.height):
        for x in range(terrain.width):
            source = (y, x)
            source_is_land = terrain.can_stand(y, x)
            source_is_water = include_surf and terrain.can_surf(y, x)
            if source in unavailable or not (source_is_land or source_is_water):
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
                    source_is_land
                    and terrain.tileset == OVERWORLD_TILESET
                    and (direction, source_tile, adjacent_tile) in ledges
                ):
                    landing = (y + 2 * dy, x + 2 * dx)
                    if landing not in unavailable and terrain.can_stand(*landing):
                        outgoing.append(
                            LocalEdge(
                                target=landing,
                                action=direction.value,
                                kind="ledge",
                                required_mode=LAND_MODE if include_surf else None,
                            )
                        )
                    continue
                if adjacent in unavailable:
                    continue
                adjacent_is_land = terrain.can_stand(*adjacent)
                adjacent_is_water = include_surf and terrain.can_surf(*adjacent)
                if source_is_land and adjacent_is_land:
                    if any(
                        rule.blocks(terrain.tileset, source_tile, adjacent_tile)
                        for rule in rules.land_pair_restrictions
                    ):
                        continue
                    outgoing.append(
                        LocalEdge(
                            target=adjacent,
                            action=direction.value,
                            kind="walk",
                            required_mode=LAND_MODE if include_surf else None,
                        )
                    )
                    continue
                if not include_surf or not (adjacent_is_land or adjacent_is_water):
                    continue
                if any(
                    rule.blocks(terrain.tileset, source_tile, adjacent_tile)
                    for rule in rules.water_pair_restrictions
                ):
                    continue
                if source_is_land and adjacent_is_water:
                    outgoing.append(
                        LocalEdge(
                            target=adjacent,
                            action=f"surf:{direction.value}",
                            kind="water_entry",
                            requirements=frozenset({SURF_CAPABILITY}),
                            cost=SURF_MODE_CHANGE_COST,
                            action_kind=MacroActionKind.FIELD_MOVE,
                            required_mode=LAND_MODE,
                            result_mode=WATER_MODE,
                        )
                    )
                elif source_is_water and adjacent_is_water:
                    outgoing.append(
                        LocalEdge(
                            target=adjacent,
                            action=direction.value,
                            kind="water_travel",
                            required_mode=WATER_MODE,
                        )
                    )
                elif source_is_water and adjacent_is_land:
                    outgoing.append(
                        LocalEdge(
                            target=adjacent,
                            action=direction.value,
                            kind="water_exit",
                            required_mode=WATER_MODE,
                            result_mode=LAND_MODE,
                        )
                    )
            edges[source] = tuple(outgoing)
    return LocalGraph(edges)


def _inside(terrain: Terrain, coordinate: tuple[int, int]) -> bool:
    y, x = coordinate
    return 0 <= y < terrain.height and 0 <= x < terrain.width
