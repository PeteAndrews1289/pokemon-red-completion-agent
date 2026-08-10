"""Read where a player can stand, and record a walk computed from it.

Every chapter module in this repository walks by hand: press UP eleven times,
then RIGHT four. Those sequences are the reason a title costs what it costs, and
they transfer to nothing. The grid they could be computed from is in the
cartridge.

Usage::

    POKEMON_RED_ROM=<path> POKEMON_BLUE_ROM=<path> \\
        python scripts/extract_terrain.py --out docs/evidence/<name>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.gen1_maps import read_map_graph  # noqa: E402
from pokemon_red_completion.gen1_terrain import (  # noqa: E402
    Terrain,
    steps_between,
    tilesets,
    walkable_world,
)
from pokemon_red_completion.observation import MapId  # noqa: E402
from pokemon_red_completion.rom import (  # noqa: E402
    resolve_title_rom_path,
    supported_rom_for,
    verify_rom,
)

TITLES = ("red", "blue")


def picture(terrain: Terrain) -> list[str]:
    """The grid as characters: ``.`` stands, ``#`` blocks, ``"`` is tall grass."""

    return [
        "".join(
            '"' if grass else ("." if walkable else "#")
            for walkable, grass in zip(walk_row, grass_row, strict=True)
        )
        for walk_row, grass_row in zip(terrain.walkable, terrain.grass, strict=True)
    ]


def summarise(rom: bytes) -> dict[str, object]:
    world = walkable_world(rom)
    graph = read_map_graph(rom)
    sets = tilesets(rom)

    standing = total = 0
    for map_id, node in graph.items():
        terrain = world[map_id]
        for passage in node.passages:
            if passage.at is None:
                continue
            y, x = passage.at
            if 0 <= y < terrain.height and 0 <= x < terrain.width:
                total += 1
                standing += terrain.walkable[y][x]

    pallet = world[MapId.PALLET_TOWN.value]
    doors = sorted(p.at for p in graph[MapId.PALLET_TOWN.value].passages if p.at is not None)
    walk = steps_between(pallet, doors[0], doors[-1])

    return {
        "maps": len(world),
        "standable_squares": sum(
            sum(row.count(True) for row in t.walkable) for t in world.values()
        ),
        "grass_squares": sum(sum(row.count(True) for row in t.grass) for t in world.values()),
        "tilesets": len(sets),
        "tilesets_with_grass": sorted(index for index, t in sets.items() if t.has_grass),
        "warps_on_passable_ground": round(standing / total, 4),
        "pallet_town": {
            "size": [pallet.height, pallet.width],
            "picture": picture(pallet),
            "doors": [list(door) for door in doors],
            "computed_walk": [list(step) for step in walk],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    summaries: dict[str, dict[str, object]] = {}
    for title in TITLES:
        path = resolve_title_rom_path(title)
        verify_rom(path, supported_rom_for(title))
        summaries[title] = summarise(path.read_bytes())
        found = summaries[title]
        print(
            f"{title}: {found['maps']} maps, {found['standable_squares']} standable squares, "
            f"{found['grass_squares']} grass, "
            f"{found['warps_on_passable_ground']:.1%} of warps on passable ground"
        )

    agree = summaries["red"] == summaries["blue"]
    print(f"\ncartridges describe the same ground: {agree}")
    pallet = summaries["red"]["pallet_town"]
    print(f"\nPallet Town, {pallet['size'][0]} by {pallet['size'][1]} steps:")
    for row in pallet["picture"]:
        print("  " + row)
    print(f"\ncomputed walk {pallet['doors'][0]} -> {pallet['doors'][-1]}: "
          f"{len(pallet['computed_walk'])} steps")

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "schema": "pokemon-terrain-v1",
                    "recorded_on": args.recorded_on,
                    "scope": (
                        "per-map walkability from tileset collision data. Says which "
                        "squares are standable ground; does not model Surf, Cut, "
                        "Strength, ledges, one-way jumps, doors that open on a story "
                        "flag, or people standing in the way."
                    ),
                    "cartridges_agree": agree,
                    "by_title": summaries,
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
