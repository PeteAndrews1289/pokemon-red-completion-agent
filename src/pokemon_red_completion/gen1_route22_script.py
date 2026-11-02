"""Decode the pinned cartridge's Route22 rival scripts, never battle policy.

Only this bounded script grammar is qualified. Coordinates, starter branches,
identity and completion event are cartridge operands, not walkthrough actions.
"""

from dataclasses import dataclass

from .gen1_cartridge import CartridgeReadError, bank_offset
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS, SCRIPT_POINTER_OFFSET
from .observation import EventFlag, event_flag_is_set
from .rom import verify_rom_bytes


@dataclass(frozen=True)
class RivalScriptBinding:
    triggers: tuple[tuple[int, int], ...]
    identity: tuple[int, int, int]
    defeated_event: int
    map_id: int = 33

    def require_available(self, raw):
        if (
            raw.event_flags is None
            or raw.badge_bits != 255
            or not event_flag_is_set(raw.event_flags, EventFlag.SECOND_ROUTE_22_RIVAL_BATTLE)
            or not event_flag_is_set(raw.event_flags, EventFlag.ROUTE_22_RIVAL_WANTS_BATTLE)
            or event_flag_is_set(raw.event_flags, 0x520)
            or event_flag_is_set(raw.event_flags, self.defeated_event)
        ):
            raise ValueError("second rival unavailable, consumed or ambiguous")


def route22_script_binding(rom, starter):
    verify_rom_bytes(rom)
    return _decode(rom, starter)


@dataclass(frozen=True)
class FirstRivalScriptBinding(RivalScriptBinding):
    def require_available(self, raw):
        if (
            raw.event_flags is None
            or not event_flag_is_set(raw.event_flags, 0x520)
            or event_flag_is_set(raw.event_flags, EventFlag.SECOND_ROUTE_22_RIVAL_BATTLE)
            or not event_flag_is_set(raw.event_flags, EventFlag.ROUTE_22_RIVAL_WANTS_BATTLE)
            or event_flag_is_set(raw.event_flags, self.defeated_event)
        ):
            raise ValueError("first rival unavailable, consumed or ambiguous")


def first_route22_script_binding(rom, starter):
    verify_rom_bytes(rom)
    return _decode_first(rom, starter)


def _decode_first(rom, starter):
    # Authenticate the shared trigger/default script and retain the independently
    # guarded second-rival contract. No first encounter is admitted by that class.
    shared = _decode(rom, starter)

    def require(ok):
        if not ok:
            raise CartridgeReadError("unsupported first Route22 script grammar")

    bank = rom[MAP_HEADER_BANKS + shared.map_id]

    def read(at, size):
        require(bank * 0x4000 <= at and at + size <= min(len(rom), (bank + 1) * 0x4000))
        return rom[at : at + size]

    def pointer(at):
        return bank_offset(bank, int.from_bytes(read(at, 2), "little"))

    header = bank_offset(
        bank, int.from_bytes(rom[MAP_HEADER_POINTERS + 66 : MAP_HEADER_POINTERS + 68], "little")
    )
    script = pointer(header + SCRIPT_POINTER_OFFSET)
    table = pointer(script + 4)
    stages = tuple(pointer(table + 2 * i) for i in range(8))
    start = read(stages[1], 77)
    require(
        start[:52] == bytes.fromhex(
            "fa 30 d7 cb 47 c0 fa 0d cf fe 01 20 09 3e 04 ea 28 d5 "
            "3e 04 18 02 3e 0c e0 8d 3e 01 e0 8c cd a6 34 af ea 6b cd "
            "3e 01 e0 8c cd 20 29 21 2d d7 cb f6 cb fe 21"
        )
        and start[54] == 0x11
        and start[57:61] == bytes.fromhex("cd 54 33 3e")
        and start[62:66] == bytes.fromhex("ea 59 d0 21")
        and start[68] == 0xCD
        and start[71:] == bytes.fromhex("3e 02 ea 0a d6 c9")
        and 201 <= start[61] <= 247
    )
    require(
        read(pointer(stages[1] + 69), 16)
        == bytes.fromhex("fa 15 d7 47 2a b8 28 03 23 18 f9 7e ea 5d d0 c9")
    )
    choices = read(pointer(stages[1] + 66), 6)
    branches = dict(zip(choices[::2], choices[1::2], strict=True))
    require(len(branches) == 3 and starter in branches and all(branches.values()))
    after = read(stages[2], 39)
    require(
        after[:6] == bytes.fromhex("fa 57 d0 fe ff ca")
        and after[8:35] == bytes.fromhex(
            "fa 09 c1 a7 20 04 3e 04 18 02 3e 0c e0 8d 3e 01 e0 8c "
            "cd a6 34 3e f0 ea 6b cd 21"
        )
        and after[37] == 0xCB
    )
    event_byte = int.from_bytes(after[35:37], "little") - 0xD747
    bit = (after[38] - 0xC6) // 8
    require(0 <= event_byte < 320 and 0 <= bit < 8 and after[38] == 0xC6 + 8 * bit)
    require(
        read(stages[3], 36) == bytes.fromhex(
            "fa 30 d7 cb 47 c0 af ea 6b cd 3e 22 ea 4d cc 3e 11 cd 6d 3e "
            "cd 07 23 21 eb d7 cb 86 cb be 3e 00 ea 0a d6 c9"
        )
    )
    return FirstRivalScriptBinding(
        shared.triggers, (start[61], start[61] - 200, branches[starter]), event_byte * 8 + bit
    )


def _decode(rom, starter):
    def require(ok):
        if not ok:
            raise CartridgeReadError("unsupported Route22 script grammar")

    require(type(rom) is bytes and type(starter) is int and 1 <= starter <= 190)
    require(len(rom) > MAP_HEADER_BANKS + 33)
    bank = rom[MAP_HEADER_BANKS + 33]

    def read(at, size):
        require(bank * 0x4000 <= at and at + size <= min(len(rom), (bank + 1) * 0x4000))
        return rom[at : at + size]

    def pointer(at):
        return bank_offset(bank, int.from_bytes(read(at, 2), "little"))

    header = bank_offset(
        bank, int.from_bytes(rom[MAP_HEADER_POINTERS + 66 : MAP_HEADER_POINTERS + 68], "little")
    )
    script = pointer(header + SCRIPT_POINTER_OFFSET)
    entry = read(script, 12)
    require(
        entry[:4] == bytes.fromhex("cd 3c 3c 21")
        and entry[6:] == bytes.fromhex("fa 0a d6 c3 97 3d")
    )
    table = pointer(script + 4)
    stages = tuple(pointer(table + 2 * i) for i in range(8))
    default = read(stages[0], 45)
    require(
        default[:7] == bytes.fromhex("fa eb d7 cb 7f c8 21")
        and default[9:39]
        == bytes.fromhex(
            "cd bf 34 d0 fa 3d cd ea 0d cf af e0 b4 3e f0 ea 6b cd "
            "3e 02 ea 28 d5 fa eb d7 cb 47 20 0b"
        )
        and default[39:42] == bytes.fromhex("cb 4f c2")
        and default[44] == 0xC9
    )
    coords = read(pointer(stages[0] + 7), 5)
    require(coords[4] == 255 and coords[:2] != coords[2:4] and all(v < 64 for v in coords[:4]))
    start = read(stages[4], 82)
    require(
        start[:6] == bytes.fromhex("fa 30 d7 cb 47 c0")
        and start[6:10] == bytes.fromhex("3e 02 e0 8c")
        and start[38:54] == bytes.fromhex("af ea 6b cd 3e 02 e0 8c cd 20 29 21 2d d7 cb f6")
        and start[54:57] == bytes.fromhex("cb fe 21")
        and start[59] == 0x11
        and start[62:66] == bytes.fromhex("cd 54 33 3e")
        and start[67:71] == bytes.fromhex("ea 59 d0 21")
        and start[73] == 0xCD
        and start[76:] == bytes.fromhex("3e 05 ea 0a d6 c9")
    )
    require(
        read(pointer(stages[4] + 74), 16)
        == bytes.fromhex("fa 15 d7 47 2a b8 28 03 23 18 f9 7e ea 5d d0 c9")
    )
    choices = read(pointer(stages[4] + 71), 6)
    branches = dict(zip(choices[::2], choices[1::2], strict=True))
    require(
        len(branches) == 3
        and starter in branches
        and all(branches.values())
        and 201 <= start[66] <= 247
    )
    after = read(stages[5], 50)
    require(
        after[:6] == bytes.fromhex("fa 57 d0 fe ff ca")
        and after[40:46] == bytes.fromhex("3e f0 ea 6b cd 21")
        and after[48] == 0xCB
    )
    event_byte = int.from_bytes(after[46:48], "little") - 0xD747
    bit = (after[49] - 0xC6) // 8
    require(0 <= event_byte < 320 and 0 <= bit < 8 and after[49] == 0xC6 + 8 * bit)
    require(
        read(stages[6], 36)
        == bytes.fromhex(
            "fa 30 d7 cb 47 c0 af ea 6b cd 3e 23 ea 4d cc 3e 11 cd 6d 3e "
            "cd 07 23 21 eb d7 cb 8e cb be 3e 07 ea 0a d6 c9"
        )
    )
    return RivalScriptBinding(
        (tuple(coords[:2]), tuple(coords[2:4])),
        (start[66], start[66] - 200, branches[starter]),
        event_byte * 8 + bit,
    )
