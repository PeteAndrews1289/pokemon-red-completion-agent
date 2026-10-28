"""Read Victory Road switch contracts, not their solutions, from Red.

Only authenticated floor-specific grammars are admitted. Shared Strength search
then supplies the solution from live terrain and boulders; no directions live here.
"""

from dataclasses import dataclass

from .gen1_cartridge import CartridgeReadError, bank_offset
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS, SCRIPT_POINTER_OFFSET
from .rom import verify_rom_bytes


@dataclass(frozen=True)
class BoulderSwitch:
    map_id: int
    at: tuple[int, int]
    event: int
    changed_block_at: tuple[int, int]
    changed_block: int


@dataclass(frozen=True)
class BoulderDrop:
    map_id: int
    at: tuple[int, int]
    event: int
    destination_map: int


def victory_road_first_switch(rom):
    verify_rom_bytes(rom)
    return _decode(rom)


def victory_road_second_switches(rom):
    """Return both second-floor contracts; this does not solve either puzzle."""
    verify_rom_bytes(rom)
    return _decode_second(rom)


def victory_road_third_floor(rom):
    """First switch and a forbidden player hole; hole execution is not admitted."""
    verify_rom_bytes(rom)
    return _decode_third(rom)


def victory_road_boulder_drop(rom):
    """Quote the authenticated hide/show boulder action, not a player hole warp.

    The existing grammar pins the branch's bit6 event and HideObject/ShowObject
    calls. Execution must still verify removal, event and the destination boulder.
    Player entry into the hole remains forbidden; ordinary stairs are separate.
    """
    verify_rom_bytes(rom)
    switch, hole = _decode_third(rom)
    return BoulderDrop(switch.map_id, hole, switch.event + 6, 194)


def _decode_third(rom):
    def require(ok):
        if not ok:
            raise CartridgeReadError("unsupported third-floor boulder-switch grammar")

    require(type(rom) is bytes and len(rom) > MAP_HEADER_BANKS + 198)
    bank = rom[MAP_HEADER_BANKS + 198]

    def read(address, size):
        require(address >= 0x4000 and address + size <= 0x8000)
        at = bank_offset(bank, address)
        require(at + size <= len(rom))
        return rom[at : at + size]

    def word(data):
        return int.from_bytes(data, "little")

    header = word(rom[MAP_HEADER_POINTERS + 396 : MAP_HEADER_POINTERS + 398])
    entry = read(word(read(header + SCRIPT_POINTER_OFFSET, 2)), 22)
    require(
        entry[0] == 0xCD
        and entry[3:7] == bytes.fromhex("cd 3c 3c 21")
        and entry[9] == 0x11
        and entry[12:] == bytes.fromhex("fa 40 d6 cd 60 31 ea 40 d6 c9")
    )
    check = read(word(entry[1:3]), 27)
    require(
        check[:15] == bytes.fromhex("21 26 d1 cb 6e cb ae c8 21 13 d8 cb 46 c8 3e")
        and check[16:20] == bytes.fromhex("ea 9f d0 01")
        and check[22:] == bytes.fromhex("3e 17 c3 6d 3e")
    )
    default = word(read(word(entry[10:12]), 2))
    body = read(default, 66)
    require(
        body[:8] == bytes.fromhex("21 60 cd cb 7e cb be ca")
        and body[10] == 0x21
        and body[13:17] == bytes.fromhex("cd e4 34 d2")
        and body[19:]
        == bytes.fromhex(
            "fa 3d cd fe 01 20 0b 21 26 d1 cb ee 21 13 d8 cb c6 c9 "
            "21 13 d8 cb 76 cb f6 20 19 3e 7a ea 4d cc 3e 11 cd 6d 3e "
            "3e 60 ea 4d cc 3e 15 c3 6d 3e"
        )
    )
    coords_address = word(body[11:13])
    warp_address = word(body[8:10])
    # Relative branch from byte44 must land at the same warp check.
    require(word(body[17:19]) == warp_address == default + 71 and coords_address == default + 66)
    coords = read(coords_address, 5)
    require(coords[4] == 255 and all(v < 64 for v in coords[:4]) and coords[:2] != coords[2:4])
    warp = read(warp_address, 38)
    require(
        warp[:6] == bytes.fromhex("3e c2 ea 1d d7 21")
        and word(warp[6:8]) == coords_address
        and warp[8:]
        == bytes.fromhex(
            "cd 81 69 fa 3d cd fe 01 20 0b 21 2d d7 cb a6 21 32 d7 cb a6 c9 "
            "fa 2d d7 cb 67 ca 19 32 c9"
        )
    )
    event = (word(body[32:34]) - 0xD747) * 8
    return (
        BoulderSwitch(198, tuple(coords[:2]), event, (check[21], check[20]), check[15]),
        tuple(coords[2:4]),
    )


def _decode_second(rom):
    def require(ok):
        if not ok:
            raise CartridgeReadError("unsupported second-floor boulder-switch grammar")

    require(type(rom) is bytes and len(rom) > MAP_HEADER_BANKS + 194)
    bank = rom[MAP_HEADER_BANKS + 194]

    def read(address, size):
        require(address >= 0x4000 and address + size <= 0x8000)
        at = bank_offset(bank, address)
        require(at + size <= len(rom))
        return rom[at : at + size]

    def word(data):
        return int.from_bytes(data, "little")

    header = word(rom[MAP_HEADER_POINTERS + 388 : MAP_HEADER_POINTERS + 390])
    script = word(read(header + SCRIPT_POINTER_OFFSET, 2))
    entry = read(script, 39)
    require(
        entry[:8] == bytes.fromhex("21 26 d1 cb 76 cb b6 c4")
        and entry[10:18] == bytes.fromhex("21 26 d1 cb 6e cb ae c4")
        and entry[20:24] == bytes.fromhex("cd 3c 3c 21")
        and entry[26] == 0x11
        and entry[29:] == bytes.fromhex("fa 3f d6 cd 60 31 ea 3f d6 c9")
    )
    reset_address = word(entry[8:10])
    check_address = word(entry[18:20])
    require(
        read(reset_address, 5) == bytes.fromhex("21 69 d8 cb be")
        and reset_address + 5 == check_address
    )
    check = read(check_address, 34)
    require(
        check[:9] == bytes.fromhex("fa ee d7 cb 47 28 0a f5 3e")
        and check[10] == 1
        and check[13] == 0xCD
        and word(check[14:16]) == check_address + 25
        and check[16:21] == bytes.fromhex("f1 cb 7f c8 3e")
        and check[22] == 1
        and check[25:] == bytes.fromhex("ea 9f d0 3e 17 cd 6d 3e c9")
    )
    default = word(read(word(entry[27:29]), 2))
    body = read(default, 37)
    require(
        body[0] == 0x21
        and body[3:]
        == bytes.fromhex(
            "cd e4 34 d2 19 32 21 ee d7 fa 3d cd fe 02 28 07 cb 46 cb c6 c0 "
            "18 05 cb 7e cb fe c0 21 26 d1 cb ee c9"
        )
    )
    coords = read(word(body[1:3]), 5)
    require(coords[4] == 255 and all(v < 64 for v in coords[:4]) and coords[:2] != coords[2:4])
    base_event = (word(body[10:12]) - 0xD747) * 8
    return (
        BoulderSwitch(194, tuple(coords[:2]), base_event, (check[12], check[11]), check[9]),
        BoulderSwitch(194, tuple(coords[2:4]), base_event + 7, (check[24], check[23]), check[21]),
    )


def _decode(rom):
    def require(ok):
        if not ok:
            raise CartridgeReadError("unsupported first-floor boulder-switch grammar")

    require(type(rom) is bytes and len(rom) > MAP_HEADER_BANKS + 108)
    bank = rom[MAP_HEADER_BANKS + 108]

    def read(address, size):
        require(address >= 0x4000 and address + size <= 0x8000)
        at = bank_offset(bank, address)
        require(at + size <= len(rom))
        return rom[at : at + size]

    def word(data):
        return int.from_bytes(data, "little")

    header = word(rom[MAP_HEADER_POINTERS + 216 : MAP_HEADER_POINTERS + 218])
    script = word(read(header + SCRIPT_POINTER_OFFSET, 2))
    entry = read(script, 29)
    require(
        entry[:8] == bytes.fromhex("21 26 d1 cb 6e cb ae c4")
        and entry[10:14] == bytes.fromhex("cd 3c 3c 21")
        and entry[16] == 0x11
        and entry[19:] == bytes.fromhex("fa 51 d6 cd 60 31 ea 51 d6 c9")
    )
    replace_block = read(word(entry[8:10]), 19)
    require(
        replace_block[:6] == bytes.fromhex("fa 69 d8 cb 7f c8")
        and replace_block[6] == 0x3E
        and replace_block[8:12] == bytes.fromhex("ea 9f d0 01")
        and replace_block[14:] == bytes.fromhex("3e 17 c3 6d 3e")
    )
    table = word(entry[17:19])
    default = word(read(table, 2))
    body = read(default, 28)
    require(
        body[:9] == bytes.fromhex("fa 69 d8 cb 7f c2 19 32 21")
        and body[11:] == bytes.fromhex("cd e4 34 d2 19 32 21 26 d1 cb ee 21 69 d8 cb fe c9")
    )
    coords = read(word(body[9:11]), 3)
    require(coords[2] == 255 and all(v < 64 for v in coords[:2]))
    event = (word(body[23:25]) - 0xD747) * 8 + 7
    require(event == 0x917)
    return BoulderSwitch(
        108, tuple(coords[:2]), event, (replace_block[13], replace_block[12]), replace_block[7]
    )
