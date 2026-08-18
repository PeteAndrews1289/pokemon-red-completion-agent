#!/usr/bin/env python3
"""Qualify the successor executor for one frozen paired Red outcome screen."""

# ruff: noqa: E402 -- reviewed local runners must win import resolution

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
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

import run_paired_goal_manager_outcome_screen as freeze
import run_repeatable_goal_manager_development as development

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    write_root_claim,
)
from pokemon_red_completion.paired_goal_manager_screen import (
    PAIRED_SCREEN_ARM_ORDER,
    PAIRED_SCREEN_SCHEMA,
    adjudicate_paired_screen,
    paired_screen_arm_claim,
    paired_screen_arm_execution_identity,
    paired_screen_behavior_contract,
    paired_screen_endpoint_contract,
    paired_screen_execution_identity,
)
from pokemon_red_completion.provenance import canonical_sha256

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_STAGE = re.compile(r"[a-z0-9_]+\Z")
_MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
_DESIGN_SCHEMA = "pokemon.red.paired-goal-manager-outcome-screen-design.v1"


class PairedExecutionRunError(RuntimeError):
    """A path-free failure at one paired execution-qualification stage."""


@dataclass(frozen=True, slots=True)
class _Readiness:
    paired: freeze._Readiness
    runner_sha256: str
    freeze_runner_sha256: str


@dataclass(frozen=True, slots=True)
class _QualifiedPair:
    plan: Mapping[str, object]
    plan_sha256: str
    root: development._Root
    pair_execution_identity_sha256: str
    arm_execution_identity_sha256: tuple[str, str]
    store: Any
    screen_plan_path: Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("preflight", "execute", "admit"),
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
    parser.add_argument("--expected-freeze-runner-sha256", required=True)
    parser.add_argument("--expected-development-runner-sha256", required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-numpy-runtime-sha256", required=True)
    parser.add_argument("--expected-skill-manifest-sha256", required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--screen-plan", type=Path, required=True)
    parser.add_argument("--expected-screen-plan-sha256", required=True)
    parser.add_argument("--design-receipt", type=Path, required=True)
    parser.add_argument("--expected-design-receipt-sha256", required=True)
    parser.add_argument("--expected-pair-execution-identity-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        readiness = _readiness(args)
        qualified = _qualify(
            readiness,
            screen_plan_path=args.screen_plan,
            expected_screen_plan_sha256=args.expected_screen_plan_sha256,
            design_receipt_path=args.design_receipt,
            expected_design_receipt_sha256=args.expected_design_receipt_sha256,
            private_root_path=args.private_root,
            require_unclaimed=args.mode != "admit",
        )
        if args.mode == "preflight":
            result = _public_preflight(readiness, qualified)
        else:
            expected_pair = _sha(
                args.expected_pair_execution_identity_sha256,
                "pair execution",
            )
            if expected_pair != qualified.pair_execution_identity_sha256:
                raise PairedExecutionRunError("pair_execution_authorization")
            if args.mode == "execute":
                result = _execute_pair(readiness, qualified)
            else:
                result = _admit_pair(readiness, qualified)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as error:
        preflight_failure = getattr(locals().get("args", None), "mode", None) == "preflight"
        effects: dict[str, object]
        if preflight_failure:
            effects = {
                "model_predictions": 0,
                "controller_actions": 0,
                "teacher_queries": 0,
                "model_fits": 0,
                "authority_promotions": 0,
            }
        else:
            effects = {"execution_effects_status": "not_attested_on_failure"}
        print(
            json.dumps(
                {
                    "schema": "pokemon.red.paired-goal-manager-execution-failure.v1",
                    "status": (
                        "failed_closed_before_prediction_or_action"
                        if preflight_failure
                        else "failed_closed_execution_state_retained"
                    ),
                    "failure_stage": _sanitized_failure_stage(error),
                    "protected_access_status": "not_attested_on_failure",
                    "private_path_fields": 0,
                    **effects,
                },
                sort_keys=True,
            )
        )
        return 1


def _readiness(args: argparse.Namespace) -> _Readiness:
    expected_freeze_path = (
        SCRIPTS_ROOT / "run_paired_goal_manager_outcome_screen.py"
    ).resolve()
    expected_development_path = (
        SCRIPTS_ROOT / "run_repeatable_goal_manager_development.py"
    ).resolve()
    if (
        not isinstance(getattr(freeze, "__file__", None), str)
        or Path(freeze.__file__).resolve(strict=True) != expected_freeze_path
        or not isinstance(getattr(development, "__file__", None), str)
        or Path(development.__file__).resolve(strict=True) != expected_development_path
    ):
        raise PairedExecutionRunError("import_origin_attestation")
    freeze_runner_sha256 = _file_sha256(expected_freeze_path)
    if freeze_runner_sha256 != _sha(
        args.expected_freeze_runner_sha256,
        "freeze runner",
    ):
        raise PairedExecutionRunError("freeze_runner_attestation")
    paired_args = argparse.Namespace(
        context_plan=args.context_plan,
        context_catalog=args.context_catalog,
        base_model=args.base_model,
        base_fit_summary=args.base_fit_summary,
        candidate_model=args.candidate_model,
        candidate_fit_summary=args.candidate_fit_summary,
        fit_result_receipt=args.fit_result_receipt,
        prior_campaign=args.prior_campaign,
        expected_prior_campaign_sha256=args.expected_prior_campaign_sha256,
        expected_fit_result_receipt_sha256=(
            args.expected_fit_result_receipt_sha256
        ),
        expected_source_commit=args.expected_source_commit,
        expected_source_bundle_sha256=args.expected_source_bundle_sha256,
        expected_runner_sha256=args.expected_freeze_runner_sha256,
        expected_development_runner_sha256=(
            args.expected_development_runner_sha256
        ),
        expected_runtime_sha256=args.expected_runtime_sha256,
        expected_numpy_runtime_sha256=args.expected_numpy_runtime_sha256,
        expected_skill_manifest_sha256=args.expected_skill_manifest_sha256,
        expected_context_plan_sha256=args.expected_context_plan_sha256,
        rom=args.rom,
    )
    paired = freeze._readiness(paired_args)
    runner_path = Path(__file__).resolve()
    if runner_path.parent != SCRIPTS_ROOT.resolve():
        raise PairedExecutionRunError("executable_attestation")
    runner_sha256 = _file_sha256(runner_path)
    if runner_sha256 != _sha(args.expected_runner_sha256, "execution runner"):
        raise PairedExecutionRunError("executable_attestation")
    return _Readiness(
        paired=paired,
        runner_sha256=runner_sha256,
        freeze_runner_sha256=freeze_runner_sha256,
    )


def _qualify(
    readiness: _Readiness,
    *,
    screen_plan_path: Path,
    expected_screen_plan_sha256: str,
    design_receipt_path: Path,
    expected_design_receipt_sha256: str,
    private_root_path: Path,
    require_unclaimed: bool = True,
) -> _QualifiedPair:
    base = readiness.paired.development
    store, private_root_identity_sha256 = development._open_bound_private_root(
        private_root_path,
        rom_path=base.rom_path,
    )
    plan_path = development._external_regular(screen_plan_path, rom_path=base.rom_path)
    plan_payload = plan_path.read_bytes()
    plan_sha256 = hashlib.sha256(plan_payload).hexdigest()
    if plan_sha256 != _sha(expected_screen_plan_sha256, "screen plan"):
        raise PairedExecutionRunError("screen_plan_attestation")
    plan = development._canonical_document(plan_payload, subject="screen plan")

    receipt_path = freeze._tracked_regular(design_receipt_path)
    receipt_payload = receipt_path.read_bytes()
    if hashlib.sha256(receipt_payload).hexdigest() != _sha(
        expected_design_receipt_sha256,
        "design receipt",
    ):
        raise PairedExecutionRunError("design_receipt_attestation")
    receipt = freeze._document(receipt_payload, subject="design receipt")
    _validate_frozen_plan(
        readiness,
        plan,
        plan_sha256=plan_sha256,
        receipt=receipt,
        private_root_identity_sha256=private_root_identity_sha256,
    )

    root_record = _mapping(plan.get("root"), "screen root")
    entry_index = _integer(root_record.get("entry_index"), "entry index")
    if entry_index >= len(base.entries):
        raise PairedExecutionRunError("screen_root_attestation")
    entry = base.entries[entry_index]
    frozen_assignment_id = _sha(root_record.get("assignment_id"), "assignment")
    inspected = development._inspect_root(
        base,
        entry,
        entry_index=entry_index,
        ordering_assignment_id=frozen_assignment_id,
    )
    if inspected is None:
        raise PairedExecutionRunError("screen_root_drift")
    _validate_stable_root(inspected, root_record)

    arms = _arms(plan)
    arm_claims = tuple(
        _sha(arm.get("claim_sha256"), "arm claim") for arm in arms
    )
    pair_execution_identity_sha256 = paired_screen_execution_identity(
        screen_plan_sha256=plan_sha256,
        screen_id=_sha(plan.get("screen_id"), "screen"),
        execution_source_commit=base.source.git_commit or "",
        execution_runner_sha256=readiness.runner_sha256,
        runtime_sha256=base.runtime.sha256,
        root_consumption_sha256=_sha(
            plan.get("root_consumption_sha256"),
            "root consumption",
        ),
        arm_claim_sha256=cast(tuple[str, str], arm_claims),
    )
    arm_execution = tuple(
        paired_screen_arm_execution_identity(
            pair_execution_identity_sha256=pair_execution_identity_sha256,
            arm=_text(arm.get("arm"), "arm"),
            model_canonical_sha256=_sha(
                arm.get("model_canonical_sha256"),
                "arm model",
            ),
            arm_claim_sha256=_sha(arm.get("claim_sha256"), "arm claim"),
            episode_id=_text(arm.get("episode_id"), "episode identity"),
        )
        for arm in arms
    )

    if require_unclaimed:
        registry = open_fixed_account_claim_registry()
        with fixed_account_claim_registry_lease(registry, exclusive=False):
            if not root_claim_is_available(
                registry,
                _sha(plan.get("root_consumption_sha256"), "root consumption"),
            ):
                raise PairedExecutionRunError("paired_root_already_consumed")
            for arm in arms:
                episode_id = _text(arm.get("episode_id"), "episode identity")
                claim = _sha(arm.get("claim_sha256"), "arm claim")
                if (
                    store.inspect_episode_state(episode_id).status != "absent"
                    or not development._trial_claim_is_available(registry, claim)
                ):
                    raise PairedExecutionRunError("paired_arm_already_consumed")
    return _QualifiedPair(
        plan=plan,
        plan_sha256=plan_sha256,
        root=inspected,
        pair_execution_identity_sha256=pair_execution_identity_sha256,
        arm_execution_identity_sha256=cast(tuple[str, str], arm_execution),
        store=store,
        screen_plan_path=plan_path,
    )


def _claim_pair(readiness: _Readiness, qualified: _QualifiedPair) -> None:
    registry = open_fixed_account_claim_registry()
    root_consumption = _sha(
        qualified.plan.get("root_consumption_sha256"),
        "root consumption",
    )
    arms = _arms(qualified.plan)
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        if not root_claim_is_available(registry, root_consumption):
            raise PairedExecutionRunError("paired_root_already_consumed")
        for arm in arms:
            if (
                qualified.store.inspect_episode_state(
                    _text(arm.get("episode_id"), "episode identity")
                ).status
                != "absent"
                or not development._trial_claim_is_available(
                    registry,
                    _sha(arm.get("claim_sha256"), "arm claim"),
                )
            ):
                raise PairedExecutionRunError("paired_arm_already_consumed")
        write_root_claim(
            registry,
            root_consumption_sha256=root_consumption,
            execution_identity_sha256=qualified.pair_execution_identity_sha256,
            source_commit=readiness.paired.development.source.git_commit or "",
            runner_sha256=readiness.runner_sha256,
        )
        for index, arm in enumerate(arms):
            development._write_trial_claim(
                registry,
                trial_claim_sha256=_sha(arm.get("claim_sha256"), "arm claim"),
                execution_identity_sha256=(
                    qualified.arm_execution_identity_sha256[index]
                ),
                source_commit=readiness.paired.development.source.git_commit or "",
                runner_sha256=readiness.runner_sha256,
            )


def _execute_pair(
    readiness: _Readiness,
    qualified: _QualifiedPair,
) -> dict[str, object]:
    _claim_pair(readiness, qualified)
    arm_results: list[dict[str, object]] = []
    models = (
        readiness.paired.development.candidate.model,
        readiness.paired.candidate_model,
    )
    for index, (arm, model) in enumerate(zip(_arms(qualified.plan), models, strict=True)):
        arm_results.append(
            _execute_arm(
                readiness,
                qualified,
                arm=arm,
                model=model,
                arm_execution_identity_sha256=(
                    qualified.arm_execution_identity_sha256[index]
                ),
            )
        )
    return {
        "schema": "pokemon.red.paired-goal-manager-execution-summary.v1",
        "status": "paired_execution_complete_pending_strict_admission",
        "screen_plan_sha256": qualified.plan_sha256,
        "pair_execution_identity_sha256": (
            qualified.pair_execution_identity_sha256
        ),
        "arms": arm_results,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "private_path_fields": 0,
    }


def _execute_arm(
    readiness: _Readiness,
    qualified: _QualifiedPair,
    *,
    arm: Mapping[str, object],
    model: Any,
    arm_execution_identity_sha256: str,
) -> dict[str, object]:
    base = readiness.paired.development
    root = qualified.root
    frozen_root = _mapping(qualified.plan.get("root"), "screen root")
    screen_id = _sha(qualified.plan.get("screen_id"), "screen")
    claim = _sha(arm.get("claim_sha256"), "arm claim")
    episode_id = _text(arm.get("episode_id"), "episode identity")
    seed = _integer(
        _mapping(qualified.plan.get("behavior"), "behavior").get("seed"),
        "behavior seed",
    )
    protected = development._protected_digests(
        (
            base.context_plan_path,
            base.context_catalog_path,
            base.model_path,
            base.fit_summary_path,
            readiness.paired.candidate_model_path,
            qualified.screen_plan_path,
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
            metadata=_paired_episode_metadata(
                readiness,
                qualified,
                arm_claim_sha256=claim,
                arm_execution_identity_sha256=arm_execution_identity_sha256,
            )
        )
        with development.PyBoyAdapter(base.rom_path, watch=False, speed=None) as emulator:
            development.require_pyboy_import_origins(base.runtime)
            emulator.load_state_bytes(root.capture.state_bytes)
            development.require_pyboy_import_origins(base.runtime)
            frames = development.WindowedFrameBudgetController(
                emulator,
                maximum_frames_per_window=(
                    development.FRESH_COMPOSITION_FRAMES_PER_DECISION
                ),
                maximum_total_frames=development.FRESH_COMPOSITION_MAX_FRAMES,
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
            snapshot_provider = development.PokemonRedObservationEncoder.from_state_reader(
                reader
            )
            recorder = development.RecordingExecutor(
                delegate=frame_safe,
                snapshot_provider=snapshot_provider,
                sink=sink,
                episode_id=episode_id,
            )
            hard_actions = development.HardCompositionActionLimiter(recorder)
            actions = development.CountingExecutor(hard_actions)
            meter = development.CompositionIndependentBudgetMeter(hard_actions, frames)
            trajectory = development.GoalManagerTrajectoryObserver(
                episode_id=episode_id,
                root_lineage_id=_text(
                    frozen_root.get("root_lineage_id"),
                    "root lineage",
                ),
                partition="development",
                environment_id="pokemon.mainline:red:gb:us:rev0",
                actor="exploratory_goal_manager",
                policy_id="red-goal-manager-outcome-development-v1",
                collection_id=screen_id,
                assignment_id=claim,
                source_commit=base.source.git_commit or "",
                snapshot_provider=snapshot_provider,
                recorder=recorder,
                sink=sink,
                ordering_assignment_id=_sha(
                    frozen_root.get("assignment_id"),
                    "assignment",
                ),
            )
            policy = development.ExploratoryGoalManagerPolicy(model, seed=seed)
            observe = development._live_observer(
                runtime=runtime,
                actions=actions,
                meter=meter,
                root=root,
                ordering_assignment_id=_sha(
                    frozen_root.get("assignment_id"),
                    "assignment",
                ),
            )
            result = development.run_repeatable_goal_manager_development_episode(
                observe=observe,
                policy=policy,
                trajectory=trajectory,
                budget_meter=meter,
                maximum_decisions=3,
            )
            if recorder.recording_failures:
                raise PairedExecutionRunError("trajectory_durability")
            development.require_pyboy_import_origins(base.runtime)
        development.require_pyboy_import_origins(base.runtime)
        development._require_unchanged(protected)
        if development.rom_adjacent_artifacts(base.rom_path) != adjacent_before:
            raise PairedExecutionRunError("protected_input_integrity")
        sink.record_event(
            development.SparseEvent(
                event_id=f"{episode_id}:terminal",
                episode_id=episode_id,
                step_index=recorder.next_step_index,
                kind="terminal",
                payload={
                    "status": "complete",
                    "development": cast(
                        Mapping[str, development.JSONValue],
                        result.public_dict(),
                    ),
                },
            )
        )
        sink.finalize()
        summary = writer.complete()
        return {
            "arm": _text(arm.get("arm"), "arm"),
            "status": "durable_terminal",
            "manifest_sha256": summary.manifest_sha256,
            "total_records": summary.total_records,
            "model_predictions": result.verified_outcomes,
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
                failure_stage=_sanitized_failure_stage(cast(Exception, error)),
            )
        raise


def _paired_episode_metadata(
    readiness: _Readiness,
    qualified: _QualifiedPair,
    *,
    arm_claim_sha256: str,
    arm_execution_identity_sha256: str,
) -> dict[str, object]:
    base = readiness.paired.development
    root = qualified.root
    frozen_root = _mapping(qualified.plan.get("root"), "screen root")
    return {
        "policy": {
            "actor": "exploratory_goal_manager",
            "policy_id": "red-goal-manager-outcome-development-v1",
        },
        "split": {
            "partition": "development",
            "root_lineage_id": _text(
                frozen_root.get("root_lineage_id"),
                "root lineage",
            ),
        },
        "goal_manager": {
            "assignment_id": arm_claim_sha256,
            "binding_manifest_sha256": root.binding_manifest_sha256,
            "collection_id": _sha(qualified.plan.get("screen_id"), "screen"),
            "context_catalog_sha256": base.candidate.catalog.catalog_sha256,
            "context_id": base.candidate.catalog.entry(root.entry.slot_id).context_id,
            "envelope_sha256": root.capture.envelope_sha256,
            "execution_identity_sha256": arm_execution_identity_sha256,
            "source_commit": base.source.git_commit,
            "state_sha256": root.capture.state_sha256,
        },
        "development": development.goal_manager_development_contract(),
        "paired_screen": {
            "schema": "pokemon.red.paired-goal-manager-arm-metadata.v1",
            "screen_plan_sha256": qualified.plan_sha256,
            "pair_execution_identity_sha256": (
                qualified.pair_execution_identity_sha256
            ),
        },
    }


def _admit_pair(
    readiness: _Readiness,
    qualified: _QualifiedPair,
) -> dict[str, object]:
    base = readiness.paired.development
    registry = open_fixed_account_claim_registry()
    root_consumption = _sha(
        qualified.plan.get("root_consumption_sha256"),
        "root consumption",
    )
    arms = _arms(qualified.plan)
    endpoints: list[bool | None] = []
    secondary: list[dict[str, object]] = []
    models = (base.candidate.model, readiness.paired.candidate_model)
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        root_claim = read_root_claim(registry, root_consumption)
        if (
            root_claim.get("execution_identity_sha256")
            != qualified.pair_execution_identity_sha256
            or root_claim.get("source_commit") != (base.source.git_commit or "")
            or root_claim.get("runner_sha256") != readiness.runner_sha256
        ):
            raise PairedExecutionRunError("paired_root_claim_authentication")
        for index, (arm, model) in enumerate(zip(arms, models, strict=True)):
            claim = _sha(arm.get("claim_sha256"), "arm claim")
            marker = development._read_trial_claim(registry, claim)
            if (
                set(marker)
                != {
                    "execution_identity_sha256",
                    "runner_sha256",
                    "schema",
                    "source_commit",
                    "trial_claim_sha256",
                }
                or marker.get("schema")
                != "pokemon.red.repeatable-goal-manager-trial-claim.v1"
                or marker.get("trial_claim_sha256") != claim
                or marker.get("execution_identity_sha256")
                != qualified.arm_execution_identity_sha256[index]
                or marker.get("source_commit") != (base.source.git_commit or "")
                or marker.get("runner_sha256") != readiness.runner_sha256
            ):
                raise PairedExecutionRunError("paired_arm_claim_authentication")
            state = qualified.store.inspect_episode_state(
                _text(arm.get("episode_id"), "episode identity")
            )
            if state.status != "complete":
                endpoints.append(None)
                secondary.append(
                    {
                        "arm": _text(arm.get("arm"), "arm"),
                        "artifact_status": state.status,
                        "admitted": False,
                    }
                )
                continue
            admitted = development.load_repeatable_goal_manager_development_episode(
                qualified.store.open_episode(
                    _text(arm.get("episode_id"), "episode identity")
                ),
                expected_campaign_id=_sha(qualified.plan.get("screen_id"), "screen"),
                expected_trial_claim_sha256=claim,
                expected_episode_id=_text(arm.get("episode_id"), "episode identity"),
                expected_root_lineage_id=_text(
                    _mapping(qualified.plan.get("root"), "screen root").get(
                        "root_lineage_id"
                    ),
                    "root lineage",
                ),
                expected_seed=_integer(
                    _mapping(qualified.plan.get("behavior"), "behavior").get("seed"),
                    "behavior seed",
                ),
                expected_execution_identity_sha256=(
                    qualified.arm_execution_identity_sha256[index]
                ),
                expected_context_catalog_sha256=(
                    base.candidate.catalog.catalog_sha256
                ),
                expected_context_id=base.candidate.catalog.entry(
                    qualified.root.entry.slot_id
                ).context_id,
                expected_binding_manifest_sha256=(
                    qualified.root.binding_manifest_sha256
                ),
                expected_state_sha256=qualified.root.capture.state_sha256,
                expected_envelope_sha256=qualified.root.capture.envelope_sha256,
                expected_first_question_sha256=qualified.root.question_sha256,
                expected_first_policy_context_sha256=(
                    qualified.root.policy_context_sha256
                ),
                expected_first_available_menu_sha256=(
                    qualified.root.available_menu_sha256
                ),
                expected_model=model,
                expected_source_commit=base.source.git_commit or "",
            )
            endpoint = admitted.successful_retained_acquisitions > 0
            endpoints.append(endpoint)
            secondary.append(
                {
                    "arm": _text(arm.get("arm"), "arm"),
                    "artifact_status": state.status,
                    "admitted": True,
                    "verified_outcomes": admitted.verified_outcomes,
                    "composition": admitted.composition,
                    "successful_retained_acquisitions": (
                        admitted.successful_retained_acquisitions
                    ),
                }
            )
    adjudication = adjudicate_paired_screen(
        base_safe_retained_acquisition=endpoints[0],
        candidate_safe_retained_acquisition=endpoints[1],
    )
    return {
        "schema": "pokemon.red.paired-goal-manager-admission.v1",
        "status": "paired_screen_admitted",
        "screen_plan_sha256": qualified.plan_sha256,
        "pair_execution_identity_sha256": (
            qualified.pair_execution_identity_sha256
        ),
        "adjudication": adjudication.public_dict(),
        "arms": secondary,
        "development_attempts_added": 2,
        "composition_episodes_added": sum(
            item.get("admitted") is True for item in secondary
        ),
        "model_fits_added": 0,
        "unseen_comparisons_added": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "private_path_fields": 0,
    }


def _validate_frozen_plan(
    readiness: _Readiness,
    plan: Mapping[str, object],
    *,
    plan_sha256: str,
    receipt: Mapping[str, object],
    private_root_identity_sha256: str,
) -> None:
    expected_keys = {
        "arms",
        "base",
        "behavior",
        "candidate",
        "context_plan_sha256",
        "development_runner_sha256",
        "endpoint",
        "numpy_runtime_sha256",
        "prior_campaign_sha256",
        "private_root_identity_sha256",
        "root",
        "root_consumption_sha256",
        "runner_sha256",
        "schema",
        "screen_id",
        "selection",
        "skill_manifest_sha256",
        "source_bundle_sha256",
        "source_commit",
        "runtime_sha256",
    }
    if set(plan) != expected_keys or plan.get("schema") != PAIRED_SCREEN_SCHEMA:
        raise PairedExecutionRunError("screen_plan_contract")
    identity = dict(plan)
    screen_id = _sha(identity.pop("screen_id", None), "screen")
    raw_arms = identity.pop("arms", None)
    if screen_id != canonical_sha256(identity):
        raise PairedExecutionRunError("screen_plan_identity")
    bindings = _mapping(receipt.get("bindings"), "design bindings")
    source = _mapping(receipt.get("source_verification"), "design source")
    base_identity = _mapping(plan.get("base"), "base identity")
    candidate_identity = _mapping(plan.get("candidate"), "candidate identity")
    base = readiness.paired.development
    if (
        receipt.get("schema") != _DESIGN_SCHEMA
        or receipt.get("status")
        != "design_frozen_action_free_execution_not_implemented"
        or source.get("ci_conclusion") != "success"
        or source.get("worktree_dirty") is not False
        or source.get("git_commit") != plan.get("source_commit")
        or bindings.get("screen_plan_sha256") != plan_sha256
        or bindings.get("screen_identity_sha256") != screen_id
        or bindings.get("runner_sha256") != plan.get("runner_sha256")
        or bindings.get("source_bundle_sha256") != plan.get("source_bundle_sha256")
        or bindings.get("runtime_sha256") != plan.get("runtime_sha256")
        or bindings.get("numpy_runtime_sha256") != plan.get("numpy_runtime_sha256")
        or bindings.get("skill_manifest_sha256") != plan.get("skill_manifest_sha256")
        or bindings.get("context_plan_sha256") != plan.get("context_plan_sha256")
        or bindings.get("base_model_canonical_sha256")
        != base_identity.get("model_canonical_sha256")
        or bindings.get("candidate_model_canonical_sha256")
        != candidate_identity.get("model_canonical_sha256")
        or plan.get("private_root_identity_sha256") != private_root_identity_sha256
        or plan.get("context_plan_sha256") != base.context_plan_sha256
        or base_identity.get("model_canonical_sha256")
        != base.candidate.plan.model_canonical_sha256
        or candidate_identity.get("model_canonical_sha256")
        != readiness.paired.candidate_model_canonical_sha256
        or candidate_identity.get("model_file_sha256")
        != readiness.paired.candidate_model_file_sha256
        or candidate_identity.get("fit_summary_sha256")
        != readiness.paired.fit_summary_sha256
        or candidate_identity.get("fit_result_receipt_sha256")
        != readiness.paired.fit_result_receipt_sha256
        or plan.get("prior_campaign_sha256")
        != list(readiness.paired.prior_campaign_sha256)
        or plan.get("selection") != freeze._selection_contract()
        or plan.get("behavior") != paired_screen_behavior_contract()
        or plan.get("endpoint") != paired_screen_endpoint_contract()
    ):
        raise PairedExecutionRunError("screen_plan_attestation")
    root = _mapping(plan.get("root"), "screen root")
    if (
        bindings.get("selected_root_commitment_sha256") != canonical_sha256(root)
        or plan.get("root_consumption_sha256")
        != development.root_consumption_sha256(
            state_sha256=_sha(root.get("state_sha256"), "root state"),
            envelope_sha256=_sha(root.get("envelope_sha256"), "root envelope"),
        )
    ):
        raise PairedExecutionRunError("screen_root_attestation")
    arms = _arms({**plan, "arms": raw_arms})
    if tuple(_text(arm.get("arm"), "arm") for arm in arms) != PAIRED_SCREEN_ARM_ORDER:
        raise PairedExecutionRunError("screen_arm_contract")
    expected_arm_models = (
        _sha(base_identity.get("model_canonical_sha256"), "base model"),
        _sha(candidate_identity.get("model_canonical_sha256"), "candidate model"),
    )
    for arm_index, arm in enumerate(arms):
        arm_name = _text(arm.get("arm"), "arm")
        model_sha = _sha(arm.get("model_canonical_sha256"), "arm model")
        claim = paired_screen_arm_claim(
            screen_id=screen_id,
            arm=arm_name,
            model_canonical_sha256=model_sha,
        )
        if (
            set(arm)
            != {"arm", "claim_sha256", "episode_id", "model_canonical_sha256"}
            or arm.get("claim_sha256") != claim
            or arm.get("episode_id") != freeze._arm_episode_id(claim)
            or model_sha != expected_arm_models[arm_index]
        ):
            raise PairedExecutionRunError("screen_arm_contract")


def _validate_stable_root(
    inspected: development._Root,
    frozen: Mapping[str, object],
) -> None:
    actual = development._private_root_record(inspected)
    source_bound = {"assignment_id", "root_lineage_id"}
    if (
        any(actual.get(key) != value for key, value in frozen.items() if key not in source_bound)
        or frozen.get("focus_kind") != GoalKind.ACQUIRE_SPECIES.value
        or len(inspected.available_goal_kinds) < 2
        or GoalKind.ACQUIRE_SPECIES.value not in inspected.available_goal_kinds
        or GoalKind.EVOLVE_SPECIES.value in inspected.available_goal_kinds
    ):
        raise PairedExecutionRunError("screen_root_drift")


def _public_preflight(
    readiness: _Readiness,
    qualified: _QualifiedPair,
) -> dict[str, object]:
    return {
        "schema": "pokemon.red.paired-goal-manager-execution-preflight.v1",
        "status": "paired_execution_ready_without_prediction_or_action",
        "source_commit": readiness.paired.development.source.git_commit,
        "runner_sha256": readiness.runner_sha256,
        "screen_plan_sha256": qualified.plan_sha256,
        "screen_identity_sha256": _sha(qualified.plan.get("screen_id"), "screen"),
        "pair_execution_identity_sha256": (
            qualified.pair_execution_identity_sha256
        ),
        "arm_execution_identity_sha256": list(
            qualified.arm_execution_identity_sha256
        ),
        "arm_count": 2,
        "maximum_decisions_per_arm": 3,
        "primary_endpoint": "safe_retained_acquisition",
        "pair_identity_available": True,
        "arm_identities_available": 2,
        "model_predictions": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "game_executions": 0,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "model_fits": 0,
        "unseen_comparisons": 0,
        "authority_promotions": 0,
        "transfer_results": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "tracked_private_paths": 0,
        "tracked_private_identities": 0,
    }


def _arms(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("arms")
    if not isinstance(value, list) or len(value) != 2 or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise PairedExecutionRunError("screen_arm_contract")
    return tuple(cast(Mapping[str, object], item) for item in value)


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PairedExecutionRunError(f"{subject.replace(' ', '_')}_contract")
    return cast(Mapping[str, object], value)


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value or not value.isascii() or "\n" in value:
        raise PairedExecutionRunError(f"{subject.replace(' ', '_')}_contract")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise PairedExecutionRunError(f"{subject.replace(' ', '_')}_contract")
    return value


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PairedExecutionRunError(f"{subject.replace(' ', '_')}_attestation")
    return value


def _file_sha256(path: Path) -> str:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        raise PairedExecutionRunError("executable_attestation") from None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise PairedExecutionRunError("executable_attestation")
    return hashlib.sha256(payload).hexdigest()


def _sanitized_failure_stage(error: Exception) -> str:
    if isinstance(
        error,
        (
            PairedExecutionRunError,
            freeze.PairedScreenRunError,
            development.RepeatableGoalManagerRunError,
        ),
    ):
        candidate = str(error)
    else:
        return "paired_execution_internal"
    if not isinstance(candidate, str) or _SAFE_STAGE.fullmatch(candidate) is None:
        return "paired_execution_internal"
    return candidate


if __name__ == "__main__":
    raise SystemExit(main())
