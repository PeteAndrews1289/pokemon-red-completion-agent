"""Read and record the complete Generation I evolution graph.

The committed evolution record used to have no reproducing command: tests
could compare declarations with the JSON, but nothing in the repository proved
that the JSON still came from either cartridge. This script is that missing
link. It verifies both private ROM identities, runs the guarded decoder, compares
the complete decoded graphs, and emits the ROM-free public measurement.

Usage::

    POKEMON_RED_ROM=<path> POKEMON_BLUE_ROM=<path> \
        python scripts/extract_evolution_graph.py --out docs/evidence/<name>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.gen1_cartridge import (  # noqa: E402
    Evolution,
    evolution_graph,
    trade_evolutions,
)
from pokemon_red_completion.rom import (  # noqa: E402
    resolve_title_rom_path,
    supported_rom_for,
    verify_rom,
)

TITLES = ("red", "blue")


def public_graph(graph: dict[int, tuple[Evolution, ...]]) -> dict[str, list[dict[str, object]]]:
    return {
        str(species): [
            {
                "to": step.to_species,
                "method": step.method.value,
                "requirement": step.requirement,
            }
            for step in steps
        ]
        for species, steps in sorted(graph.items())
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    graphs: dict[str, dict[int, tuple[Evolution, ...]]] = {}
    for title in TITLES:
        path = resolve_title_rom_path(title)
        verify_rom(path, supported_rom_for(title))
        graphs[title] = evolution_graph(path.read_bytes())

    selected = graphs["red"]
    by_method = Counter(
        step.method.value for steps in selected.values() for step in steps
    )
    payload = {
        "schema": "pokemon-evolution-graph-v1",
        "recorded_on": args.recorded_on,
        "method": (
            "Read from both supported cartridges. The decoder verifies the complete "
            "151-species mapping, the Diglett and Kadabra anchors, 70 evolving species, "
            "and all 72 evolution methods before emitting."
        ),
        "cartridges_agree": graphs["red"] == graphs["blue"],
        "species_with_evolutions": len(selected),
        "totals_by_method": dict(sorted(by_method.items())),
        "trade_evolutions": {
            str(species): precursor
            for species, precursor in sorted(trade_evolutions(selected).items())
        },
        "graph": public_graph(selected),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out}: {len(selected)} evolving species, "
        f"{sum(by_method.values())} evolutions, cartridges agree "
        f"{payload['cartridges_agree']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
