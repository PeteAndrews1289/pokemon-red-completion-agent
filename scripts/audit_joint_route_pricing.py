#!/usr/bin/env python3
"""Audit topology-only versus joint local/macro pricing on Red and Blue.

The cartridge's shortest map sequence from Pallet to Pewter tries to bypass
Viridian Forest through a Route 2 connection whose exact border is not locally
reachable. The joint planner must reject that candidate and compose the real
south-gate → forest → north-gate route instead.

This is a static cartridge audit, not live execution authority. ROM paths and
bytes remain private; the output contains only public fingerprints and derived
route facts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.collection_protocol import (  # noqa: E402
    committed_source_bundle_sha256,
    working_source_bundle_sha256,
)
from pokemon_red_completion.gen1_maps import (  # noqa: E402
    macro_graph_from_nodes,
    map_graph,
)
from pokemon_red_completion.gen1_terrain import walkable_world  # noqa: E402
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    local_graph,
    traversal_rules,
)
from pokemon_red_completion.global_router import find_macro_path  # noqa: E402
from pokemon_red_completion.observation import MapId  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
)
from pokemon_red_completion.rom import verify_rom  # noqa: E402
from pokemon_red_completion.route_plan import (  # noqa: E402
    RoutePlanningError,
    compose_route,
    plan_route,
)

START_MAP = MapId.PALLET_TOWN.value
START_YX = (12, 12)
GOAL_MAP = MapId.PEWTER_CITY.value
EXPECTED_TOPOLOGY_MAPS = (
    MapId.PALLET_TOWN.value,
    MapId.ROUTE_1.value,
    MapId.VIRIDIAN_CITY.value,
    MapId.ROUTE_2.value,
    MapId.PEWTER_CITY.value,
)
EXPECTED_JOINT_MAPS = (
    MapId.PALLET_TOWN.value,
    MapId.ROUTE_1.value,
    MapId.VIRIDIAN_CITY.value,
    MapId.ROUTE_2.value,
    MapId.VIRIDIAN_FOREST_SOUTH_GATE.value,
    MapId.VIRIDIAN_FOREST.value,
    MapId.VIRIDIAN_FOREST_NORTH_GATE.value,
    MapId.ROUTE_2.value,
    MapId.PEWTER_CITY.value,
)


class JointRouteAuditError(RuntimeError):
    """Raised when a cartridge no longer supports the audited distinction."""


def _map_name(map_id: int) -> str:
    try:
        return MapId(map_id).name
    except ValueError:
        return f"MAP_{map_id}"


def _audit_cartridge(rom_path: Path) -> dict[str, object]:
    fingerprint = verify_rom(rom_path)
    rom = rom_path.read_bytes()
    maps = map_graph(rom)
    macro = macro_graph_from_nodes(maps)
    world = walkable_world(rom)
    rules = traversal_rules(rom, maps)
    local_graphs = {
        map_id: local_graph(terrain, rules) for map_id, terrain in world.items()
    }

    topology_path = find_macro_path(macro, START_MAP, GOAL_MAP)
    if topology_path.maps != EXPECTED_TOPOLOGY_MAPS:
        raise JointRouteAuditError(
            f"topology-only Pallet→Pewter path changed to {topology_path.maps}"
        )
    try:
        compose_route(macro, topology_path, local_graphs, START_YX)
    except RoutePlanningError as error:
        topology_failure = str(error)
    else:
        raise JointRouteAuditError("topology-only path unexpectedly became locally composable")

    joint = plan_route(macro, local_graphs, START_MAP, START_YX, GOAL_MAP)
    if joint.macro_path.maps != EXPECTED_JOINT_MAPS:
        raise JointRouteAuditError(f"joint Pallet→Pewter path changed to {joint.macro_path.maps}")
    if joint.cost != 317 or len(joint.steps) != 314:
        raise JointRouteAuditError(
            f"joint route changed cost/steps to {joint.cost}/{len(joint.steps)}"
        )

    return {
        "rom": fingerprint.public_dict(),
        "topology_only": {
            "map_ids": list(topology_path.maps),
            "map_names": [_map_name(map_id) for map_id in topology_path.maps],
            "composable": False,
            "failure": topology_failure,
        },
        "joint": {
            "map_ids": list(joint.macro_path.maps),
            "map_names": [_map_name(map_id) for map_id in joint.macro_path.maps],
            "combined_cost": joint.cost,
            "acknowledgement_contract_steps": len(joint.steps),
            "segments": [
                {
                    "source_map_id": segment.source_map,
                    "target_map_id": segment.target_map,
                    "passage_kind": segment.passage_kind,
                    "local_approach_cost": sum(
                        edge.cost for edge in segment.approach.edges
                    ),
                    "exit_yx": list(segment.transition.exit_at),
                    "arrival_yx": list(segment.transition.arrival_at),
                    "passage_cost": edge.cost,
                }
                for segment, edge in zip(
                    joint.segments,
                    joint.macro_path.edges,
                    strict=True,
                )
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--red-rom", type=Path, required=True)
    parser.add_argument("--blue-rom", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", required=True)
    args = parser.parse_args(argv)

    source = detect_source_identity(PROJECT_ROOT, include_untracked=False)
    require_clean_source(source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise JointRouteAuditError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=source.git_commit,
    )
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise JointRouteAuditError("the executable source differs from its commit")

    cartridges = [_audit_cartridge(args.red_rom), _audit_cartridge(args.blue_rom)]
    projections = [
        {key: value for key, value in cartridge.items() if key != "rom"}
        for cartridge in cartridges
    ]
    if projections[0] != projections[1]:
        raise JointRouteAuditError("Red and Blue produced different joint route facts")

    payload = {
        "schema": "joint-route-pricing-audit-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "source": source.public_dict(),
        "executable_source_bundle_sha256": source_bundle,
        "scope": {
            "start_map_id": START_MAP,
            "start_yx": list(START_YX),
            "goal_map_id": GOAL_MAP,
            "terrain": "cartridge_initial",
            "capabilities": [],
            "dynamic_blockers": "not_projected",
            "live_execution_authority": False,
        },
        "cartridges": cartridges,
        "red_blue_route_facts_identical": True,
        "finding": (
            "Topology alone selects an uncomposable Route 2 border. Joint pricing rejects it "
            "and carries exact coordinates through both Viridian Forest gates."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out}: topology-only rejected; joint route "
        f"{len(EXPECTED_JOINT_MAPS)} maps / 314 acknowledgement steps"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
