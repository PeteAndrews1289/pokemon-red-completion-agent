"""Try to disprove cartridge-derived trainer-sight avoidance on Victory Road 1F.

The authenticated post-Giovanni capture supplies the origin.  The qualified
teacher reaches Victory Road, the Strength planner solves the first switch,
and the local router is deliberately asked for a shortest exit approach
without trainer sight.  That candidate enters an undefeated trainer's lane.
The live route observer must identify the semantic hazard and request a
replacement before any input is sent toward the lane.

The capture and ROM are private inputs and never appear in the public receipt.
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

from pokemon_red_completion.actions import MacroAction, MacroActionKind  # noqa: E402
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.captured_progress import load_captured_progress  # noqa: E402
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    committed_source_bundle_sha256,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.gen1_field_moves import Gen1FieldMovePort  # noqa: E402
from pokemon_red_completion.gen1_maps import map_graph  # noqa: E402
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver  # noqa: E402
from pokemon_red_completion.gen1_strength import (  # noqa: E402
    Gen1StrengthExecutor,
    StrengthGoal,
    StrengthState,
    plan_strength,
)
from pokemon_red_completion.gen1_terrain import (  # noqa: E402
    terrain_from_blocks,
    tilesets,
    water_tilesets,
)
from pokemon_red_completion.gen1_trainer_sight import (  # noqa: E402
    Gen1TrainerSightProjector,
    TrainerSightZone,
    trainer_headers,
    trainer_sight_zones,
)
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    local_graph,
    map_object_events,
    traversal_rules,
)
from pokemon_red_completion.global_router import MacroGraph  # noqa: E402
from pokemon_red_completion.lavender import DEFAULT_LAVENDER_TIMING, _use_bag_item  # noqa: E402
from pokemon_red_completion.observation import (  # noqa: E402
    EventFlag,
    ItemId,
    MapId,
    PokemonRedStateReader,
    event_flag_is_set,
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
    TraversalHazard,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route  # noqa: E402
from pokemon_red_completion.victory_road import (  # noqa: E402
    VictoryRoadProgress,
    run_victory_road_chapter,
)

REQUIRED_CAPTURE_OBJECTIVES = frozenset({"defeat_giovanni", "obtain_strength"})
MAP_ID = int(MapId.VICTORY_ROAD_1F)
STRENGTH_BOUNDARY_YX = (17, 8)
PLANNED_STRENGTH_TERMINAL_YX = (12, 17)
SWITCH_YX = (13, 17)
EXIT_APPROACH_YX = (1, 2)
EXPECTED_MALE_TRAINER_LANE = ((3, 3), (4, 3))


class VictoryRoadTrainerSightProbeError(RuntimeError):
    """Raised when live play falsifies trainer-sight route semantics."""


class _ReachedStrengthBoundary(RuntimeError):
    pass


def _stop_at_strength_boundary(progress: VictoryRoadProgress) -> None:
    if progress.checkpoint_id == "badge_corridor":
        raise _ReachedStrengthBoundary


def _artifact_identity(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, None
    return True, hashlib.sha256(path.read_bytes()).hexdigest()


def _adjacent_artifacts(rom_path: Path) -> tuple[tuple[bool, str | None], ...]:
    return tuple(
        _artifact_identity(Path(f"{rom_path}{suffix}"))
        for suffix in (".ram", ".rtc", ".state")
    )


def hazard_crossings(
    plan: RoutePlan,
    hazards: tuple[TraversalHazard, ...],
) -> tuple[tuple[int, int], ...]:
    constrained = {item.at for item in hazards if item.kind == "trainer_sight"}
    return tuple(step.expected_at for step in plan.steps if step.expected_at in constrained)


def _public_plan(plan: RoutePlan) -> dict[str, object]:
    return {
        "start_yx": list(plan.start_at),
        "terminal_yx": list(plan.terminal_at),
        "steps": [
            {
                "source_yx": list(step.source_at),
                "action": step.action,
                "expected_yx": list(step.expected_at),
                "kind": step.kind,
            }
            for step in plan.steps
        ],
    }


def _public_zone(zone: TrainerSightZone) -> dict[str, object]:
    return {
        "sprite_index": zone.sprite_index,
        "trainer_class": zone.trainer_class,
        "trainer_set": zone.trainer_set,
        "trainer_yx": list(zone.at),
        "facing": zone.facing.value,
        "engage_distance_tiles": zone.engage_distance,
        "event_flag": zone.event_flag,
        "defeated": zone.defeated,
        "visible_at_planning_boundary": zone.visible,
        "reserved_lane_yx": [list(at) for at in zone.lane],
    }


def _public_execution(report: RouteExecutionReport) -> dict[str, object]:
    return {
        "passed": report.passed,
        "movement_requests": report.movement_requests,
        "acknowledged_steps": len(report.executed_steps),
        "wait_actions": report.wait_actions,
        "interruptions": [item.kind for item in report.interruptions],
        "replans": [
            {
                "ordinal": item.ordinal,
                "map_id": item.map_id,
                "at_yx": list(item.at),
                "candidate_hazard_yx": list(item.newly_blocked),
                "replacement_steps": item.replacement_steps,
                "reason": item.reason,
            }
            for item in report.replans
        ],
        "terminal_map_id": report.terminal.map_id,
        "terminal_yx": list(report.terminal.at),
        "terminal_ready": report.terminal.ready,
    }


def _replanner(graph):
    macro = MacroGraph({MAP_ID: ()})

    def replan(request: ReplanRequest) -> RoutePlan:
        return plan_route(
            macro,
            {MAP_ID: graph},
            request.current.map_id,
            request.current.at,
            request.goal_map,
            goal_at=request.goal_at,
            blocked=request.blocked,
        )

    return replan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    fingerprint = verify_rom(args.rom)
    envelope_path = args.envelope or Path(f"{args.state}.json")
    capture = load_captured_progress(envelope_path, state_path=args.state)
    missing = REQUIRED_CAPTURE_OBJECTIVES.difference(capture.verified_objective_ids)
    if missing:
        raise VictoryRoadTrainerSightProbeError(
            f"capture lacks verified objectives {sorted(missing)}"
        )

    source = detect_source_identity(PROJECT_ROOT, include_untracked=False)
    require_clean_source(source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise VictoryRoadTrainerSightProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(PROJECT_ROOT, revision=source.git_commit)
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise VictoryRoadTrainerSightProbeError(
            "the executable source differs from its commit"
        )

    rom = args.rom.read_bytes()
    maps = map_graph(rom)
    rules = traversal_rules(rom, maps)
    sets = tilesets(rom)
    surf_tileset_ids = water_tilesets(rom)
    events = map_object_events(rom, {MAP_ID})
    headers = trainer_headers(rom, {MAP_ID})
    before_artifacts = _adjacent_artifacts(args.rom)

    with PyBoyAdapter(args.rom) as emulator:
        emulator.load_state(args.state)
        reader = PokemonRedStateReader(emulator)
        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        try:
            run_victory_road_chapter(
                emulator,
                reader,
                controller,
                progress=_stop_at_strength_boundary,
            )
        except _ReachedStrengthBoundary:
            pass
        else:
            raise VictoryRoadTrainerSightProbeError(
                "qualified teacher did not expose the pre-Strength boundary"
            )

        boundary = reader.read()
        if (
            boundary.map_id != MAP_ID
            or (boundary.player_y, boundary.player_x) != STRENGTH_BOUNDARY_YX
            or boundary.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise VictoryRoadTrainerSightProbeError("Victory Road boundary changed")

        counted = CountingExecutor(controller)
        start_frames = emulator.frame_count
        _use_bag_item(
            counted,
            reader,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            ItemId.MAX_REPEL,
        )
        field = Gen1FieldMovePort(counted, reader, emulator)
        field.execute(MacroAction(MacroActionKind.FIELD_MOVE, "strength:activate"))

        raw = reader.read()
        if raw.player_y is None or raw.player_x is None:
            raise VictoryRoadTrainerSightProbeError(
                "Strength activation lost the player coordinate"
            )
        blocks = reader.read_current_map_blocks()
        terrain = terrain_from_blocks(
            rom,
            MAP_ID,
            blocks.rows,
            sets,
            water_set_ids=surf_tileset_ids,
        )
        initial_strength = StrengthState.from_observation(
            (raw.player_y, raw.player_x),
            reader.read_current_strength_boulders(),
        )
        strength_plan = plan_strength(
            terrain,
            rules,
            initial_strength,
            StrengthGoal(
                SWITCH_YX,
                boulder_index=5,
                player_at=PLANNED_STRENGTH_TERMINAL_YX,
            ),
            raw,
            blocked=reader.read_current_object_coordinates() - initial_strength.occupied,
        )
        strength_execution = Gen1StrengthExecutor(counted, reader, emulator).execute(
            strength_plan
        )
        planned = reader.read()
        if (
            not strength_execution.passed
            or (planned.player_y, planned.player_x) != PLANNED_STRENGTH_TERMINAL_YX
            or not event_flag_is_set(
                planned.event_flags,
                int(EventFlag.VICTORY_ROAD_1F_BOULDER_ON_SWITCH),
            )
        ):
            raise VictoryRoadTrainerSightProbeError("the planned Strength boundary changed")

        current_objects = reader.read_current_map_objects()
        zones = trainer_sight_zones(headers, events, planned, current_objects)
        male = next((zone for zone in zones if zone.sprite_index == 2), None)
        if male is None or male.lane != EXPECTED_MALE_TRAINER_LANE or male.defeated:
            raise VictoryRoadTrainerSightProbeError("male trainer lane changed")

        terrain = terrain_from_blocks(
            rom,
            MAP_ID,
            reader.read_current_map_blocks().rows,
            sets,
            water_set_ids=surf_tileset_ids,
        )
        graph = local_graph(
            terrain,
            rules,
            blocked=reader.read_current_object_coordinates(),
        )
        macro = MacroGraph({MAP_ID: ()})
        unsafe = plan_route(
            macro,
            {MAP_ID: graph},
            MAP_ID,
            PLANNED_STRENGTH_TERMINAL_YX,
            MAP_ID,
            goal_at=EXIT_APPROACH_YX,
        )
        projector = Gen1TrainerSightProjector(rom, reader)
        hazards = projector.observe_hazards(planned)
        crossings = hazard_crossings(unsafe, hazards)
        if (4, 3) not in crossings:
            raise VictoryRoadTrainerSightProbeError(
                "the unprotected shortest route no longer enters trainer sight"
            )

        observer = Gen1TraversalObserver(reader, hazard_projector=projector)
        report = execute_route(
            unsafe,
            counted,
            observer,
            replanner=_replanner(graph),
            limits=RouteExecutionLimits(max_replans=4),
        )
        final = reader.read()
        if (
            not report.passed
            or len(report.replans) != 1
            or report.replans[0].reason != "trainer_sight"
            or report.replans[0].newly_blocked != (4, 3)
            or report.interruptions
            or report.movement_requests != len(report.executed_steps)
            or (final.map_id, final.player_y, final.player_x)
            != (MAP_ID, *EXIT_APPROACH_YX)
            or reader.trainer_engagement_active()
            or not reader.read_input_readiness().ready
        ):
            raise VictoryRoadTrainerSightProbeError(
                "trainer-sight route did not settle under its exact contract"
            )
        frames_executed = emulator.frame_count - start_frames
        controller_released = not emulator.pressed_buttons

    if before_artifacts != _adjacent_artifacts(args.rom):
        raise VictoryRoadTrainerSightProbeError(
            "the no-save probe changed a ROM-adjacent artifact"
        )

    payload = {
        "schema": "victory-road-trainer-sight-route-probe-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "rom": fingerprint.public_dict(),
        "source": {
            "git_commit": source.git_commit,
            "source_bundle_sha256": source_bundle,
        },
        "capture": {
            "checkpoint_id": capture.checkpoint_id,
            "required_verified_objectives": sorted(REQUIRED_CAPTURE_OBJECTIVES),
        },
        "strength_boundary": {
            "initial_yx": list(STRENGTH_BOUNDARY_YX),
            "planned_terminal_yx": list(PLANNED_STRENGTH_TERMINAL_YX),
            "plan_steps": len(strength_plan.steps),
            "explored_states": strength_plan.explored_states,
            "execution_passed": strength_execution.passed,
            "switch_event_set": True,
        },
        "trainers": [_public_zone(zone) for zone in zones],
        "selection": {
            "unprotected_plan": _public_plan(unsafe),
            "trainer_sight_crossings_yx": [list(at) for at in crossings],
            "rom_object_positions_used_as_solid_blockers": True,
            "trainer_lanes_used_as_solid_objects": False,
        },
        "execution": _public_execution(report),
        "decision": {
            "hazard_yx": [4, 3],
            "hazard_kind": "trainer_sight",
            "input_sent_toward_hazard": False,
            "trainer_engagement_observed": False,
            "battle_observed": False,
        },
        "frames_executed_after_strength_boundary": frames_executed,
        "actions_executed_after_strength_boundary": counted.actions_executed,
        "controller_released": controller_released,
        "rom_adjacent_artifacts_unchanged": True,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "Trainer sight passed: unsafe route crossed "
        f"{len(crossings)} reserved square(s), then zero-input replanned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
