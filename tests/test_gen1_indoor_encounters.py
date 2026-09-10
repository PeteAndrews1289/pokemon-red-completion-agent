"""ROM-free tests for Generation I indoor land encounter mask.

Tests distinguish:
- Bottom-right tile from bottom-left tile in encounter eligibility.
- Second block and row strides in multi-block terrain grids.
- Outdoor map and Forest tileset exclusions.
- Absence of a non-empty land wild table and Safari Zone exclusions.
- Water tile (0x14) in either half and terrain.water.
- Automatic warp/door tile IDs from automatic_warp_tiles(rom).
- Unwalkable tiles.
- Inconsistent and missing terrain blocks and ROM bounds violations.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_indoor_encounters import (
    FOREST_TILESET,
    indoor_land_encounter_mask,
    is_safari_map,
)
from pokemon_red_completion.gen1_terrain import (
    BLOCK_TILES,
    Terrain,
    Tileset,
)

TILESET_BANK = 1
BLOCKSET_ADDR = 0x4000
BLOCKSET_OFFSET = 0x4000  # bank 1 flat offset: 1 * 0x4000 + (0x4000 - 0x4000)
ROM_SIZE = 0x8000

INDOOR_MAP_ID = 0x3B  # Mt Moon 1F (>= FIRST_INDOOR_MAP 0x25)
INDOOR_TILESET_ID = 1  # Indoor tileset != FOREST_TILESET 3

FLOOR_TILE = 0x01
WATER_TILE = 0x14  # Independent engine fixture value, not imported from the implementation.
SOLID_TILE = 0x02
WARP_TILE = 0x60


def make_tileset(
    index: int = INDOOR_TILESET_ID,
    bank: int = TILESET_BANK,
    blockset: int = BLOCKSET_ADDR,
    walkable: frozenset[int] = frozenset({FLOOR_TILE, WARP_TILE, WATER_TILE}),
) -> Tileset:
    return Tileset(
        index=index,
        bank=bank,
        blockset=blockset,
        collision=0x2000,
        grass_tile=0xFF,
        walkable=walkable,
    )


def make_test_rom(blocks: dict[int, list[int]], total_size: int = ROM_SIZE) -> bytes:
    """Create a minimal synthetic ROM holding explicit 16-tile blocks."""
    rom = bytearray(total_size)
    for block_id, tiles in blocks.items():
        assert len(tiles) == BLOCK_TILES
        offset = BLOCKSET_OFFSET + BLOCK_TILES * block_id
        rom[offset : offset + BLOCK_TILES] = bytes(tiles)
    return bytes(rom)


def test_distinguish_bottom_right_from_bottom_left(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bottom-right tile controls encounter chance; bottom-left controls table.

    A step square is 2x2 tiles within a 4x4 block.
    Bottom-left is at (FEET_ROW=1, FEET_COL=0).
    Bottom-right is at (row=1, col=1).

    We construct a 2x2 step terrain (one block 0) with four distinct step cases:
    - Step (0, 0): bottom-left is WARP_TILE, bottom-right is FLOOR_TILE.
      Even though bottom-right is floor, standing on a warp tile disables encounters.
      Must be False.
    - Step (0, 1): bottom-left is FLOOR_TILE, bottom-right is WARP_TILE.
      Even though bottom-left is floor, bottom-right is warp, disabling encounters.
      Must be False.
    - Step (1, 0): bottom-left is FLOOR_TILE, bottom-right is FLOOR_TILE.
      Both halves are clean plain land floor. Must be True.
    - Step (1, 1): bottom-left is FLOOR_TILE, bottom-right is WATER_TILE (0x14).
      Even though bottom-left is land floor, bottom-right is water.
      Must be False.
    """
    # Block 0 layout (4 rows of 4 tiles):
    # Row 0: [0, 0, 0, 0]
    # Row 1: [WARP_TILE, FLOOR_TILE, FLOOR_TILE, WARP_TILE]
    # Row 2: [0, 0, 0, 0]
    # Row 3: [FLOOR_TILE, FLOOR_TILE, FLOOR_TILE, WATER_TILE]
    block_0 = [
        0, 0, 0, 0,
        WARP_TILE, FLOOR_TILE, FLOOR_TILE, WARP_TILE,
        0, 0, 0, 0,
        FLOOR_TILE, FLOOR_TILE, FLOOR_TILE, WATER_TILE,
    ]

    rom = make_test_rom({0: block_0})
    tileset = make_tileset()

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.tilesets",
        lambda _rom: {INDOOR_TILESET_ID: tileset},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.automatic_warp_tiles",
        lambda _rom: {INDOOR_TILESET_ID: frozenset({WARP_TILE})},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.wild_tables",
        lambda _rom, medium=None: {INDOOR_MAP_ID: [(10, 1)]},
    )

    # Reconstructed left tiles:
    # (0, 0) -> block_0[4] = WARP_TILE
    # (0, 1) -> block_0[6] = FLOOR_TILE
    # (1, 0) -> block_0[12] = FLOOR_TILE
    # (1, 1) -> block_0[14] = FLOOR_TILE
    terrain = Terrain(
        map_id=INDOOR_MAP_ID,
        tileset=INDOOR_TILESET_ID,
        walkable=((True, True), (True, True)),
        grass=((False, False), (False, False)),
        water=((False, False), (False, False)),
        tiles=((WARP_TILE, FLOOR_TILE), (FLOOR_TILE, FLOOR_TILE)),
        blocks=((0,),),
    )

    mask = indoor_land_encounter_mask(rom, terrain)
    expected = (
        (False, False),
        (True, False),
    )
    assert mask == expected


def test_second_block_and_row_strides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify stride arithmetic across multiple blocks (X and Y) and cell rows.

    A 4x4 step terrain built from 2x2 blocks:
      blocks = ((0, 1),
                (2, 3))
    Each block contains a unique configuration of encounter and non-encounter steps:
    - Block 0 (y in 0..1, x in 0..1):
        (0, 0): floor / floor -> True
        (0, 1): floor / warp -> False
        (1, 0): unwalkable -> False
        (1, 1): floor / floor -> True
    - Block 1 (y in 0..1, x in 2..3):
        (0, 2): floor / water -> False
        (0, 3): floor / floor -> True
        (1, 2): floor / floor -> True
        (1, 3): warp / floor -> False
    - Block 2 (y in 2..3, x in 0..1):
        (2, 0): floor / floor -> True
        (2, 1): water / floor -> False
        (3, 0): unwalkable -> False
        (3, 1): floor / floor -> True
    - Block 3 (y in 2..3, x in 2..3):
        (2, 2): floor / warp -> False
        (2, 3): floor / floor -> True
        (3, 2): floor / floor -> True
        (3, 3): floor / water -> False
    """
    b0 = [
        0, 0, 0, 0,
        FLOOR_TILE, FLOOR_TILE, FLOOR_TILE, WARP_TILE,
        0, 0, 0, 0,
        FLOOR_TILE, FLOOR_TILE, FLOOR_TILE, FLOOR_TILE,
    ]
    b1 = [
        0, 0, 0, 0,
        FLOOR_TILE, WATER_TILE, FLOOR_TILE, FLOOR_TILE,
        0, 0, 0, 0,
        FLOOR_TILE, FLOOR_TILE, WARP_TILE, FLOOR_TILE,
    ]
    b2 = [
        0, 0, 0, 0,
        FLOOR_TILE, FLOOR_TILE, WATER_TILE, FLOOR_TILE,
        0, 0, 0, 0,
        FLOOR_TILE, FLOOR_TILE, FLOOR_TILE, FLOOR_TILE,
    ]
    b3 = [
        0, 0, 0, 0,
        FLOOR_TILE, WARP_TILE, FLOOR_TILE, FLOOR_TILE,
        0, 0, 0, 0,
        FLOOR_TILE, FLOOR_TILE, FLOOR_TILE, WATER_TILE,
    ]

    rom = make_test_rom({0: b0, 1: b1, 2: b2, 3: b3})
    tileset = make_tileset()

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.tilesets",
        lambda _rom: {INDOOR_TILESET_ID: tileset},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.automatic_warp_tiles",
        lambda _rom: {INDOOR_TILESET_ID: frozenset({WARP_TILE})},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.wild_tables",
        lambda _rom, medium=None: {INDOOR_MAP_ID: [(10, 1)]},
    )

    # Reconstructed left tiles for each step:
    # y=0: b0[4]=FLOOR, b0[6]=FLOOR, b1[4]=FLOOR, b1[6]=FLOOR
    # y=1: b0[12]=FLOOR, b0[14]=FLOOR, b1[12]=FLOOR, b1[14]=WARP
    # y=2: b2[4]=FLOOR, b2[6]=WATER, b3[4]=FLOOR, b3[6]=FLOOR
    # y=3: b2[12]=FLOOR, b2[14]=FLOOR, b3[12]=FLOOR, b3[14]=FLOOR
    terrain = Terrain(
        map_id=INDOOR_MAP_ID,
        tileset=INDOOR_TILESET_ID,
        walkable=(
            (True, True, True, True),
            (False, True, True, True),
            (True, True, True, True),
            (False, True, True, True),
        ),
        grass=((False,) * 4,) * 4,
        water=((False,) * 4,) * 4,
        tiles=(
            (FLOOR_TILE, FLOOR_TILE, FLOOR_TILE, FLOOR_TILE),
            (FLOOR_TILE, FLOOR_TILE, FLOOR_TILE, WARP_TILE),
            (FLOOR_TILE, WATER_TILE, FLOOR_TILE, FLOOR_TILE),
            (FLOOR_TILE, FLOOR_TILE, FLOOR_TILE, FLOOR_TILE),
        ),
        blocks=((0, 1), (2, 3)),
    )

    mask = indoor_land_encounter_mask(rom, terrain)
    expected = (
        (True, False, False, True),
        (False, True, True, False),
        (True, False, False, True),
        (False, True, True, False),
    )
    assert mask == expected


def test_forest_and_outdoor_exclusion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outdoor maps and Forest tileset maps yield all-False."""
    block_0 = [FLOOR_TILE] * BLOCK_TILES
    rom = make_test_rom({0: block_0})
    tileset = make_tileset(index=INDOOR_TILESET_ID)
    forest_tileset = make_tileset(index=FOREST_TILESET)

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.tilesets",
        lambda _rom: {INDOOR_TILESET_ID: tileset, FOREST_TILESET: forest_tileset},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.automatic_warp_tiles",
        lambda _rom: {INDOOR_TILESET_ID: frozenset(), FOREST_TILESET: frozenset()},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.wild_tables",
        lambda _rom, medium=None: {0x00: [(10, 1)], 0x33: [(10, 1)]},
    )

    # 1. Outdoor map (map_id = 0x00 < FIRST_INDOOR_MAP 0x25)
    outdoor_terrain = Terrain(
        map_id=0x00,
        tileset=INDOOR_TILESET_ID,
        walkable=((True, True), (True, True)),
        grass=((False, False), (False, False)),
        water=((False, False), (False, False)),
        tiles=((FLOOR_TILE, FLOOR_TILE), (FLOOR_TILE, FLOOR_TILE)),
        blocks=((0,),),
    )
    assert indoor_land_encounter_mask(rom, outdoor_terrain) == (
        (False, False),
        (False, False),
    )

    # 2. Forest tileset 3, even on an indoor-ID map (Viridian Forest is 0x33).
    forest_terrain = Terrain(
        map_id=0x33,
        tileset=FOREST_TILESET,
        walkable=((True, True), (True, True)),
        grass=((False, False), (False, False)),
        water=((False, False), (False, False)),
        tiles=((FLOOR_TILE, FLOOR_TILE), (FLOOR_TILE, FLOOR_TILE)),
        blocks=((0,),),
    )
    assert indoor_land_encounter_mask(rom, forest_terrain) == (
        (False, False),
        (False, False),
    )


def test_no_land_table_and_safari_exclusion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Maps without wild grass/land tables or Safari maps yield all-False."""
    block_0 = [FLOOR_TILE] * BLOCK_TILES
    rom = make_test_rom({0: block_0})
    tileset = make_tileset()

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.tilesets",
        lambda _rom: {INDOOR_TILESET_ID: tileset},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.automatic_warp_tiles",
        lambda _rom: {INDOOR_TILESET_ID: frozenset()},
    )
    # Wild tables has NO entry for INDOOR_MAP_ID, but has one for Safari Zone East (0xD9)
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.wild_tables",
        lambda _rom, medium=None: {0xD9: [(25, 47)]},
    )

    # 1. Indoor map without land wild table
    indoor_terrain = Terrain(
        map_id=INDOOR_MAP_ID,
        tileset=INDOOR_TILESET_ID,
        walkable=((True, True), (True, True)),
        grass=((False, False), (False, False)),
        water=((False, False), (False, False)),
        tiles=((FLOOR_TILE, FLOOR_TILE), (FLOOR_TILE, FLOOR_TILE)),
        blocks=((0,),),
    )
    assert indoor_land_encounter_mask(rom, indoor_terrain) == (
        (False, False),
        (False, False),
    )

    # 2. Safari Zone map (0xD9 >= 0x25, tileset != 3, non-empty wild table)
    safari_terrain = Terrain(
        map_id=0xD9,
        tileset=INDOOR_TILESET_ID,
        walkable=((True, True), (True, True)),
        grass=((False, False), (False, False)),
        water=((False, False), (False, False)),
        tiles=((FLOOR_TILE, FLOOR_TILE), (FLOOR_TILE, FLOOR_TILE)),
        blocks=((0,),),
    )
    assert is_safari_map(0xD9)
    assert indoor_land_encounter_mask(rom, safari_terrain) == (
        (False, False),
        (False, False),
    )


def test_water_halves_and_terrain_water(monkeypatch: pytest.MonkeyPatch) -> None:
    """Either half having WATER_TILE (0x14) or terrain.water excludes the square."""
    # Step (0, 0): left=WATER_TILE, right=FLOOR_TILE -> False
    # Step (0, 1): left=FLOOR_TILE, right=WATER_TILE -> False
    # Step (1, 0): left=FLOOR_TILE, right=FLOOR_TILE, but terrain.water=True -> False
    # Step (1, 1): left=FLOOR_TILE, right=FLOOR_TILE, terrain.water=False -> True
    block_0 = [
        0, 0, 0, 0,
        WATER_TILE, FLOOR_TILE, FLOOR_TILE, WATER_TILE,
        0, 0, 0, 0,
        FLOOR_TILE, FLOOR_TILE, FLOOR_TILE, FLOOR_TILE,
    ]
    rom = make_test_rom({0: block_0})
    tileset = make_tileset()

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.tilesets",
        lambda _rom: {INDOOR_TILESET_ID: tileset},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.automatic_warp_tiles",
        lambda _rom: {INDOOR_TILESET_ID: frozenset()},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.wild_tables",
        lambda _rom, medium=None: {INDOOR_MAP_ID: [(10, 1)]},
    )

    terrain = Terrain(
        map_id=INDOOR_MAP_ID,
        tileset=INDOOR_TILESET_ID,
        walkable=((True, True), (True, True)),
        grass=((False, False), (False, False)),
        water=((False, False), (True, False)),
        tiles=((WATER_TILE, FLOOR_TILE), (FLOOR_TILE, FLOOR_TILE)),
        blocks=((0,),),
    )

    mask = indoor_land_encounter_mask(rom, terrain)
    expected = (
        (False, False),
        (False, True),
    )
    assert mask == expected


def test_automatic_warp_tiles_exclusion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tiles in automatic_warp_tiles on either half prevent encounters."""
    DOOR_TILE = 0x58
    # Step (0, 0): left=DOOR_TILE, right=FLOOR_TILE -> False
    # Step (0, 1): left=FLOOR_TILE, right=DOOR_TILE -> False
    # Step (1, 0): left=WARP_TILE, right=FLOOR_TILE -> False
    # Step (1, 1): left=FLOOR_TILE, right=FLOOR_TILE -> True
    block_0 = [
        0, 0, 0, 0,
        DOOR_TILE, FLOOR_TILE, FLOOR_TILE, DOOR_TILE,
        0, 0, 0, 0,
        WARP_TILE, FLOOR_TILE, FLOOR_TILE, FLOOR_TILE,
    ]
    rom = make_test_rom({0: block_0})
    tileset = make_tileset(walkable=frozenset({FLOOR_TILE, DOOR_TILE, WARP_TILE}))

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.tilesets",
        lambda _rom: {INDOOR_TILESET_ID: tileset},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.automatic_warp_tiles",
        lambda _rom: {INDOOR_TILESET_ID: frozenset({DOOR_TILE, WARP_TILE})},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.wild_tables",
        lambda _rom, medium=None: {INDOOR_MAP_ID: [(10, 1)]},
    )

    terrain = Terrain(
        map_id=INDOOR_MAP_ID,
        tileset=INDOOR_TILESET_ID,
        walkable=((True, True), (True, True)),
        grass=((False, False), (False, False)),
        water=((False, False), (False, False)),
        tiles=((DOOR_TILE, FLOOR_TILE), (WARP_TILE, FLOOR_TILE)),
        blocks=((0,),),
    )

    mask = indoor_land_encounter_mask(rom, terrain)
    expected = (
        (False, False),
        (False, True),
    )
    assert mask == expected


def test_unwalkable_exclusion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unwalkable squares are excluded regardless of tiles."""
    block_0 = [FLOOR_TILE] * BLOCK_TILES
    rom = make_test_rom({0: block_0})
    tileset = make_tileset()

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.tilesets",
        lambda _rom: {INDOOR_TILESET_ID: tileset},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.automatic_warp_tiles",
        lambda _rom: {INDOOR_TILESET_ID: frozenset()},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.wild_tables",
        lambda _rom, medium=None: {INDOOR_MAP_ID: [(10, 1)]},
    )

    terrain = Terrain(
        map_id=INDOOR_MAP_ID,
        tileset=INDOOR_TILESET_ID,
        walkable=((False, True), (True, False)),
        grass=((False, False), (False, False)),
        water=((False, False), (False, False)),
        tiles=((FLOOR_TILE, FLOOR_TILE), (FLOOR_TILE, FLOOR_TILE)),
        blocks=((0,),),
    )

    mask = indoor_land_encounter_mask(rom, terrain)
    expected = (
        (False, True),
        (True, False),
    )
    assert mask == expected


def test_inconsistent_and_missing_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing blocks, tile-reconstruction mismatches, and bounds fail closed."""
    block_0 = [FLOOR_TILE] * BLOCK_TILES
    rom = make_test_rom({0: block_0})
    tileset = make_tileset()

    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.tilesets",
        lambda _rom: {INDOOR_TILESET_ID: tileset},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.automatic_warp_tiles",
        lambda _rom: {INDOOR_TILESET_ID: frozenset()},
    )
    monkeypatch.setattr(
        "pokemon_red_completion.gen1_indoor_encounters.wild_tables",
        lambda _rom, medium=None: {INDOOR_MAP_ID: [(10, 1)]},
    )

    # 1. Missing blocks (terrain.blocks is None)
    terrain_no_blocks = Terrain(
        map_id=INDOOR_MAP_ID,
        tileset=INDOOR_TILESET_ID,
        walkable=((True, True), (True, True)),
        grass=((False, False), (False, False)),
        water=((False, False), (False, False)),
        tiles=((FLOOR_TILE, FLOOR_TILE), (FLOOR_TILE, FLOOR_TILE)),
        blocks=None,
    )
    with pytest.raises(ValueError, match="requires terrain with blocks"):
        indoor_land_encounter_mask(rom, terrain_no_blocks)

    # 2. Inconsistent blocks (reconstructed left tile != terrain.tiles)
    # block 0 has FLOOR_TILE, but terrain.tiles claims SOLID_TILE at (0, 0)
    terrain_mismatched = Terrain(
        map_id=INDOOR_MAP_ID,
        tileset=INDOOR_TILESET_ID,
        walkable=((True, True), (True, True)),
        grass=((False, False), (False, False)),
        water=((False, False), (False, False)),
        tiles=((SOLID_TILE, FLOOR_TILE), (FLOOR_TILE, FLOOR_TILE)),
        blocks=((0,),),
    )
    with pytest.raises(ValueError, match="terrain block mismatch at step"):
        indoor_land_encounter_mask(rom, terrain_mismatched)

    # 3. ROM bounds violation: truncated ROM where blockset exceeds ROM size
    short_rom = rom[:BLOCKSET_OFFSET + 8]
    terrain_valid = Terrain(
        map_id=INDOOR_MAP_ID,
        tileset=INDOOR_TILESET_ID,
        walkable=((True, True), (True, True)),
        grass=((False, False), (False, False)),
        water=((False, False), (False, False)),
        tiles=((FLOOR_TILE, FLOOR_TILE), (FLOOR_TILE, FLOOR_TILE)),
        blocks=((0,),),
    )
    with pytest.raises(CartridgeReadError, match="exceeds ROM bounds"):
        indoor_land_encounter_mask(short_rom, terrain_valid)


def test_type_validation() -> None:
    """Validate rom and terrain input argument types."""
    terrain = Terrain(
        map_id=INDOOR_MAP_ID,
        tileset=INDOOR_TILESET_ID,
        walkable=((True,),),
        grass=((False,),),
        water=((False,),),
        tiles=((FLOOR_TILE,),),
    )
    with pytest.raises(TypeError, match="rom must be bytes"):
        indoor_land_encounter_mask("not_bytes", terrain)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="terrain must be a Terrain instance"):
        indoor_land_encounter_mask(b"123", "not_terrain")  # type: ignore[arg-type]


@pytest.mark.parametrize("map_id,excluded", [(0xDD, True), (0xE1, True), (0xE2, False)])
def test_safari_boundary_does_not_exclude_cerulean_cave(map_id, excluded):
    # Independent map_constants.asm values: center rest house, north rest house,
    # then Cerulean Cave 2F. The initial draft had shifted the rest-house range.
    assert is_safari_map(map_id) is excluded


@pytest.mark.parametrize("map_id,expected", [(0x24, False), (0x25, True)])
def test_first_indoor_map_boundary(monkeypatch, map_id, expected):
    rom = make_test_rom({0: [FLOOR_TILE] * 16})
    monkeypatch.setattr("pokemon_red_completion.gen1_indoor_encounters.tilesets",
                        lambda _: {1: make_tileset()})
    monkeypatch.setattr("pokemon_red_completion.gen1_indoor_encounters.automatic_warp_tiles",
                        lambda _: {1: frozenset()})
    monkeypatch.setattr("pokemon_red_completion.gen1_indoor_encounters.wild_tables",
                        lambda _, *, medium: {map_id: [(5, 1)]} if medium == "grass" else {})
    terrain = Terrain(map_id, 1, ((True, True),) * 2, ((False, False),) * 2,
                      ((False, False),) * 2, ((FLOOR_TILE, FLOOR_TILE),) * 2, ((0,),))
    assert indoor_land_encounter_mask(rom, terrain) == ((expected, expected),) * 2


@pytest.mark.parametrize("block_id", [-1, 256, True])
def test_invalid_block_identity_fails_closed(monkeypatch, block_id):
    rom = make_test_rom({0: [FLOOR_TILE] * 16})
    monkeypatch.setattr("pokemon_red_completion.gen1_indoor_encounters.tilesets",
                        lambda _: {1: make_tileset()})
    monkeypatch.setattr("pokemon_red_completion.gen1_indoor_encounters.automatic_warp_tiles",
                        lambda _: {1: frozenset()})
    monkeypatch.setattr("pokemon_red_completion.gen1_indoor_encounters.wild_tables",
                        lambda _, *, medium: {0x3B: [(5, 1)]})
    terrain = Terrain(0x3B, 1, ((True, True),) * 2, ((False, False),) * 2,
                      ((False, False),) * 2, ((FLOOR_TILE, FLOOR_TILE),) * 2, ((0,),))
    with pytest.raises(CartridgeReadError, match="cartridge bytes"):
        indoor_land_encounter_mask(rom, replace(terrain, blocks=((block_id,),)))
