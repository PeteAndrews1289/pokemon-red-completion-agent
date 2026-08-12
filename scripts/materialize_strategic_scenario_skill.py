#!/usr/bin/env python3
"""Materialize one non-test scenario or construction frontier with one skill.

This is not a data-collection command.  It may consume an authenticated
teacher capture whose frontier is not itself a learning scenario, but it never
opens that frontier as a policy context.  The command executes one explicitly
declared bounded skill, may explicitly relocate its stable terminal to a
declared target-origin map through the cartridge-derived router, verifies the
exact target frontier from fresh live state, and writes a new private
state/envelope without an episode or label.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
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
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    CollectionProtocolError,
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import EmulatorError, PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor  # noqa: E402
from pokemon_red_completion.gen1_field_moves import (  # noqa: E402
    Gen1FieldMovePort,
    surf_permission,
)
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
)
from pokemon_red_completion.objective_skills import ObjectiveSkillError  # noqa: E402
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
from pokemon_red_completion.red_objective_skills import (  # noqa: E402
    build_red_midgame_objective_skill_registry,
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
from pokemon_red_completion.strategic_navigation_protocol import (  # noqa: E402
    StrategicNavigationProtocolError,
    load_committed_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (  # noqa: E402
    STRATEGIC_OBJECTIVE_SKILL_BOUNDARIES,
    STRATEGIC_SCENARIO_ORIGIN_MAPS,
    StrategicScenarioRouteCatalogError,
    require_objective_skill_intermediate_step,
    require_objective_skill_materialization_step,
    require_scenario_origin,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (  # noqa: E402
    StrategicScenarioRouteWorld,
    StrategicScenarioRuntimeError,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    StrategicScenarioProtocolError,
    load_strategic_navigation_scenario_registry,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-scenario-id", required=True)
    parser.add_argument("--complete-objective-id", required=True)
    parser.add_argument(
        "--intermediate-toward-target",
        action="store_true",
        help=(
            "write a construction-only strict subset of the declared target "
            "instead of claiming the target scenario is complete"
        ),
    )
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
    parser.add_argument(
        "--relocate-to-skill-boundary",
        action="store_true",
        help=(
            "before the skill, execute one bounded cartridge-derived route to "
            "its declared exact input boundary when the source is elsewhere"
        ),
    )
    parser.add_argument(
        "--relocate-to-origin",
        action="store_true",
        help=(
            "after the skill, execute one bounded cartridge-derived route to the "
            "target scenario's declared origin"
        ),
    )
    return parser


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
    """Latch every construction-side semantic effect after controller input."""

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
    return f"{target_scenario_id}-skill-materialized"


def _intermediate_checkpoint_id(
    target_scenario_id: str,
    objective_id: str,
) -> str:
    return f"{target_scenario_id}-toward-{objective_id}-skill-materialized"


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise StrategicScenarioRuntimeError("--speed requires --watch")
    if args.intermediate_toward_target and args.relocate_to_origin:
        raise StrategicScenarioRuntimeError(
            "intermediate construction cannot claim the target scenario origin"
        )

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
    target_scenario = scenario_registry.scenario(args.target_scenario_id)
    objective = COMPLETION_QUEST.objective(args.complete_objective_id)

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
            or raw.player_y is None
            or raw.player_x is None
            or raw.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise StrategicScenarioRuntimeError(
                "source capture is not a stable ready overworld boundary"
            )
        semantic_observer = CapturedPokemonRedObserver(
            reader,
            COMPLETION_QUEST,
            capture,
        )
        before = semantic_observer.observe()
        initial_completed = COMPLETION_QUEST.completed_ids(before)
        if args.intermediate_toward_target:
            expected_added = require_objective_skill_intermediate_step(
                initial_completed,
                target_scenario,
                args.complete_objective_id,
            )
        else:
            expected_added = require_objective_skill_materialization_step(
                initial_completed,
                target_scenario,
                args.complete_objective_id,
            )
        expected_final = initial_completed.union(expected_added)

        controller = FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
        tracked_controller = _SemanticTrackingExecutor(
            controller,
            semantic_observer,
        )
        skills = build_red_midgame_objective_skill_registry(
            emulator,
            reader,
            tracked_controller,
        )
        skill = skills.require_for(objective)
        route_world = StrategicScenarioRouteWorld.from_rom(rom)
        counted = CountingExecutor(tracked_controller)
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

        def execute_relocation(
            plan: RoutePlan,
            *,
            route_name: str,
        ) -> RouteExecutionReport:
            interruption_handler = Gen1RouteInterruptionHandler(
                field_actions,
                reader,
                maximum_flees=8,
                maximum_trainer_battles=8,
                stabilization_frames=120,
                route_name=route_name,
            )
            return execute_route(
                plan,
                field_actions,
                traversal_observer,
                interruption_handler=interruption_handler,
                replanner=route_world.replanner(),
                limits=RELOCATION_LIMITS,
            )

        pre_skill_relocation_report = None
        availability = skill.availability(before)
        if not availability.executable and args.relocate_to_skill_boundary:
            boundary = STRATEGIC_OBJECTIVE_SKILL_BOUNDARIES.get(
                args.complete_objective_id
            )
            if boundary is None:
                raise StrategicScenarioRuntimeError(
                    "bounded objective has no declared construction boundary"
                )
            boundary_map, boundary_at = boundary
            pre_skill_relocation_report = execute_relocation(
                route_world.plan_to_map(
                    traversal_observer.observe(),
                    boundary_map.value,
                    goal_at=boundary_at,
                ),
                route_name="strategic scenario pre-skill relocation",
            )
            before = semantic_observer.observe()
            if COMPLETION_QUEST.completed_ids(before) != initial_completed:
                raise StrategicScenarioRuntimeError(
                    "pre-skill relocation changed the authenticated frontier"
                )
            availability = skill.availability(before)
        if not availability.executable:
            raise StrategicScenarioRuntimeError(
                "bounded objective skill is unavailable at the source boundary"
            )
        skill_report = skills.execute_bounded(skill)

        relocation_report = None
        after_skill = reader.read()
        if (
            after_skill.map_id is None
            or after_skill.player_y is None
            or after_skill.player_x is None
            or after_skill.battle_state != 0
            or not reader.read_input_readiness().ready
        ):
            raise StrategicScenarioRuntimeError(
                "bounded objective skill did not end at a stable ready boundary"
            )
        target_origin_maps = STRATEGIC_SCENARIO_ORIGIN_MAPS.get(
            target_scenario.origin_region
        )
        if not args.intermediate_toward_target and target_origin_maps is None:
            raise StrategicScenarioRuntimeError(
                "target scenario has no declared origin maps"
            )
        if (
            not args.intermediate_toward_target
            and target_origin_maps is not None
            and after_skill.map_id not in target_origin_maps
        ):
            if not args.relocate_to_origin:
                raise StrategicScenarioRuntimeError(
                    "bounded skill terminal differs from the target origin; "
                    "explicit relocation is required"
                )
            relocation_plan = route_world.plan_to_any_map(
                traversal_observer.observe(),
                frozenset(item.value for item in target_origin_maps),
            )
            relocation_report = execute_relocation(
                relocation_plan,
                route_name="strategic scenario post-skill relocation",
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
        if not args.intermediate_toward_target:
            require_scenario_origin(target_scenario, final_raw.map_id)
        final_completed = COMPLETION_QUEST.completed_ids(semantic_observer.observe())
        if final_completed != expected_final:
            raise StrategicScenarioRuntimeError(
                "materialized live frontier differs from the authorized result"
            )

        emulator.save_state(out_state)
        output_envelope = write_captured_progress(
            Path(f"{out_state}.json"),
            state_path=out_state,
            checkpoint_id=(
                _intermediate_checkpoint_id(
                    target_scenario.scenario_id,
                    args.complete_objective_id,
                )
                if args.intermediate_toward_target
                else _materialized_checkpoint_id(target_scenario.scenario_id)
            ),
            checkpoint_label=(
                f"Materialized {'toward ' if args.intermediate_toward_target else ''}"
                f"{target_scenario.scenario_id} by bounded skill "
                f"{args.complete_objective_id}"
            ),
            checkpoints_completed=capture.checkpoints_completed,
            checkpoints_total=capture.checkpoints_total,
            verified_objective_ids=tuple(sorted(expected_final)),
        )

    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise StrategicScenarioRuntimeError("source capture changed during materialization")
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise StrategicScenarioRuntimeError(
            "materialization created a ROM-adjacent artifact"
        )
    return {
        "schema": "strategic-navigation-scenario-skill-materialization-v1",
        "status": "complete",
        "counted": False,
        "episode_created": False,
        "source_registry_assignment_opened": False,
        "target_scenario_id": target_scenario.scenario_id,
        "target_scenario_exact": not args.intermediate_toward_target,
        "completed_objective_id": args.complete_objective_id,
        "expected_objectives_added": sorted(expected_added),
        "skill": {
            "actions_executed": skill_report.actions_executed,
            "frames_executed": skill_report.frames_executed,
        },
        "pre_skill_relocation": {
            "requested": args.relocate_to_skill_boundary,
            "performed": pre_skill_relocation_report is not None,
            "acknowledged_steps": (
                0
                if pre_skill_relocation_report is None
                else len(pre_skill_relocation_report.executed_steps)
            ),
            "interruptions": (
                0
                if pre_skill_relocation_report is None
                else len(pre_skill_relocation_report.interruptions)
            ),
            "movement_requests": (
                0
                if pre_skill_relocation_report is None
                else pre_skill_relocation_report.movement_requests
            ),
            "replans": (
                0
                if pre_skill_relocation_report is None
                else len(pre_skill_relocation_report.replans)
            ),
            "wait_actions": (
                0
                if pre_skill_relocation_report is None
                else pre_skill_relocation_report.wait_actions
            ),
        },
        "relocation": {
            "requested": args.relocate_to_origin,
            "performed": relocation_report is not None,
            "acknowledged_steps": (
                0
                if relocation_report is None
                else len(relocation_report.executed_steps)
            ),
            "interruptions": (
                0
                if relocation_report is None
                else len(relocation_report.interruptions)
            ),
            "movement_requests": (
                0
                if relocation_report is None
                else relocation_report.movement_requests
            ),
            "replans": (
                0 if relocation_report is None else len(relocation_report.replans)
            ),
            "wait_actions": (
                0 if relocation_report is None else relocation_report.wait_actions
            ),
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
        ObjectiveSkillError,
        ResumedStateError,
        RomValidationError,
        StrategicNavigationProtocolError,
        StrategicScenarioProtocolError,
        StrategicScenarioRouteCatalogError,
        StrategicScenarioRuntimeError,
        KeyError,
        OSError,
        RuntimeError,
    ):
        parser.error(
            "Strategic scenario skill materialization failed closed; private paths "
            "were withheld."
        )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
