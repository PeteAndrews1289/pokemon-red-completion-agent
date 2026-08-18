#!/usr/bin/env python3
# mypy: disable-error-code=attr-defined
"""Collect one authenticated train-only Red goal choice and its verified outcome."""

# ruff: noqa: E402 -- reviewed local runners must win import resolution

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import run_repeatable_goal_manager_development as development
import run_resettable_goal_manager_multiroot_campaign as multiroot

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    root_consumption_sha256,
    write_root_claim,
)
from pokemon_red_completion.provenance import canonical_sha256

CAMPAIGN_SCHEMA = "pokemon.red.single-root-causal-goal-outcome-campaign.v1"
TRIAL_CLAIM_SCHEMA = "pokemon.red.single-root-causal-goal-outcome-trial-claim.v1"
CAMPAIGN_CONSUMPTION_SCHEMA = "pokemon.red.single-root-causal-goal-outcome-campaign-consumption.v1"
LANE_ID = "first-causal-goal-outcome-v1"
LANE_CONSUMPTION_SCHEMA = "pokemon.red.single-root-causal-goal-outcome-lane-consumption.v1"
LANE_CONSUMPTION_SHA256 = canonical_sha256({"lane_id": LANE_ID, "schema": LANE_CONSUMPTION_SCHEMA})
TRIAL_SEED = 40_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_STAGE = re.compile(r"[a-z0-9_]+\Z")
_T = TypeVar("_T")


class SingleRootCausalRunError(RuntimeError):
    """A sanitized failure at one single-root outcome stage."""

    def __init__(self, stage: str) -> None:
        if _SAFE_STAGE.fullmatch(stage) is None:
            stage = "unexpected_failure"
        self.stage = stage
        super().__init__(stage)


@dataclass(frozen=True, slots=True)
class _Readiness:
    paired: Any
    runner_sha256: str
    multiroot_runner_sha256: str


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("freeze", "preflight", "execute", "admit"),
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
    parser.add_argument("--expected-multiroot-runner-sha256", required=True)
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
    del argv
    print(
        json.dumps(
            {
                "schema": "pokemon.red.single-root-causal-goal-outcome-failure.v1",
                "status": "failed_closed",
                "failure_stage": "lane_retired",
                "effects": "no_manifest_readiness_or_private_access",
                "private_path_fields": 0,
            },
            sort_keys=True,
        )
    )
    return 1


def _at_stage(stage: str, operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except SingleRootCausalRunError:
        raise
    except Exception as error:
        raise SingleRootCausalRunError(stage) from error


def _readiness(args: argparse.Namespace) -> _Readiness:
    runner_path = Path(__file__).resolve()
    runner_sha256 = _file_sha256(runner_path)
    if runner_path.parent != SCRIPTS_ROOT.resolve() or runner_sha256 != _sha(
        args.expected_runner_sha256,
        "runner",
    ):
        raise SingleRootCausalRunError("executable_attestation")
    multiroot_path = (SCRIPTS_ROOT / "run_resettable_goal_manager_multiroot_campaign.py").resolve()
    development_path = (SCRIPTS_ROOT / "run_repeatable_goal_manager_development.py").resolve()
    if (
        not isinstance(getattr(multiroot, "__file__", None), str)
        or Path(multiroot.__file__).resolve(strict=True) != multiroot_path
        or not isinstance(getattr(development, "__file__", None), str)
        or Path(development.__file__).resolve(strict=True) != development_path
    ):
        raise SingleRootCausalRunError("import_origin_attestation")
    multiroot_sha256 = _file_sha256(multiroot_path)
    if multiroot_sha256 != _sha(
        args.expected_multiroot_runner_sha256,
        "multiroot runner",
    ):
        raise SingleRootCausalRunError("multiroot_runner_attestation")
    inherited = multiroot._readiness(
        argparse.Namespace(
            context_plan=args.context_plan,
            context_catalog=args.context_catalog,
            base_model=args.base_model,
            base_fit_summary=args.base_fit_summary,
            candidate_model=args.candidate_model,
            candidate_fit_summary=args.candidate_fit_summary,
            fit_result_receipt=args.fit_result_receipt,
            prior_campaign=args.prior_campaign,
            expected_prior_campaign_sha256=args.expected_prior_campaign_sha256,
            expected_fit_result_receipt_sha256=(args.expected_fit_result_receipt_sha256),
            expected_source_commit=args.expected_source_commit,
            expected_source_bundle_sha256=args.expected_source_bundle_sha256,
            expected_runner_sha256=args.expected_multiroot_runner_sha256,
            expected_paired_runner_sha256=args.expected_paired_runner_sha256,
            expected_development_runner_sha256=(args.expected_development_runner_sha256),
            expected_runtime_sha256=args.expected_runtime_sha256,
            expected_numpy_runtime_sha256=args.expected_numpy_runtime_sha256,
            expected_skill_manifest_sha256=args.expected_skill_manifest_sha256,
            expected_context_plan_sha256=args.expected_context_plan_sha256,
            rom=args.rom,
        )
    )
    return _Readiness(
        paired=inherited.paired,
        runner_sha256=runner_sha256,
        multiroot_runner_sha256=multiroot_sha256,
    )


def _freeze(readiness: _Readiness, destination: Path, private_root: Path) -> dict[str, object]:
    base = readiness.paired.development
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        if not root_claim_is_available(registry, LANE_CONSUMPTION_SHA256):
            raise SingleRootCausalRunError("lane_already_consumed")
    destination = development._new_external_file(destination, rom_path=base.rom_path)
    _store, private_root_identity = development._open_bound_private_root(
        private_root,
        rom_path=base.rom_path,
    )
    root = _at_stage(
        "action_free_root_inventory",
        lambda: _select_unused_acquisition_root(readiness),
    )
    root_record = development._private_root_record(root)
    root_payload = {
        "partition": "train",
        "root_consumption_sha256": root_consumption_sha256(
            state_sha256=root.capture.state_sha256,
            envelope_sha256=root.capture.envelope_sha256,
        ),
        "root": root_record,
    }
    trial = {
        "maximum_decisions": 1,
        "partition": "train",
        "root_index": 0,
        "seed": TRIAL_SEED,
        "trial_index": 0,
    }
    identity = {
        "base_model_canonical_sha256": readiness.paired.candidate_model_canonical_sha256,
        "context_plan_sha256": base.context_plan_sha256,
        "lane_consumption_sha256": LANE_CONSUMPTION_SHA256,
        "numpy_runtime_sha256": base.numpy_runtime_sha256,
        "outcome_objective": development.goal_manager_development_outcome_objective(),
        "private_root_identity_sha256": private_root_identity,
        "prior_campaign_sha256": list(readiness.paired.prior_campaign_sha256),
        "roots": [root_payload],
        "runner_sha256": readiness.runner_sha256,
        "runtime_sha256": base.runtime.sha256,
        "schema": CAMPAIGN_SCHEMA,
        "skill_manifest_sha256": base.skill_manifest_sha256,
        "source_bundle_sha256": base.source_bundle_sha256,
        "source_commit": base.source.git_commit,
        "trials": [trial],
    }
    campaign_id = canonical_sha256(identity)
    plan = {
        **identity,
        "campaign_id": campaign_id,
        "campaign_consumption_sha256": canonical_sha256(
            {"campaign_id": campaign_id, "schema": CAMPAIGN_CONSUMPTION_SCHEMA}
        ),
        "trials": [
            {
                **trial,
                "episode_id": f"red-causal-goal-{campaign_id[:32]}-00",
                "trial_claim_sha256": canonical_sha256(
                    {
                        "campaign_id": campaign_id,
                        "schema": TRIAL_CLAIM_SCHEMA,
                        "trial_index": 0,
                    }
                ),
            }
        ],
    }
    try:
        development._write_exclusive(destination, _canonical_line(plan))
    except Exception as error:
        raise SingleRootCausalRunError("campaign_freeze_write") from error
    return {
        "schema": "pokemon.red.single-root-causal-goal-outcome-freeze.v1",
        "status": "one_train_root_frozen_without_prediction_or_action",
        "campaign_plan_sha256": hashlib.sha256(_canonical_line(plan)).hexdigest(),
        "root_focus_kind": GoalKind.ACQUIRE_SPECIES.value,
        "choice_policy": "full_admitted_menu",
        "lane_consumption_sha256": LANE_CONSUMPTION_SHA256,
        "train_roots": 1,
        "planned_trials": 1,
        "maximum_decisions": 1,
        "claims_consumed": 0,
        "model_predictions": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "development_labels_opened": 0,
        "causal_train_examples_added": 0,
        "model_fits": 0,
        "private_path_fields": 0,
    }


def _select_unused_acquisition_root(readiness: _Readiness) -> development._Root:
    base = readiness.paired.development
    entry_index, entry, assignment, prior_state_envelope = _first_static_root_candidate(readiness)
    inspected = development._inspect_root(
        base,
        entry,
        entry_index=entry_index,
        ordering_assignment_id=assignment.assignment_id,
    )
    if not _inspected_root_is_eligible(inspected, prior_state_envelope):
        raise SingleRootCausalRunError("action_free_root_inventory")
    return cast(development._Root, inspected)


def _first_static_root_candidate(
    readiness: _Readiness,
) -> tuple[int, Any, Any, set[tuple[str, str]]]:
    base = readiness.paired.development
    registry = open_fixed_account_claim_registry()
    prior_lineages, prior_state_envelope = multiroot._prior_root_identities(
        readiness.paired.prior_campaigns
    )
    for entry_index, entry in enumerate(base.entries):
        assignment = base.candidate.registry.assignment(entry.slot_id)
        if (
            assignment.partition != "train"
            or assignment.focus_kind is not GoalKind.ACQUIRE_SPECIES
            or assignment.root_lineage_id in prior_lineages
            or not development._historical_root_is_open(base, entry, registry)
        ):
            continue
        return entry_index, entry, assignment, prior_state_envelope
    raise SingleRootCausalRunError("action_free_root_inventory")


def _inspected_root_is_eligible(
    inspected: development._Root | None,
    prior_state_envelope: set[tuple[str, str]],
) -> bool:
    if inspected is None:
        return False
    physical = (inspected.capture.state_sha256, inspected.capture.envelope_sha256)
    return not (
        physical in prior_state_envelope
        or GoalKind.ACQUIRE_SPECIES.value not in inspected.available_goal_kinds
        or len(inspected.available_goal_kinds) < 2
        or GoalKind.EVOLVE_SPECIES.value in inspected.available_goal_kinds
    )


def _qualify(
    readiness: _Readiness,
    campaign_path: Path,
    private_root: Path,
    *,
    expected_campaign_sha256: str,
    require_unclaimed: bool,
) -> multiroot._QualifiedCampaign:
    base = readiness.paired.development
    store, private_root_identity = development._open_bound_private_root(
        private_root,
        rom_path=base.rom_path,
    )
    path = development._external_regular(campaign_path, rom_path=base.rom_path)
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_campaign_sha256:
        raise SingleRootCausalRunError("campaign_attestation")
    plan = development._canonical_document(payload, subject="causal goal campaign")
    _validate_plan(readiness, plan, private_root_identity=private_root_identity)
    root_record = _mapping(_root_records(plan)[0].get("root"), "root")
    inspected = _reconstruct_plan_root(
        readiness,
        root_record,
        require_unclaimed=require_unclaimed,
    )
    qualified = multiroot._QualifiedCampaign(
        plan=plan,
        plan_sha256=digest,
        plan_path=path,
        roots=(inspected,),
        store=store,
    )
    if require_unclaimed:
        registry = open_fixed_account_claim_registry()
        with fixed_account_claim_registry_lease(registry, exclusive=False):
            claims = (
                _sha(plan.get("lane_consumption_sha256"), "lane consumption"),
                _sha(plan.get("campaign_consumption_sha256"), "campaign consumption"),
                _sha(
                    _root_records(plan)[0].get("root_consumption_sha256"),
                    "root consumption",
                ),
            )
            trial = _trials(plan)[0]
            if (
                any(not root_claim_is_available(registry, claim) for claim in claims)
                or store.inspect_episode_state(_text(trial.get("episode_id"), "episode")).status
                != "absent"
                or not development._trial_claim_is_available(
                    registry,
                    _sha(trial.get("trial_claim_sha256"), "trial claim"),
                )
            ):
                raise SingleRootCausalRunError("campaign_already_consumed")
    return qualified


def _reconstruct_plan_root(
    readiness: _Readiness,
    root_record: Mapping[str, object],
    *,
    require_unclaimed: bool,
) -> development._Root:
    base = readiness.paired.development
    entry_index = _integer(root_record.get("entry_index"), "entry index")
    if entry_index >= len(base.entries):
        raise SingleRootCausalRunError("root_attestation")
    prior_state_envelope = multiroot._prior_root_identities(readiness.paired.prior_campaigns)[1]
    if require_unclaimed:
        expected_index, entry, assignment, prior_state_envelope = _first_static_root_candidate(
            readiness
        )
        if entry_index != expected_index:
            raise SingleRootCausalRunError("root_selection_authentication")
    else:
        entry = base.entries[entry_index]
        assignment = base.candidate.registry.assignment(entry.slot_id)
    inspected = development._inspect_root(
        base,
        entry,
        entry_index=entry_index,
        ordering_assignment_id=assignment.assignment_id,
    )
    if (
        not _inspected_root_is_eligible(inspected, prior_state_envelope)
        or inspected is None
        or inspected.assignment.partition != "train"
        or inspected.assignment.focus_kind is not GoalKind.ACQUIRE_SPECIES
        or development._private_root_record(inspected) != root_record
    ):
        raise SingleRootCausalRunError("root_drift")
    return inspected


def _preflight(
    readiness: _Readiness,
    qualified: multiroot._QualifiedCampaign,
) -> dict[str, object]:
    return {
        "schema": "pokemon.red.single-root-causal-goal-outcome-preflight.v1",
        "status": "ready_without_prediction_or_action",
        "campaign_plan_sha256": qualified.plan_sha256,
        "source_commit": readiness.paired.development.source.git_commit,
        "runner_sha256": readiness.runner_sha256,
        "root_focus_kind": GoalKind.ACQUIRE_SPECIES.value,
        "choice_policy": "full_admitted_menu",
        "lane_consumption_sha256": LANE_CONSUMPTION_SHA256,
        "train_roots": 1,
        "planned_trials": 1,
        "maximum_decisions": 1,
        "claims_consumed": 0,
        "model_predictions": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "development_labels_opened": 0,
        "causal_train_examples_added": 0,
        "model_fits": 0,
        "private_path_fields": 0,
    }


def _execute(
    readiness: _Readiness,
    qualified: multiroot._QualifiedCampaign,
) -> dict[str, object]:
    base = readiness.paired.development
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        if not root_claim_is_available(registry, LANE_CONSUMPTION_SHA256):
            raise SingleRootCausalRunError("lane_already_consumed")
        write_root_claim(
            registry,
            root_consumption_sha256=LANE_CONSUMPTION_SHA256,
            execution_identity_sha256=multiroot._campaign_execution_identity(
                _execution_readiness(readiness),
                qualified,
            ),
            source_commit=base.source.git_commit or "",
            runner_sha256=readiness.runner_sha256,
        )
    inherited = multiroot._execute(_execution_readiness(readiness), qualified, resume=False)
    trials = inherited.get("trials")
    if not isinstance(trials, list) or len(trials) != 1 or not isinstance(trials[0], Mapping):
        raise SingleRootCausalRunError("execution_summary_authentication")
    row = dict(cast(Mapping[str, object], trials[0]))
    if row.get("failure_stage") == "unexpected_failure":
        row["failure_stage"] = "development_execution"
    return {
        "schema": "pokemon.red.single-root-causal-goal-outcome-execution.v1",
        "status": "single_trial_consumed_pending_strict_admission",
        "campaign_plan_sha256": qualified.plan_sha256,
        "campaign_terminal_sha256": inherited.get("campaign_terminal_sha256"),
        "trial": row,
        "complete_trials": inherited.get("complete_trials"),
        "failed_trials": inherited.get("failed_trials"),
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "development_labels_opened": 0,
        "causal_train_examples_added": 0,
        "model_fits": 0,
        "private_path_fields": 0,
    }


def _admit(
    readiness: _Readiness,
    qualified: multiroot._QualifiedCampaign,
) -> dict[str, object]:
    registry = open_fixed_account_claim_registry()
    if root_claim_is_available(registry, LANE_CONSUMPTION_SHA256):
        raise SingleRootCausalRunError("lane_claim_authentication")
    inherited_readiness = _execution_readiness(readiness)
    if read_root_claim(registry, LANE_CONSUMPTION_SHA256) != _expected_lane_claim(
        readiness,
        qualified,
    ):
        raise SingleRootCausalRunError("lane_claim_authentication")
    multiroot._require_campaign_terminal(inherited_readiness, qualified, registry)
    episodes, invalid = multiroot._load_partition(
        inherited_readiness,
        qualified,
        partition="train",
    )
    if len(episodes) > 1 or sum(invalid.values()) + len(episodes) != 1:
        raise SingleRootCausalRunError("outcome_denominator_authentication")
    admitted = episodes[0] if episodes else None
    causal_train_examples = (
        1
        if admitted is not None and len(admitted.targets) == 1 and admitted.verified_outcomes == 1
        else 0
    )
    attested_atomic_episode = 1 if admitted is not None and admitted.verified_outcomes == 1 else 0
    return {
        "schema": "pokemon.red.single-root-causal-goal-outcome-admission.v1",
        "status": (
            "single_train_outcome_admitted"
            if causal_train_examples == 1
            else "single_train_trial_retained_without_settled_target"
        ),
        "campaign_plan_sha256": qualified.plan_sha256,
        "planned_trials": 1,
        "complete_episodes": len(episodes),
        "invalid_trials": sum(invalid.values()),
        "invalid_trial_states": invalid,
        "verified_outcomes": 0 if admitted is None else admitted.verified_outcomes,
        "claimed_train_roots": 1,
        "causal_train_attempts": attested_atomic_episode,
        "invalid_trial_controller_start_status": (
            "not_applicable" if attested_atomic_episode == 1 else "not_attested"
        ),
        "atomic_goal_episodes_added": attested_atomic_episode,
        "collection_relevant_selections": (
            0 if admitted is None else admitted.collection_relevant_outcomes
        ),
        "successful_retained_acquisitions": (
            0 if admitted is None else admitted.successful_retained_acquisitions
        ),
        "causal_train_examples_added": causal_train_examples,
        "development_episode_attempts_added": 0,
        "verified_outcome_examples_added": 0,
        "teacher_queries": 0,
        "teacher_fallbacks": 0,
        "development_labels_opened": 0,
        "model_fits_added": 0,
        "unseen_comparisons_added": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "private_path_fields": 0,
    }


def _expected_lane_claim(
    readiness: _Readiness,
    qualified: multiroot._QualifiedCampaign,
) -> dict[str, str]:
    return {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": LANE_CONSUMPTION_SHA256,
        "execution_identity_sha256": multiroot._campaign_execution_identity(
            _execution_readiness(readiness),
            qualified,
        ),
        "source_commit": readiness.paired.development.source.git_commit or "",
        "runner_sha256": readiness.runner_sha256,
    }


def _execution_readiness(readiness: _Readiness) -> multiroot._Readiness:
    """Present this runner's identity to the inherited generic execution machinery."""

    return multiroot._Readiness(
        paired=readiness.paired,
        runner_sha256=readiness.runner_sha256,
    )


def _validate_plan(
    readiness: _Readiness,
    plan: Mapping[str, object],
    *,
    private_root_identity: str,
) -> None:
    base = readiness.paired.development
    if (
        set(plan)
        != {
            "base_model_canonical_sha256",
            "campaign_consumption_sha256",
            "campaign_id",
            "context_plan_sha256",
            "lane_consumption_sha256",
            "numpy_runtime_sha256",
            "outcome_objective",
            "prior_campaign_sha256",
            "private_root_identity_sha256",
            "roots",
            "runner_sha256",
            "runtime_sha256",
            "schema",
            "skill_manifest_sha256",
            "source_bundle_sha256",
            "source_commit",
            "trials",
        }
        or plan.get("schema") != CAMPAIGN_SCHEMA
        or plan.get("source_commit") != base.source.git_commit
        or plan.get("source_bundle_sha256") != base.source_bundle_sha256
        or plan.get("runner_sha256") != readiness.runner_sha256
        or plan.get("runtime_sha256") != base.runtime.sha256
        or plan.get("numpy_runtime_sha256") != base.numpy_runtime_sha256
        or plan.get("skill_manifest_sha256") != base.skill_manifest_sha256
        or plan.get("context_plan_sha256") != base.context_plan_sha256
        or plan.get("lane_consumption_sha256") != LANE_CONSUMPTION_SHA256
        or plan.get("private_root_identity_sha256") != private_root_identity
        or plan.get("prior_campaign_sha256") != list(readiness.paired.prior_campaign_sha256)
        or plan.get("base_model_canonical_sha256")
        != readiness.paired.candidate_model_canonical_sha256
        or plan.get("outcome_objective") != development.goal_manager_development_outcome_objective()
    ):
        raise SingleRootCausalRunError("campaign_authentication")
    roots = _root_records(plan)
    trials = _trials(plan)
    if len(roots) != 1 or len(trials) != 1:
        raise SingleRootCausalRunError("campaign_layout")
    root_payload = roots[0]
    if set(root_payload) != {"partition", "root", "root_consumption_sha256"}:
        raise SingleRootCausalRunError("campaign_layout")
    root = _mapping(root_payload.get("root"), "root")
    state = _sha(root.get("state_sha256"), "state")
    envelope = _sha(root.get("envelope_sha256"), "envelope")
    if (
        root_payload.get("partition") != "train"
        or root.get("focus_kind") != GoalKind.ACQUIRE_SPECIES.value
        or root_payload.get("root_consumption_sha256")
        != root_consumption_sha256(state_sha256=state, envelope_sha256=envelope)
    ):
        raise SingleRootCausalRunError("campaign_layout")
    campaign_id = _sha(plan.get("campaign_id"), "campaign")
    trial = trials[0]
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
        or trial.get("trial_index") != 0
        or trial.get("root_index") != 0
        or trial.get("partition") != "train"
        or trial.get("maximum_decisions") != 1
        or trial.get("seed") != TRIAL_SEED
        or trial.get("episode_id") != f"red-causal-goal-{campaign_id[:32]}-00"
        or trial.get("trial_claim_sha256")
        != canonical_sha256(
            {
                "campaign_id": campaign_id,
                "schema": TRIAL_CLAIM_SCHEMA,
                "trial_index": 0,
            }
        )
    ):
        raise SingleRootCausalRunError("campaign_layout")
    identity = dict(plan)
    identity.pop("campaign_id")
    identity.pop("campaign_consumption_sha256")
    stripped = dict(trial)
    stripped.pop("episode_id")
    stripped.pop("trial_claim_sha256")
    identity["trials"] = [stripped]
    if canonical_sha256(identity) != campaign_id or plan.get(
        "campaign_consumption_sha256"
    ) != canonical_sha256({"campaign_id": campaign_id, "schema": CAMPAIGN_CONSUMPTION_SCHEMA}):
        raise SingleRootCausalRunError("campaign_authentication")


def _root_records(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("roots")
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise SingleRootCausalRunError("campaign_layout")
    return tuple(cast(Mapping[str, object], item) for item in value)


def _trials(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("trials")
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise SingleRootCausalRunError("campaign_layout")
    return tuple(cast(Mapping[str, object], item) for item in value)


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SingleRootCausalRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise SingleRootCausalRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise SingleRootCausalRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise SingleRootCausalRunError(f"{subject.replace(' ', '_')}_authentication")
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


def _failure_stage(error: Exception, *, default: str) -> str:
    if isinstance(error, SingleRootCausalRunError):
        return error.stage
    candidate = getattr(error, "stage", None)
    if isinstance(candidate, str) and _SAFE_STAGE.fullmatch(candidate) is not None:
        return candidate
    if _SAFE_STAGE.fullmatch(default) is not None:
        return default
    return "unexpected_failure"


if __name__ == "__main__":
    raise SystemExit(main())
