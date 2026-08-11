from __future__ import annotations

import pytest

from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_trainer_sight import (
    TrainerFacing,
    TrainerHeader,
    trainer_headers,
    trainer_sight_zones,
)
from pokemon_red_completion.gen1_traversal import MapObjectEvent, map_object_events
from pokemon_red_completion.observation import CurrentMapObject, RawGameState

HEADER_POINTERS = 0x01AE
HEADER_BANKS = 0xC23D
MAP_HEADER = 0x4100
OBJECTS = 0x4200
SCRIPT = 0x4300
TRAINERS = 0x4400


def trainer_cartridge() -> bytearray:
    data = bytearray(0x10000)
    data[HEADER_BANKS] = 1
    data[HEADER_POINTERS : HEADER_POINTERS + 2] = (MAP_HEADER).to_bytes(2, "little")
    data[MAP_HEADER + 7 : MAP_HEADER + 9] = (SCRIPT).to_bytes(2, "little")
    data[MAP_HEADER + 9] = 0
    data[MAP_HEADER + 10 : MAP_HEADER + 12] = (OBJECTS).to_bytes(2, "little")
    data[SCRIPT : SCRIPT + 8] = bytes((0x21, 0x00, 0xD0, 0x21, 0x00, 0x44, 0xC9, 0x00))

    cursor = OBJECTS
    data[cursor] = 0x0A
    data[cursor + 1] = 0
    data[cursor + 2] = 0
    data[cursor + 3] = 3
    data[cursor + 4 : cursor + 12] = bytes((6, 9, 11, 0xFF, 0xD3, 0x41, 0xE8, 5))
    data[cursor + 12 : cursor + 20] = bytes((6, 8, 8, 0xFF, 0xD2, 0x42, 0xE8, 6))
    data[cursor + 20 : cursor + 28] = bytes((7, 6, 7, 0xFF, 0xD0, 0x43, 0xE7, 5))

    data[TRAINERS : TRAINERS + 25] = bytes(
        (
            2,
            0x20,
            0x48,
            0xD7,
            0x10,
            0x40,
            0x20,
            0x40,
            0x30,
            0x40,
            0x40,
            0x40,
            3,
            0x40,
            0x49,
            0xD7,
            0x50,
            0x40,
            0x60,
            0x40,
            0x70,
            0x40,
            0x80,
            0x40,
            0xFF,
        )
    )
    return data


def test_object_and_header_reads_join_independent_cartridge_structures() -> None:
    rom = bytes(trainer_cartridge())
    events = map_object_events(rom, {0})

    assert [(item.object_index, item.trainer_class, item.trainer_set) for item in events] == [
        (1, 0xE8, 5),
        (2, 0xE8, 6),
        (3, 0xE7, 5),
    ]
    assert trainer_headers(rom, {0}) == (
        TrainerHeader(0, 2, 2, 10, 0x4400),
        TrainerHeader(0, 3, 4, 19, 0x440C),
    )


def test_scripted_trainer_objects_do_not_require_sight_headers() -> None:
    rom = trainer_cartridge()
    for direction_offset in (8, 16, 24):
        rom[OBJECTS + direction_offset] = 0xFF

    assert trainer_headers(bytes(rom), {0}) == ()


def test_header_candidate_requires_the_real_stride_and_sentinel() -> None:
    mutated = trainer_cartridge()
    mutated[TRAINERS + 24] = 0

    with pytest.raises(CartridgeReadError, match="0 validated"):
        trainer_headers(bytes(mutated), {0})


@pytest.mark.parametrize(
    ("offset", "value"),
    (
        (0, 1),  # the standard table no longer starts at trainer object slot two
        (1, 0x21),  # engage distance must occupy only the high nybble
        (2, 0x00),  # defeated-event pointer leaves the event flag region
        (5, 0x00),  # battle text pointer leaves the switchable ROM window
        (12, 2),  # the twelve-byte stride no longer reaches object slot three
    ),
)
def test_header_decode_rejects_each_independent_structural_corruption(
    offset: int,
    value: int,
) -> None:
    mutated = trainer_cartridge()
    mutated[TRAINERS + offset] = value

    with pytest.raises(CartridgeReadError, match="0 validated"):
        trainer_headers(bytes(mutated), {0})


def test_active_lane_uses_live_facing_while_defeated_lane_disappears() -> None:
    events = (
        MapObjectEvent(0, 6, 5, 7, 0xFF, 0xD3, 0x41, 1, 0xE8, 5),
        MapObjectEvent(0, 7, 2, 3, 0xFF, 0xD0, 0x42, 2, 0xE7, 5),
    )
    headers = (
        TrainerHeader(0, 1, 2, 9, 0x4400),
        TrainerHeader(0, 2, 2, 10, 0x440C),
    )
    flags = bytearray(2)
    flags[1] = 1 << 1
    raw = RawGameState(True, 0, 17, 12, 1, 0, event_flags=bytes(flags))
    current = (
        CurrentMapObject(1, 6, (5, 7), 1, 0x20, 0x0C),
        CurrentMapObject(2, 7, (2, 3), 0, 0xFF, 0x00),
    )

    zones = trainer_sight_zones(headers, events, raw, current)

    assert zones[0].defeated
    assert zones[0].lane == ()
    assert zones[0].facing is TrainerFacing.RIGHT
    assert not zones[1].defeated
    assert not zones[1].visible
    assert zones[1].lane == ((3, 3), (4, 3))


def test_unknown_event_memory_keeps_the_trainer_conservatively_active() -> None:
    event = MapObjectEvent(0, 7, 2, 3, 0xFF, 0xD0, 0x41, 1, 0xE7, 5)
    header = TrainerHeader(0, 1, 2, 9, 0x4400)
    raw = RawGameState(True, 0, 17, 12, 1, 0, event_flags=None)
    current = CurrentMapObject(1, 7, (2, 3), 0, 0xFF)

    zone = trainer_sight_zones((header,), (event,), raw, (current,))[0]

    assert zone.active
    assert zone.lane == ((3, 3), (4, 3))


def test_offscreen_default_facing_does_not_override_the_cartridge_object() -> None:
    event = MapObjectEvent(0, 7, 2, 3, 0xFF, 0xD2, 0x41, 1, 0xE7, 5)
    header = TrainerHeader(0, 1, 2, 9, 0x4400)
    raw = RawGameState(True, 0, 17, 12, 1, 0, event_flags=None)
    current = CurrentMapObject(
        1,
        7,
        (2, 3),
        0,
        0xFF,
        0x00,  # stale/default DOWN while the cartridge object faces LEFT
    )

    zone = trainer_sight_zones((header,), (event,), raw, (current,))[0]

    assert zone.facing is TrainerFacing.LEFT
    assert zone.lane == ((2, 2), (2, 1))
