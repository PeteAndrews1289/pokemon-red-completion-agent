"""Which squares a player can stand on, read from the cartridge.

:mod:`pokemon_red_completion.gen1_maps` says which maps are joined. That is half
a route. The other half is where you can walk once you are on one, and without it
every chapter module in this repository stays what it is today: a hand-written
list of button presses that is worth nothing to the next game.

A map is a grid of blocks; each block is a four-by-four square of tiles; the
player moves two tiles at a time. So a map ``width`` blocks across is ``width *
2`` steps across, and each step lands on one particular tile of a block.

Which one is not obvious, and guessing it wrong is silent -- every guess yields a
grid, and three of the four look plausible. It was settled by measurement rather
than assumption: of the 919 warps in Kanto, the share landing on a passable tile
is 98.3% under the lower-left reading and 34.7%, 34.4% and 62.5% under the other
three. A warp is a square the player has to stand on, so the reading that makes
almost all of them passable is the one the game uses.

How the offsets were found
==========================

``TILESET_TABLE`` was found by searching for a 24-entry table whose entries hold
a bank byte and pointers into the switchable window -- and it stayed hidden until
the search stopped requiring *all* its pointers to look like that. The collision
pointer does not: collision lists live in bank 0, so those pointers are flat ROM
offsets while the blockset pointers beside them are banked. A search that assumed
one convention for the whole entry could not find it.

What is checked
===============

Two invariants, both cross-checks against reads verified elsewhere rather than
restatements of this one:

* Three of the 24 tilesets name a grass tile; the rest use ``$FF`` for "no
  grass". Every map that has a grass encounter rate *and* uses one of those three
  must actually contain that tile. All 28 do. If the blockset or the block data
  were being read wrongly, tall grass would not land where the encounter tables
  say encounters happen.
* Warps must overwhelmingly fall on passable ground. Six of 919 do not, all on
  the bottom edge of Seafoam Islands and Rock Tunnel, which are landing spots
  reached by falling through a hole rather than by walking. The threshold is set
  well below that and far above the ~62% a wrong reading produces.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pokemon_red_completion.gen1_cartridge import (
    WILD_DATA_BANK,
    WILD_POINTER_ARRAY,
    CartridgeReadError,
    bank_offset,
)
from pokemon_red_completion.gen1_maps import (
    MAP_HEADER_BANKS,
    MAP_HEADER_POINTERS,
    read_map_graph,
)

TILESET_TABLE = 0xC7BE
TILESET_ENTRY_BYTES = 12
TILESET_COUNT = 24
COLLISION_LIST_LIMIT = 128
AUTOMATIC_WARP_TILE_LIMIT = 32
BLOCK_SIDE = 4
BLOCK_TILES = BLOCK_SIDE * BLOCK_SIDE
STEPS_PER_BLOCK = 2

#: Which tile of the two-by-two cell the player's feet occupy. Measured, not
#: assumed -- see the module docstring.
FEET_ROW = 1
FEET_COLUMN = 0

#: A tileset with no tall grass says so with this instead of a tile id.
NO_GRASS_TILE = 0xFF

#: The share of warps that must land on passable ground. A correct read gives
#: 98.3%; the best wrong reading gives 62.5%.
WARPS_ON_PASSABLE_GROUND = 0.95

#: Exact source table used by ``IsNextTileShoreOrWater`` in the supported
#: pret/pokered revision.  The list is cartridge data, not a Python tileset
#: allowlist, so Red and Blue can be compared independently.
WATER_TILESETS_TABLE = 0xE8E0
WATER_TILESET_COUNT = 9
WATER_TILE = 0x14
EAST_SHORE_TILE = 0x48
USUAL_SHORE_TILE = 0x32
SHIP_PORT_TILESET = 14

#: Pointer array consulted by ``IsPlayerStandingOnDoorTileOrWarpTile``.  Every
#: tileset owns one $FF-terminated list in bank 3.
WARP_TILE_ID_POINTERS = 0xC4CC
WARP_TILE_ID_BANK = 3

#: Sparse ``tileset, pointer`` records consulted first by the same routine.
#: Door lists live in bank 6 and use zero rather than $FF as their terminator.
DOOR_TILE_ID_POINTERS = 0x1A62C
DOOR_TILE_ID_BANK = 6
DOOR_TILESET_RECORDS = 13


@dataclass(frozen=True, slots=True)
class Tileset:
    """One tileset: how its blocks are built and which of its tiles are solid."""

    index: int
    bank: int
    blockset: int
    collision: int
    grass_tile: int
    walkable: frozenset[int]

    @property
    def has_grass(self) -> bool:
        return self.grass_tile != NO_GRASS_TILE


@dataclass(frozen=True, slots=True)
class Terrain:
    """One map's walkable grid, in steps rather than blocks or tiles."""

    map_id: int
    tileset: int
    #: ``walkable[y][x]`` -- indexed the way the game reports position.
    walkable: tuple[tuple[bool, ...], ...]
    #: Where tall grass is, which is where wild encounters happen.
    grass: tuple[tuple[bool, ...], ...]
    #: Squares accepted as shore/water while the player is in Surf mode.
    water: tuple[tuple[bool, ...], ...]
    #: The exact tile under each step. Traversal rules such as ledges and
    #: elevation-pair collisions depend on tile identity, not passability alone.
    tiles: tuple[tuple[int, ...], ...]
    #: Mutable map block ids when this terrain was built from live RAM. Keeping
    #: the source grid makes a verified Cut replacement reconstructible without
    #: silently falling back to the cartridge's initial map.
    blocks: tuple[tuple[int, ...], ...] | None = None

    def __post_init__(self) -> None:
        shape = tuple(len(row) for row in self.walkable)
        if not shape or not shape[0] or len(set(shape)) != 1:
            raise ValueError("terrain walkability must be a non-empty rectangular grid")
        for label, grid in (
            ("grass", self.grass),
            ("water", self.water),
            ("tiles", self.tiles),
        ):
            if len(grid) != len(self.walkable) or tuple(len(row) for row in grid) != shape:
                raise ValueError(f"terrain {label} must match the walkability grid")
        if self.blocks is not None:
            block_shape = tuple(len(row) for row in self.blocks)
            if not block_shape or not block_shape[0] or len(set(block_shape)) != 1:
                raise ValueError("terrain blocks must form a non-empty rectangular grid")
            if len(self.blocks) * STEPS_PER_BLOCK != len(self.walkable) or (
                block_shape[0] * STEPS_PER_BLOCK != shape[0]
            ):
                raise ValueError("terrain blocks must match the step-grid dimensions")

    @property
    def height(self) -> int:
        return len(self.walkable)

    @property
    def width(self) -> int:
        return len(self.walkable[0]) if self.walkable else 0

    def can_stand(self, y: int, x: int) -> bool:
        if not (0 <= y < self.height and 0 <= x < self.width):
            return False
        return self.walkable[y][x]

    def can_surf(self, y: int, x: int) -> bool:
        if not (0 <= y < self.height and 0 <= x < self.width):
            return False
        return self.water[y][x]


def water_tilesets(rom: bytes) -> frozenset[int]:
    """Decode the complete list consulted before shore/water tile checks."""

    found: list[int] = []
    cursor = WATER_TILESETS_TABLE
    while rom[cursor] != 0xFF:
        if len(found) == WATER_TILESET_COUNT:
            raise CartridgeReadError("the water tileset table does not end")
        tileset = rom[cursor]
        if tileset >= TILESET_COUNT:
            raise CartridgeReadError("the water tileset table contains an invalid tileset")
        found.append(tileset)
        cursor += 1
    if len(found) != WATER_TILESET_COUNT or len(set(found)) != WATER_TILESET_COUNT:
        raise CartridgeReadError("the water tileset table is incomplete or duplicated")
    return frozenset(found)


def automatic_warp_tiles(rom: bytes) -> dict[int, frozenset[int]]:
    """Tiles that trigger a warp as soon as Red steps onto them.

    Other warp coordinates are directional: the player may stand on the
    coordinate and has to keep moving toward an edge or warp carpet.  That
    distinction cannot be inferred from the coordinate alone.  In particular,
    Cerulean's robbed-house top door and the Underground Path top edge occupy
    the same geometric position but have different trigger semantics.
    """

    found: dict[int, set[int]] = {index: set() for index in range(TILESET_COUNT)}
    for tileset_id in range(TILESET_COUNT):
        pointer_at = WARP_TILE_ID_POINTERS + 2 * tileset_id
        pointer = int.from_bytes(rom[pointer_at : pointer_at + 2], "little")
        if not 0x4000 <= pointer <= 0x7FFF:
            raise CartridgeReadError(
                f"tileset {tileset_id}'s automatic-warp pointer is outside the bank window"
            )
        cursor = bank_offset(WARP_TILE_ID_BANK, pointer)
        values = _terminated_tile_ids(
            rom,
            cursor,
            terminator=0xFF,
            subject=f"tileset {tileset_id}'s automatic-warp list",
        )
        found[tileset_id].update(values)

    cursor = DOOR_TILE_ID_POINTERS
    seen_tilesets: set[int] = set()
    for _ in range(DOOR_TILESET_RECORDS):
        tileset_id = rom[cursor]
        if tileset_id >= TILESET_COUNT or tileset_id in seen_tilesets:
            raise CartridgeReadError("the automatic-door tileset table is invalid")
        pointer = int.from_bytes(rom[cursor + 1 : cursor + 3], "little")
        if not 0x4000 <= pointer <= 0x7FFF:
            raise CartridgeReadError("an automatic-door pointer is outside the bank window")
        values = _terminated_tile_ids(
            rom,
            bank_offset(DOOR_TILE_ID_BANK, pointer),
            terminator=0,
            subject=f"tileset {tileset_id}'s automatic-door list",
        )
        found[tileset_id].update(values)
        seen_tilesets.add(tileset_id)
        cursor += 3
    if rom[cursor] != 0xFF:
        raise CartridgeReadError("the automatic-door tileset table does not end")
    return {index: frozenset(values) for index, values in found.items()}


def _terminated_tile_ids(
    rom: bytes,
    cursor: int,
    *,
    terminator: int,
    subject: str,
) -> tuple[int, ...]:
    values: list[int] = []
    while rom[cursor] != terminator:
        values.append(rom[cursor])
        cursor += 1
        if len(values) > AUTOMATIC_WARP_TILE_LIMIT:
            raise CartridgeReadError(f"{subject} does not end")
    if len(set(values)) != len(values):
        raise CartridgeReadError(f"{subject} contains a duplicate")
    return tuple(values)


def tilesets(rom: bytes) -> dict[int, Tileset]:
    """Every tileset, with the list of tiles it lets a player stand on."""

    found: dict[int, Tileset] = {}
    for index in range(TILESET_COUNT):
        at = TILESET_TABLE + TILESET_ENTRY_BYTES * index
        bank = rom[at]
        blockset = int.from_bytes(rom[at + 1 : at + 3], "little")
        # Collision lists live in bank 0, so this pointer is a flat offset while
        # the one above it is banked. That mismatch is what hid this table.
        collision = int.from_bytes(rom[at + 5 : at + 7], "little")
        if not 0x4000 <= blockset <= 0x7FFF:
            raise CartridgeReadError(
                f"tileset {index} names blockset {blockset:#06x}, outside the bank window; "
                "the tileset table is not where it was located"
            )
        walkable: set[int] = set()
        cursor = collision
        while rom[cursor] != 0xFF:
            walkable.add(rom[cursor])
            cursor += 1
            if len(walkable) > COLLISION_LIST_LIMIT:
                raise CartridgeReadError(
                    f"tileset {index}'s collision list does not end; it is not a list"
                )
        if not walkable:
            raise CartridgeReadError(f"tileset {index} lets a player stand nowhere")
        found[index] = Tileset(
            index=index,
            bank=bank,
            blockset=blockset,
            collision=collision,
            grass_tile=rom[at + 10],
            walkable=frozenset(walkable),
        )
    return found


def _map_header(rom: bytes, map_id: int) -> tuple[int, int, int, int, int]:
    """``(tileset, height, width, block data offset, bank)`` for one map."""

    bank = rom[MAP_HEADER_BANKS + map_id]
    at = MAP_HEADER_POINTERS + 2 * map_id
    header = bank_offset(bank, int.from_bytes(rom[at : at + 2], "little"))
    blocks = int.from_bytes(rom[header + 3 : header + 5], "little")
    return rom[header], rom[header + 1], rom[header + 2], bank_offset(bank, blocks), bank


def terrain_for(
    rom: bytes,
    map_id: int,
    sets: Mapping[int, Tileset],
    *,
    water_set_ids: frozenset[int] | None = None,
) -> Terrain:
    """One map's walkable grid."""

    tileset_id, height, width, blocks, _ = _map_header(rom, map_id)
    block_rows = tuple(
        tuple(rom[blocks + y * width + x] for x in range(width)) for y in range(height)
    )
    return terrain_from_blocks(
        rom,
        map_id,
        block_rows,
        sets,
        water_set_ids=water_set_ids,
    )


def terrain_from_blocks(
    rom: bytes,
    map_id: int,
    block_rows: tuple[tuple[int, ...], ...],
    sets: Mapping[int, Tileset],
    *,
    water_set_ids: frozenset[int] | None = None,
) -> Terrain:
    """Decode one map from an explicit current block grid.

    Cartridge map blocks describe only the initial state. Field actions such as
    Cut replace entries in Red's live ``wOverworldMap`` buffer, so execution
    must supply the observed post-action grid here before planning a crossing.
    """

    tileset_id, height, width, _, _ = _map_header(rom, map_id)
    shape = tuple(len(row) for row in block_rows)
    if len(block_rows) != height or shape != (width,) * height:
        raise ValueError(
            f"map {map_id} needs a {height}x{width} block grid, got "
            f"{len(block_rows)}x{shape[0] if shape else 0}"
        )
    tileset = sets[tileset_id]
    blockset = bank_offset(tileset.bank, tileset.blockset)

    walkable: list[tuple[bool, ...]] = []
    grass: list[tuple[bool, ...]] = []
    water: list[tuple[bool, ...]] = []
    tile_rows: list[tuple[int, ...]] = []
    surf_tilesets = water_tilesets(rom) if water_set_ids is None else water_set_ids
    for y in range(height * STEPS_PER_BLOCK):
        row_walkable: list[bool] = []
        row_grass: list[bool] = []
        row_water: list[bool] = []
        row_tiles: list[int] = []
        for x in range(width * STEPS_PER_BLOCK):
            block = block_rows[y // STEPS_PER_BLOCK][x // STEPS_PER_BLOCK]
            row = (y % STEPS_PER_BLOCK) * STEPS_PER_BLOCK + FEET_ROW
            column = (x % STEPS_PER_BLOCK) * STEPS_PER_BLOCK + FEET_COLUMN
            tile = rom[blockset + BLOCK_TILES * block + BLOCK_SIDE * row + column]
            row_tiles.append(tile)
            row_walkable.append(tile in tileset.walkable)
            row_grass.append(tileset.has_grass and tile == tileset.grass_tile)
            row_water.append(
                tileset_id in surf_tilesets
                and (
                    tile == WATER_TILE
                    or (
                        tileset_id != SHIP_PORT_TILESET
                        and tile in {EAST_SHORE_TILE, USUAL_SHORE_TILE}
                    )
                )
            )
        walkable.append(tuple(row_walkable))
        grass.append(tuple(row_grass))
        water.append(tuple(row_water))
        tile_rows.append(tuple(row_tiles))
    return Terrain(
        map_id=map_id,
        tileset=tileset_id,
        walkable=tuple(walkable),
        grass=tuple(grass),
        water=tuple(water),
        tiles=tuple(tile_rows),
        blocks=block_rows,
    )


def terrain_with_block(
    rom: bytes,
    terrain: Terrain,
    block_at: tuple[int, int],
    block_id: int,
    sets: Mapping[int, Tileset],
    *,
    water_set_ids: frozenset[int] | None = None,
) -> Terrain:
    """Predict one block replacement while retaining the exact source grid.

    This is suitable for candidate selection. Live execution must still read
    the mutated grid from RAM and call :func:`terrain_from_blocks` afterward.
    """

    if terrain.blocks is None:
        raise ValueError("a block replacement needs terrain built from explicit blocks")
    block_y, block_x = block_at
    if not (0 <= block_y < len(terrain.blocks) and 0 <= block_x < len(terrain.blocks[0])):
        raise ValueError(f"block coordinate {block_at} is outside map {terrain.map_id}")
    if not 0 <= block_id <= 0xFF:
        raise ValueError("a block id must fit in one byte")
    changed = [list(row) for row in terrain.blocks]
    changed[block_y][block_x] = block_id
    return terrain_from_blocks(
        rom,
        terrain.map_id,
        tuple(tuple(row) for row in changed),
        sets,
        water_set_ids=water_set_ids,
    )


def walkable_world(rom: bytes) -> dict[int, Terrain]:
    """Every reachable map's walkable grid, verified against other reads."""

    sets = tilesets(rom)
    surf_tilesets = water_tilesets(rom)
    graph = read_map_graph(rom)
    world = {
        map_id: terrain_for(
            rom,
            map_id,
            sets,
            water_set_ids=surf_tilesets,
        )
        for map_id in graph
    }
    _verify_grass_matches_the_encounter_tables(rom, world, sets)
    _verify_warps_land_on_ground(graph, world)
    return world


def _verify_grass_matches_the_encounter_tables(
    rom: bytes, world: Mapping[int, Terrain], sets: Mapping[int, Tileset]
) -> None:
    """Wild grass must be where the encounter tables say encounters happen."""

    missing: list[int] = []
    checked = 0
    for map_id, terrain in world.items():
        if not sets[terrain.tileset].has_grass:
            continue
        at = WILD_POINTER_ARRAY + 2 * map_id
        address = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= address <= 0x7FFF:
            continue
        if rom[bank_offset(WILD_DATA_BANK, address)] == 0:
            continue  # no grass encounter rate, so no grass is expected
        checked += 1
        if not any(any(row) for row in terrain.grass):
            missing.append(map_id)
    if not checked:
        raise CartridgeReadError("no map has both grass encounters and a grass tileset")
    if missing:
        raise CartridgeReadError(
            f"maps {sorted(missing)} have a grass encounter rate but no grass tile anywhere "
            "on them; the blockset or collision read disagrees with the encounter tables"
        )


def _verify_warps_land_on_ground(graph: Mapping[int, object], world: Mapping[int, Terrain]) -> None:
    """A warp is a square the player stands on, so it must be passable."""

    standing = total = 0
    for map_id, node in graph.items():
        terrain = world[map_id]
        for passage in getattr(node, "passages", ()):
            if passage.at is None:
                continue
            y, x = passage.at
            if not (0 <= y < terrain.height and 0 <= x < terrain.width):
                continue
            total += 1
            standing += terrain.walkable[y][x]
    if not total:
        raise CartridgeReadError("no warps to check the terrain against")
    share = standing / total
    if share < WARPS_ON_PASSABLE_GROUND:
        raise CartridgeReadError(
            f"only {share:.1%} of warps land on passable ground; a correct read gives 98.3% "
            "and the best wrong reading of the block layout gives 62.5%"
        )


def steps_between(
    terrain: Terrain, start: tuple[int, int], goal: tuple[int, int]
) -> tuple[tuple[int, int], ...]:
    """The shortest walk across one map, or empty if there is none.

    This is what a hand-written chapter module does by hand today. Every step is
    one square in one of four directions, and every square on the way is one the
    cartridge says a player can stand on.
    """

    if not terrain.can_stand(*start) or not terrain.can_stand(*goal):
        return ()
    if start == goal:
        return (start,)

    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    seen = {start}
    frontier = [start]
    while frontier:
        following: list[tuple[int, int]] = []
        for y, x in frontier:
            for step in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if step in seen or not terrain.can_stand(*step):
                    continue
                seen.add(step)
                came_from[step] = (y, x)
                if step == goal:
                    return _walk_back(came_from, start, goal)
                following.append(step)
        frontier = following
    return ()


def _walk_back(
    came_from: Mapping[tuple[int, int], tuple[int, int]],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> tuple[tuple[int, int], ...]:
    path = [goal]
    while path[-1] != start:
        path.append(came_from[path[-1]])
    return tuple(reversed(path))
