#!/usr/bin/env python3
"""Preflight or execute one frozen Red multi-goal calibration trial."""

# ruff: noqa: E402 -- attest and prefer the reviewed scripts directory first

from __future__ import annotations

import argparse
import json
import re
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import run_repeatable_goal_manager_development as development

from pokemon_red_completion.bootstrap import DEFAULT_NEW_GAME_TIMING
from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.emulator import PyBoyAdapter
from pokemon_red_completion.executor import (
    CountingExecutor,
    FrameSafeExecutor,
    WindowedFrameBudgetController,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    CompositionIndependentBudgetMeter,
    HardCompositionActionLimiter,
    composition_skill_manifest,
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    write_root_claim,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    FRESH_COMPOSITION_FRAMES_PER_DECISION,
    FRESH_COMPOSITION_MAX_FRAMES,
)
from pokemon_red_completion.goal_manager_development import (
    goal_manager_development_numpy_runtime_sha256,
)
from pokemon_red_completion.goal_manager_trajectory import (
    GoalManagerTrajectoryObserver,
)
from pokemon_red_completion.multi_goal_calibration_admission import (
    MultiGoalCalibrationAdmissionError,
    admit_multi_goal_calibration_episode,
)
from pokemon_red_completion.multi_goal_calibration_execution import (
    MultiGoalCalibrationCampaign,
    MultiGoalCalibrationExecutionError,
    parse_multi_goal_calibration_campaign,
)
from pokemon_red_completion.multi_goal_calibration_outcome import (
    FORCED_CALIBRATION_POLICY_ID,
    ForcedCalibrationPolicy,
    run_forced_calibration_outcome,
)
from pokemon_red_completion.observation import PokemonRedStateReader
from pokemon_red_completion.private_artifacts import EpisodeWriter
from pokemon_red_completion.provenance import (
    detect_source_identity,
    require_clean_source,
    require_published_source,
)
from pokemon_red_completion.red_goal_context import build_red_goal_context_runtime
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder
from pokemon_red_completion.route_evidence import rom_adjacent_artifacts
from pokemon_red_completion.runtime_identity import (
    build_runtime_identity,
    require_pyboy_import_origins,
)
from pokemon_red_completion.trajectory import (
    JSONValue,
    RecordingExecutor,
    SparseEvent,
)
from pokemon_red_completion.trajectory_io import EpisodeTrajectorySink

INVENTORY_RESULT_PATH = (
    PROJECT_ROOT
    / "docs"
    / "evidence"
    / "red-multi-goal-curriculum-lineage-inventory-2026-09-03.json"
)
FREEZER_PATH = SCRIPTS_ROOT / "freeze_multi_goal_calibration_campaign.py"
DEVELOPMENT_RUNNER_PATH = SCRIPTS_ROOT / "run_repeatable_goal_manager_development.py"
CALIBRATION_ADMISSION_PATH = (
    PROJECT_ROOT
    / "src"
    / "pokemon_red_completion"
    / "multi_goal_calibration_admission.py"
)
CALIBRATION_EXECUTION_PATH = (
    PROJECT_ROOT
    / "src"
    / "pokemon_red_completion"
    / "multi_goal_calibration_execution.py"
)
CALIBRATION_OUTCOME_PATH = (
    PROJECT_ROOT
    / "src"
    / "pokemon_red_completion"
    / "multi_goal_calibration_outcome.py"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


class RunMultiGoalCalibrationError(RuntimeError):
    """A path-free execution or admission failure."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if stage.replace("_", "").isalnum() else "unexpected_failure"
        super().__init__(self.stage)


class _Readiness:
    def __init__(
        self,
        *,
        development_readiness: Any,
        runner_sha256: str,
        freezer_sha256: str,
        development_runner_sha256: str,
    ) -> None:
        self.development = development_readiness
        self.runner_sha256 = runner_sha256
        self.freezer_sha256 = freezer_sha256
        self.development_runner_sha256 = development_runner_sha256


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("preflight", "execute", "admit"),
        required=True,
    )
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--fit-summary", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--expected-freezer-sha256", required=True)
    parser.add_argument("--expected-development-runner-sha256", required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-numpy-runtime-sha256", required=True)
    parser.add_argument("--expected-skill-manifest-sha256", required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--expected-inventory-result-sha256", required=True)
    parser.add_argument("--expected-campaign-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--campaign-plan", type=Path, required=True)
    parser.add_argument("--trial-ordinal", type=int, required=True)
    return parser


def _readiness(args: argparse.Namespace) -> _Readiness:
    runner_path = Path(__file__).resolve()
    runner_sha256 = development._file_sha256(runner_path)
    freezer_sha256 = development._file_sha256(FREEZER_PATH)
    development_sha256 = development._file_sha256(DEVELOPMENT_RUNNER_PATH)
    if (
        runner_path.parent != SCRIPTS_ROOT.resolve()
        or runner_sha256 != _sha(args.expected_runner_sha256, "runner")
        or freezer_sha256 != _sha(args.expected_freezer_sha256, "freezer")
        or development_sha256
        != _sha(args.expected_development_runner_sha256, "development runner")
    ):
        raise RunMultiGoalCalibrationError("executable_attestation")
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    if (
        source.git_commit != args.expected_source_commit
        or not isinstance(source.git_commit, str)
        or _GIT_COMMIT.fullmatch(source.git_commit) is None
        or working_source_bundle_sha256(PROJECT_ROOT)
        != _sha(args.expected_source_bundle_sha256, "source bundle")
        or build_runtime_identity().sha256
        != _sha(args.expected_runtime_sha256, "runtime")
        or goal_manager_development_numpy_runtime_sha256()
        != _sha(args.expected_numpy_runtime_sha256, "NumPy runtime")
        or composition_skill_manifest(PROJECT_ROOT).get("manifest_sha256")
        != _sha(args.expected_skill_manifest_sha256, "skill manifest")
    ):
        raise RunMultiGoalCalibrationError("external_executable_attestation")
    inherited = development._readiness(
        argparse.Namespace(
            context_plan=args.context_plan,
            context_catalog=args.context_catalog,
            model=args.model,
            fit_summary=args.fit_summary,
            expected_source_commit=args.expected_source_commit,
            expected_source_bundle_sha256=args.expected_source_bundle_sha256,
            expected_runner_sha256=development_sha256,
            expected_runtime_sha256=args.expected_runtime_sha256,
            expected_numpy_runtime_sha256=args.expected_numpy_runtime_sha256,
            expected_skill_manifest_sha256=args.expected_skill_manifest_sha256,
            expected_context_plan_sha256=args.expected_context_plan_sha256,
            rom=args.rom,
        )
    )
    return _Readiness(
        development_readiness=inherited,
        runner_sha256=runner_sha256,
        freezer_sha256=freezer_sha256,
        development_runner_sha256=development_sha256,
    )


def _load_campaign(
    args: argparse.Namespace,
    readiness: _Readiness,
) -> tuple[Path, MultiGoalCalibrationCampaign, Any]:
    base = readiness.development
    path = development._external_regular(args.campaign_plan, rom_path=base.rom_path)
    try:
        payload = path.read_bytes()
        campaign = parse_multi_goal_calibration_campaign(payload)
    except (OSError, MultiGoalCalibrationExecutionError) as error:
        raise RunMultiGoalCalibrationError("campaign_authentication") from error
    if campaign.plan_sha256 != _sha(args.expected_campaign_sha256, "campaign"):
        raise RunMultiGoalCalibrationError("campaign_authentication")
    store, private_root_identity = development._open_bound_private_root(
        args.private_root,
        rom_path=base.rom_path,
    )
    if (
        campaign.freezer_runner_sha256 != readiness.freezer_sha256
        or campaign.development_runner_sha256
        != readiness.development_runner_sha256
        or campaign.runtime_sha256 != base.runtime.sha256
        or campaign.numpy_runtime_sha256 != base.numpy_runtime_sha256
        or campaign.skill_manifest_sha256 != base.skill_manifest_sha256
        or campaign.context_plan_sha256 != base.context_plan_sha256
        or campaign.inventory_result_sha256
        != _sha(args.expected_inventory_result_sha256, "inventory result")
        or campaign.private_root_identity_sha256 != private_root_identity
        or campaign.candidate != development._candidate_identity(base)
    ):
        raise RunMultiGoalCalibrationError("campaign_binding")
    if development._file_sha256(INVENTORY_RESULT_PATH) != campaign.inventory_result_sha256:
        raise RunMultiGoalCalibrationError("inventory_result_attestation")
    return path, campaign, store


def _root_claim_record(
    campaign: MultiGoalCalibrationCampaign,
    readiness: _Readiness,
) -> dict[str, str]:
    return {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "execution_identity_sha256": campaign.root_reservation_execution_identity(
            readiness.runner_sha256
        ),
        "source_commit": readiness.development.source.git_commit,
        "runner_sha256": readiness.runner_sha256,
    }


def _verify_roots_reservable(
    campaign: MultiGoalCalibrationCampaign,
    readiness: _Readiness,
    registry: Path,
) -> None:
    expected = _root_claim_record(campaign, readiness)
    inherited_identity: dict[str, object] | None = None
    for root in campaign.roots:
        if root_claim_is_available(registry, root.physical_root_sha256):
            continue
        observed = read_root_claim(registry, root.physical_root_sha256)
        observed_runner = observed.get("runner_sha256")
        observed_source = observed.get("source_commit")
        authentic_inherited = (
            set(observed)
            == {
                "execution_identity_sha256",
                "root_consumption_sha256",
                "runner_sha256",
                "schema",
                "source_commit",
            }
            and isinstance(observed_runner, str)
            and _SHA256.fullmatch(observed_runner) is not None
            and isinstance(observed_source, str)
            and _GIT_COMMIT.fullmatch(observed_source) is not None
            and observed.get("schema")
            == "pokemon.red.fresh-composition-root-claim.v1"
            and observed.get("root_consumption_sha256")
            == root.physical_root_sha256
            and observed.get("execution_identity_sha256")
            == campaign.root_reservation_execution_identity(observed_runner)
        )
        observed_identity = {
            key: value
            for key, value in observed.items()
            if key != "root_consumption_sha256"
        }
        if any(observed.get(key) != value for key, value in expected.items()) and not (
            authentic_inherited
            and (
                inherited_identity is None
                or observed_identity == inherited_identity
            )
        ):
            raise RunMultiGoalCalibrationError("closed_root_collision")
        if authentic_inherited:
            inherited_identity = observed_identity


def _reserve_all_roots(
    campaign: MultiGoalCalibrationCampaign,
    readiness: _Readiness,
    registry: Path,
) -> None:
    _verify_roots_reservable(campaign, readiness, registry)
    expected = _root_claim_record(campaign, readiness)
    for root in campaign.roots:
        if not root_claim_is_available(registry, root.physical_root_sha256):
            continue
        write_root_claim(
            registry,
            root_consumption_sha256=root.physical_root_sha256,
            execution_identity_sha256=expected["execution_identity_sha256"],
            source_commit=expected["source_commit"],
            runner_sha256=expected["runner_sha256"],
        )


def _selected_root(
    campaign: MultiGoalCalibrationCampaign,
    readiness: _Readiness,
    trial_ordinal: int,
) -> tuple[Any, Any]:
    if type(trial_ordinal) is not int or not 0 <= trial_ordinal < len(campaign.trials):  # noqa: E721
        raise RunMultiGoalCalibrationError("trial_selection")
    trial = campaign.trials[trial_ordinal]
    expected = campaign.roots[trial.root_ordinal]
    record = expected.record
    entry_index = record.get("entry_index")
    if (
        type(entry_index) is not int  # noqa: E721
        or not 0 <= entry_index < len(readiness.development.entries)
    ):
        raise RunMultiGoalCalibrationError("campaign_authentication")
    entry = readiness.development.entries[entry_index]
    root = development._open_frozen_root(
        readiness.development,
        entry,
        record,
        entry_index=entry_index,
    )
    return trial, root


def _preflight(
    args: argparse.Namespace,
    readiness: _Readiness,
    registry: Path,
) -> dict[str, object]:
    campaign_path, campaign, store = _load_campaign(args, readiness)
    trial, _root = _selected_root(campaign, readiness, args.trial_ordinal)
    _verify_roots_reservable(campaign, readiness, registry)
    if (
        store.inspect_episode_state(trial.episode_id).status != "absent"
        or not development._trial_claim_is_available(
            registry,
            trial.trial_claim_sha256,
        )
    ):
        raise RunMultiGoalCalibrationError("trial_already_consumed")
    protected = _protected_paths(readiness, campaign_path, trial.root_ordinal)
    _require_unchanged(protected)
    return {
        "campaign_plan_sha256": campaign.plan_sha256,
        "controller_actions": 0,
        "emulator_frames": 0,
        "model_predictions": 0,
        "private_path_fields": 0,
        "root_count": len(campaign.roots),
        "schema": "pokemon.red.multi-goal-calibration-preflight.v1",
        "status": "trial_ready",
        "teacher_queries": 0,
        "trial_count": len(campaign.trials),
        "trial_ordinal": trial.trial_ordinal,
    }


def _execute(
    args: argparse.Namespace,
    readiness: _Readiness,
    registry: Path,
) -> dict[str, object]:
    campaign_path, campaign, store = _load_campaign(args, readiness)
    trial, root = _selected_root(campaign, readiness, args.trial_ordinal)
    if (
        store.inspect_episode_state(trial.episode_id).status != "absent"
        or not development._trial_claim_is_available(
            registry,
            trial.trial_claim_sha256,
        )
    ):
        raise RunMultiGoalCalibrationError("trial_already_consumed")
    protected = _protected_paths(readiness, campaign_path, trial.root_ordinal)
    adjacent_before = rom_adjacent_artifacts(readiness.development.rom_path)
    _reserve_all_roots(campaign, readiness, registry)
    execution_identity = campaign.trial_execution_identity(
        trial.trial_ordinal,
        readiness.runner_sha256,
    )
    development._write_trial_claim(
        registry,
        trial_claim_sha256=trial.trial_claim_sha256,
        execution_identity_sha256=execution_identity,
        source_commit=readiness.development.source.git_commit,
        runner_sha256=readiness.runner_sha256,
    )
    writer: EpisodeWriter | None = None
    sink: EpisodeTrajectorySink | None = None
    recorder: RecordingExecutor[Any, Any] | None = None
    try:
        writer = store.begin_episode(trial.episode_id)
        sink = EpisodeTrajectorySink(
            writer,
            episode_id=trial.episode_id,
            game_id="pokemon.mainline:red:gb:us:rev0",
            durable_writes=True,
        )
        sink.write_episode_header(
            metadata=_episode_metadata(
                readiness,
                campaign=campaign,
                root=root,
                trial=trial,
                execution_identity=execution_identity,
            )
        )
        with PyBoyAdapter(
            readiness.development.rom_path,
            watch=False,
            speed=None,
        ) as emulator:
            require_pyboy_import_origins(readiness.development.runtime)
            emulator.load_state_bytes(root.capture.state_bytes)
            require_pyboy_import_origins(readiness.development.runtime)
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
            snapshot = PokemonRedObservationEncoder.from_state_reader(reader)
            recorder = RecordingExecutor(
                delegate=frame_safe,
                snapshot_provider=snapshot,
                sink=sink,
                episode_id=trial.episode_id,
            )
            hard_actions = HardCompositionActionLimiter(recorder)
            actions = CountingExecutor(hard_actions)
            meter = CompositionIndependentBudgetMeter(hard_actions, frames)
            trajectory = GoalManagerTrajectoryObserver(
                episode_id=trial.episode_id,
                root_lineage_id=root.assignment.root_lineage_id,
                partition="train",
                environment_id="pokemon.mainline:red:gb:us:rev0",
                actor="forced_calibration_arm",
                policy_id=FORCED_CALIBRATION_POLICY_ID,
                collection_id=campaign.campaign_id,
                assignment_id=trial.trial_claim_sha256,
                source_commit=readiness.development.source.git_commit,
                snapshot_provider=snapshot,
                recorder=recorder,
                sink=sink,
                ordering_assignment_id=root.assignment.assignment_id,
            )
            policy = ForcedCalibrationPolicy(
                selected_available_ordinal=trial.selected_candidate_index,
                selected_goal_kind=trial.selected_goal_kind,
                expected_question_sha256=root.question_sha256,
                expected_policy_context_sha256=root.policy_context_sha256,
                expected_available_menu_sha256=root.available_menu_sha256,
            )
            observe = development._live_observer(
                runtime=runtime,
                actions=actions,
                meter=meter,
                root=root,
            )
            outcome = run_forced_calibration_outcome(
                observe=observe,
                policy=policy,
                trajectory=trajectory,
                budget_meter=meter,
            )
            if recorder.recording_failures:
                raise RunMultiGoalCalibrationError("trajectory_durability")
            require_pyboy_import_origins(readiness.development.runtime)
        _require_unchanged(protected)
        if rom_adjacent_artifacts(readiness.development.rom_path) != adjacent_before:
            raise RunMultiGoalCalibrationError("protected_input_integrity")
        sink.record_event(
            SparseEvent(
                event_id=f"{trial.episode_id}:terminal",
                episode_id=trial.episode_id,
                step_index=recorder.next_step_index,
                kind="terminal",
                payload={
                    "status": "complete",
                    "calibration": cast(
                        dict[str, JSONValue],
                        outcome.public_dict(),
                    ),
                },
            )
        )
        sink.finalize()
        summary = writer.complete()
        return {
            "calibration": outcome.public_dict(),
            "campaign_plan_sha256": campaign.plan_sha256,
            "private_artifact": {
                "manifest_sha256": summary.manifest_sha256,
                "status": summary.status,
                "stream_records": dict(summary.stream_records),
                "total_records": summary.total_records,
            },
            "private_path_fields": 0,
            "schema": "pokemon.red.multi-goal-calibration-trial-summary.v1",
            "status": "complete",
            "teacher_queries": 0,
            "trial_ordinal": trial.trial_ordinal,
        }
    except BaseException as error:
        if writer is not None:
            _retain_failure(
                writer,
                sink=sink,
                episode_id=trial.episode_id,
                step_index=0 if recorder is None else recorder.next_step_index,
                failure_stage=(
                    error.stage
                    if isinstance(error, RunMultiGoalCalibrationError)
                    else "calibration_runtime"
                ),
            )
        raise


def _admit(
    args: argparse.Namespace,
    readiness: _Readiness,
    registry: Path,
) -> dict[str, object]:
    campaign_path, campaign, store = _load_campaign(args, readiness)
    if type(args.trial_ordinal) is not int or not (  # noqa: E721
        0 <= args.trial_ordinal < len(campaign.trials)
    ):
        raise RunMultiGoalCalibrationError("trial_selection")
    trial = campaign.trials[args.trial_ordinal]
    root_record = campaign.roots[trial.root_ordinal].record
    entry_index = root_record.get("entry_index")
    if type(entry_index) is not int or not (  # noqa: E721
        0 <= entry_index < len(readiness.development.entries)
    ):
        raise RunMultiGoalCalibrationError("campaign_authentication")
    entry = readiness.development.entries[entry_index]
    context_entry = readiness.development.candidate.catalog.entry(entry.slot_id)
    execution_identity = campaign.trial_execution_identity(
        trial.trial_ordinal,
        readiness.runner_sha256,
    )
    try:
        claim = development._read_trial_claim(registry, trial.trial_claim_sha256)
    except Exception as error:
        raise RunMultiGoalCalibrationError("trial_claim_authentication") from error
    if claim != {
        "execution_identity_sha256": execution_identity,
        "runner_sha256": readiness.runner_sha256,
        "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
        "source_commit": readiness.development.source.git_commit,
        "trial_claim_sha256": trial.trial_claim_sha256,
    }:
        raise RunMultiGoalCalibrationError("trial_claim_authentication")
    state = store.inspect_episode_state(trial.episode_id)
    if state.status != "complete":
        raise RunMultiGoalCalibrationError("episode_not_complete")
    protected = _protected_paths(readiness, campaign_path, trial.root_ordinal)
    _require_unchanged(protected)
    try:
        admitted = admit_multi_goal_calibration_episode(
            store.open_episode(trial.episode_id),
            expected_episode_id=trial.episode_id,
            expected_campaign_id=campaign.campaign_id,
            expected_trial_claim_sha256=trial.trial_claim_sha256,
            expected_execution_identity_sha256=execution_identity,
            expected_root_lineage_id=str(root_record["root_lineage_id"]),
            expected_context_catalog_sha256=(
                readiness.development.candidate.catalog.catalog_sha256
            ),
            expected_context_id=context_entry.context_id,
            expected_binding_manifest_sha256=str(
                root_record["binding_manifest_sha256"]
            ),
            expected_state_sha256=str(root_record["state_sha256"]),
            expected_envelope_sha256=str(root_record["envelope_sha256"]),
            expected_question_sha256=str(root_record["question_sha256"]),
            expected_policy_context_sha256=str(
                root_record["policy_context_sha256"]
            ),
            expected_available_menu_sha256=str(
                root_record["available_menu_sha256"]
            ),
            expected_selected_available_ordinal=trial.selected_candidate_index,
            expected_selected_goal_kind=trial.selected_goal_kind,
            expected_source_commit=readiness.development.source.git_commit,
            expected_trial_ordinal=trial.trial_ordinal,
        )
    except MultiGoalCalibrationAdmissionError as error:
        raise RunMultiGoalCalibrationError("episode_admission") from error
    _require_unchanged(protected)
    return {
        "admitted_outcome": admitted.public_dict(),
        "campaign_plan_sha256": campaign.plan_sha256,
        "private_path_fields": 0,
        "schema": "pokemon.red.multi-goal-calibration-admission-receipt.v1",
        "status": "admitted",
        "teacher_queries": 0,
        "trial_ordinal": trial.trial_ordinal,
    }


def _episode_metadata(
    readiness: _Readiness,
    *,
    campaign: MultiGoalCalibrationCampaign,
    root: Any,
    trial: Any,
    execution_identity: str,
) -> dict[str, object]:
    base = readiness.development
    return {
        "policy": {
            "actor": "forced_calibration_arm",
            "policy_id": FORCED_CALIBRATION_POLICY_ID,
        },
        "split": {
            "partition": "train",
            "root_lineage_id": root.assignment.root_lineage_id,
        },
        "goal_manager": {
            "assignment_id": trial.trial_claim_sha256,
            "binding_manifest_sha256": root.binding_manifest_sha256,
            "collection_id": campaign.campaign_id,
            "context_catalog_sha256": base.candidate.catalog.catalog_sha256,
            "context_id": base.candidate.catalog.entry(root.entry.slot_id).context_id,
            "envelope_sha256": root.capture.envelope_sha256,
            "execution_identity_sha256": execution_identity,
            "source_commit": base.source.git_commit,
            "state_sha256": root.capture.state_sha256,
        },
        "calibration": {
            "assignment_probability": 1.0,
            "maximum_decisions": 1,
            "outcome_objective": (
                "selected-semantic-option-multioutcome-calibration-v1"
            ),
            "teacher_queries": 0,
            "trial_ordinal": trial.trial_ordinal,
        },
    }


def _protected_paths(
    readiness: _Readiness,
    campaign_path: Path,
    root_ordinal: int,
) -> tuple[tuple[Path, str], ...]:
    campaign = parse_multi_goal_calibration_campaign(campaign_path.read_bytes())
    root = campaign.roots[root_ordinal]
    entry_index = root.record["entry_index"]
    assert isinstance(entry_index, int)
    entry = readiness.development.entries[entry_index]
    return development._protected_digests(
        (
            readiness.development.context_plan_path,
            campaign_path,
            readiness.development.context_catalog_path,
            readiness.development.model_path,
            readiness.development.fit_summary_path,
            entry.state,
            entry.envelope,
            entry.profile,
            readiness.development.rom_path,
            INVENTORY_RESULT_PATH,
            FREEZER_PATH,
            DEVELOPMENT_RUNNER_PATH,
            CALIBRATION_ADMISSION_PATH,
            CALIBRATION_EXECUTION_PATH,
            CALIBRATION_OUTCOME_PATH,
            Path(__file__).resolve(),
        )
    )


def _require_unchanged(protected: tuple[tuple[Path, str], ...]) -> None:
    try:
        development._require_unchanged(protected)
    except Exception as error:
        raise RunMultiGoalCalibrationError("protected_input_integrity") from error


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
        writer.abort("multi_goal_calibration_failed")


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RunMultiGoalCalibrationError(f"{subject.replace(' ', '_')}_attestation")
    return value


def _failure_receipt(stage: str) -> dict[str, object]:
    return {
        "controller_effects": "not_attested_on_failure",
        "failure_stage": stage,
        "private_path_fields": 0,
        "schema": "pokemon.red.multi-goal-calibration-trial-failure.v1",
        "status": "failed_closed",
        "teacher_queries": 0,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        registry = open_fixed_account_claim_registry()
        with fixed_account_claim_registry_lease(registry, exclusive=True):
            readiness = _readiness(args)
            if args.mode == "preflight":
                result = _preflight(args, readiness, registry)
            elif args.mode == "execute":
                result = _execute(args, readiness, registry)
            else:
                result = _admit(args, readiness, registry)
    except Exception as error:
        stage = (
            error.stage
            if isinstance(error, RunMultiGoalCalibrationError)
            else "unexpected_failure"
        )
        print(json.dumps(_failure_receipt(stage), sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
