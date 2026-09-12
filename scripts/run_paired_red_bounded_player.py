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
from pokemon_red_completion.forward_goal import ForwardGoalPlan  # noqa: E402
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
    GoalBindingSet,
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
from pokemon_red_completion.red_forward_goal import (  # noqa: E402
    RED_FORWARD_EXECUTION_FLAGS,
    RedForwardGoalCollector,
    red_forward_context,
    red_forward_continuation_sha256,
    red_forward_goal_observed,
    red_forward_verifier_sha256,
)
from pokemon_red_completion.red_forward_probe import RedForwardProbeSpec  # noqa: E402
from pokemon_red_completion.red_forward_training import RedForwardTrainingTrajectory  # noqa: E402
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
from pokemon_red_completion.red_regional_goal_proposal import (  # noqa: E402
    load_regional_proposal_profile,
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
FORWARD_PROBE_ARM_ID = "forward-first-choice-training-probe"
_CHALLENGER_IDS = (LEARNED_ARM_ID, CAUSAL_ARM_ID, CALIBRATION_ARM_ID)
_PAIR_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,47}\Z")
# Historical references, not controller authority. A living collection can need
# hundreds of source/objective revisits; retain them instead of truncating history.
# Per-episode decision/action/frame limits and ordered authentication are unchanged.
_MAX_REGIONAL_TRANSITIONS = 512


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
    restore_completion_dose: bool = False
    restore_routed_recovery: bool = False
    restore_trainer_funding: bool = False
    restore_trainer_pending_recovery: bool = False
    restore_regional_trainer_funding: bool = False
    restore_observed_trainer_funding: bool = False
    completion_dose: bool = False
    routed_recovery: bool = False
    trainer_funding: bool = False
    trainer_pending_recovery: bool = False
    regional_trainer_funding: bool = False
    observed_trainer_funding: bool = False
    regional_choice_record_sha256: str | None = None
    regional_proposal_record_sha256: str | None = None
    remaining_acquisition_demand: bool = False
    restore_remaining_acquisition_demand: bool = False
    level_evolution_acquisitions: bool = False
    restore_level_evolution_acquisitions: bool = False
    forward_story_objective: str | None = None
    forward_resource_budget: int | None = None
    registration_policy: Any = None
    registration_ledger: Path | None = None
    registration_session_record_id: str | None = None
    registration_sequence: int | None = None
    restore_registration_record_id: str | None = None


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
    routed_recovery: bool = False
    trainer_funding: bool = False
    trainer_pending_recovery: bool = False
    regional_trainer_funding: bool = False
    observed_trainer_funding: bool = False
    retain_quantum: Callable[[], None] | None = None
    remaining_acquisition_demand: bool = False
    level_evolution_acquisitions: bool = False

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
            routed_recovery=self.routed_recovery,
            trainer_funding=self.trainer_funding,
            trainer_pending_recovery=self.trainer_pending_recovery,
            regional_trainer_funding=self.regional_trainer_funding,
            observed_trainer_funding=self.observed_trainer_funding,
            remaining_acquisition_demand=self.remaining_acquisition_demand,
            level_evolution_acquisitions=self.level_evolution_acquisitions,
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
    routed_recovery: bool = False,
    trainer_funding: bool = False,
    trainer_pending_recovery: bool = False,
    regional_trainer_funding: bool = False,
    observed_trainer_funding: bool = False,
    remaining_acquisition_demand: bool = False,
    level_evolution_acquisitions: bool = False,
    retain_quantum: Callable[[], None] | None = None,
    forward_story_only: bool = False,
) -> RedBoundedPlayerObserver:
    from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic

    if world is not None and any(
        spec.parameters.get("trainer_objective")
        in {"defeat_lorelei", "defeat_bruno", "defeat_agatha", "defeat_lance", "defeat_champion"}
        for spec in runtime.profile.providers
    ):
        runtime = replace(runtime, trainer_story_world=world)
    if type(remaining_acquisition_demand) is not bool:
        raise PairedRedBoundedPlayerRunError("remaining_acquisition_demand_type")
    if remaining_acquisition_demand or getattr(runtime, "remaining_acquisition_demand", False):
        runtime = replace(runtime, remaining_acquisition_demand=remaining_acquisition_demand)
    if type(level_evolution_acquisitions) is not bool or (
        level_evolution_acquisitions and (not remaining_acquisition_demand or world is None)
    ):
        raise PairedRedBoundedPlayerRunError("level_evolution_acquisitions_scope")
    if level_evolution_acquisitions:
        from pokemon_red_completion.red_acquisition_alternatives import (
            cartridge_level_acquisition_edges,
        )

        assert world is not None
        runtime = replace(
            runtime,
            level_evolution_acquisition_edges=cartridge_level_acquisition_edges(world.rom),
        )
    elif getattr(runtime, "level_evolution_acquisition_edges", ()):
        runtime = replace(runtime, level_evolution_acquisition_edges=())
    if world is not None and any(
        s.mechanic is RedGoalMechanic.TARGETED_LEVEL_EVOLUTION for s in runtime.profile.providers
    ):
        from pokemon_red_completion.red_native_boxed_evolution import bind_native_boxed_evolution

        runtime = bind_native_boxed_evolution(
            runtime,
            world,
            maximum_quanta=128 if completion_dose else 1,
            retain_quantum=retain_quantum,
            allow_cross_box=completion_dose,
        )
    router = (
        None
        if world is None
        else RedResourceGoalRouter(
            runtime,
            actions,
            world,
            quote_resource_costs=quote_resource_costs,
            prepare_capture_storage=completion_dose,
            routed_recovery=routed_recovery,
            trainer_funding=trainer_funding,
            trainer_pending_recovery=trainer_pending_recovery,
            regional_trainer_funding=regional_trainer_funding,
            observed_trainer_funding=observed_trainer_funding,
            maximum_controller_actions=30_000 if completion_dose else 6_000,
            maximum_emulator_frames=3_000_000 if completion_dose else 600_000,
        )
    )

    def enumerate_forward(observation: Any) -> Any:
        bindings = (
            runtime.enumerator(actions).enumerate(observation)
            if router is None
            else router.enumerate(observation)
        )
        _require_forward_binding_scope(bindings, runtime.profile)
        return bindings

    observer = RedBoundedPlayerObserver(
        runtime=runtime,
        actions=actions,
        enumerate_bindings=(
            enumerate_forward
            if forward_story_only
            else None
            if router is None
            else router.enumerate
        ),
        registered_objective=getattr(runtime, "registration_policy", None) is not None,
    )
    if completion_dose:
        from pokemon_red_completion.goal_manager_composition_qualification import (
            living_completion_checkpoint,
        )

        observer.collection_projector = living_completion_checkpoint
    return observer


def _require_forward_binding_scope(
    bindings: GoalBindingSet,
    profile: RedGoalContextProfile,
) -> None:
    """Reject the whole menu if routing added a different execution mechanic.

    These private identities are never model features. Exact profile/configuration
    suffixes are added by the direct provider and are absent from routed Center,
    funding and capture bindings. Keep inherited capabilities and unavailable
    alternatives intact; do not manufacture a menu by filtering them away.
    """
    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic

    allowed = {
        (spec.kind, f":profile-{profile.profile_sha256}:config-{spec.configuration_sha256}")
        for spec in profile.providers
        if (spec.kind is GoalKind.ADVANCE_STORY and spec.mechanic is RedGoalMechanic.MIDGAME_STORY)
        or (
            spec.kind is GoalKind.RESTORE_TEAM
            and spec.mechanic
            in {
                RedGoalMechanic.FIELD_RESTORE,
                RedGoalMechanic.FIELD_PP_RESTORE,
            }
        )
    }
    if any(
        not any(
            binding.kind is kind and binding.binding_ref.endswith(suffix)
            for kind, suffix in allowed
        )
        for binding in bindings.bindings
    ):
        raise PairedRedBoundedPlayerRunError("forward_goal_unsupported_binding")


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
    parser.add_argument("--registered-ledger", type=Path, default=None)
    parser.add_argument("--registration-session", default=None)
    parser.add_argument("--economy-training", action="store_true",
                        help="Opt in to recorded cash outcomes with a feature-v4 model.")
    parser.add_argument("--registration-run-id", default=None)
    parser.add_argument(
        "--remaining-acquisition-demand",
        action="store_true",
        help="credit retained evolved/traded forms after historical continuation restore",
    )
    parser.add_argument(
        "--level-evolution-acquisitions",
        action="store_true",
        help="offer spare-precursor captures using cartridge level rules and actual living stock",
    )
    parser.add_argument(
        "--routed-recovery",
        action="store_true",
        help="enable guarded walking-to-Center recovery after verified continuation restore",
    )
    parser.add_argument(
        "--trainer-funding",
        action="store_true",
        help="offer finite ordinary trainer income after authenticated training continuation",
    )
    parser.add_argument(
        "--trainer-pending-recovery",
        action="store_true",
        help="resume an already-armed trainer battle after authenticating the legacy endpoint",
    )
    parser.add_argument(
        "--regional-trainer-funding",
        action="store_true",
        help="extend funding to inventoried adjacent maps through walking-only connections",
    )
    parser.add_argument(
        "--observed-trainer-funding",
        action="store_true",
        help="qualify new funding menus against observed current-map terrain",
    )
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
    parser.add_argument(
        "--capture-access-requirements", dest="regional_transitions",
        action="append_const", const="capture-access-requirements",
        help="prospective item prerequisites for capture destinations",
    )
    parser.add_argument(
        "--travel-capture", dest="regional_transitions", action="append_const",
        const="travel-capture", help="prospective registered capture during acquisition travel",
    )
    parser.add_argument(
        "--observed-local-capture",
        dest="regional_transitions",
        action="append_const",
        const="observed-local-capture",
        help="prospective current-map encounter patch from actual reachable terrain",
    )
    parser.add_argument(
        "--indoor-fly-departure",
        dest="regional_transitions",
        action="append_const",
        const="indoor-fly-departure",
        help="prospective indoor departure before Fly; preserves prior checkpoint menus",
    )
    parser.add_argument(
        "--resupply-fly-transport", dest="regional_transitions", action="append_const",
        const="resupply-fly", help="opt future Mart supply into observed indoor exit and Fly",
    )
    parser.add_argument(
        "--dig-recovery", dest="regional_transitions", action="append_const",
        const="dig-recovery", help="opt future recovery into observed legal Dig escape",
    )
    parser.add_argument(
        "--capture-surf-transport", dest="regional_transitions", action="append_const",
        const="capture-surf", help="opt future capture routes into observed Surf access",
    )
    parser.add_argument(
        "--capture-cut-transport",
        dest="regional_transitions",
        action="append_const",
        const="capture-cut",
        help="opt future capture routes into observed land-only Cut access",
    )
    parser.add_argument(
        "--capture-fly-transport",
        dest="regional_transitions",
        action="append_const",
        const="capture-fly",
        help="opt future wild capture destinations into guarded Fly access",
    )
    parser.add_argument(
        "--evolution-fly-transport",
        dest="regional_transitions",
        action="append_const",
        const="evolution-fly",
        help="opt the current evolution objective into guarded Fly access",
    )
    parser.add_argument(
        "--evolution-objective",
        dest="regional_transitions",
        action="append",
        type=_evolution_objective_argument,
        help="ordered future boxed evolution SOURCE:TARGET:LEVEL; preserves earlier profiles",
    )
    parser.add_argument(
        "--wild-source",
        dest="regional_transitions",
        action="append",
        default=[],
        help="ordered cartridge-derived grass-source profile transitions for saved continuations",
    )
    parser.add_argument(
        "--supply-profile",
        dest="regional_transitions",
        type=Path,
        action="append",
        help="ordered private profile transition changing only the existing Mart supply skill",
    )
    parser.add_argument(
        "--warp-safe-wild-source",
        dest="regional_transitions",
        action="append",
        type=lambda value: f"warp-safe:{value}",
        help="registered corridor transition excluding warps; preserves older source declarations",
    )
    parser.add_argument(
        "--discovery-source",
        dest="regional_transitions",
        action="append",
        type=lambda value: f"discovery:{value}",
        help="explicit source-local sighting coverage from the authenticated cartridge",
    )
    parser.add_argument(
        "--opportunistic-capture",
        dest="regional_transitions",
        action="append_const",
        const="opportunistic-capture",
        help="Accept useful local cartridge grass encounters, not canonical targets only.",
    )
    parser.add_argument(
        "--capture-status-support",
        dest="regional_transitions",
        action="append_const",
        const="capture-status",
        help="explicit opt-in to bounded observed non-damaging capture status preparation",
    )
    parser.add_argument(
        "--capture-search-budget", dest="regional_transitions", action="append_const",
        const="capture-search-budget",
        help="prospective up-to160-leg captures; reserves encounter handling within action caps",
    )
    parser.add_argument(
        "--affordable-capture-supply",
        dest="regional_transitions",
        action="append_const",
        const="affordable-capture-supply",
        help="explicit cash-only bounded ball purchases; no sale or increased batch cap",
    )
    parser.add_argument("--expected-training-catalog-sha256", default=None)
    parser.add_argument(
        "--resource-choice-variants", dest="regional_transitions", action="append_const",
        const="resource-choice-variants",
        help="explicit useful-reserve earning choice beside an affordable capture purchase",
    )
    parser.add_argument(
        "--composable-trainer-funding",
        dest="regional_transitions",
        action="append_const",
        const="composable-trainer-funding",
        help="allow multiple finite trainer payouts to compose toward a capture reserve",
    )
    parser.add_argument(
        "--mart-funding-departure", dest="regional_transitions", action="append_const",
        const="mart-funding-departure",
        help="explicit observed exit from the declared Mart for bounded trainer funding",
    )
    parser.add_argument(
        "--funding-fly-transport", dest="regional_transitions", action="append_const",
        const="funding-fly",
        help="explicit observed Fly to bounded ordinary trainer income; not a League replay",
    )
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
    parser.add_argument(
        "--story-outcome-curriculum",
        action="store_true",
        help="Record forced story outcomes separately from choices (completion dose only).",
    )
    parser.add_argument(
        "--forward-story-objective",
        default=None,
        help="Record separate forward story outcomes; no new model authority.",
    )
    parser.add_argument(
        "--forward-resource-budget",
        type=int,
        default=None,
        help="Explicit total consumable allowance for the forward story attempt.",
    )
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
    wild_sources = getattr(args, "regional_transitions", getattr(args, "wild_source", ()))
    if (
        not isinstance(wild_sources, (list, tuple))
        or len(wild_sources) > _MAX_REGIONAL_TRANSITIONS
        or any(not isinstance(source, (str, Path)) for source in wild_sources)
        or (
            wild_sources
            and (not continuation_chain or not getattr(args, "routed_resource_goals", False))
        )
    ):
        raise PairedRedBoundedPlayerRunError("regional_profile_scope")
    if type(expand_local) is not bool or (expand_local and not continuation_chain):
        raise PairedRedBoundedPlayerRunError("profile_transition_scope")
    boxed_evolution = getattr(args, "boxed_evolution", None)
    remaining_acquisition_demand = getattr(args, "remaining_acquisition_demand", False)
    if type(remaining_acquisition_demand) is not bool or (
        remaining_acquisition_demand and not continuation_chain
    ):
        raise PairedRedBoundedPlayerRunError("remaining_acquisition_demand_scope")
    level_evolution_acquisitions = getattr(args, "level_evolution_acquisitions", False)
    if type(level_evolution_acquisitions) is not bool or (
        level_evolution_acquisitions
        and (not remaining_acquisition_demand or not getattr(args, "routed_resource_goals", False))
    ):
        raise PairedRedBoundedPlayerRunError("level_evolution_acquisitions_scope")
    routed_recovery = getattr(args, "routed_recovery", False)
    if type(routed_recovery) is not bool or (
        routed_recovery
        and (not getattr(args, "routed_resource_goals", False) or not continuation_chain)
    ):
        raise PairedRedBoundedPlayerRunError("routed_recovery_scope")
    trainer_funding = getattr(args, "trainer_funding", False)
    regional_trainer_funding = getattr(args, "regional_trainer_funding", False)
    if type(regional_trainer_funding) is not bool or (
        regional_trainer_funding and not trainer_funding
    ):
        raise PairedRedBoundedPlayerRunError("regional_trainer_funding_scope")
    observed_trainer_funding = getattr(args, "observed_trainer_funding", False)
    if type(observed_trainer_funding) is not bool or (
        observed_trainer_funding and not trainer_funding
    ):
        raise PairedRedBoundedPlayerRunError("observed_trainer_funding_scope")
    trainer_pending_recovery = getattr(args, "trainer_pending_recovery", False)
    if type(trainer_pending_recovery) is not bool or (
        trainer_pending_recovery and not trainer_funding
    ):
        raise PairedRedBoundedPlayerRunError("trainer_pending_recovery_scope")
    if type(trainer_funding) is not bool or (
        trainer_funding
        and (
            not getattr(args, "routed_resource_goals", False)
            or not continuation_chain
            or not getattr(args, "train_player", False)
        )
    ):
        raise PairedRedBoundedPlayerRunError("trainer_funding_scope")
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
            feature_version=(min(3, causal_record.model.feature_version)
                if causal_record is not None and getattr(args, "economy_training", False)
                else causal_record.model.feature_version if causal_record is not None else 1),
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
        routed_recovery=routed_recovery,
        trainer_funding=trainer_funding,
        trainer_pending_recovery=trainer_pending_recovery,
        regional_trainer_funding=regional_trainer_funding,
        observed_trainer_funding=observed_trainer_funding,
        remaining_acquisition_demand=remaining_acquisition_demand,
        level_evolution_acquisitions=level_evolution_acquisitions,
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
    execution_profile = (
        _boxed_evolution_profile(expanded_profile or profile, boxed_evolution)
        if boxed_evolution is not None
        else None
    )
    regional_profiles = _regional_profiles(
        execution_profile or expanded_profile or profile, tuple(wild_sources), readiness,
        allow_cartridge_sources=getattr(args, "registered_ledger", None) is not None,
    )
    readiness = replace(
        readiness,
        protected_paths=(
            *readiness.protected_paths,
            *(path.resolve() for path in wild_sources if isinstance(path, Path)),
        ),
    )
    readiness = _continue_readiness(
        readiness,
        continuation_chain,
        expanded_profile=expanded_profile,
        execution_profile=execution_profile,
        regional_profiles=regional_profiles,
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
    if readiness.training_plan is not None and any(
        spec.parameters.get("maximum_full_restores", 0) for spec in readiness.profile.providers
    ):
        readiness = replace(
            readiness,
            training_plan=RedPlayerTrainingPlan(
                {
                    **readiness.training_plan.document,
                    "economic_contract": "known-spend-and-bounded-consumption-v2",
                }
            ),
        )
    if getattr(args, "story_outcome_curriculum", False):
        from pokemon_red_completion.red_player_training_plan import declare_story_curriculum

        if readiness.training_plan is None:
            raise PairedRedBoundedPlayerRunError("curriculum_requires_training_plan")
        readiness = replace(
            readiness,
            training_plan=declare_story_curriculum(readiness.training_plan),
        )
    readiness = replace(
        readiness,
        forward_story_objective=getattr(args, "forward_story_objective", None),
        forward_resource_budget=getattr(args, "forward_resource_budget", None),
    )
    _forward_goal_plan(readiness)  # Validate the opt-in before any execution claim.
    readiness = _prepare_registration(readiness, args)
    if getattr(args, "economy_training", False):
        from pokemon_red_completion.living_dex_player_exploration import (
            ECONOMY_EXPLORATION_POLICY_ID,
        )
        from pokemon_red_completion.red_player_economy import supply_from_profile
        from pokemon_red_completion.red_player_training_plan import (
            ECONOMY_TRAINING_PLAN_SCHEMA,
            REGISTERED_TRAINING_PLAN_SCHEMA,
        )

        if (readiness.training_plan is None
                or readiness.training_plan.document["schema"] != REGISTERED_TRAINING_PLAN_SCHEMA
                or readiness.causal_record is None
                or readiness.causal_record.model.feature_version != 4):
            raise ValueError("economy training requires a registered continuation and v4 model")
        supply = supply_from_profile(readiness.profile)
        readiness = replace(readiness, training_plan=RedPlayerTrainingPlan({
            **readiness.training_plan.document, "schema": ECONOMY_TRAINING_PLAN_SCHEMA,
            "behavior_policy_id": ECONOMY_EXPLORATION_POLICY_ID, **supply.plan_fields(),
        }))
    return readiness


def _registered_runtime(
    readiness: _Readiness, runtime: RedGoalContextRuntime, *, restore: bool = False
) -> RedGoalContextRuntime:
    policy = getattr(readiness, "registration_policy", None)
    if restore:
        from pokemon_red_completion.red_registration_session import (
            SESSION_KIND,
            load_registration_policy,
        )

        record_id = getattr(readiness, "restore_registration_record_id", None)
        policy = None
        if record_id is not None:
            record = readiness.private_root.find_sealed_record(
                record_id, expected_kind=SESSION_KIND
            )
            if record is None:
                raise ValueError("registered restore binding is missing")
            policy = load_registration_policy(record.read())
            if (readiness.continuation is None
                    or policy.sha256 != readiness.continuation.collection.get("binding_sha256")):
                raise ValueError("registered restore checkpoint binding differs")
    if policy is None:
        return runtime
    # Routes and skills also take fresh observations directly from the adapter.
    # They must hash the same objective projection as their initial menu.
    return replace(runtime, registration_policy=policy,
                   adapter=replace(runtime.adapter, registration_policy=policy))


def _training_observation(runtime: RedGoalContextRuntime) -> Any:
    from pokemon_red_completion.red_registered_observation import project_registered_observation

    observed = runtime.adapter.observe()
    policy = getattr(runtime, "registration_policy", None)
    return observed if policy is None else project_registered_observation(observed, policy)


def _prepare_registration(readiness: _Readiness, args: argparse.Namespace) -> _Readiness:
    """Freeze shared credit only after authenticating a no-input saved-state restore."""
    ledger_path = getattr(args, "registered_ledger", None)
    name, run_id = (
        getattr(args, "registration_session", None),
        getattr(args, "registration_run_id", None),
    )
    if ledger_path is None:
        if name is not None or run_id is not None or readiness.restore_registration_record_id:
            raise ValueError("registered continuation requires its ledger and session")
        return readiness
    if (
        not name
        or not run_id
        or readiness.training_plan is None
        or readiness.continuation is None
        or not readiness.completion_dose
        or not readiness.save_terminal_checkpoints
        or not readiness.remaining_acquisition_demand
        or getattr(args, "story_outcome_curriculum", False)
        or readiness.forward_story_objective is not None
    ):
        raise ValueError("registered mode requires a saved collection training continuation")
    from pokemon_red_completion.red_player_training_plan import REGISTERED_TRAINING_PLAN_SCHEMA
    from pokemon_red_completion.red_registration_session import (
        SESSION_KIND,
        load_registration_policy,
        observe_registration,
        publish_registration_session,
        read_registration_state,
        session_record_id,
        validate_terminal_registration,
    )
    from pokemon_red_completion.registered_collection import REGISTERED_OBJECTIVE
    from pokemon_red_completion.registration_memory import RegistrationMemory

    if ledger_path.is_symlink():
        raise ValueError("registration ledger cannot be a symlink")
    ledger_path = ledger_path.resolve()
    if ledger_path.is_relative_to(PROJECT_ROOT) or ledger_path == readiness.rom_path:
        raise ValueError("registration ledger must be private and separate from the ROM")
    if ledger_path.exists():
        if not ledger_path.is_file():
            raise ValueError("registration ledger must be a regular database file")
        with ledger_path.open("rb") as existing:
            if existing.read(16) != b"SQLite format 3\x00":
                raise ValueError("registration ledger path belongs to another file")
    record_id = session_record_id(name)
    record = readiness.private_root.find_sealed_record(record_id, expected_kind=SESSION_KIND)
    if record is None:
        with PyBoyAdapter(readiness.rom_path, watch=False, speed=None) as emulator:
            emulator.load_state_bytes(readiness.capture.state_bytes)
            _verify_continuation_restore(readiness, emulator)
            controller = ReadOnlyController(emulator)
            runtime = build_red_goal_context_runtime(
                profile=readiness.profile,
                capture=readiness.capture,
                emulator=controller,
                reader=PokemonRedStateReader(controller),
            )
            observed, seen = read_registration_state(emulator, runtime)
            latest = RegistrationMemory(ledger_path).snapshot().latest(run_id)
            if latest is not None and latest.snapshot_sha256 != readiness.capture.state_sha256:
                raise ValueError("registration import cannot roll back the current run ledger")
            row = observe_registration(
                observed,
                seen=seen,
                run_id=run_id,
                rom_sha256=readiness.rom_sha256,
                snapshot_sha256=readiness.capture.state_sha256,
                sequence=0 if latest is None else latest.sequence,
            )
            anchor_id, anchor_sha = readiness.continuation_chain[-1]
            document = publish_registration_session(
                readiness.private_root,
                name=name,
                ledger_path=ledger_path,
                observation=observed,
                row=row,
                anchor_episode_id=anchor_id,
                anchor_checkpoint_sha256=anchor_sha,
            )
    else:
        document = record.read()
    policy = load_registration_policy(document)
    anchor = (document["anchor_episode_id"], document["anchor_checkpoint_sha256"])
    if anchor not in readiness.continuation_chain or policy.run_id != run_id:
        raise ValueError("registration session does not belong to this continuation")
    initial = policy.initial_memory.latest(run_id)
    if initial is None or initial.cartridge_sha256 != readiness.rom_sha256:
        raise ValueError("registration session cartridge differs")
    present = RegistrationMemory(ledger_path).snapshot()
    if not {r.sha256 for r in policy.initial_memory.observations} <= {
        r.sha256 for r in present.observations
    }:
        raise ValueError("registration ledger lost frozen source evidence")
    suffix = readiness.continuation_chain[readiness.continuation_chain.index(anchor) + 1 :]
    ledger = RegistrationMemory(ledger_path)
    for offset, (episode_id, _) in enumerate(suffix, start=1):
        # _continue_readiness authenticated each completed trajectory and its
        # checkpoint before this point. Reconcile a crash after checkpoint
        # publication but before its ledger commit, without controller input.
        terminal = readiness.private_root.find_sealed_record(
            checkpoint_record_id(episode_id),
            expected_kind="red_bounded_player_checkpoint",
        )
        if terminal is None:
            raise ValueError("registered continuation terminal is missing")
        ledger.record(
            validate_terminal_registration(
                terminal.read(),
                policy,
                sequence=initial.sequence + offset,
                rom_sha256=readiness.rom_sha256,
            )
        )
    sequence = initial.sequence + len(suffix) + 1
    latest = ledger.snapshot().latest(run_id)
    if (
        latest is None
        or latest.sequence != sequence - 1
        or latest.snapshot_sha256 != readiness.capture.state_sha256
    ):
        raise ValueError("registered continuation would roll back the durable ledger")
    return replace(
        readiness,
        registration_policy=policy,
        registration_ledger=ledger_path,
        registration_session_record_id=record_id,
        registration_sequence=sequence,
        training_plan=RedPlayerTrainingPlan(
            {
                **readiness.training_plan.document,
                "schema": REGISTERED_TRAINING_PLAN_SCHEMA,
                "objective": REGISTERED_OBJECTIVE,
                "registration_binding_sha256": policy.sha256,
            }
        ),
    )


def _forward_goal_plan(readiness: _Readiness) -> ForwardGoalPlan | None:
    objective = getattr(readiness, "forward_story_objective", None)
    resources = getattr(readiness, "forward_resource_budget", None)
    if objective is None:
        if resources is not None:
            raise PairedRedBoundedPlayerRunError("forward_goal_requires_objective")
        return None
    plan = readiness.training_plan
    if (
        plan is None
        or readiness.decision_limit != 2
        or type(resources) is not int
        or resources < 2
        or plan.document.get("curriculum_contract") is not None
        or readiness.causal_record is None
        or readiness.causal_record.model.feature_version != 3
    ):
        raise PairedRedBoundedPlayerRunError("forward_goal_scope")
    from pokemon_red_completion.goal_manager import GoalKind
    from pokemon_red_completion.red_goal_context_profile import RedGoalMechanic

    # routed_resource_goals also provides the cartridge-derived story world and
    # authenticated profile transitions. It does not turn field restoration into
    # a Center trip. Inherited capabilities remain authenticated. Every actual
    # menu rejects non-direct bindings before prediction, rather than filtering.
    if not {GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM} <= {
        spec.kind for spec in readiness.profile.providers
    }:
        raise PairedRedBoundedPlayerRunError("forward_goal_missing_mechanics")
    for spec in readiness.profile.providers:
        if spec.kind is GoalKind.RESTORE_TEAM and spec.mechanic not in {
            RedGoalMechanic.FIELD_RESTORE,
            RedGoalMechanic.FIELD_PP_RESTORE,
        }:
            raise PairedRedBoundedPlayerRunError("forward_goal_requires_field_recovery")
        if spec.mechanic is RedGoalMechanic.FIELD_RESTORE and (
            spec.parameters.get("affordable_single_item") is not True
        ):
            raise PairedRedBoundedPlayerRunError("forward_goal_requires_single_item_recovery")
        if spec.kind is GoalKind.ADVANCE_STORY and (
            spec.parameters.get("trainer_objective") != objective
        ):
            raise PairedRedBoundedPlayerRunError("forward_goal_story_binding_differs")
    limits = _player_limits(2, completion_dose=readiness.completion_dose)
    return ForwardGoalPlan(
        "red-story-objective",
        red_forward_verifier_sha256(objective),
        red_forward_continuation_sha256(
            behavior_policy_id=cast(str, plan.document["behavior_policy_id"]),
            model_sha256=readiness.model_sha256,
            source_bundle_sha256=readiness.source_bundle_sha256,
            profile_sha256=readiness.profile.profile_sha256,
            execution_flags={
                key: getattr(readiness, key, False) for key in RED_FORWARD_EXECUTION_FLAGS
            },
        ),
        limits.max_total_actions,
        limits.max_total_frames,
        resources,
        2,
    )


def _forward_goal_header(readiness: _Readiness) -> dict[str, object]:
    plan = _forward_goal_plan(readiness)
    return (
        {}
        if plan is None
        else {
            "forward_goal_plan": plan.public_dict(),
            "forward_goal_plan_sha256": plan.sha256,
            "forward_story_objective": readiness.forward_story_objective,
            "forward_goal_authority": "recording-only-existing-actor",
        }
    )


def _require_forward_probe_scope(readiness: _Readiness, probe: RedForwardProbeSpec) -> None:
    if (
        not isinstance(probe, RedForwardProbeSpec)
        or readiness.training_plan is None
        or readiness.continuation is None
        or not readiness.continuation_root_lineage_id
        or readiness.forward_story_objective is not None
        or readiness.forward_resource_budget is not None
        or readiness.challenger_arm_id != CAUSAL_ARM_ID
        or readiness.model_sha256 != probe.tail_model_sha256
        or readiness.profile.profile_sha256 != probe.profile_sha256
        or readiness.training_plan.document["behavior_policy_id"] != probe.tail_policy_id
        or tuple((name, getattr(readiness, name, False)) for name in RED_FORWARD_EXECUTION_FLAGS)
        != probe.execution_flags
    ):
        raise PairedRedBoundedPlayerRunError("forward_probe_scope")
    scoped = replace(
        readiness,
        forward_story_objective=probe.objective_id,
        forward_resource_budget=probe.fitted_plan.max_resources,
    )
    actual = _forward_goal_plan(scoped)
    assert actual is not None
    if (actual.max_actions, actual.max_frames, actual.max_resources, actual.max_macros) != (
        probe.fitted_plan.max_actions,
        probe.fitted_plan.max_frames,
        probe.fitted_plan.max_resources,
        probe.fitted_plan.max_macros,
    ):
        raise PairedRedBoundedPlayerRunError("forward_probe_budget_differs")


def _evolution_objective_argument(value: str) -> str:
    parts = value.split(":")
    if (
        len(parts) != 3
        or any(not part.isascii() or not part.isdecimal() for part in parts)
        or not all(1 <= int(part) <= 151 for part in parts[:2])
        or not 2 <= int(parts[2]) <= 100
        or int(parts[0]) == int(parts[1])
    ):
        raise argparse.ArgumentTypeError("evolution objective needs SOURCE:TARGET:LEVEL")
    return "evolution:" + ":".join(str(int(part)) for part in parts)


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


def _regional_profiles(
    profile: RedGoalContextProfile,
    sources: tuple[str | Path, ...],
    readiness: _Readiness,
    *, allow_cartridge_sources: bool = False,
) -> tuple[RedGoalContextProfile, ...]:
    """Derive explicit source transitions; no emulator, policy or input is used."""
    from pokemon_red_completion.goal_manager import GoalKind

    if not sources:
        return ()
    from pokemon_red_completion.red_acquisition import RED_ACQUISITION_CATALOG, RedAcquisitionKind
    from pokemon_red_completion.red_living_dex_multifamily_curriculum import map_id_for_wild_source
    from pokemon_red_completion.red_living_dex_provider_curriculum import RedEncounterSourceTarget
    from pokemon_red_completion.red_living_dex_wild_corridor import (
        derive_red_living_dex_wild_corridor,
        retarget_red_wild_profile,
    )

    for source in sources:
        if isinstance(source, str) and source.startswith("warp-safe:"):
            source = source.removeprefix("warp-safe:")
            if not allow_cartridge_sources or not source.startswith("wild:"):
                raise PairedRedBoundedPlayerRunError("warp_safe_source_requires_registered_wild")
        if isinstance(source, str) and source.startswith("evolution:"):
            _evolution_objective_argument(source.removeprefix("evolution:"))
            continue
        if (
            isinstance(source, Path)
            or source.startswith("discovery:")
            or source
            in {
                "capture-status",
                "capture-search-budget",
                "opportunistic-capture",
                "evolution-fly",
                "capture-fly",
                "capture-cut",
                "capture-surf",
                "resupply-fly",
                "dig-recovery",
                "indoor-fly-departure",
                "observed-local-capture",
                "travel-capture",
                "capture-access-requirements",
                "affordable-capture-supply",
                "resource-choice-variants",
                "composable-trainer-funding",
                "mart-funding-departure",
                "funding-fly",
                "cartridge-trainer-story",
                "cartridge-trainer-story:bruno",
                "cartridge-trainer-story:agatha",
                "cartridge-trainer-story:lance",
                "cartridge-trainer-story:champion",
                "affordable-field-restore",
                "reserved-field-restore",
                "field-pp-restore",
                "combined-field-restore",
            }
            or source in {"trainer-recovery:1", "trainer-recovery:2"}
            or source in {"ordinary-trainer-recovery:1", "ordinary-trainer-recovery:2"}
        ):
            continue
        methods = RED_ACQUISITION_CATALOG.methods_at_source(source)
        if not methods and allow_cartridge_sources:
            from pokemon_red_completion.gen1_cartridge import wild_tables

            if wild_tables(readiness.rom_path.read_bytes(), medium="grass").get(
                int(map_id_for_wild_source(source))
            ):
                continue
        if not methods or any(method.kind is not RedAcquisitionKind.WILD for method in methods):
            raise PairedRedBoundedPlayerRunError("regional_source_requires_ordinary_wild_capture")
    world = _route_world(readiness)
    if world is None:
        raise PairedRedBoundedPlayerRunError("regional_profile_world")
    result = []
    for source in sources:
        warp_safe = isinstance(source, str) and source.startswith("warp-safe:")
        if warp_safe:
            assert isinstance(source, str)
            source = source.removeprefix("warp-safe:")
        if source == "resupply-fly":
            from pokemon_red_completion.red_goal_context_profile import bind_resupply_fly_profile

            profile = bind_resupply_fly_profile(profile)
            result.append(profile)
            continue
        if source == "dig-recovery":
            from pokemon_red_completion.red_goal_context_profile import bind_dig_recovery_profile

            profile = bind_dig_recovery_profile(profile)
            result.append(profile)
            continue
        if source == "capture-surf":
            from pokemon_red_completion.red_goal_context_profile import bind_capture_surf_profile

            profile = bind_capture_surf_profile(profile)
            result.append(profile)
            continue
        if source == "capture-cut":
            from pokemon_red_completion.red_goal_context_profile import bind_capture_cut_profile

            profile = bind_capture_cut_profile(profile)
            result.append(profile)
            continue
        if source == "capture-fly":
            from pokemon_red_completion.red_goal_context_profile import bind_capture_fly_profile

            profile = bind_capture_fly_profile(profile)
            result.append(profile)
            continue
        if source == "indoor-fly-departure":
            from pokemon_red_completion.red_goal_context_profile import (
                bind_indoor_fly_departure_profile,
            )

            profile = bind_indoor_fly_departure_profile(profile)
            result.append(profile)
            continue
        if source == "capture-access-requirements":
            from pokemon_red_completion.red_goal_context_profile import (
                bind_capture_access_requirements_profile,
            )

            profile = bind_capture_access_requirements_profile(profile)
            result.append(profile)
            continue
        if source == "travel-capture":
            from pokemon_red_completion.red_goal_context_profile import bind_travel_capture_profile

            if not allow_cartridge_sources:
                raise PairedRedBoundedPlayerRunError("travel_capture_requires_registered_objective")
            profile = bind_travel_capture_profile(profile)
            result.append(profile)
            continue
        if source == "observed-local-capture":
            from pokemon_red_completion.red_goal_context_profile import (
                bind_observed_local_capture_profile,
            )

            profile = bind_observed_local_capture_profile(profile)
            result.append(profile)
            continue
        if source == "evolution-fly":
            from pokemon_red_completion.red_goal_context_profile import bind_evolution_fly_profile

            profile = bind_evolution_fly_profile(profile)
            result.append(profile)
            continue
        if source in {
            "trainer-recovery:1",
            "trainer-recovery:2",
            "ordinary-trainer-recovery:1",
            "ordinary-trainer-recovery:2",
        }:
            from pokemon_red_completion.red_goal_context_profile import (
                bind_cartridge_trainer_story_profile,
            )

            story = next(
                (spec for spec in profile.providers if spec.kind is GoalKind.ADVANCE_STORY), None
            )
            if story is None or not story.parameters.get("trainer_objective"):
                raise PairedRedBoundedPlayerRunError("recovery_requires_cartridge_story_profile")
            profile = bind_cartridge_trainer_story_profile(
                profile,
                objective_id=str(story.parameters["trainer_objective"]),
                maximum_full_restores=int(str(source).split(":")[1]),
                recovery_controller=(
                    "ordinary-bounded-healing"
                    if str(source).startswith("ordinary-")
                    else "critical-inclusive"
                ),
            )
            result.append(profile)
            continue
        if source == "combined-field-restore":
            from pokemon_red_completion.red_goal_context_profile import (
                bind_combined_field_restore_profile,
            )

            profile = bind_combined_field_restore_profile(profile)
            result.append(profile)
            continue
        if source == "field-pp-restore":
            from pokemon_red_completion.red_goal_context_profile import (
                bind_field_pp_restore_profile,
            )

            profile = bind_field_pp_restore_profile(profile)
            result.append(profile)
            continue
        if source in {"affordable-field-restore", "reserved-field-restore"}:
            from pokemon_red_completion.red_goal_context_profile import (
                bind_affordable_field_restore_profile,
            )

            profile = bind_affordable_field_restore_profile(
                profile,
                reserve_last_full_restore=source == "reserved-field-restore",
            )
            result.append(profile)
            continue
        if source in {
            "cartridge-trainer-story",
            "cartridge-trainer-story:bruno",
            "cartridge-trainer-story:agatha",
            "cartridge-trainer-story:lance",
            "cartridge-trainer-story:champion",
        }:
            from pokemon_red_completion.red_goal_context_profile import (
                bind_cartridge_trainer_story_profile,
            )

            profile = bind_cartridge_trainer_story_profile(
                profile,
                objective_id=(
                    "defeat_champion"
                    if source.endswith(":champion")
                    else "defeat_lance"
                    if source.endswith(":lance")
                    else "defeat_agatha"
                    if source.endswith(":agatha")
                    else "defeat_bruno"
                    if source.endswith(":bruno")
                    else "defeat_lorelei"
                ),
            )
            result.append(profile)
            continue
        if isinstance(source, str) and source.startswith("evolution:"):
            profile = _boxed_evolution_profile(
                profile,
                tuple(int(value) for value in source.split(":")[1:]),
            )
            result.append(profile)
            continue
        if source == "affordable-capture-supply":
            from pokemon_red_completion.red_goal_context_profile import (
                bind_affordable_ball_supply_profile,
            )

            profile = bind_affordable_ball_supply_profile(profile)
            result.append(profile)
            continue
        if source == "resource-choice-variants":
            from pokemon_red_completion.red_goal_context_profile import bind_resource_choice_profile

            if not allow_cartridge_sources:
                raise PairedRedBoundedPlayerRunError(
                    "resource_variants_require_registered_objective",
                )
            profile = bind_resource_choice_profile(profile)
            result.append(profile)
            continue
        if source == "composable-trainer-funding":
            from pokemon_red_completion.red_goal_context_profile import (
                bind_composable_trainer_funding_profile,
            )

            if not allow_cartridge_sources:
                raise PairedRedBoundedPlayerRunError(
                    "composable_funding_requires_registered_objective",
                )
            profile = bind_composable_trainer_funding_profile(profile)
            result.append(profile)
            continue
        if source == "funding-fly":
            from pokemon_red_completion.red_goal_context_profile import bind_funding_fly_profile

            if not allow_cartridge_sources:
                raise PairedRedBoundedPlayerRunError(
                    "funding_fly_requires_registered_objective",
                )
            profile = bind_funding_fly_profile(profile)
            result.append(profile)
            continue
        if source == "mart-funding-departure":
            from pokemon_red_completion.red_goal_context_profile import (
                bind_mart_funding_departure_profile,
            )

            if not allow_cartridge_sources:
                raise PairedRedBoundedPlayerRunError(
                    "mart_funding_requires_registered_objective",
                )
            profile = bind_mart_funding_departure_profile(profile)
            result.append(profile)
            continue
        if source == "capture-status":
            from pokemon_red_completion.red_living_dex_wild_corridor import (
                bind_red_capture_status_profile,
            )

            profile = bind_red_capture_status_profile(profile)
            result.append(profile)
            continue
        if source == "capture-search-budget":
            from pokemon_red_completion.red_living_dex_wild_corridor import (
                bind_red_capture_search_budget_profile,
            )

            if not allow_cartridge_sources:
                raise PairedRedBoundedPlayerRunError("search_budget_requires_registered_objective")
            profile = bind_red_capture_search_budget_profile(profile)
            result.append(profile)
            continue
        if source == "opportunistic-capture":
            from pokemon_red_completion.red_living_dex_wild_corridor import (
                bind_red_opportunistic_capture_profile,
            )

            profile = bind_red_opportunistic_capture_profile(profile, world.rom)
            result.append(profile)
            continue
        if isinstance(source, str) and source.startswith("discovery:"):
            from pokemon_red_completion.red_living_dex_wild_corridor import (
                bind_red_local_discovery_profile,
            )

            profile = bind_red_local_discovery_profile(
                profile,
                source.removeprefix("discovery:"),
                world.rom,
            )
            result.append(profile)
            continue
        if isinstance(source, Path):
            from pokemon_red_completion.red_goal_context_profile import (
                require_resupply_only_profile_transition,
            )

            path = _regular_external(source, subject="supply_profile", rom_path=readiness.rom_path)
            candidate = load_red_goal_context_profile(path)
            require_resupply_only_profile_transition(profile, candidate)
            profile = candidate
            result.append(profile)
            continue
        map_id = int(map_id_for_wild_source(source))
        excluded = world.object_blockers[map_id]
        if warp_safe:
            # Match registered source enumeration exactly. A different lane
            # changes the profile hash even when the native goal was evolution.
            excluded = frozenset(excluded) | frozenset(
                world.macro_graph.warp_locations.get(map_id, ())
            )
        corridor = derive_red_living_dex_wild_corridor(
            RedEncounterSourceTarget(source),
            world.terrain[map_id],
            world.local_graphs[map_id],
            excluded=excluded,
            **({"cartridge": world.rom} if allow_cartridge_sources else {}),
        )
        profile = retarget_red_wild_profile(profile, corridor, rom=world.rom)
        result.append(profile)
    return tuple(result)


def _continue_readiness(
    readiness: _Readiness,
    chain: tuple[tuple[str, str], ...],
    *,
    expanded_profile: RedGoalContextProfile | None = None,
    execution_profile: RedGoalContextProfile | None = None,
    regional_profiles: tuple[RedGoalContextProfile, ...] = (),
) -> _Readiness:
    """Authenticate each completed ancestor without inventing an independent root."""
    seen: set[str] = set()
    admitted_profiles = tuple(
        p
        for p in (readiness.profile, expanded_profile, execution_profile, *regional_profiles)
        if p is not None
    )
    profile_index = 0
    for episode_id, record_sha256 in chain:
        if episode_id in seen:
            raise PairedRedBoundedPlayerRunError("continuation_duplicate_ancestor")
        seen.add(episode_id)
        episode = readiness.private_root.open_episode(episode_id)
        header = episode.read_header()
        metadata = header.get("metadata")
        proposal_profile = None
        if isinstance(metadata, Mapping):
            proposal_sha256 = metadata.get("regional_proposal_record_sha256")
            if proposal_sha256 is not None:
                if not isinstance(proposal_sha256, str):
                    raise PairedRedBoundedPlayerRunError(
                        "continuation_regional_proposal_binding"
                    )
                parent_plan = metadata.get("player_training_plan")
                if not isinstance(parent_plan, Mapping):
                    raise PairedRedBoundedPlayerRunError(
                        "continuation_regional_proposal_binding"
                    )
                try:
                    proposal_profile = load_regional_proposal_profile(
                        readiness.private_root,
                        episode_id,
                        proposal_sha256,
                        expected_parent_plan=parent_plan,
                    )
                except ValueError as error:
                    raise PairedRedBoundedPlayerRunError(
                        "continuation_regional_proposal_binding"
                    ) from error
                if metadata.get("profile_sha256") != proposal_profile.profile_sha256:
                    raise PairedRedBoundedPlayerRunError(
                        "continuation_regional_proposal_profile"
                    )
            matches = [
                index
                for index, candidate in enumerate(admitted_profiles)
                if metadata.get("profile_sha256") == candidate.profile_sha256
            ]
            forward = [index for index in matches if index >= profile_index]
            if forward:
                # Static transitions still advance monotonically. A profile
                # committed in this episode's proposal is an explicit
                # transition and need not occupy the static transition list.
                profile_index = forward[0]
                readiness = replace(readiness, profile=admitted_profiles[profile_index])
            elif proposal_profile is not None:
                readiness = replace(readiness, profile=proposal_profile)
            elif matches:
                raise PairedRedBoundedPlayerRunError("continuation_profile_rollback")
        checkpoint = open_red_player_checkpoint(
            readiness.private_root,
            episode_id=episode_id,
            expected_record_sha256=record_sha256,
            original_parent=readiness.capture,
            expected_profile_sha256=readiness.profile.profile_sha256,
            expected_rom_sha256=readiness.rom_sha256,
            expected_context_origin=readiness.context_origin,
            verified_episode=episode,
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
            restore_registration_record_id=cast(
                str | None,
                cast(Mapping[str, object], metadata).get(
                    "registration_session_record_id",
                    readiness.restore_registration_record_id,
                ),
            ),
            restore_completion_dose=_checkpoint_completion_dose(header),
            restore_routed_recovery=_checkpoint_routed_recovery(header),
            restore_trainer_funding=_checkpoint_trainer_funding(header),
            restore_trainer_pending_recovery=_checkpoint_trainer_pending_recovery(header),
            restore_regional_trainer_funding=_checkpoint_regional_trainer_funding(header),
            restore_observed_trainer_funding=_checkpoint_observed_trainer_funding(header),
            restore_remaining_acquisition_demand=_checkpoint_remaining_acquisition_demand(header),
            restore_level_evolution_acquisitions=_checkpoint_level_evolution_acquisitions(header),
            continuation_root_lineage_id=lineage,
            continuation_chain=(*readiness.continuation_chain, (episode_id, record_sha256)),
        )
    if chain:
        if readiness.restore_regional_trainer_funding and not readiness.regional_trainer_funding:
            raise PairedRedBoundedPlayerRunError("regional_trainer_funding_rollback")
        if readiness.restore_observed_trainer_funding and not readiness.observed_trainer_funding:
            raise PairedRedBoundedPlayerRunError("observed_trainer_funding_rollback")
        if readiness.restore_trainer_pending_recovery and not readiness.trainer_pending_recovery:
            raise PairedRedBoundedPlayerRunError("trainer_pending_recovery_rollback")
        if (
            readiness.restore_level_evolution_acquisitions
            and not readiness.level_evolution_acquisitions
        ):
            raise PairedRedBoundedPlayerRunError("level_evolution_acquisitions_rollback")
        if (
            readiness.restore_remaining_acquisition_demand
            and not readiness.remaining_acquisition_demand
        ):
            raise PairedRedBoundedPlayerRunError("remaining_acquisition_demand_rollback")
        readiness = replace(
            readiness,
            restore_profile=readiness.profile,
            profile=(
                regional_profiles[-1]
                if regional_profiles
                else execution_profile or expanded_profile or readiness.profile
            ),
        )
    return readiness


def _checkpoint_level_evolution_acquisitions(header: Mapping[str, object]) -> bool:
    metadata = header.get("metadata")
    if not isinstance(metadata, Mapping):
        raise PairedRedBoundedPlayerRunError("continuation_parent_metadata")
    enabled = metadata.get("level_evolution_acquisitions", False)
    if type(enabled) is not bool or (
        enabled and not _checkpoint_remaining_acquisition_demand(header)
    ):
        raise PairedRedBoundedPlayerRunError("continuation_parent_level_evolution_acquisitions")
    return enabled


def _checkpoint_remaining_acquisition_demand(header: Mapping[str, object]) -> bool:
    """Absent metadata preserves the original static-demand observation exactly."""
    metadata = header.get("metadata")
    if not isinstance(metadata, Mapping):
        raise PairedRedBoundedPlayerRunError("continuation_parent_metadata")
    enabled = metadata.get("remaining_acquisition_demand", False)
    if type(enabled) is not bool:
        raise PairedRedBoundedPlayerRunError("continuation_parent_remaining_acquisition_demand")
    return enabled


def _checkpoint_routed_recovery(header: Mapping[str, object]) -> bool:
    """Old endpoints use old opportunity menus; new ones retain their opt-in."""
    metadata = header.get("metadata")
    if not isinstance(metadata, Mapping):
        raise PairedRedBoundedPlayerRunError("continuation_parent_metadata")
    enabled = metadata.get("routed_recovery", False)
    if type(enabled) is not bool:
        raise PairedRedBoundedPlayerRunError("continuation_parent_routed_recovery")
    return enabled


def _checkpoint_trainer_funding(header: Mapping[str, object]) -> bool:
    """Keep historical opportunity menus unchanged on exact-state restore."""
    metadata = header.get("metadata")
    if not isinstance(metadata, Mapping):
        raise PairedRedBoundedPlayerRunError("continuation_parent_metadata")
    enabled = metadata.get("trainer_funding", False)
    if type(enabled) is not bool:
        raise PairedRedBoundedPlayerRunError("continuation_parent_trainer_funding")
    return enabled


def _checkpoint_trainer_pending_recovery(header: Mapping[str, object]) -> bool:
    """Authenticate old pending endpoints with their original unavailable menu."""
    metadata = header.get("metadata")
    if not isinstance(metadata, Mapping):
        raise PairedRedBoundedPlayerRunError("continuation_parent_metadata")
    enabled = metadata.get("trainer_pending_recovery", False)
    if type(enabled) is not bool:
        raise PairedRedBoundedPlayerRunError("continuation_parent_trainer_pending_recovery")
    if enabled and not _checkpoint_trainer_funding(header):
        raise PairedRedBoundedPlayerRunError("continuation_parent_trainer_pending_recovery")
    return enabled


def _checkpoint_regional_trainer_funding(header: Mapping[str, object]) -> bool:
    """Historical menus remain local; new endpoints retain explicit regional scope."""
    metadata = header.get("metadata")
    if not isinstance(metadata, Mapping):
        raise PairedRedBoundedPlayerRunError("continuation_parent_metadata")
    enabled = metadata.get("regional_trainer_funding", False)
    if type(enabled) is not bool or (enabled and not _checkpoint_trainer_funding(header)):
        raise PairedRedBoundedPlayerRunError("continuation_parent_regional_trainer_funding")
    return enabled


def _checkpoint_observed_trainer_funding(header: Mapping[str, object]) -> bool:
    """Historical menus remain static; new endpoints retain observed terrain mode."""
    metadata = header.get("metadata")
    if not isinstance(metadata, Mapping):
        raise PairedRedBoundedPlayerRunError("continuation_parent_metadata")
    enabled = metadata.get("observed_trainer_funding", False)
    if type(enabled) is not bool or (enabled and not _checkpoint_trainer_funding(header)):
        raise PairedRedBoundedPlayerRunError("continuation_parent_observed_trainer_funding")
    return enabled


def _checkpoint_completion_dose(header: Mapping[str, object]) -> bool:
    """Restore the parent's recorded observer settings, not the successor's.

    Completion-dose execution exposes storage-supported capture opportunities.
    Reconstructing its terminal with legacy settings changes the semantic hash
    even when the emulator bytes and complete specimen ledger match exactly.
    """
    from pokemon_red_completion.red_player_training_plan import (
        COMPLETION_TRAINING_PLAN_SCHEMA,
        CURRICULUM_TRAINING_PLAN_SCHEMA,
        ECONOMY_TRAINING_PLAN_SCHEMA,
        REGISTERED_TRAINING_PLAN_SCHEMA,
    )

    metadata = header.get("metadata")
    if isinstance(metadata, Mapping) and "forward_probe" in metadata:
        probe = metadata["forward_probe"]
        enabled = metadata.get("completion_dose")
        if (
            not isinstance(probe, Mapping)
            or probe.get("schema") != "pokemon.red.forward-first-choice-training-probe.v1"
            or type(enabled) is not bool
            or not isinstance(probe.get("execution_flags"), Mapping)
            or cast(Mapping[str, object], probe["execution_flags"]).get("completion_dose")
            is not enabled
        ):
            raise PairedRedBoundedPlayerRunError("continuation_probe_observer_mode")
        return enabled
    if isinstance(metadata, Mapping) and metadata.get("schema") in {
        "pokemon.red.forced-recovery-header.v1",
        "pokemon.red.recorded-support-header.v1",
    }:
        enabled = metadata.get("completion_dose")
        if type(enabled) is not bool:
            raise PairedRedBoundedPlayerRunError("continuation_recovery_observer_mode")
        return enabled
    plan = metadata.get("player_training_plan") if isinstance(metadata, Mapping) else None
    if plan is None:
        return False
    if not isinstance(plan, Mapping):
        raise PairedRedBoundedPlayerRunError("continuation_parent_plan")
    parsed = RedPlayerTrainingPlan(plan)
    return parsed.document["schema"] in {
        COMPLETION_TRAINING_PLAN_SCHEMA,
        CURRICULUM_TRAINING_PLAN_SCHEMA,
        ECONOMY_TRAINING_PLAN_SCHEMA,
        REGISTERED_TRAINING_PLAN_SCHEMA,
    }


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
    runtime = _registered_runtime(readiness, runtime, restore=True)
    actions = CountingExecutor(
        FrameSafeExecutor(controller, DEFAULT_NEW_GAME_TIMING.controller_timing())
    )
    observer = _player_observer(
        runtime,
        actions,
        _route_world(readiness),
        readiness.quote_resource_costs,
        completion_dose=getattr(readiness, "restore_completion_dose", False),
        routed_recovery=getattr(readiness, "restore_routed_recovery", False),
        trainer_funding=getattr(readiness, "restore_trainer_funding", False),
        trainer_pending_recovery=getattr(readiness, "restore_trainer_pending_recovery", False),
        regional_trainer_funding=getattr(readiness, "restore_regional_trainer_funding", False),
        observed_trainer_funding=getattr(readiness, "restore_observed_trainer_funding", False),
        remaining_acquisition_demand=getattr(
            readiness,
            "restore_remaining_acquisition_demand",
            False,
        ),
        level_evolution_acquisitions=getattr(
            readiness,
            "restore_level_evolution_acquisitions",
            False,
        ),
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
    if record is not None and record.model.feature_version >= 2:
        return GoalSearchMemory()
    return None


def _episode_id(pair_id: str, arm_id: str) -> str:
    suffix_by_arm = {
        LEARNED_ARM_ID: "learned",
        CAUSAL_ARM_ID: "causal",
        CALIBRATION_ARM_ID: "calibration",
        BASELINE_ARM_ID: "baseline",
        FORWARD_PROBE_ARM_ID: "forward-probe",
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
        runtime = _registered_runtime(readiness, runtime)
        actions = CountingExecutor(
            FrameSafeExecutor(controller, DEFAULT_NEW_GAME_TIMING.controller_timing())
        )
        meter = _ReadOnlyBudgetMeter(actions, emulator, initial_frame_count)
        observer = _player_observer(
            runtime,
            actions,
            world,
            readiness.quote_resource_costs,
            completion_dose=readiness.completion_dose,
            routed_recovery=readiness.routed_recovery,
            trainer_funding=getattr(readiness, "trainer_funding", False),
            trainer_pending_recovery=getattr(readiness, "trainer_pending_recovery", False),
            regional_trainer_funding=getattr(readiness, "regional_trainer_funding", False),
            observed_trainer_funding=getattr(readiness, "observed_trainer_funding", False),
            remaining_acquisition_demand=getattr(readiness, "remaining_acquisition_demand", False),
            level_evolution_acquisitions=getattr(readiness, "level_evolution_acquisitions", False),
            forward_story_only=getattr(readiness, "forward_story_objective", None) is not None,
        )
        # Preview the same prospective history as the actor. Historical restore
        # authentication above must still use the checkpoint's original inputs.
        observer.search_memory = _execution_search_memory(readiness)
        result = preflight_red_bounded_player(
            observe=observer,
            budget_meter=meter,
            assignment_id=readiness.pair_id,
            authorities=(
                (readiness.challenger_arm_id, challenger),
                (BASELINE_ARM_ID, CompletionFirstGoalTeacher()),
            ),
            allow_forced_bridge=readiness.continuation is not None,
        )
        forward_plan = _forward_goal_plan(readiness)
        if forward_plan is not None:
            from pokemon_red_completion.goal_manager import GoalKind

            if (
                not isinstance(challenger, ExploringLivingDexGoalPolicy)
                or not challenger.training_eligible
            ):
                raise PairedRedBoundedPlayerRunError("forward_goal_requires_sampled_choice")
            available = observer().binding_set.opportunities
            if any(
                op.kind not in {GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM}
                for op in available
                if op.availability.value == "available"
            ):
                raise PairedRedBoundedPlayerRunError("forward_goal_unsupported_option")
            collector = RedForwardGoalCollector(
                forward_plan,
                cast(str, readiness.forward_story_objective),
                runtime.adapter.observe,
                meter,
                lambda _event: None,
            )
            collector.prepare()  # Read-only qualification; no persistent episode/anchor.
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
    qualified_completion = False
    if not observation.input_ready and any(
        spec.parameters.get("trainer_objective") == "defeat_champion"
        for spec in runtime.profile.providers
    ):
        from pokemon_red_completion.observation import MapId
        from pokemon_red_completion.referee import CompletionReferee

        if (
            observation.raw.map_id == MapId.HALL_OF_FAME
            and not observation.raw.battle_state
            and CompletionReferee().inspect(observation.game_state).complete
            and not runtime.emulator.pressed_buttons
        ):
            # A terminal-only scene snapshot, not a generally input-ready field
            # checkpoint. Stop before Hall-of-Fame processing clears current events.
            scene = runtime.reader.read_final_league_scene()
            qualified_completion = scene.map_id == MapId.HALL_OF_FAME and scene.script_stage in {
                0,
                1,
            }
    if (
        meter.checkpoint() != before
        or observation.raw.battle_state
        or runtime.emulator.pressed_buttons
        or not (observation.input_ready or qualified_completion)
    ):
        raise PairedRedBoundedPlayerRunError("terminal_checkpoint_unsafe_boundary")


def _run_arm(
    readiness: _Readiness,
    *,
    arm_id: str,
    authority: GoalDecisionAuthority,
    viewer: BoundedPlayerDashboard | None = None,
    forward_probe: RedForwardProbeSpec | None = None,
) -> PairedBoundedPlayerArm:
    if (arm_id == FORWARD_PROBE_ARM_ID) != (forward_probe is not None):
        raise PairedRedBoundedPlayerRunError("forward_probe_arm_identity")
    if forward_probe is not None:
        _require_forward_probe_scope(readiness, forward_probe)
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
                model_sha256=(
                    readiness.model_sha256 if forward_probe is None else forward_probe.model.sha256
                ),
                train_examples=(
                    forward_probe.model.settled_examples
                    if forward_probe is not None
                    else readiness.causal_record.model.settled_examples
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
                **(
                    _training_header(readiness, arm_id)
                    if forward_probe is None
                    else {
                        "forward_probe": forward_probe.header(),
                        "split": {
                            "partition": "train",
                            "root_lineage_id": readiness.continuation_root_lineage_id,
                        },
                        "native_training_admission": False,
                    }
                ),
                **_forward_goal_header(readiness),
                **_continuation_header(readiness),
                **(
                    {"training_eligible": False, "tail_model_sha256": readiness.model_sha256}
                    if forward_probe is not None
                    else {}
                ),
                "schema": "pokemon.red.paired-bounded-player-arm-header.v1",
                "pair_id": readiness.pair_id,
                "arm_id": arm_id,
                "source_commit": readiness.source_commit,
                "source_bundle_sha256": readiness.source_bundle_sha256,
                "rom_sha256": readiness.rom_sha256,
                "state_sha256": readiness.capture.state_sha256,
                "envelope_sha256": readiness.capture.envelope_sha256,
                "profile_sha256": readiness.profile.profile_sha256,
                "model_sha256": (
                    readiness.model_sha256 if forward_probe is None else forward_probe.model.sha256
                ),
                "continue_after_progress": readiness.continue_after_progress,
                "completion_dose": readiness.completion_dose,
                **(
                    {"registration_session_record_id": readiness.registration_session_record_id}
                    if getattr(readiness, "registration_session_record_id", None) is not None
                    else {}
                ),
                "routed_resource_goals": readiness.routed_resource_goals,
                "routed_recovery": readiness.routed_recovery,
                "trainer_funding": getattr(readiness, "trainer_funding", False),
                "trainer_pending_recovery": getattr(readiness, "trainer_pending_recovery", False),
                "regional_trainer_funding": getattr(readiness, "regional_trainer_funding", False),
                "observed_trainer_funding": getattr(readiness, "observed_trainer_funding", False),
                **(
                    {"remaining_acquisition_demand": True}
                    if readiness.remaining_acquisition_demand
                    else {}
                ),
                **(
                    {"level_evolution_acquisitions": True}
                    if readiness.level_evolution_acquisitions
                    else {}
                ),
                "quote_resource_costs": readiness.quote_resource_costs,
                "save_terminal_checkpoints": readiness.save_terminal_checkpoints,
                **(
                    {"regional_choice_record_sha256": readiness.regional_choice_record_sha256}
                    if readiness.regional_choice_record_sha256 is not None
                    else {}
                ),
                **(
                    {"regional_proposal_record_sha256": readiness.regional_proposal_record_sha256}
                    if getattr(readiness, "regional_proposal_record_sha256", None) is not None
                    else {}
                ),
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
            runtime = _registered_runtime(readiness, runtime)
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
                routed_recovery=readiness.routed_recovery,
                trainer_funding=getattr(readiness, "trainer_funding", False),
                trainer_pending_recovery=getattr(readiness, "trainer_pending_recovery", False),
                regional_trainer_funding=getattr(readiness, "regional_trainer_funding", False),
                observed_trainer_funding=getattr(readiness, "observed_trainer_funding", False),
                remaining_acquisition_demand=readiness.remaining_acquisition_demand,
                level_evolution_acquisitions=readiness.level_evolution_acquisitions,
                retain_quantum=retain_quantum if readiness.save_terminal_checkpoints else None,
            )
            if forward_probe is not None:
                from pokemon_red_completion.forward_first_choice_policy import (
                    FirstChoiceForwardTrainingPolicy,
                )

                if red_forward_goal_observed(runtime.adapter.observe(), forward_probe.objective_id):
                    raise PairedRedBoundedPlayerRunError("forward_probe_goal_already_complete")
                assert readiness.causal_record is not None
                authority = FirstChoiceForwardTrainingPolicy(
                    forward_model=forward_probe.model,
                    fitted_plan=forward_probe.fitted_plan,
                    tail_model=readiness.causal_record.model,
                    tail_seed=forward_probe.tail_seed,
                    observe_context=lambda: red_forward_context(runtime.adapter.observe()),
                    meter=meter,
                    append_decision=lambda event: writer.append(
                        "forward_probe",
                        event,
                        durable=True,
                    ),
                    training_probe=True,
                )
            forward = None
            forward_plan = _forward_goal_plan(readiness)
            if forward_plan is not None:

                def append_forward(event: dict[str, object]) -> None:
                    writer.append("forward_goal", event, durable=True)

                forward = RedForwardGoalCollector(
                    forward_plan,
                    cast(str, readiness.forward_story_objective),
                    runtime.adapter.observe,
                    meter,
                    append_forward,
                )
                forward.prepare()
            trajectory_class = (
                ViewerGoalTrajectory
                if forward_probe is not None
                else RedForwardTrainingTrajectory
                if forward is not None
                else (
                    ViewerGoalTrajectory
                    if readiness.training_plan is None
                    else RedPlayerTrainingTrajectory
                )
            )
            training_kwargs: dict[str, Any] = (
                {}
                if readiness.training_plan is None or forward_probe is not None
                else {
        "observe_training": runtime.adapter.observe,
                    "training_meter": meter,
                    "training_plan_sha256": readiness.training_plan.plan_sha256,
                    "maximum_actions": limits.max_actions_per_decision,
                    "maximum_frames": limits.max_frames_per_decision,
                    "curriculum_contract": readiness.training_plan.document.get(
                        "curriculum_contract"
                    ),
                    "registration_binding_sha256": readiness.training_plan.document.get(
                        "registration_binding_sha256"
                    ),
                }
            )
            if forward is not None:
                training_kwargs["forward"] = forward
            if readiness.training_plan is not None:
                from pokemon_red_completion.red_player_training_plan import (
                    ECONOMY_TRAINING_PLAN_SCHEMA,
                )

                if readiness.training_plan.document["schema"] == ECONOMY_TRAINING_PLAN_SCHEMA:
                    from pokemon_red_completion.red_player_economy import (
                        PlayerEconomySupply,
                        supply_from_profile,
                    )

                    supply = PlayerEconomySupply.from_plan(readiness.training_plan.document)
                    if supply != supply_from_profile(runtime.profile):
                        raise ValueError("live supply profile differs from economy declaration")
                    training_kwargs["economy_supply"] = supply
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
                policy_id=(
                    _policy_id(readiness, arm_id)
                    if forward_probe is None
                    else forward_probe.policy_id
                ),
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
            last_failure_state: dict[str, object] | None = None

            def retain_failure_state() -> None:
                from pokemon_red_completion.red_player_checkpoint import capture_red_failure_state

                nonlocal last_failure_state
                state = capture_red_failure_state(emulator=emulator, meter=meter)
                # Execution may already have retained this exact boundary. A
                # later verification error must not duplicate it or lose a newer
                # state reached by intervening controller input.
                if state != last_failure_state:
                    writer.append("failure_state", state, durable=True)
                    last_failure_state = state

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
                if readiness.save_terminal_checkpoints:
                    retain_failure_state()

            try:
                forward_callbacks: dict[str, Any] = (
                    {}
                    if forward is None
                    else {
                        "stop_requested": lambda _observation: forward.outcome is not None,
                        "validate_choice_menu": lambda observation: _require_forward_binding_scope(
                            observation.binding_set,
                            readiness.profile,
                        ),
                    }
                )
                if forward_probe is not None:
                    first_choice_actor = cast(FirstChoiceForwardTrainingPolicy, authority)

                    def validate_probe_menu(observation: Any) -> None:
                        _require_forward_binding_scope(observation.binding_set, readiness.profile)
                        if (
                            first_choice_actor.forward_decisions == 0
                            and len(observation.binding_set.bindings) < 2
                        ):
                            raise PairedRedBoundedPlayerRunError("forward_probe_initial_singleton")

                    forward_callbacks["validate_choice_menu"] = validate_probe_menu
                result = run_bounded_player_episode(
                    observe=observer,
                    authority=authority,
                    authority_id=arm_id,
                    trajectory=trajectory,
                    budget_meter=meter,
                    completion_satisfied=(
                        (
                            lambda _observation: red_forward_goal_observed(
                                runtime.adapter.observe(),
                                forward_probe.objective_id,
                            )
                        )
                        if forward_probe is not None
                        else _completion_predicate(readiness)
                        if forward is None
                        else lambda _observation: (
                            forward.outcome is not None
                            and forward.outcome.target is not None
                            and forward.outcome.target[0] == 1.0
                        )
                    ),
                    limits=limits,
                    failure_observer=record_component_failure,
                    search_memory=search_memory,
                    **forward_callbacks,
                )
                if forward is not None:
                    forward.finish()
                if forward_probe is not None:
                    writer.append(
                        "forward_probe",
                        {
                            "kind": "forward_probe_terminal",
                            "bounded_result": result.public_dict(),
                            "native_training_admission": False,
                            "model_fitted": False,
                            "independent_evaluation": False,
                        },
                        durable=True,
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
                        model_sha256=(
                            readiness.model_sha256
                            if forward_probe is None
                            else forward_probe.model.sha256
                        ),
                        source_commit=readiness.source_commit,
                        source_bundle_sha256=readiness.source_bundle_sha256,
                        context_origin=readiness.context_origin,
                    )
                    if getattr(readiness, "registration_policy", None) is not None:
                        from pokemon_red_completion.red_registration_session import (
                            observe_registration,
                            read_registration_state,
                            validate_terminal_registration,
                        )

                        registration_state, seen = read_registration_state(emulator, runtime)
                        terminal_checkpoint["registration_observation"] = observe_registration(
                            registration_state,
                            seen=seen,
                            run_id=readiness.registration_policy.run_id,
                            rom_sha256=readiness.rom_sha256,
                            snapshot_sha256=cast(str, terminal_checkpoint["state_sha256"]),
                            sequence=cast(int, readiness.registration_sequence),
                        ).document()
                        validate_terminal_registration(
                            terminal_checkpoint,
                            readiness.registration_policy,
                            sequence=cast(int, readiness.registration_sequence),
                            rom_sha256=readiness.rom_sha256,
                        )
                    writer.append("checkpoint", terminal_checkpoint, durable=True)
            except BaseException as error:
                if forward is not None:
                    try:
                        forward.finish(interrupted=True)
                    except BaseException as forward_error:
                        error.add_note(
                            "forward-goal terminal unavailable: " + type(forward_error).__name__
                        )
                # Verifiers, training observers and checkpoint serialization may
                # fail AFTER legitimate gameplay. Save while the emulator is
                # still open; this is diagnostic evidence, never an admitted
                # outcome or authority to replay the attempted decision.
                if readiness.save_terminal_checkpoints:
                    try:
                        retain_failure_state()
                    except BaseException as retention_error:
                        error.add_note(
                            "failure state retention also failed: " + type(retention_error).__name__
                        )
                raise
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
            if getattr(readiness, "registration_policy", None) is not None:
                from pokemon_red_completion.red_registration_session import registration_row
                from pokemon_red_completion.registration_memory import RegistrationMemory

                assert readiness.registration_ledger is not None
                RegistrationMemory(readiness.registration_ledger).record(
                    registration_row(terminal_checkpoint["registration_observation"]),
                )
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


def _require_causal_decision_or_forced_bridge(authority: Any, episode: Any) -> None:
    if authority.last_decision is None and not (
        episode.forced_singleton_steps > 0
        and episode.authority_decisions == 0
        and authority.decisions == 0
    ):
        raise PairedRedBoundedPlayerRunError("causal_outcome_decision")


def _run(args: argparse.Namespace) -> dict[str, object]:
    return _run_prepared(_prepare(args))


def _run_prepared(readiness: _Readiness) -> dict[str, object]:
    """Execute one already-authenticated scope; reused by the source-choice layer."""
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
        **_forward_goal_header(readiness),
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
        _require_causal_decision_or_forced_bridge(challenger_authority, learned.episode)
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
