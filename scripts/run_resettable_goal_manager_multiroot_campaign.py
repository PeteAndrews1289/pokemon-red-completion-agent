#!/usr/bin/env python3
# mypy: disable-error-code=attr-defined
"""Freeze, run, and strictly admit the resettable 8/4 Red curriculum."""

# ruff: noqa: E402 -- reviewed local runners must win import resolution

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import run_paired_goal_manager_outcome_screen as paired
import run_repeatable_goal_manager_development as development

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    root_consumption_sha256,
    write_root_claim,
)
from pokemon_red_completion.goal_manager_development import (
    AdmittedGoalManagerDevelopmentEpisode,
    repeatable_goal_manager_trial_execution_identity,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.resettable_goal_manager_multiroot_learning import (
    MULTIROOT_DEVELOPMENT_EPISODES,
    MULTIROOT_EPISODES_PER_ROOT,
    MULTIROOT_TRAIN_EPISODES,
)
from pokemon_red_completion.trajectory import JSONValue

CAMPAIGN_SCHEMA = "pokemon.red.resettable-goal-manager-multiroot-campaign.v1"
TRAIN_ROOT_SPECS = (
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.MANAGE_STORAGE,
    GoalKind.DEVELOP_TEAM,
    GoalKind.RESTORE_TEAM,
)
DEVELOPMENT_ROOT_SPECS = (
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.DEVELOP_TEAM,
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_DOCUMENT_BYTES = 4 * 1024 * 1024


class ResettableMultirootRunError(RuntimeError):
    """A path-free failure at one resettable-curriculum stage."""


@dataclass(frozen=True, slots=True)
class _Readiness:
    paired: paired._Readiness
    runner_sha256: str


@dataclass(frozen=True, slots=True)
class _QualifiedCampaign:
    plan: Mapping[str, object]
    plan_sha256: str
    plan_path: Path
    roots: tuple[development._Root, ...]
    store: Any


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("freeze", "preflight", "execute", "resume"),
        required=True,
    )
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--base-fit-summary", type=Path, required=True)
    parser.add_argument("--candidate-model", type=Path, required=True)
    parser.add_argument("--candidate-fit-summary", type=Path, required=True)
    parser.add_argument("--fit-result-receipt", type=Path, required=True)
    parser.add_argument("--prior-campaign", type=Path, action="append", required=True)
    parser.add_argument(
        "--expected-prior-campaign-sha256",
        action="append",
        required=True,
    )
    parser.add_argument("--expected-fit-result-receipt-sha256", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--expected-paired-runner-sha256", required=True)
    parser.add_argument("--expected-development-runner-sha256", required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-numpy-runtime-sha256", required=True)
    parser.add_argument("--expected-skill-manifest-sha256", required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--campaign-plan", type=Path, required=True)
    parser.add_argument("--expected-campaign-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        readiness = _readiness(args)
        if args.mode == "freeze":
            if args.expected_campaign_sha256 is not None:
                raise ResettableMultirootRunError("mode_arguments")
            result = _freeze(readiness, args.campaign_plan, args.private_root)
        else:
            expected = _sha(args.expected_campaign_sha256, "campaign")
            qualified = _qualify(
                readiness,
                args.campaign_plan,
                args.private_root,
                expected_campaign_sha256=expected,
                require_unclaimed=args.mode in {"preflight", "execute"},
            )
            if args.mode == "preflight":
                result = _preflight(readiness, qualified)
            elif args.mode == "execute":
                result = _execute(readiness, qualified, resume=False)
            else:
                result = _execute(readiness, qualified, resume=True)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema": "pokemon.red.resettable-goal-manager-multiroot-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": _failure_stage(error),
                    "effects": "not_attested_on_failure",
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _readiness(args: argparse.Namespace) -> _Readiness:
    paired_path = (SCRIPTS_ROOT / "run_paired_goal_manager_outcome_screen.py").resolve()
    development_path = (SCRIPTS_ROOT / "run_repeatable_goal_manager_development.py").resolve()
    if (
        not isinstance(getattr(paired, "__file__", None), str)
        or Path(paired.__file__).resolve(strict=True) != paired_path
        or not isinstance(getattr(development, "__file__", None), str)
        or Path(development.__file__).resolve(strict=True) != development_path
        or _file_sha256(paired_path) != _sha(args.expected_paired_runner_sha256, "paired runner")
    ):
        raise ResettableMultirootRunError("import_origin_attestation")
    paired_args = _paired_readiness_args(args)
    paired_readiness = paired._readiness(paired_args)
    runner_path = Path(__file__).resolve()
    runner_sha256 = _file_sha256(runner_path)
    if runner_path.parent != SCRIPTS_ROOT.resolve() or runner_sha256 != _sha(
        args.expected_runner_sha256, "runner"
    ):
        raise ResettableMultirootRunError("executable_attestation")
    return _Readiness(paired=paired_readiness, runner_sha256=runner_sha256)


def _paired_readiness_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        context_plan=args.context_plan,
        context_catalog=args.context_catalog,
        base_model=args.base_model,
        base_fit_summary=args.base_fit_summary,
        candidate_model=args.candidate_model,
        candidate_fit_summary=args.candidate_fit_summary,
        fit_result_receipt=args.fit_result_receipt,
        prior_campaign=args.prior_campaign,
        expected_prior_campaign_sha256=args.expected_prior_campaign_sha256,
        expected_fit_result_receipt_sha256=args.expected_fit_result_receipt_sha256,
        expected_source_commit=args.expected_source_commit,
        expected_source_bundle_sha256=args.expected_source_bundle_sha256,
        expected_runner_sha256=args.expected_paired_runner_sha256,
        expected_development_runner_sha256=args.expected_development_runner_sha256,
        expected_runtime_sha256=args.expected_runtime_sha256,
        expected_numpy_runtime_sha256=args.expected_numpy_runtime_sha256,
        expected_skill_manifest_sha256=args.expected_skill_manifest_sha256,
        expected_context_plan_sha256=args.expected_context_plan_sha256,
        allow_historical_context_plan=True,
        rom=args.rom,
    )


def _freeze(readiness: _Readiness, destination: Path, private_root: Path) -> dict[str, object]:
    base = readiness.paired.development
    destination = development._new_external_file(destination, rom_path=base.rom_path)
    _store, private_root_identity = development._open_bound_private_root(
        private_root,
        rom_path=base.rom_path,
    )
    registry = open_fixed_account_claim_registry()
    prior_lineages, prior_state_envelope = _prior_root_identities(readiness.paired.prior_campaigns)
    selected: list[tuple[str, development._Root]] = []
    seen_state_envelope: set[tuple[str, str]] = set()
    for partition, registry_partition, kinds in (
        ("train", "train", TRAIN_ROOT_SPECS),
        ("development", "validation", DEVELOPMENT_ROOT_SPECS),
    ):
        for kind in kinds:
            chosen: development._Root | None = None
            for entry_index, entry in enumerate(base.entries):
                assignment = base.candidate.registry.assignment(entry.slot_id)
                if (
                    assignment.partition != registry_partition
                    or assignment.focus_kind is not kind
                    or assignment.root_lineage_id in prior_lineages
                    or not development._historical_root_is_open(base, entry, registry)
                ):
                    continue
                inspected = development._inspect_root(
                    base,
                    entry,
                    entry_index=entry_index,
                    ordering_assignment_id=assignment.assignment_id,
                )
                if inspected is None:
                    continue
                root_identity = (
                    inspected.capture.state_sha256,
                    inspected.capture.envelope_sha256,
                )
                if (
                    root_identity in seen_state_envelope
                    or root_identity in prior_state_envelope
                    or kind.value not in inspected.available_goal_kinds
                    or len(inspected.available_goal_kinds) < 2
                    or GoalKind.EVOLVE_SPECIES.value in inspected.available_goal_kinds
                ):
                    continue
                chosen = inspected
                seen_state_envelope.add(root_identity)
                break
            if chosen is None:
                raise ResettableMultirootRunError("action_free_root_inventory")
            selected.append((partition, chosen))

    roots: list[dict[str, object]] = []
    for partition, root in selected:
        record = development._private_root_record(root)
        roots.append(
            {
                "partition": partition,
                "root_consumption_sha256": root_consumption_sha256(
                    state_sha256=root.capture.state_sha256,
                    envelope_sha256=root.capture.envelope_sha256,
                ),
                "root": record,
            }
        )
    trial_rows: list[dict[str, object]] = []
    for root_index, root_payload in enumerate(roots):
        for offset in range(MULTIROOT_EPISODES_PER_ROOT):
            trial_rows.append(
                {
                    "maximum_decisions": 1,
                    "partition": root_payload["partition"],
                    "root_index": root_index,
                    "seed": 30_000 + root_index * 100 + offset,
                    "trial_index": len(trial_rows),
                }
            )
    identity = {
        "base_model_canonical_sha256": (readiness.paired.candidate_model_canonical_sha256),
        "context_plan_sha256": base.context_plan_sha256,
        "numpy_runtime_sha256": base.numpy_runtime_sha256,
        "outcome_objective": development.goal_manager_development_outcome_objective(),
        "private_root_identity_sha256": private_root_identity,
        "prior_campaign_sha256": list(readiness.paired.prior_campaign_sha256),
        "roots": roots,
        "runner_sha256": readiness.runner_sha256,
        "runtime_sha256": base.runtime.sha256,
        "schema": CAMPAIGN_SCHEMA,
        "skill_manifest_sha256": base.skill_manifest_sha256,
        "source_bundle_sha256": base.source_bundle_sha256,
        "source_commit": base.source.git_commit,
        "trials": trial_rows,
    }
    campaign_id = canonical_sha256(identity)
    trials = [
        {
            **trial,
            "episode_id": f"red-multiroot-{campaign_id[:32]}-{trial['trial_index']:02d}",
            "trial_claim_sha256": canonical_sha256(
                {
                    "campaign_id": campaign_id,
                    "schema": "pokemon.red.resettable-goal-manager-trial-claim.v1",
                    "trial_index": trial["trial_index"],
                }
            ),
        }
        for trial in trial_rows
    ]
    plan = {
        **identity,
        "campaign_id": campaign_id,
        "campaign_consumption_sha256": canonical_sha256(
            {
                "campaign_id": campaign_id,
                "schema": "pokemon.red.resettable-goal-manager-campaign-consumption.v1",
            }
        ),
        "trials": trials,
    }
    development._write_exclusive(destination, _canonical_line(plan))
    return {
        "schema": "pokemon.red.resettable-goal-manager-multiroot-freeze.v1",
        "status": "six_roots_and_twelve_resets_frozen_without_prediction_or_action",
        "campaign_plan_sha256": hashlib.sha256(_canonical_line(plan)).hexdigest(),
        "train_roots": 4,
        "development_roots": 2,
        "train_episodes": MULTIROOT_TRAIN_EPISODES,
        "development_episodes": MULTIROOT_DEVELOPMENT_EPISODES,
        "model_predictions": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "private_path_fields": 0,
    }


def _qualify(
    readiness: _Readiness,
    campaign_path: Path,
    private_root: Path,
    *,
    expected_campaign_sha256: str,
    require_unclaimed: bool,
) -> _QualifiedCampaign:
    base = readiness.paired.development
    store, private_root_identity = development._open_bound_private_root(
        private_root,
        rom_path=base.rom_path,
    )
    path = development._external_regular(campaign_path, rom_path=base.rom_path)
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_campaign_sha256:
        raise ResettableMultirootRunError("campaign_attestation")
    plan = development._canonical_document(payload, subject="multiroot campaign")
    _validate_plan(readiness, plan, private_root_identity=private_root_identity)
    inspected_roots: list[development._Root] = []
    for record in _root_records(plan):
        frozen = _mapping(record.get("root"), "root")
        entry_index = _integer(frozen.get("entry_index"), "entry index")
        if entry_index >= len(base.entries):
            raise ResettableMultirootRunError("root_attestation")
        entry = base.entries[entry_index]
        root = development._inspect_root(
            base,
            entry,
            entry_index=entry_index,
            ordering_assignment_id=_sha(frozen.get("assignment_id"), "assignment"),
        )
        expected_registry_partition = (
            "train" if record.get("partition") == "train" else "validation"
        )
        if (
            root is None
            or root.assignment.partition != expected_registry_partition
            or development._private_root_record(root) != frozen
        ):
            raise ResettableMultirootRunError("root_drift")
        inspected_roots.append(root)
    if require_unclaimed:
        registry = open_fixed_account_claim_registry()
        with fixed_account_claim_registry_lease(registry, exclusive=False):
            claims = (
                _sha(plan.get("campaign_consumption_sha256"), "campaign consumption"),
                *(
                    _sha(record.get("root_consumption_sha256"), "root consumption")
                    for record in _root_records(plan)
                ),
            )
            if any(not root_claim_is_available(registry, claim) for claim in claims):
                raise ResettableMultirootRunError("campaign_already_consumed")
            for trial in _trials(plan):
                if store.inspect_episode_state(
                    _text(trial.get("episode_id"), "episode")
                ).status != "absent" or not development._trial_claim_is_available(
                    registry,
                    _sha(trial.get("trial_claim_sha256"), "trial claim"),
                ):
                    raise ResettableMultirootRunError("campaign_already_consumed")
    return _QualifiedCampaign(
        plan=plan,
        plan_sha256=digest,
        plan_path=path,
        roots=tuple(inspected_roots),
        store=store,
    )


def _preflight(readiness: _Readiness, qualified: _QualifiedCampaign) -> dict[str, object]:
    return {
        "schema": "pokemon.red.resettable-goal-manager-multiroot-preflight.v1",
        "status": "ready_without_prediction_or_action",
        "campaign_plan_sha256": qualified.plan_sha256,
        "source_commit": readiness.paired.development.source.git_commit,
        "runner_sha256": readiness.runner_sha256,
        "base_model_canonical_sha256": (readiness.paired.candidate_model_canonical_sha256),
        "train_roots": 4,
        "development_roots": 2,
        "planned_trials": 12,
        "claims_consumed": 0,
        "model_predictions": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "private_path_fields": 0,
    }


def _claim_campaign(readiness: _Readiness, qualified: _QualifiedCampaign) -> None:
    base = readiness.paired.development
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        root_claims = (
            _sha(
                qualified.plan.get("campaign_consumption_sha256"),
                "campaign consumption",
            ),
            *(
                _sha(record.get("root_consumption_sha256"), "root consumption")
                for record in _root_records(qualified.plan)
            ),
        )
        if any(not root_claim_is_available(registry, claim) for claim in root_claims):
            raise ResettableMultirootRunError("campaign_already_consumed")
        for trial in _trials(qualified.plan):
            if qualified.store.inspect_episode_state(
                _text(trial.get("episode_id"), "episode")
            ).status != "absent" or not development._trial_claim_is_available(
                registry,
                _sha(trial.get("trial_claim_sha256"), "trial claim"),
            ):
                raise ResettableMultirootRunError("campaign_already_consumed")
        for claim in root_claims:
            write_root_claim(
                registry,
                root_consumption_sha256=claim,
                execution_identity_sha256=_campaign_execution_identity(
                    readiness,
                    qualified,
                ),
                source_commit=base.source.git_commit or "",
                runner_sha256=readiness.runner_sha256,
            )
        for trial in _trials(qualified.plan):
            development._write_trial_claim(
                registry,
                trial_claim_sha256=_sha(trial.get("trial_claim_sha256"), "trial claim"),
                execution_identity_sha256=_trial_execution_identity(
                    readiness,
                    qualified,
                    trial,
                ),
                source_commit=base.source.git_commit or "",
                runner_sha256=readiness.runner_sha256,
            )


def _execute(
    readiness: _Readiness,
    qualified: _QualifiedCampaign,
    *,
    resume: bool,
) -> dict[str, object]:
    campaign_id = _sha(qualified.plan.get("campaign_id"), "campaign")
    with qualified.store.collection_session(campaign_id) as session:
        registry = open_fixed_account_claim_registry()
        terminal_identity = _campaign_terminal_identity(qualified)
        if not root_claim_is_available(registry, terminal_identity):
            raise ResettableMultirootRunError("campaign_already_closed")
        if resume:
            _require_consumption_claims(readiness, qualified, registry)
            _require_trial_claims(readiness, qualified, registry)
        else:
            _claim_campaign(readiness, qualified)
        results: list[dict[str, object]] = []
        for trial in _trials(qualified.plan):
            episode_id = _text(trial.get("episode_id"), "episode")
            existing = session.inspect_episode(episode_id)
            if resume and existing.status == "partial":
                existing = session.recover_interrupted_episode(episode_id)
            if resume and existing.status != "absent":
                results.append(
                    {
                        "trial_index": _integer(
                            trial.get("trial_index"),
                            "trial index",
                        ),
                        "partition": _partition(trial.get("partition")),
                        "status": "existing_terminal_not_retried",
                        "artifact_state": existing.status,
                    }
                )
                continue
            try:
                results.append(_execute_trial(readiness, qualified, trial))
            except Exception as error:
                artifact_state = session.inspect_episode(episode_id).status
                if artifact_state == "partial":
                    artifact_state = session.recover_interrupted_episode(episode_id).status
                results.append(
                    _failure_row(
                        trial,
                        artifact_state=artifact_state,
                        error=error,
                    )
                )
        if any(
            session.inspect_episode(_text(trial.get("episode_id"), "episode")).status
            in {"absent", "partial"}
            for trial in _trials(qualified.plan)
        ):
            raise ResettableMultirootRunError("campaign_terminal_incomplete")
        with fixed_account_claim_registry_lease(registry, exclusive=True):
            if not root_claim_is_available(registry, terminal_identity):
                raise ResettableMultirootRunError("campaign_already_closed")
            write_root_claim(
                registry,
                root_consumption_sha256=terminal_identity,
                execution_identity_sha256=_campaign_execution_identity(
                    readiness,
                    qualified,
                ),
                source_commit=readiness.paired.development.source.git_commit or "",
                runner_sha256=readiness.runner_sha256,
            )
    return {
        "schema": "pokemon.red.resettable-goal-manager-multiroot-execution.v1",
        "status": "fixed_denominator_consumed_pending_strict_admission",
        "campaign_plan_sha256": qualified.plan_sha256,
        "campaign_terminal_sha256": terminal_identity,
        "trials": results,
        "complete_trials": sum(
            row["status"] == "complete" or row.get("artifact_state") == "complete"
            for row in results
        ),
        "failed_trials": sum(
            row["status"] != "complete" and row.get("artifact_state") != "complete"
            for row in results
        ),
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "private_path_fields": 0,
    }


def _execute_trial(
    readiness: _Readiness,
    qualified: _QualifiedCampaign,
    trial: Mapping[str, object],
) -> dict[str, object]:
    base = readiness.paired.development
    root_index = _integer(trial.get("root_index"), "root index")
    root_record = _mapping(_root_records(qualified.plan)[root_index].get("root"), "root")
    frozen_root = qualified.roots[root_index]
    root = development._inspect_root(
        base,
        frozen_root.entry,
        entry_index=_integer(root_record.get("entry_index"), "entry index"),
        ordering_assignment_id=_sha(root_record.get("assignment_id"), "assignment"),
    )
    if root is None or development._private_root_record(root) != root_record:
        raise ResettableMultirootRunError("root_drift_after_claim")
    partition = _partition(trial.get("partition"))
    episode_id = _text(trial.get("episode_id"), "episode")
    claim = _sha(trial.get("trial_claim_sha256"), "trial claim")
    seed = _integer(trial.get("seed"), "seed")
    protected = development._protected_digests(
        (
            base.context_plan_path,
            base.context_catalog_path,
            base.model_path,
            base.fit_summary_path,
            readiness.paired.candidate_model_path,
            qualified.plan_path,
            root.entry.state,
            root.entry.envelope,
            root.entry.profile,
            base.rom_path,
        )
    )
    adjacent_before = development.rom_adjacent_artifacts(base.rom_path)
    writer: Any | None = None
    sink: Any | None = None
    recorder: Any | None = None
    try:
        writer = qualified.store.begin_episode(episode_id)
        sink = development.EpisodeTrajectorySink(
            writer,
            episode_id=episode_id,
            game_id="pokemon.mainline:red:gb:us:rev0",
            durable_writes=True,
        )
        sink.write_episode_header(
            metadata=_episode_metadata(
                readiness,
                qualified,
                root=root,
                root_record=root_record,
                partition=partition,
                claim=claim,
                execution_identity_sha256=_trial_execution_identity(
                    readiness,
                    qualified,
                    trial,
                ),
            )
        )
        with development.PyBoyAdapter(base.rom_path, watch=False, speed=None) as emulator:
            development.require_pyboy_import_origins(base.runtime)
            emulator.load_state_bytes(root.capture.state_bytes)
            development.require_pyboy_import_origins(base.runtime)
            frames = development.WindowedFrameBudgetController(
                emulator,
                maximum_frames_per_window=(development.FRESH_COMPOSITION_FRAMES_PER_DECISION),
                maximum_total_frames=development.FRESH_COMPOSITION_FRAMES_PER_DECISION,
            )
            reader = development.PokemonRedStateReader(frames)
            runtime = development.build_red_goal_context_runtime(
                profile=root.profile,
                capture=root.capture,
                emulator=frames,
                reader=reader,
            )
            frame_safe = development.FrameSafeExecutor(
                frames,
                development.DEFAULT_NEW_GAME_TIMING.controller_timing(),
            )
            snapshot_provider = development.PokemonRedObservationEncoder.from_state_reader(reader)
            recorder = development.RecordingExecutor(
                delegate=frame_safe,
                snapshot_provider=snapshot_provider,
                sink=sink,
                episode_id=episode_id,
            )
            hard_actions = development.HardCompositionActionLimiter(
                recorder,
                maximum_episode_actions=(development.FRESH_COMPOSITION_ACTIONS_PER_DECISION),
            )
            actions = development.CountingExecutor(hard_actions)
            meter = development.CompositionIndependentBudgetMeter(hard_actions, frames)
            trajectory = development.GoalManagerTrajectoryObserver(
                episode_id=episode_id,
                root_lineage_id=_text(root_record.get("root_lineage_id"), "root lineage"),
                partition=partition,
                environment_id="pokemon.mainline:red:gb:us:rev0",
                actor="exploratory_goal_manager",
                policy_id="red-goal-manager-outcome-development-v1",
                collection_id=_sha(qualified.plan.get("campaign_id"), "campaign"),
                assignment_id=claim,
                source_commit=base.source.git_commit or "",
                snapshot_provider=snapshot_provider,
                recorder=recorder,
                sink=sink,
                ordering_assignment_id=_sha(root_record.get("assignment_id"), "assignment"),
            )
            policy = development.ExploratoryGoalManagerPolicy(
                readiness.paired.candidate_model,
                seed=seed,
            )
            observe = development._live_observer(
                runtime=runtime,
                actions=actions,
                meter=meter,
                root=root,
                ordering_assignment_id=_sha(root_record.get("assignment_id"), "assignment"),
            )
            result = development.run_repeatable_goal_manager_development_episode(
                observe=observe,
                policy=policy,
                trajectory=trajectory,
                budget_meter=meter,
                maximum_decisions=1,
            )
            if recorder.recording_failures:
                raise ResettableMultirootRunError("trajectory_durability")
            development.require_pyboy_import_origins(base.runtime)
        development._require_unchanged(protected)
        if development.rom_adjacent_artifacts(base.rom_path) != adjacent_before:
            raise ResettableMultirootRunError("protected_input_integrity")
        sink.record_event(
            development.SparseEvent(
                event_id=f"{episode_id}:terminal",
                episode_id=episode_id,
                step_index=recorder.next_step_index,
                kind="terminal",
                payload={
                    "status": "complete",
                    "development": cast(
                        Mapping[str, JSONValue],
                        result.public_dict(),
                    ),
                },
            )
        )
        sink.finalize()
        summary = writer.complete()
        return {
            "trial_index": _integer(trial.get("trial_index"), "trial index"),
            "partition": partition,
            "status": "complete",
            "manifest_sha256": summary.manifest_sha256,
            "model_predictions": 1,
            "controller_actions": sum(step.actions_executed for step in result.steps),
            "emulator_frames": sum(step.frames_executed for step in result.steps),
        }
    except BaseException as error:
        if writer is not None:
            development._retain_failure(
                writer,
                sink=sink,
                episode_id=episode_id,
                step_index=0 if recorder is None else recorder.next_step_index,
                failure_stage=_failure_stage(cast(Exception, error)),
            )
        raise


def _failure_row(
    trial: Mapping[str, object],
    *,
    artifact_state: str,
    error: Exception,
) -> dict[str, object]:
    return {
        "trial_index": _integer(trial.get("trial_index"), "trial index"),
        "partition": _partition(trial.get("partition")),
        "status": (
            "failed_terminal_retained"
            if artifact_state == "failed"
            else "consumed_without_durable_failure_terminal"
        ),
        "artifact_state": artifact_state,
        "failure_stage": _failure_stage(error),
    }


def _episode_metadata(
    readiness: _Readiness,
    qualified: _QualifiedCampaign,
    *,
    root: development._Root,
    root_record: Mapping[str, object],
    partition: str,
    claim: str,
    execution_identity_sha256: str,
) -> dict[str, object]:
    base = readiness.paired.development
    return {
        "policy": {
            "actor": "exploratory_goal_manager",
            "policy_id": "red-goal-manager-outcome-development-v1",
        },
        "split": {
            "partition": partition,
            "root_lineage_id": _text(root_record.get("root_lineage_id"), "root lineage"),
        },
        "goal_manager": {
            "assignment_id": claim,
            "binding_manifest_sha256": root.binding_manifest_sha256,
            "collection_id": _sha(qualified.plan.get("campaign_id"), "campaign"),
            "context_catalog_sha256": base.candidate.catalog.catalog_sha256,
            "context_id": base.candidate.catalog.entry(root.entry.slot_id).context_id,
            "envelope_sha256": root.capture.envelope_sha256,
            "execution_identity_sha256": execution_identity_sha256,
            "source_commit": base.source.git_commit,
            "state_sha256": root.capture.state_sha256,
        },
        "development": development.goal_manager_development_contract(maximum_decisions=1),
        "multiroot_curriculum": {
            "schema": "pokemon.red.resettable-goal-manager-episode-metadata.v1",
            "campaign_plan_sha256": qualified.plan_sha256,
        },
    }


def _load_partition(
    readiness: _Readiness,
    qualified: _QualifiedCampaign,
    *,
    partition: str,
) -> tuple[tuple[AdmittedGoalManagerDevelopmentEpisode, ...], dict[str, int]]:
    base = readiness.paired.development
    registry = open_fixed_account_claim_registry()
    _require_consumption_claims(readiness, qualified, registry)
    _require_trial_claims(readiness, qualified, registry)
    episodes: list[AdmittedGoalManagerDevelopmentEpisode] = []
    invalid: dict[str, int] = {}
    for trial in _trials(qualified.plan):
        if trial.get("partition") != partition:
            continue
        claim = _sha(trial.get("trial_claim_sha256"), "trial claim")
        expected_claim = {
            "execution_identity_sha256": _trial_execution_identity(
                readiness,
                qualified,
                trial,
            ),
            "runner_sha256": readiness.runner_sha256,
            "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
            "source_commit": base.source.git_commit,
            "trial_claim_sha256": claim,
        }
        if development._read_trial_claim(registry, claim) != expected_claim:
            raise ResettableMultirootRunError("trial_claim_authentication")
        episode_id = _text(trial.get("episode_id"), "episode")
        state = qualified.store.inspect_episode_state(episode_id)
        if state.status != "complete":
            invalid[state.status] = invalid.get(state.status, 0) + 1
            continue
        root_index = _integer(trial.get("root_index"), "root index")
        root = qualified.roots[root_index]
        root_record = _mapping(_root_records(qualified.plan)[root_index].get("root"), "root")
        episodes.append(
            development.load_repeatable_goal_manager_development_episode(
                qualified.store.open_episode(episode_id),
                expected_campaign_id=_sha(qualified.plan.get("campaign_id"), "campaign"),
                expected_trial_claim_sha256=claim,
                expected_episode_id=episode_id,
                expected_root_lineage_id=_text(
                    root_record.get("root_lineage_id"),
                    "root lineage",
                ),
                expected_seed=_integer(trial.get("seed"), "seed"),
                expected_execution_identity_sha256=_trial_execution_identity(
                    readiness,
                    qualified,
                    trial,
                ),
                expected_context_catalog_sha256=base.candidate.catalog.catalog_sha256,
                expected_context_id=base.candidate.catalog.entry(root.entry.slot_id).context_id,
                expected_binding_manifest_sha256=_sha(
                    root_record.get("binding_manifest_sha256"),
                    "binding manifest",
                ),
                expected_state_sha256=_sha(root_record.get("state_sha256"), "state"),
                expected_envelope_sha256=_sha(
                    root_record.get("envelope_sha256"),
                    "envelope",
                ),
                expected_first_question_sha256=_sha(
                    root_record.get("question_sha256"),
                    "question",
                ),
                expected_first_policy_context_sha256=_sha(
                    root_record.get("policy_context_sha256"),
                    "policy context",
                ),
                expected_first_available_menu_sha256=_sha(
                    root_record.get("available_menu_sha256"),
                    "available menu",
                ),
                expected_model=readiness.paired.candidate_model,
                expected_source_commit=base.source.git_commit or "",
                expected_partition=partition,
                expected_maximum_decisions=1,
            )
        )
    return tuple(episodes), dict(sorted(invalid.items()))


def _validate_plan(
    readiness: _Readiness,
    plan: Mapping[str, object],
    *,
    private_root_identity: str,
) -> None:
    base = readiness.paired.development
    if (
        plan.get("schema") != CAMPAIGN_SCHEMA
        or plan.get("source_commit") != base.source.git_commit
        or plan.get("source_bundle_sha256") != base.source_bundle_sha256
        or plan.get("runner_sha256") != readiness.runner_sha256
        or plan.get("runtime_sha256") != base.runtime.sha256
        or plan.get("numpy_runtime_sha256") != base.numpy_runtime_sha256
        or plan.get("skill_manifest_sha256") != base.skill_manifest_sha256
        or plan.get("context_plan_sha256") != base.context_plan_sha256
        or plan.get("private_root_identity_sha256") != private_root_identity
        or plan.get("prior_campaign_sha256") != list(readiness.paired.prior_campaign_sha256)
        or plan.get("base_model_canonical_sha256")
        != readiness.paired.candidate_model_canonical_sha256
        or plan.get("outcome_objective") != development.goal_manager_development_outcome_objective()
    ):
        raise ResettableMultirootRunError("campaign_authentication")
    campaign_id = _sha(plan.get("campaign_id"), "campaign")
    roots = _root_records(plan)
    trials = _trials(plan)
    if len(roots) != 6 or len(trials) != 12:
        raise ResettableMultirootRunError("campaign_layout")
    expected_specs = (
        *(("train", kind.value) for kind in TRAIN_ROOT_SPECS),
        *(("development", kind.value) for kind in DEVELOPMENT_ROOT_SPECS),
    )
    seen_entries: set[int] = set()
    seen_states: set[tuple[str, str]] = set()
    for index, (record, expected) in enumerate(zip(roots, expected_specs, strict=True)):
        if set(record) != {"partition", "root", "root_consumption_sha256"}:
            raise ResettableMultirootRunError("campaign_layout")
        frozen = _mapping(record.get("root"), "root")
        if (record.get("partition"), frozen.get("focus_kind")) != expected or _integer(
            frozen.get("entry_index"), "entry index"
        ) in seen_entries:
            raise ResettableMultirootRunError("campaign_layout")
        seen_entries.add(_integer(frozen.get("entry_index"), "entry index"))
        state_pair = (
            _sha(frozen.get("state_sha256"), "state"),
            _sha(frozen.get("envelope_sha256"), "envelope"),
        )
        if state_pair in seen_states:
            raise ResettableMultirootRunError("campaign_layout")
        seen_states.add(state_pair)
        if record.get("root_consumption_sha256") != root_consumption_sha256(
            state_sha256=state_pair[0],
            envelope_sha256=state_pair[1],
        ):
            raise ResettableMultirootRunError("campaign_layout")
        expected_indices = (index * 2, index * 2 + 1)
        if (
            tuple(
                _integer(trial.get("trial_index"), "trial index")
                for trial in trials
                if trial.get("root_index") == index
            )
            != expected_indices
        ):
            raise ResettableMultirootRunError("campaign_layout")
    stripped_trials: list[dict[str, object]] = []
    for expected_index, trial in enumerate(trials):
        root_index = expected_index // 2
        expected_partition = "train" if root_index < 4 else "development"
        if (
            set(trial)
            != {
                "episode_id",
                "maximum_decisions",
                "partition",
                "root_index",
                "seed",
                "trial_claim_sha256",
                "trial_index",
            }
            or trial.get("trial_index") != expected_index
            or trial.get("root_index") != root_index
            or trial.get("partition") != expected_partition
            or trial.get("maximum_decisions") != 1
            or trial.get("seed") != 30_000 + root_index * 100 + expected_index % 2
            or trial.get("episode_id") != f"red-multiroot-{campaign_id[:32]}-{expected_index:02d}"
            or trial.get("trial_claim_sha256")
            != canonical_sha256(
                {
                    "campaign_id": campaign_id,
                    "schema": "pokemon.red.resettable-goal-manager-trial-claim.v1",
                    "trial_index": expected_index,
                }
            )
        ):
            raise ResettableMultirootRunError("campaign_layout")
        stripped = dict(trial)
        stripped.pop("episode_id")
        stripped.pop("trial_claim_sha256")
        stripped_trials.append(stripped)
    identity = dict(plan)
    identity.pop("campaign_id", None)
    identity.pop("campaign_consumption_sha256", None)
    identity["trials"] = stripped_trials
    if canonical_sha256(identity) != campaign_id or plan.get(
        "campaign_consumption_sha256"
    ) != canonical_sha256(
        {
            "campaign_id": campaign_id,
            "schema": "pokemon.red.resettable-goal-manager-campaign-consumption.v1",
        }
    ):
        raise ResettableMultirootRunError("campaign_authentication")


def _require_consumption_claims(
    readiness: _Readiness,
    qualified: _QualifiedCampaign,
    registry: Path,
) -> None:
    base = readiness.paired.development
    identity = _campaign_execution_identity(readiness, qualified)
    claims = (
        _sha(qualified.plan.get("campaign_consumption_sha256"), "campaign consumption"),
        *(
            _sha(record.get("root_consumption_sha256"), "root consumption")
            for record in _root_records(qualified.plan)
        ),
    )
    for claim in claims:
        record = read_root_claim(registry, claim)
        if (
            record.get("execution_identity_sha256") != identity
            or record.get("source_commit") != base.source.git_commit
            or record.get("runner_sha256") != readiness.runner_sha256
        ):
            raise ResettableMultirootRunError("campaign_claim_authentication")


def _require_trial_claims(
    readiness: _Readiness,
    qualified: _QualifiedCampaign,
    registry: Path,
) -> None:
    base = readiness.paired.development
    for trial in _trials(qualified.plan):
        claim = _sha(trial.get("trial_claim_sha256"), "trial claim")
        expected = {
            "execution_identity_sha256": _trial_execution_identity(
                readiness,
                qualified,
                trial,
            ),
            "runner_sha256": readiness.runner_sha256,
            "schema": "pokemon.red.repeatable-goal-manager-trial-claim.v1",
            "source_commit": base.source.git_commit,
            "trial_claim_sha256": claim,
        }
        if development._read_trial_claim(registry, claim) != expected:
            raise ResettableMultirootRunError("trial_claim_authentication")


def _campaign_execution_identity(
    readiness: _Readiness,
    qualified: _QualifiedCampaign,
) -> str:
    base = readiness.paired.development
    return cast(
        str,
        canonical_sha256(
            {
                "campaign_plan_sha256": qualified.plan_sha256,
                "model_canonical_sha256": readiness.paired.candidate_model_canonical_sha256,
                "runner_sha256": readiness.runner_sha256,
                "runtime_sha256": base.runtime.sha256,
                "schema": "pokemon.red.resettable-goal-manager-execution.v1",
                "source_commit": base.source.git_commit,
            },
        ),
    )


def _campaign_terminal_identity(qualified: _QualifiedCampaign) -> str:
    return cast(
        str,
        canonical_sha256(
            {
                "campaign_plan_sha256": qualified.plan_sha256,
                "schema": "pokemon.red.resettable-goal-manager-campaign-terminal.v1",
            },
        ),
    )


def _require_campaign_terminal(
    readiness: _Readiness,
    qualified: _QualifiedCampaign,
    registry: Path,
) -> None:
    record = read_root_claim(registry, _campaign_terminal_identity(qualified))
    if (
        record.get("execution_identity_sha256")
        != _campaign_execution_identity(readiness, qualified)
        or record.get("source_commit") != readiness.paired.development.source.git_commit
        or record.get("runner_sha256") != readiness.runner_sha256
    ):
        raise ResettableMultirootRunError("campaign_terminal_authentication")


def _trial_execution_identity(
    readiness: _Readiness,
    qualified: _QualifiedCampaign,
    trial: Mapping[str, object],
) -> str:
    base = readiness.paired.development
    root_index = _integer(trial.get("root_index"), "root index")
    frozen = _mapping(_root_records(qualified.plan)[root_index].get("root"), "root")
    return cast(
        str,
        repeatable_goal_manager_trial_execution_identity(
            campaign_id=_sha(qualified.plan.get("campaign_id"), "campaign"),
            campaign_plan_sha256=qualified.plan_sha256,
            model_canonical_sha256=readiness.paired.candidate_model_canonical_sha256,
            numpy_runtime_sha256=base.numpy_runtime_sha256,
            root_lineage_id=_text(frozen.get("root_lineage_id"), "root lineage"),
            runtime_sha256=base.runtime.sha256,
            source_commit=base.source.git_commit or "",
            trial_index=_integer(trial.get("trial_index"), "trial index"),
            trial_claim_sha256=_sha(trial.get("trial_claim_sha256"), "trial claim"),
        ),
    )


def _root_records(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("roots")
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ResettableMultirootRunError("campaign_layout")
    return tuple(cast(Mapping[str, object], item) for item in value)


def _prior_root_identities(
    campaigns: tuple[Mapping[str, object], ...],
) -> tuple[set[str], set[tuple[str, str]]]:
    roots = tuple(root for plan in campaigns for root in development._roots(plan))
    return (
        {_text(root.get("root_lineage_id"), "prior lineage") for root in roots},
        {
            (
                _sha(root.get("state_sha256"), "prior state"),
                _sha(root.get("envelope_sha256"), "prior envelope"),
            )
            for root in roots
        },
    )


def _trials(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("trials")
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ResettableMultirootRunError("campaign_layout")
    return tuple(cast(Mapping[str, object], item) for item in value)


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ResettableMultirootRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ResettableMultirootRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise ResettableMultirootRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise ResettableMultirootRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _partition(value: object) -> str:
    if not isinstance(value, str) or value not in {"train", "development"}:
        raise ResettableMultirootRunError("partition_authentication")
    return value


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


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _failure_stage(error: Exception) -> str:
    if isinstance(error, ResettableMultirootRunError):
        value = str(error)
        if value and value.replace("_", "").isalnum():
            return value
    return "unexpected_failure"


if __name__ == "__main__":
    raise SystemExit(main())
