"""Focused ROM-free tests for the bounded fishing foundation.

Verifies:
1. ItemId additions (OLD_ROD=0x4C, GOOD_ROD=0x4D beside existing SUPER_ROD=0x4E).
2. Strict mapping of observed bag entries to available RodKind values without inventing ownership.
3. Deterministic derivation of fishable shoreline stances from Terrain in canonical order.
4. Out-of-bounds exclusions, nonstandable land, diagonal/non-orthogonal cases, and input mutations.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from pokemon_red_completion.fishing import (
    ROD_ITEM_TO_KIND,
    ROD_KIND_TO_ITEM,
    ShorelineStance,
    available_rod_kinds,
    fishable_shoreline_stances,
    item_for_rod_kind,
    rod_kind_for_item,
)
from pokemon_red_completion.gen1_cartridge import RodKind
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import Direction
from pokemon_red_completion.observation import ItemId, RawGameState


def _make_terrain(
    walkable: tuple[tuple[bool, ...], ...],
    water: tuple[tuple[bool, ...], ...],
) -> Terrain:
    """Construct a ROM-free Terrain instance with explicit walkable and water grids."""
    tiles = tuple(tuple(0x01 if w else 0x02 for w in row) for row in walkable)
    grass = tuple(tuple(False for _ in row) for row in walkable)
    return Terrain(
        map_id=0,
        tileset=0,
        walkable=walkable,
        grass=grass,
        water=water,
        tiles=tiles,
    )


# ---------------------------------------------------------------------------
# ItemId and RodKind mapping tests
# ---------------------------------------------------------------------------


def test_rod_item_ids_match_gen1_constants() -> None:
    assert ItemId.OLD_ROD == 0x4C
    assert ItemId.GOOD_ROD == 0x4D
    assert ItemId.SUPER_ROD == 0x4E
    assert ItemId.OLD_ROD.value == 0x4C
    assert ItemId.GOOD_ROD.value == 0x4D
    assert ItemId.SUPER_ROD.value == 0x4E
    assert ItemId(0x4C) is ItemId.OLD_ROD
    assert ItemId(0x4D) is ItemId.GOOD_ROD
    assert ItemId(0x4E) is ItemId.SUPER_ROD
    assert len({ItemId.OLD_ROD, ItemId.GOOD_ROD, ItemId.SUPER_ROD}) == 3


def test_rod_item_mapping_and_lookups() -> None:
    assert rod_kind_for_item(ItemId.OLD_ROD) == RodKind.OLD
    assert rod_kind_for_item(ItemId.GOOD_ROD) == RodKind.GOOD
    assert rod_kind_for_item(ItemId.SUPER_ROD) == RodKind.SUPER
    assert rod_kind_for_item(0x4C) == RodKind.OLD
    assert rod_kind_for_item(0x4D) == RodKind.GOOD
    assert rod_kind_for_item(0x4E) == RodKind.SUPER
    assert rod_kind_for_item(ItemId.POKE_BALL) is None
    assert rod_kind_for_item(0x01) is None

    assert item_for_rod_kind(RodKind.OLD) == ItemId.OLD_ROD
    assert item_for_rod_kind(RodKind.GOOD) == ItemId.GOOD_ROD
    assert item_for_rod_kind(RodKind.SUPER) == ItemId.SUPER_ROD

    assert ROD_ITEM_TO_KIND[ItemId.OLD_ROD] == RodKind.OLD
    assert ROD_ITEM_TO_KIND[ItemId.GOOD_ROD] == RodKind.GOOD
    assert ROD_ITEM_TO_KIND[ItemId.SUPER_ROD] == RodKind.SUPER

    assert ROD_KIND_TO_ITEM[RodKind.OLD] == ItemId.OLD_ROD
    assert ROD_KIND_TO_ITEM[RodKind.GOOD] == ItemId.GOOD_ROD
    assert ROD_KIND_TO_ITEM[RodKind.SUPER] == ItemId.SUPER_ROD


def test_rod_lookup_negative_cases() -> None:
    with pytest.raises(TypeError, match="item_id must be an integer"):
        rod_kind_for_item("0x4C")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="item_id must be an integer"):
        rod_kind_for_item(True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="rod_kind must be a RodKind"):
        item_for_rod_kind("old")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Bag mapping tests (available_rod_kinds)
# ---------------------------------------------------------------------------


def test_available_rod_kinds_missing_or_empty_does_not_invent_ownership() -> None:
    assert available_rod_kinds(None) == ()
    assert available_rod_kinds(()) == ()
    assert available_rod_kinds([]) == ()
    assert available_rod_kinds({}) == ()

    raw_none = RawGameState(True, 0, 0, 0, 0, 0, bag_items=None)
    assert available_rod_kinds(raw_none) == ()

    raw_empty = RawGameState(True, 0, 0, 0, 0, 0, bag_items=())
    assert available_rod_kinds(raw_empty) == ()


def test_available_rod_kinds_individual_and_combination() -> None:
    assert available_rod_kinds(((ItemId.OLD_ROD, 1),)) == (RodKind.OLD,)
    assert available_rod_kinds(((ItemId.GOOD_ROD, 1),)) == (RodKind.GOOD,)
    assert available_rod_kinds(((ItemId.SUPER_ROD, 1),)) == (RodKind.SUPER,)

    # Multiple rods returned in canonical order (OLD, GOOD, SUPER) regardless of bag order
    mixed = (
        (ItemId.SUPER_ROD, 1),
        (ItemId.OLD_ROD, 2),
    )
    assert available_rod_kinds(mixed) == (RodKind.OLD, RodKind.SUPER)

    all_three = (
        (ItemId.SUPER_ROD, 1),
        (ItemId.OLD_ROD, 1),
        (ItemId.GOOD_ROD, 1),
    )
    assert available_rod_kinds(all_three) == (
        RodKind.OLD,
        RodKind.GOOD,
        RodKind.SUPER,
    )


def test_available_rod_kinds_with_mapping_and_raw_state() -> None:
    mapping = {ItemId.GOOD_ROD: 1, ItemId.POKE_BALL: 5}
    assert available_rod_kinds(mapping) == (RodKind.GOOD,)

    raw = RawGameState(
        True,
        0,
        0,
        0,
        0,
        0,
        bag_items=((ItemId.SUPER_ROD, 1), (ItemId.POTION, 3)),
    )
    assert available_rod_kinds(raw) == (RodKind.SUPER,)


def test_available_rod_kinds_zero_quantity_does_not_invent_ownership() -> None:
    # Quantity 0 means not possessed
    assert available_rod_kinds(((ItemId.OLD_ROD, 0),)) == ()
    assert available_rod_kinds(((ItemId.GOOD_ROD, 0), (ItemId.SUPER_ROD, 0))) == ()
    assert available_rod_kinds({ItemId.OLD_ROD: 0, ItemId.SUPER_ROD: 1}) == (
        RodKind.SUPER,
    )


def test_available_rod_kinds_unrelated_items_only() -> None:
    unrelated = ((ItemId.POKE_BALL, 10), (ItemId.POTION, 5), (ItemId.FULL_HEAL, 2))
    assert available_rod_kinds(unrelated) == ()


def test_available_rod_kinds_duplicate_entries_deduplicated() -> None:
    duplicates = ((ItemId.OLD_ROD, 1), (ItemId.OLD_ROD, 2))
    assert available_rod_kinds(duplicates) == (RodKind.OLD,)


def test_available_rod_kinds_strict_validation_negative_cases() -> None:
    # Non-iterable / wrong type
    with pytest.raises(TypeError, match="bag_entries must be an iterable"):
        available_rod_kinds(123)  # type: ignore[arg-type]

    # Malformed entry: not a tuple/list
    with pytest.raises(TypeError, match="each bag entry must be a 2-tuple"):
        available_rod_kinds(["not_a_tuple"])  # type: ignore[list-item]

    # Malformed entry: wrong length
    with pytest.raises(ValueError, match="must have exactly 2 elements"):
        available_rod_kinds([(ItemId.OLD_ROD,)])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="must have exactly 2 elements"):
        available_rod_kinds([(ItemId.OLD_ROD, 1, 99)])  # type: ignore[list-item]

    # Malformed item_id: non-int or bool
    with pytest.raises(TypeError, match="item_id must be an integer"):
        available_rod_kinds([("old_rod", 1)])  # type: ignore[list-item]
    with pytest.raises(TypeError, match="item_id must be an integer"):
        available_rod_kinds([(True, 1)])  # type: ignore[list-item]

    # Malformed quantity: non-int or bool
    with pytest.raises(TypeError, match="quantity must be an integer"):
        available_rod_kinds([(ItemId.OLD_ROD, "1")])  # type: ignore[list-item]
    with pytest.raises(TypeError, match="quantity must be an integer"):
        available_rod_kinds([(ItemId.OLD_ROD, 1.5)])  # type: ignore[list-item]
    with pytest.raises(TypeError, match="quantity must be an integer"):
        available_rod_kinds([(ItemId.OLD_ROD, False)])  # type: ignore[list-item]

    # Malformed quantity: negative
    with pytest.raises(ValueError, match="cannot be negative"):
        available_rod_kinds([(ItemId.OLD_ROD, -1)])


# ---------------------------------------------------------------------------
# ShorelineStance unit tests
# ---------------------------------------------------------------------------


def test_shoreline_stance_properties() -> None:
    stance = ShorelineStance(
        at=(3, 5),
        direction=Direction.DOWN,
        water_at=(4, 5),
    )
    assert stance.at == (3, 5)
    assert stance.direction == Direction.DOWN
    assert stance.water_at == (4, 5)


def test_shoreline_stance_immutability() -> None:
    stance = ShorelineStance(at=(1, 2), direction=Direction.UP, water_at=(0, 2))
    with pytest.raises(FrozenInstanceError):
        stance.at = (0, 0)  # type: ignore[misc]


def test_shoreline_stance_validation_negative_cases() -> None:
    # Invalid 'at' coordinate
    with pytest.raises(TypeError, match="stance coordinate 'at' must be a tuple of two integers"):
        ShorelineStance(at=[1, 2], direction=Direction.DOWN, water_at=(2, 2))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="stance coordinate 'at' must be a tuple of two integers"):
        ShorelineStance(at=(1,), direction=Direction.DOWN, water_at=(2, 2))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="stance coordinate 'at' must be a tuple of two integers"):
        ShorelineStance(at=(1, "2"), direction=Direction.DOWN, water_at=(2, 2))  # type: ignore[arg-type]

    # Invalid 'direction'
    with pytest.raises(TypeError, match="stance direction must be a Direction"):
        ShorelineStance(at=(1, 2), direction="down", water_at=(2, 2))  # type: ignore[arg-type]

    # Invalid 'water_at' coordinate
    with pytest.raises(TypeError, match="water coordinate .* must be a tuple"):
        ShorelineStance(at=(1, 2), direction=Direction.DOWN, water_at=[2, 2])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="water coordinate .* must be a tuple"):
        ShorelineStance(at=(1, 2), direction=Direction.DOWN, water_at=(2, True))  # type: ignore[arg-type]

    # Inconsistent water coordinate with direction delta
    with pytest.raises(ValueError, match="water coordinate .* does not match facing"):
        ShorelineStance(at=(1, 2), direction=Direction.DOWN, water_at=(1, 3))


# ---------------------------------------------------------------------------
# fishable_shoreline_stances derivation tests
# ---------------------------------------------------------------------------


def test_fishable_shoreline_stances_simple_horizontal() -> None:
    # 1 row, 2 cols: (0, 0) is land, (0, 1) is water
    terrain = _make_terrain(
        walkable=((True, False),),
        water=((False, True),),
    )
    stances = fishable_shoreline_stances(terrain)
    assert len(stances) == 1
    assert stances[0] == ShorelineStance(
        at=(0, 0),
        direction=Direction.RIGHT,
        water_at=(0, 1),
    )


def test_canonical_direction_order_center_island() -> None:
    # 3x3 grid: center (1, 1) is standable land, surrounded orthogonally by water
    terrain = _make_terrain(
        walkable=(
            (False, False, False),
            (False, True, False),
            (False, False, False),
        ),
        water=(
            (False, True, False),
            (True, False, True),
            (False, True, False),
        ),
    )
    stances = fishable_shoreline_stances(terrain)
    assert len(stances) == 4

    # Canonical direction order is strictly DOWN, UP, LEFT, RIGHT
    assert [s.direction for s in stances] == [
        Direction.DOWN,
        Direction.UP,
        Direction.LEFT,
        Direction.RIGHT,
    ]
    assert [s.at for s in stances] == [(1, 1), (1, 1), (1, 1), (1, 1)]
    assert [s.water_at for s in stances] == [
        (2, 1),  # DOWN
        (0, 1),  # UP
        (1, 0),  # LEFT
        (1, 2),  # RIGHT
    ]


def test_canonical_coordinate_order_row_major() -> None:
    # 2x2 grid: top row (0,0) and (0,1) are land; bottom row (1,0) and (1,1) are water
    terrain = _make_terrain(
        walkable=(
            (True, True),
            (False, False),
        ),
        water=(
            (False, False),
            (True, True),
        ),
    )
    stances = fishable_shoreline_stances(terrain)
    assert len(stances) == 2
    # (0, 0) facing DOWN before (0, 1) facing DOWN
    assert stances[0] == ShorelineStance(
        at=(0, 0),
        direction=Direction.DOWN,
        water_at=(1, 0),
    )
    assert stances[1] == ShorelineStance(
        at=(0, 1),
        direction=Direction.DOWN,
        water_at=(1, 1),
    )


def test_out_of_bounds_exclusion() -> None:
    # 1x1 grid with land only: all orthogonal neighbors are out-of-bounds
    terrain = _make_terrain(
        walkable=((True,),),
        water=((False,),),
    )
    assert fishable_shoreline_stances(terrain) == ()

    # 2x1 grid with land at (0, 0) and water at (1, 0)
    # (0, 0) faces UP (-1, 0), LEFT (0, -1), RIGHT (0, 1) all out of bounds
    # Only DOWN (1, 0) is valid in-bounds water
    terrain2 = _make_terrain(
        walkable=((True,), (False,)),
        water=((False,), (True,)),
    )
    stances = fishable_shoreline_stances(terrain2)
    assert len(stances) == 1
    assert stances[0] == ShorelineStance(
        at=(0, 0),
        direction=Direction.DOWN,
        water_at=(1, 0),
    )


def test_diagonal_water_is_not_orthogonally_adjacent() -> None:
    # 2x2 grid: land at (0, 0), water at (1, 1), others are unwalkable solid (not water)
    terrain = _make_terrain(
        walkable=(
            (True, False),
            (False, False),
        ),
        water=(
            (False, False),
            (False, True),
        ),
    )
    # (0, 1) and (1, 0) are not water, so (0, 0) has NO orthogonal water neighbor
    assert fishable_shoreline_stances(terrain) == ()


def test_nonstandable_land_and_water_exclusions() -> None:
    # Unwalkable solid tile adjacent to water does NOT produce a stance
    solid_facing_water = _make_terrain(
        walkable=((False, False),),
        water=((False, True),),
    )
    assert fishable_shoreline_stances(solid_facing_water) == ()

    # Water tile adjacent to water does NOT produce a stance (surfing is not land)
    water_facing_water = _make_terrain(
        walkable=((False, False),),
        water=((True, True),),
    )
    assert fishable_shoreline_stances(water_facing_water) == ()

    # Water tile adjacent to land does NOT produce a stance
    water_facing_land = _make_terrain(
        walkable=((False, True),),
        water=((True, False),),
    )
    stances = fishable_shoreline_stances(water_facing_land)
    # Only land at (0, 1) facing LEFT to water at (0, 0) is a stance;
    # water at (0, 0) facing RIGHT to land is NOT a stance.
    assert len(stances) == 1
    assert stances[0] == ShorelineStance(
        at=(0, 1),
        direction=Direction.LEFT,
        water_at=(0, 0),
    )

    # Tile with both walkable=True and water=True is water, not land
    dual_tile = _make_terrain(
        walkable=((True, False),),
        water=((True, True),),
    )
    assert fishable_shoreline_stances(dual_tile) == ()


def test_no_water_or_all_water_returns_empty() -> None:
    all_land = _make_terrain(
        walkable=((True, True), (True, True)),
        water=((False, False), (False, False)),
    )
    assert fishable_shoreline_stances(all_land) == ()

    all_water = _make_terrain(
        walkable=((False, False), (False, False)),
        water=((True, True), (True, True)),
    )
    assert fishable_shoreline_stances(all_water) == ()


def test_invalid_terrain_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="terrain must be a Terrain instance"):
        fishable_shoreline_stances("not_terrain")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="terrain must be a Terrain instance"):
        fishable_shoreline_stances(None)  # type: ignore[arg-type]


def test_gen1_fishing_reexport() -> None:
    import pokemon_red_completion.gen1_fishing as gen1_fishing

    assert gen1_fishing.ROD_ITEM_TO_KIND is ROD_ITEM_TO_KIND
    assert gen1_fishing.ROD_KIND_TO_ITEM is ROD_KIND_TO_ITEM
    assert gen1_fishing.ShorelineStance is ShorelineStance
    assert gen1_fishing.available_rod_kinds is available_rod_kinds
    assert gen1_fishing.fishable_shoreline_stances is fishable_shoreline_stances
    assert gen1_fishing.rod_kind_for_item is rod_kind_for_item
    assert gen1_fishing.item_for_rod_kind is item_for_rod_kind

