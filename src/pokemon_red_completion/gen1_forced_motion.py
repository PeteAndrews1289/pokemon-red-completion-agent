"""Decode native spinner scripts into closed-loop route edges, not walk strings.

The supported Red/Blue scripts load a coordinate/RLE table, then the engine
executes the expanded joypad buffer backwards. Arrow graphics are insufficient:
the cartridge's script supplies the actual path. See pret/pokered's
scripts/{ViridianGym,RocketHideoutB2F,RocketHideoutB3F}.asm at revision
1e96034092686d006e863cace09e87273051a3d8. No trigger coordinates or routes are
copied here. Unknown script encodings in these maps fail closed.
"""

from collections.abc import Collection, Mapping
from dataclasses import replace

from .gen1_cartridge import CartridgeReadError, bank_offset
from .gen1_maps import MAP_HEADER_BANKS, MAP_HEADER_POINTERS, SCRIPT_POINTER_OFFSET
from .local_router import Coordinate, LocalEdge, LocalGraph

SPINNER_MAP_IDS = frozenset({0x2D, 0xC8, 0xC9})
# ld a,[wYCoord]; ld b,a; ld a,[wXCoord]; ld c,a; ld hl,table
_TABLE_LOAD = bytes.fromhex("fa61d347fa62d34f21")
# call DecodeArrowMovementRLE; cp $ff; jp z,CheckFightingMapTrainers
_DECODE_CALL = bytes.fromhex("cd4234feffca1932")
_DIRECTIONS = {0x10: (0, 1), 0x20: (0, -1), 0x40: (-1, 0), 0x80: (1, 0)}
_MAX_TRIGGERS = 64
_MAX_STEPS = 256


def spinner_sequences(rom: bytes, map_id: int) -> dict[Coordinate, tuple[Coordinate, ...]]:
    """Return each trigger's native ordered path (excluding its starting tile)."""
    if map_id not in SPINNER_MAP_IDS:
        return {}

    def read(at: int, count: int) -> bytes:
        if at < 0 or at + count > len(rom):
            raise CartridgeReadError("spinner data is truncated")
        return rom[at:at + count]

    bank = read(MAP_HEADER_BANKS + map_id, 1)[0]

    def pointer(at: int) -> int:
        address = int.from_bytes(read(at, 2), "little")
        if not 0x4000 <= address < 0x8000:
            raise CartridgeReadError("spinner pointer is outside its script bank")
        return bank_offset(bank, address)

    header = pointer(MAP_HEADER_POINTERS + 2 * map_id)
    script = pointer(header + SCRIPT_POINTER_OFFSET)
    window = read(script, 96)
    matches = [i for i in range(len(window)) if window.startswith(_TABLE_LOAD, i)]
    if len(matches) != 1:
        raise CartridgeReadError("spinner script needs one authenticated table reference")
    reference = script + matches[0] + len(_TABLE_LOAD)
    if read(reference + 2, len(_DECODE_CALL)) != _DECODE_CALL:
        raise CartridgeReadError("unsupported spinner decoder call")
    cursor = pointer(reference)
    bank_end = (bank + 1) * 0x4000

    def bank_read(at: int, count: int) -> bytes:
        if at < bank * 0x4000 or at + count > bank_end:
            raise CartridgeReadError("spinner data crosses its script bank")
        return read(at, count)

    found: dict[Coordinate, tuple[Coordinate, ...]] = {}
    for _ in range(_MAX_TRIGGERS + 1):
        if bank_read(cursor, 1)[0] == 0xFF:
            if not found:
                raise CartridgeReadError("spinner table is empty")
            return found
        if len(found) >= _MAX_TRIGGERS:
            break
        row = bank_read(cursor, 4)
        at = (row[0], row[1])
        if at in found:
            raise CartridgeReadError("spinner table repeats a trigger")
        movement = pointer(cursor + 2)
        directions: list[tuple[int, int]] = []
        for _ in range(_MAX_STEPS + 1):
            value = bank_read(movement, 1)[0]
            if value == 0xFF:
                break
            pair = bank_read(movement, 2)
            if value not in _DIRECTIONS or pair[1] == 0:
                raise CartridgeReadError("spinner RLE has invalid direction or count")
            if len(directions) + pair[1] > _MAX_STEPS:
                raise CartridgeReadError("spinner RLE exceeds movement bound")
            directions.extend([_DIRECTIONS[value]] * pair[1])
            movement += 2
        else:
            raise CartridgeReadError("spinner RLE is unterminated")
        if not directions:
            raise CartridgeReadError("spinner RLE is empty")
        position = at
        path = []
        for dy, dx in reversed(directions):
            position = (position[0] + dy, position[1] + dx)
            path.append(position)
        found[at] = tuple(path)
        cursor += 4
    raise CartridgeReadError("spinner table exceeds trigger bound")


def apply_forced_motion(
    graph: LocalGraph,
    sequences: Mapping[Coordinate, tuple[Coordinate, ...]],
    *,
    forbidden: Collection[Coordinate] = (),
) -> LocalGraph:
    """Collapse supported walks into one input plus an observed forced endpoint.

    Intermediate coordinates remain part of the edge for dynamic hazard checks.
    Stops come from the script, not tile appearance. An impossible/cyclic chain,
    static blocker, warp or mode transition removes the edge instead of guessing
    how a partly blocked script would finish. Never offer a trigger as a goal.
    """
    if not sequences:
        return graph
    unavailable = frozenset(forbidden)
    projected: dict[Coordinate, tuple[LocalEdge, ...]] = {}
    for source, outgoing in graph.edges.items():
        if source in sequences:
            continue
        result = []
        for edge in outgoing:
            if edge.target not in sequences:
                result.append(edge)
                continue
            if edge.kind != "walk":
                continue
            path = [edge.target]
            position = edge.target
            triggers: set[Coordinate] = set()
            requirements = edge.requirements
            valid = True
            while position in sequences:
                if position in triggers or not sequences[position]:
                    valid = False
                    break
                triggers.add(position)
                for target in sequences[position]:
                    leg = next((candidate for candidate in graph.neighbors(position)
                                if candidate.target == target and candidate.kind == "walk"
                                and candidate.required_mode == edge.required_mode
                                and candidate.result_mode is None), None)
                    if leg is None or len(path) >= _MAX_STEPS:
                        valid = False
                        break
                    requirements |= leg.requirements
                    path.append(target)
                    position = target
                if not valid:
                    break
            if not valid or source in path or unavailable.intersection(path):
                continue
            result.append(replace(edge, target=position, kind="forced_motion",
                                  via=tuple(path[:-1]), cost=len(path),
                                  requirements=requirements))
        projected[source] = tuple(result)
    return LocalGraph(projected)
