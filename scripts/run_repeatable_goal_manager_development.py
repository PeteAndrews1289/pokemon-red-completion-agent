#!/usr/bin/env python3
"""Freeze or run a repeatable, teacher-free Red goal-manager development campaign."""

# ruff: noqa: E402 -- pin the reviewed workspace source before project imports

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_BOOTSTRAP_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_BOOTSTRAP_SRC = _BOOTSTRAP_PROJECT_ROOT / "src"
_PRELOADED_PROJECT_MODULES = tuple(
    sorted(
        name
        for name in sys.modules
        if name == "pokemon_red_completion" or name.startswith("pokemon_red_completion.")
    )
)
while str(_BOOTSTRAP_SRC) in sys.path:
    sys.path.remove(str(_BOOTSTRAP_SRC))
sys.path.insert(0, str(_BOOTSTRAP_SRC))

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameSafeExecutor,
    ReadOnlyController,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_collection_runtime import (
    goal_binding_manifest_sha256,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    ActionFreeAdmissionExecutor,
    CompositionIndependentBudgetMeter,
    HardCompositionActionLimiter,
    composition_skill_manifest,
    fixed_account_claim_registry_lease,
    living_collection_checkpoint,
    open_fixed_account_claim_registry,
    root_claim_is_available,
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    FRESH_COMPOSITION_FRAMES_PER_DECISION,
    FRESH_COMPOSITION_MAX_FRAMES,
    GoalManagerCompositionObservation,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    parse_goal_manager_context_capture,
)
from pokemon_red_completion.goal_manager_development import (
    DEVELOPMENT_MAX_DECISIONS,
    ExploratoryGoalManagerPolicy,
    GoalManagerDevelopmentResult,
    goal_manager_development_contract,
    goal_manager_development_numpy_runtime_sha256,
    goal_manager_development_outcome_objective,
    load_repeatable_goal_manager_development_episode,
    repeatable_goal_manager_trial_execution_identity,
    run_repeatable_goal_manager_development_episode,
)
from pokemon_red_completion.goal_manager_promotion import (
    AuthenticatedGoalManagerCandidate,
    authenticate_goal_manager_candidate,
    load_committed_goal_manager_promotion_plan,
)
from pokemon_red_completion.goal_manager_protocol import GoalManagerAssignment
from pokemon_red_completion.goal_manager_trajectory import (
    GoalManagerTrajectoryObserver,
    ordered_goal_manager_question,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.private_artifacts import (
    PRIVATE_ROOT_SENTINEL,
    EpisodeWriter,
    PrivateArtifactRoot,
    open_private_root,
)
from pokemon_red_completion.private_artifacts import (
    _rename_no_replace as atomic_no_replace_rename,
)
from pokemon_red_completion.provenance import (
    SourceIdentity,
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import (
    RedGoalContextRuntime,
    build_red_goal_context_runtime,
)
from pokemon_red_completion.red_goal_context_profile import (
    RedGoalContextProfile,
    parse_red_goal_context_profile,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.rom import RomFingerprint, resolve_rom_path, verify_rom
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts
from pokemon_red_completion.runtime_identity import (
    RuntimeIdentity,
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.trajectory import JSONValue, RecordingExecutor, SparseEvent
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink

PROJECT_ROOT = _BOOTSTRAP_PROJECT_ROOT
CONTEXT_PLAN_SCHEMA = "pokemon-red-private-goal-manager-context-plan-v1"
CAMPAIGN_SCHEMA = "pokemon.red.repeatable-goal-manager-development-campaign.v1"
REQUIRED_FOCUS_KINDS = (
    GoalKind.ADVANCE_STORY,
    GoalKind.RESTORE_TEAM,
    GoalKind.MANAGE_STORAGE,
    GoalKind.ACQUIRE_SPECIES,
)
TRIALS_PER_ROOT = 3
_MAX_PLAN_BYTES = 4 * 1024 * 1024
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,95}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RepeatableGoalManagerRunError(RuntimeError):
    """A path-free failure at a declared development stage."""

    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


class _DeferredActionExecutor:
    """Bind skills action-free, then permit dispatch only after enumeration returns."""

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
            raise RepeatableGoalManagerRunError("action_free_reobservation")
        execute = getattr(self._delegate, "execute", None)
        if not callable(execute):
            raise RepeatableGoalManagerRunError("executor_authentication")
        return execute(action)


@dataclass(frozen=True, slots=True)
class _ContextEntry:
    slot_id: str
    state: Path
    envelope: Path
    profile: Path


@dataclass(frozen=True, slots=True)
class _Root:
    entry_index: int
    entry: _ContextEntry
    assignment: GoalManagerAssignment
    capture: GoalManagerContextCapture
    profile: RedGoalContextProfile
    state_file_sha256: str
    envelope_file_sha256: str
    profile_file_sha256: str
    question_sha256: str
    policy_context_sha256: str
    available_menu_sha256: str
    binding_manifest_sha256: str
    available_goal_kinds: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Readiness:
    source: SourceIdentity
    source_bundle_sha256: str
    runner_sha256: str
    runtime: RuntimeIdentity
    numpy_runtime_sha256: str
    skill_manifest_sha256: str
    rom_path: Path
    rom: RomFingerprint
    candidate: AuthenticatedGoalManagerCandidate
    context_catalog_path: Path
    model_path: Path
    fit_summary_path: Path
    context_plan_path: Path
    context_plan_sha256: str
    entries: tuple[_ContextEntry, ...]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("freeze", "preflight", "execute", "admit"),
        required=True,
    )
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--fit-summary", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-numpy-runtime-sha256", required=True)
    parser.add_argument("--expected-skill-manifest-sha256", required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--campaign-plan", type=Path, required=True)
    parser.add_argument("--expected-campaign-sha256")
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--trial-index", type=int)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--speed", type=int)
    return parser


def _readiness(args: argparse.Namespace) -> _Readiness:
    _require_project_import_origins()
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if not source.git_commit or len(source.git_commit) != 40:
        raise RepeatableGoalManagerRunError("source_authentication")
    runner_path = Path(__file__).resolve()
    if runner_path.parent != (PROJECT_ROOT / "scripts").resolve():
        raise RepeatableGoalManagerRunError("source_authentication")
    runner_sha256 = _file_sha256(runner_path)
    runtime = build_runtime_identity()
    numpy_runtime_sha256 = goal_manager_development_numpy_runtime_sha256()
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    skill_manifest = composition_skill_manifest(PROJECT_ROOT)
    skill_sha = _sha(skill_manifest.get("manifest_sha256"), "skill manifest")
    expected_source_commit = args.expected_source_commit
    if (
        not isinstance(expected_source_commit, str)
        or _GIT_COMMIT.fullmatch(expected_source_commit) is None
        or source.git_commit != expected_source_commit
        or source_bundle_sha256
        != _sha(args.expected_source_bundle_sha256, "expected source bundle")
        or runner_sha256 != _sha(args.expected_runner_sha256, "expected runner")
        or runtime.sha256 != _sha(args.expected_runtime_sha256, "expected runtime")
        or numpy_runtime_sha256
        != _sha(args.expected_numpy_runtime_sha256, "expected NumPy runtime")
        or skill_sha
        != _sha(args.expected_skill_manifest_sha256, "expected skill manifest")
    ):
        raise RepeatableGoalManagerRunError("external_executable_attestation")
    rom_path = resolve_rom_path(args.rom)
    rom = verify_rom(rom_path)
    plan, _evaluation_commit = load_committed_goal_manager_promotion_plan(PROJECT_ROOT)
    context_catalog_path = _external_regular(args.context_catalog, rom_path=rom_path)
    model_path = _external_regular(args.model, rom_path=rom_path)
    fit_summary_path = _external_regular(args.fit_summary, rom_path=rom_path)
    candidate = authenticate_goal_manager_candidate(
        repository_root=PROJECT_ROOT,
        plan=plan,
        context_catalog_path=context_catalog_path,
        model_path=model_path,
        fit_summary_path=fit_summary_path,
    )
    context_plan_path = _external_regular(args.context_plan, rom_path=rom_path)
    context_payload = context_plan_path.read_bytes()
    context_plan_sha256 = hashlib.sha256(context_payload).hexdigest()
    if context_plan_sha256 != _sha(
        args.expected_context_plan_sha256,
        "expected context plan",
    ):
        raise RepeatableGoalManagerRunError("external_context_plan_attestation")
    entries = _load_context_plan(context_payload, candidate)
    return _Readiness(
        source=source,
        source_bundle_sha256=source_bundle_sha256,
        runner_sha256=runner_sha256,
        runtime=runtime,
        numpy_runtime_sha256=numpy_runtime_sha256,
        skill_manifest_sha256=skill_sha,
        rom_path=rom_path,
        rom=rom,
        candidate=candidate,
        context_catalog_path=context_catalog_path,
        model_path=model_path,
        fit_summary_path=fit_summary_path,
        context_plan_path=context_plan_path,
        context_plan_sha256=context_plan_sha256,
        entries=entries,
    )


def _require_project_import_origins() -> None:
    if _PRELOADED_PROJECT_MODULES:
        raise RepeatableGoalManagerRunError("source_authentication")
    package_root = (_BOOTSTRAP_SRC / "pokemon_red_completion").resolve()
    for name, module in tuple(sys.modules.items()):
        if name != "pokemon_red_completion" and not name.startswith(
            "pokemon_red_completion."
        ):
            continue
        raw = getattr(module, "__file__", None)
        if not isinstance(raw, str):
            raise RepeatableGoalManagerRunError("source_authentication")
        path = Path(raw)
        try:
            metadata = path.lstat()
            resolved = path.resolve(strict=True)
        except OSError:
            raise RepeatableGoalManagerRunError("source_authentication") from None
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or not resolved.is_relative_to(package_root)
        ):
            raise RepeatableGoalManagerRunError("source_authentication")


def _freeze(
    readiness: _Readiness,
    destination: Path,
    private_root_path: Path,
) -> dict[str, object]:
    destination = _new_external_file(destination, rom_path=readiness.rom_path)
    _store, private_root_identity_sha256 = _open_bound_private_root(
        private_root_path,
        rom_path=readiness.rom_path,
    )
    closed_root_registry = open_fixed_account_claim_registry()
    selected: list[_Root] = []
    adjacent_before = rom_adjacent_artifacts(readiness.rom_path)
    try:
        for focus_kind in REQUIRED_FOCUS_KINDS:
            candidates = tuple(
                (entry_index, entry)
                for entry_index, entry in enumerate(readiness.entries)
                if (
                    readiness.candidate.registry.assignment(entry.slot_id).partition == "train"
                    and readiness.candidate.registry.assignment(entry.slot_id).focus_kind
                    is focus_kind
                    and _historical_root_is_open(
                        readiness,
                        entry,
                        closed_root_registry,
                    )
                )
            )
            root = next(
                (
                    inspected
                    for entry_index, entry in candidates
                    if (
                        inspected := _inspect_root(
                            readiness,
                            entry,
                            entry_index=entry_index,
                        )
                    )
                    is not None
                    and focus_kind.value in inspected.available_goal_kinds
                    and GoalKind.EVOLVE_SPECIES.value
                    not in inspected.available_goal_kinds
                ),
                None,
            )
            if root is None:
                raise RepeatableGoalManagerRunError("action_free_root_inventory")
            selected.append(root)
    finally:
        if rom_adjacent_artifacts(readiness.rom_path) != adjacent_before:
            raise RepeatableGoalManagerRunError("protected_input_integrity")

    roots = [_private_root_record(root) for root in selected]
    trial_rows: list[dict[str, object]] = []
    for root_index in range(len(selected)):
        for seed_offset in range(TRIALS_PER_ROOT):
            trial_rows.append(
                {
                    "maximum_decisions": DEVELOPMENT_MAX_DECISIONS,
                    "root_index": root_index,
                    "seed": 10_000 + root_index * 100 + seed_offset,
                    "trial_index": len(trial_rows),
                }
            )
    identity_source = {
        "candidate": _candidate_identity(readiness),
        "context_plan_sha256": readiness.context_plan_sha256,
        "outcome_objective": _outcome_objective(),
        "private_root_identity_sha256": private_root_identity_sha256,
        "roots": roots,
        "numpy_runtime_sha256": readiness.numpy_runtime_sha256,
        "runtime_sha256": readiness.runtime.sha256,
        "runner_sha256": readiness.runner_sha256,
        "schema": CAMPAIGN_SCHEMA,
        "skill_manifest_sha256": readiness.skill_manifest_sha256,
        "source_bundle_sha256": readiness.source_bundle_sha256,
        "source_commit": readiness.source.git_commit,
        "trials": trial_rows,
    }
    campaign_id = canonical_sha256(identity_source)
    trials = [
        {
            **trial,
            "episode_id": f"red-goal-dev-{campaign_id}-{trial['trial_index']:02d}",
            "trial_claim_sha256": canonical_sha256(
                {
                    "campaign_id": campaign_id,
                    "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
                    "trial_index": trial["trial_index"],
                }
            ),
        }
        for trial in trial_rows
    ]
    plan = {
        **identity_source,
        "campaign_id": campaign_id,
        "trials": trials,
    }
    _write_exclusive(destination, _canonical_line(plan))
    return {
        "schema": "pokemon.red.repeatable-goal-manager-development-freeze.v1",
        "status": "training_campaign_frozen_without_prediction_or_action",
        "campaign_plan_sha256": hashlib.sha256(_canonical_line(plan)).hexdigest(),
        "executable_identity": _public_executable_identity(readiness),
        "root_lineages": len(roots),
        "trial_count": len(trials),
        "focus_goal_kinds": [kind.value for kind in REQUIRED_FOCUS_KINDS],
        "model_predictions": 0,
        "numpy_runtime_sha256": readiness.numpy_runtime_sha256,
        "controller_actions": 0,
        "emulator_frames": 0,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "tracked_private_paths": 0,
        "tracked_private_identities": 0,
    }


def _preflight(
    readiness: _Readiness,
    campaign_path: Path,
    private_root_path: Path,
    *,
    expected_campaign_sha256: str,
) -> dict[str, object]:
    store, private_root_identity_sha256 = _open_bound_private_root(
        private_root_path,
        rom_path=readiness.rom_path,
    )
    campaign_path, campaign_sha256, plan = _load_campaign(
        campaign_path,
        readiness,
        expected_campaign_sha256=expected_campaign_sha256,
        expected_private_root_identity_sha256=private_root_identity_sha256,
    )
    registry = open_fixed_account_claim_registry()
    for expected_root in _roots(plan):
        entry_index = _integer(expected_root.get("entry_index"), "entry index")
        if entry_index >= len(readiness.entries):
            raise RepeatableGoalManagerRunError("campaign_authentication")
        entry = readiness.entries[entry_index]
        if not _historical_root_is_open(readiness, entry, registry):
            raise RepeatableGoalManagerRunError("closed_root_collision")
        _open_frozen_root(
            readiness,
            entry,
            expected_root,
            entry_index=entry_index,
        )
    available = 0
    for trial in _trials(plan):
        episode_id = _text(trial.get("episode_id"), "episode identity")
        claim = _sha(trial.get("trial_claim_sha256"), "trial claim")
        if (
            store.inspect_episode_state(episode_id).status == "absent"
            and _trial_claim_is_available(registry, claim)
        ):
            available += 1
    return {
        "schema": "pokemon.red.repeatable-goal-manager-development-preflight.v1",
        "status": (
            "training_ready"
            if available == len(_trials(plan))
            else "campaign_consumed"
            if available == 0
            else "campaign_in_progress"
        ),
        "campaign_plan_sha256": campaign_sha256,
        "executable_identity": _public_executable_identity(readiness),
        "planned_trials": len(_trials(plan)),
        "available_trials": available,
        "root_lineages": len(_roots(plan)),
        "model_predictions": 0,
        "numpy_runtime_sha256": readiness.numpy_runtime_sha256,
        "controller_actions": 0,
        "emulator_frames": 0,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "tracked_private_paths": 0,
        "tracked_private_identities": 0,
    }


def _execute(
    readiness: _Readiness,
    campaign_path: Path,
    private_root_path: Path,
    *,
    trial_index: int,
    watch: bool,
    speed: int | None,
    expected_campaign_sha256: str,
) -> dict[str, object]:
    if type(trial_index) is not int or trial_index < 0:  # noqa: E721
        raise RepeatableGoalManagerRunError("trial_selection")
    if watch or speed is not None:
        raise RepeatableGoalManagerRunError("presentation_mode")
    store, private_root_identity_sha256 = _open_bound_private_root(
        private_root_path,
        rom_path=readiness.rom_path,
    )
    campaign_path, campaign_sha256, plan = _load_campaign(
        campaign_path,
        readiness,
        expected_campaign_sha256=expected_campaign_sha256,
        expected_private_root_identity_sha256=private_root_identity_sha256,
    )
    trials = _trials(plan)
    if trial_index >= len(trials):
        raise RepeatableGoalManagerRunError("trial_selection")
    trial = trials[trial_index]
    if trial.get("trial_index") != trial_index:
        raise RepeatableGoalManagerRunError("trial_selection")
    roots = _roots(plan)
    root_index = _integer(trial.get("root_index"), "root index")
    if root_index >= len(roots):
        raise RepeatableGoalManagerRunError("campaign_authentication")
    root_record = roots[root_index]
    entry_index = _integer(root_record.get("entry_index"), "entry index")
    if entry_index >= len(readiness.entries):
        raise RepeatableGoalManagerRunError("campaign_authentication")
    entry = readiness.entries[entry_index]
    claim_registry = open_fixed_account_claim_registry()
    if not _historical_root_is_open(readiness, entry, claim_registry):
        raise RepeatableGoalManagerRunError("closed_root_collision")
    root = _open_frozen_root(
        readiness,
        entry,
        root_record,
        entry_index=entry_index,
    )
    episode_id = _text(trial.get("episode_id"), "episode identity")
    claim = _sha(trial.get("trial_claim_sha256"), "trial claim")
    seed = _integer(trial.get("seed"), "trial seed")
    maximum_decisions = _integer(trial.get("maximum_decisions"), "decision bound")
    if store.inspect_episode_state(episode_id).status != "absent":
        raise RepeatableGoalManagerRunError("trial_already_consumed")
    if not _trial_claim_is_available(claim_registry, claim):
        raise RepeatableGoalManagerRunError("trial_already_consumed")
    protected = _protected_digests(
        (
            readiness.context_plan_path,
            campaign_path,
            readiness.context_catalog_path,
            readiness.model_path,
            readiness.fit_summary_path,
            entry.state,
            entry.envelope,
            entry.profile,
            readiness.rom_path,
        )
    )
    adjacent_before = rom_adjacent_artifacts(readiness.rom_path)
    execution_identity = repeatable_goal_manager_trial_execution_identity(
        campaign_id=_text(plan.get("campaign_id"), "campaign identity"),
        campaign_plan_sha256=campaign_sha256,
        model_canonical_sha256=readiness.candidate.plan.model_canonical_sha256,
        numpy_runtime_sha256=readiness.numpy_runtime_sha256,
        root_lineage_id=root.assignment.root_lineage_id,
        runtime_sha256=readiness.runtime.sha256,
        source_commit=readiness.source.git_commit or "",
        trial_index=trial_index,
        trial_claim_sha256=claim,
    )
    _write_trial_claim(
        claim_registry,
        trial_claim_sha256=claim,
        execution_identity_sha256=execution_identity,
        source_commit=readiness.source.git_commit or "",
        runner_sha256=readiness.runner_sha256,
    )
    writer: EpisodeWriter | None = None
    sink: EpisodeTrajectorySink | None = None
    recorder: RecordingExecutor[Any, Any] | None = None
    try:
        writer = store.begin_episode(episode_id)
        sink = EpisodeTrajectorySink(
            writer,
            episode_id=episode_id,
            game_id="pokemon.mainline:red:gb:us:rev0",
            durable_writes=True,
        )
        sink.write_episode_header(
            metadata=_episode_metadata(
                readiness,
                plan=plan,
                root=root,
                assignment_id=claim,
                execution_identity_sha256=execution_identity,
            )
        )
        with PyBoyAdapter(readiness.rom_path, watch=False, speed=None) as emulator:
            require_pyboy_import_origins(readiness.runtime)
            emulator.load_state_bytes(root.capture.state_bytes)
            require_pyboy_import_origins(readiness.runtime)
            frames = WindowedFrameBudgetController(
                emulator,
                maximum_frames_per_window=FRESH_COMPOSITION_FRAMES_PER_DECISION,
                maximum_total_frames=FRESH_COMPOSITION_MAX_FRAMES,
            )
            reader = PokemonRedStateReader(frames)
            runtime = build_red_goal_context_runtime(
                profile=root.profile,
                capture=root.capture,
                emulator=frames,
                reader=reader,
            )
            frame_safe = FrameSafeExecutor(
                frames,
                DEFAULT_NEW_GAME_TIMING.controller_timing(),
            )
            snapshot_provider = PokemonRedObservationEncoder.from_state_reader(reader)
            recorder = RecordingExecutor(
                delegate=frame_safe,
                snapshot_provider=snapshot_provider,
                sink=sink,
                episode_id=episode_id,
            )
            hard_actions = HardCompositionActionLimiter(recorder)
            actions = CountingExecutor(hard_actions)
            meter = CompositionIndependentBudgetMeter(hard_actions, frames)
            trajectory = GoalManagerTrajectoryObserver(
                episode_id=episode_id,
                root_lineage_id=root.assignment.root_lineage_id,
                partition="development",
                environment_id="pokemon.mainline:red:gb:us:rev0",
                actor="exploratory_goal_manager",
                policy_id="red-goal-manager-outcome-development-v1",
                collection_id=_text(plan.get("campaign_id"), "campaign identity"),
                assignment_id=claim,
                source_commit=readiness.source.git_commit or "",
                snapshot_provider=snapshot_provider,
                recorder=recorder,
                sink=sink,
                ordering_assignment_id=root.assignment.assignment_id,
            )
            policy = ExploratoryGoalManagerPolicy(readiness.candidate.model, seed=seed)
            require_pyboy_import_origins(readiness.runtime)
            observe = _live_observer(
                runtime=runtime,
                actions=actions,
                meter=meter,
                root=root,
            )
            result = run_repeatable_goal_manager_development_episode(
                observe=observe,
                policy=policy,
                trajectory=trajectory,
                budget_meter=meter,
                maximum_decisions=maximum_decisions,
            )
            if recorder.recording_failures:
                raise RepeatableGoalManagerRunError("trajectory_durability")
            require_pyboy_import_origins(readiness.runtime)
        require_pyboy_import_origins(readiness.runtime)
        _require_unchanged(protected)
        if rom_adjacent_artifacts(readiness.rom_path) != adjacent_before:
            raise RepeatableGoalManagerRunError("protected_input_integrity")
        sink.record_event(
            SparseEvent(
                event_id=f"{episode_id}:terminal",
                episode_id=episode_id,
                step_index=recorder.next_step_index,
                kind="terminal",
                payload={
                    "status": "complete",
                    "development": cast(Mapping[str, JSONValue], result.public_dict()),
                },
            )
        )
        sink.finalize()
        summary = writer.complete()
        return {
            "schema": "pokemon.red.repeatable-goal-manager-development-summary.v1",
            "status": "complete",
            "campaign_plan_sha256": campaign_sha256,
            "trial_index": trial_index,
            "private_artifact": {
                "manifest_sha256": summary.manifest_sha256,
                "status": summary.status,
                "stream_records": dict(summary.stream_records),
                "total_records": summary.total_records,
            },
            "development": _public_development_summary(result),
            "teacher_queries": 0,
            "teacher_fallbacks": 0,
            "sealed_red_accesses": 0,
            "crystal_accesses": 0,
            "private_path_fields": 0,
        }
    except BaseException as error:
        if writer is not None:
            _retain_failure(
                writer,
                sink=sink,
                episode_id=episode_id,
                step_index=0 if recorder is None else recorder.next_step_index,
                failure_stage=(
                    error.stage
                    if isinstance(error, RepeatableGoalManagerRunError)
                    else "development_runtime"
                ),
            )
        raise


def _admit_campaign(
    readiness: _Readiness,
    campaign_path: Path,
    private_root_path: Path,
    *,
    expected_campaign_sha256: str,
) -> dict[str, object]:
    store, private_root_identity_sha256 = _open_bound_private_root(
        private_root_path,
        rom_path=readiness.rom_path,
    )
    _resolved, campaign_sha256, plan = _load_campaign(
        campaign_path,
        readiness,
        expected_campaign_sha256=expected_campaign_sha256,
        expected_private_root_identity_sha256=private_root_identity_sha256,
    )
    registry = open_fixed_account_claim_registry()
    episodes = 0
    invalid_trials = 0
    verified_outcomes = 0
    atomic_episodes = 0
    composition_attempts = 0
    verified_compositions = 0
    collection_relevant_selections = 0
    successful_retained_acquisitions = 0
    successful_specimen_preserving_storage = 0
    manifests: set[str] = set()
    invalid_states: dict[str, int] = {}
    roots = _roots(plan)
    for trial in _trials(plan):
        trial_index = _integer(trial.get("trial_index"), "trial index")
        root_index = _integer(trial.get("root_index"), "root index")
        root = roots[root_index]
        claim = _sha(trial.get("trial_claim_sha256"), "trial claim")
        episode_id = _text(trial.get("episode_id"), "episode identity")
        execution_identity = repeatable_goal_manager_trial_execution_identity(
            campaign_id=_text(plan.get("campaign_id"), "campaign identity"),
            campaign_plan_sha256=campaign_sha256,
            model_canonical_sha256=readiness.candidate.plan.model_canonical_sha256,
            numpy_runtime_sha256=readiness.numpy_runtime_sha256,
            root_lineage_id=_text(root.get("root_lineage_id"), "root lineage"),
            runtime_sha256=readiness.runtime.sha256,
            source_commit=readiness.source.git_commit or "",
            trial_index=trial_index,
            trial_claim_sha256=claim,
        )
        claim_record = _read_trial_claim(registry, claim)
        if claim_record != {
            "execution_identity_sha256": execution_identity,
            "runner_sha256": readiness.runner_sha256,
            "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
            "source_commit": readiness.source.git_commit,
            "trial_claim_sha256": claim,
        }:
            raise RepeatableGoalManagerRunError("campaign_claim_authentication")
        state = store.inspect_episode_state(episode_id)
        if state.status != "complete":
            if state.status not in {"absent", "failed", "interrupted", "partial", "invalid"}:
                raise RepeatableGoalManagerRunError("campaign_artifact_authentication")
            invalid_trials += 1
            invalid_states[state.status] = invalid_states.get(state.status, 0) + 1
            continue
        entry_index = _integer(root.get("entry_index"), "entry index")
        entry = readiness.entries[entry_index]
        catalog_entry = readiness.candidate.catalog.entry(entry.slot_id)
        admitted = load_repeatable_goal_manager_development_episode(
            store.open_episode(episode_id),
            expected_campaign_id=_text(plan.get("campaign_id"), "campaign identity"),
            expected_trial_claim_sha256=claim,
            expected_episode_id=episode_id,
            expected_root_lineage_id=_text(root.get("root_lineage_id"), "root lineage"),
            expected_seed=_integer(trial.get("seed"), "trial seed"),
            expected_execution_identity_sha256=execution_identity,
            expected_context_catalog_sha256=readiness.candidate.catalog.catalog_sha256,
            expected_context_id=catalog_entry.context_id,
            expected_binding_manifest_sha256=_sha(
                root.get("binding_manifest_sha256"),
                "binding manifest",
            ),
            expected_state_sha256=_sha(root.get("state_sha256"), "state"),
            expected_envelope_sha256=_sha(root.get("envelope_sha256"), "envelope"),
            expected_first_question_sha256=_sha(root.get("question_sha256"), "question"),
            expected_first_policy_context_sha256=_sha(
                root.get("policy_context_sha256"),
                "policy context",
            ),
            expected_first_available_menu_sha256=_sha(
                root.get("available_menu_sha256"),
                "available menu",
            ),
            expected_model=readiness.candidate.model,
            expected_source_commit=readiness.source.git_commit or "",
        )
        if admitted.dataset.manifest_sha256 in manifests:
            raise RepeatableGoalManagerRunError("campaign_artifact_authentication")
        manifests.add(admitted.dataset.manifest_sha256)
        episodes += 1
        verified_outcomes += admitted.verified_outcomes
        atomic_episodes += admitted.verified_outcomes == 1
        composition_attempts += admitted.verified_outcomes >= 2
        verified_compositions += admitted.composition
        collection_relevant_selections += admitted.collection_relevant_outcomes
        successful_retained_acquisitions += admitted.successful_retained_acquisitions
        successful_specimen_preserving_storage += (
            admitted.successful_specimen_preserving_storage
        )
    return {
        "schema": "pokemon.red.repeatable-goal-manager-development-admission.v1",
        "status": "fixed_denominator_admitted",
        "campaign_plan_sha256": campaign_sha256,
        "planned_trials": len(_trials(plan)),
        "complete_episodes": episodes,
        "invalid_trials": invalid_trials,
        "invalid_trial_states": dict(sorted(invalid_states.items())),
        "verified_outcomes": verified_outcomes,
        "atomic_goal_episodes": atomic_episodes,
        "composition_attempts": composition_attempts,
        "verified_composition_episodes": verified_compositions,
        "collection_relevant_selections": collection_relevant_selections,
        "successful_retained_acquisitions": successful_retained_acquisitions,
        "successful_specimen_preserving_storage": (
            successful_specimen_preserving_storage
        ),
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "tracked_private_paths": 0,
        "tracked_private_identities": 0,
    }


def _inspect_root(
    readiness: _Readiness,
    entry: _ContextEntry,
    *,
    entry_index: int,
) -> _Root | None:
    assignment = readiness.candidate.registry.assignment(entry.slot_id)
    capture, profile, digests = _open_context_input(readiness, entry)
    adjacent_before = rom_adjacent_artifacts(readiness.rom_path)
    with PyBoyAdapter(readiness.rom_path, watch=False, speed=None) as emulator:
        require_pyboy_import_origins(readiness.runtime)
        emulator.load_state_bytes(capture.state_bytes)
        require_pyboy_import_origins(readiness.runtime)
        initial_frame_count = emulator.frame_count
        read_only_emulator = ReadOnlyController(emulator)
        reader = PokemonRedStateReader(read_only_emulator)
        runtime = build_red_goal_context_runtime(
            profile=profile,
            capture=capture,
            emulator=read_only_emulator,
            reader=reader,
        )
        action_guard = ActionFreeAdmissionExecutor()
        guard_actions = CountingExecutor(action_guard)
        observation = runtime.adapter.observe()
        binding_set = runtime.enumerator(guard_actions).enumerate(observation)
        if action_guard.attempted_actions or guard_actions.actions_executed:
            raise RepeatableGoalManagerRunError("action_free_root_inventory")
        if emulator.frame_count != initial_frame_count:
            raise RepeatableGoalManagerRunError("action_free_root_inventory")
        require_pyboy_import_origins(readiness.runtime)
        question = ordered_goal_manager_question(
            assignment_id=assignment.assignment_id,
            decision_index=0,
            situation=observation.situation,
            opportunities=binding_set.opportunities,
        )
    require_pyboy_import_origins(readiness.runtime)
    if rom_adjacent_artifacts(readiness.rom_path) != adjacent_before:
        raise RepeatableGoalManagerRunError("protected_input_integrity")
    if len(question.available_indices) < 2:
        return None
    return _Root(
        entry_index=entry_index,
        entry=entry,
        assignment=assignment,
        capture=capture,
        profile=profile,
        state_file_sha256=digests[0],
        envelope_file_sha256=digests[1],
        profile_file_sha256=digests[2],
        question_sha256=question.ordered_policy_input_sha256,
        policy_context_sha256=question.policy_context_sha256,
        available_menu_sha256=question.available_menu_sha256,
        binding_manifest_sha256=goal_binding_manifest_sha256(binding_set),
        available_goal_kinds=tuple(
            question.opportunities[index].kind.value for index in question.available_indices
        ),
    )


def _historical_root_is_open(
    readiness: _Readiness,
    entry: _ContextEntry,
    registry: Path,
) -> bool:
    context = readiness.candidate.catalog.entry(entry.slot_id)
    identity = root_consumption_sha256(
        state_sha256=context.state_sha256,
        envelope_sha256=context.envelope_sha256,
    )
    return bool(root_claim_is_available(registry, identity))


def _open_frozen_root(
    readiness: _Readiness,
    entry: _ContextEntry,
    expected: Mapping[str, object],
    *,
    entry_index: int,
) -> _Root:
    inspected = _inspect_root(readiness, entry, entry_index=entry_index)
    if (
        inspected is None
        or inspected.assignment.partition != "train"
        or _private_root_record(inspected) != expected
    ):
        raise RepeatableGoalManagerRunError("campaign_root_drift")
    return inspected


def _live_observer(
    *,
    runtime: RedGoalContextRuntime,
    actions: CountingExecutor,
    meter: CompositionIndependentBudgetMeter,
    root: _Root,
) -> Callable[[], GoalManagerCompositionObservation]:
    observations = 0

    def observe() -> GoalManagerCompositionObservation:
        nonlocal observations
        if observations:
            meter.begin_decision_window()
        before = meter.checkpoint()
        live = runtime.adapter.observe()
        deferred = _DeferredActionExecutor(actions)
        deferred_actions = CountingExecutor(deferred)
        binding_set = runtime.enumerator(deferred_actions).enumerate(live)
        if (
            meter.checkpoint() != before
            or deferred.attempted_while_disabled
            or deferred_actions.actions_executed
        ):
            raise RepeatableGoalManagerRunError("action_free_reobservation")
        deferred.enable()
        checkpoint = living_collection_checkpoint(live)
        semantic = canonical_sha256(
            {
                "schema": "pokemon.red.repeatable-goal-manager-semantic-state.v1",
                "goal_observation": live.public_dict(),
                "collection": checkpoint.public_dict(),
                "available_goal_kinds": [
                    binding.kind.value for binding in binding_set.bindings
                ],
            }
        )
        result = GoalManagerCompositionObservation(
            semantic_state_sha256=semantic,
            situation=live.situation,
            binding_set=binding_set,
            collection=checkpoint,
        )
        if observations == 0:
            question = ordered_goal_manager_question(
                assignment_id=root.assignment.assignment_id,
                decision_index=0,
                situation=live.situation,
                opportunities=binding_set.opportunities,
            )
            if (
                question.ordered_policy_input_sha256 != root.question_sha256
                or goal_binding_manifest_sha256(binding_set)
                != root.binding_manifest_sha256
            ):
                raise RepeatableGoalManagerRunError("campaign_root_drift")
        observations += 1
        return result

    return observe


def _open_context_input(
    readiness: _Readiness,
    entry: _ContextEntry,
) -> tuple[GoalManagerContextCapture, RedGoalContextProfile, tuple[str, str, str]]:
    for path in (entry.state, entry.envelope, entry.profile):
        _external_regular(path, rom_path=readiness.rom_path)
    try:
        state_bytes = entry.state.read_bytes()
        envelope_bytes = entry.envelope.read_bytes()
        profile_bytes = entry.profile.read_bytes()
    except OSError:
        raise RepeatableGoalManagerRunError("context_authentication") from None
    capture = parse_goal_manager_context_capture(state_bytes, envelope_bytes)
    profile = parse_red_goal_context_profile(profile_bytes)
    state_file_sha256 = hashlib.sha256(state_bytes).hexdigest()
    envelope_file_sha256 = hashlib.sha256(envelope_bytes).hexdigest()
    profile_file_sha256 = hashlib.sha256(profile_bytes).hexdigest()
    context = readiness.candidate.catalog.entry(entry.slot_id)
    if (
        capture.capture_id != entry.slot_id
        or profile.profile_id != entry.slot_id
        or capture.capture_id != context.capture_id
        or capture.state_sha256 != context.state_sha256
        or capture.envelope_sha256 != context.envelope_sha256
        or capture.state_sha256 != state_file_sha256
        or capture.envelope_sha256 != envelope_file_sha256
        or profile.profile_sha256 != profile_file_sha256
    ):
        raise RepeatableGoalManagerRunError("context_authentication")
    return (
        capture,
        profile,
        (
            state_file_sha256,
            envelope_file_sha256,
            profile_file_sha256,
        ),
    )


def _private_root_record(root: _Root) -> dict[str, object]:
    return {
        "assignment_id": root.assignment.assignment_id,
        "available_goal_kinds": list(root.available_goal_kinds),
        "available_menu_sha256": root.available_menu_sha256,
        "binding_manifest_sha256": root.binding_manifest_sha256,
        "capture_id": root.capture.capture_id,
        "entry_index": root.entry_index,
        "envelope_file_sha256": root.envelope_file_sha256,
        "envelope_sha256": root.capture.envelope_sha256,
        "focus_kind": root.assignment.focus_kind.value,
        "policy_context_sha256": root.policy_context_sha256,
        "profile_file_sha256": root.profile_file_sha256,
        "question_sha256": root.question_sha256,
        "root_lineage_id": root.assignment.root_lineage_id,
        "state_file_sha256": root.state_file_sha256,
        "state_sha256": root.capture.state_sha256,
    }


def _candidate_identity(readiness: _Readiness) -> dict[str, object]:
    return {
        "context_catalog_sha256": readiness.candidate.catalog.catalog_sha256,
        "fit_summary_file_sha256": readiness.candidate.fit_summary_sha256,
        "model_canonical_sha256": readiness.candidate.plan.model_canonical_sha256,
        "model_file_sha256": readiness.candidate.plan.model_file_sha256,
        "promotion_plan_sha256": readiness.candidate.plan.plan_sha256,
        "registry_sha256": readiness.candidate.registry.registry_sha256,
        "rom_sha256": readiness.rom.sha256,
    }


def _public_executable_identity(readiness: _Readiness) -> dict[str, object]:
    return {
        "context_catalog_sha256": readiness.candidate.catalog.catalog_sha256,
        "context_plan_sha256": readiness.context_plan_sha256,
        "model_canonical_sha256": readiness.candidate.plan.model_canonical_sha256,
        "model_file_sha256": readiness.candidate.plan.model_file_sha256,
        "numpy_runtime_sha256": readiness.numpy_runtime_sha256,
        "promotion_plan_sha256": readiness.candidate.plan.plan_sha256,
        "registry_sha256": readiness.candidate.registry.registry_sha256,
        "runner_sha256": readiness.runner_sha256,
        "runtime_sha256": readiness.runtime.sha256,
        "skill_manifest_sha256": readiness.skill_manifest_sha256,
        "source_bundle_sha256": readiness.source_bundle_sha256,
        "source_commit": readiness.source.git_commit,
    }


def _episode_metadata(
    readiness: _Readiness,
    *,
    plan: Mapping[str, object],
    root: _Root,
    assignment_id: str,
    execution_identity_sha256: str,
) -> dict[str, object]:
    return {
        "policy": {
            "actor": "exploratory_goal_manager",
            "policy_id": "red-goal-manager-outcome-development-v1",
        },
        "split": {
            "partition": "development",
            "root_lineage_id": root.assignment.root_lineage_id,
        },
        "goal_manager": {
            "assignment_id": assignment_id,
            "binding_manifest_sha256": root.binding_manifest_sha256,
            "collection_id": _text(plan.get("campaign_id"), "campaign identity"),
            "context_catalog_sha256": readiness.candidate.catalog.catalog_sha256,
            "context_id": readiness.candidate.catalog.entry(root.entry.slot_id).context_id,
            "envelope_sha256": root.capture.envelope_sha256,
            "execution_identity_sha256": execution_identity_sha256,
            "source_commit": readiness.source.git_commit,
            "state_sha256": root.capture.state_sha256,
        },
        "development": goal_manager_development_contract(),
    }


def _public_development_summary(
    result: GoalManagerDevelopmentResult,
) -> dict[str, object]:
    return {
        "actions_executed": sum(step.actions_executed for step in result.steps),
        "collection_relevant_outcomes": result.collection_relevant_outcomes,
        "collection_relevant_selections": result.collection_relevant_outcomes,
        "composition": result.is_composition,
        "decisions": result.verified_outcomes,
        "frames_executed": sum(step.frames_executed for step in result.steps),
        "model_sha256": result.model_sha256,
        "schema": "pokemon.red.repeatable-goal-manager-development-public-summary.v1",
        "selected_goal_kinds": [step.selected_kind.value for step in result.steps],
        "status": "durable_terminal",
        "stopped_reason": result.stopped_reason,
        "successful_retained_acquisitions": result.successful_retained_acquisitions,
        "successful_specimen_preserving_storage": (
            result.successful_specimen_preserving_storage
        ),
        "teacher_fallbacks": 0,
        "teacher_queries": 0,
        "tracked_private_identities": 0,
        "tracked_private_paths": 0,
        "verified_outcomes": result.verified_outcomes,
    }


def _retain_failure(
    writer: EpisodeWriter,
    *,
    sink: EpisodeTrajectorySink | None,
    episode_id: str,
    step_index: int,
    failure_stage: str,
) -> None:
    if sink is not None:
        with suppress(Exception):
            sink.record_event(
                SparseEvent(
                    event_id=f"{episode_id}:terminal",
                    episode_id=episode_id,
                    step_index=step_index,
                    kind="terminal",
                    payload={"status": "failed", "failure_stage": failure_stage},
                )
            )
            sink.finalize()
    with suppress(Exception):
        writer.abort("development_failed")


def _load_context_plan(
    payload: bytes,
    candidate: AuthenticatedGoalManagerCandidate,
) -> tuple[_ContextEntry, ...]:
    document = _canonical_document(payload, subject="context plan")
    if set(document) != {"entries", "registry_sha256", "schema", "source_commit"}:
        raise RepeatableGoalManagerRunError("context_plan_authentication")
    if (
        document.get("schema") != CONTEXT_PLAN_SCHEMA
        or document.get("registry_sha256") != candidate.registry.registry_sha256
        or document.get("source_commit") != candidate.registry.execution.source_commit
    ):
        raise RepeatableGoalManagerRunError("context_plan_authentication")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list):
        raise RepeatableGoalManagerRunError("context_plan_authentication")
    entries: list[_ContextEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, Mapping) or set(raw) != {
            "envelope",
            "profile",
            "slot_id",
            "state",
        }:
            raise RepeatableGoalManagerRunError("context_plan_authentication")
        entries.append(
            _ContextEntry(
                slot_id=_text(raw.get("slot_id"), "slot identity"),
                state=Path(_text(raw.get("state"), "state location")),
                envelope=Path(_text(raw.get("envelope"), "envelope location")),
                profile=Path(_text(raw.get("profile"), "profile location")),
            )
        )
    if tuple(entry.slot_id for entry in entries) != tuple(
        slot.slot_id for slot in candidate.registry.slots
    ):
        raise RepeatableGoalManagerRunError("context_plan_authentication")
    return tuple(entries)


def _load_campaign(
    path: Path,
    readiness: _Readiness,
    *,
    expected_campaign_sha256: str,
    expected_private_root_identity_sha256: str,
) -> tuple[Path, str, Mapping[str, object]]:
    resolved = _external_regular(path, rom_path=readiness.rom_path)
    payload = resolved.read_bytes()
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    if payload_sha256 != _sha(expected_campaign_sha256, "expected campaign"):
        raise RepeatableGoalManagerRunError("campaign_authentication")
    plan = _canonical_document(payload, subject="campaign plan")
    expected_keys = {
        "campaign_id",
        "candidate",
        "context_plan_sha256",
        "outcome_objective",
        "private_root_identity_sha256",
        "roots",
        "numpy_runtime_sha256",
        "runtime_sha256",
        "runner_sha256",
        "schema",
        "skill_manifest_sha256",
        "source_bundle_sha256",
        "source_commit",
        "trials",
    }
    if set(plan) != expected_keys or plan.get("schema") != CAMPAIGN_SCHEMA:
        raise RepeatableGoalManagerRunError("campaign_authentication")
    identity = dict(plan)
    campaign_id = identity.pop("campaign_id", None)
    trials = identity.get("trials")
    if not isinstance(trials, list):
        raise RepeatableGoalManagerRunError("campaign_authentication")
    stripped_trials = []
    for trial in trials:
        if not isinstance(trial, Mapping):
            raise RepeatableGoalManagerRunError("campaign_authentication")
        stripped = dict(trial)
        stripped.pop("episode_id", None)
        stripped.pop("trial_claim_sha256", None)
        stripped_trials.append(stripped)
    identity["trials"] = stripped_trials
    if (
        campaign_id != canonical_sha256(identity)
        or plan.get("source_commit") != readiness.source.git_commit
        or plan.get("source_bundle_sha256") != readiness.source_bundle_sha256
        or plan.get("runner_sha256") != readiness.runner_sha256
        or plan.get("runtime_sha256") != readiness.runtime.sha256
        or plan.get("numpy_runtime_sha256") != readiness.numpy_runtime_sha256
        or plan.get("skill_manifest_sha256") != readiness.skill_manifest_sha256
        or plan.get("context_plan_sha256") != readiness.context_plan_sha256
        or plan.get("outcome_objective") != _outcome_objective()
        or plan.get("private_root_identity_sha256")
        != expected_private_root_identity_sha256
        or plan.get("candidate") != _candidate_identity(readiness)
    ):
        raise RepeatableGoalManagerRunError("campaign_authentication")
    _validate_campaign_layout(plan)
    return resolved, payload_sha256, plan


def _validate_campaign_layout(plan: Mapping[str, object]) -> None:
    campaign_id = _sha(plan.get("campaign_id"), "campaign identity")
    roots = _roots(plan)
    trials = _trials(plan)
    if len(roots) != len(REQUIRED_FOCUS_KINDS) or len(trials) != (
        len(REQUIRED_FOCUS_KINDS) * TRIALS_PER_ROOT
    ):
        raise RepeatableGoalManagerRunError("campaign_authentication")
    expected_root_keys = {
        "assignment_id",
        "available_goal_kinds",
        "available_menu_sha256",
        "binding_manifest_sha256",
        "capture_id",
        "entry_index",
        "envelope_file_sha256",
        "envelope_sha256",
        "focus_kind",
        "policy_context_sha256",
        "profile_file_sha256",
        "question_sha256",
        "root_lineage_id",
        "state_file_sha256",
        "state_sha256",
    }
    seen_entries: set[int] = set()
    seen_lineages: set[str] = set()
    for root_index, (root, focus_kind) in enumerate(
        zip(roots, REQUIRED_FOCUS_KINDS, strict=True)
    ):
        if set(root) != expected_root_keys or root.get("focus_kind") != focus_kind.value:
            raise RepeatableGoalManagerRunError("campaign_authentication")
        entry_index = _integer(root.get("entry_index"), "entry index")
        if entry_index in seen_entries:
            raise RepeatableGoalManagerRunError("campaign_authentication")
        seen_entries.add(entry_index)
        assignment_id = _sha(root.get("assignment_id"), "assignment identity")
        lineage = _text(root.get("root_lineage_id"), "root lineage")
        if lineage != f"red-goal-root-{assignment_id}":
            raise RepeatableGoalManagerRunError("campaign_authentication")
        if lineage in seen_lineages:
            raise RepeatableGoalManagerRunError("campaign_authentication")
        seen_lineages.add(lineage)
        available = root.get("available_goal_kinds")
        if (
            not isinstance(available, list)
            or len(available) < 2
            or any(not isinstance(kind, str) for kind in available)
            or focus_kind.value not in available
            or GoalKind.EVOLVE_SPECIES.value in available
        ):
            raise RepeatableGoalManagerRunError("campaign_authentication")
        for key in (
            "available_menu_sha256",
            "binding_manifest_sha256",
            "envelope_file_sha256",
            "envelope_sha256",
            "policy_context_sha256",
            "profile_file_sha256",
            "question_sha256",
            "state_file_sha256",
            "state_sha256",
        ):
            _sha(root.get(key), key)
        capture_id = _text(root.get("capture_id"), "capture identity")
        if _SAFE_ID.fullmatch(capture_id) is None:
            raise RepeatableGoalManagerRunError("campaign_authentication")
        expected_trial_indices = tuple(
            root_index * TRIALS_PER_ROOT + offset for offset in range(TRIALS_PER_ROOT)
        )
        actual_trial_indices = tuple(
            _integer(trial.get("trial_index"), "trial index")
            for trial in trials
            if trial.get("root_index") == root_index
        )
        if actual_trial_indices != expected_trial_indices:
            raise RepeatableGoalManagerRunError("campaign_authentication")

    expected_trial_keys = {
        "episode_id",
        "maximum_decisions",
        "root_index",
        "seed",
        "trial_claim_sha256",
        "trial_index",
    }
    for expected_index, trial in enumerate(trials):
        if set(trial) != expected_trial_keys:
            raise RepeatableGoalManagerRunError("campaign_authentication")
        trial_index = _integer(trial.get("trial_index"), "trial index")
        root_index = _integer(trial.get("root_index"), "root index")
        seed = _integer(trial.get("seed"), "trial seed")
        if (
            trial_index != expected_index
            or root_index != expected_index // TRIALS_PER_ROOT
            or trial.get("maximum_decisions") != DEVELOPMENT_MAX_DECISIONS
            or seed != 10_000 + root_index * 100 + expected_index % TRIALS_PER_ROOT
        ):
            raise RepeatableGoalManagerRunError("campaign_authentication")
        if trial.get("episode_id") != f"red-goal-dev-{campaign_id}-{trial_index:02d}":
            raise RepeatableGoalManagerRunError("campaign_authentication")
        expected_claim = canonical_sha256(
            {
                "campaign_id": campaign_id,
                "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
                "trial_index": trial_index,
            }
        )
        if trial.get("trial_claim_sha256") != expected_claim:
            raise RepeatableGoalManagerRunError("campaign_authentication")


def _roots(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("roots")
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise RepeatableGoalManagerRunError("campaign_authentication")
    return tuple(cast(Mapping[str, object], item) for item in value)


def _outcome_objective() -> dict[str, object]:
    return goal_manager_development_outcome_objective()


def _trials(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("trials")
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise RepeatableGoalManagerRunError("campaign_authentication")
    return tuple(cast(Mapping[str, object], item) for item in value)


def _canonical_document(payload: bytes, *, subject: str) -> dict[str, object]:
    if not payload or len(payload) > _MAX_PLAN_BYTES:
        raise RepeatableGoalManagerRunError(f"{subject.replace(' ', '_')}_authentication")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise RepeatableGoalManagerRunError(
            f"{subject.replace(' ', '_')}_authentication"
        ) from None
    if not isinstance(value, dict) or _canonical_line(value) != payload:
        raise RepeatableGoalManagerRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _external_regular(path: Path, *, rom_path: Path) -> Path:
    resolved = path.resolve()
    try:
        metadata = path.lstat()
    except OSError:
        raise RepeatableGoalManagerRunError("external_input_authentication") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
    ):
        raise RepeatableGoalManagerRunError("external_input_authentication")
    return resolved


def _new_external_file(path: Path, *, rom_path: Path) -> Path:
    resolved = path.resolve()
    if (
        resolved.is_relative_to(PROJECT_ROOT.resolve())
        or resolved.parent == rom_path.resolve().parent
        or not resolved.parent.is_dir()
        or resolved.exists()
        or resolved.name.startswith(".")
    ):
        raise RepeatableGoalManagerRunError("campaign_destination")
    return resolved


def _open_bound_private_root(
    path: Path,
    *,
    rom_path: Path,
) -> tuple[PrivateArtifactRoot, str]:
    resolved = path.resolve()
    if resolved.is_relative_to(PROJECT_ROOT.resolve()) or resolved.parent == (
        rom_path.resolve().parent
    ):
        raise RepeatableGoalManagerRunError("private_root_authentication")
    try:
        metadata = path.lstat()
        store = open_private_root(path, repository_root=PROJECT_ROOT)
        sentinel_sha256 = _file_sha256(resolved / PRIVATE_ROOT_SENTINEL)
        metadata_after = resolved.lstat()
    except (OSError, RuntimeError):
        raise RepeatableGoalManagerRunError("private_root_authentication") from None
    if (
        path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or not stat.S_ISDIR(metadata_after.st_mode)
        or metadata.st_dev != metadata_after.st_dev
        or metadata.st_ino != metadata_after.st_ino
    ):
        raise RepeatableGoalManagerRunError("private_root_authentication")
    return store, canonical_sha256(
        {
            "device": metadata.st_dev,
            "inode": metadata.st_ino,
            "resolved_path": str(resolved),
            "schema": "pokemon.red.private-root-binding.v1",
            "sentinel_sha256": sentinel_sha256,
        }
    )


def _write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        with suppress(OSError):
            path.unlink()
        raise


def _trial_claim_marker(registry: Path, claim: str) -> Path:
    return registry / f"repeatable-development-{_sha(claim, 'trial claim')}.json"


def _trial_claim_is_available(registry: Path, claim: str) -> bool:
    marker = _trial_claim_marker(registry, claim)
    try:
        marker.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        raise RepeatableGoalManagerRunError("trial_claim_registry") from None
    return False


def _read_trial_claim(registry: Path, claim: str) -> Mapping[str, object]:
    marker = _trial_claim_marker(registry, claim)
    descriptor = -1
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        named_metadata = marker.lstat()
        descriptor = os.open(marker, flags)
        metadata = os.fstat(descriptor)
        if (
            named_metadata.st_dev != metadata.st_dev
            or named_metadata.st_ino != metadata.st_ino
            or named_metadata.st_nlink != metadata.st_nlink
        ):
            raise OSError("claim marker changed while opening")
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 1 <= metadata.st_size <= 4096
        ):
            raise OSError("claim marker metadata is invalid")
        payload = os.read(descriptor, metadata.st_size + 1)
    except OSError:
        raise RepeatableGoalManagerRunError("campaign_claim_authentication") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
    if (
        len(payload) != metadata.st_size
    ):
        raise RepeatableGoalManagerRunError("campaign_claim_authentication")
    return _canonical_document(payload, subject="campaign claim")


def _write_trial_claim(
    registry: Path,
    *,
    trial_claim_sha256: str,
    execution_identity_sha256: str,
    source_commit: str,
    runner_sha256: str,
) -> None:
    payload = _canonical_line(
        {
            "execution_identity_sha256": _sha(
                execution_identity_sha256,
                "execution identity",
            ),
            "runner_sha256": _sha(runner_sha256, "runner"),
            "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
            "source_commit": _text(source_commit, "source commit"),
            "trial_claim_sha256": _sha(trial_claim_sha256, "trial claim"),
        }
    )
    marker = _trial_claim_marker(registry, trial_claim_sha256)
    temporary = registry / (
        f".{marker.name}.pending-{os.getpid()}-{os.urandom(8).hex()}"
    )
    descriptor = -1
    directory_descriptor = -1
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(temporary, flags, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("trial claim write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            atomic_no_replace_rename(temporary, marker)
        except FileExistsError:
            raise RepeatableGoalManagerRunError("trial_already_consumed") from None
        directory_descriptor = os.open(
            registry,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        os.fsync(directory_descriptor)
    except RepeatableGoalManagerRunError:
        raise
    except OSError:
        raise RepeatableGoalManagerRunError("trial_claim_registry") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if directory_descriptor >= 0:
            with suppress(OSError):
                os.close(directory_descriptor)
        with suppress(OSError):
            temporary.unlink()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _protected_digests(paths: tuple[Path, ...]) -> tuple[tuple[Path, str], ...]:
    return tuple((path, _file_sha256(path)) for path in paths)


def _require_unchanged(protected: tuple[tuple[Path, str], ...]) -> None:
    try:
        if any(_file_sha256(path) != expected for path, expected in protected):
            raise RepeatableGoalManagerRunError("protected_input_integrity")
    except OSError:
        raise RepeatableGoalManagerRunError("protected_input_integrity") from None


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RepeatableGoalManagerRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise RepeatableGoalManagerRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise RepeatableGoalManagerRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _failure_receipt(stage: str) -> dict[str, object]:
    return {
        "schema": "pokemon.red.repeatable-goal-manager-development-failure.v1",
        "status": "failed_closed",
        "failure_stage": stage,
        "private_path_fields": 0,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "sealed_red_accesses": "not_attested_on_failure",
        "crystal_accesses": "not_attested_on_failure",
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        registry = open_fixed_account_claim_registry()
        with fixed_account_claim_registry_lease(registry, exclusive=True):
            readiness = _readiness(args)
            if args.mode == "freeze":
                if (
                    args.private_root is None
                    or args.trial_index is not None
                    or args.expected_campaign_sha256 is not None
                ):
                    raise RepeatableGoalManagerRunError("mode_arguments")
                result = _freeze(readiness, args.campaign_plan, args.private_root)
            elif args.mode == "preflight":
                if (
                    args.private_root is None
                    or args.trial_index is not None
                    or args.expected_campaign_sha256 is None
                ):
                    raise RepeatableGoalManagerRunError("mode_arguments")
                result = _preflight(
                    readiness,
                    args.campaign_plan,
                    args.private_root,
                    expected_campaign_sha256=args.expected_campaign_sha256,
                )
            elif args.mode == "admit":
                if (
                    args.private_root is None
                    or args.trial_index is not None
                    or args.expected_campaign_sha256 is None
                    or args.watch
                    or args.speed is not None
                ):
                    raise RepeatableGoalManagerRunError("mode_arguments")
                result = _admit_campaign(
                    readiness,
                    args.campaign_plan,
                    args.private_root,
                    expected_campaign_sha256=args.expected_campaign_sha256,
                )
            else:
                if (
                    args.private_root is None
                    or args.trial_index is None
                    or args.expected_campaign_sha256 is None
                ):
                    raise RepeatableGoalManagerRunError("mode_arguments")
                result = _execute(
                    readiness,
                    args.campaign_plan,
                    args.private_root,
                    trial_index=args.trial_index,
                    watch=args.watch,
                    speed=args.speed,
                    expected_campaign_sha256=args.expected_campaign_sha256,
                )
    except RepeatableGoalManagerRunError as error:
        print(json.dumps(_failure_receipt(error.stage), sort_keys=True))
        return 2
    except Exception:
        print(json.dumps(_failure_receipt("unexpected_failure"), sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
