import pytest

from pokemon_red_completion import gen1_boulder_switch as switch
from pokemon_red_completion.gen1_cartridge import CartridgeReadError


def cartridge(y=13, x=17, block_y=6, block_x=4):
    rom = bytearray(0x20000)
    rom[switch.MAP_HEADER_BANKS + 108] = 3
    rom[switch.MAP_HEADER_POINTERS + 216 : switch.MAP_HEADER_POINTERS + 218] = b"\x00\x41"
    rom[0xC107:0xC109] = b"\x00\x42"

    def put(at, payload):
        rom[at : at + len(payload)] = payload

    put(
        0xC200,
        bytes.fromhex(
            "21 26 d1 cb 6e cb ae c4 00 43 cd 3c 3c 21 00 48 11 00 44 fa 51 d6 cd 60 31 ea 51 d6 c9"
        ),
    )
    put(
        0xC300,
        bytes.fromhex("fa 69 d8 cb 7f c8 3e 1d ea 9f d0 01")
        + bytes((block_x, block_y))
        + bytes.fromhex("3e 17 c3 6d 3e"),
    )
    put(0xC400, b"\x00\x45")
    put(
        0xC500,
        bytes.fromhex(
            "fa 69 d8 cb 7f c2 19 32 21 00 46 cd e4 34 d2 19 32 21 26 d1 cb ee 21 69 d8 cb fe c9"
        ),
    )
    put(0xC600, bytes((y, x, 255)))
    return bytes(rom)


@pytest.mark.parametrize("at,block", [((13, 17), (6, 4)), ((11, 15), (5, 3))])
def test_reads_goal_and_geometry_operands_without_solution(at, block):
    result = switch._decode(cartridge(*at, *block))
    assert result == switch.BoulderSwitch(108, at, 0x917, block, 0x1D)


@pytest.mark.parametrize(
    "address",
    [0xC200, 0xC214, 0xC300, 0xC305, 0xC308, 0xC500, 0xC50C, 0xC516, 0xC517, 0xC51A, 0xC602],
)
def test_changed_grammar_refuses(address):
    rom = bytearray(cartridge())
    rom[address] ^= 1
    with pytest.raises(CartridgeReadError):
        switch._decode(bytes(rom))


def test_public_entry_checks_cartridge_identity():
    with pytest.raises(ValueError):
        switch.victory_road_first_switch(cartridge())


def second_cartridge(coords=(16, 1, 16, 9), first_block=(4, 3), second_block=(7, 11)):
    rom = bytearray(0x20000)
    rom[switch.MAP_HEADER_BANKS + 194] = 3
    rom[switch.MAP_HEADER_POINTERS + 388 : switch.MAP_HEADER_POINTERS + 390] = b"\x00\x41"
    rom[0xC107:0xC109] = b"\x00\x42"

    def put(at, payload):
        rom[at : at + len(payload)] = payload

    put(
        0xC200,
        bytes.fromhex(
            "21 26 d1 cb 76 cb b6 c4 00 43 21 26 d1 cb 6e cb ae c4 05 43 cd 3c 3c "
            "21 00 48 11 00 44 fa 3f d6 cd 60 31 ea 3f d6 c9"
        ),
    )
    put(0xC300, bytes.fromhex("21 69 d8 cb be"))
    put(
        0xC305,
        bytes.fromhex("fa ee d7 cb 47 28 0a f5 3e 15 01")
        + bytes(reversed(first_block))
        + bytes.fromhex("cd 1e 43 f1 cb 7f c8 3e 1d 01")
        + bytes(reversed(second_block))
        + bytes.fromhex("ea 9f d0 3e 17 cd 6d 3e c9"),
    )
    put(0xC400, b"\x00\x45")
    put(
        0xC500,
        bytes.fromhex(
            "21 00 46 cd e4 34 d2 19 32 21 ee d7 fa 3d cd fe 02 28 07 cb 46 cb c6 c0 "
            "18 05 cb 7e cb fe c0 21 26 d1 cb ee c9"
        ),
    )
    put(0xC600, bytes((*coords, 255)))
    return bytes(rom)


@pytest.mark.parametrize(
    "coords,blocks", [((16, 1, 16, 9), ((4, 3), (7, 11))), ((14, 2, 15, 8), ((3, 2), (6, 10)))]
)
def test_second_floor_reads_both_switch_operands(coords, blocks):
    result = switch._decode_second(second_cartridge(coords, *blocks))
    assert result == (
        switch.BoulderSwitch(194, coords[:2], 1336, blocks[0], 0x15),
        switch.BoulderSwitch(194, coords[2:], 1343, blocks[1], 0x1D),
    )


@pytest.mark.parametrize(
    "address",
    [
        0xC200,
        0xC20E,
        0xC21D,
        0xC300,
        0xC304,
        0xC308,
        0xC30B,
        0xC313,
        0xC317,
        0xC31E,
        0xC321,
        0xC500,
        0xC507,
        0xC510,
        0xC512,
        0xC516,
        0xC51D,
        0xC523,
        0xC604,
    ],
)
def test_second_floor_changed_grammar_refuses(address):
    rom = bytearray(second_cartridge())
    rom[address] ^= 1
    with pytest.raises(CartridgeReadError):
        switch._decode_second(bytes(rom))


def test_second_floor_public_identity_and_invalid_coords_refuse():
    with pytest.raises(ValueError):
        switch.victory_road_second_switches(second_cartridge())
    for coords in ((64, 1, 16, 9), (16, 1, 16, 1)):
        with pytest.raises(CartridgeReadError):
            switch._decode_second(second_cartridge(coords))


def test_second_floor_pointer_out_of_bank_refuses():
    rom = bytearray(second_cartridge())
    rom[0xC21B:0xC21D] = b"\xff\x7f"
    with pytest.raises(CartridgeReadError):
        switch._decode_second(bytes(rom))


def third_cartridge(coords=(5, 3, 15, 23), block=(5, 3)):
    rom = bytearray(0x20000)
    # Bank4 avoids aliasing this map's bank-table byte with the fake script.
    rom[switch.MAP_HEADER_BANKS + 198] = 4
    rom[switch.MAP_HEADER_POINTERS + 396 : switch.MAP_HEADER_POINTERS + 398] = b"\x00\x41"
    rom[0x10107:0x10109] = b"\x00\x42"

    def put(at, payload):
        rom[at + 0x4000 : at + 0x4000 + len(payload)] = payload

    put(0xC200, bytes.fromhex("cd 00 43 cd 3c 3c 21 00 48 11 00 44 fa 40 d6 cd 60 31 ea 40 d6 c9"))
    put(
        0xC300,
        bytes.fromhex("21 26 d1 cb 6e cb ae c8 21 13 d8 cb 46 c8 3e 1d ea 9f d0 01")
        + bytes(reversed(block))
        + bytes.fromhex("3e 17 c3 6d 3e"),
    )
    put(0xC400, b"\x00\x45")
    put(
        0xC500,
        bytes.fromhex(
            "21 60 cd cb 7e cb be ca 47 45 21 42 45 cd e4 34 d2 47 45 "
            "fa 3d cd fe 01 20 0b 21 26 d1 cb ee 21 13 d8 cb c6 c9 "
            "21 13 d8 cb 76 cb f6 20 19 3e 7a ea 4d cc 3e 11 cd 6d 3e 3e 60 ea 4d cc 3e 15 c3 6d 3e"
        ),
    )
    put(0xC542, bytes((*coords, 255)))
    put(
        0xC547,
        bytes.fromhex(
            "3e c2 ea 1d d7 21 42 45 cd 81 69 fa 3d cd fe 01 20 0b "
            "21 2d d7 cb a6 21 32 d7 cb a6 c9 fa 2d d7 cb 67 ca 19 32 c9"
        ),
    )
    return bytes(rom)


@pytest.mark.parametrize("coords,block", [((5, 3, 15, 23), (5, 3)), ((4, 2, 14, 22), (4, 2))])
def test_third_floor_reads_switch_and_forbidden_hole(coords, block):
    assert switch._decode_third(third_cartridge(coords, block)) == (
        switch.BoulderSwitch(198, coords[:2], 1632, block, 29),
        coords[2:],
    )


@pytest.mark.parametrize(
    "address",
    [
        0xC200,
        0xC20C,
        0xC300,
        0xC30C,
        0xC318,
        0xC500,
        0xC507,
        0xC508,
        0xC50B,
        0xC510,
        0xC511,
        0xC519,
        0xC520,
        0xC523,
        0xC529,
        0xC52D,
        0xC52F,
        0xC539,
        0xC546,
        0xC548,
        0xC54D,
        0xC557,
        0xC55D,
        0xC56C,
    ],
)
def test_third_floor_changed_grammar_refuses(address):
    rom = bytearray(third_cartridge())
    rom[address + 0x4000] ^= 1
    with pytest.raises(CartridgeReadError):
        switch._decode_third(bytes(rom))


def test_third_floor_rejects_identity_duplicate_or_out_of_range_coordinates():
    with pytest.raises(ValueError):
        switch.victory_road_third_floor(third_cartridge())
    for coords in ((5, 3, 5, 3), (5, 3, 64, 23)):
        with pytest.raises(CartridgeReadError):
            switch._decode_third(third_cartridge(coords))


def test_third_floor_pointer_and_short_reads_refuse():
    rom = bytearray(third_cartridge())
    rom[0x10201:0x10203] = b"\xff\x7f"
    with pytest.raises(CartridgeReadError):
        switch._decode_third(bytes(rom))
    with pytest.raises(CartridgeReadError):
        switch._decode_third(third_cartridge()[:0x10568])


def test_drop_contract_checks_identity():
    with pytest.raises(ValueError):
        switch.victory_road_boulder_drop(third_cartridge())


@pytest.mark.parametrize("coords", [(5, 3, 15, 23), (4, 2, 14, 22)])
def test_drop_contract_reuses_authenticated_hide_show_grammar(monkeypatch, coords):
    monkeypatch.setattr(switch, "verify_rom_bytes", lambda rom: None)
    assert switch.victory_road_boulder_drop(third_cartridge(coords)) == switch.BoulderDrop(
        198, coords[2:], 1638, 194
    )
    for offset in (38, 40, 42, 47, 52, 57, 64):
        rom = bytearray(third_cartridge(coords))
        rom[0x10500 + offset] ^= 1
        with pytest.raises(CartridgeReadError):
            switch.victory_road_boulder_drop(bytes(rom))
