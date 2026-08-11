"""Try to disprove a closed-loop Pallet-to-Viridian route live.

The qualified opening and Oak's-errand teachers establish a post-Pokédex state
and exit the lab. From the resulting Pallet coordinate onward, no authored
corridor chooses the route: cartridge map headers, connection geometry, warp
indices, terrain and traversal rules produce every movement and arrival.

Usage::

    POKEMON_RED_ROM=<path> python scripts/falsify_pallet_viridian_route.py \
        --destination center --out docs/evidence/<name>.json

``--inject-first-step-blocker`` is an explicitly artificial fault used to
prove that repeated unacknowledged movement causes a new cartridge-derived
plan. It is evidence about recovery authority, not evidence of a live NPC.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.actions import MacroAction, MacroActionKind  # noqa: E402
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
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
    local_graph,
    map_object_events,
    traversal_rules,
)
from pokemon_red_completion.observation import MapId, PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.opening import run_opening_chapter  # noqa: E402
from pokemon_red_completion.pewter import (  # noqa: E402
    DEFAULT_PEWTER_TIMING,
    LAB_TO_PALLET_DIRECTIONS,
)
from pokemon_red_completion.play import (  # noqa: E402
    DEFAULT_QUALIFIED_PLAY_TIMING,
    _expect_position,
    _move,
    _wait,
    run_oaks_errand_chapter,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    detect_source_identity,
    require_clean_source,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_executor import (  # noqa: E402
    ReplanRequest,
    RouteExecutionLimits,
    RouteExecutionReport,
    TraversalSnapshot,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan, plan_route  # noqa: E402
from pokemon_red_completion.strategic_navigation import (  # noqa: E402
    StrategicNavigationTag,
)
from pokemon_red_completion.strategic_navigation_binding import (  # noqa: E402
    DestinationRouteBinding,
    bind_strategic_navigation_decision,
)
from pokemon_red_completion.strategic_navigation_trajectory import (  # noqa: E402
    strategic_navigation_decision_record,
    strategic_navigation_outcome_event,
)
from pokemon_red_completion.trajectory import SemanticSnapshot  # noqa: E402


class PalletViridianRouteProbeError(RuntimeError):
    """Raised when live play disagrees with the composed route."""


DESTINATIONS = {
    "center": MapId.VIRIDIAN_POKECENTER,
    "home": MapId.REDS_HOUSE_1F,
    "mart": MapId.VIRIDIAN_MART,
}


@dataclass(slots=True)
class FirstStepBlockerInjector:
    """Suppress a disclosed movement so the live executor must replan."""

    delegate: CountingExecutor
    observer: Gen1TraversalObserver
    source: TraversalSnapshot
    direction: str
    remaining: int
    suppressed: int = 0

    def execute(self, action: MacroAction) -> object:
        current = self.observer.observe()
        if (
            self.remaining > 0
            and action.kind is MacroActionKind.MOVE
            and action.value == self.direction
            and current.interruption is None
            and current.map_id == self.source.map_id
            and current.at == self.source.at
        ):
            self.remaining -= 1
            self.suppressed += 1
            return action
        return self.delegate.execute(action)


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
        "maps": [MapId(map_id).name for map_id in plan.macro_path.maps],
        "map_ids": list(plan.macro_path.maps),
        "start_yx": list(plan.start_at),
        "terminal_yx": list(plan.terminal_at),
        "actions": list(plan.actions),
        "segments": [
            {
                "source_map": MapId(segment.source_map).name,
                "source_map_id": segment.source_map,
                "target_map": MapId(segment.target_map).name,
                "target_map_id": segment.target_map,
                "approach_coordinates_yx": [
                    list(coordinate) for coordinate in segment.approach.coordinates
                ],
                "actions": list(segment.actions),
                "transition": {
                    "exit_yx": list(segment.transition.exit_at),
                    "arrival_yx": list(segment.transition.arrival_at),
                    "action": segment.transition.action,
                    "action_in_approach": segment.transition_action_in_approach,
                },
            }
            for segment in plan.segments
        ],
    }


def _public_execution(report: RouteExecutionReport) -> dict[str, object]:
    return {
        "passed": report.passed,
        "movement_requests": report.movement_requests,
        "wait_actions": report.wait_actions,
        "acknowledged_steps": len(report.executed_steps),
        "steps": [
            {
                "source_map_id": receipt.step.source_map,
                "source_yx": list(receipt.step.source_at),
                "action": receipt.step.action,
                "expected_map_id": receipt.step.expected_map,
                "expected_yx": list(receipt.step.expected_at),
                "kind": receipt.step.kind,
                "movement_requests": receipt.movement_requests,
                "interruption_count": receipt.interruption_count,
            }
            for receipt in report.executed_steps
        ],
        "interruptions": [
            {
                "kind": receipt.kind,
                "resumed_map_id": receipt.resumed_map,
                "resumed_yx": list(receipt.resumed_at),
                "details": dict(receipt.details),
            }
            for receipt in report.interruptions
        ],
        "replans": [
            {
                "ordinal": receipt.ordinal,
                "map_id": receipt.map_id,
                "at_yx": list(receipt.at),
                "newly_blocked_yx": list(receipt.newly_blocked),
                "replacement_steps": receipt.replacement_steps,
            }
            for receipt in report.replans
        ],
        "terminal_map_id": report.terminal.map_id,
        "terminal_yx": list(report.terminal.at),
        "terminal_ready": report.terminal.ready,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--recorded-on", default=date.today().isoformat())
    parser.add_argument(
        "--destination",
        choices=tuple(DESTINATIONS),
        default="center",
    )
    parser.add_argument(
        "--inject-first-step-blocker",
        action="store_true",
        help="suppress two first-step inputs to force a disclosed live replan",
    )
    parser.add_argument(
        "--record-safe-hub-choice",
        action="store_true",
        help=(
            "with --destination home, bind Pallet home versus Viridian Center as an "
            "unassigned strategic safe-hub calibration choice"
        ),
    )
    args = parser.parse_args(argv)

    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    source = detect_source_identity(PROJECT_ROOT, include_untracked=False)
    require_clean_source(source)
    if source.git_commit is None:  # pragma: no cover - established above
        raise PalletViridianRouteProbeError("the source commit is unavailable")
    source_bundle = committed_source_bundle_sha256(
        PROJECT_ROOT,
        revision=source.git_commit,
    )
    if working_source_bundle_sha256(PROJECT_ROOT) != source_bundle:
        raise PalletViridianRouteProbeError("the executable source differs from its commit")

    rom = rom_path.read_bytes()
    maps = map_graph(rom)
    macro = macro_graph_from_nodes(maps)
    world = walkable_world(rom)
    rules = traversal_rules(rom, maps)
    destination = DESTINATIONS[args.destination]
    local_graphs = {
        map_id: local_graph(
            terrain,
            rules,
            blocked={event.at for event in map_object_events(rom, {map_id})},
        )
        for map_id, terrain in world.items()
    }
    start_yx = (12, 12)
    plan = plan_route(
        macro,
        local_graphs,
        MapId.PALLET_TOWN.value,
        start_yx,
        destination.value,
    )
    strategic_choice = None
    if args.record_safe_hub_choice:
        if args.destination != "home":
            raise PalletViridianRouteProbeError(
                "safe-hub calibration requires --destination home"
            )
        center_plan = plan_route(
            macro,
            local_graphs,
            MapId.PALLET_TOWN.value,
            start_yx,
            MapId.VIRIDIAN_POKECENTER.value,
        )
        bindings = (
            DestinationRouteBinding.available(
                "pokemon.red:destination:pallet_home",
                (
                    StrategicNavigationTag.RECOVERY,
                    StrategicNavigationTag.SAFE_HUB,
                ),
                plan,
            ),
            DestinationRouteBinding.available(
                "pokemon.red:destination:viridian_center",
                (
                    StrategicNavigationTag.RECOVERY,
                    StrategicNavigationTag.SAFE_HUB,
                ),
                center_plan,
            ),
        )
        if plan.cost >= center_plan.cost:
            raise PalletViridianRouteProbeError(
                "home is no longer the lower-cost available safe hub"
            )
        strategic_choice = bind_strategic_navigation_decision(
            episode_id="pallet-safe-hub-calibration-2026-08-11",
            decision_index=0,
            root_lineage_id="pallet-safe-hub-diagnostic-root",
            partition="unassigned",
            actor="deterministic_teacher",
            policy_id="lowest-route-cost-safe-hub-v1",
            semantic_need_tags=(StrategicNavigationTag.RETURN_TO_SAFETY,),
            origin_semantic_tags=(StrategicNavigationTag.OVERWORLD,),
            origin_region_ref="pokemon.red:region:pallet",
            bindings=bindings,
            selected_destination_ref="pokemon.red:destination:pallet_home",
        )
    if not plan.steps:
        raise PalletViridianRouteProbeError("the composed route contains no movement")
    before_artifacts = _adjacent_artifacts(rom_path)

    timing = DEFAULT_PEWTER_TIMING
    with PyBoyAdapter(rom_path) as emulator:
        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        opening = run_opening_chapter(
            rom_path,
            _emulator=emulator,
            _executor=controller,
        )
        if not opening.passed:
            raise PalletViridianRouteProbeError("the qualified opening precondition failed")
        reader = PokemonRedStateReader(emulator)
        executor = CountingExecutor(controller)
        errand = run_oaks_errand_chapter(
            emulator,
            reader,
            executor,
            timing=DEFAULT_QUALIFIED_PLAY_TIMING,
        )
        if not errand.passed:
            raise PalletViridianRouteProbeError("the verified Pokédex precondition failed")

        _move(executor, reader, LAB_TO_PALLET_DIRECTIONS, "composed-route lab exit")
        _wait(executor, timing.transition_wait_frames)
        _expect_position(
            reader.read(),
            MapId.PALLET_TOWN,
            start_yx[1],
            start_yx[0],
            "composed-route Pallet start",
        )
        observer = Gen1TraversalObserver(reader)
        route_actions: CountingExecutor | FirstStepBlockerInjector = executor
        limits = RouteExecutionLimits(
            max_step_attempts=timing.max_route_1_step_attempts,
            max_interruptions=timing.max_route_1_wild_flees,
            replan_after_unchanged=2,
            retry_wait_frames=timing.route_1_step_retry_wait_frames,
            transition_settle_frames=timing.transition_wait_frames,
        )
        injected_blocker: FirstStepBlockerInjector | None = None
        if args.inject_first_step_blocker:
            first = plan.steps[0]
            injected_blocker = FirstStepBlockerInjector(
                executor,
                observer,
                TraversalSnapshot(first.source_map, first.source_at, True),
                first.action,
                limits.replan_after_unchanged,
            )
            route_actions = injected_blocker
        wild_handler = Gen1WildFleeHandler(
            route_actions,
            reader,
            maximum_flees=timing.max_route_1_wild_flees,
            stabilization_frames=timing.route_1_wild_exit_stabilization_frames,
            route_name="closed-loop Pallet-to-Viridian route",
        )

        def replan(request: ReplanRequest) -> RoutePlan:
            return plan_route(
                macro,
                local_graphs,
                request.current.map_id,
                request.current.at,
                request.goal_map,
                blocked=request.blocked,
            )

        actions_before_plan = executor.actions_executed
        report = execute_route(
            plan,
            route_actions,
            observer,
            interruption_handler=wild_handler,
            replanner=replan,
            limits=limits,
        )
        final = reader.read()
        plan_actions_executed = executor.actions_executed - actions_before_plan
        frames_executed = emulator.frame_count
        controller_released = not emulator.pressed_buttons

    artifacts_unchanged = before_artifacts == _adjacent_artifacts(rom_path)
    if not artifacts_unchanged:
        raise PalletViridianRouteProbeError(
            "the no-save probe changed a ROM-adjacent artifact"
        )
    final_map_id = final.map_id
    final_x = final.player_x
    final_y = final.player_y
    if final_map_id is None or final_x is None or final_y is None:
        raise PalletViridianRouteProbeError("the final route position is incomplete")

    strategic_payload = None
    if strategic_choice is not None:
        strategic_record = strategic_choice.successful_record(report)
        trajectory_decision = strategic_navigation_decision_record(
            strategic_record,
            SemanticSnapshot(
                game_id="pokemon.red",
                mode="overworld",
                facts=("need:return_to_safety",),
                features={"candidate_count": len(strategic_record.decision.candidates)},
            ),
            step_index=0,
        )
        trajectory_outcome = strategic_navigation_outcome_event(
            strategic_record,
            step_index=len(report.executed_steps),
        )
        strategic_payload = {
            "scope": "unassigned calibration; excluded from model development",
            "selection_rule": "lowest route cost among two available safe hubs",
            "record": strategic_record.public_dict(),
            "identity_free_trajectory_decision": trajectory_decision.to_dict(),
            "identity_free_trajectory_outcome": trajectory_outcome.to_dict(),
            "numeric_feature_schema_frozen": False,
            "promotion_eligible": False,
        }

    payload = {
        "schema": (
            "pallet-strategic-safe-hub-route-probe-v1"
            if strategic_payload is not None
            else "pallet-viridian-closed-loop-route-probe-v2"
        ),
        "recorded_on": args.recorded_on,
        "status": "ok",
        "rom": fingerprint.public_dict(),
        "source": source.public_dict(),
        "executable_source_bundle_sha256": source_bundle,
        "precondition": (
            "Qualified teachers established a clean-power-on post-Pokédex run and "
            "exited Oak's Lab to the verified Pallet coordinate (12, 12)."
        ),
        "authority_under_test": (
            "From the Pallet start onward, cartridge map headers, exact connection "
            "geometry, destination warp indices, terrain and traversal rules supplied "
            "the multi-map route. A game-neutral executor required live acknowledgement "
            "for every requested movement, bounded readiness and retries, delegated "
            "authenticated wild exits, and could replace its route around newly observed "
            "blockers."
        ),
        "destination": args.destination,
        "plan": _public_plan(plan),
        "execution": _public_execution(report),
        "fault_injection": {
            "enabled": args.inject_first_step_blocker,
            "kind": "suppressed movement requests" if injected_blocker else None,
            "source_map_id": plan.steps[0].source_map if injected_blocker else None,
            "source_yx": list(plan.steps[0].source_at) if injected_blocker else None,
            "blocked_yx": list(plan.steps[0].expected_at) if injected_blocker else None,
            "direction": plan.steps[0].action if injected_blocker else None,
            "suppressed_requests": injected_blocker.suppressed if injected_blocker else 0,
            "disclosure": (
                "Artificial fault for causal recovery testing; not a naturally observed NPC."
                if injected_blocker
                else None
            ),
        },
        "wild_flees": [flee.public_dict() for flee in wild_handler.evidence],
        "final_map": {"id": int(final_map_id), "name": MapId(final_map_id).name},
        "final_yx": [final_y, final_x],
        "planned_actions": len(plan.actions),
        "actions_executed_during_plan": plan_actions_executed,
        "frames_executed": frames_executed,
        "controller_released": controller_released,
        "rom_adjacent_artifacts_unchanged": artifacts_unchanged,
        "strategic_navigation": strategic_payload,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out}: {len(plan.actions)} initial actions, "
        f"{len(report.executed_steps)} acknowledged steps, "
        f"{len(report.replans)} replans, entered {destination.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
