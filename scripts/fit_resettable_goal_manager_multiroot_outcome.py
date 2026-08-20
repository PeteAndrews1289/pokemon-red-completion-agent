#!/usr/bin/env python3
"""Fit once on multiroot train resets, then compare once on untouched roots."""

# ruff: noqa: E402 -- reviewed local runners must win import resolution

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import run_resettable_goal_manager_multiroot_campaign as campaign

from pokemon_red_completion.goal_manager import GoalKind, GoalManagerExample
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    write_root_claim,
)
from pokemon_red_completion.goal_manager_dataset import (
    load_assigned_goal_manager_episode,
)
from pokemon_red_completion.goal_manager_development import (
    AdmittedGoalManagerDevelopmentEpisode,
    load_repeatable_goal_manager_development_episode,
)
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
)
from pokemon_red_completion.goal_manager_outcome_learning import (
    GoalManagerOutcomeLearningError,
)
from pokemon_red_completion.private_artifacts import (
    PrivateEpisodeReader,
    _rename_no_replace,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.resettable_goal_manager_multiroot_learning import (
    MULTIROOT_DEVELOPMENT_EPISODES,
    MULTIROOT_TRAIN_EPISODES,
    ResettableGoalManagerComparison,
    ResettableGoalManagerLearningError,
    admit_resettable_goal_manager_train_set,
    compare_resettable_goal_manager_development,
    fit_resettable_goal_manager_train_set,
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GUARD_KINDS = {
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.EVOLVE_SPECIES,
    GoalKind.ADVANCE_STORY,
}
_MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
_FIT_TERMINAL_KIND = "resettable_goal_manager_fit_terminal"
_COMPARISON_TERMINAL_KIND = "resettable_goal_manager_comparison_terminal"
_TERMINAL_STATES = frozenset({"absent", "complete", "failed", "invalid", "interrupted", "partial"})


class MultirootFitRunError(RuntimeError):
    """A path-free failure at one fit/comparison stage."""


@dataclass(frozen=True, slots=True)
class _PreparedTrial:
    trial: Mapping[str, object]
    status: str
    manifest_sha256: str | None
    reason_code: str | None
    reader: PrivateEpisodeReader | None


@dataclass(frozen=True, slots=True)
class _PreparedInputs:
    partition: str
    trials: tuple[_PreparedTrial, ...]
    trial_manifest_roster_sha256: str
    guard_examples: tuple[GoalManagerExample, ...]
    kl_examples: tuple[GoalManagerExample, ...]
    guard_winner_manifest_roster_sha256: str
    guard_menu_manifest_roster_sha256: str
    runner_sha256: str
    learner_sha256: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("preflight-fit", "fit", "preflight-compare", "compare"),
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
    parser.add_argument("--expected-campaign-runner-sha256", required=True)
    parser.add_argument("--expected-paired-runner-sha256", required=True)
    parser.add_argument("--expected-development-runner-sha256", required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-numpy-runtime-sha256", required=True)
    parser.add_argument("--expected-skill-manifest-sha256", required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--campaign-plan", type=Path, required=True)
    parser.add_argument("--expected-campaign-sha256", required=True)
    parser.add_argument("--candidate-bundle", type=Path, required=True)
    parser.add_argument("--expected-candidate-bundle-manifest-sha256")
    parser.add_argument("--comparison-output", type=Path, required=True)
    parser.add_argument("--expected-operation-identity-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        ready, qualified = _readiness(args)
        if args.mode in {"preflight-fit", "fit"}:
            prepared = _prepare_inputs(ready, qualified, partition="train")
            identity = _fit_identity(ready, qualified, prepared)
            _require_operation_available(identity)
            _require_terminal_absent(qualified, operation="fit", identity=identity)
            candidate_destination = _require_new_bundle(
                args.candidate_bundle,
                args.private_root,
            )
            if args.mode == "preflight-fit":
                result = _preflight_result(
                    ready,
                    qualified,
                    prepared,
                    identity,
                    operation="fit",
                )
            else:
                _require_authorized(args, identity)
                result = _fit(
                    ready,
                    qualified,
                    prepared,
                    candidate_destination,
                    identity,
                )
        else:
            fit_prepared = _prepare_inputs(ready, qualified, partition="train")
            fit_identity = _fit_identity(ready, qualified, fit_prepared)
            expected_bundle_manifest_sha256 = _sha(
                args.expected_candidate_bundle_manifest_sha256,
                "candidate bundle manifest",
            )
            candidate_model, bundle_manifest_sha256 = _load_candidate_bundle(
                args.candidate_bundle,
                args.private_root,
                ready=ready,
                qualified=qualified,
                prepared=fit_prepared,
                expected_fit_identity=fit_identity,
                expected_bundle_manifest_sha256=expected_bundle_manifest_sha256,
                expected_source_commit=ready.paired.development.source.git_commit or "",
            )
            prepared = _prepare_inputs(
                ready,
                qualified,
                partition="development",
                guard_source=fit_prepared,
            )
            identity = _comparison_identity(
                ready,
                qualified,
                prepared,
                fit_identity_sha256=fit_identity,
                candidate_model=candidate_model,
                bundle_manifest_sha256=bundle_manifest_sha256,
            )
            _require_operation_available(identity)
            _require_terminal_absent(
                qualified,
                operation="comparison",
                identity=identity,
            )
            comparison_destination = _require_new_output(
                args.comparison_output,
                args.private_root,
            )
            if args.mode == "preflight-compare":
                result = _preflight_result(
                    ready,
                    qualified,
                    prepared,
                    identity,
                    operation="comparison",
                )
            else:
                _require_authorized(args, identity)
                result = _compare(
                    ready,
                    qualified,
                    prepared,
                    candidate_model=candidate_model,
                    bundle_manifest_sha256=bundle_manifest_sha256,
                    destination=comparison_destination,
                    comparison_identity=identity,
                )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except BaseException as error:
        print(
            json.dumps(
                {
                    "schema": "pokemon.red.resettable-goal-manager-fit-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": _failure_stage(error),
                    "effects": "not_attested_on_failure",
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _readiness(args: argparse.Namespace) -> tuple[campaign._Readiness, campaign._QualifiedCampaign]:
    campaign_path = (SCRIPTS_ROOT / "run_resettable_goal_manager_multiroot_campaign.py").resolve()
    runner_path = Path(__file__).resolve()
    if (
        not isinstance(getattr(campaign, "__file__", None), str)
        or Path(campaign.__file__).resolve(strict=True) != campaign_path
        or _file_sha256(campaign_path)
        != _sha(args.expected_campaign_runner_sha256, "campaign runner")
        or runner_path.parent != SCRIPTS_ROOT.resolve()
        or _file_sha256(runner_path) != _sha(args.expected_runner_sha256, "fit runner")
    ):
        raise MultirootFitRunError("executable_attestation")
    campaign_args = argparse.Namespace(
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
        expected_runner_sha256=args.expected_campaign_runner_sha256,
        expected_paired_runner_sha256=args.expected_paired_runner_sha256,
        expected_development_runner_sha256=args.expected_development_runner_sha256,
        expected_runtime_sha256=args.expected_runtime_sha256,
        expected_numpy_runtime_sha256=args.expected_numpy_runtime_sha256,
        expected_skill_manifest_sha256=args.expected_skill_manifest_sha256,
        expected_context_plan_sha256=args.expected_context_plan_sha256,
        rom=args.rom,
    )
    ready = campaign._readiness(campaign_args)
    qualified = campaign._qualify(
        ready,
        args.campaign_plan,
        args.private_root,
        expected_campaign_sha256=_sha(
            args.expected_campaign_sha256,
            "campaign",
        ),
        require_unclaimed=False,
    )
    registry = open_fixed_account_claim_registry()
    campaign._require_consumption_claims(ready, qualified, registry)
    campaign._require_trial_claims(ready, qualified, registry)
    campaign._require_campaign_terminal(ready, qualified, registry)
    return ready, qualified


def _prepare_inputs(
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
    *,
    partition: str,
    guard_source: _PreparedInputs | None = None,
) -> _PreparedInputs:
    if partition not in {"train", "development"}:
        raise MultirootFitRunError("partition_authentication")
    registry = open_fixed_account_claim_registry()
    campaign._require_campaign_terminal(ready, qualified, registry)
    campaign._require_consumption_claims(ready, qualified, registry)
    campaign._require_trial_claims(ready, qualified, registry)

    prepared_trials: list[_PreparedTrial] = []
    roster: list[dict[str, object]] = []
    for trial in campaign._trials(qualified.plan):
        trial_partition = campaign._partition(trial.get("partition"))
        if trial_partition != partition:
            continue
        episode_id = campaign._text(trial.get("episode_id"), "episode")
        state = qualified.store.inspect_episode_state(episode_id)
        if state.status not in _TERMINAL_STATES:
            raise MultirootFitRunError("campaign_artifact_authentication")
        manifest_sha256 = state.manifest_sha256
        if manifest_sha256 is not None:
            manifest_sha256 = _sha(manifest_sha256, "trial manifest")
        reader: PrivateEpisodeReader | None = None
        if state.status == "complete":
            reader = qualified.store.open_episode(episode_id)
            if reader.manifest_sha256 != manifest_sha256:
                raise MultirootFitRunError("campaign_artifact_authentication")
        claim = campaign._sha(trial.get("trial_claim_sha256"), "trial claim")
        trial_index = campaign._integer(trial.get("trial_index"), "trial index")
        roster.append(
            {
                "manifest_sha256": manifest_sha256,
                "partition": trial_partition,
                "reason_code": state.reason_code,
                "status": state.status,
                "trial_claim_sha256": claim,
                "trial_index": trial_index,
            }
        )
        prepared_trials.append(
            _PreparedTrial(
                trial=trial,
                status=state.status,
                manifest_sha256=manifest_sha256,
                reason_code=state.reason_code,
                reader=reader,
            )
        )

    expected_trials = (
        MULTIROOT_TRAIN_EPISODES if partition == "train" else MULTIROOT_DEVELOPMENT_EPISODES
    )
    if len(prepared_trials) != expected_trials:
        raise MultirootFitRunError("campaign_artifact_authentication")
    if guard_source is None:
        guards, menus, winner_roster, menu_roster = _load_guard_sets(ready, qualified)
        runner_sha256 = _file_sha256(Path(__file__).resolve())
        learner_sha256 = _file_sha256(
            PROJECT_ROOT / "src/pokemon_red_completion/"
            "resettable_goal_manager_multiroot_learning.py"
        )
    else:
        if (
            guard_source.partition != "train"
            or len(guard_source.guard_examples) != 18
            or len(guard_source.kl_examples) != 54
            or _file_sha256(Path(__file__).resolve()) != guard_source.runner_sha256
            or _file_sha256(
                PROJECT_ROOT / "src/pokemon_red_completion/"
                "resettable_goal_manager_multiroot_learning.py"
            )
            != guard_source.learner_sha256
        ):
            raise MultirootFitRunError("guard_set_contract")
        guards = guard_source.guard_examples
        menus = guard_source.kl_examples
        winner_roster = guard_source.guard_winner_manifest_roster_sha256
        menu_roster = guard_source.guard_menu_manifest_roster_sha256
        runner_sha256 = guard_source.runner_sha256
        learner_sha256 = guard_source.learner_sha256
    return _PreparedInputs(
        partition=partition,
        trials=tuple(prepared_trials),
        trial_manifest_roster_sha256=canonical_sha256(
            {
                "schema": "pokemon.red.resettable-goal-manager-trial-roster.v1",
                "trials": roster,
            }
        ),
        guard_examples=guards,
        kl_examples=menus,
        guard_winner_manifest_roster_sha256=winner_roster,
        guard_menu_manifest_roster_sha256=menu_roster,
        runner_sha256=runner_sha256,
        learner_sha256=learner_sha256,
    )


def _preflight_result(
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
    prepared: _PreparedInputs,
    identity: str,
    *,
    operation: str,
) -> dict[str, object]:
    statuses = [trial.status for trial in prepared.trials]
    return {
        "schema": "pokemon.red.resettable-goal-manager-operation-preflight.v1",
        "status": "ready_without_fresh_campaign_outcome_decode",
        "operation": operation,
        "operation_identity_sha256": identity,
        "campaign_plan_sha256": qualified.plan_sha256,
        "campaign_terminal_sha256": campaign._campaign_terminal_identity(qualified),
        "base_model_canonical_sha256": (ready.paired.candidate_model_canonical_sha256),
        "source_commit": ready.paired.development.source.git_commit,
        "runner_sha256": prepared.runner_sha256,
        "campaign_runner_sha256": ready.runner_sha256,
        "learner_sha256": prepared.learner_sha256,
        "campaign_terminal_authenticated": True,
        "prepared_partition": prepared.partition,
        "trial_manifest_roster_sha256": prepared.trial_manifest_roster_sha256,
        "guard_menu_manifest_roster_sha256": (prepared.guard_menu_manifest_roster_sha256),
        "guard_winner_manifest_roster_sha256": (prepared.guard_winner_manifest_roster_sha256),
        "terminal_states": dict(
            sorted({status: statuses.count(status) for status in set(statuses)}.items())
        ),
        "fresh_campaign_outcomes_decoded": 0,
        "historical_guard_examples_loaded": len(prepared.kl_examples),
        "model_fits": 0,
        "comparisons": 0,
        "private_path_fields": 0,
    }


def _fit(
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
    prepared: _PreparedInputs,
    destination: Path,
    fit_identity: str,
) -> dict[str, object]:
    _claim_operation(ready, prepared, fit_identity)
    model_fits = 0
    candidate_sha256: str | None = None
    model_file_sha256: str | None = None
    summary_file_sha256: str | None = None
    bundle_manifest_sha256: str | None = None
    try:
        train_episodes, invalid = _decode_prepared_partition(
            ready,
            qualified,
            prepared,
            partition="train",
        )
        if len(train_episodes) + sum(invalid.values()) != MULTIROOT_TRAIN_EPISODES:
            raise MultirootFitRunError("train_denominator_authentication")
        train_set = admit_resettable_goal_manager_train_set(train_episodes)
        base_model = ready.paired.candidate_model
        fitted = fit_resettable_goal_manager_train_set(
            base_model,
            train_episodes,
            guard_examples=prepared.guard_examples,
            kl_examples=prepared.kl_examples,
        )
        model_fits = 1
        model_payload = _canonical_line(fitted.update.model.to_dict())
        reloaded = GoalManagerLinearModel.from_dict(json.loads(model_payload))
        if reloaded.to_dict() != fitted.update.model.to_dict():
            raise MultirootFitRunError("candidate_round_trip")
        candidate_sha256 = canonical_goal_manager_model_sha256(reloaded)
        model_file_sha256 = hashlib.sha256(model_payload).hexdigest()
        summary = {
            "schema": "pokemon.red.resettable-goal-manager-fit-summary.v1",
            "status": "train_only_shadow_fit_complete",
            "fit_identity_sha256": fit_identity,
            "campaign_plan_sha256": qualified.plan_sha256,
            "campaign_terminal_sha256": campaign._campaign_terminal_identity(qualified),
            "base_model_canonical_sha256": canonical_goal_manager_model_sha256(base_model),
            "candidate_model_canonical_sha256": candidate_sha256,
            "candidate_model_file_sha256": model_file_sha256,
            "train_gate": train_set.public_dict(),
            "fit": fitted.public_dict(),
            "trial_manifest_roster_sha256": prepared.trial_manifest_roster_sha256,
            "guard_menu_manifest_roster_sha256": (prepared.guard_menu_manifest_roster_sha256),
            "guard_winner_manifest_roster_sha256": (prepared.guard_winner_manifest_roster_sha256),
            "invalid_train_states": invalid,
            "development_outcomes_accessed": 0,
            "evaluation": None,
            "promotion_authorized": False,
            "authority_delta": 0,
            "private_path_fields": 0,
        }
        summary_payload = _canonical_line(summary)
        summary_file_sha256 = hashlib.sha256(summary_payload).hexdigest()
        bundle_manifest_sha256 = _publish_bundle(
            destination,
            model_payload=model_payload,
            summary_payload=summary_payload,
            identity_sha256=fit_identity,
        )
        terminal = _publish_operation_terminal(
            qualified,
            operation="fit",
            identity=fit_identity,
            record=_fit_terminal_record(
                ready,
                qualified,
                prepared,
                fit_identity=fit_identity,
                status="complete",
                failure_stage=None,
                model_fits=model_fits,
                bundle_manifest_sha256=bundle_manifest_sha256,
                candidate_model_canonical_sha256=candidate_sha256,
                candidate_model_file_sha256=model_file_sha256,
                summary_file_sha256=summary_file_sha256,
            ),
        )
        return {
            "schema": "pokemon.red.resettable-goal-manager-fit-result.v1",
            "status": "train_only_shadow_fit_complete",
            "fit_identity_sha256": fit_identity,
            "bundle_manifest_sha256": bundle_manifest_sha256,
            "fit_terminal_manifest_sha256": terminal.summary.manifest_sha256,
            "fit_terminal_record_sha256": terminal.summary.record_sha256,
            "train_targets": len(train_set.rows),
            "train_roots": len(train_set.roots),
            "train_goal_kinds": list(train_set.selected_goal_kinds),
            "candidate_model_canonical_sha256": candidate_sha256,
            "development_outcomes_accessed": 0,
            "model_fits_added": 1,
            "comparisons_added": 0,
            "authority_delta": 0,
            "private_path_fields": 0,
        }
    except BaseException as error:
        try:
            _publish_operation_terminal(
                qualified,
                operation="fit",
                identity=fit_identity,
                record=_fit_terminal_record(
                    ready,
                    qualified,
                    prepared,
                    fit_identity=fit_identity,
                    status="failed",
                    failure_stage=_failure_stage(error),
                    model_fits=model_fits,
                    bundle_manifest_sha256=bundle_manifest_sha256,
                    candidate_model_canonical_sha256=candidate_sha256,
                    candidate_model_file_sha256=model_file_sha256,
                    summary_file_sha256=summary_file_sha256,
                ),
            )
        except BaseException:
            raise MultirootFitRunError("fit_terminal_publication") from None
        raise


def _compare(
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
    prepared: _PreparedInputs,
    *,
    candidate_model: GoalManagerLinearModel,
    bundle_manifest_sha256: str,
    destination: Path,
    comparison_identity: str,
) -> dict[str, object]:
    _claim_operation(ready, prepared, comparison_identity)
    comparisons = 0
    output_file_sha256: str | None = None
    result_sha256: str | None = None
    try:
        development_episodes, invalid = _decode_prepared_partition(
            ready,
            qualified,
            prepared,
            partition="development",
        )
        if len(development_episodes) + sum(invalid.values()) != MULTIROOT_DEVELOPMENT_EPISODES:
            raise MultirootFitRunError("development_denominator_authentication")
        settled = tuple(episode for episode in development_episodes if len(episode.targets) == 1)
        unsettled = len(development_episodes) - len(settled)
        if unsettled:
            invalid = dict(invalid)
            invalid["complete_without_settled_target"] = unsettled
        comparison: ResettableGoalManagerComparison | None = None
        if len(settled) == MULTIROOT_DEVELOPMENT_EPISODES:
            train_roots = tuple(
                campaign._text(
                    campaign._mapping(record.get("root"), "root").get("root_lineage_id"),
                    "root lineage",
                )
                for record in campaign._root_records(qualified.plan)
                if record.get("partition") == "train"
            )
            comparison = compare_resettable_goal_manager_development(
                ready.paired.candidate_model,
                candidate_model,
                settled,
                train_roots=train_roots,
            )
            comparisons = 1
        result = {
            "schema": "pokemon.red.resettable-goal-manager-comparison-result.v1",
            "status": (
                "fixed_denominator_compared"
                if comparison is not None
                else "fixed_denominator_uninterpretable"
            ),
            "comparison_identity_sha256": comparison_identity,
            "campaign_plan_sha256": qualified.plan_sha256,
            "campaign_terminal_sha256": campaign._campaign_terminal_identity(qualified),
            "candidate_bundle_manifest_sha256": bundle_manifest_sha256,
            "trial_manifest_roster_sha256": prepared.trial_manifest_roster_sha256,
            "guard_menu_manifest_roster_sha256": (prepared.guard_menu_manifest_roster_sha256),
            "guard_winner_manifest_roster_sha256": (prepared.guard_winner_manifest_roster_sha256),
            "planned_development_episodes": MULTIROOT_DEVELOPMENT_EPISODES,
            "complete_development_episodes": len(development_episodes),
            "settled_development_targets": len(settled),
            "invalid_development_states": dict(sorted(invalid.items())),
            "comparison": None if comparison is None else comparison.public_dict(),
            "favorable": None if comparison is None else comparison.favorable,
            "model_fits_added": 0,
            "unseen_comparisons_added": comparisons,
            "authority_delta": 0,
            "promotion_authorized": False,
            "private_path_fields": 0,
        }
        result_payload = _canonical_line(result)
        result_sha256 = hashlib.sha256(result_payload).hexdigest()
        output_file_sha256 = _write_atomic_no_replace(
            destination,
            result_payload,
            subject="comparison",
        )
        terminal = _publish_operation_terminal(
            qualified,
            operation="comparison",
            identity=comparison_identity,
            record=_comparison_terminal_record(
                ready,
                qualified,
                prepared,
                comparison_identity=comparison_identity,
                candidate_bundle_manifest_sha256=bundle_manifest_sha256,
                status=cast(str, result["status"]),
                failure_stage=None,
                comparisons=comparisons,
                output_file_sha256=output_file_sha256,
                result_sha256=result_sha256,
            ),
        )
        return {
            **result,
            "comparison_terminal_manifest_sha256": terminal.summary.manifest_sha256,
            "comparison_terminal_record_sha256": terminal.summary.record_sha256,
        }
    except BaseException as error:
        try:
            _publish_operation_terminal(
                qualified,
                operation="comparison",
                identity=comparison_identity,
                record=_comparison_terminal_record(
                    ready,
                    qualified,
                    prepared,
                    comparison_identity=comparison_identity,
                    candidate_bundle_manifest_sha256=bundle_manifest_sha256,
                    status="failed",
                    failure_stage=_failure_stage(error),
                    comparisons=comparisons,
                    output_file_sha256=output_file_sha256,
                    result_sha256=result_sha256,
                ),
            )
        except BaseException:
            raise MultirootFitRunError("comparison_terminal_publication") from None
        raise


def _load_guard_sets(
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
) -> tuple[
    tuple[GoalManagerExample, ...],
    tuple[GoalManagerExample, ...],
    str,
    str,
]:
    base = ready.paired.development
    registry = base.candidate.registry
    catalog = base.candidate.catalog
    guards: list[GoalManagerExample] = []
    menus: list[GoalManagerExample] = []
    manifests: list[str] = []
    guard_manifests: list[str] = []
    for slot in registry.slots:
        if slot.partition != "train":
            continue
        assignment = registry.assignment(slot.slot_id)
        reader = qualified.store.open_episode(assignment.episode_id)
        loaded = load_assigned_goal_manager_episode(
            reader,
            assignment,
            context_catalog=catalog,
        )
        manifests.append(reader.manifest_sha256)
        menus.extend(loaded.examples)
        if slot.focus_kind in _GUARD_KINDS:
            guard_manifests.append(reader.manifest_sha256)
            guards.extend(loaded.examples)
    if (
        len(menus) != 54
        or len(guards) != 18
        or len(manifests) != 54
        or len(set(manifests)) != 54
        or len(guard_manifests) != 18
        or len(set(guard_manifests)) != 18
    ):
        raise MultirootFitRunError("guard_set_contract")
    return (
        tuple(guards),
        tuple(menus),
        canonical_sha256(
            {
                "schema": "pokemon.red.resettable-goal-manager-guard-winner-roster.v1",
                "manifest_sha256": guard_manifests,
            }
        ),
        canonical_sha256(
            {
                "schema": "pokemon.red.resettable-goal-manager-guard-menu-roster.v1",
                "manifest_sha256": manifests,
            }
        ),
    )


def _decode_prepared_partition(
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
    prepared: _PreparedInputs,
    *,
    partition: str,
) -> tuple[tuple[AdmittedGoalManagerDevelopmentEpisode, ...], dict[str, int]]:
    if prepared.partition != partition:
        raise MultirootFitRunError("prepared_partition_authentication")
    base = ready.paired.development
    episodes: list[AdmittedGoalManagerDevelopmentEpisode] = []
    invalid: dict[str, int] = {}
    for retained in prepared.trials:
        trial = retained.trial
        if trial.get("partition") != partition:
            continue
        if retained.status != "complete":
            invalid[retained.status] = invalid.get(retained.status, 0) + 1
            continue
        if retained.reader is None or retained.reader.manifest_sha256 != retained.manifest_sha256:
            raise MultirootFitRunError("prepared_reader_authentication")
        claim = campaign._sha(trial.get("trial_claim_sha256"), "trial claim")
        root_index = campaign._integer(trial.get("root_index"), "root index")
        root = qualified.roots[root_index]
        root_record = campaign._mapping(
            campaign._root_records(qualified.plan)[root_index].get("root"),
            "root",
        )
        episodes.append(
            load_repeatable_goal_manager_development_episode(
                retained.reader,
                expected_campaign_id=campaign._sha(
                    qualified.plan.get("campaign_id"),
                    "campaign",
                ),
                expected_trial_claim_sha256=claim,
                expected_episode_id=campaign._text(trial.get("episode_id"), "episode"),
                expected_root_lineage_id=campaign._text(
                    root_record.get("root_lineage_id"),
                    "root lineage",
                ),
                expected_seed=campaign._integer(trial.get("seed"), "seed"),
                expected_execution_identity_sha256=campaign._trial_execution_identity(
                    ready,
                    qualified,
                    trial,
                ),
                expected_context_catalog_sha256=(base.candidate.catalog.catalog_sha256),
                expected_context_id=base.candidate.catalog.entry(root.entry.slot_id).context_id,
                expected_binding_manifest_sha256=campaign._sha(
                    root_record.get("binding_manifest_sha256"),
                    "binding manifest",
                ),
                expected_state_sha256=campaign._sha(
                    root_record.get("state_sha256"),
                    "state",
                ),
                expected_envelope_sha256=campaign._sha(
                    root_record.get("envelope_sha256"),
                    "envelope",
                ),
                expected_first_question_sha256=campaign._sha(
                    root_record.get("question_sha256"),
                    "question",
                ),
                expected_first_policy_context_sha256=campaign._sha(
                    root_record.get("policy_context_sha256"),
                    "policy context",
                ),
                expected_first_available_menu_sha256=campaign._sha(
                    root_record.get("available_menu_sha256"),
                    "available menu",
                ),
                expected_model=ready.paired.candidate_model,
                expected_source_commit=base.source.git_commit or "",
                expected_partition=partition,
                expected_maximum_decisions=1,
            )
        )
    return tuple(episodes), dict(sorted(invalid.items()))


def _terminal_record_id(operation: str, identity: str) -> str:
    prefix = "rgm-fit" if operation == "fit" else "rgm-compare"
    if operation not in {"fit", "comparison"}:
        raise MultirootFitRunError("operation_authentication")
    return f"{prefix}-{_sha(identity, 'operation identity')}"


def _terminal_kind(operation: str) -> str:
    if operation == "fit":
        return _FIT_TERMINAL_KIND
    if operation == "comparison":
        return _COMPARISON_TERMINAL_KIND
    raise MultirootFitRunError("operation_authentication")


def _require_terminal_absent(
    qualified: campaign._QualifiedCampaign,
    *,
    operation: str,
    identity: str,
) -> None:
    try:
        existing = qualified.store.find_sealed_record(
            _terminal_record_id(operation, identity),
            expected_kind=_terminal_kind(operation),
        )
    except Exception:
        raise MultirootFitRunError("operation_terminal_authentication") from None
    if existing is not None:
        raise MultirootFitRunError("operation_identity_consumed")


def _publish_operation_terminal(
    qualified: campaign._QualifiedCampaign,
    *,
    operation: str,
    identity: str,
    record: Mapping[str, object],
) -> Any:
    try:
        return qualified.store.publish_sealed_record(
            _terminal_record_id(operation, identity),
            kind=_terminal_kind(operation),
            record=record,
        )
    except Exception:
        raise MultirootFitRunError(f"{operation}_terminal_publication") from None


def _fit_terminal_record(
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
    prepared: _PreparedInputs,
    *,
    fit_identity: str,
    status: str,
    failure_stage: str | None,
    model_fits: int,
    bundle_manifest_sha256: str | None,
    candidate_model_canonical_sha256: str | None,
    candidate_model_file_sha256: str | None,
    summary_file_sha256: str | None,
) -> dict[str, object]:
    if status not in {"complete", "failed"}:
        raise MultirootFitRunError("fit_terminal_authentication")
    return {
        "schema": "pokemon.red.resettable-goal-manager-fit-terminal.v1",
        "status": status,
        "failure_stage": failure_stage,
        "fit_identity_sha256": fit_identity,
        "campaign_plan_sha256": qualified.plan_sha256,
        "campaign_terminal_sha256": campaign._campaign_terminal_identity(qualified),
        "source_commit": ready.paired.development.source.git_commit,
        "runner_sha256": prepared.runner_sha256,
        "trial_manifest_roster_sha256": prepared.trial_manifest_roster_sha256,
        "guard_menu_manifest_roster_sha256": (prepared.guard_menu_manifest_roster_sha256),
        "guard_winner_manifest_roster_sha256": (prepared.guard_winner_manifest_roster_sha256),
        "bundle_manifest_sha256": bundle_manifest_sha256,
        "candidate_model_canonical_sha256": candidate_model_canonical_sha256,
        "candidate_model_file_sha256": candidate_model_file_sha256,
        "summary_file_sha256": summary_file_sha256,
        "model_fits": model_fits,
        "development_outcomes_decoded": 0,
        "authority_delta": 0,
        "private_path_fields": 0,
    }


def _comparison_terminal_record(
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
    prepared: _PreparedInputs,
    *,
    comparison_identity: str,
    candidate_bundle_manifest_sha256: str,
    status: str,
    failure_stage: str | None,
    comparisons: int,
    output_file_sha256: str | None,
    result_sha256: str | None,
) -> dict[str, object]:
    if status not in {
        "failed",
        "fixed_denominator_compared",
        "fixed_denominator_uninterpretable",
    }:
        raise MultirootFitRunError("comparison_terminal_authentication")
    return {
        "schema": "pokemon.red.resettable-goal-manager-comparison-terminal.v1",
        "status": status,
        "failure_stage": failure_stage,
        "comparison_identity_sha256": comparison_identity,
        "campaign_plan_sha256": qualified.plan_sha256,
        "campaign_terminal_sha256": campaign._campaign_terminal_identity(qualified),
        "candidate_bundle_manifest_sha256": candidate_bundle_manifest_sha256,
        "source_commit": ready.paired.development.source.git_commit,
        "runner_sha256": prepared.runner_sha256,
        "trial_manifest_roster_sha256": prepared.trial_manifest_roster_sha256,
        "guard_menu_manifest_roster_sha256": (prepared.guard_menu_manifest_roster_sha256),
        "guard_winner_manifest_roster_sha256": (prepared.guard_winner_manifest_roster_sha256),
        "output_file_sha256": output_file_sha256,
        "result_sha256": result_sha256,
        "comparisons": comparisons,
        "model_fits": 0,
        "authority_delta": 0,
        "private_path_fields": 0,
    }


def _fit_identity(
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
    prepared: _PreparedInputs,
) -> str:
    return cast(
        str,
        canonical_sha256(
            {
                "base_model_canonical_sha256": (ready.paired.candidate_model_canonical_sha256),
                "campaign_plan_sha256": qualified.plan_sha256,
                "campaign_terminal_sha256": (campaign._campaign_terminal_identity(qualified)),
                "trial_manifest_roster_sha256": (prepared.trial_manifest_roster_sha256),
                "guard_menu_manifest_roster_sha256": (prepared.guard_menu_manifest_roster_sha256),
                "guard_winner_manifest_roster_sha256": (
                    prepared.guard_winner_manifest_roster_sha256
                ),
                "learner_sha256": prepared.learner_sha256,
                "runner_sha256": prepared.runner_sha256,
                "schema": "pokemon.red.resettable-goal-manager-fit-identity.v1",
                "source_commit": ready.paired.development.source.git_commit,
            },
        ),
    )


def _comparison_identity(
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
    prepared: _PreparedInputs,
    *,
    fit_identity_sha256: str,
    candidate_model: GoalManagerLinearModel,
    bundle_manifest_sha256: str,
) -> str:
    return cast(
        str,
        canonical_sha256(
            {
                "campaign_plan_sha256": qualified.plan_sha256,
                "campaign_terminal_sha256": (campaign._campaign_terminal_identity(qualified)),
                "candidate_bundle_manifest_sha256": bundle_manifest_sha256,
                "candidate_model_canonical_sha256": (
                    canonical_goal_manager_model_sha256(candidate_model)
                ),
                "fit_identity_sha256": _sha(
                    fit_identity_sha256,
                    "fit identity",
                ),
                "trial_manifest_roster_sha256": (prepared.trial_manifest_roster_sha256),
                "guard_menu_manifest_roster_sha256": (prepared.guard_menu_manifest_roster_sha256),
                "guard_winner_manifest_roster_sha256": (
                    prepared.guard_winner_manifest_roster_sha256
                ),
                "rule": {
                    "candidate_cross_entropy": "strictly_lower",
                    "maximum_directional_losses": 0,
                    "minimum_directional_wins": 3,
                },
                "schema": "pokemon.red.resettable-goal-manager-comparison-identity.v1",
            },
        ),
    )


def _claim_operation(
    ready: campaign._Readiness,
    prepared: _PreparedInputs,
    identity: str,
) -> None:
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        if not root_claim_is_available(registry, identity):
            raise MultirootFitRunError("operation_identity_consumed")
        write_root_claim(
            registry,
            root_consumption_sha256=identity,
            execution_identity_sha256=identity,
            source_commit=ready.paired.development.source.git_commit or "",
            runner_sha256=prepared.runner_sha256,
        )


def _require_operation_available(identity: str) -> None:
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        if not root_claim_is_available(registry, identity):
            raise MultirootFitRunError("operation_identity_consumed")


def _load_candidate_bundle(
    path: Path,
    private_root: Path,
    *,
    ready: campaign._Readiness,
    qualified: campaign._QualifiedCampaign,
    prepared: _PreparedInputs,
    expected_fit_identity: str,
    expected_bundle_manifest_sha256: str,
    expected_source_commit: str,
) -> tuple[GoalManagerLinearModel, str]:
    manifest_payload, model_payload, summary_payload = _read_bundle_files(
        path,
        private_root,
    )
    manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
    if manifest_sha256 != expected_bundle_manifest_sha256:
        raise MultirootFitRunError("candidate_bundle_attestation")
    manifest = _document(manifest_payload, "candidate manifest")
    if (
        set(manifest) != {"files", "fit_identity_sha256", "schema", "status"}
        or manifest.get("schema") != "pokemon.red.resettable-goal-manager-fit-bundle.v1"
        or manifest.get("status") != "complete"
        or manifest.get("fit_identity_sha256") != expected_fit_identity
        or manifest.get("files")
        != {
            "model.json": hashlib.sha256(model_payload).hexdigest(),
            "summary.json": hashlib.sha256(summary_payload).hexdigest(),
        }
    ):
        raise MultirootFitRunError("candidate_bundle_authentication")
    summary = _document(summary_payload, "candidate summary")
    model = GoalManagerLinearModel.from_dict(_document(model_payload, "candidate model"))
    model_sha256 = canonical_goal_manager_model_sha256(model)
    model_file_sha256 = hashlib.sha256(model_payload).hexdigest()
    summary_file_sha256 = hashlib.sha256(summary_payload).hexdigest()
    expected_summary_keys = {
        "authority_delta",
        "base_model_canonical_sha256",
        "campaign_plan_sha256",
        "campaign_terminal_sha256",
        "candidate_model_canonical_sha256",
        "candidate_model_file_sha256",
        "development_outcomes_accessed",
        "evaluation",
        "fit",
        "fit_identity_sha256",
        "guard_menu_manifest_roster_sha256",
        "guard_winner_manifest_roster_sha256",
        "invalid_train_states",
        "private_path_fields",
        "promotion_authorized",
        "schema",
        "status",
        "train_gate",
        "trial_manifest_roster_sha256",
    }
    if (
        set(summary) != expected_summary_keys
        or summary.get("schema") != "pokemon.red.resettable-goal-manager-fit-summary.v1"
        or summary.get("status") != "train_only_shadow_fit_complete"
        or summary.get("fit_identity_sha256") != expected_fit_identity
        or summary.get("campaign_plan_sha256") != qualified.plan_sha256
        or summary.get("campaign_terminal_sha256")
        != campaign._campaign_terminal_identity(qualified)
        or summary.get("base_model_canonical_sha256")
        != ready.paired.candidate_model_canonical_sha256
        or summary.get("candidate_model_canonical_sha256") != model_sha256
        or summary.get("candidate_model_file_sha256") != model_file_sha256
        or summary.get("trial_manifest_roster_sha256") != prepared.trial_manifest_roster_sha256
        or summary.get("guard_menu_manifest_roster_sha256")
        != prepared.guard_menu_manifest_roster_sha256
        or summary.get("guard_winner_manifest_roster_sha256")
        != prepared.guard_winner_manifest_roster_sha256
        or summary.get("development_outcomes_accessed") != 0
        or summary.get("evaluation") is not None
        or summary.get("promotion_authorized") is not False
        or summary.get("authority_delta") != 0
        or summary.get("private_path_fields") != 0
        or not isinstance(summary.get("train_gate"), Mapping)
        or not isinstance(summary.get("fit"), Mapping)
        or not isinstance(summary.get("invalid_train_states"), Mapping)
    ):
        raise MultirootFitRunError("candidate_bundle_authentication")
    registry = open_fixed_account_claim_registry()
    claim = read_root_claim(registry, expected_fit_identity)
    if claim != {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": expected_fit_identity,
        "execution_identity_sha256": expected_fit_identity,
        "source_commit": expected_source_commit,
        "runner_sha256": prepared.runner_sha256,
    }:
        raise MultirootFitRunError("fit_claim_authentication")
    try:
        terminal = qualified.store.find_sealed_record(
            _terminal_record_id("fit", expected_fit_identity),
            expected_kind=_FIT_TERMINAL_KIND,
        )
    except Exception:
        raise MultirootFitRunError("fit_terminal_authentication") from None
    if terminal is None or terminal.read() != _fit_terminal_record(
        ready,
        qualified,
        prepared,
        fit_identity=expected_fit_identity,
        status="complete",
        failure_stage=None,
        model_fits=1,
        bundle_manifest_sha256=manifest_sha256,
        candidate_model_canonical_sha256=model_sha256,
        candidate_model_file_sha256=model_file_sha256,
        summary_file_sha256=summary_file_sha256,
    ):
        raise MultirootFitRunError("fit_terminal_authentication")
    return model, manifest_sha256


def _publish_bundle(
    destination: Path,
    *,
    model_payload: bytes,
    summary_payload: bytes,
    identity_sha256: str,
) -> str:
    temporary: Path | None = None
    try:
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.partial-", dir=destination.parent)
        )
        os.chmod(temporary, 0o700)
        model_sha256 = _write_file(temporary / "model.json", model_payload)
        summary_sha256 = _write_file(temporary / "summary.json", summary_payload)
        manifest_payload = _canonical_line(
            {
                "schema": "pokemon.red.resettable-goal-manager-fit-bundle.v1",
                "status": "complete",
                "fit_identity_sha256": identity_sha256,
                "files": {
                    "model.json": model_sha256,
                    "summary.json": summary_sha256,
                },
            }
        )
        manifest_sha256 = _write_file(temporary / "manifest.json", manifest_payload)
        descriptor = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _rename_no_replace(temporary, destination)
        parent = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        return manifest_sha256
    except OSError:
        raise MultirootFitRunError("bundle_publication") from None
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)


def _write_file(path: Path, payload: bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return hashlib.sha256(payload).hexdigest()


def _write_atomic_no_replace(path: Path, payload: bytes, *, subject: str) -> str:
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, raw_temporary = tempfile.mkstemp(
            prefix=f".{path.name}.partial-",
            dir=path.parent,
        )
        temporary = Path(raw_temporary)
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _rename_no_replace(temporary, path)
        temporary = None
        directory = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise MultirootFitRunError(f"{subject}_publication") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink()
    return hashlib.sha256(payload).hexdigest()


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("write made no progress")
        offset += written


def _require_new_bundle(path: Path, private_root: Path) -> Path:
    root = private_root.resolve(strict=True)
    parent = path.parent.resolve(strict=True)
    resolved = parent / path.name
    if not resolved.is_relative_to(root) or resolved.exists() or path.is_symlink():
        raise MultirootFitRunError("output_contract")
    return resolved


def _require_new_output(path: Path, private_root: Path) -> Path:
    return _require_new_bundle(path, private_root)


def _require_authorized(args: argparse.Namespace, identity: str) -> None:
    if _sha(args.expected_operation_identity_sha256, "operation identity") != identity:
        raise MultirootFitRunError("operation_authorization")


def _document(payload: bytes, subject: str) -> Mapping[str, object]:
    if not payload or len(payload) > _MAX_DOCUMENT_BYTES:
        raise MultirootFitRunError(f"{subject.replace(' ', '_')}_authentication")
    try:
        value = json.loads(payload.decode("ascii"))
        canonical = _canonical_line(value)
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise MultirootFitRunError(f"{subject.replace(' ', '_')}_authentication") from None
    if not isinstance(value, Mapping) or canonical != payload:
        raise MultirootFitRunError(f"{subject.replace(' ', '_')}_authentication")
    return cast(Mapping[str, object], value)


def _read_bundle_files(
    path: Path,
    private_root: Path,
) -> tuple[bytes, bytes, bytes]:
    directory = -1
    try:
        root = private_root.resolve(strict=True)
        bundle = path.resolve(strict=True)
        named = bundle.lstat()
        if path.is_symlink() or not bundle.is_relative_to(root):
            raise OSError("unsafe bundle path")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        if not hasattr(os, "O_NOFOLLOW"):
            raise OSError("nofollow unavailable")
        flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        directory = os.open(bundle, flags)
        metadata = os.fstat(directory)
        if (
            named.st_dev != metadata.st_dev
            or named.st_ino != metadata.st_ino
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or set(os.listdir(directory)) != {"manifest.json", "model.json", "summary.json"}
        ):
            raise OSError("unsafe bundle directory")
        manifest = _read_regular_file_at(
            directory,
            "manifest.json",
            "candidate manifest",
        )
        model = _read_regular_file_at(directory, "model.json", "candidate model")
        summary = _read_regular_file_at(
            directory,
            "summary.json",
            "candidate summary",
        )
    except OSError:
        raise MultirootFitRunError("candidate_bundle_authentication") from None
    finally:
        if directory >= 0:
            with suppress(OSError):
                os.close(directory)
    return manifest, model, summary


def _read_regular_file(path: Path, subject: str) -> bytes:
    directory = -1
    try:
        if not hasattr(os, "O_NOFOLLOW"):
            raise OSError("nofollow unavailable")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        directory = os.open(path.parent, flags)
        return _read_regular_file_at(directory, path.name, subject)
    except OSError:
        raise MultirootFitRunError(f"{subject.replace(' ', '_')}_authentication") from None
    finally:
        if directory >= 0:
            with suppress(OSError):
                os.close(directory)


def _read_regular_file_at(directory: int, name: str, subject: str) -> bytes:
    descriptor = -1
    try:
        if not hasattr(os, "O_NOFOLLOW"):
            raise OSError("nofollow unavailable")
        named = os.stat(name, dir_fd=directory, follow_symlinks=False)
        flags = os.O_RDONLY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(name, flags, dir_fd=directory)
        metadata = os.fstat(descriptor)
        if (
            named.st_dev != metadata.st_dev
            or named.st_ino != metadata.st_ino
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 1 <= metadata.st_size <= _MAX_DOCUMENT_BYTES
        ):
            raise OSError("unsafe regular file")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise OSError("short read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise OSError("file grew during read")
        after = os.fstat(descriptor)
        if (
            metadata.st_dev != after.st_dev
            or metadata.st_ino != after.st_ino
            or metadata.st_size != after.st_size
            or metadata.st_mtime_ns != after.st_mtime_ns
            or metadata.st_ctime_ns != after.st_ctime_ns
        ):
            raise OSError("file changed during read")
        payload = b"".join(chunks)
    except OSError:
        raise MultirootFitRunError(f"{subject.replace(' ', '_')}_authentication") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
    return payload


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
    descriptor = -1
    try:
        if not hasattr(os, "O_NOFOLLOW"):
            raise OSError("nofollow unavailable")
        named = path.lstat()
        flags = os.O_RDONLY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            named.st_dev != metadata.st_dev
            or named.st_ino != metadata.st_ino
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o644
            or not 1 <= metadata.st_size <= _MAX_DOCUMENT_BYTES
        ):
            raise OSError("unsafe source file")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise OSError("short source read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise OSError("source file grew during read")
        after = os.fstat(descriptor)
        if (
            metadata.st_dev != after.st_dev
            or metadata.st_ino != after.st_ino
            or metadata.st_size != after.st_size
            or metadata.st_mtime_ns != after.st_mtime_ns
            or metadata.st_ctime_ns != after.st_ctime_ns
        ):
            raise OSError("source file changed during read")
        return hashlib.sha256(b"".join(chunks)).hexdigest()
    except OSError:
        raise MultirootFitRunError("source_file_authentication") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise MultirootFitRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _failure_stage(error: BaseException) -> str:
    if isinstance(
        error,
        (GoalManagerOutcomeLearningError, ResettableGoalManagerLearningError),
    ):
        return "preregistered_learning_gate_rejected"
    if isinstance(error, (MultirootFitRunError, campaign.ResettableMultirootRunError)):
        value = str(error)
        if value and value.replace("_", "").isalnum():
            return value
    return "unexpected_failure"


if __name__ == "__main__":
    raise SystemExit(main())
