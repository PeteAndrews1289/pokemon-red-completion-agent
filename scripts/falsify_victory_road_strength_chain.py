"""Try to disprove planned Strength execution across all of Victory Road.

The authenticated post-Giovanni capture supplies the origin. The qualified
teacher reaches the first puzzle boundary, then live RAM and cartridge-derived
terrain drive five bounded player-and-boulder searches. Cartridge-composed
routes replace both authored room changes. A generic observed-resource manager
renews Repel wherever its counter actually reaches zero, including inside a
Strength plan, rather than walking an authored expiry preamble.

The capture and ROM are private inputs and never appear in the public receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
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
from pokemon_red_completion.gen1_field_moves import (  # noqa: E402
    Gen1FieldMovePort,
    Gen1StrengthReceipt,
)
from pokemon_red_completion.gen1_maps import (  # noqa: E402
    macro_graph_from_nodes,
    map_graph,
)
from pokemon_red_completion.gen1_repel import (  # noqa: E402
    Gen1RepelRenewalManager,
)
from pokemon_red_completion.gen1_route_runtime import (  # noqa: E402
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_story_routing import (  # noqa: E402
    apply_gen1_story_requirements,
)
from pokemon_red_completion.gen1_strength import (  # noqa: E402
    Gen1StrengthExecutor,
    StrengthExecutionReport,
    StrengthGoal,
    StrengthPlan,
    StrengthState,
    plan_strength,
)
from pokemon_red_completion.gen1_terrain import (  # noqa: E402
    Tileset,
    terrain_from_blocks,
    tilesets,
    walkable_world,
    water_tilesets,
)
from pokemon_red_completion.gen1_trainer_sight import (  # noqa: E402
    Gen1TrainerSightProjector,
)
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    TraversalRules,
    local_graph,
    map_object_events,
    traversal_rules,
)
from pokemon_red_completion.lavender import (  # noqa: E402
    DEFAULT_LAVENDER_TIMING,
    _use_bag_item,
)
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
    RouteActionPort,
    RouteExecutionLimits,
    RouteExecutionReport,
    RouteReplanner,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route  # noqa: E402
from pokemon_red_completion.victory_road import (  # noqa: E402
    VictoryRoadProgress,
    _step,
    run_victory_road_chapter,
)

REQUIRED_CAPTURE_OBJECTIVES = frozenset({"defeat_giovanni", "obtain_strength"})
VICTORY_ROAD_MAPS = frozenset(
    {
        int(MapId.VICTORY_ROAD_1F),
        int(MapId.VICTORY_ROAD_2F),
        int(MapId.VICTORY_ROAD_3F),
    }
)
VR1_SWITCH_YX = (13, 17)
VR2_SWITCH_1_YX = (16, 1)
VR3_SWITCH_YX = (5, 3)
VR3_HOLE_YX = (15, 23)
VR2_SWITCH_2_YX = (16, 9)
class VictoryRoadStrengthChainProbeError(RuntimeError):
    """Raised when the full live Strength proof cannot satisfy its contract."""


class _ReachedStrengthBoundary(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _SolvedPhase:
    phase_id: str
    map_id: int
    event: EventFlag
    goal: StrengthGoal
    plan: StrengthPlan
    execution: StrengthExecutionReport


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


def _public_state(state: StrengthState) -> dict[str, object]:
    return {
        "player_yx": list(state.player_at),
        "boulders": [
            {"sprite_index": item.sprite_index, "yx": list(item.at)}
            for item in state.boulders
        ],
    }


def _activation_payload(receipt: Gen1StrengthReceipt) -> dict[str, object]:
    return {
        "party_index": receipt.party_index,
        "submenu_row": receipt.submenu_row,
        "confirmation_count": receipt.confirmation_count,
        "already_active": receipt.already_active,
    }


def _phase_payload(phase: _SolvedPhase) -> dict[str, object]:
    plan = phase.plan
    execution = phase.execution
    return {
        "phase_id": phase.phase_id,
        "map_id": phase.map_id,
        "event": phase.event.name,
        "event_set": True,
        "goal_boulder_yx": list(phase.goal.boulder_at),
        "goal_boulder_index": phase.goal.boulder_index,
        "goal_removes_boulder": phase.goal.remove_boulder,
        "max_states": 100_000,
        "explored_states": plan.explored_states,
        "cost": plan.cost,
        "steps": len(plan.steps),
        "walks": sum(step.kind == "walk" for step in plan.steps),
        "pushes": sum(step.kind == "push" for step in plan.steps),
        "drops": sum(step.kind == "drop" for step in plan.steps),
        "initial": _public_state(plan.states[0]),
        "terminal": _public_state(plan.states[-1]),
        "execution": {
            "passed": execution.passed,
            "acknowledged_steps": execution.acknowledged_steps,
            "controller_inputs": execution.controller_inputs,
            "wait_actions": execution.wait_actions,
            "push_receipts": [
                {
                    "ordinal": receipt.ordinal,
                    "direction": receipt.direction.value,
                    "boulder_index": receipt.boulder_index,
                    "player_before_yx": list(receipt.player_before),
                    "player_after_yx": list(receipt.player_after),
                    "boulder_before_yx": list(receipt.boulder_before),
                    "boulder_after_yx": list(receipt.boulder_after),
                    "boulder_removed": receipt.boulder_removed,
                    "player_stationary": receipt.player_stationary,
                    "boulder_dust_observed": receipt.boulder_dust_observed,
                    "pushed_flag_observed": receipt.pushed_flag_observed,
                    "engine_acknowledged": receipt.engine_acknowledged,
                    "engine_attempt_cost": receipt.engine_attempt_cost,
                }
                for receipt in execution.pushes
            ],
            "resource_renewals": [
                {
                    "kind": receipt.kind,
                    "map_id": receipt.map_id,
                    "at_yx": list(receipt.at),
                    "before_remaining": receipt.before_remaining,
                    "after_remaining": receipt.after_remaining,
                    "units_consumed": receipt.units_consumed,
                    "details": dict(receipt.details),
                }
                for receipt in execution.resource_renewals
            ],
        },
    }


def _route_payload(plan: RoutePlan, report: RouteExecutionReport) -> dict[str, object]:
    return {
        "map_ids": list(plan.macro_path.maps),
        "start_yx": list(plan.start_at),
        "terminal_yx": list(plan.terminal_at),
        "steps": len(plan.steps),
        "passages": [step.kind for step in plan.steps if step.kind != "walk"],
        "execution": {
            "passed": report.passed,
            "movement_requests": report.movement_requests,
            "acknowledged_steps": len(report.executed_steps),
            "interruptions": [item.kind for item in report.interruptions],
            "replans": [item.reason for item in report.replans],
            "terminal_map_id": report.terminal.map_id,
            "terminal_yx": list(report.terminal.at),
            "resource_renewals": [
                {
                    "kind": receipt.kind,
                    "map_id": receipt.map_id,
                    "at_yx": list(receipt.at),
                    "before_remaining": receipt.before_remaining,
                    "after_remaining": receipt.after_remaining,
                    "units_consumed": receipt.units_consumed,
                    "details": dict(receipt.details),
                }
                for receipt in report.resource_renewals
            ],
        },
    }


def _solve_phase(
    phase_id: str,
    event: EventFlag,
    goal: StrengthGoal,
    rom: bytes,
    sets: Mapping[int, Tileset],
    surf_tileset_ids: frozenset[int],
    rules: TraversalRules,
    occupancy: dict[int, frozenset[tuple[int, int]]],
    actions: RouteActionPort,
    reader: PokemonRedStateReader,
    emulator: PyBoyAdapter,
    resource_manager: Gen1RepelRenewalManager,
    route_observer: Gen1TraversalObserver,
) -> _SolvedPhase:
    raw = reader.read()
    if raw.map_id is None or raw.player_y is None or raw.player_x is None:
        raise VictoryRoadStrengthChainProbeError(f"{phase_id} lacks a live map position")
    blocks = reader.read_current_map_blocks()
    terrain = terrain_from_blocks(
        rom,
        raw.map_id,
        blocks.rows,
        sets,
        water_set_ids=surf_tileset_ids,
    )
    initial = StrengthState.from_observation(
        (raw.player_y, raw.player_x),
        reader.read_current_strength_boulders(),
    )
    live_non_boulder_occupancy = (
        reader.read_current_object_coordinates() - initial.occupied
    )
    plan = plan_strength(
        terrain,
        rules,
        initial,
        goal,
        raw,
        blocked=occupancy[raw.map_id] | live_non_boulder_occupancy,
        max_states=100_000,
    )
    execution = Gen1StrengthExecutor(
        actions,
        reader,
        emulator,
        resource_manager=resource_manager,
        resource_observer=route_observer,
    ).execute(plan)
    final = reader.read()
    if (
        not execution.passed
        or not event_flag_is_set(final.event_flags, int(event))
        or not reader.read_input_readiness().ready
    ):
        raise VictoryRoadStrengthChainProbeError(f"{phase_id} did not settle exactly")
    return _SolvedPhase(phase_id, raw.map_id, event, goal, plan, execution)


def _compose_live_passage(
    rom: bytes,
    reader: PokemonRedStateReader,
    macro,
    static_graphs,
    sets: Mapping[int, Tileset],
    surf_tileset_ids: frozenset[int],
    rules: TraversalRules,
    target_map: int,
    target_at: tuple[int, int],
) -> tuple[RoutePlan, RouteReplanner]:
    raw = reader.read()
    if raw.map_id is None or raw.player_y is None or raw.player_x is None:
        raise VictoryRoadStrengthChainProbeError("live passage lacks a start coordinate")
    terrain = terrain_from_blocks(
        rom,
        raw.map_id,
        reader.read_current_map_blocks().rows,
        sets,
        water_set_ids=surf_tileset_ids,
    )
    graphs = dict(static_graphs)
    graphs[raw.map_id] = local_graph(
        terrain,
        rules,
        blocked=reader.read_current_object_coordinates(),
    )
    graphs = apply_gen1_story_requirements(graphs)
    start_at = raw.player_y, raw.player_x
    plan = plan_route(
        macro,
        graphs,
        raw.map_id,
        start_at,
        target_map,
        goal_at=target_at,
        last_outside=int(MapId.ROUTE_23),
    )

    def replan(request: ReplanRequest) -> RoutePlan:
        return plan_route(
            macro,
            graphs,
            request.current.map_id,
            request.current.at,
            request.goal_map,
            goal_at=request.goal_at,
            blocked=request.blocked,
            capabilities=request.current.capabilities,
            last_outside=int(MapId.ROUTE_23),
        )

    return plan, replan


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
        raise VictoryRoadStrengthChainProbeError(
            f"capture lacks verified objectives {sorted(missing)}"
        )

    source = detect_source_identity(PROJECT_ROOT, include_untracked=False)
    require_clean_source(source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise VictoryRoadStrengthChainProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(PROJECT_ROOT, revision=source.git_commit)
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise VictoryRoadStrengthChainProbeError(
            "the executable source differs from its commit"
        )

    rom = args.rom.read_bytes()
    maps = map_graph(rom)
    macro = macro_graph_from_nodes(maps)
    rules = traversal_rules(rom, maps)
    sets = tilesets(rom)
    static_world = walkable_world(rom)
    surf_tileset_ids = water_tilesets(rom)
    object_events = map_object_events(rom, VICTORY_ROAD_MAPS)
    occupancy = {
        map_id: frozenset(
            event.at
            for event in object_events
            if event.map_id == map_id and not event.is_boulder
        )
        for map_id in VICTORY_ROAD_MAPS
    }
    static_graphs = {
        map_id: local_graph(
            static_world[map_id],
            rules,
            blocked={event.at for event in object_events if event.map_id == map_id},
        )
        for map_id in VICTORY_ROAD_MAPS
    }
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
            raise VictoryRoadStrengthChainProbeError(
                "qualified teacher did not expose the pre-Strength boundary"
            )

        boundary = reader.read()
        if (
            boundary.map_id != MapId.VICTORY_ROAD_1F
            or (boundary.player_y, boundary.player_x) != (17, 8)
            or boundary.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise VictoryRoadStrengthChainProbeError("Victory Road boundary changed")

        counted = CountingExecutor(controller)
        field = Gen1FieldMovePort(counted, reader, emulator)
        projector = Gen1TrainerSightProjector(rom, reader)
        route_observer = Gen1TraversalObserver(reader, hazard_projector=projector)

        def use_repel(item_id: int) -> None:
            _use_bag_item(
                counted,
                reader,
                emulator,
                DEFAULT_LAVENDER_TIMING,
                item_id,
            )

        resource_manager = Gen1RepelRenewalManager(counted, reader, use_repel)
        activations: list[Gen1StrengthReceipt] = []
        phases: list[_SolvedPhase] = []
        passage_plans: list[RoutePlan] = []
        passage_reports: list[RouteExecutionReport] = []

        _use_bag_item(
            counted,
            reader,
            emulator,
            DEFAULT_LAVENDER_TIMING,
            ItemId.MAX_REPEL,
        )
        field.execute(MacroAction(MacroActionKind.FIELD_MOVE, "strength:activate"))
        activations.append(field.strength_receipts[-1])
        phases.append(
            _solve_phase(
                "victory_road_1f_switch",
                EventFlag.VICTORY_ROAD_1F_BOULDER_ON_SWITCH,
                StrengthGoal(
                    VR1_SWITCH_YX,
                    boulder_index=5,
                    player_at=(12, 17),
                ),
                rom,
                sets,
                surf_tileset_ids,
                rules,
                occupancy,
                counted,
                reader,
                emulator,
                resource_manager,
                route_observer,
            )
        )
        plan, replanner = _compose_live_passage(
            rom,
            reader,
            macro,
            static_graphs,
            sets,
            surf_tileset_ids,
            rules,
            int(MapId.VICTORY_ROAD_2F),
            (0, 8),
        )
        passage_plans.append(plan)
        passage_reports.append(
            execute_route(
                plan,
                counted,
                route_observer,
                replanner=replanner,
                resource_manager=resource_manager,
                limits=RouteExecutionLimits(max_replans=4),
            )
        )

        field.execute(MacroAction(MacroActionKind.FIELD_MOVE, "strength:activate"))
        activations.append(field.strength_receipts[-1])
        phases.append(
            _solve_phase(
                "victory_road_2f_switch_1",
                EventFlag.VICTORY_ROAD_2F_BOULDER_ON_SWITCH_1,
                StrengthGoal(
                    VR2_SWITCH_1_YX,
                    boulder_index=11,
                    player_at=(16, 2),
                ),
                rom,
                sets,
                surf_tileset_ids,
                rules,
                occupancy,
                counted,
                reader,
                emulator,
                resource_manager,
                route_observer,
            )
        )
        plan, replanner = _compose_live_passage(
            rom,
            reader,
            macro,
            static_graphs,
            sets,
            surf_tileset_ids,
            rules,
            int(MapId.VICTORY_ROAD_3F),
            (23, 7),
        )
        passage_plans.append(plan)
        passage_reports.append(
            execute_route(
                plan,
                counted,
                route_observer,
                replanner=replanner,
                resource_manager=resource_manager,
                limits=RouteExecutionLimits(max_replans=4),
            )
        )

        field.execute(MacroAction(MacroActionKind.FIELD_MOVE, "strength:activate"))
        activations.append(field.strength_receipts[-1])
        phases.append(
            _solve_phase(
                "victory_road_3f_switch",
                EventFlag.VICTORY_ROAD_3F_BOULDER_ON_SWITCH_1,
                StrengthGoal(VR3_SWITCH_YX, boulder_index=7),
                rom,
                sets,
                surf_tileset_ids,
                rules,
                occupancy,
                counted,
                reader,
                emulator,
                resource_manager,
                route_observer,
            )
        )
        phases.append(
            _solve_phase(
                "victory_road_3f_hole",
                EventFlag.VICTORY_ROAD_3F_BOULDER_IN_HOLE,
                StrengthGoal(VR3_HOLE_YX, boulder_index=10, remove_boulder=True),
                rom,
                sets,
                surf_tileset_ids,
                rules,
                occupancy,
                counted,
                reader,
                emulator,
                resource_manager,
                route_observer,
            )
        )

        for _ in range(24):
            if reader.read().map_id == MapId.VICTORY_ROAD_2F:
                break
            _step(counted, reader, "right", "planned Strength probe follow boulder")
        arrived = reader.read()
        if (arrived.map_id, arrived.player_y, arrived.player_x) != (
            MapId.VICTORY_ROAD_2F,
            16,
            22,
        ):
            raise VictoryRoadStrengthChainProbeError("the hole warp changed")
        _step(counted, reader, "down", "planned Strength probe final flank")
        field.execute(MacroAction(MacroActionKind.FIELD_MOVE, "strength:activate"))
        activations.append(field.strength_receipts[-1])
        phases.append(
            _solve_phase(
                "victory_road_2f_switch_2",
                EventFlag.VICTORY_ROAD_2F_BOULDER_ON_SWITCH_2,
                StrengthGoal(VR2_SWITCH_2_YX, boulder_index=13),
                rom,
                sets,
                surf_tileset_ids,
                rules,
                occupancy,
                counted,
                reader,
                emulator,
                resource_manager,
                route_observer,
            )
        )

        final = reader.read()
        if final.map_id is None or final.player_y is None or final.player_x is None:
            raise VictoryRoadStrengthChainProbeError("terminal position disappeared")
        frames_executed = emulator.frame_count
        controller_released = not emulator.pressed_buttons

    renewals = tuple(
        renewal
        for report in passage_reports
        for renewal in report.resource_renewals
    ) + tuple(
        renewal
        for phase in phases
        for renewal in phase.execution.resource_renewals
    )

    if before_artifacts != _adjacent_artifacts(args.rom):
        raise VictoryRoadStrengthChainProbeError(
            "the no-save probe changed a ROM-adjacent artifact"
        )

    payload = {
        "schema": "victory-road-composed-resource-chain-probe-v1",
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
        "boundary": {
            "map_id": int(MapId.VICTORY_ROAD_1F),
            "player_yx": [17, 8],
            "ready": True,
        },
        "planner": {
            "algorithm": "bounded_dijkstra_player_and_toggle_present_boulders",
            "phase_count": len(phases),
            "phases": [_phase_payload(phase) for phase in phases],
        },
        "execution": {
            "passed": all(phase.execution.passed for phase in phases)
            and all(report.passed for report in passage_reports),
            "activations": [_activation_payload(item) for item in activations],
            "derived_phase_steps": sum(len(phase.plan.steps) for phase in phases),
            "derived_phase_pushes": sum(
                len(phase.execution.pushes) for phase in phases
            ),
            "composed_inter_phase_routes": [
                _route_payload(plan, report)
                for plan, report in zip(
                    passage_plans,
                    passage_reports,
                    strict=True,
                )
            ],
            "authored_inter_phase_route_steps": 0,
            "actions_executed_after_boundary": counted.actions_executed,
            "frames_executed": frames_executed,
            "controller_released": controller_released,
            "terminal_map_id": final.map_id,
            "terminal_player_yx": [final.player_y, final.player_x],
            "all_switch_events_set": True,
        },
        "resource_boundary": {
            "kind": "repel_expiry",
            "authored_direction_count": 0,
            "renewals": [
                {
                    "kind": receipt.kind,
                    "map_id": receipt.map_id,
                    "at_yx": list(receipt.at),
                    "before_remaining": receipt.before_remaining,
                    "after_remaining": receipt.after_remaining,
                    "units_consumed": receipt.units_consumed,
                    "details": dict(receipt.details),
                }
                for receipt in renewals
            ],
            "puzzle_search_resumed_after_observed_replenishment": bool(renewals),
        },
        "rom_adjacent_artifacts_unchanged": True,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Strength chain passed: {len(phases)} phases, "
        f"{payload['execution']['derived_phase_steps']} planned steps"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
