#!/usr/bin/env python3
"""Exercise a post-Hideout story-versus-collection destination choice.

The authenticated capture is the healed Celadon Center boundary after the
Silph Scope is secured.  Rescuing Fuji advances the completion route but is
farther away than the optional Eevee gift.  The teacher therefore rejects the
unique minimum-cost candidate, while the cartridge planner and generic
executor retain authority over the selected route to Pokémon Tower.
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
from pokemon_red_completion.gen1_story_routing import apply_gen1_story_requirements
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
    public_route_execution_summary,
    public_route_plan_summary,
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
STORY_DESTINATION = "pokemon.red:destination:pokemon_tower"
COLLECTION_DESTINATION = "pokemon.red:destination:eevee_gift"
REQUIRED_CAPTURE_OBJECTIVES = frozenset(
    {
        "reach_celadon",
        "clear_rocket_hideout",
        "obtain_silph_scope",
    }
)


class CeladonStrategicRouteProbeError(RuntimeError):
    """Raised when the capture, branch or live route fails closed."""


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
        raise CeladonStrategicRouteProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=source.git_commit,
    )
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise CeladonStrategicRouteProbeError(
            "the executable source differs from its published commit"
        )

    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    state_path = args.state
    envelope_path = args.envelope or state_path.with_name(state_path.name + ".json")
    envelope = load_captured_progress(envelope_path, state_path=state_path)
    if not REQUIRED_CAPTURE_OBJECTIVES.issubset(envelope.verified_objective_ids):
        raise CeladonStrategicRouteProbeError(
            "the capture lacks the verified post-Hideout objective lineage"
        )
    state_sha256_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    adjacent_before = rom_adjacent_artifacts(rom_path)

    rom = rom_path.read_bytes()
    maps = map_graph(rom)
    macro = macro_graph_from_nodes(maps)
    world = walkable_world(rom)
    rules = traversal_rules(rom, maps)
    local_graphs = apply_gen1_story_requirements(
        {
            map_id: local_graph(
                terrain,
                rules,
                blocked={event.at for event in map_object_events(rom, {map_id})},
            )
            for map_id, terrain in world.items()
        }
    )

    timing = DEFAULT_QUALIFIED_PLAY_TIMING
    with PyBoyAdapter(rom_path) as emulator:
        emulator.load_state(state_path)
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        if (
            raw.map_id != MapId.CELADON_POKECENTER
            or (raw.player_y, raw.player_x) != (3, 3)
            or not reader.read_input_readiness().ready
        ):
            raise CeladonStrategicRouteProbeError(
                "the capture is not the ready post-Hideout Celadon Center boundary"
            )
        observer = Gen1TraversalObserver(reader)
        observed = observer.observe()
        if observed.last_outside_map != MapId.CELADON_CITY:
            raise CeladonStrategicRouteProbeError(
                "the capture lacks the live Celadon return-warp context"
            )
        plans = {
            STORY_DESTINATION: plan_route(
                macro,
                local_graphs,
                observed.map_id,
                observed.at,
                MapId.POKEMON_TOWER_1F.value,
                capabilities=observed.capabilities,
                last_outside=observed.last_outside_map,
                start_mode=observed.mode,
            ),
            COLLECTION_DESTINATION: plan_route(
                macro,
                local_graphs,
                observed.map_id,
                observed.at,
                MapId.CELADON_MANSION_ROOF_HOUSE.value,
                capabilities=observed.capabilities,
                last_outside=observed.last_outside_map,
                start_mode=observed.mode,
            ),
        }
        minimum_cost = min(plan.cost for plan in plans.values())
        minimum_destinations = tuple(
            destination for destination, plan in plans.items() if plan.cost == minimum_cost
        )
        if minimum_destinations != (COLLECTION_DESTINATION,):
            raise CeladonStrategicRouteProbeError(
                "the story-versus-collection branch lacks its unique cost baseline"
            )
        if plans[STORY_DESTINATION].cost <= minimum_cost:
            raise CeladonStrategicRouteProbeError(
                "the teacher did not reject the minimum-cost candidate"
            )
        bindings = (
            DestinationRouteBinding.available(
                STORY_DESTINATION,
                (
                    StrategicNavigationTag.REMOVE_BLOCKER,
                    StrategicNavigationTag.STORY_PROGRESS,
                ),
                plans[STORY_DESTINATION],
            ),
            DestinationRouteBinding.available(
                COLLECTION_DESTINATION,
                (
                    StrategicNavigationTag.ACQUIRE_PARTY_MEMBER,
                    StrategicNavigationTag.COLLECTION,
                    StrategicNavigationTag.OPTIONAL_REWARD,
                ),
                plans[COLLECTION_DESTINATION],
            ),
        )
        strategic_choice = bind_strategic_navigation_decision(
            episode_id="celadon-story-over-collection-calibration-2026-08-11",
            decision_index=0,
            root_lineage_id="celadon-post-hideout-diagnostic-root",
            partition="unassigned",
            actor="deterministic_teacher",
            policy_id="qualified-completion-order-v1",
            semantic_need_tags=(
                StrategicNavigationTag.ADVANCE_STORY,
                StrategicNavigationTag.REMOVE_BLOCKER,
            ),
            origin_semantic_tags=(
                StrategicNavigationTag.OVERWORLD,
                StrategicNavigationTag.SAFE_HUB,
            ),
            origin_region_ref="pokemon.red:region:celadon",
            bindings=bindings,
            selected_destination_ref=STORY_DESTINATION,
        )

        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        actions = CountingExecutor(controller)
        wild_handler = Gen1WildFleeHandler(
            actions,
            reader,
            maximum_flees=8,
            stabilization_frames=timing.route_1_wild_exit_stabilization_frames,
            route_name="generated post-Hideout Celadon-to-Tower route",
        )
        limits = RouteExecutionLimits(
            max_step_attempts=timing.max_route_1_step_attempts,
            max_interruptions=8,
            max_replans=8,
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
                last_outside=request.current.last_outside_map,
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
        final_traversal = observer.observe()
        frames_executed = emulator.frame_count - frame_start
        controller_released = not emulator.pressed_buttons

    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise CeladonStrategicRouteProbeError("the private input capture changed")
    artifacts_unchanged = adjacent_before == rom_adjacent_artifacts(rom_path)
    if not artifacts_unchanged:
        raise CeladonStrategicRouteProbeError("the no-save probe changed a ROM sidecar")
    if (
        final.map_id != MapId.POKEMON_TOWER_1F
        or (final.player_y, final.player_x) != (17, 10)
        or final_traversal.last_outside_map != MapId.LAVENDER_TOWN
    ):
        raise CeladonStrategicRouteProbeError(
            "the generated route missed Pokémon Tower or its live return context"
        )

    record = strategic_choice.successful_record(report)
    trajectory_decision = strategic_navigation_decision_record(
        record,
        SemanticSnapshot(
            game_id="pokemon.red",
            mode="overworld",
            facts=("need:advance_story", "need:remove_blocker"),
            features={"candidate_count": len(bindings)},
        ),
        step_index=0,
    )
    trajectory_outcome = strategic_navigation_outcome_event(
        record,
        step_index=len(report.executed_steps),
    )
    selected_cost = plans[STORY_DESTINATION].cost
    payload = {
        "schema": "celadon-strategic-objective-route-probe-v1",
        "recorded_on": args.recorded_on,
        "status": "ok",
        "source": source.public_dict(),
        "executable_source_bundle_sha256": source_bundle,
        "rom": fingerprint.public_dict(),
        "capture": envelope.to_dict(),
        "authority_under_test": (
            "The completion teacher preferred story progress over a closer optional "
            "collection reward. Cartridge-derived geometry bound the selected destination "
            "to an exact plan, and the game-neutral executor required live acknowledgement "
            "for every movement while retaining nested return-warp context."
        ),
        "selection_rule": "qualified completion-teacher objective order",
        "route_cost_baseline": {
            "unique_minimum_destination": COLLECTION_DESTINATION,
            "minimum_cost": minimum_cost,
            "teacher_selected_minimum": False,
            "teacher_selected_cost": selected_cost,
            "selected_cost_above_minimum": selected_cost - minimum_cost,
        },
        "candidate_plans": {
            destination: public_route_plan_summary(
                plan,
                map_name=lambda value: MapId(value).name,
            )
            for destination, plan in plans.items()
        },
        "selected_destination": STORY_DESTINATION,
        "selected_execution": public_route_execution_summary(report),
        "final_map": {"id": int(final.map_id), "name": MapId(final.map_id).name},
        "final_yx": [final.player_y, final.player_x],
        "final_last_outside_map": {
            "id": final_traversal.last_outside_map,
            "name": MapId(final_traversal.last_outside_map).name,
        },
        "frames_executed": frames_executed,
        "controller_released": controller_released,
        "private_capture_unchanged": True,
        "rom_adjacent_artifacts_unchanged": artifacts_unchanged,
        "strategic_navigation": {
            "scope": (
                "unassigned non-cost-minimizing calibration; excluded from model development"
            ),
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
        f"wrote {args.out}: selected Pokémon Tower at cost {selected_cost} over "
        f"the cost-{minimum_cost} collection candidate; "
        f"{len(report.executed_steps)} acknowledged steps, "
        f"{len(report.interruptions)} interruptions, {len(report.replans)} replans"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
