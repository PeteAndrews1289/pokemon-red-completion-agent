"""Focused ROM-free tests for the bounded fishing foundation.

Verifies:
1. ItemId additions (OLD_ROD=0x4C, GOOD_ROD=0x4D beside existing SUPER_ROD=0x4E).
2. Strict mapping of observed bag entries to available RodKind values without inventing ownership.
3. Deterministic derivation of fishable shoreline stances from Terrain in canonical order.
4. Out-of-bounds exclusions, nonstandable land, diagonal/non-orthogonal cases, and input mutations.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.fishing import (
    ROD_ITEM_TO_KIND,
    ROD_KIND_TO_ITEM,
    ActionExecutor,
    FishingCastError,
    FishingCastExecutor,
    FishingCastOutcome,
    FishingCastReader,
    FishingCastResult,
    FishingTiming,
    ShorelineStance,
    available_rod_kinds,
    execute_fishing_cast,
    fishable_shoreline_stances,
    item_for_rod_kind,
    rod_kind_for_item,
)
from pokemon_red_completion.gen1_cartridge import RodKind
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import Direction
from pokemon_red_completion.observation import (
    InputReadiness,
    ItemId,
    MapId,
    MenuCursorState,
    RawGameState,
)


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
    assert gen1_fishing.FishingCastError is FishingCastError
    assert gen1_fishing.FishingCastOutcome is FishingCastOutcome
    assert gen1_fishing.FishingTiming is FishingTiming
    assert gen1_fishing.ActionExecutor is ActionExecutor
    assert gen1_fishing.FishingCastReader is FishingCastReader
    assert gen1_fishing.FishingCastResult is FishingCastResult
    assert gen1_fishing.FishingCastExecutor is FishingCastExecutor
    assert gen1_fishing.execute_fishing_cast is execute_fishing_cast


# ---------------------------------------------------------------------------
# FishingTiming & FishingCastResult validation tests
# ---------------------------------------------------------------------------


def test_fishing_timing_validation() -> None:
    timing = FishingTiming()
    assert timing.menu_wait_frames == 180
    assert timing.cursor_wait_frames == 120
    assert timing.dialogue_wait_frames == 180
    assert timing.max_menu_moves == 32
    assert timing.max_settle_pulses == 16

    custom = FishingTiming(
        menu_wait_frames=60,
        cursor_wait_frames=40,
        dialogue_wait_frames=70,
        max_menu_moves=10,
        max_settle_pulses=5,
    )
    assert custom.menu_wait_frames == 60
    assert custom.cursor_wait_frames == 40
    assert custom.dialogue_wait_frames == 70
    assert custom.max_menu_moves == 10
    assert custom.max_settle_pulses == 5

    # Rejection of non-positive or non-int values
    for field_name in (
        "menu_wait_frames",
        "cursor_wait_frames",
        "dialogue_wait_frames",
        "max_menu_moves",
        "max_settle_pulses",
    ):
        with pytest.raises(ValueError, match="must be a positive integer"):
            FishingTiming(**{field_name: 0})
        with pytest.raises(ValueError, match="must be a positive integer"):
            FishingTiming(**{field_name: -5})
        with pytest.raises(ValueError, match="must be a positive integer"):
            FishingTiming(**{field_name: True})  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="must be a positive integer"):
            FishingTiming(**{field_name: "100"})  # type: ignore[arg-type]


def test_fishing_cast_result_validation() -> None:
    res = FishingCastResult(
        outcome=FishingCastOutcome.NO_BITE,
        rod_kind=RodKind.OLD,
        actions=5,
        frames=300,
        facing_action_used=False,
    )
    assert res.outcome is FishingCastOutcome.NO_BITE
    assert res.rod_kind is RodKind.OLD
    assert res.actions == 5
    assert res.frames == 300
    assert res.facing_action_used is False

    with pytest.raises(TypeError, match="outcome must be a FishingCastOutcome"):
        FishingCastResult(
            outcome="no_bite",  # type: ignore[arg-type]
            rod_kind=RodKind.OLD,
            actions=5,
            frames=300,
        )
    with pytest.raises(TypeError, match="rod_kind must be a RodKind"):
        FishingCastResult(
            outcome=FishingCastOutcome.NO_BITE,
            rod_kind="old",  # type: ignore[arg-type]
            actions=5,
            frames=300,
        )
    with pytest.raises(ValueError, match="actions must be a non-negative integer"):
        FishingCastResult(
            outcome=FishingCastOutcome.NO_BITE,
            rod_kind=RodKind.OLD,
            actions=-1,
            frames=300,
        )
    with pytest.raises(ValueError, match="actions must be a non-negative integer"):
        FishingCastResult(
            outcome=FishingCastOutcome.NO_BITE,
            rod_kind=RodKind.OLD,
            actions=True,  # type: ignore[arg-type]
            frames=300,
        )
    with pytest.raises(ValueError, match="frames must be a non-negative integer"):
        FishingCastResult(
            outcome=FishingCastOutcome.NO_BITE,
            rod_kind=RodKind.OLD,
            actions=5,
            frames=-10,
        )
    with pytest.raises(ValueError, match="frames must be a non-negative integer"):
        FishingCastResult(
            outcome=FishingCastOutcome.NO_BITE,
            rod_kind=RodKind.OLD,
            actions=5,
            frames=True,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="facing_action_used must be a bool"):
        FishingCastResult(
            outcome=FishingCastOutcome.NO_BITE,
            rod_kind=RodKind.OLD,
            actions=5,
            frames=300,
            facing_action_used=1,  # type: ignore[arg-type]
        )
    with pytest.raises(FrozenInstanceError):
        res.actions = 10  # type: ignore[misc]


def test_fishing_cast_result_public_dict_does_not_leak_identity() -> None:
    result = FishingCastResult(
        outcome=FishingCastOutcome.NO_BITE,
        rod_kind=RodKind.SUPER,
        actions=14,
        frames=1500,
        facing_action_used=True,
    )
    d = result.public_dict()
    assert d["schema"] == "pokemon.red.fishing-cast.v1"
    assert d["status"] == "no_bite"
    assert d["rod_kind"] == "super"
    assert d["actions"] == 14
    assert d["frames"] == 1500
    assert d["wild_encounter"] is False
    assert d["no_bite"] is True
    assert d["facing_action_used"] is True
    assert d["forced_support_step"] is False
    assert d["learned_goal_authority"] is False
    assert d["training_examples"] == 0

    assert set(d.keys()) == {
        "schema",
        "status",
        "rod_kind",
        "actions",
        "frames",
        "wild_encounter",
        "no_bite",
        "facing_action_used",
        "forced_support_step",
        "learned_goal_authority",
        "training_examples",
    }

    # Verify no map, coordinate, species, or level leaked in keys or values
    for k, v in d.items():
        k_str = str(k).lower()
        v_str = str(v).lower()
        for forbidden in (
            "map",
            "coord",
            "species",
            "level",
            "pallet",
            "cerulean",
            "party",
            "money",
            "badge",
            "event",
        ):
            assert forbidden not in k_str, f"forbidden '{forbidden}' in key {k}"
            assert forbidden not in v_str, f"forbidden '{forbidden}' in value {v}"


# ---------------------------------------------------------------------------
# Simulator test harness
# ---------------------------------------------------------------------------


def _base_raw(
    *,
    game_started: bool = True,
    map_id: int | None = MapId.PALLET_TOWN,
    player_x: int | None = 10,
    player_y: int | None = 1,
    battle_state: int = 0,
    bag_items: tuple[tuple[int, int], ...] | None = (
        (ItemId.OLD_ROD, 1),
        (ItemId.SUPER_ROD, 1),
    ),
    money: int = 3000,
    party_hp: tuple[int, ...] = (20,),
    party_species: tuple[int, ...] = (0x99,),
) -> RawGameState:
    return RawGameState(
        game_started=game_started,
        map_id=map_id,
        player_x=player_x,
        player_y=player_y,
        battle_state=battle_state,
        bag_items=bag_items,
        player_money=money,
        party_count=len(party_species),
        party_species_ids=party_species,
        party_levels=(5,) * len(party_species),
        party_hp=party_hp,
        party_max_hp=(20,) * len(party_species),
        party_status=(0,) * len(party_species),
        party_moves=((1, 0, 0, 0),) * len(party_species),
        party_pp=((35, 0, 0, 0),) * len(party_species),
        badge_bits=0,
        event_flags=b"\x00" * 320,
        status_flags_1=0,
    )


class _MockEmulator:
    def __init__(self, frame_count: int = 1000) -> None:
        self.frame_count = frame_count


class _FishingSimulation:
    def __init__(
        self,
        raw_state: RawGameState | None = None,
        *,
        initial_facing: str = "down",
        # "no_bite", "wild_encounter_immediate", "wild_encounter_delayed"
        outcome_mode: str = "no_bite",
        dialogue_settle_delay: int = 1,
        emulator: _MockEmulator | None = None,
        fail_start_menu: bool = False,
        fail_bag_menu: bool = False,
        fail_submenu: bool = False,
        stuck_start_menu: bool = False,
        stuck_bag_menu: bool = False,
        stuck_submenu: bool = False,
        stuck_dialogue: bool = False,
        drift_on_move: bool = False,
        ignore_facing_turn: bool = False,
        not_ready_after_facing: bool = False,
        unexpected_settle_battle_state: int | None = None,
        initial_dialogue_visible: bool = False,
        initial_ready: bool = True,
    ) -> None:
        self.raw = raw_state if raw_state is not None else _base_raw()
        self.facing = initial_facing
        self.outcome_mode = outcome_mode
        self.dialogue_settle_delay = dialogue_settle_delay
        self.emulator = emulator
        self.input_ready = initial_ready
        self.stage = "field"
        self.start_cursor = 0
        self.bag_cursor = 0
        self.submenu_cursor = 0
        self.settle_pulses = 0
        self.dialogue_box_visible = initial_dialogue_visible
        self.actions_executed = 0
        self.recorded_actions: list[MacroAction] = []

        self.fail_start_menu = fail_start_menu
        self.fail_bag_menu = fail_bag_menu
        self.fail_submenu = fail_submenu
        self.stuck_start_menu = stuck_start_menu
        self.stuck_bag_menu = stuck_bag_menu
        self.stuck_submenu = stuck_submenu
        self.stuck_dialogue = stuck_dialogue
        self.drift_on_move = drift_on_move
        self.ignore_facing_turn = ignore_facing_turn
        self.not_ready_after_facing = not_ready_after_facing
        self.unexpected_settle_battle_state = unexpected_settle_battle_state

    def read(self) -> RawGameState:
        return self.raw

    def read_input_readiness(self) -> InputReadiness:
        return InputReadiness(0 if self.input_ready else 1, 0, 0, 0, 0)

    def read_player_facing(self) -> str:
        return self.facing

    def read_bottom_dialogue_box_visible(self) -> bool:
        return self.dialogue_box_visible

    def read_menu_cursor_state(self) -> MenuCursorState:
        if self.stage == "start_menu":
            if self.fail_start_menu:
                raise RuntimeError("simulated corrupt start menu")
            return MenuCursorState(
                selected_visible_index=self.start_cursor,
                scroll_offset=0,
                maximum_visible_index=6,
                top_x=11,
                top_y=0,
            )
        if self.stage == "bag_menu":
            if self.fail_bag_menu:
                raise RuntimeError("simulated corrupt bag menu")
            visible_idx = min(self.bag_cursor, 3)
            scroll_off = max(0, self.bag_cursor - 3)
            return MenuCursorState(
                selected_visible_index=visible_idx,
                scroll_offset=scroll_off,
                maximum_visible_index=3,
                top_x=4,
                top_y=1,
            )
        if self.stage == "item_submenu":
            if self.fail_submenu:
                raise RuntimeError("simulated corrupt item submenu")
            return MenuCursorState(
                selected_visible_index=self.submenu_cursor,
                scroll_offset=0,
                maximum_visible_index=1,
                top_x=11,
                top_y=8,
            )
        raise RuntimeError(f"read_menu_cursor_state called outside menu stages: {self.stage}")

    def execute(self, action: MacroAction) -> object:
        self.actions_executed += 1
        self.recorded_actions.append(action)
        if (
            self.emulator is not None
            and action.kind is MacroActionKind.WAIT
            and isinstance(action.repeat, int)
        ):
            self.emulator.frame_count += action.repeat

        if action.kind is MacroActionKind.OPEN_MENU:
            if self.stage == "field":
                self.stage = "start_menu"
                self.start_cursor = 0
        elif action.kind is MacroActionKind.MOVE:
            if self.stage == "field":
                if not self.ignore_facing_turn and isinstance(action.value, str):
                    self.facing = action.value
                if self.drift_on_move:
                    assert self.raw.player_x is not None
                    self.raw = replace(self.raw, player_x=self.raw.player_x + 1)
                if self.not_ready_after_facing:
                    self.input_ready = False
            elif self.stage == "start_menu":
                if not self.stuck_start_menu:
                    if action.value == "down":
                        self.start_cursor = min(self.start_cursor + 1, 6)
                    elif action.value == "up":
                        self.start_cursor = max(self.start_cursor - 1, 0)
            elif self.stage == "bag_menu":
                if not self.stuck_bag_menu:
                    if action.value == "down":
                        self.bag_cursor += 1
                    elif action.value == "up":
                        self.bag_cursor = max(self.bag_cursor - 1, 0)
            elif self.stage == "item_submenu":
                if not self.stuck_submenu:
                    if action.value == "down":
                        self.submenu_cursor = min(self.submenu_cursor + 1, 1)
                    elif action.value == "up":
                        self.submenu_cursor = max(self.submenu_cursor - 1, 0)
        elif action.kind is MacroActionKind.CONFIRM:
            if self.stage == "start_menu":
                if self.start_cursor == 2:  # ITEM
                    self.stage = "bag_menu"
                    self.bag_cursor = 0
            elif self.stage == "bag_menu":
                self.stage = "item_submenu"
                self.submenu_cursor = 1 if self.stuck_submenu else 0
            elif self.stage == "item_submenu":
                if self.submenu_cursor == 0:  # USE
                    self.stage = "settlement"
                    if self.unexpected_settle_battle_state is not None:
                        self.raw = replace(
                            self.raw,
                            battle_state=self.unexpected_settle_battle_state,
                        )
                    elif self.outcome_mode == "wild_encounter_immediate":
                        self.raw = replace(self.raw, battle_state=1)
                    else:
                        self.dialogue_box_visible = True
            elif self.stage == "settlement":
                self.settle_pulses += 1
                if not self.stuck_dialogue:
                    if (
                        self.outcome_mode == "wild_encounter_delayed"
                        and self.settle_pulses >= self.dialogue_settle_delay
                    ):
                        self.dialogue_box_visible = False
                        self.raw = replace(self.raw, battle_state=1)
                    elif self.settle_pulses >= self.dialogue_settle_delay:
                        self.dialogue_box_visible = False
                        self.input_ready = True
        return action


# ---------------------------------------------------------------------------
# Executor Happy Path Tests
# ---------------------------------------------------------------------------


def test_fishing_cast_no_bite_already_facing() -> None:
    sim = _FishingSimulation(initial_facing="down", outcome_mode="no_bite")
    emulator = _MockEmulator(1000)
    sim.emulator = emulator
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    executor = FishingCastExecutor(actions=sim, reader=sim, emulator=emulator)
    result = executor.execute(stance)

    assert result.outcome is FishingCastOutcome.NO_BITE
    # Default selection picked SUPER_ROD (the highest rod order available)
    assert result.rod_kind is RodKind.SUPER
    assert result.facing_action_used is False
    assert result.actions > 0
    assert result.frames > 0
    assert emulator.frame_count > 1000

    public = result.public_dict()
    assert public["status"] == "no_bite"
    assert public["wild_encounter"] is False
    assert public["no_bite"] is True
    assert public["facing_action_used"] is False


def test_fishing_cast_no_bite_facing_turn() -> None:
    sim = _FishingSimulation(initial_facing="right", outcome_mode="no_bite")
    emulator = _MockEmulator(2000)
    sim.emulator = emulator
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    executor = FishingCastExecutor(actions=sim, reader=sim, emulator=emulator)
    result = executor.execute(stance)

    assert result.outcome is FishingCastOutcome.NO_BITE
    assert result.facing_action_used is True
    assert sim.facing == "down"
    # First recorded action should be MOVE down
    assert sim.recorded_actions[0] == MacroAction(MacroActionKind.MOVE, "down")

    public = result.public_dict()
    assert public["status"] == "no_bite"
    assert public["facing_action_used"] is True


def test_fishing_cast_wild_encounter_immediate() -> None:
    sim = _FishingSimulation(initial_facing="down", outcome_mode="wild_encounter_immediate")
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    executor = FishingCastExecutor(actions=sim, reader=sim)
    result = executor.execute(stance)

    assert result.outcome is FishingCastOutcome.WILD_ENCOUNTER
    assert result.rod_kind is RodKind.SUPER
    assert result.facing_action_used is False

    public = result.public_dict()
    assert public["status"] == "wild_encounter"
    assert public["wild_encounter"] is True
    assert public["no_bite"] is False


def test_fishing_cast_wild_encounter_delayed() -> None:
    sim = _FishingSimulation(
        initial_facing="down",
        outcome_mode="wild_encounter_delayed",
        dialogue_settle_delay=2,
    )
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    executor = FishingCastExecutor(actions=sim, reader=sim)
    result = executor.execute(stance)

    assert result.outcome is FishingCastOutcome.WILD_ENCOUNTER
    assert sim.settle_pulses == 2


def test_fishing_cast_explicit_rod_selection() -> None:
    sim = _FishingSimulation(initial_facing="down", outcome_mode="no_bite")
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    executor = FishingCastExecutor(actions=sim, reader=sim)
    result = executor.execute(stance, rod=RodKind.OLD)

    assert result.outcome is FishingCastOutcome.NO_BITE
    assert result.rod_kind is RodKind.OLD
    public = result.public_dict()
    assert public["rod_kind"] == "old"


def test_fishing_cast_default_rod_selection_picks_last_in_order() -> None:
    raw = _base_raw(
        bag_items=(
            (ItemId.GOOD_ROD, 1),
            (ItemId.OLD_ROD, 1),
        )
    )
    sim = _FishingSimulation(raw, initial_facing="down", outcome_mode="no_bite")
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    executor = FishingCastExecutor(actions=sim, reader=sim)
    result = executor.execute(stance)

    assert result.rod_kind is RodKind.GOOD


def test_fishing_cast_bag_scrolling_navigation() -> None:
    # Rod placed deep in the bag (index 5, requiring scrolling down)
    raw = _base_raw(
        bag_items=(
            (ItemId.POTION, 2),
            (ItemId.ANTIDOTE, 1),
            (ItemId.SUPER_POTION, 1),
            (ItemId.HYPER_POTION, 1),
            (ItemId.AWAKENING, 1),
            (ItemId.SUPER_ROD, 1),
        )
    )
    sim = _FishingSimulation(raw, initial_facing="down", outcome_mode="no_bite")
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    executor = FishingCastExecutor(actions=sim, reader=sim)
    result = executor.execute(stance)

    assert result.outcome is FishingCastOutcome.NO_BITE
    assert result.rod_kind is RodKind.SUPER
    assert sim.bag_cursor == 5


def test_execute_fishing_cast_wrapper() -> None:
    sim = _FishingSimulation(initial_facing="down", outcome_mode="no_bite")
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    result = execute_fishing_cast(sim, sim, stance, rod=RodKind.OLD)
    assert result.outcome is FishingCastOutcome.NO_BITE
    assert result.rod_kind is RodKind.OLD


# ---------------------------------------------------------------------------
# Preconditions & Starting Gate Failure Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_kwargs", "sim_kwargs", "error_match"),
    [
        ({"game_started": False}, {}, "starting gate is invalid or not ready"),
        ({"map_id": None}, {}, "starting gate is invalid or not ready"),
        ({"player_x": None}, {}, "starting gate is invalid or not ready"),
        ({"player_y": None}, {}, "starting gate is invalid or not ready"),
        ({"battle_state": 1}, {}, "starting gate is invalid or not ready"),
        ({"battle_state": 2}, {}, "starting gate is invalid or not ready"),
        ({"bag_items": None}, {}, "starting gate is invalid or not ready"),
        ({}, {"initial_ready": False}, "starting gate is invalid or not ready"),
        ({}, {"initial_dialogue_visible": True}, "starting gate is invalid or not ready"),
    ],
)
def test_starting_gate_precondition_failures(
    raw_kwargs: dict[str, object],
    sim_kwargs: dict[str, object],
    error_match: str,
) -> None:
    raw = _base_raw(**raw_kwargs)  # type: ignore[arg-type]
    sim = _FishingSimulation(raw, **sim_kwargs)  # type: ignore[arg-type]
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    executor = FishingCastExecutor(actions=sim, reader=sim)
    with pytest.raises(FishingCastError, match=error_match):
        executor.execute(stance)


def test_starting_gate_position_mismatch() -> None:
    raw = _base_raw(player_y=5, player_x=5)
    sim = _FishingSimulation(raw)
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    executor = FishingCastExecutor(actions=sim, reader=sim)
    with pytest.raises(FishingCastError, match="player position does not match"):
        executor.execute(stance)


def test_argument_type_errors() -> None:
    sim = _FishingSimulation()
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    with pytest.raises(TypeError, match="timing must be a FishingTiming"):
        FishingCastExecutor(actions=sim, reader=sim, timing="invalid")  # type: ignore[arg-type]

    executor = FishingCastExecutor(actions=sim, reader=sim)
    with pytest.raises(TypeError, match="stance must be a ShorelineStance"):
        executor.execute("not_stance")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="rod must be a RodKind"):
        executor.execute(stance, rod="super")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Facing Turn Failure Tests
# ---------------------------------------------------------------------------


def test_facing_turn_failures() -> None:
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    # Player position drifted during facing turn
    sim1 = _FishingSimulation(initial_facing="right", drift_on_move=True)
    with pytest.raises(FishingCastError, match="fishing cast altered protected game state"):
        FishingCastExecutor(actions=sim1, reader=sim1).execute(stance)

    # Player facing failed to update
    sim2 = _FishingSimulation(initial_facing="right", ignore_facing_turn=True)
    with pytest.raises(FishingCastError, match="failed to face shoreline candidate direction"):
        FishingCastExecutor(actions=sim2, reader=sim2).execute(stance)

    # Input not ready after facing turn
    sim3 = _FishingSimulation(initial_facing="right", not_ready_after_facing=True)
    with pytest.raises(FishingCastError, match="failed to face shoreline candidate direction"):
        FishingCastExecutor(actions=sim3, reader=sim3).execute(stance)


# ---------------------------------------------------------------------------
# Rod Selection Failure Tests
# ---------------------------------------------------------------------------


def test_rod_selection_failures() -> None:
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    # No rods in bag
    raw_no_rods = _base_raw(bag_items=((ItemId.POKE_BALL, 5),))
    sim1 = _FishingSimulation(raw_no_rods)
    with pytest.raises(FishingCastError, match="no fishing rod observed in bag"):
        FishingCastExecutor(actions=sim1, reader=sim1).execute(stance)

    # Requested rod missing from bag
    raw_with_old = _base_raw(bag_items=((ItemId.OLD_ROD, 1),))
    sim2 = _FishingSimulation(raw_with_old)
    with pytest.raises(FishingCastError, match="requested rod SUPER is not in observed bag"):
        FishingCastExecutor(actions=sim2, reader=sim2).execute(stance, rod=RodKind.SUPER)

    # Rod item with 0 quantity
    raw_zero_qty = _base_raw(bag_items=((ItemId.SUPER_ROD, 0),))
    sim3 = _FishingSimulation(raw_zero_qty)
    with pytest.raises(FishingCastError, match="no fishing rod observed in bag"):
        FishingCastExecutor(actions=sim3, reader=sim3).execute(stance)


# ---------------------------------------------------------------------------
# Menu Navigation Failure Tests
# ---------------------------------------------------------------------------


def test_menu_navigation_failures() -> None:
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    # Start menu cursor read fails (unknown UI)
    sim1 = _FishingSimulation(fail_start_menu=True)
    with pytest.raises(FishingCastError, match="unknown UI during Start menu navigation"):
        FishingCastExecutor(actions=sim1, reader=sim1).execute(stance)

    # Start menu cursor stuck
    sim2 = _FishingSimulation(stuck_start_menu=True)
    with pytest.raises(FishingCastError, match="could not select ITEM in Start menu"):
        FishingCastExecutor(
            actions=sim2,
            reader=sim2,
            timing=FishingTiming(max_menu_moves=5),
        ).execute(stance)

    # Bag menu cursor read fails (unknown UI)
    sim3 = _FishingSimulation(fail_bag_menu=True)
    with pytest.raises(FishingCastError, match="unknown UI during bag menu navigation"):
        FishingCastExecutor(actions=sim3, reader=sim3).execute(stance)

    # Bag menu cursor stuck
    sim4 = _FishingSimulation(stuck_bag_menu=True)
    with pytest.raises(FishingCastError, match="could not select rod at bag index"):
        FishingCastExecutor(
            actions=sim4,
            reader=sim4,
            timing=FishingTiming(max_menu_moves=5),
        ).execute(stance)

    # Submenu cursor read fails (unknown UI)
    sim5 = _FishingSimulation(fail_submenu=True)
    with pytest.raises(FishingCastError, match="unknown UI during item submenu navigation"):
        FishingCastExecutor(actions=sim5, reader=sim5).execute(stance)

    # Submenu cursor stuck away from USE
    sim6 = _FishingSimulation(stuck_submenu=True)
    with pytest.raises(FishingCastError, match="could not select USE in item submenu"):
        FishingCastExecutor(
            actions=sim6,
            reader=sim6,
            timing=FishingTiming(max_menu_moves=5),
        ).execute(stance)


# ---------------------------------------------------------------------------
# Settlement Failure Tests
# ---------------------------------------------------------------------------


def test_settlement_failures() -> None:
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    # Unexpected battle state (e.g. 2: trainer battle)
    sim1 = _FishingSimulation(unexpected_settle_battle_state=2)
    with pytest.raises(FishingCastError, match="unexpected battle state: 2"):
        FishingCastExecutor(actions=sim1, reader=sim1).execute(stance)

    # Dialogue never settles
    sim2 = _FishingSimulation(stuck_dialogue=True)
    with pytest.raises(FishingCastError, match="dialogue did not settle within bounded pulses"):
        FishingCastExecutor(
            actions=sim2,
            reader=sim2,
            timing=FishingTiming(max_settle_pulses=3),
        ).execute(stance)


# ---------------------------------------------------------------------------
# Mutation-Distinguishable Protected State Failure Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field_name", "mutated_value"),
    [
        ("game_started", False),
        ("map_id", MapId.VIRIDIAN_CITY),
        ("player_x", 11),
        ("player_y", 2),
        ("badge_bits", 1),
        ("event_flags", b"\x01" + b"\x00" * 319),
        ("status_flags_1", 1),
        ("party_count", 2),
        ("party_species_ids", (0x99, 0xB3)),
        ("party_levels", (6,)),
        ("party_hp", (19,)),
        ("party_max_hp", (21,)),
        ("party_status", (1,)),
        ("party_moves", ((2, 0, 0, 0),)),
        ("party_pp", ((34, 0, 0, 0),)),
        ("player_money", 2999),
        ("bag_items", ((ItemId.OLD_ROD, 1),)),
    ],
)
def test_protected_state_mutation_rejection(field_name: str, mutated_value: object) -> None:
    base = _base_raw()
    sim = _FishingSimulation(base)
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    orig_read = sim.read

    def mutating_read() -> RawGameState:
        current = orig_read()
        if sim.stage == "settlement":
            return replace(current, **{field_name: mutated_value})  # type: ignore[arg-type]
        return current

    sim.read = mutating_read  # type: ignore[method-assign]

    executor = FishingCastExecutor(actions=sim, reader=sim)
    with pytest.raises(FishingCastError, match="fishing cast altered protected game state"):
        executor.execute(stance)


def test_protected_state_mutation_during_facing_turn() -> None:
    base = _base_raw()
    sim = _FishingSimulation(base, initial_facing="right")
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    orig_read = sim.read

    def mutating_read() -> RawGameState:
        current = orig_read()
        if sim.recorded_actions:  # after facing MOVE pulse
            return replace(current, player_money=999)
        return current

    sim.read = mutating_read  # type: ignore[method-assign]

    executor = FishingCastExecutor(actions=sim, reader=sim)
    with pytest.raises(FishingCastError, match="fishing cast altered protected game state"):
        executor.execute(stance)


# ---------------------------------------------------------------------------
# Auxiliary Executor Tests
# ---------------------------------------------------------------------------


def test_emulator_without_frame_count() -> None:
    sim = _FishingSimulation()
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    # Emulator object without frame_count attribute
    executor1 = FishingCastExecutor(actions=sim, reader=sim, emulator=object())
    with pytest.raises(FishingCastError, match="emulator lacks integer frame_count"):
        executor1.execute(stance)

    # Emulator object with non-integer frame_count
    class _BadEmulator:
        frame_count = "100"

    executor2 = FishingCastExecutor(actions=sim, reader=sim, emulator=_BadEmulator())
    with pytest.raises(FishingCastError, match="emulator lacks integer frame_count"):
        executor2.execute(stance)


def test_actions_executed_internal_fallback() -> None:
    # ActionExecutor that does NOT expose actions_executed attribute
    class _MinimalActions:
        def __init__(self, sim: _FishingSimulation) -> None:
            self._sim = sim

        def execute(self, action: MacroAction) -> object:
            return self._sim.execute(action)

    sim = _FishingSimulation()
    actions = _MinimalActions(sim)
    stance = ShorelineStance(at=(1, 10), direction=Direction.DOWN, water_at=(2, 10))

    executor = FishingCastExecutor(actions=actions, reader=sim)
    result = executor.execute(stance)

    assert result.outcome is FishingCastOutcome.NO_BITE
    assert result.actions > 0


