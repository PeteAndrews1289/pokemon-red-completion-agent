"""Authenticated Seafoam boulder contracts; no puzzle solution or flag writes.

The original routing guard stays closed unless BOTH current systems are settled.
This is deliberately stricter than the cartridge's location-specific Surf gate.
"""

from dataclasses import dataclass

from .gen1_cartridge import CartridgeReadError, bank_offset
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS, SCRIPT_POINTER_OFFSET
from .local_router import LocalGraph
from .observation import event_flag_is_set
from .rom import verify_rom_bytes

SEAFOAM_CURRENT_EVENTS = (2504, 2505, 2512, 2513)
TOGGLEABLE_OBJECT_STATES = 0xCAEA


def seafoam_currents_settled(raw) -> bool:
    return all(event_flag_is_set(raw.event_flags, event) for event in SEAFOAM_CURRENT_EVENTS)


@dataclass(frozen=True)
class SeafoamDrop:
    map_id: int
    at: tuple[int, int]
    boulder_index: int
    event: int
    destination_map: int
    hide_object: int
    show_object: int


def seafoam_drops(rom: bytes, map_id: int) -> tuple[SeafoamDrop, ...]:
    verify_rom_bytes(rom)
    return _decode_drops(rom, map_id)


def apply_seafoam_hole_guards(rom, graphs):
    """Ordinary walking must not claim an unmodelled dungeon-hole transition.

    These are script coordinates, absent from the ordinary warp table. Retain
    outgoing edges to avoid inventing a wall if a diagnostic begins at one, but
    never plan to enter or traverse one. Strength has separate explicit drops.
    """
    result = dict(graphs)
    for map_id in {192, 159, 160, 161}.intersection(result):
        holes = {drop.at for drop in seafoam_drops(rom, map_id)}
        result[map_id] = LocalGraph({
            at: tuple(edge for edge in edges if edge.target not in holes
                      and edge.transient not in holes and not holes.intersection(edge.via))
            for at, edges in result[map_id].edges.items()
        })
    return result


def _decode_drops(rom, map_id):
    def require(ok):
        if not ok:
            raise CartridgeReadError("unsupported Seafoam boulder grammar")

    require(type(map_id) is int and map_id in (192, 159, 160, 161))
    require(type(rom) is bytes and len(rom) > MAP_HEADER_BANKS + map_id)
    bank = rom[MAP_HEADER_BANKS + map_id]

    def read(address, size):
        require(address >= 0x4000 and address + size <= 0x8000)
        offset = bank_offset(bank, address)
        require(offset + size <= len(rom))
        return rom[offset : offset + size]

    def word(data):
        require(len(data) == 2)
        return int.from_bytes(data, "little")

    header = word(rom[MAP_HEADER_POINTERS + 2 * map_id : MAP_HEADER_POINTERS + 2 * map_id + 2])
    script = word(read(header + SCRIPT_POINTER_OFFSET, 2))
    require(read(script, 3) == bytes.fromhex("cd 3c 3c"))
    start = script + 3
    if map_id == 192:
        require(read(start, 5) == bytes.fromhex("21 e7 d7 cb c6"))
        start += 5
    body = read(start, 74)
    # Coordinates/event-bit/hide-show operands are decoded; every branch and
    # call must still have the supported native semantics.
    require(body[:8] == bytes.fromhex("21 60 cd cb 7e cb be 28"))
    require(
        body[9] == 0x21
        and body[12:16] == bytes.fromhex("cd e4 34 d0")
        and body[16] == 0x21
        and body[19:27] == bytes.fromhex("fa 3d cd fe 01 20 0e cb")
        and body[28] == 0x3E
        and body[30:34] == bytes.fromhex("ea 79 d0 3e")
        and body[35:41] == bytes.fromhex("ea 7a d0 18 0c cb")
        and body[42] == 0x3E
        and body[44:48] == bytes.fromhex("ea 79 d0 3e")
        and body[49:68] == bytes.fromhex("ea 7a d0 fa 79 d0 ea 4d cc 3e 11 cd 6d 3e fa 7a d0 ea 4d")
        and body[68:71] == bytes.fromhex("cc 3e 15")
        and body[72:74] == bytes.fromhex("6d 3e")
    )
    require(body[27] in range(0xC6, 0xFF, 8) and body[41] == body[27] + 8)
    first_bit = (body[27] - 0xC6) // 8
    event = (word(body[17:19]) - 0xD747) * 8 + first_bit
    require(event == {192: 1294, 159: 2496, 160: 2504, 161: 2512}[map_id])
    warp = start + 9 + body[8]
    coords_address = word(body[10:12])
    destination = {192: 159, 159: 160, 160: 161, 161: 162}[map_id]
    if map_id == 161:
        require(
            body[71] == 0xCD
            and read(start + 74, 2) == bytes.fromhex("18 11")
            and warp == start + 76
        )
        suffix = read(warp, 26)
        require(
            suffix[:6] == bytes((0x3E, destination, 0xEA, 0x1D, 0xD7, 0x21))
            and word(suffix[6:8]) == coords_address
            and suffix[8:18] == bytes.fromhex("cd 81 69 fa 32 d7 cb 67 c0 21")
        )
        # Dispatch to this map's script table after the hole check.
        require(suffix[20:] == bytes.fromhex("fa 66 d6 c3 97 3d") and coords_address == warp + 26)
    else:
        require(body[71] == 0xC3 and warp == start + 74)
        suffix = read(warp, 11)
        require(
            suffix[:6] == bytes((0x3E, destination, 0xEA, 0x1D, 0xD7, 0x21))
            and word(suffix[6:8]) == coords_address
            and suffix[8:] == bytes.fromhex("c3 81 69")
            and coords_address == warp + 11
        )
    coords = read(coords_address, 5)
    require(coords[4] == 255 and all(v < 64 for v in coords[:4]) and coords[:2] != coords[2:4])
    def sprite(toggle_index, expected_map):
        # A toggle ordinal is NOT a local sprite ordinal. In particular B3F's
        # two hole flags remove sprites 2 and 3, not sprites 1 and 2.
        offset = TOGGLEABLE_OBJECT_STATES + 3 * toggle_index
        require(offset + 3 <= len(rom))
        map_number, sprite_index, initial_visibility = rom[offset : offset + 3]
        require(map_number == expected_map and 1 <= sprite_index <= 15)
        require(initial_visibility in (0x11, 0x15))
        return sprite_index

    removed = tuple(sprite(body[29 + 14 * i], map_id) for i in range(2))
    shown = tuple(sprite(body[34 + 14 * i], destination) for i in range(2))
    require(len(set(removed)) == 2 and len(set(shown)) == 2)
    return tuple(
        SeafoamDrop(
            map_id,
            tuple(coords[i * 2 : i * 2 + 2]),
            removed[i],
            event + i,
            destination,
            body[29 + 14 * i],
            body[34 + 14 * i],
        )
        for i in range(2)
    )
