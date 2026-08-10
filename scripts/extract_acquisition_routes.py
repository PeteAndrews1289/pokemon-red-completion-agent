"""Read every way a Generation I cartridge yields a species, and check the count.

Walking in grass is one acquisition route out of several, and treating it as the
whole picture is measurably wrong. Comparing only the wild tables makes four
species look version-exclusive that are not -- Horsea and Seadra in Red, Krabby
and Kingler in Blue -- because both cartridges offer all four on a rod. It also
misses six that *are* exclusive and appear in no wild table at all, because they
are only ever reached by evolving something that does.

So this reads the wild tables, the three rods, the ten in-game trades and the
evolution graph together, closes the catchable set under all of them, and
differences the two cartridges. The eleven-species exclusive lists fall out.
They used to be typed.

Four more species come only from the trades: Farfetch'd, Lickitung, Mr. Mime and
Jynx appear in no wild table, on no rod, and at the end of no evolution.

Usage::

    POKEMON_RED_ROM=<path> POKEMON_BLUE_ROM=<path> \\
        python scripts/extract_acquisition_routes.py --out docs/evidence/<name>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.gen1_cartridge import (  # noqa: E402
    catchable_species,
    evolution_graph,
    fishing_tables,
    in_game_trades,
    internal_to_dex,
    reachable_species,
    version_exclusives,
    wild_tables,
)
from pokemon_red_completion.rom import (  # noqa: E402
    resolve_title_rom_path,
    supported_rom_for,
    verify_rom,
)

TITLES = ("red", "blue")


def wild_species(rom: bytes) -> set[int]:
    dex = internal_to_dex(rom)
    return {dex[s] for slots in wild_tables(rom).values() for _, s in slots if s in dex}


def without_trading(rom: bytes) -> set[int]:
    """What a cartridge reaches by catching and evolving alone.

    Needed to say which species *only* an in-game trade supplies, and computed
    plainly rather than by subtracting sets that nearly mean the right thing.
    An earlier one-liner here reported Beedrill as trade-only, which is wrong:
    it is a trade reward, but it is also what a caught Weedle grows into.
    """

    graph = evolution_graph(rom)
    reached = set(catchable_species(rom))
    frontier = list(reached)
    while frontier:
        species = frontier.pop()
        for step in graph.get(species, ()):
            if step.needs_a_trade_partner or step.to_species in reached:
                continue
            reached.add(step.to_species)
            frontier.append(step.to_species)
    return reached


def describe(rom: bytes) -> dict[str, object]:
    tables = fishing_tables(rom)
    wild = wild_species(rom)
    rods = tables.species()
    trades = in_game_trades(rom)
    caught = catchable_species(rom)
    reachable = reachable_species(rom)
    return {
        "in_game_trades": [
            {
                "give": trade.give_species,
                "get": trade.get_species,
                "nickname": trade.nickname,
            }
            for trade in trades
        ],
        "species_only_an_in_game_trade_supplies": sorted(
            {trade.get_species for trade in trades} - without_trading(rom)
        ),
        "wild_table_species": sorted(wild),
        "rod_species": sorted(rods),
        "rod_only_species": sorted(rods - wild),
        "super_rod_maps": sorted(tables.by_map),
        "anywhere": [
            {"rod": slot.rod.value, "level": slot.level, "species": slot.species}
            for slot in tables.anywhere
        ],
        "catchable": sorted(caught),
        "reachable_through_parsed_routes_alone": sorted(reachable),
        "reachable_through_parsed_routes_with_a_trade_partner": sorted(
            reachable_species(rom, with_trade_partner=True)
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="evidence file to write")
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    roms: dict[str, bytes] = {}
    for title in TITLES:
        path = resolve_title_rom_path(title)
        verify_rom(path, supported_rom_for(title))
        roms[title] = path.read_bytes()

    described = {title: describe(rom) for title, rom in roms.items()}
    red_only, blue_only = version_exclusives(roms["red"], roms["blue"])

    for title, found in described.items():
        print(
            f"{title}: {len(found['wild_table_species'])} in wild tables, "
            f"{len(found['rod_species'])} on a rod "
            f"({len(found['rod_only_species'])} of them nowhere else), "
            f"{len(found['catchable'])} catchable, "
            f"{len(found['reachable_through_parsed_routes_alone'])} "
            "reachable through parsed routes alone"
        )

    wild_difference = set(described["red"]["wild_table_species"]) ^ set(  # type: ignore[arg-type]
        described["blue"]["wild_table_species"]
    )
    false_positives = sorted(wild_difference - red_only - blue_only)
    invisible = sorted(
        (red_only | blue_only)
        - set(described["red"]["wild_table_species"])  # type: ignore[arg-type]
        - set(described["blue"]["wild_table_species"])  # type: ignore[arg-type]
    )

    print(f"\nexclusive to Red : {sorted(red_only)}")
    print(f"exclusive to Blue: {sorted(blue_only)}")
    print(f"\nwild tables differ but not exclusive (a rod covers them): {false_positives}")
    print(f"exclusive but in no wild table (reached by evolution)    : {invisible}")

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "schema": "pokemon-acquisition-routes-v1",
                    "recorded_on": args.recorded_on,
                    "scope": (
                        "wild grass and water tables, the three rods, the evolution "
                        "graph and the ten in-game trades. Gifts, fossils and the Game "
                        "Corner are further routes and are not read here."
                    ),
                    "by_title": described,
                    "version_exclusives": {
                        "red": sorted(red_only),
                        "blue": sorted(blue_only),
                    },
                    "wild_difference_that_is_not_exclusivity": false_positives,
                    "exclusive_but_absent_from_every_wild_table": invisible,
                    "fishing_tables_identical_across_cartridges": (
                        fishing_tables(roms["red"]) == fishing_tables(roms["blue"])
                    ),
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
