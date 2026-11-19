"""Candidate-only ROM-free grammar/applicability falsifiers; zero native state."""
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import gen1_scripted_wild as p

def fixture(*, level=17, species=59):
    image = bytearray(0x80000)
    bank, map_id = 24, 147
    at = lambda address: bank * 0x4000 + address - 0x4000
    word = lambda value: value.to_bytes(2, 'little')
    header, entry, table, default, coords = 0x4100, 0x4200, 0x4300, 0x4400, 0x4500
    local, current, override, level_source = 0xD62F, int(p.RamAddress.CURRENT_MAP_SCRIPT), 0xD733, 0xD127
    event_address = p.EVENT_FLAGS_START + 271 // 8
    image[p.MAP_HEADER_BANKS + map_id] = bank
    image[p.MAP_HEADER_POINTERS + 2 * map_id:p.MAP_HEADER_POINTERS + 2 * map_id + 2] = word(header)
    def put(address, body, *, fixed=False):
        offset = address if fixed else at(address)
        image[offset:offset + len(body)] = body
    put(header, bytes([0, 10, 10, 0, 0, 0, 0]) + word(entry) + b'\x00')
    put(entry, b'\xcd'+word(0x3C3C)+b'\x21'+word(0x4600)+b'\x11'+word(table)
        +b'\xfa'+word(local)+b'\xcd'+word(0x3160)+b'\xea'+word(local)+b'\xc9')
    put(table, word(default))
    put(0x3C3C, bytes.fromhex('af18023e01ea0ccfafea3cccc9'), fixed=True)
    put(0x3157, b'\x7c\xea'+word(0xDA30)+b'\x7d\xea'+word(0xDA31)+b'\xc9', fixed=True)
    dispatch = (b'\xf5\xd5\xcd'+word(0x3157)+b'\xe1\xf1\xe5\x21'+word(override)
        +bytes.fromhex('cb66cba62803fa')+word(current)+b'\xe1\xea'+word(current)
        +b'\xcd'+word(0x3D97)+b'\xfa'+word(current)+b'\xc9')
    put(0x3160, dispatch, fixed=True)
    put(0x3D97, bytes.fromhex('e5d5c58716005f192a666f11')+word(0x3DA7)
        +bytes.fromhex('d5e9c1d1e1c9'), fixed=True)
    code = (b'\xfa'+word(event_address)+bytes.fromhex('cb7fc2')+word(0x3219)
        +b'\x21'+word(coords)+b'\xcd'+word(0x34BF)+b'\xd2'+word(0x3219)
        +bytes.fromhex('afe0b43e06e08ccd')+word(0x2920)+b'\x3e'+bytes([species])
        +b'\xea'+word(int(p.RamAddress.CURRENT_OPPONENT))+b'\x3e'+bytes([level])
        +b'\xea'+word(level_source)+bytes.fromhex('3e04ea')+word(local)+b'\xea'+word(current)+b'\xc9')
    assert len(code) == 46
    put(default, code)
    put(coords, bytes([16, 10, 255]))
    coordinate_code = (b'\xfa'+word(int(p.RamAddress.PLAYER_Y))+b'\x47\xfa'
        +word(int(p.RamAddress.PLAYER_X))+bytes.fromhex('4fafea')+word(0xCD3D)
        +bytes.fromhex('2afeff2812e521')+word(0xCD3D)
        +bytes.fromhex('34e1b828032318ef2ab920eb37c9a7c9'))
    assert len(coordinate_code) == 37
    put(0x34BF, coordinate_code, fixed=True)
    bridge = b'\x11'+word(int(p.RamAddress.ENEMY_LEVEL))+b'\xfa'+word(level_source)+b'\x12'
    image[p._LEVEL_DE_BRIDGE_OFFSET:p._LEVEL_DE_BRIDGE_OFFSET+len(bridge)] = bridge
    scope = p.ScriptedWildGateScope(map_id, 271, (16, 10), 72)

    class Raw:
        def __getattr__(self, name):
            raise AssertionError('No undeclared/future native field may be read: '+name)
    raw = Raw()
    raw.map_id, raw.battle_state = map_id, 0
    raw.event_flags, raw.bag_items = bytes(320), ((72, 1),)
    phases = {local:0, current:0, override:0}
    reads = []
    def read_u8(address):
        reads.append(address)
        return phases[address]
    return N(image=image, map_id=map_id, scope=scope, raw=raw, phases=phases,
             read_u8=read_u8, reads=reads, default=at(default), local=local,
             current=current, override=override, coords=at(coords))


def observe(s, monkeypatch):
    monkeypatch.setattr(p, 'verify_rom_bytes', lambda payload: None)
    return p.observe_scripted_wild_opposition(bytes(s.image), s.raw, scope=s.scope, read_u8=s.read_u8)


@pytest.mark.parametrize('level', [1, 17, 99, 100])
def test_derives_operand_instead_of_copying_expected_ghost_level(monkeypatch, level):
    s = fixture(level=level)
    proof = observe(s, monkeypatch)
    assert proof.level == level and proof.species_id == 59
    assert proof.opponent_levels == (level,)
    assert proof.trigger_coordinates == ((16, 10),) and proof.defeated_event == 271
    assert s.reads == [s.local, s.current, s.override]


@pytest.mark.parametrize('region,index,value', [
    ('default', 0, 0), ('default', 4, 0), ('default', 15, 0),
    ('default', 28, 0), ('default', 33, 0), ('default', 33, 101),
    ('default', 35, 0), ('default', 43, 0),
])
def test_mutated_opcode_guard_store_or_invalid_opponent_stays_unknown(monkeypatch, region, index, value):
    s = fixture()
    s.image[getattr(s, region)+index] = value
    assert observe(s, monkeypatch) is None


@pytest.mark.parametrize('address', [0x3160, 0x3157, 0x3D97, 0x34BF, p._LEVEL_DE_BRIDGE_OFFSET])
def test_unqualified_engine_grammar_stays_unknown(monkeypatch, address):
    s = fixture()
    s.image[address] ^= 1
    assert observe(s, monkeypatch) is None


@pytest.mark.parametrize('phase,value', [('local',4),('current',4),('override',16),('local',True),('current',None)])
def test_nondefault_or_unknown_native_phase_cannot_advertise_quote(monkeypatch, phase, value):
    s = fixture()
    s.phases[getattr(s, phase)] = value
    assert observe(s, monkeypatch) is None


@pytest.mark.parametrize('fault', ['map','engaged','event','scope_absent','scope_quantity','events_unknown','items_unknown'])
def test_gate_scope_refusals_never_use_enemy_ram(monkeypatch, fault):
    s = fixture()
    if fault == 'map':s.raw.map_id = 146
    elif fault == 'engaged':s.raw.battle_state = 1
    elif fault == 'event':
        events=bytearray(s.raw.event_flags);events[271//8]|=1<<(271%8);s.raw.event_flags=bytes(events)
    elif fault == 'scope_absent':s.raw.bag_items = ()
    elif fault == 'scope_quantity':s.raw.bag_items = ((72,2),)
    elif fault == 'events_unknown':s.raw.event_flags = None
    elif fault == 'items_unknown':s.raw.bag_items = None
    assert observe(s, monkeypatch) is None


def test_unsupported_rom_identity_does_not_decode_or_read_phases():
    s = fixture()
    assert p.observe_scripted_wild_opposition(b'unsupported',s.raw,scope=s.scope,read_u8=s.read_u8) is None
    assert s.reads == []


def test_witness_binds_source_and_exact_executor_reference(monkeypatch):
    s = fixture();proof = observe(s, monkeypatch)
    bound = p.BoundScriptedWildOpposition(proof, 'a'*64, 'private:existing-wild-binding')
    assert bound.document()['opposition']['level'] == 17
    with pytest.raises(ValueError):p.BoundScriptedWildOpposition(proof,'not-a-source','private:existing-wild-binding')


@pytest.mark.parametrize('fault', ['opcode','local_phase','override'])
def test_entry_helper_changed_or_guard_writes_are_unknown(monkeypatch,fault):
    s=fixture()
    if fault=='opcode':
        s.image[0x3C3C]=0
    else:
        address=s.local if fault=='local_phase' else s.override
        s.image[0x3C3C+6:0x3C3C+8]=address.to_bytes(2,'little')
    assert observe(s,monkeypatch) is None
