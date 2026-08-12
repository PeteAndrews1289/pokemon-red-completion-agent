#!/usr/bin/env python3
"""Materialize one construction-only resource without opening a policy context.

Supported lessons collect Gold Teeth without HM03, acquire and teach HM02/Fly,
or recruit Jolteon without changing a completion objective.
Each preserves the source's verified completion objectives, writes a new
authenticated private capture, and never creates an episode or label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.actions import MacroAction  # noqa: E402
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.captured_progress import (  # noqa: E402
    CapturedProgressError,
    load_captured_progress,
    write_captured_progress,
)
from pokemon_red_completion.celadon import _bag  # noqa: E402
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    CollectionProtocolError,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.fly_resource import (  # noqa: E402
    FlyResourceError,
    FlyResourceReport,
    run_fly_resource_chapter,
)
from pokemon_red_completion.fuchsia import (  # noqa: E402
    SnorlaxResourceReport,
    run_snorlax_resource_chapter,
)
from pokemon_red_completion.gen1_field_moves import (  # noqa: E402
    Gen1FieldMovePort,
    surf_permission,
)
from pokemon_red_completion.gen1_route_runtime import (  # noqa: E402
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector  # noqa: E402
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    cut_capabilities,
    strength_capabilities,
    surf_capabilities,
)
from pokemon_red_completion.observation import (  # noqa: E402
    ItemId,
    MapId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    EvaluationIdentityError,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_player_observer import (  # noqa: E402
    CapturedPokemonRedObserver,
    ResumedStateError,
)
from pokemon_red_completion.rom import (  # noqa: E402
    RomValidationError,
    resolve_rom_path,
    verify_rom,
)
from pokemon_red_completion.route import COMPLETION_QUEST  # noqa: E402
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402
from pokemon_red_completion.route_executor import (  # noqa: E402
    RouteActionPort,
    RouteExecutionLimits,
    RouteExecutionReport,
    execute_route,
)
from pokemon_red_completion.route_plan import RoutePlan  # noqa: E402
from pokemon_red_completion.safari import (  # noqa: E402
    GoldTeethChapterReport,
    SafariChapterError,
    run_gold_teeth_chapter,
)
from pokemon_red_completion.saffron import (  # noqa: E402
    JolteonResourceReport,
    run_jolteon_resource_chapter,
)
from pokemon_red_completion.strategic_navigation_protocol import (  # noqa: E402
    StrategicNavigationProtocolError,
    load_committed_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (  # noqa: E402
    StrategicScenarioRouteWorld,
    StrategicScenarioRuntimeError,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    StrategicScenarioProtocolError,
    load_strategic_navigation_scenario_registry,
)

SUPPORTED_RESOURCE_IDS = ("fly", "gold_teeth", "jolteon", "snorlax")
RESOURCE_BOUNDARIES = {
    "fly": (MapId.CELADON_POKECENTER, (3, 3)),
    "gold_teeth": (MapId.FUCHSIA_POKECENTER, (3, 3)),
    "jolteon": (MapId.CELADON_POKECENTER, (3, 3)),
    "snorlax": (MapId.LAVENDER_POKECENTER, (3, 3)),
}
RELOCATION_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_readiness_waits=16,
    max_interruptions=8,
    max_replans=8,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    readiness_wait_frames=24,
    transition_settle_frames=180,
)


class _SemanticTrackingExecutor:
    def __init__(
        self,
        delegate: RouteActionPort,
        observer: CapturedPokemonRedObserver,
    ) -> None:
        self._delegate = delegate
        self._observer = observer

    def execute(self, action: MacroAction) -> object:
        result = self._delegate.execute(action)
        self._observer.observe()
        return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-scenario-id", required=True)
    parser.add_argument("--acquire-resource-id", choices=SUPPORTED_RESOURCE_IDS, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, default=None, help="defaults to <state>.json")
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    parser.add_argument("--maximum-flees", type=int, default=8)
    parser.add_argument("--maximum-trainer-battles", type=int, default=8)
    parser.add_argument("--maximum-interruptions", type=int, default=8)
    parser.add_argument(
        "--relocate-to-resource-boundary",
        action="store_true",
        help="execute one bounded cartridge-derived route to the lesson boundary",
    )
    return parser


def _at_resource_boundary(raw: RawGameState, resource_id: str) -> bool:
    map_id, coordinate = RESOURCE_BOUNDARIES[resource_id]
    exact = (
        raw.game_started
        and raw.map_id == map_id
        and (raw.player_x, raw.player_y) == coordinate
        and raw.battle_state == 0
    )
    return exact or (
        resource_id == "fly"
        and raw.game_started
        and raw.map_id == MapId.CELADON_CITY
        and (raw.player_x, raw.player_y) == (49, 11)
        and raw.battle_state == 0
    )


def _require_private_new_output(destination: Path, rom_path: Path) -> Path:
    resolved = destination.resolve()
    envelope = Path(f"{resolved}.json")
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise StrategicScenarioRuntimeError("resource capture must remain outside the repository")
    if resolved.parent == rom_path.resolve().parent:
        raise StrategicScenarioRuntimeError("resource capture must not be written beside the ROM")
    if not resolved.parent.is_dir():
        raise StrategicScenarioRuntimeError("resource capture parent directory does not exist")
    if resolved.exists() or envelope.exists():
        raise StrategicScenarioRuntimeError("resource capture output already exists")
    return resolved


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise StrategicScenarioRuntimeError("--speed requires --watch")
    if (
        args.maximum_flees < 0
        or args.maximum_trainer_battles < 0
        or args.maximum_interruptions < 0
    ):
        raise StrategicScenarioRuntimeError("interruption budgets must be non-negative")

    source_identity = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source_identity)
    require_published_source(PROJECT_ROOT, source_identity)
    execution = load_committed_strategic_navigation_registry(PROJECT_ROOT).execution
    if (
        source_identity.git_commit != execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT) != execution.source_bundle_sha256
    ):
        raise StrategicScenarioRuntimeError(
            "the executable source differs from the committed strategic execution"
        )

    registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    target = registry.scenario(args.target_scenario_id)
    if target.partition == "test":
        raise StrategicScenarioRuntimeError("resource construction cannot open a test scenario")

    rom_path = resolve_rom_path(args.rom)
    verify_rom(rom_path)
    rom = rom_path.read_bytes()
    out_state = _require_private_new_output(args.out_state, rom_path)
    state_path = args.state.resolve()
    envelope_path = (args.envelope or Path(f"{state_path}.json")).resolve()
    capture = load_captured_progress(envelope_path, state_path=state_path)
    state_sha256_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    adjacent_before = rom_adjacent_artifacts(rom_path)

    with PyBoyAdapter(rom_path, watch=args.watch, speed=args.speed) as emulator:
        emulator.load_state(state_path)
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        if (
            not raw.game_started
            or raw.map_id is None
            or raw.player_x is None
            or raw.player_y is None
            or raw.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise StrategicScenarioRuntimeError(
                "resource source is not a stable ready overworld boundary"
            )
        observer = CapturedPokemonRedObserver(reader, COMPLETION_QUEST, capture)
        before = observer.observe()
        completed_before = COMPLETION_QUEST.completed_ids(before)
        target_completed = frozenset(target.completed_objective_ids)
        if not completed_before < target_completed:
            raise StrategicScenarioRuntimeError(
                "resource source must be a strict subset of the target frontier"
            )
        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        tracked = _SemanticTrackingExecutor(controller, observer)
        route_world = StrategicScenarioRouteWorld.from_rom(rom)
        counted = CountingExecutor(tracked)
        field_actions = Gen1FieldMovePort(
            counted,
            reader,
            emulator,
            cut_block_swaps={
                swap.before: swap.after for swap in route_world.rules.cut_block_swaps
            },
        )

        def field_capabilities(observed: RawGameState) -> frozenset[str]:
            capabilities = cut_capabilities(observed).union(
                strength_capabilities(observed)
            )
            permission = surf_permission(emulator, observed)
            return capabilities.union(
                surf_capabilities(observed, surf_allowed=permission.allowed)
            )

        traversal_observer = Gen1TraversalObserver(
            reader,
            hazard_projector=Gen1TrainerSightProjector(rom, reader),
            capability_projector=field_capabilities,
        )

        def execute_relocation(plan: RoutePlan) -> RouteExecutionReport:
            interruption_handler = Gen1RouteInterruptionHandler(
                field_actions,
                reader,
                maximum_flees=args.maximum_flees,
                maximum_trainer_battles=args.maximum_trainer_battles,
                stabilization_frames=120,
                route_name="strategic resource pre-lesson relocation",
            )
            return execute_route(
                plan,
                field_actions,
                traversal_observer,
                interruption_handler=interruption_handler,
                replanner=route_world.replanner(),
                limits=replace(
                    RELOCATION_LIMITS,
                    max_interruptions=args.maximum_interruptions,
                ),
            )

        relocation_report = None
        if not _at_resource_boundary(raw, args.acquire_resource_id):
            if not args.relocate_to_resource_boundary:
                raise StrategicScenarioRuntimeError(
                    "resource source differs from the lesson boundary; "
                    "explicit relocation is required"
                )
            boundary_map, boundary_at = RESOURCE_BOUNDARIES[args.acquire_resource_id]
            relocation_report = execute_relocation(
                route_world.plan_to_map(
                    traversal_observer.observe(),
                    boundary_map.value,
                    goal_at=boundary_at,
                )
            )
            raw = reader.read()
            before = observer.observe()
            if COMPLETION_QUEST.completed_ids(before) != completed_before:
                raise StrategicScenarioRuntimeError(
                    "resource relocation changed the authenticated frontier"
                )
        if not _at_resource_boundary(raw, args.acquire_resource_id):
            raise StrategicScenarioRuntimeError(
                "resource relocation did not reach the exact lesson boundary"
            )
        if args.acquire_resource_id == "gold_teeth" and (
            "item:gold_teeth" in before.facts or "move:surf_available" in before.facts
        ):
            raise StrategicScenarioRuntimeError(
                "Gold Teeth resource source is not pristine or already contains Surf"
            )
        if args.acquire_resource_id == "fly" and ItemId.HM02_FLY in _bag(emulator):
            raise StrategicScenarioRuntimeError("Fly resource source already contains HM02")

        report: (
            GoldTeethChapterReport
            | FlyResourceReport
            | JolteonResourceReport
            | SnorlaxResourceReport
        )
        if args.acquire_resource_id == "gold_teeth":
            report = run_gold_teeth_chapter(emulator, reader, tracked)
            encounters_fled = report.encounters_fled
        elif args.acquire_resource_id == "jolteon":
            report = run_jolteon_resource_chapter(emulator, reader, tracked)
            encounters_fled = 0
        elif args.acquire_resource_id == "snorlax":
            report = run_snorlax_resource_chapter(emulator, reader, tracked)
            encounters_fled = 0
        else:
            report = run_fly_resource_chapter(emulator, reader, tracked)
            encounters_fled = report.wild_battles
        after = observer.observe()
        objectives_changed = COMPLETION_QUEST.completed_ids(after) != completed_before
        gold_teeth_failed = args.acquire_resource_id == "gold_teeth" and (
            "item:gold_teeth" not in after.facts
            or "move:surf_available" in after.facts
            or ItemId.HM03_SURF in _bag(emulator)
        )
        fly_failed = args.acquire_resource_id == "fly" and (
            ItemId.HM02_FLY not in _bag(emulator) or not report.passed
        )
        jolteon_failed = args.acquire_resource_id == "jolteon" and not report.passed
        snorlax_failed = args.acquire_resource_id == "snorlax" and not report.passed
        if (
            objectives_changed
            or gold_teeth_failed
            or fly_failed
            or jolteon_failed
            or snorlax_failed
        ):
            raise StrategicScenarioRuntimeError(
                "resource lesson changed objectives or failed its acquisition contract"
            )
        final = reader.read()
        expected_terminal = {
            "fly": (MapId.CELADON_POKECENTER, (3, 3)),
            "gold_teeth": (MapId.FUCHSIA_POKECENTER, (3, 3)),
            "jolteon": (MapId.CELADON_CITY, (10, 14)),
            "snorlax": (MapId.LAVENDER_POKECENTER, (3, 3)),
        }[args.acquire_resource_id]
        if (
            final.map_id != expected_terminal[0]
            or (final.player_x, final.player_y) != expected_terminal[1]
            or final.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise StrategicScenarioRuntimeError(
                "resource lesson did not end at its stable boundary"
            )

        emulator.save_state(out_state)
        output_envelope = write_captured_progress(
            Path(f"{out_state}.json"),
            state_path=out_state,
            checkpoint_id=(
                f"{target.scenario_id}-toward-{args.acquire_resource_id}-resource-materialized"
            ),
            checkpoint_label=(
                f"Materialized {args.acquire_resource_id} toward {target.scenario_id} "
                "without an objective label"
            ),
            checkpoints_completed=capture.checkpoints_completed,
            checkpoints_total=capture.checkpoints_total,
            verified_objective_ids=tuple(sorted(completed_before)),
        )

    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise StrategicScenarioRuntimeError(
            "source capture changed during resource materialization"
        )
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise StrategicScenarioRuntimeError(
            "resource materialization created a ROM-adjacent artifact"
        )
    return {
        "schema": "strategic-navigation-resource-skill-materialization-v1",
        "status": "complete",
        "resource_id": args.acquire_resource_id,
        "target_scenario_id": target.scenario_id,
        "target_scenario_exact": False,
        "counted": False,
        "episode_created": False,
        "source_registry_assignment_opened": False,
        "verified_objectives_added": [],
        "surf_objective_added": False,
        "pre_resource_relocation": {
            "requested": args.relocate_to_resource_boundary,
            "performed": relocation_report is not None,
            "acknowledged_steps": (
                0 if relocation_report is None else len(relocation_report.executed_steps)
            ),
            "interruptions": (
                0 if relocation_report is None else len(relocation_report.interruptions)
            ),
            "movement_requests": (
                0 if relocation_report is None else relocation_report.movement_requests
            ),
            "replans": 0 if relocation_report is None else len(relocation_report.replans),
            "wait_actions": (
                0 if relocation_report is None else relocation_report.wait_actions
            ),
        },
        "skill": {
            "actions_executed": report.actions_executed,
            "frames_executed": report.frames_executed,
            "encounters_fled": encounters_fled,
        },
        "capture": {
            "checkpoint_id": output_envelope.checkpoint_id,
            "state_sha256": output_envelope.state_sha256,
            "verified_objective_count": len(output_envelope.verified_objective_ids),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        payload = _run(args)
    except (
        CapturedProgressError,
        CollectionProtocolError,
        EmulatorError,
        EvaluationIdentityError,
        FlyResourceError,
        OSError,
        ResumedStateError,
        RomValidationError,
        SafariChapterError,
        StrategicNavigationProtocolError,
        StrategicScenarioProtocolError,
        StrategicScenarioRuntimeError,
        ValueError,
    ):
        parser.error(
            "Strategic resource materialization failed closed; private paths were withheld."
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
