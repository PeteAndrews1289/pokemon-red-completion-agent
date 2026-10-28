"""Explicit Route12 Flute adapter reusing the ordinary one-off capture runtime."""

from functools import lru_cache

from .gen1_acquisition import route16_snorlax_consumption_flag, static_encounters
from .gen1_traversal import map_object_events
from .observation import EventFlag, ItemId, MapId
from .red_static_capture import RedStaticCaptureTarget
from .rom import verify_rom_bytes


@lru_cache(maxsize=2)
def route12_snorlax_target(rom: bytes) -> RedStaticCaptureTarget:
    """Bind pinned script species/level, cartridge object and observed native event."""
    verify_rom_bytes(rom)
    entries = [
        e for e in static_encounters(rom) if e.species == 143 and e.map_id == int(MapId.ROUTE_12)
    ]
    objects = [o for o in map_object_events(rom, {int(MapId.ROUTE_12)}) if o.sprite_id == 67]
    if len(entries) != 1 or len(objects) != 1:
        raise ValueError("Route12 Snorlax cartridge source differs")
    entry, obj = entries[0], objects[0]
    if entry.at != obj.at or entry.level != 30 or obj.is_trainer:
        raise ValueError("Route12 Snorlax script/object identity differs")
    return RedStaticCaptureTarget(
        143,
        132,
        30,
        obj.map_id,
        obj.object_index,
        obj.sprite_id,
        obj.at,
        int(EventFlag.BEAT_ROUTE12_SNORLAX),
    )


@lru_cache(maxsize=2)
def route16_snorlax_target(rom: bytes) -> RedStaticCaptureTarget:
    """Bind the exact second native source, retaining independent consumption."""
    verify_rom_bytes(rom)
    entries = [e for e in static_encounters(rom) if (e.species, e.map_id) == (143, 27)]
    objects = [o for o in map_object_events(rom, {27}) if o.sprite_id == 67]
    if len(entries) != 1 or len(objects) != 1:
        raise ValueError("Route16 Snorlax cartridge source differs")
    entry, obj = entries[0], objects[0]
    if entry.at != obj.at or obj.at != (10, 26) or entry.level != 30 or obj.is_trainer:
        raise ValueError("Route16 Snorlax script/object identity differs")
    return RedStaticCaptureTarget(
        143, 132, 30, 27, obj.object_index, 67, obj.at,
        route16_snorlax_consumption_flag(rom),
    )


def activate_snorlax(actions, reader, emulator):
    """Use the held Flute once; introduction/target verification belongs to caller."""
    from .actions import MacroActionKind
    from .lavender import DEFAULT_LAVENDER_TIMING, _open_bag, _select_bag_item
    from .surge import _pulse

    raw = reader.read()
    if raw.battle_state or not dict(raw.bag_items or ()).get(int(ItemId.POKE_FLUTE)):
        raise ValueError("Snorlax activation requires the held Flute in the field")
    _open_bag(actions, emulator, DEFAULT_LAVENDER_TIMING)
    _select_bag_item(actions, emulator, ItemId.POKE_FLUTE, DEFAULT_LAVENDER_TIMING)
    _pulse(actions, MacroActionKind.CONFIRM, frames=120)
