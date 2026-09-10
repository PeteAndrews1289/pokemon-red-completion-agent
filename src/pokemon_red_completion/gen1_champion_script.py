"""Qualify Red's distinct scripted final trainer from cartridge operands.

This is a bounded grammar, not a CPU interpreter or a transfer claim. The exact
ROM gate qualifies engine callees. Movement is descriptive: the cartridge runs
its own queue; the actor must not replay these directions over that queue.
"""

from dataclasses import dataclass

from .gen1_cartridge import CartridgeReadError, bank_offset
from .gen1_joypad_rle import decode_direction_runs
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS, SCRIPT_POINTER_OFFSET
from .rom import verify_rom_bytes


@dataclass(frozen=True, slots=True)
class ChampionScriptBinding:
    opponent: int
    trainer_class: int
    trainer_set: int
    event_flag: int
    entry_runs: tuple[tuple[tuple[int, int], int], ...]
    exit_runs: tuple[tuple[tuple[int, int], int], ...]
    hall_runs: tuple[tuple[tuple[int, int], int], ...]

    @property
    def active_identity(self) -> tuple[int, int, int]:
        return self.opponent, self.trainer_class, self.trainer_set


def champion_script_binding(rom: bytes, rival_starter: int) -> ChampionScriptBinding:
    verify_rom_bytes(rom)
    return _decode_champion_script(rom, rival_starter)


def _decode_champion_script(rom: bytes, rival_starter: int) -> ChampionScriptBinding:
    def require(ok: bool) -> None:
        if not ok:
            raise CartridgeReadError("unsupported final-trainer scene grammar")

    require(type(rom) is bytes and type(rival_starter) is int and 1 <= rival_starter <= 190)

    def script_table(map_id: int, count: int, address: bytes):
        require(len(rom) > max(MAP_HEADER_BANKS + map_id, MAP_HEADER_POINTERS + 2 * map_id + 1))
        bank = rom[MAP_HEADER_BANKS + map_id]

        def read(at: int, size: int) -> bytes:
            require(bank * 0x4000 <= at and at + size <= min(len(rom), (bank + 1) * 0x4000))
            return rom[at : at + size]

        def pointer(at: int) -> int:
            return bank_offset(bank, int.from_bytes(read(at, 2), "little"))

        header = bank_offset(
            bank,
            int.from_bytes(
                rom[MAP_HEADER_POINTERS + 2 * map_id : MAP_HEADER_POINTERS + 2 * map_id + 2],
                "little",
            ),
        )
        script = pointer(header + SCRIPT_POINTER_OFFSET)
        entry = read(script, 12)
        require(
            entry[:4] == bytes.fromhex("cd 3c 3c 21")
            and entry[6:7] == b"\xfa"
            and entry[7:9] == address
            and entry[9:] == bytes.fromhex("c3 97 3d")
        )
        table = pointer(script + 4)
        return read, pointer, tuple(pointer(table + 2 * i) for i in range(count))

    read, pointer, stages = script_table(120, 11, bytes.fromhex("4c d6"))
    require(read(stages[0], 1) == b"\xc9")

    def runs(read, pointer, at: int, stage: int, address: bytes):
        code = read(at, 27)
        require(
            code[:9] == bytes.fromhex("3e ff ea 6b cd 21 d3 cc 11")
            and code[11:23] == bytes.fromhex("cd 0c 35 3d ea 38 cd cd 86 34 3e") + bytes((stage,))
            and code[23:24] == b"\xea"
            and code[24:26] == address
            and code[26:] == b"\xc9"
        )
        start = pointer(at + 9)
        data = bytearray()
        for index in range(51):
            direction = read(start + index * 2, 1)
            data.extend(direction)
            if direction == b"\xff":
                break
            data.extend(read(start + index * 2 + 1, 1))
        else:
            raise CartridgeReadError("unterminated final-scene movement")
        return tuple(reversed(decode_direction_runs(bytes(data), max_steps=100)))

    entry_runs = runs(read, pointer, stages[1], 2, bytes.fromhex("4c d6"))
    exit_runs = runs(read, pointer, stages[9], 10, bytes.fromhex("4c d6"))
    ready = read(stages[2], 81)
    require(
        ready[:6] == bytes.fromhex("fa 38 cd a7 c0 cd")
        and ready[43] == 0x3E
        and ready[45:50] == bytes.fromhex("ea 59 d0 fa 15")
        and ready[50] == 0xD7
        and ready[51] == 0xFE
        and ready[53:59] == bytes.fromhex("20 04 3e 01 18 0a")
        and ready[59] == 0xFE
        and ready[61:]
        == bytes.fromhex("20 04 3e 02 18 02 3e 03 ea 5d d0 af e0 b4 3e 03 ea 4c d6 c9")
    )
    opponent = ready[44]
    require(201 <= opponent <= 247 and ready[52] != ready[60])
    trainer_set = 1 if rival_starter == ready[52] else 2 if rival_starter == ready[60] else 3
    defeated = read(stages[3], 41)
    require(
        defeated[:6] == bytes.fromhex("fa 57 d0 fe ff ca")
        and defeated[8] == 0xCD
        and defeated[11] == 0x21
        and defeated[14] == 0xCB
        and defeated[-6:] == bytes.fromhex("3e 04 ea 4c d6 c9")
    )
    bit = (defeated[15] - 0xC6) // 8
    event_byte = int.from_bytes(defeated[12:14], "little") - 0xD747
    require(0 <= bit < 8 and defeated[15] == 0xC6 + bit * 8 and 0 <= event_byte < 320)
    require(read(stages[10], 15) == bytes.fromhex("fa 38 cd a7 c0 af ea 6b cd 3e 00 ea 4c d6 c9"))
    hall_read, hall_pointer, hall_stages = script_table(118, 4, bytes.fromhex("4b d6"))
    hall_runs = runs(hall_read, hall_pointer, hall_stages[0], 1, bytes.fromhex("4b d6"))
    require(
        hall_read(hall_stages[1], 5) == bytes.fromhex("fa 38 cd a7 c0")
        and hall_read(hall_stages[3], 1) == b"\xc9"
    )
    return ChampionScriptBinding(
        opponent,
        opponent - 200,
        trainer_set,
        event_byte * 8 + bit,
        entry_runs,
        exit_runs,
        hall_runs,
    )
