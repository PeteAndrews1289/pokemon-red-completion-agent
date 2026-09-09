"""Opt-in decoding of the cartridge's one-shot trainer-room entrance walk.

This recognizes one bounded Gen I script grammar, not arbitrary machine code.
Unknown revisions, visited entrances or different scripts fail closed. It only
supplies an exact settled coordinate; the route executor still rejects drift.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .gen1_cartridge import MAP_ID_LIMIT, CartridgeReadError, bank_offset
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS, SCRIPT_POINTER_OFFSET
from .gen1_trainer_sight import EVENT_FLAGS_START
from .global_router import MacroGraph
from .rom import verify_rom_bytes


@dataclass(frozen=True, slots=True)
class ScriptedTrainerArrival:
    map_id: int
    entrance_coordinates: tuple[tuple[int, int], ...]
    direction: tuple[int, int]
    steps: int
    event_flag: int

    def settled_at(self, coordinate: tuple[int, int]) -> tuple[int, int]:
        if coordinate not in self.entrance_coordinates:
            return coordinate
        return (
            coordinate[0] + self.direction[0] * self.steps,
            coordinate[1] + self.direction[1] * self.steps,
        )


def trainer_room_arrival(rom: bytes, map_id: int, events: bytes) -> ScriptedTrainerArrival:
    """Qualify critical engine callees with the existing exact Red revision pin.

    The local grammar alone cannot prove what arbitrary CALL targets do. A ROM
    modification requires separate engine qualification, never silent acceptance.
    """
    verify_rom_bytes(rom)
    return _decode_trainer_room_arrival(rom, map_id, events)


def _decode_trainer_room_arrival(rom: bytes, map_id: int, events: bytes) -> ScriptedTrainerArrival:
    """Follow script-table/default/relative-walk pointers, then check its event."""

    def require(ok: bool) -> None:
        if not ok:
            raise CartridgeReadError("unsupported or already consumed scripted trainer arrival")

    require(type(map_id) is int and 0 <= map_id < MAP_ID_LIMIT)
    require(isinstance(rom, bytes) and len(rom) > MAP_HEADER_BANKS + map_id)
    bank = rom[MAP_HEADER_BANKS + map_id]

    def word(at: int) -> int:
        require(0 <= at <= len(rom) - 2)
        return int.from_bytes(rom[at : at + 2], "little")

    def read(at: int, count: int) -> bytes:
        require(at >= 0 and at + count <= len(rom))
        return rom[at : at + count]

    header = bank_offset(bank, word(MAP_HEADER_POINTERS + map_id * 2))
    script = bank_offset(bank, word(header + SCRIPT_POINTER_OFFSET))
    entry = read(script, 22)
    require(entry[0] == entry[3] == entry[15] == 0xCD)
    require(
        entry[6] == 0x21
        and entry[9] == 0x11
        and entry[12] == 0xFA
        and entry[18] == 0xEA
        and entry[21] == 0xC9
        and entry[13:15] == entry[19:21]
    )
    table = bank_offset(bank, word(script + 10))
    default = bank_offset(bank, word(table))
    code = read(default, 36)
    require(code[0] == 0x21 and code[3] == 0xCD and code[6] == 0xD2)
    require(code[9:27] == bytes.fromhex("af e0 b3 e0 b4 ea d3 cc ea 38 cd fa 3d cd fe 03 38 09"))
    require(code[27] == 0x21 and code[30] == code[32] == 0xCB and code[34] == 0x28)
    bit = (code[31] - 0x46) // 8
    require(0 <= bit < 8 and code[31] == 0x46 + 8 * bit and code[33] == 0xC6 + 8 * bit)
    event_address = word(default + 28)
    event_index = event_address - EVENT_FLAGS_START
    require(isinstance(events, bytes) and 0 <= event_index < len(events))
    require(not bool(events[event_index] & (1 << bit)))
    delta = int.from_bytes(code[35:36], "little", signed=True)
    walk_at = default + 36 + delta
    walk = read(walk_at, 48)
    require(walk[:4] == bytes.fromhex("21 d3 cc 3e"))
    directions = {0x40: (-1, 0), 0x80: (1, 0), 0x20: (0, -1), 0x10: (0, 1)}
    require(walk[4] in directions)
    cursor = 5
    while cursor < 20 and walk[cursor] == 0x22:
        cursor += 1
    count = cursor - 4
    require(1 <= count <= 12 and walk[cursor : cursor + 3] == bytes((0x77, 0x3E, count)))
    tail = walk[cursor + 3 : cursor + 18]
    require(tail[:4] == bytes.fromhex("ea 38 cd cd") and tail[6:8] == bytes.fromhex("3e 03"))
    require(
        tail[8] == 0xEA
        and tail[9:11] == entry[13:15]
        and tail[11:15] == bytes.fromhex("ea 39 da c9")
    )
    coords_at = bank_offset(bank, word(default + 1))
    coordinates = read(coords_at, 9)
    require(coordinates[-1] == 0xFF)
    entrance = tuple((coordinates[i], coordinates[i + 1]) for i in (4, 6))
    # The first two entries are the blocked exit row; coord-index >=3 is the
    # one-shot automatic entrance branch above. Do not apply it to every warp.
    require(
        coordinates[:4]
        == bytes((entrance[0][0] - 1, entrance[0][1], entrance[1][0] - 1, entrance[1][1]))
    )
    result = ScriptedTrainerArrival(
        map_id, entrance, directions[walk[4]], count, event_index * 8 + bit
    )
    require(all(min(result.settled_at(at)) >= 0 for at in entrance))
    return result


def with_scripted_trainer_arrival(
    graph: MacroGraph,
    arrival: ScriptedTrainerArrival,
) -> MacroGraph:
    """Override only authenticated destination warp arrivals; topology is unchanged."""
    if graph.warp_arrivals is None or arrival.map_id not in graph.warp_arrivals:
        raise CartridgeReadError("scripted arrival needs qualified warp metadata")
    old = graph.warp_arrivals[arrival.map_id]
    if not set(arrival.entrance_coordinates).issubset(old):
        raise CartridgeReadError("script entrance does not match destination warps")
    return replace(
        graph,
        warp_arrivals={
            **graph.warp_arrivals,
            arrival.map_id: tuple(arrival.settled_at(at) for at in old),
        },
    )
