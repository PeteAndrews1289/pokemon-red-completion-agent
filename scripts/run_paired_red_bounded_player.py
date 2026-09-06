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
from collections.abc import Mapping
from contextlib import ExitStack, suppress
from dataclasses import dataclass
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
from pokemon_red_completion.living_dex_goal_model_record import (  # noqa: E402
    LivingDexGoalModelRecord,
    load_living_dex_goal_model_record,
)
from pokemon_red_completion.living_dex_goal_policy import (  # noqa: E402
    LivingDexGoalShadowPolicy,
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
    load_red_goal_context_profile,
)
from pokemon_red_completion.red_trajectory import (  # noqa: E402
    PokemonRedObservationEncoder,
)
from pokemon_red_completion.rom import resolve_rom_path, verify_rom  # noqa: E402
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts  # noqa: E402
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
    causal_record: LivingDexGoalModelRecord | None
    calibration_record: MultiGoalCalibrationModel | None
    model_file_sha256: str
    model_sha256: str
    decision_limit: int
    private_root: PrivateArtifactRoot
    output_path: Path
    protected_paths: tuple[Path, ...]
    continue_after_progress: bool = False
    dashboard_port: int | None = None


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

    def __call__(self) -> GoalManagerCompositionObservation:
        if self.observations:
            self.meter.begin_decision_window()
        before = self.meter.checkpoint()
        deferred = _DeferredActionExecutor(self.actions)
        bridge = RedBoundedPlayerObserver(
            runtime=self.runtime,
            actions=CountingExecutor(deferred),
        )
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
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
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
    causal_record: LivingDexGoalModelRecord | None = None
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
    for arm_id in (args.challenger, BASELINE_ARM_ID):
        episode_id = _episode_id(args.pair_id, arm_id)
        if private_root.inspect_episode_state(episode_id).status != "absent":
            raise PairedRedBoundedPlayerRunError("pair_id_already_used")
    return _Readiness(
        pair_id=args.pair_id,
        source_commit=source.git_commit,
        source_bundle_sha256=working_source_bundle_sha256(PROJECT_ROOT),
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
        return f"living-dex-goal-{readiness.model_sha256[:16]}"
    if arm_id == CALIBRATION_ARM_ID:
        return f"calibration-goal-{readiness.model_sha256[:16]}"
    raise PairedRedBoundedPlayerRunError("challenger_identity")


def _player_limits(decision_limit: int) -> BoundedPlayerLimits:
    if type(decision_limit) is not int or decision_limit not in {1, 2, 3, 4}:  # noqa: E721
        raise PairedRedBoundedPlayerRunError("decision_limit")
    return BoundedPlayerLimits(
        max_decisions=decision_limit,
        max_replans=decision_limit - 1,
        min_available_goals=2,
        max_actions_per_decision=6_000,
        max_frames_per_decision=600_000,
        max_total_actions=6_000 * decision_limit,
        max_total_frames=600_000 * decision_limit,
    )


def _action_free_preflight(readiness: _Readiness) -> dict[str, object]:
    adjacent_before = rom_adjacent_artifacts(readiness.rom_path)
    challenger = _challenger_authority(readiness)
    with PyBoyAdapter(readiness.rom_path, watch=False, speed=None) as emulator:
        emulator.load_state_bytes(readiness.capture.state_bytes)
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
            observe=RedBoundedPlayerObserver(runtime=runtime, actions=actions),
            budget_meter=meter,
            assignment_id=readiness.pair_id,
            authorities=(
                (readiness.challenger_arm_id, challenger),
                (BASELINE_ARM_ID, CompletionFirstGoalTeacher()),
            ),
        )
        if meter.checkpoint() != CompositionBudgetCheckpoint(0, 0):
            raise PairedRedBoundedPlayerRunError("preflight_budget")
    if rom_adjacent_artifacts(readiness.rom_path) != adjacent_before:
        raise PairedRedBoundedPlayerRunError("rom_adjacent_artifact")
    public = result.public_dict()
    if isinstance(challenger, LivingDexGoalShadowPolicy):
        if challenger.last_decision is None or challenger.decisions != 1:
            raise PairedRedBoundedPlayerRunError("causal_preflight_decision")
        public["living_dex_causal_shadow"] = {
            "decision": challenger.last_decision.public_dict(),
            "production_authority": False,
        }
    return public


def _run_arm(
    readiness: _Readiness,
    *,
    arm_id: str,
    authority: GoalDecisionAuthority,
    viewer: BoundedPlayerDashboard | None = None,
) -> PairedBoundedPlayerArm:
    episode_id = _episode_id(readiness.pair_id, arm_id)
    limits = _player_limits(readiness.decision_limit)
    writer: EpisodeWriter | None = None
    sink: EpisodeTrajectorySink | None = None
    recorder: RecordingExecutor[Any, Any] | None = None
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
            observer = _LiveObserver(runtime=runtime, actions=actions, meter=meter, viewer=viewer)
            trajectory = ViewerGoalTrajectory(
                episode_id=episode_id,
                root_lineage_id=canonical_sha256(
                    {
                        "schema": "pokemon.red.paired-bounded-player-root.v1",
                        "state_sha256": readiness.capture.state_sha256,
                        "envelope_sha256": readiness.capture.envelope_sha256,
                    }
                ),
                partition="development",
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
            )
            result = run_bounded_player_episode(
                observe=observer,
                authority=authority,
                authority_id=arm_id,
                trajectory=trajectory,
                budget_meter=meter,
                completion_satisfied=_completion_predicate(readiness),
                limits=limits,
            )
            if recorder.recording_failures:
                raise PairedRedBoundedPlayerRunError("trajectory_durability")
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
                    payload={"status": "failed", "failure_class": failure_class},
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
        baseline = _run_arm(
            readiness,
            arm_id=BASELINE_ARM_ID,
            authority=CompletionFirstGoalTeacher(),
            viewer=viewer,
        )
    comparison: PairedBoundedPlayerComparison = compare_paired_bounded_player_arms(
        pair_id=readiness.pair_id,
        learned=learned,
        baseline=baseline,
    )
    protected_after = {
        str(index): _sha256(path) for index, path in enumerate(readiness.protected_paths)
    }
    if protected_after != protected_before:
        raise PairedRedBoundedPlayerRunError("protected_input_changed")
    if rom_adjacent_artifacts(readiness.rom_path) != adjacent_before:
        raise PairedRedBoundedPlayerRunError("rom_adjacent_artifact")
    summary = {
        **comparison.public_dict(),
        "preflight": preflight,
        "source_commit": readiness.source_commit,
        "source_bundle_sha256": readiness.source_bundle_sha256,
        "rom_sha256": readiness.rom_sha256,
        "model_file_sha256": readiness.model_file_sha256,
        "model_sha256": readiness.model_sha256,
        "challenger_arm_id": readiness.challenger_arm_id,
        "decision_limit": readiness.decision_limit,
        "continue_after_progress": readiness.continue_after_progress,
        "viewer_instrumentation_failures": 0 if viewer is None else viewer.failure_count,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "full_game_replays": 0,
    }
    if readiness.causal_record is not None:
        if not isinstance(challenger_authority, LivingDexGoalShadowPolicy):
            raise PairedRedBoundedPlayerRunError("challenger_model_identity")
        if challenger_authority.last_decision is None:
            raise PairedRedBoundedPlayerRunError("causal_outcome_decision")
        summary["living_dex_causal_shadow"] = {
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
