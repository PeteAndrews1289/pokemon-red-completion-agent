"""Bounded fishing foundation for Generation I and title-neutral planning.

Provides strict mapping from observed bag entries to available :class:`RodKind`
values without inventing ownership, and derives deterministic fishable shoreline
stances from :class:`Terrain`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pokemon_red_completion.gen1_cartridge import RodKind
from pokemon_red_completion.gen1_terrain import Terrain
from pokemon_red_completion.gen1_traversal import Direction
from pokemon_red_completion.observation import ItemId, RawGameState

#: Mapping from rod ItemId to RodKind.
ROD_ITEM_TO_KIND: Mapping[int, RodKind] = {
    ItemId.OLD_ROD: RodKind.OLD,
    ItemId.GOOD_ROD: RodKind.GOOD,
    ItemId.SUPER_ROD: RodKind.SUPER,
}

#: Reverse mapping from RodKind to ItemId.
ROD_KIND_TO_ITEM: Mapping[RodKind, ItemId] = {
    RodKind.OLD: ItemId.OLD_ROD,
    RodKind.GOOD: ItemId.GOOD_ROD,
    RodKind.SUPER: ItemId.SUPER_ROD,
}

_ROD_ORDER: tuple[RodKind, ...] = (
    RodKind.OLD,
    RodKind.GOOD,
    RodKind.SUPER,
)

_CANONICAL_DIRECTIONS: tuple[Direction, ...] = (
    Direction.DOWN,
    Direction.UP,
    Direction.LEFT,
    Direction.RIGHT,
)


def rod_kind_for_item(item_id: int | ItemId) -> RodKind | None:
    """Return the :class:`RodKind` corresponding to a rod item ID, or None."""
    if not isinstance(item_id, int) or isinstance(item_id, bool):
        raise TypeError(f"item_id must be an integer, got {item_id!r}")
    return ROD_ITEM_TO_KIND.get(int(item_id))


def item_for_rod_kind(rod_kind: RodKind) -> ItemId:
    """Return the :class:`ItemId` corresponding to a :class:`RodKind`."""
    if not isinstance(rod_kind, RodKind):
        raise TypeError(f"rod_kind must be a RodKind instance, got {rod_kind!r}")
    return ROD_KIND_TO_ITEM[rod_kind]


def available_rod_kinds(
    bag_entries: (
        RawGameState
        | Mapping[Any, int]
        | Iterable[tuple[int | ItemId, int]]
        | None
    ),
) -> tuple[RodKind, ...]:
    """Map observed bag entries to available :class:`RodKind` values.

    Ownership is never invented: missing, empty, or zero-quantity entries
    mean no rod is available. Malformed entries raise TypeError or ValueError.

    Returns available rods in canonical order: (OLD, GOOD, SUPER).
    """
    if bag_entries is None:
        return ()

    if isinstance(bag_entries, RawGameState):
        if bag_entries.bag_items is None:
            return ()
        raw_entries: Iterable[Any] = bag_entries.bag_items
    elif isinstance(bag_entries, Mapping):
        raw_entries = bag_entries.items()
    elif isinstance(bag_entries, Iterable):
        raw_entries = bag_entries
    else:
        raise TypeError(
            f"bag_entries must be an iterable of entries, a mapping, RawGameState, or None; "
            f"got {type(bag_entries).__name__}"
        )

    available: set[RodKind] = set()
    for entry in raw_entries:
        if not isinstance(entry, (tuple, list)):
            raise TypeError(
                f"each bag entry must be a 2-tuple (item_id, quantity), "
                f"got {type(entry).__name__}: {entry!r}"
            )
        if len(entry) != 2:
            raise ValueError(
                f"each bag entry must have exactly 2 elements (item_id, quantity), "
                f"got {len(entry)}: {entry!r}"
            )
        item_raw, quantity_raw = entry
        if not isinstance(item_raw, int) or isinstance(item_raw, bool):
            raise TypeError(
                f"bag entry item_id must be an integer, got {type(item_raw).__name__}: {item_raw!r}"
            )
        if not isinstance(quantity_raw, int) or isinstance(quantity_raw, bool):
            raise TypeError(
                f"bag entry quantity must be an integer, "
                f"got {type(quantity_raw).__name__}: {quantity_raw!r}"
            )
        if quantity_raw < 0:
            raise ValueError(
                f"bag entry quantity cannot be negative, got {quantity_raw}"
            )
        if quantity_raw > 0:
            rod = ROD_ITEM_TO_KIND.get(int(item_raw))
            if rod is not None:
                available.add(rod)

    return tuple(rod for rod in _ROD_ORDER if rod in available)


@dataclass(frozen=True, slots=True)
class ShorelineStance:
    """A standable land coordinate facing an orthogonally adjacent water coordinate."""

    at: tuple[int, int]
    direction: Direction
    water_at: tuple[int, int]

    def __post_init__(self) -> None:
        if not (
            isinstance(self.at, tuple)
            and len(self.at) == 2
            and isinstance(self.at[0], int)
            and not isinstance(self.at[0], bool)
            and isinstance(self.at[1], int)
            and not isinstance(self.at[1], bool)
        ):
            raise TypeError("stance coordinate 'at' must be a tuple of two integers (y, x)")
        if not isinstance(self.direction, Direction):
            raise TypeError(
                f"stance direction must be a Direction instance, "
                f"got {type(self.direction).__name__}"
            )
        if not (
            isinstance(self.water_at, tuple)
            and len(self.water_at) == 2
            and isinstance(self.water_at[0], int)
            and not isinstance(self.water_at[0], bool)
            and isinstance(self.water_at[1], int)
            and not isinstance(self.water_at[1], bool)
        ):
            raise TypeError(
                "water coordinate 'water_at' must be a tuple of two integers (y, x)"
            )
        dy, dx = self.direction.delta
        expected_water = (self.at[0] + dy, self.at[1] + dx)
        if self.water_at != expected_water:
            raise ValueError(
                f"water coordinate {self.water_at} does not match "
                f"facing {self.direction.value} from {self.at} (expected {expected_water})"
            )


def fishable_shoreline_stances(terrain: Terrain) -> tuple[ShorelineStance, ...]:
    """Derive deterministic fishable shoreline stances from Terrain.

    A fishable shoreline stance is a standable land coordinate facing an
    orthogonally adjacent water coordinate, in canonical order (row-major
    (y, x), then Direction order: DOWN, UP, LEFT, RIGHT), excluding out-of-bounds.
    """
    if not isinstance(terrain, Terrain):
        raise TypeError(
            f"terrain must be a Terrain instance, got {type(terrain).__name__}"
        )

    stances: list[ShorelineStance] = []
    height = terrain.height
    width = terrain.width

    for y in range(height):
        for x in range(width):
            if not terrain.can_stand(y, x) or terrain.can_surf(y, x):
                continue
            for direction in _CANONICAL_DIRECTIONS:
                dy, dx = direction.delta
                water_y = y + dy
                water_x = x + dx
                if not (0 <= water_y < height and 0 <= water_x < width):
                    continue
                if terrain.can_surf(water_y, water_x):
                    stances.append(
                        ShorelineStance(
                            at=(y, x),
                            direction=direction,
                            water_at=(water_y, water_x),
                        )
                    )
    return tuple(stances)
