"""ROM-free proposal regression: native script operands and geometry authority.

Root runs baseline first, then applies source proposal. No private ROM/save,
model, emulator or executable provider is used by this file.
"""
from dataclasses import dataclass, replace
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import gen1_terrain as terrain
from pokemon_red_completion import red_player_mansion as mansion
from pokemon_red_completion.gen1_cartridge import CartridgeReadError
from pokemon_red_completion.observation import EventFlag, MapId, RamAddress

FIRST = int(MapId.POKEMON_MANSION_1F)
SECOND = int(MapId.POKEMON_MANSION_2F)
# Deliberately not the real Mansion coordinates or block ids.
COORDS = ((1, 2), (2, 3), (3, 4), (4, 5))
OFF = (81, 97, 97, 97)
ON = (97, 81, 81, 81)


def script_fixture(*, shift=0):
    rom = bytearray(0xC400)
    bank = 1
    header, entry, update = 0x4000 + shift, 0x4100 + shift, 0x4200 + shift
    closed, opened = 0x4304 + shift, 0x430B + shift
    rom[terrain.MAP_HEADER_BANKS + FIRST] = bank
    pointer = terrain.MAP_HEADER_POINTERS + FIRST * 2
    rom[pointer:pointer + 2] = header.to_bytes(2, 'little')
    rom[header:header + 3] = bytes((0, 8, 8))
    rom[header + 7:header + 9] = entry.to_bytes(2, 'little')
    rom[entry:entry + 3] = b'\xcd' + update.to_bytes(2, 'little')
    event = int(EventFlag.MANSION_SWITCH_ON)
    event_address = int(RamAddress.EVENT_FLAGS) + event // 8
    prefix = (b'\x21\x26\xd1\xcb\x6e\xcb\xae\xc8\xfa'
              + event_address.to_bytes(2, 'little')
              + bytes((0xCB, 0x47 + 8 * (event % 8), 0x20, 24)))
    rom[update:update + len(prefix)] = prefix
    for phase, ids in enumerate((OFF, ON)):
        for ordinal, ((y, x), block) in enumerate(zip(COORDS, ids, strict=True)):
            at = update + len(prefix) + phase * 24 + ordinal * 6
            helper = opened if block == 81 else closed
            rom[at:at + 6] = bytes((1, x, y, 0xC3 if ordinal == 3 else 0xCD)) + helper.to_bytes(2, 'little')
    rom[closed:closed + 7] = bytes((0x3E, 97, 0xEA, 0x9F, 0xD0, 0x18, 5))
    rom[opened:opened + 11] = bytes((0x3E, 81, 0xEA, 0x9F, 0xD0, 0x3E, 0x17, 0xCD, 0x6D, 0x3E, 0xC9))
    return rom, N(header=header, entry=entry, update=update, closed=closed, opened=opened)


@pytest.mark.parametrize('switch,expected', [(False, OFF), (True, ON)])
@pytest.mark.parametrize('shift', [0, 0x70])
def test_reads_both_phases_from_relocated_script_operands(switch, expected, shift):
    rom, _ = script_fixture(shift=shift)
    assert terrain.mansion_first_floor_door_blocks(bytes(rom), switch_on=switch) == tuple(zip(COORDS, expected, strict=True))


@pytest.mark.parametrize('value', [0, 1, None, 'on'])
def test_switch_phase_requires_boolean(value):
    rom, _ = script_fixture()
    with pytest.raises(TypeError):
        terrain.mansion_first_floor_door_blocks(bytes(rom), switch_on=value)


@pytest.mark.parametrize('fault', [
    'entry_call', 'update_guard', 'event_address', 'event_bit', 'condition',
    'branch_length', 'coordinate_opcode', 'first_call', 'last_jump',
    'helper_store', 'helper_predef', 'duplicate_coordinate', 'outside_coordinate',
    'different_phase_coordinate', 'truncated_header', 'truncated_helper',
])
def test_malformed_program_has_no_guessed_projection(fault):
    rom, pos = script_fixture()
    if fault == 'entry_call': rom[pos.entry] = 0
    elif fault == 'update_guard': rom[pos.update + 4] ^= 8
    elif fault == 'event_address': rom[pos.update + 9] ^= 1
    elif fault == 'event_bit': rom[pos.update + 12] ^= 8
    elif fault == 'condition': rom[pos.update + 13] = 0x28
    elif fault == 'branch_length': rom[pos.update + 14] = 18
    elif fault == 'coordinate_opcode': rom[pos.update + 15] = 0
    elif fault == 'first_call': rom[pos.update + 18] = 0xC3
    elif fault == 'last_jump': rom[pos.update + 15 + 3 * 6 + 3] = 0xCD
    elif fault == 'helper_store': rom[pos.opened + 3] ^= 1
    elif fault == 'helper_predef': rom[pos.opened + 8] ^= 1
    elif fault == 'duplicate_coordinate': rom[pos.update + 22:pos.update + 24] = rom[pos.update + 16:pos.update + 18]
    elif fault == 'outside_coordinate': rom[pos.update + 16] = 8
    elif fault == 'different_phase_coordinate': rom[pos.update + 40] = 6
    elif fault == 'truncated_header': rom = rom[:pos.header + 8]
    elif fault == 'truncated_helper':
        # Move the same program to bank4 so the complete map-pointer metadata
        # precedes a physically truncated block-loader body.
        lifted = bytearray(0x10400)
        lifted[:len(rom)] = rom
        lifted[0x10000:0x10400] = rom[0x4000:0x4400]
        lifted[terrain.MAP_HEADER_BANKS + FIRST] = 4
        rom = lifted[:0x1030C]
    with pytest.raises(CartridgeReadError):
        terrain.mansion_first_floor_door_blocks(bytes(rom), switch_on=False)


def test_physically_truncated_table_rejected():
    with pytest.raises(CartridgeReadError):
        terrain.mansion_first_floor_door_blocks(b'\0' * 20, switch_on=False)


def event_bytes(on=False):
    event = int(EventFlag.MANSION_SWITCH_ON)
    flags = bytearray(event // 8 + 1)
    if on: flags[event // 8] |= 1 << (event % 8)
    return bytes(flags)


@dataclass(frozen=True)
class TestTerrain:
    __test__ = False
    map_id: int
    blocks: tuple


@dataclass(frozen=True)
class TestWorld:
    __test__ = False
    rom: bytes
    terrain: dict
    local_graphs: dict
    tilesets: object
    water_tilesets: object
    object_blockers: dict
    macro_graph: object
    requirements: object
    graph_calls: list

    def _graph_for_terrain(self, changed):
        self.graph_calls.append(changed)
        # Keep blockers/requirements observable independently from block bytes.
        return (changed.blocks, self.object_blockers[changed.map_id], self.requirements)


def world_fixture():
    blocks = tuple(tuple(0 for _ in range(8)) for _ in range(8))
    blocks = tuple(tuple(77 if (y, x) == (7, 7) else value for x, value in enumerate(row)) for y, row in enumerate(blocks))
    first, second = TestTerrain(FIRST, blocks), TestTerrain(SECOND, ((42,),))
    return TestWorld(b'rom', {FIRST:first, SECOND:second}, {FIRST:object(), SECOND:object()},
                     object(), object(), {FIRST:frozenset({(1, 1)}), SECOND:frozenset()}, object(), object(), [])


def install_conversion(monkeypatch):
    calls = []
    monkeypatch.setattr(mansion, 'mansion_first_floor_door_blocks',
                        lambda rom, *, switch_on: tuple(zip(COORDS, ON if switch_on else OFF, strict=True)))
    def change(rom, original, at, block_id, sets, *, water_set_ids):
        calls.append((at, block_id))
        rows = [list(row) for row in original.blocks]
        rows[at[0]][at[1]] = block_id
        return replace(original, blocks=tuple(tuple(row) for row in rows))
    monkeypatch.setattr(mansion, 'terrain_with_block', change)
    return calls


@pytest.mark.parametrize('map_id,flags', [
    (int(MapId.CINNABAR_ISLAND), event_bytes()),
    (FIRST, event_bytes()), (FIRST, event_bytes(True)),
    (SECOND, None), (SECOND, b''), (SECOND, b'\0'),
])
def test_projection_noops_outside_current_and_unknown(monkeypatch, map_id, flags):
    world = world_fixture()
    def forbidden(*args, **kwargs): raise AssertionError('No-op decoded or rebuilt geometry')
    monkeypatch.setattr(mansion, 'mansion_first_floor_door_blocks', forbidden)
    monkeypatch.setattr(mansion, 'terrain_with_block', forbidden)
    assert mansion.mansion_first_floor_world(world, N(map_id=map_id,event_flags=flags)) is world
    assert world.graph_calls == []


@pytest.mark.parametrize('switch,expected', [(False, OFF), (True, ON)])
def test_projected_doors_preserve_other_geometry_and_guards(monkeypatch, switch, expected):
    calls = install_conversion(monkeypatch)
    world = world_fixture()
    changed = mansion.mansion_first_floor_world(world, N(map_id=SECOND,event_flags=event_bytes(switch)))
    assert calls == list(zip(COORDS, expected, strict=True))
    assert world.terrain[FIRST].blocks[COORDS[0][0]][COORDS[0][1]] == 0
    assert changed.terrain[FIRST].blocks[7][7] == 77
    for at, block in zip(COORDS, expected, strict=True): assert changed.terrain[FIRST].blocks[at[0]][at[1]] == block
    assert changed.terrain[SECOND] is world.terrain[SECOND]
    assert changed.local_graphs[SECOND] is world.local_graphs[SECOND]
    for name in ('object_blockers','macro_graph','requirements','tilesets','water_tilesets'):
        assert getattr(changed,name) is getattr(world,name)
    assert changed.local_graphs[FIRST][1] is world.object_blockers[FIRST]
    assert changed.local_graphs[FIRST][2] is world.requirements
    assert len(world.graph_calls) == 1
    count = len(calls)
    assert mansion.mansion_first_floor_world(changed,N(map_id=SECOND,event_flags=event_bytes(switch))) is changed
    assert len(calls) == count and len(world.graph_calls) == 1


def test_switch_reversal_replaces_only_script_blocks(monkeypatch):
    install_conversion(monkeypatch)
    original = world_fixture()
    off = mansion.mansion_first_floor_world(original,N(map_id=SECOND,event_flags=event_bytes()))
    on = mansion.mansion_first_floor_world(off,N(map_id=SECOND,event_flags=event_bytes(True)))
    restored = mansion.mansion_first_floor_world(on,N(map_id=SECOND,event_flags=event_bytes()))
    assert restored.terrain[FIRST] == off.terrain[FIRST]
    assert on.terrain[FIRST] != off.terrain[FIRST]
    assert restored.terrain[FIRST].blocks[7][7] == 77


def test_no_source_blocks_is_not_silently_guessed(monkeypatch):
    install_conversion(monkeypatch)
    world = world_fixture()
    world = replace(world,terrain={**world.terrain,FIRST:TestTerrain(FIRST,None)})
    with pytest.raises(ValueError,match='explicit source blocks'):
        mansion.mansion_first_floor_world(world,N(map_id=SECOND,event_flags=event_bytes()))


@pytest.mark.parametrize('switch', [False, True])
def test_legal_ordinary_binding_retains_precedence(monkeypatch, switch):
    original, projected = object(), object()
    raw = N(map_id=SECOND,event_flags=event_bytes(switch))
    runtime = N(reader=N(read=lambda:raw))
    @dataclass(frozen=True)
    class Route:
        route_world: object
    route = Route(original)
    calls = []
    sentinel = object()
    monkeypatch.setattr(mansion,'_field_ready',lambda _:True)
    def project(world, observed):
        assert world is original and observed is raw
        calls.append('projection')
        return projected
    monkeypatch.setattr(mansion,'mansion_first_floor_world',project)
    def ordinary(*args, **kwargs):
        assert kwargs['route'].route_world is projected
        calls.append('ordinary')
        return sentinel
    monkeypatch.setattr(mansion,'field_item_story_option',ordinary)
    def forbidden(*args, **kwargs): raise AssertionError('Ordinary binding was displaced')
    monkeypatch.setattr(mansion,'_mansion_interaction_option',forbidden)
    assert mansion.mansion_secret_key_option(runtime,None,None,route=route) is sentinel
    assert calls == ['projection','ordinary']
    assert route.route_world is original
