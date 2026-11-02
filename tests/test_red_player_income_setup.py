from hashlib import sha256

import pytest
from test_red_battle_practice_cartridge import _synthetic_rom
from test_red_player_training_setup import fixture

import pokemon_red_completion.red_player_income_setup as setup
from pokemon_red_completion.observation import SQUIRTLE_SPECIES_ID, MapId, RamAddress


def inputs(monkeypatch):
    rom, _ = _synthetic_rom(monkeypatch)
    rom = bytes(rom)
    digest = sha256(rom).hexdigest()
    monkeypatch.setattr(setup, "RED_ROM_SHA256", digest)
    memory = fixture()
    memory[RamAddress.PARTY_MON_1] = SQUIRTLE_SPECIES_ID
    memory[int(RamAddress.PARTY_MON_1)+27:int(RamAddress.PARTY_MON_1)+29] = b"\x98\x88"
    return memory, dict(rom=rom, rom_sha256=digest, isolated_training_setup=True,
        controller_released=True, battle_state=0, partition="train",
        level=19, money=550, balls=2, forest_warp=3)


def test_fixture_writes_are_complete_and_specimen_identity_preserved(monkeypatch):
    memory, args = inputs(monkeypatch)
    before = bytes(memory)
    rows = setup.prepare_income_fixture(memory, **args)
    addresses = {row["address"] for row in rows}
    assert all(memory[i] == value for i, value in enumerate(before) if i not in addresses)
    assert all(before[r["address"]] == r["before"] and memory[r["address"]] == r["after"]
               for r in rows)
    base = int(RamAddress.PARTY_MON_1)
    assert memory[base] == SQUIRTLE_SPECIES_ID and memory[base+33] == 19
    assert memory[base+27:base+29] == before[base+27:base+29]
    assert memory[base+12:base+14] == before[base+12:base+14]
    assert memory[base+1:base+3] == memory[base+34:base+36]
    assert memory[RamAddress.CURRENT_MAP] == MapId.OAKS_LAB
    assert memory[0xD3B2] == memory[0xD3B6] == MapId.VIRIDIAN_FOREST
    assert memory[0xD3B1] == memory[0xD3B5] == 3
    cash = int(RamAddress.PLAYER_MONEY)
    assert memory[cash:cash+3] == b"\x00\x05\x50"
    bag = int(RamAddress.BAG_ITEMS)
    assert memory[bag:bag+3] == bytes((4, 2, 255))
    terminal = bytes(memory)
    with pytest.raises(ValueError):
        setup.prepare_income_fixture(memory, **args)
    assert bytes(memory) == terminal


@pytest.mark.parametrize("key,value", [
    ("partition", "development"), ("isolated_training_setup", False),
    ("controller_released", False), ("battle_state", True), ("battle_state", 1),
    ("rom_sha256", "a"*64), ("rom", b"wrong"), ("level", 31), ("level", True),
    ("money", -1), ("money", True), ("balls", 100), ("forest_warp", 0),
])
def test_invalid_authority_and_bounds_never_write(monkeypatch, key, value):
    memory, args = inputs(monkeypatch)
    before = bytes(memory)
    args[key] = value
    with pytest.raises(ValueError):
        setup.prepare_income_fixture(memory, **args)
    assert bytes(memory) == before


@pytest.mark.parametrize("address", [RamAddress.CURRENT_MAP, RamAddress.PARTY_MON_1,
    RamAddress.PARTY_COUNT, RamAddress.NUM_BAG_ITEMS, 0xD3AF, int(RamAddress.PARTY_MON_1)+17])
def test_nonfresh_source_never_writes(monkeypatch, address):
    memory, args = inputs(monkeypatch)
    memory[address] += 1
    before = bytes(memory)
    with pytest.raises(ValueError):
        setup.prepare_income_fixture(memory, **args)
    assert bytes(memory) == before
