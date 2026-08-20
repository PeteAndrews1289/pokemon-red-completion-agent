#!/usr/bin/env python3
"""Materialize one non-test scenario frontier through an observed navigation fact.

This is not a data-collection command.  It starts from an exact authenticated
scenario capture, preflights every source candidate, executes one explicitly
declared location-completing approach, verifies the target scenario's exact
objective frontier from live state, and writes a new private state/envelope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.captured_progress import (  # noqa: E402
    CapturedProgressError,
    load_captured_progress,
    write_captured_progress,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    CollectionProtocolError,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.gen1_cartridge import CartridgeReadError  # noqa: E402
from pokemon_red_completion.gen1_field_moves import (  # noqa: E402
    Gen1FieldMoveError,
    Gen1FieldMovePort,
    surf_permission,
)
from pokemon_red_completion.gen1_maps import map_graph  # noqa: E402
from pokemon_red_completion.gen1_route_runtime import (  # noqa: E402
    Gen1RouteInterruptionHandler,
    Gen1TraversalObserver,
)
from pokemon_red_completion.gen1_trainer_sight import (  # noqa: E402
    Gen1TrainerSightProjector,
)
from pokemon_red_completion.gen1_traversal import (  # noqa: E402
    cut_capabilities,
    strength_capabilities,
    surf_capabilities,
    traversal_rules,
)
from pokemon_red_completion.observation import (  # noqa: E402
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
    RouteExecutionError,
    RouteExecutionLimits,
    execute_route,
)
from pokemon_red_completion.runtime_identity import RuntimeIdentityError  # noqa: E402
from pokemon_red_completion.strategic_navigation_protocol import (  # noqa: E402
    StrategicNavigationProtocolError,
    load_committed_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (  # noqa: E402
    StrategicScenarioRouteCatalogError,
    require_navigation_materialization_step,
    require_scenario_origin,
    scenario_destination_specs,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (  # noqa: E402
    StrategicScenarioRouteWorld,
    StrategicScenarioRuntimeError,
    require_executable_scenario_bindings,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    StrategicScenarioProtocolError,
    load_strategic_navigation_scenario_registry,
)

DEFAULT_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_readiness_waits=16,
    max_interruptions=8,
    max_replans=8,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    readiness_wait_frames=24,
    transition_settle_frames=180,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-scenario-id", required=True)
    parser.add_argument("--target-scenario-id", required=True)
    parser.add_argument("--complete-objective-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--envelope",
        type=Path,
        default=None,
        help="defaults to <state>.json",
    )
    parser.add_argument("--out-state", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    parser.add_argument("--maximum-flees", type=int, default=8)
    parser.add_argument("--maximum-trainer-battles", type=int, default=8)
    return parser


def _require_private_new_output(destination: Path, rom_path: Path) -> Path:
    resolved = destination.resolve()
    envelope = Path(f"{resolved}.json")
    if resolved.is_relative_to(PROJECT_ROOT.resolve()):
        raise StrategicScenarioRuntimeError(
            "materialized capture must remain outside the repository"
        )
    if resolved.parent == rom_path.resolve().parent:
        raise StrategicScenarioRuntimeError(
            "materialized capture must not be written beside the ROM"
        )
    if not resolved.parent.is_dir():
        raise StrategicScenarioRuntimeError(
            "materialized capture parent directory does not exist"
        )
    if resolved.exists() or envelope.exists():
        raise StrategicScenarioRuntimeError(
            "materialized capture output already exists"
        )
    return resolved


def _materialized_checkpoint_id(target_scenario_id: str) -> str:
    return f"{target_scenario_id}-materialized"


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise StrategicScenarioRuntimeError("--speed requires --watch")
    if args.maximum_flees < 0 or args.maximum_trainer_battles < 0:
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

    scenario_registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    source_scenario = scenario_registry.scenario(args.source_scenario_id)
    target_scenario = scenario_registry.scenario(args.target_scenario_id)
    materialized_spec = require_navigation_materialization_step(
        source_scenario,
        target_scenario,
        args.complete_objective_id,
    )

    rom_path = resolve_rom_path(args.rom)
    verify_rom(rom_path)
    out_state = _require_private_new_output(args.out_state, rom_path)
    state_path = args.state.resolve()
    envelope_path = (args.envelope or Path(f"{state_path}.json")).resolve()
    capture = load_captured_progress(envelope_path, state_path=state_path)
    # This call is read-only.  It enforces exact source-frontier equality and
    # binds the capture to the current committed execution identity.
    source_assignment = scenario_registry.rehearsal_assignment(
        source_scenario.scenario_id,
        capture=capture,
        execution=execution,
    )

    state_sha256_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    adjacent_before = rom_adjacent_artifacts(rom_path)
    rom = rom_path.read_bytes()
    route_world = StrategicScenarioRouteWorld.from_rom(rom)
    specs = scenario_destination_specs(
        scenario_registry,
        source_scenario.scenario_id,
    )

    with PyBoyAdapter(rom_path, watch=args.watch, speed=args.speed) as emulator:
        emulator.load_state(state_path)
        reader = PokemonRedStateReader(emulator)
        raw = reader.read()
        if (
            not raw.game_started
            or raw.map_id is None
            or raw.player_y is None
            or raw.player_x is None
            or raw.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise StrategicScenarioRuntimeError(
                "source capture is not a stable ready overworld boundary"
            )
        require_scenario_origin(source_scenario, raw.map_id)
        semantic_observer = CapturedPokemonRedObserver(
            reader,
            COMPLETION_QUEST,
            capture,
        )
        initial_completed = COMPLETION_QUEST.completed_ids(semantic_observer.observe())
        if initial_completed != frozenset(source_scenario.completed_objective_ids):
            raise StrategicScenarioRuntimeError(
                "live source capture differs from its scenario frontier"
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
        bindings = route_world.plan_bindings(specs, traversal_observer.observe())
        require_executable_scenario_bindings(source_scenario, specs, bindings)
        selected_index = source_scenario.candidate_objective_ids.index(
            materialized_spec.objective_id
        )
        selected = bindings[selected_index]
        if selected.plan is None:  # pragma: no cover - guarded by preflight above
            raise StrategicScenarioRuntimeError(
                "materialized candidate lost its preflight plan"
            )

        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        counted = CountingExecutor(controller)
        rules = traversal_rules(rom, map_graph(rom))
        field_actions = Gen1FieldMovePort(
            counted,
            reader,
            emulator,
            cut_block_swaps={swap.before: swap.after for swap in rules.cut_block_swaps},
        )
        interruption_handler = Gen1RouteInterruptionHandler(
            counted,
            reader,
            maximum_flees=args.maximum_flees,
            maximum_trainer_battles=args.maximum_trainer_battles,
            stabilization_frames=120,
            route_name="strategic scenario capture materialization",
        )
        report = execute_route(
            selected.plan,
            field_actions,
            traversal_observer,
            interruption_handler=interruption_handler,
            replanner=route_world.replanner(),
            limits=DEFAULT_LIMITS,
        )

        final_raw = reader.read()
        if (
            final_raw.map_id is None
            or final_raw.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise StrategicScenarioRuntimeError(
                "materialized capture did not end at a stable ready boundary"
            )
        require_scenario_origin(target_scenario, final_raw.map_id)
        final_completed = COMPLETION_QUEST.completed_ids(semantic_observer.observe())
        if final_completed != frozenset(target_scenario.completed_objective_ids):
            raise StrategicScenarioRuntimeError(
                "materialized live frontier differs from the target scenario"
            )

        emulator.save_state(out_state)
        output_envelope = write_captured_progress(
            Path(f"{out_state}.json"),
            state_path=out_state,
            checkpoint_id=_materialized_checkpoint_id(target_scenario.scenario_id),
            checkpoint_label=(
                f"Materialized {target_scenario.scenario_id} by completing "
                f"{materialized_spec.objective_id}"
            ),
            checkpoints_completed=capture.checkpoints_completed,
            checkpoints_total=capture.checkpoints_total,
            verified_objective_ids=target_scenario.completed_objective_ids,
        )

    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise StrategicScenarioRuntimeError("source capture changed during materialization")
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise StrategicScenarioRuntimeError(
            "materialization created a ROM-adjacent artifact"
        )
    return {
        "schema": "strategic-navigation-scenario-materialization-v1",
        "status": "complete",
        "counted": False,
        "episode_created": False,
        "source_assignment_id": source_assignment.assignment_id,
        "source_scenario_id": source_scenario.scenario_id,
        "target_scenario_id": target_scenario.scenario_id,
        "completed_objective_id": materialized_spec.objective_id,
        "candidate_count": len(bindings),
        "route": {
            "planned_cost": selected.plan.cost,
            "acknowledged_steps": len(report.executed_steps),
            "movement_requests": report.movement_requests,
            "interruptions": len(report.interruptions),
            "replans": len(report.replans),
            "wait_actions": report.wait_actions,
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
        CartridgeReadError,
        CollectionProtocolError,
        EmulatorError,
        EvaluationIdentityError,
        Gen1FieldMoveError,
        ResumedStateError,
        RomValidationError,
        RouteExecutionError,
        RuntimeIdentityError,
        StrategicNavigationProtocolError,
        StrategicScenarioProtocolError,
        StrategicScenarioRouteCatalogError,
        StrategicScenarioRuntimeError,
        OSError,
    ):
        parser.error(
            "Strategic scenario materialization failed closed; private paths were withheld."
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
