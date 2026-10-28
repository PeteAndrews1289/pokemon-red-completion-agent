from types import SimpleNamespace as NS

import pytest

from pokemon_red_completion import gen1_seafoam as m
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.gen1_field_moves import gen1_field_capabilities, surf_permission


def cartridge(map_id=160, coords=(6, 19, 6, 22)):
    rom = bytearray(0x20000)
    rom[m.MAP_HEADER_BANKS + map_id] = 4
    rom[m.MAP_HEADER_POINTERS + 2 * map_id : m.MAP_HEADER_POINTERS + 2 * map_id + 2] = b"\x00\x41"
    rom[0x10107:0x10109] = b"\x00\x42"
    prefix = bytes.fromhex("cd 3c 3c")
    if map_id == 192:
        prefix += bytes.fromhex("21 e7 d7 cb c6")
    start = 0x4200 + len(prefix)
    third = map_id == 161
    warp = start + (76 if third else 74)
    coordinates = warp + (26 if third else 11)
    address, bit, destination = {
        192: (0xD7E8, 6, 159),
        159: (0xD87F, 0, 160),
        160: (0xD880, 0, 161),
        161: (0xD881, 0, 162),
    }[map_id]
    body = bytearray(
        bytes.fromhex("21 60 cd cb 7e cb be 28 41 21")
        + coordinates.to_bytes(2, "little")
        + bytes.fromhex("cd e4 34 d0 21")
        + address.to_bytes(2, "little")
        + bytes.fromhex(
            "fa 3d cd fe 01 20 0e cb c6 3e db ea 79 d0 3e df ea 7a d0 18 0c "
            "cb ce 3e dc ea 79 d0 3e e0 ea 7a d0 fa 79 d0 ea 4d cc 3e 11 "
            "cd 6d 3e fa 7a d0 ea 4d cc 3e 15 c3 6d 3e"
        )
    )
    body[27] = 0xC6 + 8 * bit
    body[41] = body[27] + 8
    if third:
        body[8] = 0x43
        body[71] = 0xCD
        body += bytes.fromhex("18 11")
    suffix = bytes((0x3E, destination, 0xEA, 0x1D, 0xD7, 0x21)) + coordinates.to_bytes(2, "little")
    suffix += (
        bytes.fromhex("cd 81 69 fa 32 d7 cb 67 c0 21 00 46 fa 66 d6 c3 97 3d")
        if third
        else bytes.fromhex("c3 81 69")
    )
    data = prefix + body + suffix + bytes((*coords, 255))
    rom[0x10200 : 0x10200 + len(data)] = data
    for i in range(2):
        for toggle, map_number, local_sprite in (
            (body[29 + 14 * i], map_id, i + (2 if third else 1)),
            (body[34 + 14 * i], destination, i + 1),
        ):
            offset = m.TOGGLEABLE_OBJECT_STATES + 3 * toggle
            rom[offset : offset + 3] = bytes((map_number, local_sprite, 0x15))
    return bytes(rom), 0x10000 + start - 0x4000, 0x10000 + coordinates - 0x4000


@pytest.mark.parametrize("map_id", [192, 159, 160, 161])
@pytest.mark.parametrize("coords", [(6, 19, 6, 22), (4, 12, 8, 17)])
def test_decodes_dependencies_not_solutions(map_id, coords):
    rom, _, _ = cartridge(map_id, coords)
    first, second = m._decode_drops(rom, map_id)
    assert (first.at, second.at) == (coords[:2], coords[2:])
    assert (first.boulder_index, second.boulder_index) == ((2, 3) if map_id == 161 else (1, 2))
    assert second.event == first.event + 1
    assert first.destination_map == {192: 159, 159: 160, 160: 161, 161: 162}[map_id]


@pytest.mark.parametrize(
    "offset",
    [
        0,
        3,
        6,
        8,
        9,
        12,
        15,
        16,
        17,
        19,
        23,
        25,
        26,
        27,
        30,
        33,
        35,
        38,
        39,
        40,
        41,
        44,
        47,
        49,
        54,
        60,
        61,
        64,
        68,
        70,
        71,
        73,
    ],
)
@pytest.mark.parametrize("map_id", [160, 161])
def test_changed_instruction_grammar_fails_closed(offset, map_id):
    rom, start, _ = cartridge(map_id)
    changed = bytearray(rom)
    changed[start + offset] ^= 1
    with pytest.raises(CartridgeReadError):
        m._decode_drops(bytes(changed), map_id)


def test_invalid_identity_coordinates_and_pointer():
    rom, start, coords = cartridge()
    with pytest.raises(ValueError):
        m.seafoam_drops(rom, 160)
    for index, value in ((coords, 64), (coords + 4, 0), (start + 10, 255), (start + 11, 127)):
        changed = bytearray(rom)
        changed[index] = value
        with pytest.raises(CartridgeReadError):
            m._decode_drops(bytes(changed), 160)
    with pytest.raises(CartridgeReadError):
        m._decode_drops(rom[: coords + 4], 160)


@pytest.mark.parametrize("mask", range(16))
def test_current_gate_needs_all_four_observed_events(mask):
    from pokemon_red_completion.observation import Badge, RawGameState

    flags = bytearray(320)
    for i, event in enumerate(m.SEAFOAM_CURRENT_EVENTS):
        if mask & (1 << i):
            flags[event // 8] |= 1 << (event % 8)
    raw = RawGameState(
        True,
        162,
        7,
        11,
        1,
        0,
        event_flags=bytes(flags),
        badge_bits=int(Badge.SOUL),
        party_hp=(10,),
        party_moves=((57,),),
    )
    memory = NS(read_u8=lambda _: 0)
    assert m.seafoam_currents_settled(raw) == (mask == 15)
    assert surf_permission(memory, raw).allowed == (mask == 15)
    assert ("field:seafoam_current_control" in gen1_field_capabilities(memory, raw)) == (mask == 15)
    assert ("move:surf" in gen1_field_capabilities(memory, raw)) == (mask == 15)


def test_missing_short_flags_do_not_unlock_water():
    for flags in (None, b"", bytes(10)):
        assert not m.seafoam_currents_settled(NS(event_flags=flags))


@pytest.mark.parametrize('delta,value', [(0, 159), (1, 0), (1, 16), (2, 0)])
def test_invalid_toggle_mapping_rejected(delta, value):
    rom, _, _ = cartridge(161)
    changed = bytearray(rom)
    changed[m.TOGGLEABLE_OBJECT_STATES + 3 * 0xDB + delta] = value
    with pytest.raises(CartridgeReadError):
        m._decode_drops(bytes(changed), 161)


def test_toggle_mapping_is_decoded_and_unique():
    rom, _, _ = cartridge(161)
    changed = bytearray(rom)
    changed[m.TOGGLEABLE_OBJECT_STATES + 3 * 0xDB + 1] = 4
    assert m._decode_drops(bytes(changed), 161)[0].boulder_index == 4
    changed[m.TOGGLEABLE_OBJECT_STATES + 3 * 0xDC + 1] = 4
    with pytest.raises(CartridgeReadError):
        m._decode_drops(bytes(changed), 161)


@pytest.mark.parametrize('mask', range(16))
def test_static_transport_requires_observed_current_state(mask):
    from pokemon_red_completion.actions import MacroActionKind
    from pokemon_red_completion.red_resource_goal_router import _supported_plan
    flags = bytearray(320)
    for i, event in enumerate(m.SEAFOAM_CURRENT_EVENTS):
        if mask & (1 << i):
            flags[event // 8] |= 1 << (event % 8)
    step = NS(action_kind=MacroActionKind.FIELD_MOVE, action='surf:up',
              source_mode='land', expected_mode='water', source_map=162, expected_map=162)
    plan = NS(steps=(step,))
    assert not _supported_plan(plan, allow_surf=True)
    assert _supported_plan(
        plan, allow_surf=True, seafoam_state=NS(event_flags=bytes(flags))
    ) == (mask == 15)
    assert not _supported_plan(plan, seafoam_state=NS(event_flags=bytes(flags)))


def test_script_holes_block_arrivals_and_via_but_allow_departure(monkeypatch):
    from pokemon_red_completion.local_router import LocalEdge, LocalGraph
    monkeypatch.setattr(m, 'seafoam_drops', lambda *_: (NS(at=(6, 19)), NS(at=(6, 22))))
    ordinary = LocalEdge((5, 18), 'up')
    incoming = LocalEdge((6, 19), 'right')
    across = LocalEdge((6, 23), 'right', kind='forced_motion', via=((6, 22),))
    transient = LocalEdge((6, 20), 'right', kind='ledge', transient=(6, 19))
    graph = LocalGraph({(6, 18): (ordinary, incoming, across, transient),
                        (6, 19): (LocalEdge((6, 18), 'left'),)})
    result = m.apply_seafoam_hole_guards(b'rom', {160: graph, 7: graph})
    assert result[160].neighbors((6, 18)) == (ordinary,)
    assert result[160].neighbors((6, 19)) == graph.neighbors((6, 19))
    assert result[7] is graph
