"""ROM-free first-rival script and hostile handoff tests; second scope stays strict."""

from dataclasses import replace
from types import SimpleNamespace as N

import pytest
from test_route22_learned_entry import available, cartridge

from pokemon_red_completion import gen1_route22_script as script
from pokemon_red_completion import red_player_engaged_story as engaged
from pokemon_red_completion import red_player_route22_rival as rival


def first_cartridge(bank=3, shift=0, starters=(7, 9, 11)):
    rom = bytearray(cartridge(bank, shift, starters=starters))

    def word(value):
        return (value + shift).to_bytes(2, "little")

    def put(at, data):
        offset = (bank - 1) * 0x4000 + at + shift
        rom[offset:offset + len(data)] = data

    put(0x4500, bytes.fromhex(
        "fa 30 d7 cb 47 c0 fa 0d cf fe 01 20 09 3e 04 ea 28 d5 "
        "3e 04 18 02 3e 0c e0 8d 3e 01 e0 8c cd a6 34 af ea 6b cd "
        "3e 01 e0 8c cd 20 29 21 2d d7 cb f6 cb fe 21"
    ) + word(0x4D00) + b"\x11" + word(0x4D10)
        + bytes.fromhex("cd 54 33 3e e1 ea 59 d0 21") + word(0x4E20)
        + b"\xcd" + word(0x4F00) + bytes.fromhex("3e 02 ea 0a d6 c9"))
    put(0x4E20, bytes((starters[0], 4, starters[1], 5, starters[2], 6)))
    put(0x4600, bytes.fromhex("fa 57 d0 fe ff ca") + word(0x4F30) + bytes.fromhex(
        "fa 09 c1 a7 20 04 3e 04 18 02 3e 0c e0 8d 3e 01 e0 8c "
        "cd a6 34 3e f0 ea 6b cd 21 eb d7 cb ee"
    ))
    put(0x4700, bytes.fromhex(
        "fa 30 d7 cb 47 c0 af ea 6b cd 3e 22 ea 4d cc 3e 11 cd 6d 3e "
        "cd 07 23 21 eb d7 cb 86 cb be 3e 00 ea 0a d6 c9"
    ))
    return bytes(rom)


def first_raw():
    raw = available()
    flags = bytearray(raw.event_flags)
    flags[0xA4] = 0x81
    return replace(raw, badge_bits=0, player_y=2, player_x=8, event_flags=bytes(flags))


@pytest.mark.parametrize("bank,shift", [(3, 0), (7, 256)])
@pytest.mark.parametrize("starter,team", [(7, 4), (9, 5), (11, 6)])
def test_first_identity_and_defeat_operand_are_distinct(bank, shift, starter, team):
    rom = first_cartridge(bank, shift)
    binding = script._decode_first(rom, starter)
    assert binding.identity == (225, 25, team)
    assert binding.defeated_event == 1317 and binding.triggers == ((2, 8), (3, 8))
    binding.require_available(first_raw())
    with pytest.raises(ValueError, match="second rival unavailable"):
        script._decode(rom, starter).require_available(first_raw())
    with pytest.raises(ValueError, match="first rival unavailable"):
        binding.require_available(available())


@pytest.mark.parametrize("at", [0x4504, 0x4528, 0x453F, 0x4548, 0x460C, 0x4626, 0x471B])
def test_wrong_first_grammar_fails_closed(at):
    rom = bytearray(first_cartridge())
    rom[0x8000 + at] ^= 0xFF
    with pytest.raises(script.CartridgeReadError):
        script._decode_first(bytes(rom), 7)


@pytest.mark.parametrize("bit", [0, 1, 5, 7])
def test_first_event_prerequisites_remain_strict(bit):
    raw = first_raw()
    flags = bytearray(raw.event_flags)
    flags[0xA4] ^= 1 << bit
    with pytest.raises(ValueError):
        script._decode_first(first_cartridge(), 7).require_available(
            replace(raw, event_flags=bytes(flags))
        )


def fixture(monkeypatch, *, phase=1, battle=0):
    raw = replace(first_raw(), battle_state=battle)
    monkeypatch.setattr(script, "verify_rom_bytes", lambda _: None)
    reader = N(read=lambda: raw, read_rival_starter=lambda: 7,
        read_route22_script=lambda: phase, read_active_trainer_identity=lambda: (225, 25, 4),
        read_input_readiness=lambda: N(ready=False),
        read_pending_trainer_battle_identity=lambda: None)
    monkeypatch.setattr(rival, "trainer_party_quote", lambda *args: N(
        party=(N(internal_species=7),), expected_victory_money=280))
    return reader, raw


@pytest.mark.parametrize("phase,battle", [(1, 0), (2, 0), (2, 2)])
def test_exact_first_introduction_and_live_battle_bind_without_input(monkeypatch, phase, battle):
    reader, raw = fixture(monkeypatch, phase=phase, battle=battle)
    contract = rival.retained_first_route22_contract(
        first_cartridge(), reader, objective_id="defeat_brock"
    )
    assert contract.trainer_identity == (225, 25, 4) and contract.defeated_event == 1317
    assert contract.victory_money == 280 and contract.objective_id == "defeat_brock"
    assert contract.battle_plan_id == "retained-route22-first-rival"
    assert reader.read() == raw


@pytest.mark.parametrize("phase", [0, 3, 4, 5, 6, 7])
def test_unowned_script_phase_is_not_an_early_rival(monkeypatch, phase):
    reader, _ = fixture(monkeypatch, phase=phase)
    assert rival.retained_first_route22_contract(
        first_cartridge(), reader, objective_id="defeat_brock"
    ) is None


def test_first_handoff_reuses_engaged_contract_without_crediting_brock(monkeypatch):
    reader, _ = fixture(monkeypatch, phase=2)
    contract = engaged.engaged_story_contract(
        reader, first_cartridge(), objective_id="defeat_brock"
    )
    assert contract.battle_plan_id == "retained-route22-first-rival"
    assert contract.defeated_event == 1317 and contract.victory_badge_bits == 0
    assert contract.victory_items == () and contract.map_id == 33


@pytest.mark.parametrize("fault", ["trigger", "ready", "pending", "identity", "party", "events"])
def test_ambiguous_first_handoff_is_rejected(monkeypatch, fault):
    reader, raw = fixture(monkeypatch, phase=2, battle=2 if fault == "identity" else 0)
    if fault == "trigger":
        reader.read = lambda: replace(raw, player_x=9)
    elif fault == "ready":
        reader.read_input_readiness = lambda: N(ready=True)
    elif fault == "pending":
        reader.read_pending_trainer_battle_identity = lambda: (242, 11)
    elif fault == "identity":
        reader.read_active_trainer_identity = lambda: (242, 42, 11)
    elif fault == "events":
        reader.read = lambda: replace(raw, event_flags=None)
    else:
        monkeypatch.setattr(rival, "trainer_party_quote", lambda *args: N(
            party=(N(internal_species=9),), expected_victory_money=280))
    with pytest.raises(ValueError):
        rival.retained_first_route22_contract(
            first_cartridge(), reader, objective_id="defeat_brock"
        )
