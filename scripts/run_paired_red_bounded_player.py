#!/usr/bin/env python3
"""Run one repeatable same-state Red player comparison in development."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Mapping
from contextlib import ExitStack, suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING  # noqa: E402
from pokemon_red_completion.bounded_player_dashboard import (  # noqa: E402
    BoundedPlayerDashboard,
    ViewerGoalTrajectory,
)
from pokemon_red_completion.bounded_player_episode import (  # noqa: E402
    BoundedPlayerLimits,
    run_bounded_player_episode,
)
from pokemon_red_completion.collection_protocol import (  # noqa: E402
    working_source_bundle_sha256,
)
from pokemon_red_completion.emulator import PyBoyAdapter  # noqa: E402
from pokemon_red_completion.executor import (  # noqa: E402
    CountingExecutor,
    FrameSafeExecutor,
    ReadOnlyController,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.goal_manager_composition_qualification import (  # noqa: E402
    CompositionIndependentBudgetMeter,
    HardCompositionActionLimiter,
)
from pokemon_red_completion.goal_manager_composition_runtime import (  # noqa: E402
    CompositionBudgetCheckpoint,
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
)
from pokemon_red_completion.goal_manager_context_catalog import (  # noqa: E402
    GoalManagerContextCapture,
    open_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_model import (  # noqa: E402
    GoalManagerLinearModel,
    LearnedGoalManagerPolicy,
    canonical_goal_manager_model_sha256,
    load_goal_manager_model,
)
from pokemon_red_completion.goal_manager_runtime import (  # noqa: E402
    CompletionFirstGoalTeacher,
    GoalDecisionAuthority,
)
from pokemon_red_completion.goal_search_memory import GoalSearchMemory  # noqa: E402
from pokemon_red_completion.living_dex_goal_model_record import (  # noqa: E402
    LivingDexGoalModelRecord,
)
from pokemon_red_completion.living_dex_goal_policy import (  # noqa: E402
    LivingDexGoalShadowPolicy,
)
from pokemon_red_completion.living_dex_paired_development import (  # noqa: E402
    private_failure_diagnostic,
)
from pokemon_red_completion.living_dex_player_exploration import (  # noqa: E402
    ExploringLivingDexGoalPolicy,
)
from pokemon_red_completion.multi_goal_calibration_model import (  # noqa: E402
    MultiGoalCalibrationModel,
    load_multi_goal_calibration_model,
)
from pokemon_red_completion.observation import PokemonRedStateReader  # noqa: E402
from pokemon_red_completion.paired_bounded_player import (  # noqa: E402
    PairedBoundedPlayerArm,
    PairedBoundedPlayerComparison,
    compare_paired_bounded_player_arms,
)
from pokemon_red_completion.private_artifacts import (  # noqa: E402
    EpisodeWriter,
    PrivateArtifactRoot,
    open_private_root,
)
from pokemon_red_completion.progress_dashboard import (  # noqa: E402
    DashboardState,
    ProgressDashboardServer,
)
from pokemon_red_completion.provenance import (  # noqa: E402
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_bounded_player import (  # noqa: E402
    RedBoundedPlayerObserver,
    preflight_red_bounded_player,
)
from pokemon_red_completion.red_goal_context import (  # noqa: E402
    RedGoalContextRuntime,
    build_red_goal_context_runtime,
)
from pokemon_red_completion.red_goal_context_profile import (  # noqa: E402
    RedGoalContextProfile,
    build_acquisition_replanning_profile_payload,
    load_red_goal_context_profile,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_player_checkpoint import (  # noqa: E402
    CHECKPOINT_KIND,
    RedPlayerCheckpoint,
    capture_red_player_terminal,
    checkpoint_record_id,
    open_red_player_checkpoint,
    publish_red_player_checkpoint,
)
from pokemon_red_completion.red_player_model import (  # noqa: E402
    RedPlayerModelRecord,
)
from pokemon_red_completion.red_player_model import (  # noqa: E402
    load_player_goal_model_record as load_living_dex_goal_model_record,
)
from pokemon_red_completion.red_player_training import RedPlayerTrainingTrajectory  # noqa: E402
from pokemon_red_completion.red_player_training_plan import (  # noqa: E402
    RedPlayerTrainingPlan,
    continue_red_player_training,
    declare_red_player_training,
)
from pokemon_red_completion.red_resource_goal_router import RedResourceGoalRouter  # noqa: E402
from pokemon_red_completion.red_trajectory import (  # noqa: E402
    PokemonRedObservationEncoder,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402
from pokemon_red_completion.strategic_navigation_scenario_runtime import (  # noqa: E402
    StrategicScenarioRouteWorld,
)
from pokemon_red_completion.trajectory import (  # noqa: E402
    JSONValue,
    RecordingExecutor,
    SparseEvent,
)
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink  # noqa: E402

GAME_ID = "pokemon.mainline:red:gb:us:rev0"
LEARNED_ARM_ID = "learned-goal-manager"
CAUSAL_ARM_ID = "living-dex-causal-shadow"
CALIBRATION_ARM_ID = "multi-goal-calibration-shadow"
BASELINE_ARM_ID = "completion-first-teacher"
_CHALLENGER_IDS = (LEARNED_ARM_ID, CAUSAL_ARM_ID, CALIBRATION_ARM_ID)
_PAIR_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,47}\Z")


class PairedRedBoundedPlayerRunError(RuntimeError):
    """A path-free failure from the repeatable paired development runner."""


@dataclass(frozen=True, slots=True)
class _Readiness:
    pair_id: str
    source_commit: str
    source_bundle_sha256: str
    rom_path: Path
    rom_sha256: str
    capture: GoalManagerContextCapture
    profile: RedGoalContextProfile
    challenger_arm_id: str
    legacy_model: GoalManagerLinearModel | None
    causal_record: LivingDexGoalModelRecord | RedPlayerModelRecord | None
    calibration_record: MultiGoalCalibrationModel | None
    model_file_sha256: str
    model_sha256: str
    decision_limit: int
    private_root: PrivateArtifactRoot
    output_path: Path
    protected_paths: tuple[Path, ...]
    continue_after_progress: bool = False
    dashboard_port: int | None = None
    context_origin: str = "unspecified"
    routed_resource_goals: bool = False
    save_terminal_checkpoints: bool = False
    quote_resource_costs: bool = False
    training_plan: RedPlayerTrainingPlan | None = None
    continuation: RedPlayerCheckpoint | None = None
    continuation_chain: tuple[tuple[str, str], ...] = ()
    continuation_root_lineage_id: str | None = None
    restore_profile: RedGoalContextProfile | None = None
    completion_dose: bool = False


@dataclass(frozen=True, slots=True)
class _ReadOnlyBudgetMeter:
    actions: CountingExecutor
    emulator: PyBoyAdapter
    initial_frame_count: int

    def checkpoint(self) -> CompositionBudgetCheckpoint:
        frames = self.emulator.frame_count - self.initial_frame_count
        if frames < 0:
            raise PairedRedBoundedPlayerRunError("preflight_frame_counter_regressed")
        return CompositionBudgetCheckpoint(
            controller_actions=self.actions.actions_executed,
            emulator_frames=frames,
        )


class _DeferredActionExecutor:
    """Make observation action-free before enabling the returned private bindings."""

    __slots__ = ("_delegate", "_enabled", "attempted_while_disabled")

    def __init__(self, delegate: object) -> None:
        self._delegate = delegate
        self._enabled = False
        self.attempted_while_disabled = 0

    def enable(self) -> None:
        self._enabled = True

    def execute(self, action: object) -> object:
        if not self._enabled:
            self.attempted_while_disabled += 1
            raise PairedRedBoundedPlayerRunError("action_free_observation")
        execute = getattr(self._delegate, "execute", None)
        if not callable(execute):
            raise PairedRedBoundedPlayerRunError("executor_authentication")
        return execute(action)


@dataclass(slots=True)
class _LiveObserver:
    runtime: RedGoalContextRuntime
    actions: CountingExecutor
    meter: CompositionIndependentBudgetMeter
    observations: int = 0
    starting_observation: GoalManagerCompositionObservation | None = None
    viewer: BoundedPlayerDashboard | None = None
    route_world: StrategicScenarioRouteWorld | None = None
    quote_resource_costs: bool = False
    maximum_actions_per_decision: int = 6_000
    search_memory: GoalSearchMemory | None = None
    completion_dose: bool = False
    retain_quantum: Callable[[], None] | None = None

    def __call__(self) -> GoalManagerCompositionObservation:
        if self.observations:
            self.meter.begin_decision_window()
        before = self.meter.checkpoint()
        deferred = _DeferredActionExecutor(self.actions)
        # Preserve the concrete hard-limited skill interface around the
        # observation gate. The original episode-wide limiter remains below
        # the gate; this fresh per-offer limiter cannot reset that total.
        skill_actions = CountingExecutor(
            HardCompositionActionLimiter(
                deferred,
                maximum_actions_per_decision=self.maximum_actions_per_decision,
                maximum_episode_actions=self.maximum_actions_per_decision,
            )
        )
        bridge = _player_observer(
            self.runtime,
            skill_actions,
            self.route_world,
            self.quote_resource_costs,
            completion_dose=self.completion_dose,
            retain_quantum=self.retain_quantum,
        )
        bridge.search_memory = self.search_memory
        observation = bridge()
        if self.meter.checkpoint() != before or deferred.attempted_while_disabled:
            raise PairedRedBoundedPlayerRunError("action_free_observation")
        deferred.enable()
        if self.starting_observation is None:
            self.starting_observation = observation
        self.observations += 1
        if self.viewer is not None:
            self.viewer.safely("observed", bridge.last_live_observation, observation)
        return observation


def _player_observer(
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    world: StrategicScenarioRouteWorld | None,
    quote_resource_costs: bool = False,
    *,
    completion_dose: bool = False,
    retain_quantum: Callable[[], None] | None = None,
) -> RedBoundedPlayerObserver:
    from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic

    if world is not None and any(
        s.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION for s in runtime.profile.providers
    ):
        from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution

        runtime = bind_native_boxed_evolution(
            runtime,
            world,
            maximum_quanta=128 if completion_dose else 1,
            retain_quantum=retain_quantum,
        )
    router = (
        None
        if world is None
        else RedResourceGoalRouter(
            runtime,
            actions,
            world,
            quote_resource_costs=quote_resource_costs,
            maximum_controller_actions=30_000 if completion_dose else 6_000,
            maximum_emulator_frames=3_000_000 if completion_dose else 600_000,
        )
    )
    observer = RedBoundedPlayerObserver(
        runtime=runtime,
        actions=actions,
        enumerate_bindings=None if router is None else router.enumerate,
    )
    if completion_dose:
        from pokemon_red_completion.goal_manager_composition_qualification import (
            living_completion_checkpoint,
        )

        observer.collection_projector = living_completion_checkpoint
    return observer


def _route_world(readiness: _Readiness) -> StrategicScenarioRouteWorld | None:
    if not readiness.routed_resource_goals:
        return None
    payload = readiness.rom_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != readiness.rom_sha256:
        raise PairedRedBoundedPlayerRunError("routing_cartridge_identity")
    return StrategicScenarioRouteWorld.from_rom(payload)


@dataclass(slots=True)
class _ProgressPredicate:
    initial: LivingCollectionCheckpoint | None = None

    def __call__(self, observation: GoalManagerCompositionObservation) -> bool:
        current = observation.collection
        if self.initial is None:
            self.initial = current
            return False
        return any(
            (
                current.required_specimens_remaining < self.initial.required_specimens_remaining,
                current.registered_species > self.initial.registered_species,
                current.living_species > self.initial.living_species,
                current.retained_captures > self.initial.retained_captures,
                current.storage_headroom > self.initial.storage_headroom,
            )
        )


@dataclass(frozen=True, slots=True)
class _LivingDexCompletionPredicate:
    """Continue a declared goal chain until its limit or the ledger is complete."""

    def __call__(self, observation: GoalManagerCompositionObservation) -> bool:
        return observation.collection.required_specimens_remaining == 0


def _completion_predicate(
    readiness: _Readiness,
) -> _LivingDexCompletionPredicate | _ProgressPredicate:
    if readiness.challenger_arm_id == CALIBRATION_ARM_ID or readiness.continue_after_progress:
        return _LivingDexCompletionPredicate()
    return _ProgressPredicate()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument(
        "--continue-from-checkpoint",
        nargs=2,
        action="append",
        default=[],
        metavar=("EPISODE", "SHA256"),
        help="single-arm diagnostic continuation; repeat in ancestor order from --state/--envelope",
    )
    parser.add_argument(
        "--train-player",
        action="store_true",
        help="single-arm prospective training; no comparison claim",
    )
    parser.add_argument(
        "--expand-local-development",
        action="store_true",
        help="after verified restore, add the existing four-battle local development skill",
    )
    parser.add_argument("--training-seed", type=int, default=None)
    parser.add_argument(
        "--completion-dose",
        action="store_true",
        help="declare bounded complete evolution: 30000 actions / 3000000 frames per choice",
    )
    parser.add_argument(
        "--boxed-evolution",
        nargs=3,
        type=int,
        default=None,
        metavar=("SOURCE_NATIONAL", "TARGET_NATIONAL", "LEVEL"),
        help="declare an existing boxed level-evolution skill after authenticated continuation",
    )
    parser.add_argument("--training-catalog", type=Path, default=None)
    parser.add_argument("--expected-training-catalog-sha256", default=None)
    parser.add_argument(
        "--context-origin",
        choices=("training", "development", "unspecified"),
        default="unspecified",
        help="declare input provenance; a known training state is not an unseen test",
    )
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument(
        "--save-terminal-checkpoints",
        action="store_true",
        help="retain private end states joined to completed trajectories; never auto-resume",
    )
    parser.add_argument(
        "--routed-resource-goals",
        action="store_true",
        help="opt in to fresh walking routes to declared capture and supply destinations",
    )
    parser.add_argument(
        "--quote-resource-costs",
        action="store_true",
        help="opt in to known-money/reserve scoring without changing old model features or labels",
    )
    parser.add_argument(
        "--challenger",
        choices=_CHALLENGER_IDS,
        default=LEARNED_ARM_ID,
    )
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--living-dex-model-record", type=Path, default=None)
    parser.add_argument("--expected-living-dex-model-sha256", default=None)
    parser.add_argument("--calibration-model", type=Path, default=None)
    parser.add_argument("--calibration-fit-summary", type=Path, default=None)
    parser.add_argument("--expected-calibration-model-file-sha256", default=None)
    parser.add_argument("--expected-calibration-summary-file-sha256", default=None)
    parser.add_argument("--decision-limit", type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument(
        "--continue-after-progress",
        action="store_true",
        help="prospective bounded chain; do not stop at the first collection gain",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=None,
        help="optional loopback-only spectator feed (use 8769 behind the overview)",
    )
    parser.add_argument("--private-artifact-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    return parser


def _regular_external(path: Path, *, subject: str, rom_path: Path) -> Path:
    resolved = path.resolve()
    try:
        metadata = resolved.lstat()
    except OSError as error:
        raise PairedRedBoundedPlayerRunError(f"{subject}_unavailable") from error
    if (
        resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
        or resolved.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
    ):
        raise PairedRedBoundedPlayerRunError(f"{subject}_isolation")
    return resolved


def _new_external_output(path: Path, *, rom_path: Path) -> Path:
    resolved = path.resolve()
    if (
        resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
        or not resolved.parent.is_dir()
        or resolved.exists()
        or resolved.suffix != ".json"
    ):
        raise PairedRedBoundedPlayerRunError("output_isolation")
    return resolved


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _challenger_arguments(
    args: argparse.Namespace,
) -> tuple[Path, Path | None, str | None, str | None]:
    if args.challenger == LEARNED_ARM_ID:
        if (
            not isinstance(args.model, Path)
            or args.living_dex_model_record is not None
            or args.expected_living_dex_model_sha256 is not None
            or args.calibration_model is not None
            or args.calibration_fit_summary is not None
            or args.expected_calibration_model_file_sha256 is not None
            or args.expected_calibration_summary_file_sha256 is not None
        ):
            raise PairedRedBoundedPlayerRunError("challenger_model_arguments")
        return args.model, None, None, None
    if args.challenger == CAUSAL_ARM_ID:
        if (
            args.model is not None
            or not isinstance(args.living_dex_model_record, Path)
            or not isinstance(args.expected_living_dex_model_sha256, str)
            or args.calibration_model is not None
            or args.calibration_fit_summary is not None
            or args.expected_calibration_model_file_sha256 is not None
            or args.expected_calibration_summary_file_sha256 is not None
        ):
            raise PairedRedBoundedPlayerRunError("challenger_model_arguments")
        return (
            args.living_dex_model_record,
            None,
            args.expected_living_dex_model_sha256,
            None,
        )
    if args.challenger == CALIBRATION_ARM_ID:
        if (
            args.model is not None
            or args.living_dex_model_record is not None
            or args.expected_living_dex_model_sha256 is not None
            or not isinstance(args.calibration_model, Path)
            or not isinstance(args.calibration_fit_summary, Path)
            or not isinstance(args.expected_calibration_model_file_sha256, str)
            or not isinstance(args.expected_calibration_summary_file_sha256, str)
        ):
            raise PairedRedBoundedPlayerRunError("challenger_model_arguments")
        return (
            args.calibration_model,
            args.calibration_fit_summary,
            args.expected_calibration_model_file_sha256,
            args.expected_calibration_summary_file_sha256,
        )
    raise PairedRedBoundedPlayerRunError("challenger_identity")


def _prepare(args: argparse.Namespace) -> _Readiness:
    if not isinstance(args.pair_id, str) or _PAIR_ID.fullmatch(args.pair_id) is None:
        raise PairedRedBoundedPlayerRunError("pair_id")
    continuation_chain = tuple(
        tuple(item) for item in getattr(args, "continue_from_checkpoint", ())
    )
    if continuation_chain and (
        args.challenger != CAUSAL_ARM_ID
        or getattr(args, "context_origin", None) != "training"
        or not getattr(args, "save_terminal_checkpoints", False)
    ):
        raise PairedRedBoundedPlayerRunError("continuation_scope")
    expand_local = getattr(args, "expand_local_development", False)
    if type(expand_local) is not bool or (expand_local and not continuation_chain):
        raise PairedRedBoundedPlayerRunError("profile_transition_scope")
    boxed_evolution = getattr(args, "boxed_evolution", None)
    completion_dose = getattr(args, "completion_dose", False)
    if type(completion_dose) is not bool or (
        completion_dose and (boxed_evolution is None or not continuation_chain)
    ):
        raise PairedRedBoundedPlayerRunError("completion_dose_scope")
    if boxed_evolution is not None and (
        not continuation_chain
        or not getattr(args, "routed_resource_goals", False)
        or not isinstance(boxed_evolution, (tuple, list))
        or len(boxed_evolution) != 3
        or any(type(value) is not int for value in boxed_evolution)
    ):
        raise PairedRedBoundedPlayerRunError("boxed_evolution_scope")
    context_origin = getattr(args, "context_origin", "unspecified")
    if context_origin not in {"training", "development", "unspecified"}:
        raise PairedRedBoundedPlayerRunError("context_origin")
    routed_resource_goals = getattr(args, "routed_resource_goals", False)
    if type(routed_resource_goals) is not bool:
        raise PairedRedBoundedPlayerRunError("routed_resource_goals")
    quote_resource_costs = getattr(args, "quote_resource_costs", False)
    if type(quote_resource_costs) is not bool or (
        quote_resource_costs and (not routed_resource_goals or args.challenger != CAUSAL_ARM_ID)
    ):
        raise PairedRedBoundedPlayerRunError("quote_resource_costs")
    save_terminal_checkpoints = getattr(args, "save_terminal_checkpoints", False)
    if type(save_terminal_checkpoints) is not bool:
        raise PairedRedBoundedPlayerRunError("save_terminal_checkpoints")
    dashboard_port = getattr(args, "dashboard_port", None)
    if dashboard_port is not None and (
        type(dashboard_port) is not int or not 1024 <= dashboard_port <= 65535
    ):
        raise PairedRedBoundedPlayerRunError("dashboard_port")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if source.git_commit is None:
        raise PairedRedBoundedPlayerRunError("source_identity")
    (
        challenger_model_path,
        calibration_summary_path,
        expected_model_sha256,
        expected_calibration_summary_sha256,
    ) = _challenger_arguments(args)
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    state = _regular_external(args.state, subject="state", rom_path=rom_path)
    envelope = _regular_external(args.envelope, subject="envelope", rom_path=rom_path)
    profile_path = _regular_external(args.profile, subject="profile", rom_path=rom_path)
    output_path = _new_external_output(args.out, rom_path=rom_path)
    capture = open_goal_manager_context_capture(state, envelope)
    profile = load_red_goal_context_profile(profile_path)
    if capture.capture_id != profile.profile_id:
        raise PairedRedBoundedPlayerRunError("capture_profile_identity")
    model_path = _regular_external(
        challenger_model_path,
        subject="model",
        rom_path=rom_path,
    )
    model_file_sha256 = _sha256(model_path)
    legacy_model: GoalManagerLinearModel | None = None
    causal_record: LivingDexGoalModelRecord | RedPlayerModelRecord | None = None
    calibration_record: MultiGoalCalibrationModel | None = None
    extra_protected_paths: tuple[Path, ...] = ()
    if args.challenger == LEARNED_ARM_ID:
        legacy_model = load_goal_manager_model(
            model_path,
            expected_sha256=model_file_sha256,
        )
        model_sha256 = canonical_goal_manager_model_sha256(legacy_model)
    else:
        if args.challenger == CAUSAL_ARM_ID:
            if expected_model_sha256 is None:
                raise PairedRedBoundedPlayerRunError("challenger_model_arguments")
            causal_record = load_living_dex_goal_model_record(
                model_path,
                expected_model_sha256=expected_model_sha256,
            )
            if causal_record.file_sha256 != model_file_sha256:
                raise PairedRedBoundedPlayerRunError("challenger_model_identity")
            model_sha256 = causal_record.model.model_sha256
        else:
            if (
                calibration_summary_path is None
                or expected_model_sha256 is None
                or expected_calibration_summary_sha256 is None
            ):
                raise PairedRedBoundedPlayerRunError("challenger_model_arguments")
            summary_path = _regular_external(
                calibration_summary_path,
                subject="calibration_summary",
                rom_path=rom_path,
            )
            calibration_record = load_multi_goal_calibration_model(
                model_path,
                summary_path,
                expected_model_file_sha256=expected_model_sha256,
                expected_summary_file_sha256=expected_calibration_summary_sha256,
            )
            if calibration_record.model_file_sha256 != model_file_sha256:
                raise PairedRedBoundedPlayerRunError("challenger_model_identity")
            model_sha256 = canonical_goal_manager_model_sha256(calibration_record.model)
            extra_protected_paths = (summary_path,)
    private_root = open_private_root(
        args.private_artifact_root,
        repository_root=PROJECT_ROOT,
        allow_same_device=True,
    )
    training_plan = None
    bundle = working_source_bundle_sha256(PROJECT_ROOT)
    if getattr(args, "train_player", False):
        if (
            context_origin != "training"
            or not quote_resource_costs
            or not isinstance(args.training_catalog, Path)
        ):
            raise PairedRedBoundedPlayerRunError("training_mode_arguments")
        catalog_path = _regular_external(
            args.training_catalog, subject="training_catalog", rom_path=rom_path
        )
        training_plan = declare_red_player_training(
            repository_root=PROJECT_ROOT,
            catalog_path=catalog_path,
            expected_catalog_sha256=args.expected_training_catalog_sha256,
            capture=capture,
            profile_sha256=profile.profile_sha256,
            model_sha256=model_sha256,
            source_commit=source.git_commit,
            source_bundle_sha256=bundle,
            episode_id=_episode_id(args.pair_id, args.challenger),
            seed=args.training_seed,
            decision_limit=args.decision_limit,
        )
        extra_protected_paths = (*extra_protected_paths, catalog_path)
    elif any(
        getattr(args, name, None) is not None
        for name in ("training_seed", "training_catalog", "expected_training_catalog_sha256")
    ):
        raise PairedRedBoundedPlayerRunError("training_mode_arguments")
    for arm_id in (args.challenger, BASELINE_ARM_ID):
        episode_id = _episode_id(args.pair_id, arm_id)
        if private_root.inspect_episode_state(episode_id).status != "absent":
            raise PairedRedBoundedPlayerRunError("pair_id_already_used")
    readiness = _Readiness(
        pair_id=args.pair_id,
        routed_resource_goals=routed_resource_goals,
        quote_resource_costs=quote_resource_costs,
        training_plan=training_plan,
        completion_dose=completion_dose,
        save_terminal_checkpoints=save_terminal_checkpoints,
        source_commit=source.git_commit,
        source_bundle_sha256=bundle,
        rom_path=rom_path,
        rom_sha256=rom.sha256,
        capture=capture,
        profile=profile,
        challenger_arm_id=args.challenger,
        legacy_model=legacy_model,
        causal_record=causal_record,
        calibration_record=calibration_record,
        model_file_sha256=model_file_sha256,
        model_sha256=model_sha256,
        decision_limit=args.decision_limit,
        continue_after_progress=getattr(args, "continue_after_progress", False),
        dashboard_port=dashboard_port,
        context_origin=context_origin,
        private_root=private_root,
        output_path=output_path,
        protected_paths=(
            state,
            envelope,
            profile_path,
            model_path,
            *extra_protected_paths,
            rom_path,
        ),
    )
    expanded_profile = (
        parse_red_goal_context_profile(build_acquisition_replanning_profile_payload(profile))
        if expand_local
        else None
    )
    readiness = _continue_readiness(
        readiness,
        continuation_chain,
        expanded_profile=expanded_profile,
        execution_profile=(
            _boxed_evolution_profile(expanded_profile or profile, boxed_evolution)
            if boxed_evolution is not None
            else None
        ),
    )
    if readiness.training_plan is not None and readiness.continuation is not None:
        assert readiness.restore_profile is not None
        assert readiness.continuation_root_lineage_id is not None
        ancestor_id, ancestor_sha = readiness.continuation_chain[-1]
        readiness = replace(
            readiness,
            training_plan=continue_red_player_training(
                readiness.training_plan,
                capture=readiness.capture,
                root_lineage_id=readiness.continuation_root_lineage_id,
                episode_id=ancestor_id,
                checkpoint_sha256=ancestor_sha,
                restore_profile_sha256=readiness.restore_profile.profile_sha256,
                execution_profile_sha256=readiness.profile.profile_sha256,
            ),
        )
    if completion_dose and readiness.training_plan is not None:
        from pokemon_red_completion.red_player_training_plan import declare_completion_dose

        readiness = replace(
            readiness,
            training_plan=declare_completion_dose(readiness.training_plan),
        )
    return readiness


def _boxed_evolution_profile(
    profile: RedGoalContextProfile,
    values: list[int] | tuple[int, ...],
) -> RedGoalContextProfile:
    from pokemon_red_completion.red_goal_context_profile import (
        build_native_boxed_evolution_profile_payload,
    )

    return parse_red_goal_context_profile(
        build_native_boxed_evolution_profile_payload(
            profile,
            source_species=values[0],
            target_species=values[1],
            evolution_level=values[2],
        )
    )


def _continue_readiness(
    readiness: _Readiness,
    chain: tuple[tuple[str, str], ...],
    *,
    expanded_profile: RedGoalContextProfile | None = None,
    execution_profile: RedGoalContextProfile | None = None,
) -> _Readiness:
    """Authenticate each completed ancestor without inventing an independent root."""
    seen: set[str] = set()
    admitted_profiles = tuple(
        p for p in (readiness.profile, expanded_profile, execution_profile) if p is not None
    )
    profile_index = 0
    for episode_id, record_sha256 in chain:
        if episode_id in seen:
            raise PairedRedBoundedPlayerRunError("continuation_duplicate_ancestor")
        seen.add(episode_id)
        header = readiness.private_root.open_episode(episode_id).read_header()
        metadata = header.get("metadata")
        if isinstance(metadata, Mapping):
            for index, candidate in enumerate(admitted_profiles):
                if metadata.get("profile_sha256") == candidate.profile_sha256:
                    if index < profile_index:
                        raise PairedRedBoundedPlayerRunError("continuation_profile_rollback")
                    profile_index = index
                    readiness = replace(readiness, profile=candidate)
                    break
        checkpoint = open_red_player_checkpoint(
            readiness.private_root,
            episode_id=episode_id,
            expected_record_sha256=record_sha256,
            original_parent=readiness.capture,
            expected_profile_sha256=readiness.profile.profile_sha256,
            expected_rom_sha256=readiness.rom_sha256,
            expected_context_origin=readiness.context_origin,
        )
        if readiness.continuation is not None and readiness.continuation.search_memory is not None:
            if checkpoint.search_memory is None:
                raise PairedRedBoundedPlayerRunError("continuation_search_history_lost")
            GoalSearchMemory.from_private_dict(checkpoint.search_memory).require_extension(
                GoalSearchMemory.from_private_dict(readiness.continuation.search_memory)
            )
        split = metadata.get("split") if isinstance(metadata, Mapping) else None
        if not isinstance(split, Mapping) or split.get("partition") != "train":
            raise PairedRedBoundedPlayerRunError("continuation_training_lineage")
        lineage = split.get("root_lineage_id")
        if (
            not isinstance(lineage, str)
            or not lineage
            or (
                readiness.continuation_root_lineage_id is not None
                and readiness.continuation_root_lineage_id != lineage
            )
        ):
            raise PairedRedBoundedPlayerRunError("continuation_training_lineage")
        readiness = replace(
            readiness,
            capture=checkpoint.capture,
            continuation=checkpoint,
            continuation_root_lineage_id=lineage,
            continuation_chain=(*readiness.continuation_chain, (episode_id, record_sha256)),
        )
    if chain:
        readiness = replace(
            readiness,
            restore_profile=readiness.profile,
            profile=execution_profile or expanded_profile or readiness.profile,
        )
    return readiness


def _continuation_header(readiness: _Readiness) -> dict[str, object]:
    if readiness.continuation is None:
        return {}
    return {
        "continuation_chain": [
            {"episode_id": episode, "checkpoint_record_sha256": sha}
            for episode, sha in readiness.continuation_chain
        ],
        "split": {"root_lineage_id": readiness.continuation_root_lineage_id, "partition": "train"},
        "independent_root": False,
        "training_eligible": readiness.training_plan is not None,
    }


def _verify_continuation_restore(readiness: _Readiness, emulator: PyBoyAdapter) -> None:
    """Check the actual live restore through read-only controls, before enabling play."""
    if readiness.continuation is None:
        return
    initial_frame = emulator.frame_count
    controller = ReadOnlyController(emulator)
    runtime = build_red_goal_context_runtime(
        profile=getattr(readiness, "restore_profile", None) or readiness.profile,
        capture=readiness.capture,
        emulator=controller,
        reader=PokemonRedStateReader(controller),
    )
    actions = CountingExecutor(
        FrameSafeExecutor(controller, DEFAULT_NEW_GAME_TIMING.controller_timing())
    )
    observer = _player_observer(
        runtime,
        actions,
        _route_world(readiness),
        readiness.quote_resource_costs,
    )
    from pokemon_red_completion.goal_manager_composition_qualification import (
        living_completion_checkpoint,
        living_completion_contract_sha256,
    )

    if (
        getattr(readiness.continuation, "collection", {}).get("completion_contract_sha256")
        == living_completion_contract_sha256()
    ):
        observer.collection_projector = living_completion_checkpoint
    if getattr(readiness.continuation, "search_memory", None) is not None:
        observer.search_memory = GoalSearchMemory.from_private_dict(
            readiness.continuation.search_memory
        )
    observation = observer()
    readiness.continuation.require_restored_observation(observation)
    if (
        actions.actions_executed
        or emulator.frame_count != initial_frame
        or emulator.pressed_buttons
    ):
        raise PairedRedBoundedPlayerRunError("continuation_restore_effect")


def _execution_search_memory(readiness: _Readiness) -> GoalSearchMemory | None:
    """Start tracking only with an explicit V2 model; preserve restored history.

    Legacy checkpoint authentication happens first, against its original inputs.
    Empty new tracking does not claim knowledge of searches before this boundary.
    """
    saved = getattr(readiness.continuation, "search_memory", None)
    if saved is not None:
        return GoalSearchMemory.from_private_dict(saved)
    record = getattr(readiness, "causal_record", None)
    if record is not None and record.model.feature_version == 2:
        return GoalSearchMemory()
    return None


def _episode_id(pair_id: str, arm_id: str) -> str:
    suffix_by_arm = {
        LEARNED_ARM_ID: "learned",
        CAUSAL_ARM_ID: "causal",
        CALIBRATION_ARM_ID: "calibration",
        BASELINE_ARM_ID: "baseline",
    }
    try:
        suffix = suffix_by_arm[arm_id]
    except KeyError as error:
        raise PairedRedBoundedPlayerRunError("arm_identity") from error
    return f"{pair_id}-{suffix}"


def _context_scope(readiness: _Readiness) -> dict[str, object]:
    return {
        "context_origin": readiness.context_origin,
        "evidence_scope": (
            "prospective_correlated_training"
            if readiness.training_plan is not None
            else "training_context_integration_only"
            if readiness.context_origin == "training"
            else "descriptive_development_only"
        ),
        "independent_generalization_claim": False,
    }


def _training_header(readiness: _Readiness, arm_id: str) -> dict[str, object]:
    plan = readiness.training_plan
    if plan is None:
        return {}
    if arm_id != CAUSAL_ARM_ID:
        raise PairedRedBoundedPlayerRunError("training_actor")
    return {
        "player_training_plan": dict(plan.document),
        "player_training_plan_sha256": plan.plan_sha256,
        "policy": {"actor": arm_id, "policy_id": _policy_id(readiness, arm_id)},
        "split": {"root_lineage_id": plan.document["root_lineage_id"], "partition": "train"},
        "goal_manager": {
            "collection_id": readiness.pair_id,
            "assignment_id": f"{readiness.pair_id}-{arm_id}",
            "source_commit": readiness.source_commit,
            **{
                key: plan.document[key]
                for key in (
                    "context_catalog_sha256",
                    "context_id",
                    "binding_manifest_sha256",
                    "state_sha256",
                    "envelope_sha256",
                )
            },
        },
        "binding_manifest_scope": "original_catalog_origin_only; current profile separately bound",
    }


def _challenger_authority(readiness: _Readiness) -> GoalDecisionAuthority:
    if readiness.challenger_arm_id == LEARNED_ARM_ID:
        if (
            readiness.legacy_model is None
            or readiness.causal_record is not None
            or readiness.calibration_record is not None
        ):
            raise PairedRedBoundedPlayerRunError("challenger_model_identity")
        return LearnedGoalManagerPolicy(readiness.legacy_model)
    if readiness.challenger_arm_id == CAUSAL_ARM_ID:
        if (
            readiness.causal_record is None
            or readiness.legacy_model is not None
            or readiness.calibration_record is not None
        ):
            raise PairedRedBoundedPlayerRunError("challenger_model_identity")
        if readiness.training_plan is not None:
            return ExploringLivingDexGoalPolicy(
                readiness.causal_record.model,
                seed=cast(int, readiness.training_plan.document["seed"]),
            )
        return LivingDexGoalShadowPolicy(readiness.causal_record.model)
    if readiness.challenger_arm_id == CALIBRATION_ARM_ID:
        if (
            readiness.calibration_record is None
            or readiness.legacy_model is not None
            or readiness.causal_record is not None
        ):
            raise PairedRedBoundedPlayerRunError("challenger_model_identity")
        return LearnedGoalManagerPolicy(readiness.calibration_record.model)
    raise PairedRedBoundedPlayerRunError("challenger_identity")


def _policy_id(readiness: _Readiness, arm_id: str) -> str:
    if arm_id == BASELINE_ARM_ID:
        return BASELINE_ARM_ID
    if arm_id != readiness.challenger_arm_id:
        raise PairedRedBoundedPlayerRunError("arm_identity")
    if arm_id == LEARNED_ARM_ID:
        return f"goal-manager-{readiness.model_sha256[:16]}"
    if arm_id == CAUSAL_ARM_ID:
        suffix = (
            "-supported-exploration-economics-v2"
            if readiness.training_plan is not None
            else "-economics-v1"
            if readiness.quote_resource_costs
            else ""
        )
        return f"living-dex-goal-{readiness.model_sha256[:16]}{suffix}"
    if arm_id == CALIBRATION_ARM_ID:
        return f"calibration-goal-{readiness.model_sha256[:16]}"
    raise PairedRedBoundedPlayerRunError("challenger_identity")


def _player_limits(decision_limit: int, *, completion_dose: bool = False) -> BoundedPlayerLimits:
    if type(decision_limit) is not int or decision_limit not in {1, 2, 3, 4}:  # noqa: E721
        raise PairedRedBoundedPlayerRunError("decision_limit")
    from pokemon_red_completion.red_player_training_plan import (
        COMPLETION_ACTIONS,
        COMPLETION_FRAMES,
    )

    actions = COMPLETION_ACTIONS if completion_dose else 6_000
    frames = COMPLETION_FRAMES if completion_dose else 600_000
    return BoundedPlayerLimits(
        max_decisions=decision_limit,
        max_replans=decision_limit - 1,
        min_available_goals=2,
        max_actions_per_decision=actions,
        max_frames_per_decision=frames,
        max_total_actions=actions * decision_limit,
        max_total_frames=frames * decision_limit,
    )


def _action_free_preflight(readiness: _Readiness) -> dict[str, object]:
    adjacent_before = rom_adjacent_artifacts(readiness.rom_path)
    challenger = _challenger_authority(readiness)
    world = _route_world(readiness)
    with PyBoyAdapter(readiness.rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(readiness.capture.state_bytes)
        _verify_continuation_restore(readiness, emulator)
        initial_frame_count = emulator.frame_count
        controller = ReadOnlyController(emulator)
        reader = PokemonRedStateReader(controller)
        runtime = build_red_goal_context_runtime(
            profile=readiness.profile,
            capture=readiness.capture,
            emulator=controller,
            reader=reader,
        )
        actions = CountingExecutor(
            FrameSafeExecutor(controller, DEFAULT_NEW_GAME_TIMING.controller_timing())
        )
        meter = _ReadOnlyBudgetMeter(actions, emulator, initial_frame_count)
        result = preflight_red_bounded_player(
            observe=_player_observer(
                runtime, actions, world, readiness.quote_resource_costs,
                completion_dose=readiness.completion_dose,
            ),
            budget_meter=meter,
            assignment_id=readiness.pair_id,
            authorities=(
                (readiness.challenger_arm_id, challenger),
                (BASELINE_ARM_ID, CompletionFirstGoalTeacher()),
            ),
            allow_forced_bridge=readiness.continuation is not None,
        )
        if meter.checkpoint() != CompositionBudgetCheckpoint(0, 0):
            raise PairedRedBoundedPlayerRunError("preflight_budget")
    if rom_adjacent_artifacts(readiness.rom_path) != adjacent_before:
        raise PairedRedBoundedPlayerRunError("rom_adjacent_artifact")
    public = result.public_dict()
    if not result.choices:
        # The runtime already executes singleton bridges without model authority
        # or fit targets. A saved continuation must not demand a fictitious choice.
        public["status"] = "ready_for_forced_bridge"
        public["model_queries"] = 0
        return public
    if isinstance(challenger, LivingDexGoalShadowPolicy):
        if challenger.last_decision is None or challenger.decisions != 1:
            raise PairedRedBoundedPlayerRunError("causal_preflight_decision")
        public["living_dex_causal_shadow"] = {
            "decision": challenger.last_decision.public_dict(),
            "production_authority": False,
        }
    return public


def _require_safe_checkpoint_boundary(
    runtime: RedGoalContextRuntime,
    meter: CompositionIndependentBudgetMeter,
) -> None:
    before = meter.checkpoint()
    observation = runtime.adapter.observe()
    if meter.checkpoint() != before or not observation.input_ready or observation.raw.battle_state:
        raise PairedRedBoundedPlayerRunError("terminal_checkpoint_unsafe_boundary")


def _run_arm(
    readiness: _Readiness,
    *,
    arm_id: str,
    authority: GoalDecisionAuthority,
    viewer: BoundedPlayerDashboard | None = None,
) -> PairedBoundedPlayerArm:
    episode_id = _episode_id(readiness.pair_id, arm_id)
    limits = _player_limits(readiness.decision_limit, completion_dose=readiness.completion_dose)
    if readiness.continuation is not None:
        limits = replace(limits, allow_initial_forced_bridge=True)
    writer: EpisodeWriter | None = None
    sink: EpisodeTrajectorySink | None = None
    recorder: RecordingExecutor[Any, Any] | None = None
    terminal_checkpoint: dict[str, object] | None = None
    try:
        if viewer is not None:
            viewer.safely(
                "start_arm",
                learned=arm_id != BASELINE_ARM_ID,
                model_sha256=readiness.model_sha256,
                train_examples=(
                    readiness.causal_record.model.settled_examples
                    if readiness.causal_record is not None
                    else None
                ),
            )
        writer = readiness.private_root.begin_episode(episode_id)
        sink = EpisodeTrajectorySink(
            writer,
            episode_id=episode_id,
            game_id=GAME_ID,
            durable_writes=True,
        )
        sink.write_episode_header(
            metadata={
                **_context_scope(readiness),
                **_training_header(readiness, arm_id),
                **_continuation_header(readiness),
                "schema": "pokemon.red.paired-bounded-player-arm-header.v1",
                "pair_id": readiness.pair_id,
                "arm_id": arm_id,
                "source_commit": readiness.source_commit,
                "source_bundle_sha256": readiness.source_bundle_sha256,
                "rom_sha256": readiness.rom_sha256,
                "state_sha256": readiness.capture.state_sha256,
                "envelope_sha256": readiness.capture.envelope_sha256,
                "profile_sha256": readiness.profile.profile_sha256,
                "model_sha256": readiness.model_sha256,
                "continue_after_progress": readiness.continue_after_progress,
                "routed_resource_goals": readiness.routed_resource_goals,
                "quote_resource_costs": readiness.quote_resource_costs,
                "save_terminal_checkpoints": readiness.save_terminal_checkpoints,
                "teacher_queries": 0,
                "teacher_fallbacks": 0,
            }
        )
        with PyBoyAdapter(
            readiness.rom_path,
            watch=False,
            speed=None,
            frame_observer=viewer,
        ) as emulator:
            emulator.load_state_bytes(readiness.capture.state_bytes)
            _verify_continuation_restore(readiness, emulator)
            frames = WindowedFrameBudgetController(
                emulator,
                maximum_frames_per_window=limits.max_frames_per_decision,
                maximum_total_frames=limits.max_total_frames,
            )
            reader = PokemonRedStateReader(frames)
            runtime = build_red_goal_context_runtime(
                profile=readiness.profile,
                capture=readiness.capture,
                emulator=frames,
                reader=reader,
            )
            snapshot_provider = PokemonRedObservationEncoder.from_state_reader(reader)
            frame_safe = FrameSafeExecutor(
                frames,
                DEFAULT_NEW_GAME_TIMING.controller_timing(),
            )
            recorder = RecordingExecutor(
                delegate=frame_safe,
                snapshot_provider=snapshot_provider,
                sink=sink,
                episode_id=episode_id,
            )
            hard_actions = HardCompositionActionLimiter(
                recorder,
                maximum_actions_per_decision=limits.max_actions_per_decision,
                maximum_episode_actions=limits.max_total_actions,
            )
            actions = CountingExecutor(hard_actions)
            meter = CompositionIndependentBudgetMeter(hard_actions, frames)
            if viewer is not None:
                viewer.safely("bind_budget", meter.checkpoint)
            search_memory = _execution_search_memory(readiness)
            def retain_quantum() -> None:
                from pokemon_red_completion.red_player_checkpoint import capture_red_skill_recovery

                _require_safe_checkpoint_boundary(runtime, meter)
                writer.append(
                    "skill_recovery",
                    capture_red_skill_recovery(emulator=emulator, meter=meter),
                    durable=True,
                )

            observer = _LiveObserver(
                runtime=runtime,
                actions=actions,
                meter=meter,
                viewer=viewer,
                route_world=_route_world(readiness),
                quote_resource_costs=readiness.quote_resource_costs,
                maximum_actions_per_decision=limits.max_actions_per_decision,
                search_memory=search_memory,
                completion_dose=readiness.completion_dose,
                retain_quantum=retain_quantum if readiness.save_terminal_checkpoints else None,
            )
            trajectory_class = (
                ViewerGoalTrajectory
                if readiness.training_plan is None
                else RedPlayerTrainingTrajectory
            )
            training_kwargs: dict[str, Any] = (
                {}
                if readiness.training_plan is None
                else {
                    "observe_training": runtime.adapter.observe,
                    "training_meter": meter,
                    "training_plan_sha256": readiness.training_plan.plan_sha256,
                    "maximum_actions": limits.max_actions_per_decision,
                    "maximum_frames": limits.max_frames_per_decision,
                }
            )
            if readiness.continuation is not None and not readiness.continuation_root_lineage_id:
                raise PairedRedBoundedPlayerRunError("continuation_root_lineage")
            trajectory = trajectory_class(
                episode_id=episode_id,
                root_lineage_id=cast(str, readiness.training_plan.document["root_lineage_id"])
                if readiness.training_plan is not None
                else cast(str, readiness.continuation_root_lineage_id)
                if readiness.continuation is not None
                else canonical_sha256(
                    {
                        "schema": "pokemon.red.paired-bounded-player-root.v1",
                        "state_sha256": readiness.capture.state_sha256,
                        "envelope_sha256": readiness.capture.envelope_sha256,
                    }
                ),
                partition="train"
                if (readiness.training_plan is not None or readiness.continuation is not None)
                else "development",
                environment_id=GAME_ID,
                actor=arm_id,
                policy_id=_policy_id(readiness, arm_id),
                collection_id=readiness.pair_id,
                assignment_id=f"{readiness.pair_id}-{arm_id}",
                ordering_assignment_id=readiness.pair_id,
                source_commit=readiness.source_commit,
                snapshot_provider=snapshot_provider,
                recorder=recorder,
                sink=sink,
                viewer=viewer,
                displayed_authority=authority,
                learned_actor=arm_id != BASELINE_ARM_ID,
                **training_kwargs,
            )
            component_failures = 0

            def record_component_failure(error: BaseException) -> None:
                nonlocal component_failures
                component_failures += 1
                # These are private trajectory diagnostics, never policy inputs
                # or public comparison claims. Sink failure must stop recovery.
                assert sink is not None and recorder is not None
                sink.record_event(
                    SparseEvent(
                        event_id=f"{episode_id}:component-failure:{component_failures}",
                        episode_id=episode_id,
                        step_index=recorder.next_step_index,
                        kind="component_failure",
                        payload=cast(
                            Mapping[str, JSONValue],
                            {"private_diagnostic": private_failure_diagnostic(error)},
                        ),
                    )
                )

            result = run_bounded_player_episode(
                observe=observer,
                authority=authority,
                authority_id=arm_id,
                trajectory=trajectory,
                budget_meter=meter,
                completion_satisfied=_completion_predicate(readiness),
                limits=limits,
                failure_observer=record_component_failure,
                search_memory=search_memory,
            )
            if recorder.recording_failures:
                raise PairedRedBoundedPlayerRunError("trajectory_durability")
            if readiness.save_terminal_checkpoints:
                _require_safe_checkpoint_boundary(runtime, meter)
                terminal_checkpoint = capture_red_player_terminal(
                    emulator=emulator,
                    meter=meter,
                    observe=observer,
                    search_memory=search_memory,
                    parent=readiness.capture,
                    result=result,
                    episode_id=episode_id,
                    profile_sha256=readiness.profile.profile_sha256,
                    rom_sha256=readiness.rom_sha256,
                    model_sha256=readiness.model_sha256,
                    source_commit=readiness.source_commit,
                    source_bundle_sha256=readiness.source_bundle_sha256,
                    context_origin=readiness.context_origin,
                )
                writer.append("checkpoint", terminal_checkpoint, durable=True)
        starting = observer.starting_observation
        if starting is None:
            raise PairedRedBoundedPlayerRunError("starting_observation")
        sink.record_event(
            SparseEvent(
                event_id=f"{episode_id}:terminal",
                episode_id=episode_id,
                step_index=recorder.next_step_index,
                kind="terminal",
                payload={
                    "status": "complete",
                    "bounded_player": cast(Mapping[str, JSONValue], result.public_dict()),
                },
            )
        )
        sink.finalize()
        artifact = writer.complete()
        if terminal_checkpoint is not None:
            publish_red_player_checkpoint(readiness.private_root, terminal_checkpoint)
        if viewer is not None:
            viewer.safely("finished", result)
        return PairedBoundedPlayerArm(
            arm_id=arm_id,
            starting_state_sha256=readiness.capture.state_sha256,
            starting_semantic_state_sha256=starting.semantic_state_sha256,
            starting_collection=starting.collection,
            trajectory_manifest_sha256=artifact.manifest_sha256,
            episode=result,
        )
    except BaseException as error:
        if viewer is not None:
            viewer.safely("failed")
        _retain_failure(
            writer,
            sink=sink,
            recorder=recorder,
            episode_id=episode_id,
            error=error,
        )
        raise


def _retain_failure(
    writer: EpisodeWriter | None,
    *,
    sink: EpisodeTrajectorySink | None,
    recorder: RecordingExecutor[Any, Any] | None,
    episode_id: str,
    error: BaseException,
) -> None:
    if writer is None:
        return
    failure_class = (
        "external_interruption"
        if isinstance(error, (KeyboardInterrupt, SystemExit))
        else "bounded_player_failure"
    )
    with suppress(BaseException):
        if sink is not None:
            sink.record_event(
                SparseEvent(
                    event_id=f"{episode_id}:terminal",
                    episode_id=episode_id,
                    step_index=0 if recorder is None else recorder.next_step_index,
                    kind="terminal",
                    payload=cast(
                        Mapping[str, JSONValue],
                        {
                            "status": "failed",
                            "failure_class": failure_class,
                            "private_diagnostic": private_failure_diagnostic(error),
                        },
                    ),
                )
            )
            sink.finalize()
        else:
            writer.append(
                "terminal",
                {
                    "schema": "pokemon.red.paired-bounded-player-terminal.v1",
                    "status": "failed",
                    "failure_class": failure_class,
                    "private_diagnostic": private_failure_diagnostic(error),
                },
                durable=True,
            )
    with suppress(BaseException):
        writer.abort("paired_arm_failed")


def _write_exclusive(path: Path, document: Mapping[str, object]) -> None:
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("ascii")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        with suppress(OSError):
            path.unlink()
        raise


def _run(args: argparse.Namespace) -> dict[str, object]:
    readiness = _prepare(args)
    protected_before = {
        str(index): _sha256(path) for index, path in enumerate(readiness.protected_paths)
    }
    adjacent_before = rom_adjacent_artifacts(readiness.rom_path)
    preflight = _action_free_preflight(readiness)
    challenger_authority = _challenger_authority(readiness)
    if readiness.training_plan is not None:
        readiness.private_root.publish_sealed_record(
            f"rp-plan-{readiness.training_plan.plan_sha256}",
            kind="red_player_training_plan",
            record=dict(readiness.training_plan.document),
        )
    with ExitStack() as resources:
        viewer = None
        if readiness.dashboard_port is not None:
            state = DashboardState()
            viewer = BoundedPlayerDashboard(state, decision_limit=readiness.decision_limit)
            dashboard = resources.enter_context(
                ProgressDashboardServer(state, port=readiness.dashboard_port)
            )
            print(
                json.dumps({"dashboard_url": dashboard.url, "status": "bounded_play_starting"}),
                flush=True,
            )
        learned = _run_arm(
            readiness,
            arm_id=readiness.challenger_arm_id,
            authority=challenger_authority,
            viewer=viewer,
        )
        comparison_document: dict[str, object]
        if readiness.continuation is not None and readiness.training_plan is None:
            comparison_document = {
                "schema": "pokemon.red.bounded-player-continuation-result.v1",
                **_continuation_header(readiness),
                "episode_id": _episode_id(readiness.pair_id, readiness.challenger_arm_id),
                "trajectory_manifest_sha256": learned.trajectory_manifest_sha256,
                "episode": learned.episode.public_dict(),
                "model_fitted": False,
                "independent_evaluation": False,
            }
        elif readiness.training_plan is None:
            baseline = _run_arm(
                readiness,
                arm_id=BASELINE_ARM_ID,
                authority=CompletionFirstGoalTeacher(),
                viewer=viewer,
            )
            comparison: PairedBoundedPlayerComparison = compare_paired_bounded_player_arms(
                pair_id=readiness.pair_id, learned=learned, baseline=baseline
            )
            comparison_document = comparison.public_dict()
        else:
            comparison_document = {
                "schema": "pokemon.red.bounded-player-training-result.v1",
                **_continuation_header(readiness),
                "episode_id": _episode_id(readiness.pair_id, readiness.challenger_arm_id),
                "plan_sha256": readiness.training_plan.plan_sha256,
                "trajectory_manifest_sha256": learned.trajectory_manifest_sha256,
                "episode": learned.episode.public_dict(),
                "model_fitted": False,
                "independent_evaluation": False,
            }
    protected_after = {
        str(index): _sha256(path) for index, path in enumerate(readiness.protected_paths)
    }
    if protected_after != protected_before:
        raise PairedRedBoundedPlayerRunError("protected_input_changed")
    if rom_adjacent_artifacts(readiness.rom_path) != adjacent_before:
        raise PairedRedBoundedPlayerRunError("rom_adjacent_artifact")
    summary = {
        **comparison_document,
        **_context_scope(readiness),
        "preflight": preflight,
        "source_commit": readiness.source_commit,
        "source_bundle_sha256": readiness.source_bundle_sha256,
        "rom_sha256": readiness.rom_sha256,
        "model_file_sha256": readiness.model_file_sha256,
        "model_sha256": readiness.model_sha256,
        "challenger_arm_id": readiness.challenger_arm_id,
        "decision_limit": readiness.decision_limit,
        "continue_after_progress": readiness.continue_after_progress,
        "routed_resource_goals": readiness.routed_resource_goals,
        "quote_resource_costs": readiness.quote_resource_costs,
        "viewer_instrumentation_failures": 0 if viewer is None else viewer.failure_count,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "full_game_replays": 0,
    }
    if readiness.save_terminal_checkpoints:
        checkpoint_summaries = []
        for arm_id in (
            (readiness.challenger_arm_id,)
            if readiness.training_plan is not None or readiness.continuation is not None
            else (readiness.challenger_arm_id, BASELINE_ARM_ID)
        ):
            record = readiness.private_root.find_sealed_record(
                checkpoint_record_id(_episode_id(readiness.pair_id, arm_id)),
                expected_kind=CHECKPOINT_KIND,
            )
            if record is None:
                raise PairedRedBoundedPlayerRunError("terminal_checkpoint_missing")
            checkpoint_summaries.append(
                {
                    "arm_id": arm_id,
                    "record_sha256": record.summary.record_sha256,
                    "independent_root": False,
                    "training_example": False,
                    "automatic_resume_authorized": False,
                }
            )
        summary["terminal_checkpoints"] = checkpoint_summaries
    if readiness.causal_record is not None:
        if not isinstance(challenger_authority, LivingDexGoalShadowPolicy):
            raise PairedRedBoundedPlayerRunError("challenger_model_identity")
        if challenger_authority.last_decision is None:
            raise PairedRedBoundedPlayerRunError("causal_outcome_decision")
        summary["living_dex_causal_shadow"] = {
            "counts_include_unexecuted_proposals": True,
            "settled_authority_goal_count": learned.episode.authority_decisions,
            "unexecuted_proposal_count": (
                challenger_authority.decisions - learned.episode.authority_decisions
            ),
            "decision_count": challenger_authority.decisions,
            "decisions": [
                decision.public_dict() for decision in challenger_authority.decision_history
            ],
            "deterministic_decision_count": challenger_authority.deterministic_decisions,
            "model_decision_count": challenger_authority.model_decisions,
            "model_record": readiness.causal_record.public_dict(),
            "production_authority": False,
        }
    if readiness.calibration_record is not None:
        summary["multi_goal_calibration_shadow"] = {
            "model_record": readiness.calibration_record.public_dict(),
            "production_authority": False,
            "same_bank_diagnostic_only": True,
        }
    _write_exclusive(readiness.output_path, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        summary = _run(parser.parse_args(argv))
    except Exception:
        parser.error("paired Red bounded-player run failed closed; private paths were withheld")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
