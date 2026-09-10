"""Static indoor land wild encounter mask derived from cartridge blocksets and terrain.

Official pret/pokered reference:
https://github.com/pret/pokered/blob/master/engine/battle/wild_encounters.asm

In Generation I (Pokémon Red/Blue), wild encounter generation differs between
outdoor maps and indoor/dungeon maps:

1. Encounter check entry (``TryDoWildEncounter``):
   The engine first tests whether the player is standing on a door or warp tile
   (via ``IsPlayerStandingOnDoorTileOrWarpTile``). If so, wild encounters never
   occur.

2. Encounter rate selection:
   The encounter chance is evaluated against the tile under the player's bottom
   RIGHT foot. The engine checks whether that tile is tall grass (matching
   ``wGrassTile``) or water (``0x14``). If neither matches, but the map ID is an
   indoor map (``wCurMap >= FIRST_INDOOR_MAP``, where ``FIRST_INDOOR_MAP = 0x25``)
   and the tileset is not the Forest tileset (``wCurMapTileset != FOREST``,
   where ``FOREST = 3``), the engine falls back to using ``wGrassRate``.

3. Encounter species table selection:
   When an encounter triggers, the engine selects the species list by checking
   the tile under the player's bottom LEFT foot. If that tile is water (``0x14``),
   the water encounter list is selected; otherwise, the land/grass list is used.

4. Safari Zone exception:
   Safari Zone areas use distinct Safari encounter mechanics rather than ordinary
   indoor land battles.

This module computes a static grid of boolean eligibility flags for ordinary
indoor land encounters ONLY. It requires an actual non-empty land wild encounter
table for the map in the cartridge. It reads the tileset blockset directly from
the ROM to derive the bottom-right tile for every step cell and validates that
the reconstructed bottom-left tiles match ``Terrain.tiles``. If blocks are missing,
inconsistent, or out of ROM bounds, it fails closed.

This is a static encounter-location eligibility mask, not a guarantee of encounter
occurrence, capture, or route success. Revision-specific memory addresses and ROM
structures are encapsulated here; no claim is made for automatic transfer to
arbitrary modified ROMs.
"""

from __future__ import annotations

from typing import Final

from pokemon_red_completion.gen1_cartridge import (
    CartridgeReadError,
    bank_offset,
    wild_tables,
)
from pokemon_red_completion.gen1_terrain import (
    BLOCK_SIDE,
    BLOCK_TILES,
    FEET_COLUMN,
    FEET_ROW,
    STEPS_PER_BLOCK,
    Terrain,
    automatic_warp_tiles,
    tilesets,
)

#: Map IDs below this value are outdoor routes and cities.
FIRST_INDOOR_MAP: Final[int] = 0x25

#: Viridian Forest tileset ID; excluded from the indoor wGrassRate fallback.
FOREST_TILESET: Final[int] = 3

#: The canonical water tile ID across Generation I tilesets.
WATER_TILE: Final[int] = 0x14

#: Safari Zone maps are excluded from ordinary indoor wild land encounters.
SAFARI_MAP_IDS: Final[frozenset[int]] = frozenset({
    0x9C,  # SAFARI_ZONE_GATE
    0xD9,  # SAFARI_ZONE_EAST
    0xDA,  # SAFARI_ZONE_NORTH
    0xDB,  # SAFARI_ZONE_WEST
    0xDC,  # SAFARI_ZONE_CENTER
    0xDD,  # SAFARI_ZONE_CENTER_REST_HOUSE
    0xDE,  # SAFARI_ZONE_SECRET_HOUSE
    0xDF,  # SAFARI_ZONE_WEST_REST_HOUSE
    0xE0,  # SAFARI_ZONE_EAST_REST_HOUSE
    0xE1,  # SAFARI_ZONE_NORTH_REST_HOUSE
})


def is_safari_map(map_id: int) -> bool:
    """Whether a map ID belongs to the Safari Zone."""
    return map_id in SAFARI_MAP_IDS


def indoor_land_encounter_mask(
    rom: bytes,
    terrain: Terrain,
) -> tuple[tuple[bool, ...], ...]:
    """Return a grid of bool indicating ordinary indoor land encounter eligibility.

    A square is eligible if and only if:
    - The map is an indoor map (``map_id >= FIRST_INDOOR_MAP``).
    - The tileset is not the Forest tileset (``tileset != FOREST_TILESET``).
    - The map is not a Safari Zone map.
    - The map has an authenticated non-empty grass/land wild encounter table.
    - The square is walkable (``terrain.walkable[y][x]``).
    - The square is not marked as terrain water (``not terrain.water[y][x]``).
    - Neither the bottom-left nor the bottom-right tile is water (``0x14``).
    - Neither the bottom-left nor the bottom-right tile is an automatic door/warp tile.

    Outdoor maps, Forest tilesets, Safari maps, and indoor maps without a land
    wild encounter table return an all-False grid.

    Fails closed (raises an exception) if:
    - ``terrain.blocks`` is missing (``None``).
    - Reconstructed bottom-left tiles from ``terrain.blocks`` do not match ``terrain.tiles``.
    - Blockset offsets or tile reads exceed ROM bounds.
    """
    if not isinstance(rom, (bytes, bytearray)):
        raise TypeError("rom must be bytes")
    if not isinstance(terrain, Terrain):
        raise TypeError("terrain must be a Terrain instance")

    # 1. Outdoor maps and Forest tilesets yield False.
    if terrain.map_id < FIRST_INDOOR_MAP or terrain.tileset == FOREST_TILESET:
        return tuple(tuple(False for _ in range(terrain.width)) for _ in range(terrain.height))

    # 2. Safari maps are excluded.
    if is_safari_map(terrain.map_id):
        return tuple(tuple(False for _ in range(terrain.width)) for _ in range(terrain.height))

    # 3. Require actual non-empty grass/land wild encounter table.
    grass_wild_tables = wild_tables(rom, medium="grass")
    if not grass_wild_tables.get(terrain.map_id):
        return tuple(tuple(False for _ in range(terrain.width)) for _ in range(terrain.height))

    # 4. Fail closed if blocks are missing.
    if terrain.blocks is None:
        raise ValueError(
            f"indoor land encounter mask requires terrain with blocks for map {terrain.map_id}"
        )

    # 5. Read tileset and blockset from ROM.
    all_tilesets = tilesets(rom)
    if terrain.tileset not in all_tilesets:
        raise CartridgeReadError(f"tileset {terrain.tileset} not found in tileset table")
    tileset = all_tilesets[terrain.tileset]
    blockset_offset = bank_offset(tileset.bank, tileset.blockset)
    if blockset_offset < 0 or blockset_offset >= len(rom):
        raise CartridgeReadError(
            f"tileset {terrain.tileset} blockset offset {blockset_offset:#x} "
            f"exceeds ROM bounds ({len(rom)} bytes)"
        )

    # 6. Retrieve automatic door and warp tile IDs.
    auto_warp_dict = automatic_warp_tiles(rom)
    warp_tiles = auto_warp_dict.get(terrain.tileset, frozenset())

    # 7. Evaluate each step square in the grid.
    grid: list[tuple[bool, ...]] = []
    for y in range(terrain.height):
        row_mask: list[bool] = []
        block_y = y // STEPS_PER_BLOCK
        for x in range(terrain.width):
            block_x = x // STEPS_PER_BLOCK
            block_id = terrain.blocks[block_y][block_x]
            if type(block_id) is not int or not 0 <= block_id <= 255:
                raise CartridgeReadError("terrain block IDs must be cartridge bytes")
            block_offset = blockset_offset + BLOCK_TILES * block_id
            if block_offset < 0 or block_offset + BLOCK_TILES > len(rom):
                raise CartridgeReadError(
                    f"block {block_id} at offset {block_offset:#x} "
                    f"exceeds ROM bounds ({len(rom)} bytes)"
                )

            # Bottom-left tile: row offset 1, col offset 0 within 2x2 step cell
            left_row = (y % STEPS_PER_BLOCK) * STEPS_PER_BLOCK + FEET_ROW
            left_col = (x % STEPS_PER_BLOCK) * STEPS_PER_BLOCK + FEET_COLUMN
            left_offset = block_offset + BLOCK_SIDE * left_row + left_col

            # Bottom-right tile: row offset 1, col offset 1 within 2x2 step cell
            right_offset = left_offset + 1

            if left_offset >= len(rom) or right_offset >= len(rom):
                raise CartridgeReadError(
                    f"tile offsets ({left_offset:#x}, {right_offset:#x}) "
                    f"exceed ROM bounds ({len(rom)} bytes)"
                )

            left_tile = rom[left_offset]
            right_tile = rom[right_offset]

            # Fail closed on block-tile reconstruction mismatch
            if left_tile != terrain.tiles[y][x]:
                raise ValueError(
                    f"terrain block mismatch at step ({y}, {x}): "
                    f"reconstructed left tile {left_tile:#04x} "
                    f"does not match terrain.tiles {terrain.tiles[y][x]:#04x}"
                )

            # Eligibility: walkable land, non-water, and no door/warp tiles
            eligible = (
                terrain.walkable[y][x]
                and not terrain.water[y][x]
                and left_tile != WATER_TILE
                and right_tile != WATER_TILE
                and left_tile not in warp_tiles
                and right_tile not in warp_tiles
            )
            row_mask.append(eligible)
        grid.append(tuple(row_mask))

    return tuple(grid)
