"""Cartridge-described visible item acquisition; no fixed movement recipe."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .actions import MacroActionKind
from .gen1_acquisition import map_objects
from .observation import MAX_BAG_ITEMS
from .rom import verify_rom_bytes


@dataclass(frozen=True, slots=True)
class RedFieldItem:
    item_id: int
    map_id: int
    object_index: int
    sprite_id: int
    at: tuple[int, int]


def red_field_items(rom: bytes, item_id: int) -> tuple[RedFieldItem, ...]:
    verify_rom_bytes(rom)
    if type(item_id) is not int or not 1 <= item_id <= 250:
        raise ValueError("invalid field item identity")
    return tuple(
        RedFieldItem(item_id, map_id, index, obj.sprite, (obj.y, obj.x))
        for map_id, rows in map_objects(rom).items()
        for index, obj in enumerate(rows, 1)
        if obj.is_item and not obj.is_trainer and obj.extra == (item_id,)
    )


@lru_cache(maxsize=2)
def _field_item_toggle_indices(rom: bytes) -> dict[tuple[int, int], int]:
    """Verified rev0 ToggleableObjectStates; coordinates never enter policy.

    The engine's three-byte map/object/default-state rows are in global flag
    order. See pret/pokered data/maps/toggleable_objects.asm. The checksum-bound
    native table, not a supplied collection history, determines availability.
    """
    verify_rom_bytes(rom)
    table = rom[0xCAEA : 0xCAEA + 3 * 229]
    if table[:9] != bytes((0, 1, 0x11, 1, 5, 0x15, 1, 7, 0x11)) or table[-3:] != bytes(
        (255, 1, 0x15)
    ):
        raise ValueError("finite field-item toggle table differs")
    found = {}
    for index in range(228):
        map_id, object_id, default_state = table[index * 3 : index * 3 + 3]
        key = map_id, object_id
        if (
            map_id == 255
            or not 1 <= object_id <= 15
            or default_state not in (0x11, 0x15)
            or key in found
        ):
            raise ValueError("finite field-item toggle row differs")
        found[key] = index
    return found


def field_item_is_available(rom: bytes, reader, target: RedFieldItem) -> bool:
    """Observe native one-shot availability, including an off-map item."""
    if target not in red_field_items(rom, target.item_id):
        raise ValueError("finite resource is not its cartridge field item")
    index = _field_item_toggle_indices(rom).get((target.map_id, target.object_index))
    if index is None:
        raise ValueError("field item has no native availability flag")
    return not reader.read_toggleable_object_hidden(index)


def collect_visible_field_item(actions, reader, target: RedFieldItem) -> None:
    """Own one adjacent interaction; prove exact item gain and object removal."""
    from .surge import _pulse

    before = reader.read()
    if (
        before.map_id != target.map_id
        or before.battle_state
        or not reader.read_input_readiness().ready
        or reader.read_bottom_dialogue_box_visible()
    ):
        raise ValueError("field item requires a ready matching map")
    objects = [
        o for o in reader.read_current_map_objects() if o.sprite_index == target.object_index
    ]
    if (
        len(objects) != 1
        or not objects[0].visible
        or objects[0].moving
        or (objects[0].picture_id, objects[0].at) != (target.sprite_id, target.at)
    ):
        raise ValueError("field item object is absent or changed")
    direction = reader.read_player_facing()
    dy, dx = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}.get(
        direction, (0, 0)
    )
    if (
        before.player_y is None
        or before.player_x is None
        or (before.player_y + dy, before.player_x + dx) != target.at
    ):
        raise ValueError("field item is not immediately in front of the player")
    if before.bag_items is None:
        raise ValueError("field item bag evidence unavailable")
    expected = dict(before.bag_items)
    if (target.item_id not in expected and len(expected) >= MAX_BAG_ITEMS) or expected.get(
        target.item_id, 0
    ) >= 99:
        raise ValueError("field item has no bag capacity")
    expected[target.item_id] = expected.get(target.item_id, 0) + 1
    boxes, dex, pc = (
        reader.read_all_box_states(),
        reader.read_pokedex_state(),
        reader.read_pc_items(),
    )
    _pulse(actions, MacroActionKind.INTERACT, frames=120)
    for _ in range(48):
        after = reader.read()
        for field in (
            "map_id",
            "player_x",
            "player_y",
            "player_money",
            "party_species_ids",
            "party_levels",
            "party_moves",
            "party_pp",
            "party_hp",
            "party_status",
            "badge_bits",
            "battle_state",
        ):
            if getattr(before, field) != getattr(after, field):
                raise RuntimeError("field pickup changed protected " + field)
        if (
            reader.read_all_box_states() != boxes
            or reader.read_pokedex_state() != dex
            or reader.read_pc_items() != pc
        ):
            raise RuntimeError("field pickup changed collection or PC inventory")
        if after.bag_items is None or dict(after.bag_items) not in (
            dict(before.bag_items),
            expected,
        ):
            raise RuntimeError("field pickup changed unexpected inventory")
        visible = any(
            o.sprite_index == target.object_index and o.visible
            for o in reader.read_current_map_objects()
        )
        if (
            dict(after.bag_items) == expected
            and not visible
            and reader.read_input_readiness().ready
            and not reader.read_bottom_dialogue_box_visible()
        ):
            return
        _pulse(actions, MacroActionKind.CANCEL, frames=120)
    raise RuntimeError("field item interaction did not settle within its bound")
