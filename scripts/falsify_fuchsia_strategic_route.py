#!/usr/bin/env python3
"""Exercise one genuine post-Safari destination choice with generated routing.

The authenticated private capture supplies the verified Fuchsia Center boundary.
Both Koga's Gym and the Warden's house are progression-relevant and currently
reachable.  The qualified teacher order chooses the Gym; exact movement remains
the responsibility of the cartridge-derived planner and closed-loop executor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.captured_progress import load_captured_progress
from pokemon_red_completion.collection_protocol import (
    committed_source_bundle_sha256,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.gen1_maps import macro_graph_from_nodes, map_graph
from pokemon_red_completion.gen1_route_runtime import (
    Gen1TraversalObserver,
    Gen1WildFleeHandler,
)
from pokemon_red_completion.gen1_terrain import walkable_world
from pokemon_red_completion.gen1_traversal import (
    local_graph,
    map_object_events,
    traversal_rules,
)
from pokemon_red_completion.observation import MapId, PokemonRedStateReader
from pokemon_red_completion.play import DEFAULT_QUALIFIED_PLAY_TIMING
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom
from pokemon_red_completion.route_evidence import (
    public_route_execution,
    public_route_plan,
    rom_adjacent_artifacts,
)
from pokemon_red_completion.route_executor import (
    ReplanRequest,
    RouteExecutionLimits,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route
from pokemon_red_completion.strategic_navigation import StrategicNavigationTag
from pokemon_red_completion.strategic_navigation_binding import (
    DestinationRouteBinding,
    bind_strategic_navigation_decision,
)
from pokemon_red_completion.strategic_navigation_trajectory import (
    strategic_navigation_decision_record,
    strategic_navigation_outcome_event,
)
from pokemon_red_completion.trajectory import SemanticSnapshot

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SELECTED_DESTINATION = "pokemon.red:destination:fuchsia_gym"
REQUIRED_CAPTURE_OBJECTIVES = frozenset(
    {"reach_fuchsia", "obtain_surf", "rescue_fuji", "clear_rocket_hideout"}
)


class FuchsiaStrategicRouteProbeError(RuntimeError):
    """Raised when the captured boundary or generated route fails closed."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, help="defaults to <state>.json")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    args = parser.parse_args(argv)

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise FuchsiaStrategicRouteProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=source.git_commit,
    )
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise FuchsiaStrategicRouteProbeError(
            "the executable source differs from its published commit"
        )

    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    state_path = args.state
    envelope_path = args.envelope or state_path.with_name(state_path.name + ".json")
    envelope = load_captured_progress(envelope_path, state_path=state_path)
    if not REQUIRED_CAPTURE_OBJECTIVES.issubset(envelope.verified_objective_ids):
        raise FuchsiaStrategicRouteProbeError(
            "the capture lacks the verified post-Safari objective lineage"
        )
    state_sha256_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    adjacent_before = rom_adjacent_artifacts(rom_path)

    rom = rom_path.read_bytes()
    maps = map_graph(rom)
    macro = macro_graph_from_nodes(maps)
    world = walkable_world(rom)
    rules = traversal_rules(rom, maps)
    local_graphs = {
        map_id: local_graph(
            terrain,
            rules,
            blocked={event.at for event in map_object_events(rom, {map_id})},
        )
        for map_id, terrain in world.items()
    }

    timing = DEFAULT_QUALIFIED_PLAY_TIMING
    with PyBoyAdapter(rom_path) as emulator:
        emulator.load_state(state_path)
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        if (
            raw.map_id != MapId.FUCHSIA_POKECENTER
            or (raw.player_y, raw.player_x) != (3, 3)
            or not reader.read_input_readiness().ready
        ):
            raise FuchsiaStrategicRouteProbeError(
                "the capture is not the ready post-Safari Fuchsia Center boundary"
            )
        observer = Gen1TraversalObserver(reader)
        observed = observer.observe()
        plans = {
            "pokemon.red:destination:fuchsia_gym": plan_route(
                macro,
                local_graphs,
                observed.map_id,
                observed.at,
                MapId.FUCHSIA_GYM.value,
                capabilities=observed.capabilities,
                last_outside=MapId.FUCHSIA_CITY.value,
                start_mode=observed.mode,
            ),
            "pokemon.red:destination:warden_house": plan_route(
                macro,
                local_graphs,
                observed.map_id,
                observed.at,
                MapId.WARDENS_HOUSE.value,
                capabilities=observed.capabilities,
                last_outside=MapId.FUCHSIA_CITY.value,
                start_mode=observed.mode,
            ),
        }
        bindings = (
            DestinationRouteBinding.available(
                "pokemon.red:destination:fuchsia_gym",
                (
                    StrategicNavigationTag.CHALLENGE,
                    StrategicNavigationTag.STORY_PROGRESS,
                ),
                plans["pokemon.red:destination:fuchsia_gym"],
            ),
            DestinationRouteBinding.available(
                "pokemon.red:destination:warden_house",
                (
                    StrategicNavigationTag.ACQUIRE_RESOURCE,
                    StrategicNavigationTag.STORY_PROGRESS,
                ),
                plans["pokemon.red:destination:warden_house"],
            ),
        )
        strategic_choice = bind_strategic_navigation_decision(
            episode_id="fuchsia-objective-branch-calibration-2026-08-11",
            decision_index=0,
            root_lineage_id="fuchsia-objective-branch-diagnostic-root",
            partition="unassigned",
            actor="deterministic_teacher",
            policy_id="qualified-objective-order-v1",
            semantic_need_tags=(
                StrategicNavigationTag.ADVANCE_STORY,
                StrategicNavigationTag.REACH_NEXT_CHALLENGE,
            ),
            origin_semantic_tags=(
                StrategicNavigationTag.OVERWORLD,
                StrategicNavigationTag.SAFE_HUB,
            ),
            origin_region_ref="pokemon.red:region:fuchsia",
            bindings=bindings,
            selected_destination_ref=SELECTED_DESTINATION,
        )

        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        actions = CountingExecutor(controller)
        wild_handler = Gen1WildFleeHandler(
            actions,
            reader,
            maximum_flees=2,
            stabilization_frames=timing.route_1_wild_exit_stabilization_frames,
            route_name="generated post-Safari Fuchsia objective route",
        )
        limits = RouteExecutionLimits(
            max_step_attempts=timing.max_route_1_step_attempts,
            max_interruptions=2,
            replan_after_unchanged=2,
            retry_wait_frames=timing.route_1_step_retry_wait_frames,
            transition_settle_frames=timing.transition_wait_frames,
        )

        def replan(request: ReplanRequest) -> RoutePlan:
            return plan_route(
                macro,
                local_graphs,
                request.current.map_id,
                request.current.at,
                request.goal_map,
                blocked=request.blocked,
                capabilities=request.current.capabilities,
                last_outside=MapId.FUCHSIA_CITY.value,
                start_mode=request.current.mode,
                goal_at=request.goal_at,
            )

        frame_start = emulator.frame_count
        report = execute_route(
            strategic_choice.selected_plan,
            actions,
            observer,
            interruption_handler=wild_handler,
            replanner=replan,
            limits=limits,
        )
        final = reader.read()
        frames_executed = emulator.frame_count - frame_start
        controller_released = not emulator.pressed_buttons

    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise FuchsiaStrategicRouteProbeError("the private input capture changed")
    artifacts_unchanged = adjacent_before == rom_adjacent_artifacts(rom_path)
    if not artifacts_unchanged:
        raise FuchsiaStrategicRouteProbeError("the no-save probe changed a ROM sidecar")
    if final.map_id != MapId.FUCHSIA_GYM or (final.player_y, final.player_x) != (17, 4):
        raise FuchsiaStrategicRouteProbeError("the generated route missed Fuchsia Gym")

    record = strategic_choice.successful_record(report)
    trajectory_decision = strategic_navigation_decision_record(
        record,
        SemanticSnapshot(
            game_id="pokemon.red",
            mode="overworld",
            facts=("need:advance_story", "need:reach_next_challenge"),
            features={"candidate_count": len(bindings)},
        ),
        step_index=0,
    )
    trajectory_outcome = strategic_navigation_outcome_event(
        record,
        step_index=len(report.executed_steps),
    )
    payload = {
        "schema": "fuchsia-strategic-objective-route-probe-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "source": source.public_dict(),
        "executable_source_bundle_sha256": source_bundle,
        "rom": fingerprint.public_dict(),
        "capture": envelope.to_dict(),
        "authority_under_test": (
            "The qualified teacher selected between two executable progression destinations. "
            "Cartridge-derived geometry bound the selected destination to an exact plan, and "
            "the game-neutral executor required live acknowledgement for every movement."
        ),
        "selection_rule": "qualified completion-teacher objective order",
        "candidate_plans": {
            destination: public_route_plan(
                plan,
                map_name=lambda value: MapId(value).name,
            )
            for destination, plan in plans.items()
        },
        "selected_destination": SELECTED_DESTINATION,
        "selected_execution": public_route_execution(report),
        "final_map": {"id": int(final.map_id), "name": MapId(final.map_id).name},
        "final_yx": [final.player_y, final.player_x],
        "frames_executed": frames_executed,
        "controller_released": controller_released,
        "private_capture_unchanged": True,
        "rom_adjacent_artifacts_unchanged": artifacts_unchanged,
        "strategic_navigation": {
            "scope": "unassigned genuine-branch calibration; excluded from model development",
            "record": record.public_dict(),
            "identity_free_trajectory_decision": trajectory_decision.to_dict(),
            "identity_free_trajectory_outcome": trajectory_outcome.to_dict(),
            "numeric_feature_schema_frozen": False,
            "promotion_eligible": False,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="ascii")
    print(
        f"wrote {args.out}: selected Fuchsia Gym from {len(bindings)} candidates; "
        f"{len(report.executed_steps)} acknowledged steps, {len(report.replans)} replans"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
