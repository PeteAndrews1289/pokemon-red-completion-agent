from dataclasses import replace

import pytest

from pokemon_red_completion.observation import (
    PokemonRedStateReader,
    RamAddress,
    RawGameState,
    SemanticStateError,
)


class Memory:
    def __init__(self, values):
        self.values = values
        self.reads = []

    def read_u8(self, address):
        self.reads.append(int(address))
        return self.values.get(int(address), 0)


def test_enemy_status_uses_pinned_battle_struct_offset_without_snapshot_change(monkeypatch):
    memory = Memory({0xCFE9: 0x40, 0xCFE8: 7, 0xCFEA: 3})
    reader = PokemonRedStateReader(memory)
    raw = RawGameState(True, 35, 5, 30, 6, 1, enemy_hp=41)
    monkeypatch.setattr(reader, "read", lambda: raw)
    assert reader.read_enemy_capture_status() == 0x40
    assert memory.reads == [0xCFE9]
    assert int(RamAddress.ENEMY_STATUS) == int(RamAddress.ENEMY_SPECIES) + 4
    for state in (replace(raw, battle_state=0), replace(raw, battle_state=2),
                  replace(raw, enemy_hp=0), replace(raw, enemy_hp=None)):
        monkeypatch.setattr(reader, "read", lambda state=state: state)
        memory.reads.clear()
        assert reader.read_enemy_capture_status() is None
        assert memory.reads == []


def test_enemy_moves_are_actual_battle_slots_not_species_assumptions(monkeypatch):
    memory = Memory({0xCFED: 33, 0xCFEE: 100, 0xCFEF: 45, 0xCFF0: 0,
                     0xCFEC: 166, 0xCFF1: 166})
    reader = PokemonRedStateReader(memory)
    raw = RawGameState(True, 35, 5, 30, 6, 1, enemy_hp=41, enemy_species_id=108)
    monkeypatch.setattr(reader, 'read', lambda: raw)
    assert reader.read_enemy_capture_moves() == (33, 100, 45, 0)
    assert memory.reads == [0xCFED, 0xCFEE, 0xCFEF, 0xCFF0]
    assert int(RamAddress.ENEMY_MOVES) == int(RamAddress.ENEMY_SPECIES) + 8
    for state in (replace(raw, battle_state=0), replace(raw, battle_state=2),
                  replace(raw, enemy_hp=0), replace(raw, enemy_hp=None)):
        monkeypatch.setattr(reader, 'read', lambda state=state: state)
        memory.reads.clear()
        assert reader.read_enemy_capture_moves() is None
        assert memory.reads == []
    monkeypatch.setattr(reader, 'read', lambda: raw)
    memory.values[0xCFED] = 166
    with pytest.raises(SemanticStateError, match='move inventory'):
        reader.read_enemy_capture_moves()
    memory.values = {}
    with pytest.raises(SemanticStateError, match='move inventory'):
        reader.read_enemy_capture_moves()


def box_memory():
    values = {
        int(RamAddress.CURRENT_BOX_COUNT): 2,
        int(RamAddress.CURRENT_BOX_NUMBER): 0,
        int(RamAddress.CURRENT_BOX_SPECIES): 48,
        int(RamAddress.CURRENT_BOX_SPECIES) + 1: 164,
    }
    start = int(RamAddress.CURRENT_BOX_MONS)
    # Different adjacent members expose a broken 33-byte stride or field offset.
    for index, species, level, moves, pp in (
        (0, 48, 13, (1, 95, 50, 93), (35, 0xD1, 20, 25)),
        (1, 164, 40, (83, 39, 23, 45), (15, 30, 20, 40)),
    ):
        base = start + 33 * index
        values[base] = species
        values[base + 3] = level
        for slot in range(4):
            values[base + 8 + slot] = moves[slot]
            values[base + 29 + slot] = pp[slot]
    return Memory(values)


def test_box_move_inventory_preserves_slots_and_masks_pp_up_bits():
    rows = PokemonRedStateReader(box_memory()).read_current_box_move_members()
    assert [(row.box_slot, row.species_id, row.level) for row in rows] == [
        (1, 48, 13), (2, 164, 40),
    ]
    assert rows[0].moves == (1, 95, 50, 93)
    assert rows[0].pp == (35, 17, 20, 25)
    assert rows[1].moves == (83, 39, 23, 45)
    assert rows[1].pp == (15, 30, 20, 40)


def test_box_inventory_rejects_species_mismatch_and_invalid_moves():
    memory = box_memory()
    memory.values[int(RamAddress.CURRENT_BOX_SPECIES)] = 7
    with pytest.raises(SemanticStateError):
        PokemonRedStateReader(memory).read_current_box_move_members()
    memory = box_memory()
    memory.values[int(RamAddress.CURRENT_BOX_MONS) + 8] = 166
    with pytest.raises(ValueError):
        PokemonRedStateReader(memory).read_current_box_move_members()
