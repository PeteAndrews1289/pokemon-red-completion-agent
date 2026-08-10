"""Read the first state-aware traversal layer from both Generation I ROMs.

This records what can be used safely now—directed ledges and elevation-pair
collisions—and inventories the state transitions that still need planners:
Cut block replacements, Surf's exceptional tile pairs, and Strength boulders.

Usage::

    POKEMON_RED_ROM=<path> POKEMON_BLUE_ROM=<path> \
        python scripts/extract_traversal_rules.py --out docs/evidence/<name>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pokemon_red_completion.gen1_maps import map_graph  # noqa: E402
from pokemon_red_completion.gen1_terrain import Terrain, walkable_world  # noqa: E402
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    Direction,
    TraversalRules,
    local_graph,
    traversal_rules,
)
from pokemon_red_completion.local_router import LocalGraph  # noqa: E402
from pokemon_red_completion.observation import MapId  # noqa: E402
from pokemon_red_completion.rom import (  # noqa: E402
    resolve_title_rom_path,
    supported_rom_for,
    verify_rom,
)

TITLES = ("red", "blue")


def map_name(map_id: int) -> str | None:
    try:
        return MapId(map_id).name
    except ValueError:
        return None


def pair_restricted_transitions(terrain: Terrain, rules: TraversalRules) -> int:
    """Count directed, standable neighbor pairs the elevation table closes."""

    count = 0
    for y in range(terrain.height):
        for x in range(terrain.width):
            if not terrain.can_stand(y, x):
                continue
            for direction in Direction:
                dy, dx = direction.delta
                other = (y + dy, x + dx)
                if not terrain.can_stand(*other):
                    continue
                if any(
                    rule.blocks(
                        terrain.tileset,
                        terrain.tiles[y][x],
                        terrain.tiles[other[0]][other[1]],
                    )
                    for rule in rules.land_pair_restrictions
                ):
                    count += 1
    return count


def summarise(
    world: dict[int, Terrain],
    rules: TraversalRules,
    graphs: dict[int, LocalGraph],
) -> dict[str, object]:
    actions = Counter(
        edge.action
        for graph in graphs.values()
        for edges in graph.edges.values()
        for edge in edges
    )
    kinds = Counter(
        edge.kind
        for graph in graphs.values()
        for edges in graph.edges.values()
        for edge in edges
    )
    ledges_by_map = {
        map_id: sum(
            edge.kind == "ledge"
            for edges in graph.edges.values()
            for edge in edges
        )
        for map_id, graph in graphs.items()
    }
    pair_blocks_by_map = {
        map_id: pair_restricted_transitions(terrain, rules)
        for map_id, terrain in world.items()
    }
    boulders = Counter(event.map_id for event in rules.boulders)
    return {
        "static_local_graph": {
            "coordinate_nodes": sum(len(graph.edges) for graph in graphs.values()),
            "directed_edges": sum(
                len(edges) for graph in graphs.values() for edges in graph.edges.values()
            ),
            "controller_inputs": dict(sorted(actions.items())),
            "transition_kinds": dict(sorted(kinds.items())),
            "pair_restricted_directed_transitions": sum(pair_blocks_by_map.values()),
            "maps_with_pair_restrictions": [
                {
                    "map_id": map_id,
                    "map_name": map_name(map_id),
                    "directed_transitions": count,
                }
                for map_id, count in sorted(pair_blocks_by_map.items())
                if count
            ],
            "maps_with_ledge_transitions": [
                {
                    "map_id": map_id,
                    "map_name": map_name(map_id),
                    "directed_transitions": count,
                }
                for map_id, count in sorted(ledges_by_map.items())
                if count
            ],
        },
        "boulders": {
            "total": len(rules.boulders),
            "strength_enabled": sum(event.is_strength_boulder for event in rules.boulders),
            "fixed_or_already_dropped": sum(
                not event.is_strength_boulder for event in rules.boulders
            ),
            "by_map": [
                {
                    "map_id": map_id,
                    "map_name": map_name(map_id),
                    "count": count,
                    "initial_coordinates_yx": [
                        list(event.at)
                        for event in rules.boulders
                        if event.map_id == map_id
                    ],
                }
                for map_id, count in sorted(boulders.items())
            ],
        },
    }


def public_rules(rules: TraversalRules) -> dict[str, object]:
    return {
        "ledges": [
            {
                "direction": rule.direction.value,
                "standing_tile": rule.standing_tile,
                "ledge_tile": rule.ledge_tile,
            }
            for rule in rules.ledges
        ],
        "land_pair_restrictions": [
            {
                "tileset": rule.tileset,
                "tiles": [rule.first_tile, rule.second_tile],
            }
            for rule in rules.land_pair_restrictions
        ],
        "water_pair_restrictions": [
            {
                "tileset": rule.tileset,
                "tiles": [rule.first_tile, rule.second_tile],
            }
            for rule in rules.water_pair_restrictions
        ],
        "cut_block_swaps": [
            {"before": swap.before, "after": swap.after}
            for swap in rules.cut_block_swaps
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    rules_by_title: dict[str, TraversalRules] = {}
    local_graphs: dict[str, dict[int, LocalGraph]] = {}
    summaries: dict[str, dict[str, object]] = {}
    for title in TITLES:
        path = resolve_title_rom_path(title)
        verify_rom(path, supported_rom_for(title))
        rom = path.read_bytes()
        maps = map_graph(rom)
        world = walkable_world(rom)
        rules = traversal_rules(rom, maps)
        graphs = {
            map_id: local_graph(terrain, rules)
            for map_id, terrain in world.items()
        }
        rules_by_title[title] = rules
        local_graphs[title] = graphs
        summaries[title] = summarise(world, rules, graphs)
        static = summaries[title]["static_local_graph"]
        boulders = summaries[title]["boulders"]
        print(
            f"{title}: {static['directed_edges']} static land edges, "
            f"{static['transition_kinds']['ledge']} ledge hops, "
            f"{static['pair_restricted_directed_transitions']} elevation-pair blocks, "
            f"{boulders['total']} boulders"
        )

    static_rules_agree = (
        rules_by_title["red"].ledges == rules_by_title["blue"].ledges
        and rules_by_title["red"].land_pair_restrictions
        == rules_by_title["blue"].land_pair_restrictions
        and rules_by_title["red"].water_pair_restrictions
        == rules_by_title["blue"].water_pair_restrictions
        and rules_by_title["red"].cut_block_swaps
        == rules_by_title["blue"].cut_block_swaps
    )
    boulders_agree = rules_by_title["red"].boulders == rules_by_title["blue"].boulders
    graphs_agree = local_graphs["red"] == local_graphs["blue"]
    print(
        "agreement: "
        f"static rules {static_rules_agree}, boulders {boulders_agree}, "
        f"local graphs {graphs_agree}"
    )

    payload = {
        "schema": "pokemon-gen1-traversal-rules-v1",
        "recorded_on": args.recorded_on,
        "scope": (
            "Complete cartridge tables for directed ledges, land/water tile-pair "
            "restrictions and Cut block swaps; initial boulder object events across "
            "all reachable maps; and the complete static land graph."
        ),
        "interpretation": (
            "Only walk, directed ledge hops and elevation-pair restrictions are "
            "executable static edges. Cut mutates blocks, Strength moves objects, "
            "Surf changes movement mode, and story scripts change access; those "
            "inventories are evidence for future state-space adapters, not permission "
            "to traverse them now."
        ),
        "pret_pokered_commit": "1e96034092686d006e863cace09e87273051a3d8",
        "static_rule_tables_agree": static_rules_agree,
        "initial_boulder_events_agree": boulders_agree,
        "static_local_graphs_agree": graphs_agree,
        "rules": public_rules(rules_by_title["red"]),
        "by_title": summaries,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
