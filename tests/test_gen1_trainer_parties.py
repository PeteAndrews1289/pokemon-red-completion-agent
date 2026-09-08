from __future__ import annotations

import pytest

from pokemon_red_completion import gen1_trainer_parties as trainers
from pokemon_red_completion.gen1_cartridge import CartridgeReadError


@pytest.fixture
def rom(monkeypatch: pytest.MonkeyPatch) -> bytearray:
    # Independently specified machine code and asymmetric class/set layouts.
    data = bytearray(0x10000)
    party_code = bytes.fromhex("fa59d0d6c9872100424f0600092a666f")
    data[0x4100 : 0x4100 + len(party_code)] = party_code
    money_code = bytes.fromhex(
        "3e03cdbc35fa31d03d210044010500cd873a1133d02a12132a121146d02a12132a12"
    )
    data[0x0200 : 0x0200 + len(money_code)] = money_code
    # First class: two shared-level sets and one mixed-level set.
    # Second class: one set. Remaining empty classes share an end pointer.
    roster = bytes((21, 108, 0, 19, 96, 107, 0, 255, 50, 108, 12, 96, 0))
    data[0x4300 : 0x4300 + len(roster)] = roster
    data[0x430D:0x4310] = bytes((7, 108, 0))
    for i, pointer in enumerate((0x4300, 0x430D, *([0x4310] * 45))):
        data[0x4200 + i * 2 : 0x4202 + i * 2] = pointer.to_bytes(2, "little")
    data[0xC400:0xC40A] = bytes.fromhex("00450015000046007099")
    monkeypatch.setattr(trainers, "internal_to_dex", lambda _: {108: 23, 96: 27, 107: 41})
    return data


def quote(rom: bytearray, opponent: int = 201, number: int = 1):
    return trainers.trainer_party_quote(bytes(rom), opponent, number)


def test_independent_party_set_and_money_strides(rom):
    first, second, other = quote(rom), quote(rom, number=2), quote(rom, 202)
    assert [(m.species, m.level) for m in first.party] == [(23, 21)]
    assert [(m.species, m.level) for m in second.party] == [(27, 19), (41, 19)]
    assert [(m.species, m.level) for m in other.party] == [(23, 7)]
    assert (first.base_money, first.expected_victory_money) == (15, 315)
    assert (second.base_money, second.expected_victory_money) == (15, 285)
    assert (other.base_money, other.expected_victory_money) == (70, 490)
    # The unused third bcd3 byte is 99 in the second class, not another factor.


def test_mixed_level_reward_uses_last_not_first_or_max(rom):
    result = quote(rom, number=3)
    assert [(m.species, m.level) for m in result.party] == [(23, 50), (27, 12)]
    assert result.expected_victory_money == 180
    assert result.expected_money_after(9) == 189
    assert result.expected_money_after(999990) == 999999


@pytest.mark.parametrize("money", [-1, True, 1.5, 1000000])
def test_money_before_must_be_valid(rom, money):
    with pytest.raises(ValueError):
        quote(rom).expected_money_after(money)


@pytest.mark.parametrize(
    "opponent,number",
    [(200, 1), (247, 1), (True, 1), (201, 0), (201, 256), (201, True), (201, 1.5)],
)
def test_refuse_invalid_or_unbounded_identity(rom, opponent, number):
    with pytest.raises(CartridgeReadError):
        quote(rom, opponent, number)


@pytest.mark.parametrize("opponent,number", [(201, 4), (202, 2), (203, 1)])
def test_missing_sets_never_borrow_next_class(rom, opponent, number):
    with pytest.raises(CartridgeReadError, match="extent"):
        quote(rom, opponent, number)


@pytest.mark.parametrize(
    "offset,value",
    [(0x4300, 0), (0x4300, 101), (0x4301, 0), (0x4301, 190), (0x4308, 101), (0x430C, 108)],
)
def test_malformed_selected_and_skipped_records_refuse(rom, offset, value):
    rom[offset] = value
    with pytest.raises(CartridgeReadError):
        quote(rom, number=3)


def test_six_members_allowed_but_seven_refused(rom):
    rom[0x4300:0x430D] = bytes((8, 108, 96, 107, 108, 96, 107, 0, 0, 0, 0, 0, 0))
    assert len(quote(rom).party) == 6
    rom[0x4307:0x4309] = bytes((108, 0))
    with pytest.raises(CartridgeReadError, match="six"):
        quote(rom)


@pytest.mark.parametrize("start,length", [(0x4100, 64), (0x0200, 64)])
def test_missing_or_ambiguous_code_anchor_refuses(rom, start, length):
    original = rom[start : start + length]
    rom[start] = 0
    with pytest.raises(CartridgeReadError, match="anchor"):
        quote(rom)
    rom[start : start + length] = original
    rom[0x1000 : 0x1000 + length] = original
    with pytest.raises(CartridgeReadError, match="anchor"):
        quote(rom)


@pytest.mark.parametrize(
    "offset,value", [(0x4108, 0x80), (0x0201, 0), (0x020C, 0x80), (0x4201, 0x80), (0x4203, 0x42)]
)
def test_pointer_and_bank_corruption_refuse(rom, offset, value):
    rom[offset] = value
    with pytest.raises(CartridgeReadError):
        quote(rom)


@pytest.mark.parametrize("value", [0xFA, 0])
def test_invalid_or_zero_bcd_reward_refuses(rom, value):
    rom[0xC403] = value
    with pytest.raises(CartridgeReadError, match="money|reward"):
        quote(rom)


def test_rom_truncation_refuses(rom):
    with pytest.raises(CartridgeReadError, match="truncated"):
        quote(rom[:0xC405])
