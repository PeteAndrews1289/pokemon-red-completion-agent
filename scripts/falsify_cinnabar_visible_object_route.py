"""Try to disprove live visible-object avoidance in cartridge-composed routing.

An authenticated private post-Blaine capture supplies only the starting game
state.  The probe exits Cinnabar Center, deliberately asks the unblocked
cartridge graph for a route whose shortest candidate crosses a stationary map
object, and requires the live sprite overlay to trigger a replacement before
that occupied square receives an input.  It then returns to the exact shore
origin.  ROM object-event positions are used to select the test, never as
planner blockers.

The capture and ROM are private inputs and never appear in the public receipt.

Usage::

    python scripts/falsify_cinnabar_visible_object_route.py \
        --rom <red.gb> --state <post-blaine.state> --out <receipt.json>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
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
from pokemon_red_completion.gen1_route_runtime import (  # noqa: E402
    Gen1TraversalObserver,
    Gen1WildFleeHandler,
)
from pokemon_red_completion.gen1_terrain import walkable_world  # noqa: E402
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    LAND_MODE,
    MapObjectEvent,
    local_graph,
    map_object_events,
    traversal_rules,
)
from pokemon_red_completion.global_router import MacroGraph  # noqa: E402
from pokemon_red_completion.local_router import (  # noqa: E402
    LocalGraph,
    LocalPath,
    LocalRouterError,
    find_local_path,
    without_coordinates,
)
from pokemon_red_completion.observation import (  # noqa: E402
    MapId,
    PokemonRedStateReader,
    VisibleMapObject,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
)
from pokemon_red_completion.rom import verify_rom  # noqa: E402
from pokemon_red_completion.route_executor import (  # noqa: E402
    ReplanRequest,
    RouteExecutionLimits,
    RouteExecutionReport,
    TraversalSnapshot,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route  # noqa: E402

REQUIRED_CAPTURE_OBJECTIVE = "defeat_blaine"
STATIONARY_MOVEMENT = 0xFF


class CinnabarVisibleObjectProbeError(RuntimeError):
    """Raised when live play falsifies the visible-object contract."""


@dataclass(frozen=True, slots=True)
class ProbeSelection:
    blocker: MapObjectEvent
    goal: tuple[int, int]
    unblocked_path: LocalPath
    avoiding_path: LocalPath


@dataclass(frozen=True, slots=True)
class VisibleDecisionObservation:
    player_at: tuple[int, int]
    blocker: VisibleMapObject
    occupied: frozenset[tuple[int, int]]


@dataclass(slots=True)
class RecordingTraversalObserver:
    """Retain only observations in which the selected blocker is visible."""

    delegate: Gen1TraversalObserver
    reader: PokemonRedStateReader
    blocker_at: tuple[int, int]
    visible: list[VisibleDecisionObservation] = field(default_factory=list, init=False)

    def observe(self) -> TraversalSnapshot:
        snapshot = self.delegate.observe()
        if snapshot.interruption is None and self.blocker_at in snapshot.occupied:
            objects = self.reader.read_visible_map_objects()
            blocker = next((item for item in objects if item.at == self.blocker_at), None)
            if blocker is None:
                raise CinnabarVisibleObjectProbeError(
                    "coordinate projection disagreed with the typed sprite observation"
                )
            self.visible.append(
                VisibleDecisionObservation(snapshot.at, blocker, snapshot.occupied)
            )
        return snapshot


def _artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


def _adjacent_artifacts(rom_path: Path) -> tuple[tuple[bool, str | None], ...]:
    return tuple(
        _artifact_identity(Path(f"{rom_path}{suffix}"))
        for suffix in (".ram", ".rtc", ".state")
    )


def select_probe_goal(
    graph: LocalGraph,
    start: tuple[int, int],
    events: tuple[MapObjectEvent, ...],
) -> ProbeSelection:
    """Choose the shortest route whose candidate crosses an avoidable fixed object."""

    candidates: list[
        tuple[int, int, tuple[int, int], tuple[int, int], ProbeSelection]
    ] = []
    stationary = tuple(
        event for event in events if event.movement == STATIONARY_MOVEMENT and not event.is_boulder
    )
    for blocker in stationary:
        avoiding_graph = without_coordinates(graph, {blocker.at})
        for goal in sorted(graph.edges):
            if goal in {start, blocker.at}:
                continue
            try:
                candidate = find_local_path(graph, start, goal, start_mode=LAND_MODE)
                avoiding = find_local_path(
                    avoiding_graph,
                    start,
                    goal,
                    start_mode=LAND_MODE,
                )
            except LocalRouterError:
                continue
            if blocker.at not in candidate.coordinates[1:]:
                continue
            selection = ProbeSelection(blocker, goal, candidate, avoiding)
            candidates.append(
                (
                    len(candidate.edges),
                    len(avoiding.edges),
                    blocker.at,
                    goal,
                    selection,
                )
            )
    if not candidates:
        raise CinnabarVisibleObjectProbeError(
            "no stationary Cinnabar object has both a crossing route and an alternate"
        )
    return min(candidates, key=lambda item: item[:-1])[-1]


def _public_plan(plan: RoutePlan) -> dict[str, object]:
    return {
        "map_ids": list(plan.macro_path.maps),
        "start_yx": list(plan.start_at),
        "terminal_yx": list(plan.terminal_at),
        "steps": [
            {
                "source_map_id": step.source_map,
                "source_yx": list(step.source_at),
                "action": step.action,
                "expected_map_id": step.expected_map,
                "expected_yx": list(step.expected_at),
                "kind": step.kind,
            }
            for step in plan.steps
        ],
    }


def _public_execution(report: RouteExecutionReport) -> dict[str, object]:
    return {
        "passed": report.passed,
        "movement_requests": report.movement_requests,
        "wait_actions": report.wait_actions,
        "acknowledged_steps": len(report.executed_steps),
        "interruption_count": len(report.interruptions),
        "replans": [
            {
                "ordinal": receipt.ordinal,
                "map_id": receipt.map_id,
                "at_yx": list(receipt.at),
                "candidate_blocker_yx": list(receipt.newly_blocked),
                "replacement_steps": receipt.replacement_steps,
                "reason": receipt.reason,
            }
            for receipt in report.replans
        ],
        "terminal_map_id": report.terminal.map_id,
        "terminal_yx": list(report.terminal.at),
        "terminal_ready": report.terminal.ready,
    }


def _replanner(macro: MacroGraph, local_graphs: dict[int, LocalGraph]):
    def replan(request: ReplanRequest) -> RoutePlan:
        return plan_route(
            macro,
            local_graphs,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            blocked=request.blocked,
            last_outside=request.current.last_outside_map,
            start_mode=request.current.mode,
            goal_at=request.goal_at,
            goal_mode=LAND_MODE,
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
        raise CinnabarVisibleObjectProbeError(
            f"capture has not verified {REQUIRED_CAPTURE_OBJECTIVE!r}"
        )

    source = detect_source_identity(PROJECT_ROOT, include_untracked=False)
    require_clean_source(source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise CinnabarVisibleObjectProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=source.git_commit,
    )
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise CinnabarVisibleObjectProbeError("the executable source differs from its commit")

    rom = args.rom.read_bytes()
    maps = map_graph(rom)
    macro = macro_graph_from_nodes(maps)
    world = walkable_world(rom)
    rules = traversal_rules(rom, maps)
    # Deliberately leave all initial object-event coordinates traversable. The
    # live overlay, not ROM starting positions, owns temporary occupancy.
    local_graphs = {
        map_id: local_graph(terrain, rules) for map_id, terrain in world.items()
    }
    island = MapId.CINNABAR_ISLAND.value
    center = MapId.CINNABAR_POKECENTER.value
    before_artifacts = _adjacent_artifacts(args.rom)
    limits = RouteExecutionLimits(
        max_step_attempts=8,
        max_readiness_waits=16,
        max_interruptions=1,
        max_replans=4,
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
            raise CinnabarVisibleObjectProbeError(
                "capture missed the stable Cinnabar Center boundary"
            )

        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        counted = CountingExecutor(controller)
        observer = Gen1TraversalObserver(reader)
        wild_handler = Gen1WildFleeHandler(
            counted,
            reader,
            maximum_flees=limits.max_interruptions,
            stabilization_frames=24,
            route_name="cartridge-computed Cinnabar visible-object probe",
        )
        replan = _replanner(macro, local_graphs)

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
            counted,
            observer,
            interruption_handler=wild_handler,
            replanner=replan,
            limits=limits,
        )
        shore_origin = exit_report.terminal.at
        selection = select_probe_goal(
            local_graphs[island],
            shore_origin,
            map_object_events(rom, {island}),
        )
        outbound_plan = plan_route(
            macro,
            local_graphs,
            island,
            shore_origin,
            island,
            start_mode=LAND_MODE,
            goal_at=selection.goal,
            goal_mode=LAND_MODE,
        )
        recording_observer = RecordingTraversalObserver(
            observer,
            reader,
            selection.blocker.at,
        )
        outbound_report = execute_route(
            outbound_plan,
            counted,
            recording_observer,
            interruption_handler=wild_handler,
            replanner=replan,
            limits=limits,
        )
        return_plan = plan_route(
            macro,
            local_graphs,
            island,
            selection.goal,
            island,
            start_mode=LAND_MODE,
            goal_at=shore_origin,
            goal_mode=LAND_MODE,
        )
        return_report = execute_route(
            return_plan,
            counted,
            recording_observer,
            interruption_handler=wild_handler,
            replanner=replan,
            limits=limits,
        )
        final = reader.read()
        frames_executed = emulator.frame_count
        controller_released = not emulator.pressed_buttons
        final_ready = reader.read_input_readiness().ready

    if before_artifacts != _adjacent_artifacts(args.rom):
        raise CinnabarVisibleObjectProbeError(
            "the no-save probe changed a ROM-adjacent artifact"
        )
    visible_receipts = [
        receipt
        for receipt in outbound_report.replans
        if receipt.reason == "visible_object"
        and receipt.newly_blocked == selection.blocker.at
    ]
    if len(visible_receipts) != 1:
        raise CinnabarVisibleObjectProbeError(
            "outbound route did not produce exactly one selected visible-object replan"
        )
    receipt = visible_receipts[0]
    matching_observations = [
        observation
        for observation in recording_observer.visible
        if observation.player_at == receipt.at
    ]
    if not matching_observations:
        raise CinnabarVisibleObjectProbeError(
            "visible-object receipt lacks a matching typed live observation"
        )
    if any(item.reason != "visible_object" for item in outbound_report.replans):
        raise CinnabarVisibleObjectProbeError(
            "outbound route needed an inferred blocker in addition to direct occupancy"
        )
    if final.map_id != island or (final.player_y, final.player_x) != shore_origin:
        raise CinnabarVisibleObjectProbeError(
            "the probe did not return to its exact shore origin"
        )

    decision = matching_observations[0]
    payload = {
        "schema": "cinnabar-visible-object-route-probe-v1",
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
            "ROM object events selected an adversarial stationary object and route goal but "
            "did not block planner coordinates. Revision-decoded live sprite state supplied "
            "temporary occupancy; exact live map/coordinate state acknowledged every step."
        ),
        "selection": {
            "start_yx": list(shore_origin),
            "goal_yx": list(selection.goal),
            "stationary_object_initial_yx": list(selection.blocker.at),
            "unblocked_candidate_steps": len(selection.unblocked_path.edges),
            "avoiding_candidate_steps": len(selection.avoiding_path.edges),
            "unblocked_candidate_crosses_object": True,
            "rom_object_positions_used_as_planner_blockers": False,
        },
        "visible_decision": {
            "player_yx": list(decision.player_at),
            "occupied_yx": [list(item) for item in sorted(decision.occupied)],
            "sprite_index": decision.blocker.sprite_index,
            "picture_id": decision.blocker.picture_id,
            "movement_status": decision.blocker.movement_status,
            "image_index": decision.blocker.image_index,
            "object_yx": list(decision.blocker.at),
            "input_sent_toward_occupied_square": False,
        },
        "plans": {
            "center_exit": _public_plan(exit_plan),
            "outbound_initial": _public_plan(outbound_plan),
            "return": _public_plan(return_plan),
        },
        "execution": {
            "center_exit": _public_execution(exit_report),
            "outbound": _public_execution(outbound_report),
            "return": _public_execution(return_report),
        },
        "wild_flees": [receipt.public_dict() for receipt in wild_handler.evidence],
        "final": {
            "map_id": int(final.map_id),
            "yx": [final.player_y, final.player_x],
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
        f"wrote {args.out}: observed object {selection.blocker.at} from {receipt.at}, "
        f"replanned before input, reached {selection.goal}, returned to {shore_origin}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
