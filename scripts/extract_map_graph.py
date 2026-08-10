"""Read Kanto's map graph out of both cartridges and record what it contains.

Every chapter module in this repository is hand-written walk directions, which
is why "plays each and every game" has so far cost one hand-authored route per
objective. The graph that would let a route be computed instead is in the
cartridge, and this reads it.

The record it writes is what lets the tests check the graph without a ROM
present. Production has a ROM by definition -- it is running the game -- so
nothing loads this file at play time; ``gen1_maps.map_graph`` reads the
cartridge directly.

Usage::

    POKEMON_RED_ROM=<path> POKEMON_BLUE_ROM=<path> \\
        python scripts/extract_map_graph.py --out docs/evidence/<name>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.gen1_cartridge import fishing_tables, wild_tables  # noqa: E402
from pokemon_red_completion.gen1_maps import (  # noqa: E402
    STARTING_MAP,
    PassageKind,
    map_graph,
    routes_between,
)
from pokemon_red_completion.observation import MapId  # noqa: E402
from pokemon_red_completion.rom import (  # noqa: E402
    resolve_title_rom_path,
    supported_rom_for,
    verify_rom,
)

TITLES = ("red", "blue")

#: Journeys reported in full, so the record shows routes rather than only
#: counts. Chosen to exercise a plain overland walk, a crossing that needs
#: Surf, and a descent into an interior.
SAMPLE_JOURNEYS = (
    (MapId.PALLET_TOWN, MapId.PEWTER_CITY),
    (MapId.PALLET_TOWN, MapId.CINNABAR_ISLAND),
    (MapId.PALLET_TOWN, MapId.SAFFRON_CITY),
    (MapId.PALLET_TOWN, MapId.VIRIDIAN_GYM),
)


def summarise(rom: bytes) -> dict[str, object]:
    graph = map_graph(rom)
    counts = {
        kind.value: sum(
            1 for node in graph.values() for passage in node.passages if passage.kind is kind
        )
        for kind in PassageKind
    }
    return {
        "maps": len(graph),
        "passage_counts": counts,
        "maps_with_a_scripted_exit": sorted(
            map_id for map_id, node in graph.items() if node.has_a_scripted_exit
        ),
        "named_maps_reachable": sorted(m.value for m in MapId if m.value in graph),
        "maps_with_wild_tables_reachable": sorted(
            m for m in wild_tables(rom) if m in graph
        ),
        "fishable_maps_reachable": sorted(m for m in fishing_tables(rom).by_map if m in graph),
        "adjacency": {
            str(map_id): sorted(node.neighbours()) for map_id, node in sorted(graph.items())
        },
        "sample_journeys": {
            f"{start.name}->{goal.name}": list(routes_between(graph, start.value, goal.value))
            for start, goal in SAMPLE_JOURNEYS
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="evidence file to write")
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    summaries: dict[str, dict[str, object]] = {}
    for title in TITLES:
        path = resolve_title_rom_path(title)
        verify_rom(path, supported_rom_for(title))
        summaries[title] = summarise(path.read_bytes())
        found = summaries[title]
        print(
            f"{title}: {found['maps']} maps reachable from map {STARTING_MAP}, "
            f"passages {found['passage_counts']}"
        )

    agree = summaries["red"]["adjacency"] == summaries["blue"]["adjacency"]
    print(f"\ncartridges carry the same map graph: {agree}")
    for label, route in summaries["red"]["sample_journeys"].items():  # type: ignore[union-attr]
        print(f"  {label}: {len(route)} maps")

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                {
                    "schema": "pokemon-map-graph-v1",
                    "recorded_on": args.recorded_on,
                    "scope": (
                        "map headers, edge connections and warps. Says which maps are "
                        "joined, not whether the way is open: Surf, Cut, Strength and "
                        "story gates are not in this data."
                    ),
                    "starting_map": STARTING_MAP,
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
