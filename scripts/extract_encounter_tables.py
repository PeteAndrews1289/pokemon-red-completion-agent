"""Read wild encounter tables straight out of a cartridge.

Sampling encounters can only ever show what is *present*. To show that Ekans is
absent from Blue you would have to exhaustively walk every area and then argue
about how much walking is enough. The tables themselves are static data, so
reading them settles presence and absence together.

Nothing here is transcribed. The table locations were found by searching each
ROM for structures matching bands this repository had already *measured* from
real encounters — Diglett's Cave holding only Diglett and Dugtrio pinned the
wild data, and the Mansion's 28-39 band confirmed the map index was right.
The internal-index-to-Pokédex map was found the same way, anchored on the four
species the party adapter already names.

Scope, which matters for what may be concluded: this reads the per-map grass and
water tables. Fishing, Game Corner prizes, gifts, fossils, in-game trades and
evolution are separate acquisition routes stored elsewhere, so a species absent
here is not thereby unobtainable.

Usage::

    POKEMON_RED_ROM=<path> POKEMON_BLUE_ROM=<path> \\
        python scripts/extract_encounter_tables.py --out docs/evidence/<name>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.rom import (  # noqa: E402
    resolve_title_rom_path,
    supported_rom_for,
    verify_rom,
)

#: Where the located structures live. Both were found by search, and both are
#: re-verified on every run against measured bands rather than trusted.
WILD_DATA_BANK = 3
WILD_POINTER_ARRAY = 0x0CEEB
INTERNAL_TO_DEX_TABLE = 0x41024
MAP_ID_LIMIT = 248
SLOTS_PER_TABLE = 10

#: Anchors re-checked on every extraction. If a cartridge revision moves these
#: structures, the run fails rather than emitting plausible nonsense.
DIGLETTS_CAVE_MAP_ID = 197
MANSION_MAP_ID = 165
MEASURED_MANSION_BAND = (28, 39)
DEX_ANCHORS = {0x1C: 9, 0x3B: 50, 0x76: 51, 0x84: 143}


class ExtractionError(RuntimeError):
    """Raised when a cartridge does not match the located structures."""


def internal_to_dex(rom: bytes) -> dict[int, int]:
    for internal, expected in DEX_ANCHORS.items():
        actual = rom[INTERNAL_TO_DEX_TABLE + internal - 1]
        if actual != expected:
            raise ExtractionError(
                f"internal index {internal:#04x} maps to {actual}, not the "
                f"{expected} the party adapter already asserts; the table has moved"
            )
    mapping = {index + 1: rom[INTERNAL_TO_DEX_TABLE + index] for index in range(190)}
    return {internal: dex for internal, dex in mapping.items() if 1 <= dex <= 151}


def map_tables(rom: bytes) -> dict[int, list[tuple[int, int]]]:
    """Every ``(level, internal_species)`` slot each map can field."""

    base = WILD_DATA_BANK * 0x4000
    tables: dict[int, list[tuple[int, int]]] = {}
    for map_id in range(MAP_ID_LIMIT):
        at = WILD_POINTER_ARRAY + 2 * map_id
        address = int.from_bytes(rom[at : at + 2], "little")
        if not 0x4000 <= address <= 0x7FFF:
            continue
        cursor = base + (address - 0x4000)
        slots: list[tuple[int, int]] = []
        for _ in range(2):  # grass, then water
            rate = rom[cursor]
            cursor += 1
            if rate == 0:
                continue
            for slot in range(SLOTS_PER_TABLE):
                slots.append((rom[cursor + 2 * slot], rom[cursor + 2 * slot + 1]))
            cursor += 2 * SLOTS_PER_TABLE
        if slots:
            tables[map_id] = slots
    return tables


def verify_against_measurements(tables: dict[int, list[tuple[int, int]]]) -> None:
    """Re-derive two bands this repository measured from live encounters."""

    cave = tables.get(DIGLETTS_CAVE_MAP_ID)
    if not cave or {species for _, species in cave} != {0x3B, 0x76}:
        raise ExtractionError(
            "Diglett's Cave does not hold exactly Diglett and Dugtrio; the wild "
            "data pointer array has moved"
        )
    mansion = tables.get(MANSION_MAP_ID)
    if not mansion:
        raise ExtractionError("no Mansion table; the map index is wrong")
    levels = [level for level, _ in mansion]
    if (min(levels), max(levels)) != MEASURED_MANSION_BAND:
        raise ExtractionError(
            f"Mansion band {min(levels)}-{max(levels)} contradicts the measured "
            f"{MEASURED_MANSION_BAND[0]}-{MEASURED_MANSION_BAND[1]}"
        )


def species_by_dex(rom: bytes) -> tuple[set[int], dict[int, set[int]]]:
    dex = internal_to_dex(rom)
    tables = map_tables(rom)
    verify_against_measurements(tables)
    per_map = {
        map_id: {dex[species] for _, species in slots if species in dex}
        for map_id, slots in tables.items()
    }
    everything: set[int] = set()
    for found in per_map.values():
        everything |= found
    return everything, per_map


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="evidence file to write")
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    found: dict[str, set[int]] = {}
    for title in ("red", "blue"):
        path = resolve_title_rom_path(title)
        verify_rom(path, supported_rom_for(title))
        found[title], _ = species_by_dex(path.read_bytes())
        print(f"{title}: {len(found[title])} species across its wild tables")

    red_only = sorted(found["red"] - found["blue"])
    blue_only = sorted(found["blue"] - found["red"])
    print(f"\nin Red's wild tables only : {red_only}")
    print(f"in Blue's wild tables only: {blue_only}")

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "schema": "pokemon-wild-table-extraction-v1",
                    "recorded_on": args.recorded_on,
                    "scope": (
                        "per-map grass and water tables only. Fishing, Game Corner, gifts, "
                        "fossils, in-game trades and evolution are separate routes stored "
                        "elsewhere, so absence here is not unobtainability."
                    ),
                    "wild_species_count": {k: len(v) for k, v in found.items()},
                    "red_wild_tables_only": red_only,
                    "blue_wild_tables_only": blue_only,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
