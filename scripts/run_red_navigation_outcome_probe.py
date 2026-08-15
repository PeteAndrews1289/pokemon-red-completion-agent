#!/usr/bin/env python3
"""Preflight or execute the frozen same-terminal Red navigation outcome probe."""

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
    CapturedProgressEnvelope,
    load_captured_progress,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import (  # noqa: E402
    CountingExecutor,
    FrameSafeExecutor,
)
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
from pokemon_red_completion.observation import (  # noqa: E402
    MapId,
    PokemonRedStateReader,
    RawGameState,
)
from pokemon_red_completion.private_artifacts import open_private_root  # noqa: E402
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_navigation_outcome_probe import (  # noqa: E402
    RED_LOCAL_NAVIGATION_ORDER_RULE,
    RED_LOCAL_NAVIGATION_SCENARIO_ID,
    SameDestinationNavigationQuestion,
    build_same_destination_navigation_question,
)
from pokemon_red_completion.rom import (  # noqa: E402
    resolve_rom_path,
    verify_rom,
)
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402
from pokemon_red_completion.route_executor import (  # noqa: E402
    RouteExecutionError,
    RouteExecutionLimits,
    TraversalSnapshot,
    execute_route,
)
from pokemon_red_completion.scenario_lab import ScenarioPartition  # noqa: E402
from pokemon_red_completion.scenario_outcome_adapters import (  # noqa: E402
    NAVIGATION_ROUTE_OBJECTIVE,
    NavigationOutcomeTrial,
    adapt_navigation_outcomes,
)
from pokemon_red_completion.strategic_navigation_binding import (  # noqa: E402
    BoundStrategicNavigationDecision,
)
from pokemon_red_completion.strategic_navigation_protocol import (  # noqa: E402
    load_committed_strategic_navigation_registry,
)
from pokemon_red_completion.strategic_navigation_scenario_routes import (  # noqa: E402
    require_scenario_origin,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (  # noqa: E402
    StrategicScenarioRouteWorld,
)
from pokemon_red_completion.strategic_navigation_scenarios import (  # noqa: E402
    load_strategic_navigation_scenario_registry,
)

PLAN_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-local-navigation-outcome-plan-2026-08-14.json"
)
SOURCE_SCENARIO_ID = "red-strategic-scenario-v2-001-train"
DEFAULT_LIMITS = RouteExecutionLimits(
    max_step_attempts=8,
    max_readiness_waits=16,
    max_interruptions=1,
    max_replans=4,
    replan_after_unchanged=2,
    retry_wait_frames=24,
    readiness_wait_frames=24,
    transition_settle_frames=180,
)


class RedNavigationOutcomeRunError(RuntimeError):
    """Raised before this one-shot probe can misstate or repeat evidence."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument(
        "--envelope",
        type=Path,
        default=None,
        help="defaults to <state>.json",
    )
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, default=None)
    parser.add_argument("--exact-ci-run", type=int, default=None)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="consume the deterministic one-shot private artifact",
    )
    return parser


def _load_plan() -> tuple[dict[str, object], str]:
    payload = PLAN_PATH.read_bytes()
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RedNavigationOutcomeRunError("navigation plan is invalid") from error
    if not isinstance(value, dict):
        raise RedNavigationOutcomeRunError("navigation plan is not an object")
    if (
        value.get("schema") != "pokemon-red-local-navigation-outcome-plan-v1"
        or value.get("status") != "prospective_unexecuted"
        or value.get("experiment_id") != RED_LOCAL_NAVIGATION_SCENARIO_ID
    ):
        raise RedNavigationOutcomeRunError("navigation plan identity is unsupported")
    objective = _mapping(value, "outcome_objective")
    if (
        objective.get("objective_id") != NAVIGATION_ROUTE_OBJECTIVE.objective_id
        or objective.get("objective_sha256")
        != NAVIGATION_ROUTE_OBJECTIVE.objective_sha256
    ):
        raise RedNavigationOutcomeRunError("navigation objective differs from its plan")
    construction = _mapping(value, "candidate_construction")
    if construction.get("candidate_order_rule") != RED_LOCAL_NAVIGATION_ORDER_RULE:
        raise RedNavigationOutcomeRunError("navigation candidate order rule drifted")
    return value, hashlib.sha256(payload).hexdigest()


def _mapping(source: dict[str, object], key: str) -> dict[str, object]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise RedNavigationOutcomeRunError(f"navigation plan {key} is invalid")
    return value


def _observer(
    rom: bytes,
    emulator: PyBoyAdapter,
) -> tuple[PokemonRedStateReader, Gen1TraversalObserver]:
    reader = PokemonRedStateReader(emulator)

    def field_capabilities(observed: RawGameState) -> frozenset[str]:
        permission = surf_permission(emulator, observed)
        return cut_capabilities(observed).union(
            strength_capabilities(observed)
        ).union(
            surf_capabilities(
                observed,
                surf_allowed=permission.allowed,
            )
        )

    return reader, Gen1TraversalObserver(
        reader,
        hazard_projector=Gen1TrainerSightProjector(rom, reader),
        capability_projector=field_capabilities,
    )


def _stable_start(
    reader: PokemonRedStateReader,
    observer: Gen1TraversalObserver,
) -> TraversalSnapshot:
    raw = reader.read()
    if (
        not raw.game_started
        or raw.map_id is None
        or raw.player_y is None
        or raw.player_x is None
        or raw.battle_state != 0
        or not reader.read_input_readiness().ready
    ):
        raise RedNavigationOutcomeRunError(
            "navigation capture is not a stable ready overworld boundary"
        )
    return observer.observe()


def _require_materialized_question(
    plan: dict[str, object],
    question: SameDestinationNavigationQuestion,
) -> None:
    construction = _mapping(plan, "candidate_construction")
    shortest = _mapping(construction, "shortest_route")
    detour = _mapping(construction, "detour_route")
    pair = question.route_pair
    observed = (
        pair.shortest.cost,
        len(pair.shortest.steps),
        pair.detour.cost,
        len(pair.detour.steps),
        pair.excluded_step_ordinal,
        question.shortest_candidate_index,
    )
    expected = (
        shortest.get("route_cost"),
        shortest.get("route_steps"),
        detour.get("route_cost"),
        detour.get("route_steps"),
        detour.get("excluded_shortest_step_ordinal"),
        construction.get("expected_shortest_candidate_index"),
    )
    if observed != expected:
        raise RedNavigationOutcomeRunError(
            "navigation route candidates differ from the prospective plan"
        )


def _execute_candidate(
    *,
    candidate_index: int,
    question: SameDestinationNavigationQuestion,
    episode_id: str,
    root_lineage_id: str,
    expected_start: TraversalSnapshot,
    rom: bytes,
    rom_path: Path,
    state_path: Path,
    route_world: StrategicScenarioRouteWorld,
) -> tuple[NavigationOutcomeTrial, dict[str, object]]:
    decision = question.decision(
        candidate_index,
        episode_id=episode_id,
        root_lineage_id=root_lineage_id,
    )
    plan = question.plans[candidate_index]
    bound = BoundStrategicNavigationDecision(decision, plan)
    with PyBoyAdapter(rom_path) as emulator:
        emulator.load_state(state_path)
        reader, observer = _observer(rom, emulator)
        if _stable_start(reader, observer) != expected_start:
            raise RedNavigationOutcomeRunError(
                "navigation clone does not match the frozen starting observation"
            )
        controller = CountingExecutor(
            FrameSafeExecutor(
                emulator,
                DEFAULT_NEW_GAME_TIMING.controller_timing(),
            )
        )
        field_actions = Gen1FieldMovePort(
            controller,
            reader,
            emulator,
            cut_block_swaps={
                swap.before: swap.after for swap in route_world.rules.cut_block_swaps
            },
        )
        interruption_handler = Gen1RouteInterruptionHandler(
            field_actions,
            reader,
            maximum_flees=0,
            maximum_trainer_battles=0,
            stabilization_frames=120,
            route_name="same-terminal navigation outcome probe",
        )
        try:
            report = execute_route(
                plan,
                field_actions,
                observer,
                interruption_handler=interruption_handler,
                replanner=route_world.replanner(),
                limits=DEFAULT_LIMITS,
            )
        except RouteExecutionError as error:
            if error.failure is None:
                raise RedNavigationOutcomeRunError(
                    "navigation failure lacks typed partial evidence"
                ) from error
            record = bound.failed_route_record(error.failure)
        else:
            record = bound.successful_record(report)
        trial = NavigationOutcomeTrial(
            record.decision,
            record.outcome,
            frames_executed=emulator.frame_count,
        )
        retained = {
            "record_type": "same_destination_navigation_trial",
            "candidate_index": candidate_index,
            "decision_id": decision.decision_id,
            "record": record.public_dict(),
            "frames_executed": emulator.frame_count,
            "controller_actions": controller.actions_executed,
            "teacher_queries": 0,
            "teacher_choice_targets": 0,
        }
    return trial, retained


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.execute and (args.private_root is None or args.exact_ci_run is None):
        raise RedNavigationOutcomeRunError(
            "execution requires a private root and exact green CI run identity"
        )
    if args.exact_ci_run is not None and (
        type(args.exact_ci_run) is not int or args.exact_ci_run <= 0  # noqa: E721
    ):
        raise RedNavigationOutcomeRunError("exact CI run identity is invalid")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:  # pragma: no cover - clean source establishes this
        raise AssertionError("clean source identity lacks a commit")
    plan, plan_sha256 = _load_plan()
    authenticated = _mapping(plan, "authenticated_root")
    state_path = args.state
    envelope_path = args.envelope or Path(f"{state_path}.json")
    state_sha256_before = hashlib.sha256(state_path.read_bytes()).hexdigest()
    envelope_sha256_before = hashlib.sha256(envelope_path.read_bytes()).hexdigest()
    capture: CapturedProgressEnvelope = load_captured_progress(
        envelope_path,
        state_path=state_path,
    )
    if (
        capture.state_sha256 != authenticated.get("state_sha256")
        or envelope_sha256_before != authenticated.get("capture_envelope_sha256")
    ):
        raise RedNavigationOutcomeRunError(
            "navigation capture differs from the prospectively frozen root"
        )
    execution_registry = load_committed_strategic_navigation_registry(PROJECT_ROOT)
    if working_source_bundle_sha256(PROJECT_ROOT) != (
        execution_registry.execution.source_bundle_sha256
    ):
        raise RedNavigationOutcomeRunError(
            "navigation source differs from its committed execution registry"
        )
    scenario_registry = load_strategic_navigation_scenario_registry(PROJECT_ROOT)
    scenario = scenario_registry.scenario(SOURCE_SCENARIO_ID)
    source_assignment = scenario_registry.rehearsal_assignment(
        SOURCE_SCENARIO_ID,
        capture=capture,
        execution=execution_registry.execution,
    )
    rom_path = resolve_rom_path(args.rom)
    fingerprint = verify_rom(rom_path)
    if fingerprint.sha256 != authenticated.get("rom_sha256"):
        raise RedNavigationOutcomeRunError("navigation ROM differs from its plan")
    adjacent_before = rom_adjacent_artifacts(rom_path)
    rom = rom_path.read_bytes()
    route_world = StrategicScenarioRouteWorld.from_rom(rom)
    with PyBoyAdapter(rom_path) as emulator:
        emulator.load_state(state_path)
        reader, observer = _observer(rom, emulator)
        start = _stable_start(reader, observer)
        require_scenario_origin(scenario, start.map_id)
    route_pair = route_world.plan_same_destination_pair(
        start,
        MapId.CERULEAN_GYM.value,
    )
    question = build_same_destination_navigation_question(
        route_pair,
        initial_state_sha256=capture.state_sha256,
    )
    _require_materialized_question(plan, question)
    catalog = question.public_catalog()
    preflight = {
        "schema": "pokemon-red-local-navigation-outcome-preflight-v1",
        "status": "ready",
        "source_commit": source.git_commit,
        "source_bundle_sha256": execution_registry.execution.source_bundle_sha256,
        "public_plan_sha256": plan_sha256,
        "source_assignment_id": source_assignment.assignment_id,
        "catalog": catalog,
        "objective_id": NAVIGATION_ROUTE_OBJECTIVE.objective_id,
        "objective_sha256": NAVIGATION_ROUTE_OBJECTIVE.objective_sha256,
        "teacher_queries": 0,
        "teacher_choice_targets": 0,
        "red_sealed_test_cases_opened": 0,
        "crystal_contexts_opened": 0,
        "full_game_replays": 0,
        "private_path_fields": 0,
    }
    if not args.execute:
        return preflight

    artifact_id = (
        f"red-local-nav-outcome-{source.git_commit[:12]}-"
        f"{capture.state_sha256[:12]}"
    )
    root_lineage_id = f"red-local-nav-root-{capture.state_sha256[:16]}"
    private_root = open_private_root(
        args.private_root,
        repository_root=PROJECT_ROOT,
    )
    writer = private_root.begin_artifact(
        artifact_id,
        kind="navigation_outcome_probe",
    )
    trials: list[NavigationOutcomeTrial] = []
    with writer:
        writer.append(
            "catalog",
            {
                "record_type": "same_destination_navigation_catalog",
                "source": source.public_dict(),
                "exact_ci_run": args.exact_ci_run,
                "public_plan_sha256": plan_sha256,
                "source_assignment_id": source_assignment.assignment_id,
                "catalog": catalog,
                "catalog_sha256": canonical_sha256(catalog),
                "private_route_bindings": {
                    "terminal_map": route_pair.shortest.terminal_map,
                    "terminal_at": list(route_pair.shortest.terminal_at),
                    "excluded_map": route_pair.excluded_map,
                    "excluded_at": list(route_pair.excluded_at),
                    "excluded_step_ordinal": route_pair.excluded_step_ordinal,
                    "ordered_action_sha256": [
                        canonical_sha256({"actions": list(item.actions)})
                        for item in question.plans
                    ],
                },
                "teacher_queries": 0,
                "teacher_choice_targets": 0,
            },
        )
        for candidate_index in range(2):
            trial, retained = _execute_candidate(
                candidate_index=candidate_index,
                question=question,
                episode_id=artifact_id,
                root_lineage_id=root_lineage_id,
                expected_start=start,
                rom=rom,
                rom_path=rom_path,
                state_path=state_path,
                route_world=route_world,
            )
            writer.append("trials", retained)
            trials.append(trial)
        example = adapt_navigation_outcomes(
            question.inference,
            tuple(trials),
            scenario_id=RED_LOCAL_NAVIGATION_SCENARIO_ID,
            root_lineage_id=root_lineage_id,
            initial_state_sha256=capture.state_sha256,
            partition=ScenarioPartition.TRAIN,
        )
        writer.append(
            "outcomes",
            {
                "record_type": "same_destination_navigation_outcome_example",
                "example": example.public_dict(),
                "learner_update_eligible": example.learner_update_eligible,
                "best_candidate_indices": list(example.best_candidate_indices),
                "authority": "shadow_only",
            },
        )
    if hashlib.sha256(state_path.read_bytes()).hexdigest() != state_sha256_before:
        raise RedNavigationOutcomeRunError("navigation capture changed during execution")
    if hashlib.sha256(envelope_path.read_bytes()).hexdigest() != envelope_sha256_before:
        raise RedNavigationOutcomeRunError("navigation envelope changed during execution")
    if rom_adjacent_artifacts(rom_path) != adjacent_before:
        raise RedNavigationOutcomeRunError(
            "navigation execution created a ROM-adjacent artifact"
        )
    trial_summaries = [
        {
            "candidate_index": trial.candidate_index,
            "status": trial.outcome.status.value,
            "terminal_reached": trial.outcome.terminal_reached,
            "movement_requests": trial.outcome.movement_requests,
            "acknowledged_steps": trial.outcome.acknowledged_steps,
            "wait_actions": trial.outcome.wait_actions,
            "replans": len(trial.outcome.replans),
            "interruptions": len(trial.outcome.interruptions),
            "frames_executed": trial.frames_executed,
        }
        for trial in trials
    ]
    return {
        **preflight,
        "schema": "pokemon-red-local-navigation-outcome-receipt-v1",
        "status": "complete",
        "exact_ci_run": args.exact_ci_run,
        "artifact": writer.summary.public_dict(),
        "trials": trial_summaries,
        "fully_measured": example.fully_measured,
        "learner_update_eligible": example.learner_update_eligible,
        "best_candidate_indices": list(example.best_candidate_indices),
        "target_distribution": example.target_distribution.tolist(),
        "model_fit": False,
        "authority_promoted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        payload = _run(args)
    except Exception as error:
        if isinstance(error, KeyboardInterrupt):  # pragma: no cover
            raise
        parser.error(
            "Red navigation outcome probe failed closed; private paths were withheld. "
            f"Failure type: {type(error).__name__}."
        )
    print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
