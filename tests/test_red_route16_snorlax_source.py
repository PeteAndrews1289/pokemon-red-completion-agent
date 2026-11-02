"""ROM-free exact second-source catalog and consumed-bit authentication."""
from types import SimpleNamespace as N

import pytest

from pokemon_red_completion import gen1_acquisition as cartridge
from pokemon_red_completion import red_snorlax_capture as source
from pokemon_red_completion.gen1_cartridge import CartridgeReadError


@pytest.mark.parametrize("fault", [None, "missing_test", "missing_set", "duplicate_set"])
def test_consumption_is_authenticated_bit_one_not_pending_bit_zero(monkeypatch, fault):
    rom=bytearray(max(cartridge.MAP_HEADER_BANKS+28,cartridge.MAP_HEADER_POINTERS+56,200))
    rom[cartridge.MAP_HEADER_BANKS+27]=1
    rom[cartridge.MAP_HEADER_POINTERS+54:cartridge.MAP_HEADER_POINTERS+56]=(40).to_bytes(2,"little")
    rom[47:49]=(60).to_bytes(2,"little")
    test=bytes.fromhex("21e0d7cb4ec21932cb46cb86ca1932")
    consume=bytes.fromhex("21e0d7cbcecdd73d")
    payload=(test if fault!="missing_test" else b"")+(consume if fault!="missing_set" else b"")
    if fault=="duplicate_set":
        payload+=consume
    rom[60:60+len(payload)]=payload
    monkeypatch.setattr(cartridge,"bank_offset",lambda bank,pointer:pointer)
    if fault:
        with pytest.raises(CartridgeReadError,match="consumed-bit"):
            cartridge.route16_snorlax_consumption_flag(bytes(rom))
    else:
        assert cartridge.route16_snorlax_consumption_flag(bytes(rom))==1225


@pytest.mark.parametrize("fault", [None, "level", "position", "trainer", "duplicate"])
def test_route16_target_is_exact_cartridge_species_object_level_and_event(monkeypatch,fault):
    source.route16_snorlax_target.cache_clear()
    entry=N(species=143,map_id=27,at=(10,26),level=31 if fault=="level" else 30)
    obj=N(sprite_id=67,at=(10,25) if fault=="position" else (10,26),
          is_trainer=fault=="trainer",object_index=1)
    monkeypatch.setattr(source,"verify_rom_bytes",lambda _:None)
    monkeypatch.setattr(source,"static_encounters",
        lambda _:(entry,entry) if fault=="duplicate" else (entry,))
    monkeypatch.setattr(source,"map_object_events",lambda *_:(obj,))
    monkeypatch.setattr(source,"route16_snorlax_consumption_flag",lambda _:1225)
    if fault:
        with pytest.raises(ValueError,match="differs"):
            source.route16_snorlax_target(b"fixture")
    else:
        target=source.route16_snorlax_target(b"fixture")
        assert (target.species_number,target.map_id,target.at,target.event_flag)==(
            143,27,(10,26),1225)
    source.route16_snorlax_target.cache_clear()
