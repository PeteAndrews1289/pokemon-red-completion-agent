"""Try to disprove semantic closed/open routing at Route 7's Saffron gate.

The authenticated post-Erika capture supplies a clean chapter boundary. The
qualified teacher obtains the required drink and reaches the Route 7 guard
house, where static cartridge terrain still contains a five-step corridor but
the durable access predicate is false. The semantic planner must reject that
same corridor without sending an input. After the existing guard handoff sets
the observed flag, generated local plans cross the threshold in both
directions, then exact cartridge passages leave the guard house and enter
Saffron City.

The capture and ROM are private inputs and never appear in the public receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.captured_progress import load_captured_progress  # noqa: E402
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    committed_source_bundle_sha256,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.gen1_maps import (  # noqa: E402
    macro_graph_from_nodes,
    map_graph,
)
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver  # noqa: E402
from pokemon_red_completion.gen1_story_routing import (  # noqa: E402
    SAFFRON_GUARDS_OPEN,
    apply_gen1_story_requirements,
    gen1_story_capabilities,
    observe_gen1_story_predicates,
)
from pokemon_red_completion.gen1_terrain import walkable_world  # noqa: E402
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    LAND_MODE,
    local_graph,
    traversal_rules,
)
from pokemon_red_completion.global_router import (  # noqa: E402
    MacroGraph,
    MacroPath,
)
from pokemon_red_completion.observation import (  # noqa: E402
    ItemId,
    MapId,
    PokemonRedStateReader,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
)
from pokemon_red_completion.rom import verify_rom  # noqa: E402
from pokemon_red_completion.route_executor import (  # noqa: E402
    RouteExecutionLimits,
    RouteExecutionReport,
    execute_route,
)
from pokemon_red_completion.route_plan import (  # noqa: E402
    RoutePlan,
    RoutePlanningError,
    compose_route,
    plan_route,
)
from pokemon_red_completion.saffron import (  # noqa: E402
    SaffronProgress,
    run_saffron_chapter,
)
from pokemon_red_completion.semantic_traversal import PredicateState  # noqa: E402

REQUIRED_CAPTURE_OBJECTIVE = "defeat_erika"
GATE_MAP = int(MapId.ROUTE_7_GATE)
ROUTE_MAP = int(MapId.ROUTE_7)
CITY_MAP = int(MapId.SAFFRON_CITY)
WEST_YX = (4, 0)
TRIGGER_YX = (4, 3)
EAST_YX = (4, 5)


class SaffronStoryGateProbeError(RuntimeError):
    """Raised when live play falsifies story-predicate routing."""


class _ReachedOpenBoundary(RuntimeError):
    pass


def _artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


def _adjacent_artifacts(rom_path: Path) -> tuple[tuple[bool, str | None], ...]:
    return tuple(
        _artifact_identity(Path(f"{rom_path}{suffix}"))
        for suffix in (".ram", ".rtc", ".state")
    )


def _public_plan(plan: RoutePlan) -> dict[str, object]:
    return {
        "maps": list(plan.macro_path.maps),
        "start_yx": list(plan.start_at),
        "terminal_yx": list(plan.terminal_at),
        "actions": list(plan.actions),
        "steps": [
            {
                "source_map": step.source_map,
                "source_yx": list(step.source_at),
                "action": step.action,
                "expected_map": step.expected_map,
                "expected_yx": list(step.expected_at),
                "requirements": sorted(
                    requirement
                    for requirement in (
                        SAFFRON_GUARDS_OPEN
                        if step.source_at in {(3, 2), (3, 3), (4, 2), (4, 3)}
                        else ""
                    ,)
                    if requirement
                ),
            }
            for step in plan.steps
        ],
    }


def _public_execution(report: RouteExecutionReport) -> dict[str, object]:
    return {
        "passed": report.passed,
        "movement_requests": report.movement_requests,
        "acknowledged_steps": len(report.executed_steps),
        "interruptions": [item.kind for item in report.interruptions],
        "replans": len(report.replans),
        "terminal_map": report.terminal.map_id,
        "terminal_yx": list(report.terminal.at),
        "terminal_ready": report.terminal.ready,
    }


def _requires_predicate(plan: RoutePlan) -> bool:
    return any(
        step.source_map == GATE_MAP
        and (step.source_at, step.expected_at)
        in {
            ((3, 2), (3, 3)),
            ((3, 3), (3, 2)),
            ((4, 2), (4, 3)),
            ((4, 3), (4, 2)),
        }
        for step in plan.steps
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    fingerprint = verify_rom(args.rom)
    capture = load_captured_progress(
        args.envelope or Path(f"{args.state}.json"),
        state_path=args.state,
    )
    if REQUIRED_CAPTURE_OBJECTIVE not in capture.verified_objective_ids:
        raise SaffronStoryGateProbeError(
            f"capture has not verified {REQUIRED_CAPTURE_OBJECTIVE!r}"
        )

    source = detect_source_identity(PROJECT_ROOT, include_untracked=False)
    require_clean_source(source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise SaffronStoryGateProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=source.git_commit,
    )
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise SaffronStoryGateProbeError("the executable source differs from its commit")

    rom = args.rom.read_bytes()
    maps = map_graph(rom)
    macro = macro_graph_from_nodes(maps)
    world = walkable_world(rom)
    relevant_maps = {GATE_MAP, ROUTE_MAP, CITY_MAP}
    rules = traversal_rules(rom, relevant_maps)
    unfiltered_graphs = {
        map_id: local_graph(world[map_id], rules) for map_id in relevant_maps
    }
    story_graphs = apply_gen1_story_requirements(unfiltered_graphs)
    same_map = MacroGraph({GATE_MAP: ()})
    before_artifacts = _adjacent_artifacts(args.rom)
    closed_evidence: dict[str, object] = {}
    open_raw = None

    with PyBoyAdapter(args.rom) as emulator:
        emulator.load_state(args.state)
        reader = PokemonRedStateReader(emulator)
        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        counted = CountingExecutor(controller)

        def observe_boundary(progress: SaffronProgress) -> None:
            nonlocal open_raw
            if progress.checkpoint_id == "gate_reached":
                raw = reader.read()
                snapshot = Gen1TraversalObserver(reader).observe()
                if (
                    raw.map_id != GATE_MAP
                    or (raw.player_y, raw.player_x) != WEST_YX
                    or SAFFRON_GUARDS_OPEN in snapshot.capabilities
                ):
                    raise SaffronStoryGateProbeError("closed guard boundary changed")
                predicate = next(
                    item
                    for item in observe_gen1_story_predicates(raw)
                    if item.name == SAFFRON_GUARDS_OPEN
                )
                if predicate.state is not PredicateState.UNSATISFIED:
                    raise SaffronStoryGateProbeError("guard predicate was not observed closed")
                unfiltered = plan_route(
                    same_map,
                    {GATE_MAP: unfiltered_graphs[GATE_MAP]},
                    GATE_MAP,
                    WEST_YX,
                    GATE_MAP,
                    start_mode=LAND_MODE,
                    goal_at=EAST_YX,
                    goal_mode=LAND_MODE,
                )
                try:
                    plan_route(
                        same_map,
                        {GATE_MAP: story_graphs[GATE_MAP]},
                        GATE_MAP,
                        WEST_YX,
                        GATE_MAP,
                        start_mode=LAND_MODE,
                        goal_at=EAST_YX,
                        goal_mode=LAND_MODE,
                        capabilities=snapshot.capabilities,
                    )
                except RoutePlanningError:
                    closed_filtered = True
                else:
                    closed_filtered = False
                unknown_capabilities = gen1_story_capabilities(
                    replace(raw, status_flags_1=None)
                )
                try:
                    plan_route(
                        same_map,
                        {GATE_MAP: story_graphs[GATE_MAP]},
                        GATE_MAP,
                        WEST_YX,
                        GATE_MAP,
                        start_mode=LAND_MODE,
                        goal_at=EAST_YX,
                        goal_mode=LAND_MODE,
                        capabilities=unknown_capabilities,
                    )
                except RoutePlanningError:
                    unknown_filtered = True
                else:
                    unknown_filtered = False
                if not closed_filtered or not unknown_filtered or len(unfiltered.steps) != 5:
                    raise SaffronStoryGateProbeError("closed/unknown filtering did not hold")
                closed_evidence.update(
                    {
                        "predicate_state": predicate.state.value,
                        "status_flags_1": raw.status_flags_1,
                        "capabilities": sorted(snapshot.capabilities),
                        "static_unfiltered_plan": _public_plan(unfiltered),
                        "semantic_plan_available": False,
                        "unknown_predicate_plan_available": False,
                        "generated_inputs_sent": 0,
                        "fresh_water_present": ItemId.FRESH_WATER
                        in (raw.bag_item_ids or ()),
                    }
                )
            elif progress.checkpoint_id == "guards_bribed":
                open_raw = reader.read()
                raise _ReachedOpenBoundary

        try:
            run_saffron_chapter(
                emulator,
                reader,
                counted,
                progress=observe_boundary,
            )
        except _ReachedOpenBoundary:
            pass
        else:
            raise SaffronStoryGateProbeError("teacher did not expose the open guard boundary")

        if open_raw is None:  # pragma: no cover - guarded by exception above
            raise SaffronStoryGateProbeError("open guard observation is unavailable")
        open_predicate = next(
            item
            for item in observe_gen1_story_predicates(open_raw)
            if item.name == SAFFRON_GUARDS_OPEN
        )
        observer = Gen1TraversalObserver(reader)
        open_snapshot = observer.observe()
        if (
            open_predicate.state is not PredicateState.SATISFIED
            or open_snapshot.at != TRIGGER_YX
            or SAFFRON_GUARDS_OPEN not in open_snapshot.capabilities
            or ItemId.FRESH_WATER in (open_raw.bag_item_ids or ())
        ):
            raise SaffronStoryGateProbeError("open guard predicate did not settle")

        limits = RouteExecutionLimits(max_interruptions=1, max_replans=1)
        back_plan = plan_route(
            same_map,
            {GATE_MAP: story_graphs[GATE_MAP]},
            GATE_MAP,
            TRIGGER_YX,
            GATE_MAP,
            start_mode=LAND_MODE,
            goal_at=WEST_YX,
            goal_mode=LAND_MODE,
            capabilities=open_snapshot.capabilities,
        )
        back_report = execute_route(back_plan, counted, observer, limits=limits)
        forward_plan = plan_route(
            same_map,
            {GATE_MAP: story_graphs[GATE_MAP]},
            GATE_MAP,
            WEST_YX,
            GATE_MAP,
            start_mode=LAND_MODE,
            goal_at=EAST_YX,
            goal_mode=LAND_MODE,
            capabilities=back_report.terminal.capabilities,
        )
        forward_report = execute_route(forward_plan, counted, observer, limits=limits)
        if not _requires_predicate(back_plan) or not _requires_predicate(forward_plan):
            raise SaffronStoryGateProbeError("generated crossing bypassed the semantic threshold")

        east_return = next(
            edge
            for edge in macro.neighbors(GATE_MAP)
            if edge.kind == "return" and edge.at == EAST_YX and edge.exit_action == "right"
        )
        exit_plan = compose_route(
            macro,
            MacroPath((GATE_MAP, ROUTE_MAP), (east_return,)),
            story_graphs,
            EAST_YX,
            start_mode=LAND_MODE,
        )
        exit_report = execute_route(exit_plan, counted, observer, limits=limits)
        east_connection = next(
            edge
            for edge in macro.neighbors(ROUTE_MAP)
            if edge.target_map == CITY_MAP and edge.kind == "connection" and edge.heading == "east"
        )
        city_plan = compose_route(
            macro,
            MacroPath((ROUTE_MAP, CITY_MAP), (east_connection,)),
            story_graphs,
            exit_report.terminal.at,
            start_mode=LAND_MODE,
        )
        city_report = execute_route(city_plan, counted, observer, limits=limits)
        final = reader.read()
        reports = (back_report, forward_report, exit_report, city_report)
        if (
            not all(report.passed for report in reports)
            or any(report.interruptions or report.replans for report in reports)
            or any(
                report.movement_requests != len(report.executed_steps)
                for report in reports
            )
            or final.map_id != CITY_MAP
            or not reader.read_input_readiness().ready
        ):
            raise SaffronStoryGateProbeError("open generated passage did not settle")
        controller_released = not emulator.pressed_buttons
        frames_executed = emulator.frame_count

    if before_artifacts != _adjacent_artifacts(args.rom):
        raise SaffronStoryGateProbeError("the probe changed a ROM-adjacent artifact")

    payload = {
        "schema": "saffron-story-gate-route-probe-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "rom": fingerprint.public_dict(),
        "source": {
            "git_commit": source.git_commit,
            "source_bundle_sha256": source_bundle,
        },
        "capture": {
            "checkpoint_id": capture.checkpoint_id,
            "required_verified_objective": REQUIRED_CAPTURE_OBJECTIVE,
        },
        "passage": {
            "map_id": GATE_MAP,
            "west_yx": list(WEST_YX),
            "east_yx": list(EAST_YX),
            "predicate": SAFFRON_GUARDS_OPEN,
            "static_topology_changed_between_observations": False,
        },
        "closed_observation": closed_evidence,
        "open_observation": {
            "predicate_state": open_predicate.state.value,
            "status_flags_1": open_raw.status_flags_1,
            "capabilities": sorted(open_snapshot.capabilities),
            "fresh_water_present": False,
        },
        "generated_execution": {
            "open_backtrack": _public_execution(back_report),
            "open_forward_crossing": _public_execution(forward_report),
            "gate_exit": _public_execution(exit_report),
            "saffron_connection": _public_execution(city_report),
            "total_movement_requests": sum(
                report.movement_requests for report in reports
            ),
            "total_acknowledged_steps": sum(len(report.executed_steps) for report in reports),
            "semantic_threshold_crossed_westbound": _requires_predicate(back_plan),
            "semantic_threshold_crossed_eastbound": _requires_predicate(forward_plan),
            "terminal_map_id": final.map_id,
            "terminal_yx": [final.player_y, final.player_x],
        },
        "actions_executed": counted.actions_executed,
        "terminal_frame": frames_executed,
        "controller_released": controller_released,
        "rom_adjacent_artifacts_unchanged": True,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "Saffron story gate passed: closed and unknown filtered, then "
        f"{payload['generated_execution']['total_acknowledged_steps']} generated steps settled"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
