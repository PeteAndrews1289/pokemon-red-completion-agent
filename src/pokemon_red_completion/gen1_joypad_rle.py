"""Bounded direction-only RLE data; does not authenticate its engine caller."""

from .gen1_cartridge import CartridgeReadError

_DIRECTIONS = {0x40: (-1, 0), 0x80: (1, 0), 0x20: (0, -1), 0x10: (0, 1)}


def decode_direction_runs(
    data: bytes, *, max_steps: int = 127,
) -> tuple[tuple[tuple[int, int], int], ...]:
    if type(max_steps) is not int or not 1 <= max_steps <= 127:
        raise CartridgeReadError("direction RLE step limit must be an integer in 1..127")
    if type(data) is not bytes:
        raise CartridgeReadError("direction RLE requires immutable bytes")
    if len(data) < 3 or data[-1] != 0xFF or len(data) % 2 != 1:
        raise CartridgeReadError("direction RLE needs nonempty pairs and a final terminator")
    segments = []
    total = 0
    for index in range(0, len(data) - 1, 2):
        direction, count = data[index : index + 2]
        if direction not in _DIRECTIONS or count == 0:
            raise CartridgeReadError("direction RLE contains an invalid direction or count")
        total += count
        if total > max_steps:
            raise CartridgeReadError("direction RLE exceeds its declared step bound")
        segments.append((_DIRECTIONS[direction], count))
    return tuple(segments)
