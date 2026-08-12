#!/usr/bin/env python3
"""Preflight or execute one uncounted, authenticated strategic scenario.

The default mode is read-only: it reloads the exact private checkpoint, plans
every preregistered candidate, and reports whether the branch is executable.
Pass ``--execute`` only after that succeeds.  Execution creates one immutable
private episode and can never consume a train, validation, or test assignment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.actions import MacroAction  # noqa: E402
from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.captured_progress import (  # noqa: E402
    CapturedProgressError,
    load_captured_progress,
)
from pokemon_red_completion.cascade import (  # noqa: E402
    DEFAULT_CASCADE_TIMING,
    POTION_HEAL_AMOUNT,
    _bag_quantity,
    _use_battle_recovery_item,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    CollectionProtocolError,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import (  # noqa: E402
    EmulatorError,
    PyBoyAdapter,
)
from pokemon_red_completion.executor import (  # noqa: E402
    CountingExecutor,
    FrameSafeExecutor,
)
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
    ItemId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    PrivateArtifactError,
    open_private_root,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    EvaluationIdentityError,
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_player_observer import (  # noqa: E402
    CapturedPokemonRedObserver,
    ResumedStateError,
)
from pokemon_red_completion.red_trajectory import (  # noqa: E402
    POKEMON_CORE_ONTOLOGY_ID,
    POKEMON_RED_ADAPTER_ID,
    PokemonRedObservationEncoder,
)
from pokemon_red_completion.rom import (  # noqa: E402
    RomValidationError,
    resolve_rom_path,
    verify_rom,
)
from pokemon_red_completion.route import COMPLETION_QUEST  # noqa: E402
from pokemon_red_completion.route_evidence import (  # noqa: E402
    rom_adjacent_artifacts,
)
from pokemon_red_completion.route_executor import (  # noqa: E402
    RouteExecutionError,
    RouteExecutionLimits,
)
from pokemon_red_completion.runtime_identity import (  # noqa: E402
    RuntimeIdentity,
    RuntimeIdentityError,
    build_runtime_identity,
)
from pokemon_red_completion.strategic_navigation_dataset import (  # noqa: E402
    StrategicNavigationDatasetError,
)
from pokemon_red_completion.strategic_navigation_protocol import (  # noqa: E402
    StrategicNavigationProtocolError,
    StrategicNavigationScenarioRehearsalAssignment,
    load_committed_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (  # noqa: E402
    StrategicScenarioRouteCatalogError,
    require_scenario_origin,
    scenario_destination_specs,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (  # noqa: E402
    STRATEGIC_SCENARIO_MAXIMUM_FLEES,
    StrategicScenarioRouteWorld,
    StrategicScenarioRuntimeError,
    bind_scenario_interruption_limits,
    record_strategic_scenario_rehearsal,
    require_executable_scenario_bindings,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    StrategicScenarioProtocolError,
    load_strategic_navigation_scenario_registry,
)
from pokemon_red_completion.trajectory import RecordingExecutor  # noqa: E402

DEFAULT_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_readiness_waits=16,
    max_interruptions=16,
    max_replans=8,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    readiness_wait_frames=24,
    transition_settle_frames=180,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--envelope",
        type=Path,
        default=None,
        help="defaults to <state>.json",
    )
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="write and execute the uncounted one-shot rehearsal",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="show a view-only game window during execution",
    )
    parser.add_argument("--speed", type=int, choices=(1, 2, 4), default=None)
    parser.add_argument(
        "--maximum-flees",
        type=int,
        default=STRATEGIC_SCENARIO_MAXIMUM_FLEES,
    )
    parser.add_argument("--maximum-trainer-battles", type=int, default=8)
    return parser


def _metadata(
    *,
    assignment: StrategicNavigationScenarioRehearsalAssignment,
    objective_graph_sha256: str,
    rom_identity: Mapping[str, object],
    runtime: RuntimeIdentity,
    watch: bool,
    speed: int | None,
    maximum_flees: int,
    maximum_trainer_battles: int,
) -> dict[str, object]:
    metadata = dict(assignment.episode_metadata())
    runtime_public = runtime.public_dict()
    configuration = {
        "emulator": {
            "human_input": False,
            "save_on_exit": False,
            "speed": speed if watch else 0,
            "watch": watch,
        },
        "execution_mode": "one_choice_then_selected_approach",
        "maximum_flees": maximum_flees,
        "maximum_trainer_battles": maximum_trainer_battles,
        "scenario_rehearsal": True,
        "trajectory_reload_required": True,
    }
    metadata.update(
        {
            "adapter_id": POKEMON_RED_ADAPTER_ID,
            "configuration": configuration,
            "configuration_sha256": canonical_sha256(configuration),
            "objective_graph_sha256": objective_graph_sha256,
            "ontology_id": POKEMON_CORE_ONTOLOGY_ID,
            "rom_identity": dict(rom_identity),
            "runtime": runtime_public,
            "runtime_sha256": runtime.sha256,
        }
    )
    return metadata


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise StrategicScenarioRuntimeError("--speed requires --watch")
    if args.watch and not args.execute:
        raise StrategicScenarioRuntimeError("--watch requires --execute")
    if args.maximum_flees < 0 or args.maximum_trainer_battles < 0:
        raise StrategicScenarioRuntimeError("interruption budgets must be non-negative")

    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    execution_registry = load_committed_strategic_navigation_registry(PROJECT_ROOT)
    execution = execution_registry.execution
    if (
        source.git_commit != execution.source_commit
        or working_source_bundle_sha256(PROJECT_ROOT) != execution.source_bundle_sha256
    ):
        raise StrategicScenarioRuntimeError(
            "the executable source differs from the committed strategic execution"
        )
    scenario_registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = scenario_registry.scenario(args.scenario_id)

    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    state_path = args.state
    envelope_path = args.envelope or Path(f"{state_path}.json")
    capture = load_captured_progress(envelope_path, state_path=state_path)
    assignment = scenario_registry.rehearsal_assignment(
        scenario.scenario_id,
        capture=capture,
        execution=execution,
    )
    runtime = build_runtime_identity()
    metadata = _metadata(
        assignment=assignment,
        objective_graph_sha256=execution.objective_graph_sha256,
        rom_identity=fingerprint.public_dict(),
        runtime=runtime,
        watch=args.watch,
        speed=args.speed,
        maximum_flees=args.maximum_flees,
        maximum_trainer_battles=args.maximum_trainer_battles,
    )
    private_root = open_private_root(
        args.private_root,
        repository_root=PROJECT_ROOT,
    )
    state_sha256_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    adjacent_before = rom_adjacent_artifacts(rom_path)
    rom = rom_path.read_bytes()
    route_world = StrategicScenarioRouteWorld.from_rom(rom)
    specs = scenario_destination_specs(scenario_registry, scenario.scenario_id)

    with PyBoyAdapter(
        rom_path,
        watch=args.watch,
        speed=args.speed,
    ) as emulator:
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
                "scenario capture is not a stable ready overworld boundary"
            )
        require_scenario_origin(scenario, raw.map_id)
        CapturedPokemonRedObserver(reader, COMPLETION_QUEST, capture).observe()

        def field_capabilities(observed: RawGameState) -> frozenset[str]:
            capabilities = cut_capabilities(observed).union(
                strength_capabilities(observed)
            )
            permission = surf_permission(emulator, observed)
            return capabilities.union(
                surf_capabilities(
                    observed,
                    surf_allowed=permission.allowed,
                )
            )

        traversal_observer = Gen1TraversalObserver(
            reader,
            hazard_projector=Gen1TrainerSightProjector(rom, reader),
            capability_projector=field_capabilities,
        )
        start = traversal_observer.observe()
        bindings = route_world.plan_bindings(specs, start)
        selected = require_executable_scenario_bindings(scenario, specs, bindings)
        costs = [binding.plan.cost for binding in bindings if binding.plan is not None]
        preflight = {
            "schema": "strategic-navigation-scenario-preflight-v1",
            "status": "ready",
            "assignment_id": assignment.assignment_id,
            "counted": False,
            "partition": "unassigned",
            "scenario_id": scenario.scenario_id,
            "source_partition": scenario.partition,
            "candidate_count": len(bindings),
            "route_cost_min": min(costs),
            "route_cost_max": max(costs),
            "registry_teacher_ordinal": scenario.candidate_objective_ids.index(
                scenario.teacher_objective_id
            )
            + 1,
            "private_episode_exists": private_root.inspect_episode_state(
                assignment.episode_id
            ).status
            != "absent",
        }
        if not args.execute:
            return preflight

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

        def interruption_factory(
            recorder: RecordingExecutor[MacroAction, object],
        ) -> Gen1RouteInterruptionHandler:
            def recovery_required(raw: RawGameState) -> bool:
                return (
                    _bag_quantity(cast(Any, emulator), ItemId.POTION) > 0
                    and raw.first_party_hp is not None
                    and 0 < raw.first_party_hp <= 40
                )

            def recover() -> None:
                _use_battle_recovery_item(
                    reader,
                    cast(Any, recorder),
                    cast(Any, emulator),
                    DEFAULT_CASCADE_TIMING,
                    item=ItemId.POTION,
                    heal_amount=POTION_HEAL_AMOUNT,
                    max_quantity=99,
                    label="strategic route Potion",
                )

            return Gen1RouteInterruptionHandler(
                recorder,
                reader,
                maximum_flees=args.maximum_flees,
                maximum_trainer_battles=args.maximum_trainer_battles,
                stabilization_frames=120,
                route_name="authenticated strategic scenario approach",
                trainer_recovery_required=recovery_required,
                trainer_recovery_action=recover,
                maximum_trainer_recoveries=6,
            )

        result = record_strategic_scenario_rehearsal(
            private_root,
            assignment=assignment,
            scenario=scenario,
            metadata=metadata,
            snapshot_provider=PokemonRedObservationEncoder.from_state_reader(reader),
            action_delegate=field_actions,
            traversal_observer=traversal_observer,
            bindings=bindings,
            selected_destination_ref=selected,
            interruption_handler_factory=interruption_factory,
            replanner=route_world.replanner(),
            limits=bind_scenario_interruption_limits(
                DEFAULT_LIMITS,
                maximum_flees=args.maximum_flees,
                maximum_trainer_battles=args.maximum_trainer_battles,
            ),
        )

    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise StrategicScenarioRuntimeError("private capture state changed during rehearsal")
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise StrategicScenarioRuntimeError("rehearsal created a ROM-adjacent artifact")
    return {**preflight, "execution": result.public_dict()}


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
        PrivateArtifactError,
        ResumedStateError,
        RomValidationError,
        RouteExecutionError,
        RuntimeIdentityError,
        StrategicNavigationProtocolError,
        StrategicNavigationDatasetError,
        StrategicScenarioProtocolError,
        StrategicScenarioRouteCatalogError,
        StrategicScenarioRuntimeError,
        OSError,
    ):
        parser.error(
            "Strategic scenario rehearsal failed closed; private paths were withheld."
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
