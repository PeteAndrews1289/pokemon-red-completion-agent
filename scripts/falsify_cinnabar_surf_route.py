"""Try to disprove a cartridge-computed Surf round trip in live Red.

An authenticated private post-Blaine capture supplies only the starting game
state.  The cartridge-derived graph then exits Cinnabar Center, chooses the
nearest water target requiring at least two true water-travel steps, boards via
the bounded Gen I field-move compiler, and returns to the exact shore origin.

The capture and ROM are private inputs and never appear in the public receipt.

Usage::

    python scripts/falsify_cinnabar_surf_route.py \
        --rom <red.gb> --state <post-blaine.state> --out <receipt.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.captured_progress import load_captured_progress  # noqa: E402
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    committed_source_bundle_sha256,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.gen1_field_moves import (  # noqa: E402
    Gen1FieldMovePort,
    surf_permission,
)
from pokemon_red_completion.gen1_maps import (  # noqa: E402
    macro_graph_from_nodes,
    map_graph,
)
from pokemon_red_completion.gen1_route_runtime import (  # noqa: E402
    Gen1TraversalObserver,
    Gen1WildFleeHandler,
)
from pokemon_red_completion.gen1_terrain import Terrain, walkable_world  # noqa: E402
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    LAND_MODE,
    SURF_CAPABILITY,
    WATER_MODE,
    map_object_events,
    surf_capabilities,
    surf_local_graph,
    traversal_rules,
)
from pokemon_red_completion.global_router import MacroGraph  # noqa: E402
from pokemon_red_completion.local_router import (  # noqa: E402
    LocalGraph,
    LocalRouterError,
    find_local_path,
)
from pokemon_red_completion.observation import MapId, PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
)
from pokemon_red_completion.rom import verify_rom  # noqa: E402
from pokemon_red_completion.route_executor import (  # noqa: E402
    ReplanRequest,
    RouteExecutionLimits,
    RouteExecutionReport,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route  # noqa: E402

REQUIRED_CAPTURE_OBJECTIVE = "defeat_blaine"
MINIMUM_WATER_TRAVEL_STEPS = 2


class CinnabarSurfProbeError(RuntimeError):
    """Raised when the live cartridge-derived Surf contract is falsified."""


def _artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


def _adjacent_artifacts(rom_path: Path) -> tuple[tuple[bool, str | None], ...]:
    return tuple(
        _artifact_identity(Path(f"{rom_path}{suffix}")) for suffix in (".ram", ".rtc", ".state")
    )


def _water_goal(
    graph: LocalGraph,
    terrain: Terrain,
    start: tuple[int, int],
) -> tuple[int, int]:
    """Choose the cheapest water target that exercises real water travel."""

    candidates: list[tuple[int, tuple[int, int]]] = []
    for y in range(terrain.height):
        for x in range(terrain.width):
            if not terrain.can_surf(y, x):
                continue
            try:
                path = find_local_path(
                    graph,
                    start,
                    (y, x),
                    capabilities=frozenset({SURF_CAPABILITY}),
                    start_mode=LAND_MODE,
                    goal_mode=WATER_MODE,
                )
            except LocalRouterError:
                continue
            if sum(edge.kind == "water_travel" for edge in path.edges) < (
                MINIMUM_WATER_TRAVEL_STEPS
            ):
                continue
            if sum(edge.kind == "water_entry" for edge in path.edges) != 1:
                continue
            candidates.append((sum(edge.cost for edge in path.edges), (y, x)))
    if not candidates:
        raise CinnabarSurfProbeError("no bounded Cinnabar Surf target was reachable")
    return min(candidates)[1]


def _public_plan(plan: RoutePlan) -> dict[str, object]:
    return {
        "map_ids": list(plan.macro_path.maps),
        "start_yx": list(plan.start_at),
        "start_mode": plan.start_mode,
        "terminal_yx": list(plan.terminal_at),
        "terminal_mode": plan.terminal_mode,
        "steps": [
            {
                "source_map_id": step.source_map,
                "source_yx": list(step.source_at),
                "source_mode": step.source_mode,
                "action_kind": step.action_kind.value,
                "action": step.action,
                "expected_map_id": step.expected_map,
                "expected_yx": list(step.expected_at),
                "expected_mode": step.expected_mode,
                "transition_kind": step.kind,
            }
            for step in plan.steps
        ],
    }


def _public_execution(report: RouteExecutionReport) -> dict[str, object]:
    return {
        "passed": report.passed,
        "action_requests": report.movement_requests,
        "wait_actions": report.wait_actions,
        "acknowledged_steps": len(report.executed_steps),
        "interruption_count": len(report.interruptions),
        "replan_count": len(report.replans),
        "terminal_map_id": report.terminal.map_id,
        "terminal_yx": list(report.terminal.at),
        "terminal_mode": report.terminal.mode,
        "terminal_ready": report.terminal.ready,
    }


def _replanner(
    macro: MacroGraph,
    local_graphs: dict[int, LocalGraph],
    *,
    capabilities: frozenset[str],
    last_outside: int | None = None,
    goal_mode: str | None = None,
):
    def replan(request: ReplanRequest) -> RoutePlan:
        return plan_route(
            macro,
            local_graphs,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            blocked=request.blocked,
            capabilities=capabilities,
            last_outside=last_outside,
            start_mode=request.current.mode,
            goal_at=request.goal_at,
            goal_mode=goal_mode,
        )

    return replan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--envelope",
        type=Path,
        default=None,
        help="defaults to <state>.json",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    fingerprint = verify_rom(args.rom)
    envelope_path = args.envelope or Path(f"{args.state}.json")
    capture = load_captured_progress(envelope_path, state_path=args.state)
    if REQUIRED_CAPTURE_OBJECTIVE not in capture.verified_objective_ids:
        raise CinnabarSurfProbeError(f"capture has not verified {REQUIRED_CAPTURE_OBJECTIVE!r}")

    source = detect_source_identity(PROJECT_ROOT, include_untracked=False)
    require_clean_source(source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise CinnabarSurfProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=source.git_commit,
    )
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise CinnabarSurfProbeError("the executable source differs from its commit")

    rom = args.rom.read_bytes()
    maps = map_graph(rom)
    macro = macro_graph_from_nodes(maps)
    terrain = walkable_world(rom)
    rules = traversal_rules(rom, maps)
    local_graphs = {
        map_id: surf_local_graph(
            local_terrain,
            rules,
            blocked={event.at for event in map_object_events(rom, {map_id})},
        )
        for map_id, local_terrain in terrain.items()
    }
    island = MapId.CINNABAR_ISLAND.value
    center = MapId.CINNABAR_POKECENTER.value
    before_artifacts = _adjacent_artifacts(args.rom)

    limits = RouteExecutionLimits(
        max_step_attempts=8,
        max_readiness_waits=16,
        max_interruptions=2,
        max_replans=2,
        replan_after_unchanged=2,
        retry_wait_frames=24,
        readiness_wait_frames=24,
        transition_settle_frames=180,
    )
    with PyBoyAdapter(args.rom) as emulator:
        emulator.load_state(args.state)
        reader = PokemonRedStateReader(emulator)
        initial = reader.read()
        if (
            initial.map_id != center
            or (initial.player_y, initial.player_x) != (3, 3)
            or initial.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise CinnabarSurfProbeError("capture missed the stable Cinnabar Center boundary")
        permission = surf_permission(emulator, initial)
        capabilities = surf_capabilities(initial, surf_allowed=permission.allowed)
        if SURF_CAPABILITY not in capabilities:
            raise CinnabarSurfProbeError(f"capture lacks live Surf capability: {permission.reason}")

        controller = FrameSafeExecutor(emulator)
        counted = CountingExecutor(controller)
        field_actions = Gen1FieldMovePort(counted, reader, emulator)
        observer = Gen1TraversalObserver(reader)
        wild_handler = Gen1WildFleeHandler(
            field_actions,
            reader,
            maximum_flees=limits.max_interruptions,
            stabilization_frames=24,
            route_name="cartridge-computed Cinnabar Surf round trip",
        )

        exit_plan = plan_route(
            macro,
            local_graphs,
            center,
            (3, 3),
            island,
            start_mode=LAND_MODE,
            last_outside=island,
        )
        exit_report = execute_route(
            exit_plan,
            field_actions,
            observer,
            interruption_handler=wild_handler,
            replanner=_replanner(
                macro,
                local_graphs,
                capabilities=frozenset(),
                last_outside=island,
                goal_mode=LAND_MODE,
            ),
            limits=limits,
        )
        shore_origin = exit_report.terminal.at
        water_goal = _water_goal(
            local_graphs[island],
            terrain[island],
            shore_origin,
        )

        outbound_plan = plan_route(
            macro,
            local_graphs,
            island,
            shore_origin,
            island,
            capabilities=capabilities,
            start_mode=LAND_MODE,
            goal_at=water_goal,
            goal_mode=WATER_MODE,
        )
        outbound_report = execute_route(
            outbound_plan,
            field_actions,
            observer,
            interruption_handler=wild_handler,
            replanner=None,
            limits=limits,
        )
        return_plan = plan_route(
            macro,
            local_graphs,
            island,
            water_goal,
            island,
            capabilities=capabilities,
            start_mode=WATER_MODE,
            goal_at=shore_origin,
            goal_mode=LAND_MODE,
        )
        return_report = execute_route(
            return_plan,
            field_actions,
            observer,
            interruption_handler=wild_handler,
            replanner=None,
            limits=limits,
        )
        final = reader.read()
        final_mode = reader.read_overworld_movement_mode().traversal_mode
        frames_executed = emulator.frame_count
        controller_released = not emulator.pressed_buttons
        final_ready = reader.read_input_readiness().ready

    if before_artifacts != _adjacent_artifacts(args.rom):
        raise CinnabarSurfProbeError("the no-save probe changed a ROM-adjacent artifact")
    if not field_actions.receipts:
        raise CinnabarSurfProbeError("the route produced no acknowledged Surf field move")
    if final.map_id != island or (final.player_y, final.player_x) != shore_origin:
        raise CinnabarSurfProbeError("the round trip did not return to its exact shore origin")
    if final_mode != LAND_MODE:
        raise CinnabarSurfProbeError("the round trip did not acknowledge disembarkation")

    payload = {
        "schema": "cinnabar-cartridge-surf-route-probe-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "rom": fingerprint.public_dict(),
        "source": source.public_dict(),
        "executable_source_bundle_sha256": source_bundle,
        "private_capture_precondition": {
            "authenticated": True,
            "checkpoint_id": capture.checkpoint_id,
            "checkpoint_label": capture.checkpoint_label,
            "required_verified_objective": REQUIRED_CAPTURE_OBJECTIVE,
        },
        "authority_under_test": (
            "Cartridge map, warp, terrain, water-tile and pair-collision data chose the "
            "route and water target. Live RAM supplied field permission, badge, living "
            "move holder, locomotion mode, readiness and every coordinate acknowledgement."
        ),
        "selection_rule": {
            "minimum_water_travel_steps": MINIMUM_WATER_TRAVEL_STEPS,
            "tie_break": "lowest total edge cost, then y/x coordinate",
            "selected_water_yx": list(water_goal),
            "shore_origin_yx": list(shore_origin),
        },
        "plans": {
            "center_exit": _public_plan(exit_plan),
            "outbound": _public_plan(outbound_plan),
            "return": _public_plan(return_plan),
        },
        "execution": {
            "center_exit": _public_execution(exit_report),
            "outbound": _public_execution(outbound_report),
            "return": _public_execution(return_report),
        },
        "surf_receipts": [
            {
                "source_map_id": receipt.source_map,
                "source_yx": list(receipt.source_at),
                "target_yx": list(receipt.target_at),
                "direction": receipt.direction,
                "party_index": receipt.party_index,
                "submenu_row": receipt.submenu_row,
                "confirmation_count": receipt.confirmation_count,
                "permission_reason": receipt.permission_reason,
            }
            for receipt in field_actions.receipts
        ],
        "wild_flees": [receipt.public_dict() for receipt in wild_handler.evidence],
        "final": {
            "map_id": int(final.map_id),
            "yx": [final.player_y, final.player_x],
            "mode": final_mode,
            "ready": final_ready,
        },
        "actions_executed": counted.actions_executed,
        "frames_executed": frames_executed,
        "controller_released": controller_released,
        "rom_adjacent_artifacts_unchanged": True,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out}: boarded at {field_actions.receipts[0].source_at}, "
        f"reached {water_goal}, returned to {shore_origin} in land mode"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
