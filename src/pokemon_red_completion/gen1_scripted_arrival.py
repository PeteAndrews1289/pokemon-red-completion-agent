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
    direction_runs: tuple[tuple[tuple[int, int], int], ...] = ()
    interaction_coordinates: tuple[tuple[int, int], ...] = ()

    def settled_at(self, coordinate: tuple[int, int]) -> tuple[int, int]:
        if coordinate not in self.entrance_coordinates:
            return coordinate
        if self.direction_runs:
            y, x = coordinate
            for (dy, dx), count in self.direction_runs:
                y, x = y + dy * count, x + dx * count
            return y, x
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
    if type(events) is not bytes:
        raise CartridgeReadError("arrival qualification requires observed immutable event bytes")
    return _decode_trainer_room_arrival(rom, map_id, events)


def trainer_room_interaction_coordinates(rom: bytes, map_id: int) -> tuple[tuple[int, int], ...]:
    """Static script triggers only; does not advertise an unconsumed arrival."""
    verify_rom_bytes(rom)
    return _decode_trainer_room_arrival(rom, map_id, None).interaction_coordinates


def _decode_trainer_room_arrival(
    rom: bytes, map_id: int, events: bytes | None,
) -> ScriptedTrainerArrival:
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
        require(bank * 0x4000 <= at and at + count <= min(len(rom), (bank + 1) * 0x4000))
        return rom[at : at + count]

    header = bank_offset(bank, word(MAP_HEADER_POINTERS + map_id * 2))
    read(header, SCRIPT_POINTER_OFFSET + 2)
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
    read(table, 2)
    default = bank_offset(bank, word(table))
    if read(default, 1) == b"\xfa":
        return _decode_rle_trainer_arrival(rom, map_id, events, bank, default, table, entry)
    code = read(default, 36)
    require(code[0] == 0x21 and code[3] == 0xCD and code[6] == 0xD2)
    require(code[9:27] == bytes.fromhex("af e0 b3 e0 b4 ea d3 cc ea 38 cd fa 3d cd fe 03 38 09"))
    require(code[27] == 0x21 and code[30] == code[32] == 0xCB and code[34] == 0x28)
    bit = (code[31] - 0x46) // 8
    require(0 <= bit < 8 and code[31] == 0x46 + 8 * bit and code[33] == 0xC6 + 8 * bit)
    event_address = word(default + 28)
    event_index = event_address - EVENT_FLAGS_START
    require(isinstance(events, bytes) and 0 <= event_index < len(events))
    assert events is not None
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


def _decode_rle_trainer_arrival(
    rom: bytes, map_id: int, events: bytes | None, bank: int, default: int,
    table: int, entry: bytes,
) -> ScriptedTrainerArrival:
    """Decode the distinct event-gated corridor script, not a room-name route.

    Engine CALL semantics are qualified by the public exact-revision gate. The
    local grammar proves which coordinate branch invokes which movement data.
    """
    from .gen1_joypad_rle import decode_direction_runs

    def require(ok: bool) -> None:
        if not ok:
            raise CartridgeReadError("unsupported or consumed RLE trainer arrival")

    def read(at: int, size: int) -> bytes:
        require(bank * 0x4000 <= at and at + size <= min(len(rom), (bank + 1) * 0x4000))
        return rom[at : at + size]

    def word(at: int) -> int:
        return int.from_bytes(read(at, 2), "little")

    def event_clear(address: int, bit: int) -> int:
        index = address - EVENT_FLAGS_START
        require(0 <= index < 320 and 0 <= bit < 8)
        if events is not None:
            require(type(events) is bytes and index < len(events))
            require(not bool(events[index] & (1 << bit)))
        return index * 8 + bit

    code = read(default, 57)
    require(code[0] == 0xFA and code[3] == 0xCB and code[5:7] == b"\xc0\x21")
    beat_bit = (code[4] - 0x47) // 8
    require(code[4] == 0x47 + beat_bit * 8)
    event_clear(word(default + 1), beat_bit)
    require(code[9] == 0xCD and code[12] == 0xD2)
    require(code[15:30] == bytes.fromhex("af e0 b4 fa 3d cd fe 03 30 07 3e 01 e0 8c c3"))
    require(code[32:35] == bytes.fromhex("fe 05 28"))
    require(code[36] == 0x21 and code[39] == code[41] == 0xCB and code[43] == 0xC0)
    lock_bit = (code[40] - 0x46) // 8
    require(code[40] == 0x46 + lock_bit * 8 and code[42] == 0xC6 + lock_bit * 8)
    lock_event = event_clear(word(default + 37), lock_bit)
    require(code[44:52] == bytes.fromhex("21 26 d1 cb ee 3e ad cd"))
    require(code[54] == 0xC3 and code[55:57] == entry[1:3])
    coords = read(bank_offset(bank, word(default + 7)), 11)
    require(coords[-1] == 0xFF and 0xFF not in coords[:-1])
    entrance = ((coords[8], coords[9]),)
    require(len({tuple(coords[i:i + 2]) for i in range(0, 10, 2)}) == 5)
    walk_at = default + 36 + int.from_bytes(code[35:36], "little", signed=True)
    walk = read(walk_at, 30)
    require(walk[:9] == bytes.fromhex("3e ff ea 6b cd 21 d3 cc 11"))
    require(walk[11] == 0xCD and walk[14:19] == bytes.fromhex("3d ea 38 cd cd"))
    require(walk[21:24] == bytes.fromhex("3e 03 ea") and walk[24:26] == entry[13:15])
    require(walk[26:30] == bytes.fromhex("ea 39 da c9"))
    # Script slot 3 must return control only after the simulated queue drains.
    moving = read(bank_offset(bank, word(table + 6)), 19)
    require(moving[:6] == bytes.fromhex("fa 38 cd a7 c0 cd"))
    require(moving[8:13] == bytes.fromhex("af ea 6b cd ea"))
    require(moving[13:15] == entry[13:15] and moving[15:] == bytes.fromhex("ea 39 da c9"))
    data_at = bank_offset(bank, word(walk_at + 9))
    payload = bytearray()
    for index in range(128):
        direction = read(data_at + index * 2, 1)
        payload.extend(direction)
        if direction == b"\xff":
            break
        payload.extend(read(data_at + index * 2 + 1, 1))
    else:
        raise CartridgeReadError("unterminated RLE trainer arrival")
    # DecodeRLEList fills increasing addresses; JoypadOverworld consumes the
    # simulated queue from its highest index downward. Return execution order.
    # The pinned queue begins at CCD3 and its index occupies CD38: reserve a
    # byte before that index rather than allowing decoded data to overwrite it.
    runs = tuple(reversed(decode_direction_runs(bytes(payload), max_steps=100)))
    result = ScriptedTrainerArrival(
        map_id, entrance, (0, 0), sum(count for _, count in runs), lock_event, runs,
        ((coords[0], coords[1]), (coords[2], coords[3])),
    )
    y, x = entrance[0]
    for (dy, dx), count in runs:
        y, x = y + dy * count, x + dx * count
        require(0 <= y <= 255 and 0 <= x <= 255)
    # End at one of the two door-lock triggers, not an interaction/battle trigger.
    require((y, x) in {tuple(coords[4:6]), tuple(coords[6:8])})
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
