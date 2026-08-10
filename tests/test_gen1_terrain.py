"""Where a player can stand, decoded from bytes laid out by hand.

Split the same way the map reader is, and for the same reason. The record in
``docs/evidence/terrain-2026-08-10.json`` says what Kanto's ground is like; it
cannot say whether the decoder reads it correctly, because a recorded output
compared against itself agrees with any bug. So the decoding is exercised
against a cartridge small enough to write out.

The load-bearing fact here is *which* tile of a block the player stands on. Every
one of the four choices produces a grid, and three of them look plausible, so the
answer came from measurement: 98.3% of Kanto's warps land on passable ground
under the lower-left reading, against 34.7%, 34.4% and 62.5% for the others.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS
from pokemon_red_completion.gen1_terrain import (
    TILESET_COUNT,
    TILESET_ENTRY_BYTES,
    TILESET_TABLE,
    Terrain,
    steps_between,
    terrain_for,
    tilesets,
)

RECORD = Path("docs/evidence/terrain-2026-08-10.json")

ROM_BYTES = 0x10000
MAP_BANK = 1  # in bank 1 a banked address equals its flat offset
#: The tileset deliberately lives in a *different* bank from the map.
#:
#: In bank 1 a banked address and a flat offset are the same number, so a
#: fixture that put everything there could not tell a banked read from a flat
#: one -- and the whole point of the collision pointer is that it is flat while
#: the blockset pointer beside it is banked. Bank 2 makes them differ by $4000.
TILESET_BANK = 2
COLLISION_AT = 0x2000  # bank 0, because that is where collision lists live
BLOCKSET_ADDRESS = 0x5000
BLOCKSET_AT = TILESET_BANK * 0x4000 + (BLOCKSET_ADDRESS - 0x4000)
HEADER_AT = 0x4100
BLOCKS_AT = 0x4200

WALKABLE_TILE = 0x01
SOLID_TILE = 0x02
GRASS_TILE = 0x52


def cartridge(
    *,
    block_ids: list[list[int]],
    blocks: dict[int, list[int]],
    walkable: tuple[int, ...] = (WALKABLE_TILE, GRASS_TILE),
    grass_tile: int = GRASS_TILE,
) -> bytes:
    """A ROM holding one tileset and one map.

    ``blocks`` maps a block id to its sixteen tiles, written row-major as the
    cartridge does: four rows of four.
    """

    data = bytearray(ROM_BYTES)
    height, width = len(block_ids), len(block_ids[0])

    data[COLLISION_AT : COLLISION_AT + len(walkable)] = bytes(walkable)
    data[COLLISION_AT + len(walkable)] = 0xFF

    for block_id, tiles in blocks.items():
        assert len(tiles) == 16, "a block is four rows of four tiles"
        at = BLOCKSET_AT + 16 * block_id
        data[at : at + 16] = bytes(tiles)

    for index in range(TILESET_COUNT):
        at = TILESET_TABLE + TILESET_ENTRY_BYTES * index
        data[at] = TILESET_BANK
        data[at + 1 : at + 3] = BLOCKSET_ADDRESS.to_bytes(2, "little")
        data[at + 3 : at + 5] = BLOCKSET_ADDRESS.to_bytes(2, "little")  # graphics, unused
        data[at + 5 : at + 7] = COLLISION_AT.to_bytes(2, "little")
        data[at + 10] = grass_tile

    data[HEADER_AT] = 0  # tileset 0
    data[HEADER_AT + 1] = height
    data[HEADER_AT + 2] = width
    data[HEADER_AT + 3 : HEADER_AT + 5] = BLOCKS_AT.to_bytes(2, "little")
    for y, row in enumerate(block_ids):
        for x, block_id in enumerate(row):
            data[BLOCKS_AT + y * width + x] = block_id

    data[MAP_HEADER_BANKS] = MAP_BANK
    data[MAP_HEADER_POINTERS : MAP_HEADER_POINTERS + 2] = HEADER_AT.to_bytes(2, "little")
    return bytes(data)


def block(*rows: tuple[int, int, int, int]) -> list[int]:
    return [tile for row in rows for tile in row]


#: A block whose four two-by-two cells differ, so that reading the wrong corner
#: of a cell produces a visibly different grid.
CORNERS = block(
    (SOLID_TILE, SOLID_TILE, SOLID_TILE, SOLID_TILE),
    (WALKABLE_TILE, SOLID_TILE, SOLID_TILE, SOLID_TILE),
    (SOLID_TILE, SOLID_TILE, SOLID_TILE, SOLID_TILE),
    (SOLID_TILE, SOLID_TILE, SOLID_TILE, SOLID_TILE),
)


def test_the_player_stands_on_the_lower_left_tile_of_a_cell() -> None:
    """The measured choice, and the one thing here that cannot be guessed.

    Only the lower-left tile of this block is passable. If the decoder read any
    other corner the whole map would come out solid, which is exactly what three
    of the four readings do to Kanto.
    """

    rom = cartridge(block_ids=[[0]], blocks={0: CORNERS})

    terrain = terrain_for(rom, 0, tilesets(rom))

    assert (terrain.height, terrain.width) == (2, 2)
    assert terrain.walkable == ((True, False), (False, False))
    assert terrain.tiles == (
        (WALKABLE_TILE, SOLID_TILE),
        (SOLID_TILE, SOLID_TILE),
    )


def test_a_block_id_selects_which_sixteen_tiles_are_used() -> None:
    """Two blocks side by side must not be read from the same place."""

    open_block = block(*([(WALKABLE_TILE,) * 4] * 4))
    shut_block = block(*([(SOLID_TILE,) * 4] * 4))
    rom = cartridge(block_ids=[[0, 1]], blocks={0: open_block, 1: shut_block})

    terrain = terrain_for(rom, 0, tilesets(rom))

    assert terrain.walkable == ((True, True, False, False), (True, True, False, False))


def test_block_rows_are_laid_out_across_then_down() -> None:
    """A map is stored row-major, so a stride mistake transposes it."""

    open_block = block(*([(WALKABLE_TILE,) * 4] * 4))
    shut_block = block(*([(SOLID_TILE,) * 4] * 4))
    # Two rows of three, and the layout is chosen so that a stride using the
    # height instead of the width reads a *different* block: the wrong index
    # lands on the open block at the end of row one.
    rom = cartridge(block_ids=[[0, 1, 0], [1, 1, 1]], blocks={0: open_block, 1: shut_block})

    terrain = terrain_for(rom, 0, tilesets(rom))

    assert (terrain.height, terrain.width) == (4, 6)
    assert terrain.can_stand(0, 0), "row zero starts on the open block"
    assert terrain.can_stand(0, 4), "and ends on one"
    assert not terrain.can_stand(2, 0), "row one is solid all the way across"
    assert not terrain.can_stand(2, 4)


def test_tall_grass_is_found_where_the_tileset_says_it_is() -> None:
    """Grass is walkable ground that also starts encounters."""

    grass_block = block(*([(GRASS_TILE,) * 4] * 4))
    plain = block(*([(WALKABLE_TILE,) * 4] * 4))
    rom = cartridge(block_ids=[[0, 1]], blocks={0: grass_block, 1: plain})

    terrain = terrain_for(rom, 0, tilesets(rom))

    assert all(all(row) for row in terrain.walkable), "grass can be walked on"
    assert terrain.grass[0][0] and terrain.grass[1][1]
    assert not terrain.grass[0][2] and not terrain.grass[1][3]


def test_a_tileset_without_grass_reports_none() -> None:
    """Most tilesets use $FF for "no grass", and caves must not sprout any."""

    # The map is paved with tile $FF, the very value that means "no grass".
    # Without that, comparing every tile against the sentinel would find
    # nothing anyway and the test would pass whatever the code did.
    sentinel = block(*([(0xFF,) * 4] * 4))
    rom = cartridge(block_ids=[[0]], blocks={0: sentinel}, grass_tile=0xFF)

    sets = tilesets(rom)
    terrain = terrain_for(rom, 0, sets)

    assert not sets[0].has_grass
    assert not any(any(row) for row in terrain.grass), "$FF means no grass, not grass everywhere"


def test_the_collision_pointer_is_a_flat_offset_not_a_banked_one() -> None:
    """The mismatch that hid this table for an afternoon.

    Blockset pointers are banked; collision pointers name bank 0 directly. A
    search that assumed one convention for the whole entry could not find it,
    and a decoder that assumes the wrong one reads noise.
    """

    rom = cartridge(block_ids=[[0]], blocks={0: CORNERS})

    (tileset,) = {tilesets(rom)[0]}

    assert tileset.collision == COLLISION_AT
    assert tileset.collision < 0x4000, "bank 0, so the pointer is its own offset"
    assert tileset.walkable == frozenset({WALKABLE_TILE, GRASS_TILE})


def test_a_tileset_nobody_can_stand_in_is_refused() -> None:
    rom = bytearray(cartridge(block_ids=[[0]], blocks={0: CORNERS}))
    rom[COLLISION_AT] = 0xFF  # an immediately empty list

    with pytest.raises(CartridgeReadError, match="stand nowhere"):
        tilesets(bytes(rom))


def test_a_collision_list_that_never_ends_is_refused() -> None:
    rom = bytearray(cartridge(block_ids=[[0]], blocks={0: CORNERS}))
    for offset in range(COLLISION_AT, COLLISION_AT + 400):
        rom[offset] = offset % 0xFE  # never the terminator

    with pytest.raises(CartridgeReadError, match="does not end"):
        tilesets(bytes(rom))


def test_a_blockset_pointer_outside_the_bank_window_is_refused() -> None:
    rom = bytearray(cartridge(block_ids=[[0]], blocks={0: CORNERS}))
    rom[TILESET_TABLE + 1 : TILESET_TABLE + 3] = (0x1234).to_bytes(2, "little")

    with pytest.raises(CartridgeReadError, match="outside the bank window"):
        tilesets(bytes(rom))


def open_terrain(picture: list[str]) -> Terrain:
    walkable = tuple(tuple(cell != "#" for cell in row) for row in picture)
    tiles = tuple(tuple(1 if cell != "#" else 0 for cell in row) for row in picture)
    return Terrain(map_id=0, tileset=0, walkable=walkable, grass=walkable, tiles=tiles)


def test_terrain_rejects_misaligned_coordinate_grids() -> None:
    with pytest.raises(ValueError, match="non-empty rectangular"):
        Terrain(map_id=0, tileset=0, walkable=(), grass=(), tiles=())

    with pytest.raises(ValueError, match="grass must match"):
        Terrain(
            map_id=0,
            tileset=0,
            walkable=((True, True),),
            grass=((False,),),
            tiles=((1, 1),),
        )

    with pytest.raises(ValueError, match="tiles must match"):
        Terrain(
            map_id=0,
            tileset=0,
            walkable=((True, True),),
            grass=((False, False),),
            tiles=((1,),),
        )


def test_a_walk_goes_around_what_it_cannot_cross() -> None:
    """This is what a chapter module writes out by hand today."""

    terrain = open_terrain(
        [
            "....",
            ".##.",
            ".##.",
            "....",
        ]
    )

    walk = steps_between(terrain, (0, 0), (3, 0))

    assert walk[0] == (0, 0)
    assert walk[-1] == (3, 0)
    assert len(walk) == 4, "straight down the left edge"
    assert all(terrain.can_stand(*step) for step in walk)


def test_a_walk_to_somewhere_walled_off_is_empty_rather_than_wrong() -> None:
    terrain = open_terrain(
        [
            "..#.",
            "..#.",
        ]
    )

    assert steps_between(terrain, (0, 0), (0, 3)) == ()
    assert steps_between(terrain, (0, 0), (0, 2)) == (), "cannot stand on a wall"
    assert steps_between(terrain, (0, 0), (0, 0)) == ((0, 0),)
    # Asking to walk to a wall you are somehow already on is still no route.
    # This is the only input that tells the early check apart from the search,
    # which is why it is here rather than the check being deleted as dead.
    assert steps_between(terrain, (0, 2), (0, 2)) == ()


def test_a_walk_cannot_begin_inside_a_wall() -> None:
    """Every square in a returned route includes its start and must be standable."""

    terrain = open_terrain(["#.", ".."])

    assert steps_between(terrain, (0, 0), (0, 1)) == ()


def test_each_step_of_a_walk_is_one_square_in_one_direction() -> None:
    """A path that teleports is not a path a player can follow."""

    # Wide open, so a diagonal shortcut would be taken if one were on offer.
    # A player cannot move diagonally, so the walk must be five squares.
    terrain = open_terrain(["...", "...", "..."])

    walk = steps_between(terrain, (0, 0), (2, 2))

    assert len(walk) == 5, "four orthogonal moves, not two diagonal ones"
    for before, after in zip(walk, walk[1:], strict=False):
        assert abs(before[0] - after[0]) + abs(before[1] - after[1]) == 1


@pytest.fixture(scope="module")
def record() -> dict:
    if not RECORD.exists():  # pragma: no cover - the record is committed
        pytest.skip(f"{RECORD} has not been produced")
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_the_reading_that_makes_warps_stand_up_is_the_one_used(record: dict) -> None:
    """The measurement that settled the block layout.

    A warp is a square the player has to stand on. Almost all of Kanto's do
    under this reading; the six that do not are landing spots in Seafoam Islands
    and Rock Tunnel, reached by falling through a hole rather than by walking.
    """

    assert record["by_title"]["red"]["warps_on_passable_ground"] >= 0.98


def test_both_cartridges_describe_the_same_ground(record: dict) -> None:
    assert record["cartridges_agree"] is True
    assert "every decoded Terrain" in record["comparison_scope"]
    assert "storage pointers" in record["comparison_scope"]
    assert record["terrain_grids_agree"] is True
    assert record["tileset_traversal_rules_agree"] is True
    assert record["raw_tileset_records_agree"] is False
    assert record["raw_tileset_differences"] == [
        {"tileset": index, "fields": ["blockset"]}
        for index in (2, 3, 5, 6, 7, 9, 10, 12, 22)
    ]
    assert record["by_title"]["red"]["standable_squares"] == 48216
    assert record["by_title"]["red"]["grass_squares"] == 2537


def test_only_three_tilesets_grow_grass(record: dict) -> None:
    """Wild encounters elsewhere happen on cave floor, not in grass."""

    assert record["by_title"]["red"]["tilesets"] == 24
    assert record["by_title"]["red"]["tilesets_with_grass"] == [0, 3, 23]


def test_pallet_town_comes_out_looking_like_pallet_town(record: dict) -> None:
    """Two houses, a lab, a fence, and grass only at the road north.

    The cheapest possible check that the grid is real rather than plausible: it
    is a picture, and Pallet Town is a place people can recognise.
    """

    pallet = record["by_title"]["red"]["pallet_town"]

    assert pallet["size"] == [18, 20]
    assert pallet["picture"][0] == '...#.....#""#.....#.'
    assert pallet["picture"][-1] == "##..################"
    assert '"' not in "".join(pallet["picture"][2:]), "the only grass is at the north road"


def test_the_walk_across_pallet_town_is_computed_not_written(record: dict) -> None:
    """From one door to another, found by search over cartridge data."""

    pallet = record["by_title"]["red"]["pallet_town"]
    walk = [tuple(step) for step in pallet["computed_walk"]]

    assert walk[0] == tuple(pallet["doors"][0])
    assert walk[-1] == tuple(pallet["doors"][-1])
    assert len(walk) == 16
    for before, after in zip(walk, walk[1:], strict=False):
        assert abs(before[0] - after[0]) + abs(before[1] - after[1]) == 1
