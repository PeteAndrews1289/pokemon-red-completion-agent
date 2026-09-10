"""Cartridge-derived trainer rosters and ordinary victory-money quotes.

Locate tables through the instructions that consume them, not through copied
trainer lists. See pret/pokered revision a1a22aaf84d1675bcdbaeb194592379d586d838e,
engine/battle/read_trainer_party.asm and home/trainers2.asm. This is an inventory
adapter, not battle authorization: moves, AI, approach safety and actual payout
still need separate verification. Link battles remain unsupported. The final
class has no next-class pointer and requires a separate exact-Red opt-in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .gen1_cartridge import CartridgeReadError, bank_offset, internal_to_dex
from .rom import verify_rom_bytes

_PARTY_CODE = re.compile(
    rb"\xfa\x59\xd0\xd6\xc9\x87\x21(..)\x4f\x06\x00\x09\x2a\x66\x6f",
    re.DOTALL,
)
_MONEY_CODE = re.compile(
    rb"\x3e(.)\xcd..\xfa\x31\xd0\x3d\x21(..)\x01\x05\x00\xcd.."
    rb"\x11\x33\xd0\x2a\x12\x13\x2a\x12\x11\x46\xd0\x2a\x12\x13\x2a\x12",
    re.DOTALL,
)
_CLASS_COUNT = 47


@dataclass(frozen=True, slots=True)
class TrainerPartyMember:
    internal_species: int
    species: int
    level: int


@dataclass(frozen=True, slots=True)
class TrainerPartyQuote:
    opponent_id: int
    trainer_set: int
    party: tuple[TrainerPartyMember, ...]
    base_money: int
    expected_victory_money: int

    def expected_money_after(self, money_before: int) -> int:
        """Ordinary reward only: exclude Pay Day or any other money changes."""
        if type(money_before) is not int or not 0 <= money_before <= 999999:
            raise ValueError("money_before must be a six-digit nonnegative integer")
        return min(999999, money_before + self.expected_victory_money)


def _unique(rom: bytes, pattern: re.Pattern[bytes], label: str) -> re.Match[bytes]:
    matches = list(pattern.finditer(rom))
    if len(matches) != 1:
        raise CartridgeReadError(f"expected one {label} instruction anchor, found {len(matches)}")
    match = matches[0]
    if match.start() // 0x4000 != (match.end() - 1) // 0x4000:
        raise CartridgeReadError(f"{label} instruction anchor crosses a bank")
    return match


def _pointer(rom: bytes, bank: int, operand: bytes, size: int) -> int:
    address = int.from_bytes(operand, "little")
    if bank < 1 or not 0x4000 <= address < 0x8000 or address + size > 0x8000:
        raise CartridgeReadError("trainer table pointer is outside its switchable bank")
    offset = bank_offset(bank, address)
    if offset + size > len(rom):
        raise CartridgeReadError("truncated trainer table")
    return offset


def trainer_party_quote(
    rom: bytes, opponent_id: int, trainer_set: int, *, allow_final_class: bool = False,
) -> TrainerPartyQuote:
    """Read a one-based trainer set without scanning into the next class.

    Opponent IDs include the cartridge's 200 offset. Class47 has no following
    pointer: by default it still refuses. Explicit supported-Red callers may
    quote only its first set, bounded to one six-member record and its bank;
    exact revision verification qualifies that set as Lance, not arbitrary
    trailing bytes or a second invented set. Empty classes,
    missing sets, malformed species and unterminated or oversized parties refuse.
    Mixed-level rosters are supported, but special move overrides are not quoted.
    """
    if type(allow_final_class) is not bool:
        raise TypeError("allow_final_class must be boolean")
    final_class = type(opponent_id) is int and opponent_id == 200 + _CLASS_COUNT
    if type(opponent_id) is not int or not 201 <= opponent_id <= 200 + _CLASS_COUNT:
        raise CartridgeReadError("trainer opponent needs a bounded class (201..246)")
    if type(trainer_set) is not int or not 1 <= trainer_set <= 255:
        raise CartridgeReadError("trainer set must be one-based and fit a byte")
    if final_class:
        if not allow_final_class or trainer_set != 1:
            raise CartridgeReadError(
                "final trainer class needs an explicit first-set qualification"
            )
        verify_rom_bytes(rom)
    code = _unique(rom, _PARTY_CODE, "trainer-party")
    bank = code.start() // 0x4000
    table = _pointer(rom, bank, code.group(1), 2 * _CLASS_COUNT)
    pointers = [
        _pointer(rom, bank, rom[table + 2 * i : table + 2 * i + 2], 0) for i in range(_CLASS_COUNT)
    ]
    if pointers[0] < table + 2 * _CLASS_COUNT or pointers != sorted(pointers):
        raise CartridgeReadError("trainer class extents are not ordered after their table")
    index = opponent_id - 201
    if final_class:
        cursor = pointers[index]
        end = min(cursor + 14, (bank + 1) * 0x4000, len(rom))
    else:
        cursor, end = pointers[index : index + 2]
    dex = internal_to_dex(rom)
    selected: tuple[TrainerPartyMember, ...] | None = None
    for set_number in range(1, trainer_set + 1):
        if cursor >= end:
            raise CartridgeReadError("trainer set exceeds its class extent")
        shared_level = rom[cursor]
        cursor += 1
        if shared_level != 255 and not 1 <= shared_level <= 100:
            raise CartridgeReadError("invalid shared trainer level")
        party: list[TrainerPartyMember] = []
        while cursor < end and rom[cursor] != 0:
            if len(party) >= 6:
                raise CartridgeReadError("trainer party exceeds six members")
            level = shared_level
            if shared_level == 255:
                level = rom[cursor]
                cursor += 1
            if cursor >= end or not 1 <= level <= 100 or rom[cursor] not in dex:
                raise CartridgeReadError("invalid trainer level/species or truncated member")
            internal = rom[cursor]
            cursor += 1
            party.append(TrainerPartyMember(internal, dex[internal], level))
        if cursor >= end or not party:
            raise CartridgeReadError("empty or unterminated trainer party")
        cursor += 1
        if set_number == trainer_set:
            selected = tuple(party)
    assert selected is not None

    money_code = _unique(rom, _MONEY_CODE, "trainer-money")
    money_table = _pointer(rom, money_code.group(1)[0], money_code.group(2), 5 * _CLASS_COUNT)
    # GetTrainerInformation copies only the first two bytes of the bcd3 field.
    # ReadTrainer multiplies that value by the LAST party member's level.
    amount_at = money_table + 5 * index + 2
    digits = [n for byte in rom[amount_at : amount_at + 2] for n in (byte >> 4, byte & 15)]
    if any(n > 9 for n in digits):
        raise CartridgeReadError("trainer base money is not valid BCD")
    base = 1000 * digits[0] + 100 * digits[1] + 10 * digits[2] + digits[3]
    if base == 0:
        raise CartridgeReadError("trainer has no ordinary victory reward")
    return TrainerPartyQuote(opponent_id, trainer_set, selected, base, base * selected[-1].level)
