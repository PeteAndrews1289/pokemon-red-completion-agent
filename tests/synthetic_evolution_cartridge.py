"""Synthetic bytes for the existing production evolution-table decoder only.

No emulator/game image is loaded. Tables encode the committed public measurement
and fixed internal index map, including the real decoder's full-graph anchors.
"""
import json
from functools import lru_cache
from pathlib import Path

from pokemon_red_completion.gen1_cartridge import (
    EVOLUTION_DATA_BANK, EVOLUTION_POINTER_ARRAY, INTERNAL_INDEX_LIMIT,
    INTERNAL_TO_DEX_TABLE, bank_offset,
)
from pokemon_red_completion.red_collection import red_internal_species_id


@lru_cache(maxsize=1)
def synthetic_evolution_cartridge():
    import pokemon_red_completion.gen1_cartridge as decoder
    root = Path(decoder.__file__).resolve().parents[2]
    measured = json.loads((root / "docs/evidence/evolution-graph-2026-08-10.json").read_text())
    payload = bytearray(INTERNAL_TO_DEX_TABLE + INTERNAL_INDEX_LIMIT)
    start = bank_offset(EVOLUTION_DATA_BANK, 0x4000)
    cursor = start
    for dex in range(1, 152):
        internal = red_internal_species_id(dex)
        payload[INTERNAL_TO_DEX_TABLE + internal - 1] = dex
        at = EVOLUTION_POINTER_ARRAY + 2 * (internal - 1)
        payload[at:at + 2] = (0x4000 + cursor - start).to_bytes(2, "little")
        for step in measured["graph"].get(str(dex), ()):
            target = red_internal_species_id(step["to"])
            if step["method"] == "level":
                row = (1, step["requirement"], target)
            elif step["method"] == "stone":
                row = (2, step["requirement"], 0, target)
            elif step["method"] == "trade":
                row = (3, 0, target)
            else:
                raise AssertionError("unsupported synthetic evolution method")
            payload[cursor:cursor + len(row)] = bytes(row)
            cursor += len(row)
        payload[cursor] = 0
        cursor += 1
    assert cursor < EVOLUTION_POINTER_ARRAY  # Separate data and pointer regions.
    return bytes(payload)
