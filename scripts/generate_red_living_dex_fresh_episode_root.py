#!/usr/bin/env python3
"""Generate exactly one preregistered Red root from uninterrupted clean power.

This is a one-shot private execution surface.  It authenticates a published
13-episode plan, durably consumes one assignment before any emulator frame,
runs the deterministic setup teacher only through the post-Mansion frontier,
conditions the declared menu in that same emulator episode, saves once, and
verifies menu compatibility without controller input.  It never fits, scores,
or evaluates a model and never publishes ROM-derived bytes.
"""

# ruff: noqa: E402 -- establish reviewed script roots before project imports.

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Never, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
SRC_ROOT = PROJECT_ROOT / "src"
for root in (SCRIPTS_ROOT, SRC_ROOT):
    while str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

MATERIALIZER_PATH = SCRIPTS_ROOT / "materialize_goal_manager_context.py"
GENERATOR_PATH = Path(__file__).resolve()
CAPACITY_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "docs/evidence/red-living-dex-causal-capacity-census-v1-2026-08-28.json"
)
_MATERIALIZER: dict[str, Any] | None = None
_MATERIALIZER_SHA256: str | None = None

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import (
    working_source_bundle_sha256,
)
from pokemon_red_completion.constants import POKEMON_RED_US_REV_0
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import CountingExecutor, FrameSafeExecutor
from pokemon_red_completion.gen1_field_moves import gen1_field_capabilities
from pokemon_red_completion.gen1_route_runtime import Gen1TraversalObserver
from pokemon_red_completion.gen1_trainer_sight import Gen1TrainerSightProjector
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    root_claim_is_available,
)
from pokemon_red_completion.living_dex_option_value import (
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.play import (
    QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS,
    QualifiedPlayProgress,
    run_qualified_play,
)
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.provenance import (
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_manager import PokemonRedGoalStateAdapter
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_episode_lineage import (
    RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID,
    RedLivingDexFreshEpisodeAssignment,
    RedLivingDexFreshEpisodeFailureReceipt,
    compose_red_living_dex_fresh_episode_generator_execution_sha256,
    compose_red_living_dex_fresh_episode_teacher_execution_sha256,
    parse_red_living_dex_fresh_episode_plan,
)
from pokemon_red_completion.red_living_dex_fresh_episode_runtime import (
    CleanPowerFreshEpisodeEmulator,
    RedLivingDexFreshEpisodeCheckpoint,
    RedLivingDexFreshEpisodeExecutionFailure,
    RedLivingDexFreshEpisodeTargetVerification,
    execute_red_living_dex_fresh_episode,
    issue_red_living_dex_fresh_episode_process_authority,
    read_red_living_dex_fresh_episode_assignment_claim,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    RedLivingDexActionFreeRootObservation,
    RedLivingDexProviderPlanError,
    build_red_living_dex_provider_recipe_for_action_free_root,
    derive_red_living_dex_provider_corridors,
    observe_red_living_dex_provider_root_facts,
)
from pokemon_red_completion.red_living_dex_setup_recipe import (
    RedLivingDexAuthenticatedSetupRoot,
)
from pokemon_red_completion.red_player_observer import LivePokemonRedObserver
from pokemon_red_completion.rom import resolve_rom_path, verify_rom_bytes
from pokemon_red_completion.route import COMPLETION_QUEST
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts
from pokemon_red_completion.runtime_identity import (
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.strategic_navigation_scenario_runtime import (
    StrategicScenarioRouteWorld,
)

_MAXIMUM_PLAN_BYTES = 512 * 1024
_MAXIMUM_EVIDENCE_BYTES = 512 * 1024


class FreshEpisodeGeneratorError(RuntimeError):
    """A sanitized execution stage failed closed."""

    def __init__(
        self,
        stage: str,
        failure_receipt: RedLivingDexFreshEpisodeFailureReceipt | None = None,
    ) -> None:
        self.stage = stage
        self.failure_receipt = failure_receipt
        super().__init__(stage)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise FreshEpisodeGeneratorError("arguments")


class _TeacherCheckpointReached(Exception):
    def __init__(self, checkpoint: RedLivingDexFreshEpisodeCheckpoint) -> None:
        self.checkpoint = checkpoint
        super().__init__(checkpoint.checkpoint_id)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--assignment-id", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-generator-execution-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int, choices=(1, 2, 4))
    return parser


def _read_bounded(path: Path, maximum_bytes: int) -> bytes:
    try:
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not path.is_file()
            or not 0 < metadata.st_size <= maximum_bytes
        ):
            raise OSError("unsafe input")
        payload = path.read_bytes()
    except OSError:
        raise FreshEpisodeGeneratorError("artifact_authentication") from None
    if len(payload) != metadata.st_size:
        raise FreshEpisodeGeneratorError("artifact_authentication")
    return payload


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _known_runtime_effects(
    error: BaseException,
) -> tuple[bool, int | None, int | None]:
    if not isinstance(error, RedLivingDexFreshEpisodeExecutionFailure):
        return False, None, None
    return (
        error.effects_known,
        error.controller_actions,
        error.emulator_frames,
    )


def _generator_execution_sha256(source_bundle_sha256: str) -> str:
    return _generator_execution_binding(source_bundle_sha256)[0]


def _generator_execution_binding(
    source_bundle_sha256: str,
) -> tuple[str, str, str]:
    runner_sha256 = _sha256_file(GENERATOR_PATH)
    conditioner_sha256 = _sha256_file(MATERIALIZER_PATH)
    return compose_red_living_dex_fresh_episode_generator_execution_sha256(
        source_bundle_sha256=source_bundle_sha256,
        generator_runner_sha256=runner_sha256,
        conditioner_runner_sha256=conditioner_sha256,
    ), runner_sha256, conditioner_sha256


def _load_materializer(expected_sha256: str) -> dict[str, Any]:
    """Execute the exact authenticated conditioner bytes after authentication."""

    global _MATERIALIZER, _MATERIALIZER_SHA256
    if _MATERIALIZER is None:
        payload = _read_bounded(MATERIALIZER_PATH, 2 * 1024 * 1024)
        observed_sha256 = hashlib.sha256(payload).hexdigest()
        if observed_sha256 != expected_sha256:
            raise FreshEpisodeGeneratorError("conditioner_authentication")
        namespace: dict[str, Any] = {
            "__file__": str(MATERIALIZER_PATH),
            "__name__": "red_living_dex_fresh_episode_conditioner",
            "__package__": None,
        }
        exec(compile(payload, str(MATERIALIZER_PATH), "exec"), namespace)
        _MATERIALIZER = namespace
        _MATERIALIZER_SHA256 = observed_sha256
    elif expected_sha256 != _MATERIALIZER_SHA256:
        raise FreshEpisodeGeneratorError("conditioner_authentication")
    return _MATERIALIZER


def _verified_objectives(completed: int) -> tuple[str, ...]:
    return tuple(
        objective_id
        for checkpoint, objective_id in QUALIFIED_OBJECTIVE_COMPLETION_CHECKPOINTS
        if checkpoint <= completed
    )


def _latch_verified_progress(
    observer: LivePokemonRedObserver,
    checkpoint: RedLivingDexFreshEpisodeCheckpoint,
) -> None:
    observer.latch_verified_facts(
        frozenset(
            fact
            for objective_id in checkpoint.verified_objective_ids
            for fact in COMPLETION_QUEST.objective(objective_id).completion_facts
        )
    )


def _apply_target_conditioning(
    emulator: CleanPowerFreshEpisodeEmulator,
    assignment: RedLivingDexFreshEpisodeAssignment,
    checkpoint: RedLivingDexFreshEpisodeCheckpoint,
) -> None:
    reader = PokemonRedStateReader(emulator)
    observer = LivePokemonRedObserver(reader, COMPLETION_QUEST)
    _latch_verified_progress(observer, checkpoint)
    adapter = PokemonRedGoalStateAdapter(reader, observer, COMPLETION_QUEST)
    completed_before = COMPLETION_QUEST.completed_ids(observer.observe())
    actions = CountingExecutor(
        FrameSafeExecutor(
            emulator,
            DEFAULT_NEW_GAME_TIMING.controller_timing(),
        )
    )
    if _MATERIALIZER is None:
        raise FreshEpisodeGeneratorError("conditioner_authentication")
    apply_mode = cast(Any, _MATERIALIZER["_apply_mode"])
    mode = (
        "storage-ready"
        if assignment.target_template_ordinal in {2, 3}
        else "story-resource-scarce"
    )
    apply_mode(
        mode,
        actions,
        reader,
        emulator,
        adapter,
        great_ball_quantity=None,
        hyper_potion_quantity=None,
        target_safety_pressure=None,
        maximum_safety_pressure=None,
        blocked_direction=None,
        target_active_box_count=assignment.target_active_box_count,
    )
    final = reader.read()
    completed_after = COMPLETION_QUEST.completed_ids(observer.observe())
    if (
        final.battle_state
        or completed_after != completed_before
        or emulator.pressed_buttons
        or not reader.read_input_readiness().ready
    ):
        raise FreshEpisodeGeneratorError("target_conditioning")


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.speed is not None and not args.watch:
        raise FreshEpisodeGeneratorError("arguments")
    stage = "source_authentication"
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    source_bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if (
        source.git_commit != args.expected_source_commit
        or source_bundle != args.expected_source_bundle_sha256
    ):
        raise FreshEpisodeGeneratorError(stage)

    stage = "plan_authentication"
    plan_payload = _read_bounded(args.plan.resolve(), _MAXIMUM_PLAN_BYTES)
    if hashlib.sha256(plan_payload).hexdigest() != args.expected_plan_sha256:
        raise FreshEpisodeGeneratorError(stage)
    plan = parse_red_living_dex_fresh_episode_plan(plan_payload)
    (
        generator_execution,
        runner_sha256,
        conditioner_sha256,
    ) = _generator_execution_binding(source_bundle)
    teacher_execution = (
        compose_red_living_dex_fresh_episode_teacher_execution_sha256(
            source_bundle_sha256=source_bundle,
            generator_execution_sha256=generator_execution,
        )
    )
    if (
        plan.source_commit != source.git_commit
        or plan.source_bundle_sha256 != source_bundle
        or plan.generator_execution_sha256 != generator_execution
        or plan.teacher_execution_sha256 != teacher_execution
        or args.expected_generator_execution_sha256 != generator_execution
    ):
        raise FreshEpisodeGeneratorError(stage)
    assignment = plan.assignment(args.assignment_id)

    stage = "capacity_authentication"
    capacity_payload = _read_bounded(
        CAPACITY_EVIDENCE_PATH,
        _MAXIMUM_EVIDENCE_BYTES,
    )
    if hashlib.sha256(capacity_payload).hexdigest() != (
        plan.capacity_evidence_sha256
    ):
        raise FreshEpisodeGeneratorError(stage)
    _load_materializer(conditioner_sha256)

    stage = "runtime_authentication"
    rom_path = resolve_rom_path(args.rom)
    rom_bytes = rom_path.read_bytes()
    rom = verify_rom_bytes(
        rom_bytes,
        POKEMON_RED_US_REV_0,
        filename=rom_path.name,
    )
    if rom.sha256 != POKEMON_RED_US_REV_0.sha256:
        raise FreshEpisodeGeneratorError(stage)
    runtime_identity = build_runtime_identity()
    require_pyboy_import_origins(runtime_identity)
    world = StrategicScenarioRouteWorld.from_rom(rom_bytes)
    corridors = derive_red_living_dex_provider_corridors(world)
    adjacent_before = rom_adjacent_artifacts(rom_path)
    store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
    claim_registry = open_fixed_account_claim_registry()
    checkpoint_box: list[RedLivingDexFreshEpisodeCheckpoint] = []

    def emulator_factory() -> PyBoyAdapter:
        emulator = PyBoyAdapter(
            rom_path,
            watch=args.watch,
            speed=args.speed,
            expected_rom=POKEMON_RED_US_REV_0,
        )
        emulator.start()
        require_pyboy_import_origins(runtime_identity)
        return emulator

    def setup_teacher(
        emulator: CleanPowerFreshEpisodeEmulator,
        _assignment: RedLivingDexFreshEpisodeAssignment,
    ) -> RedLivingDexFreshEpisodeCheckpoint:
        def progress(update: QualifiedPlayProgress) -> None:
            if update.checkpoint_id != RED_LIVING_DEX_FRESH_EPISODE_CHECKPOINT_ID:
                return
            checkpoint = RedLivingDexFreshEpisodeCheckpoint(
                checkpoint_id=update.checkpoint_id,
                label=update.label,
                completed=update.completed,
                total=update.total,
                verified_objective_ids=_verified_objectives(update.completed),
            )
            checkpoint_box.append(checkpoint)
            raise _TeacherCheckpointReached(checkpoint)

        try:
            run_qualified_play(
                rom_path,
                progress=progress,
                _emulator=cast(Any, emulator),
            )
        except _TeacherCheckpointReached as reached:
            if checkpoint_box != [reached.checkpoint]:
                raise FreshEpisodeGeneratorError("setup_teacher") from None
            return reached.checkpoint
        raise FreshEpisodeGeneratorError("setup_teacher")

    def condition_target(
        emulator: CleanPowerFreshEpisodeEmulator,
        selected: RedLivingDexFreshEpisodeAssignment,
    ) -> None:
        if len(checkpoint_box) != 1:
            raise FreshEpisodeGeneratorError("target_conditioning")
        _apply_target_conditioning(
            emulator,
            selected,
            checkpoint_box[0],
        )

    def verify_target(
        emulator: CleanPowerFreshEpisodeEmulator,
        selected: RedLivingDexFreshEpisodeAssignment,
        root: RedLivingDexAuthenticatedSetupRoot,
        _envelope: object,
    ) -> RedLivingDexFreshEpisodeTargetVerification:
        if len(checkpoint_box) != 1:
            raise FreshEpisodeGeneratorError("target_verification")
        frame_before = emulator.frame_count
        actions_before = emulator.controller_actions
        reader = PokemonRedStateReader(emulator)
        observer = LivePokemonRedObserver(reader, COMPLETION_QUEST)
        _latch_verified_progress(observer, checkpoint_box[0])
        goal = PokemonRedGoalStateAdapter(
            reader,
            observer,
            COMPLETION_QUEST,
        ).observe()
        traversal = Gen1TraversalObserver(
            reader,
            hazard_projector=Gen1TrainerSightProjector(rom_bytes, reader),
            capability_projector=lambda raw: gen1_field_capabilities(
                emulator,
                raw,
            ),
        ).observe()
        with fixed_account_claim_registry_lease(
            claim_registry,
            exclusive=False,
        ):
            if not all(
                root_claim_is_available(claim_registry, identity)
                for identity in (
                    root.root_consumption_sha256,
                    root.physical_root_sha256,
                )
            ):
                raise FreshEpisodeGeneratorError("target_verification")
        observation = RedLivingDexActionFreeRootObservation(
            root=root,
            traversal=traversal,
            facts=observe_red_living_dex_provider_root_facts(goal),
            observed_state_sha256=root.state_sha256,
            root_claim_available=True,
            option_context=living_dex_option_context_from_goal_situation(
                goal.situation
            ),
            independence_lineage_sha256=canonical_sha256(
                {
                    "root_lineage_id": selected.root_lineage_id,
                    "schema": (
                        "pokemon.red.private-provider-capacity-lineage.v1"
                    ),
                }
            ),
            prospective_independence_authenticated=True,
            cluster_partition="train",
        )
        compatible: list[int] = []
        slots = build_red_living_dex_prospective_capture_plan().slots[:10]
        for ordinal, slot in enumerate(slots):
            try:
                build_red_living_dex_provider_recipe_for_action_free_root(
                    slot,
                    observation,
                    world=world,
                    corridors=corridors,
                )
            except RedLivingDexProviderPlanError:
                continue
            compatible.append(ordinal)
        if (
            emulator.frame_count != frame_before
            or emulator.controller_actions != actions_before
            or emulator.pressed_buttons
        ):
            raise FreshEpisodeGeneratorError("target_verification")
        pressure = None
        if selected.target_active_box_count is not None:
            pressure = round(goal.situation.storage_pressure * 1_000_000)
        return RedLivingDexFreshEpisodeTargetVerification(
            compatible_template_ordinals=tuple(compatible),
            observed_storage_pressure_millionths=pressure,
        )

    def post_close_verify() -> None:
        require_pyboy_import_origins(runtime_identity)
        if rom_adjacent_artifacts(rom_path) != adjacent_before:
            raise FreshEpisodeGeneratorError("rom_isolation")

    stage = "fresh_episode_execution"
    try:
        result = execute_red_living_dex_fresh_episode(
            plan,
            assignment.assignment_id,
            source_commit=source.git_commit,
            source_bundle_sha256=source_bundle,
            generator_execution_sha256=generator_execution,
            runner_sha256=runner_sha256,
            process_authority=(
                issue_red_living_dex_fresh_episode_process_authority()
            ),
            private_store=store,
            claim_registry=claim_registry,
            emulator_factory=emulator_factory,
            setup_teacher=setup_teacher,
            condition_target=condition_target,
            verify_target=verify_target,
            post_close_verify=post_close_verify,
        )
    except BaseException as error:
        assignment_claim_sha256: str | None = None
        try:
            claim = read_red_living_dex_fresh_episode_assignment_claim(
                claim_registry,
                assignment.assignment_id,
            )
            if (
                claim.get("assignment_id") == assignment.assignment_id
                and claim.get("plan_sha256") == plan.plan_sha256
                and claim.get("source_commit") == source.git_commit
                and claim.get("runner_sha256") == runner_sha256
            ):
                assignment_claim_sha256 = canonical_sha256(claim)
        except BaseException:
            assignment_claim_sha256 = None
        effects_known, controller_actions, emulator_frames = (
            _known_runtime_effects(error)
        )
        raise FreshEpisodeGeneratorError(
            stage,
            RedLivingDexFreshEpisodeFailureReceipt(
                assignment_id=assignment.assignment_id,
                plan_sha256=plan.plan_sha256,
                source_bundle_sha256=assignment.source_bundle_sha256,
                teacher_execution_sha256=(
                    assignment.teacher_execution_sha256
                ),
                generator_execution_sha256=(
                    assignment.generator_execution_sha256
                ),
                assignment_claim_sha256=assignment_claim_sha256,
                failure_stage=stage,
                effects_known=effects_known,
                controller_actions=controller_actions,
                emulator_frames=emulator_frames,
            ),
        ) from None
    require_pyboy_import_origins(runtime_identity)
    return result.public_dict()


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    failure_receipt: RedLivingDexFreshEpisodeFailureReceipt | None = None
    try:
        args = _parser().parse_args(argv)
        result = _run(args)
        print(
            json.dumps(
                result,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0
    except FreshEpisodeGeneratorError as error:
        stage = error.stage
        failure_receipt = error.failure_receipt
    except BaseException:
        stage = "unclassified_failure"
    if failure_receipt is not None:
        print(
            json.dumps(
                {
                    **failure_receipt.public_dict(),
                    "status": "failed_closed_consumed_no_retry",
                },
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1
    effects_unknown = stage in {
        "fresh_episode_execution",
        "rom_isolation",
        "unclassified_failure",
    }
    print(
        json.dumps(
            {
                "controller_actions": None if effects_unknown else 0,
                "effects_unknown": effects_unknown,
                "learner_outcomes": None if effects_unknown else 0,
                "model_fits": None if effects_unknown else 0,
                "model_predictions": None if effects_unknown else 0,
                "private_identity_fields": 0,
                "private_path_fields": 0,
                "schema": (
                    "pokemon.red.living-dex-fresh-episode-failure.v1"
                ),
                "stage": stage,
                "status": "failed_closed",
            },
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
