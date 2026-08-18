#!/usr/bin/env python3
# mypy: disable-error-code=attr-defined
"""Collect one authenticated train-only Red team-development causal outcome."""

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
from typing import Any, Never, TypeVar, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import freeze_causal_execution_manifest as manifest_freezer
import public_execution_manifest as public_manifest
import run_repeatable_goal_manager_development as development
import run_resettable_goal_manager_multiroot_campaign as multiroot

from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    root_consumption_sha256,
    write_root_claim,
)
from pokemon_red_completion.provenance import canonical_sha256

CAMPAIGN_SCHEMA = "pokemon.red.develop-team-causal-goal-outcome-campaign.v1"
TRIAL_CLAIM_SCHEMA = "pokemon.red.develop-team-causal-goal-outcome-trial-claim.v1"
CAMPAIGN_CONSUMPTION_SCHEMA = "pokemon.red.develop-team-causal-goal-outcome-campaign-consumption.v1"
LANE_ID = "first-develop-team-causal-goal-outcome-v1"
LANE_CONSUMPTION_SCHEMA = "pokemon.red.develop-team-causal-goal-outcome-lane-consumption.v1"
LANE_CONSUMPTION_SHA256 = canonical_sha256({"lane_id": LANE_ID, "schema": LANE_CONSUMPTION_SCHEMA})
RUNNER_RELATIVE = "scripts/run_develop_team_causal_goal_outcome.py"
PUBLIC_DEPENDENCIES = (
    "development_runner=scripts/run_repeatable_goal_manager_development.py",
    "multiroot_runner=scripts/run_resettable_goal_manager_multiroot_campaign.py",
    "paired_runner=scripts/run_paired_goal_manager_outcome_screen.py",
    "public_manifest=scripts/public_execution_manifest.py",
)
TRIAL_SEED = 41_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_STAGE = re.compile(r"[a-z0-9_]+\Z")
_T = TypeVar("_T")


class DevelopTeamCausalRunError(RuntimeError):
    """A sanitized failure at one team-development causal stage."""

    def __init__(self, stage: str) -> None:
        self.stage = stage if _SAFE_STAGE.fullmatch(stage) is not None else "develop_team_execution"
        super().__init__(self.stage)


class _SanitizedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise DevelopTeamCausalRunError("argument_authentication")


@dataclass(frozen=True, slots=True)
class _PublicGate:
    bindings: Mapping[str, str]
    manifest_sha256: str
    freeze_manifest_sha256: str | None


@dataclass(frozen=True, slots=True)
class _Readiness:
    paired: Any
    runner_sha256: str


def _parser() -> argparse.ArgumentParser:
    parser = _SanitizedArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("freeze", "preflight", "execute", "admit"),
        required=True,
    )
    parser.add_argument("--execution-manifest", type=Path, required=True)
    parser.add_argument("--expected-execution-manifest-sha256", required=True)
    parser.add_argument("--expected-freeze-execution-manifest-sha256")
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
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--campaign-plan", type=Path, required=True)
    parser.add_argument("--expected-campaign-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        gate = _at_stage("public_manifest_authentication", lambda: _public_gate(args))
        readiness = _at_stage("readiness_authentication", lambda: _readiness(args, gate))
        if args.mode == "freeze":
            if args.expected_campaign_sha256 is not None:
                raise DevelopTeamCausalRunError("campaign_authentication")
            result = _at_stage(
                "action_free_develop_team_root_inventory",
                lambda: _freeze(readiness, gate, args.campaign_plan, args.private_root),
            )
        else:
            expected = _sha(args.expected_campaign_sha256, "campaign")
            qualified = _at_stage(
                "campaign_authentication",
                lambda: _qualify(
                    readiness,
                    gate,
                    args.campaign_plan,
                    args.private_root,
                    expected_campaign_sha256=expected,
                    require_unclaimed=args.mode in {"preflight", "execute"},
                ),
            )
            if args.mode == "preflight":
                result = _at_stage(
                    "preflight_authentication",
                    lambda: _preflight(readiness, gate, qualified),
                )
            elif args.mode == "execute":
                result = _at_stage(
                    "develop_team_execution",
                    lambda: _execute(readiness, gate, qualified),
                )
            else:
                result = _at_stage(
                    "train_outcome_admission",
                    lambda: _admit(readiness, gate, qualified),
                )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as error:
        print(
            json.dumps(
                {
                    "schema": "pokemon.red.develop-team-causal-goal-outcome-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": _failure_stage(error, default="develop_team_execution"),
                    "effects": "not_attested_on_failure",
                    "development_labels_opened": 0,
                    "model_fits": 0,
                    "teacher_queries": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _public_gate(args: argparse.Namespace) -> _PublicGate:
    _require_script_module(manifest_freezer, "freeze_causal_execution_manifest.py")
    _require_script_module(public_manifest, "public_execution_manifest.py")
    bindings = manifest_freezer._current_public_bindings(
        lane_id=LANE_ID,
        runner=RUNNER_RELATIVE,
        dependencies=list(PUBLIC_DEPENDENCIES),
    )
    invocation = public_manifest.public_execution_invocation(
        lane_id=LANE_ID,
        operation=args.mode,
        expected_campaign_sha256=args.expected_campaign_sha256,
        expected_freeze_execution_manifest_sha256=(args.expected_freeze_execution_manifest_sha256),
        expected_context_plan_sha256=args.expected_context_plan_sha256,
        expected_fit_result_receipt_sha256=args.expected_fit_result_receipt_sha256,
        expected_prior_campaign_sha256=args.expected_prior_campaign_sha256,
        public_bindings=bindings,
        private_input_roles=manifest_freezer.PRIVATE_INPUT_ROLES,
    )
    payload = public_manifest.read_public_manifest(
        args.execution_manifest,
        repository_root=PROJECT_ROOT,
    )
    expected = _sha(args.expected_execution_manifest_sha256, "execution manifest")
    public_manifest.authenticate_public_execution_manifest(
        payload,
        expected_manifest_sha256=expected,
        invocation=invocation,
        current_public_bindings=bindings,
    )
    return _PublicGate(
        bindings=bindings,
        manifest_sha256=expected,
        freeze_manifest_sha256=args.expected_freeze_execution_manifest_sha256,
    )


def _require_script_module(module: object, filename: str) -> None:
    source = getattr(module, "__file__", None)
    expected = (SCRIPTS_ROOT / filename).resolve(strict=True)
    if not isinstance(source, str) or Path(source).resolve(strict=True) != expected:
        raise DevelopTeamCausalRunError("public_manifest_authentication")


def _readiness(args: argparse.Namespace, gate: _PublicGate) -> _Readiness:
    bindings = gate.bindings
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
            expected_fit_result_receipt_sha256=args.expected_fit_result_receipt_sha256,
            expected_source_commit=_binding(bindings, "source_commit"),
            expected_source_bundle_sha256=_binding(bindings, "source_bundle_sha256"),
            expected_runner_sha256=_binding(bindings, "multiroot_runner_sha256"),
            expected_paired_runner_sha256=_binding(bindings, "paired_runner_sha256"),
            expected_development_runner_sha256=_binding(bindings, "development_runner_sha256"),
            expected_runtime_sha256=_binding(bindings, "runtime_sha256"),
            expected_numpy_runtime_sha256=_binding(bindings, "numpy_runtime_sha256"),
            expected_skill_manifest_sha256=_binding(bindings, "skill_manifest_sha256"),
            expected_context_plan_sha256=args.expected_context_plan_sha256,
            rom=args.rom,
        )
    )
    return _Readiness(
        paired=inherited.paired,
        runner_sha256=_binding(bindings, "runner_sha256"),
    )


def _freeze(
    readiness: _Readiness,
    gate: _PublicGate,
    destination: Path,
    private_root: Path,
) -> dict[str, object]:
    base = readiness.paired.development
    destination = development._new_external_file(destination, rom_path=base.rom_path)
    _store, private_root_identity = development._open_bound_private_root(
        private_root,
        rom_path=base.rom_path,
    )
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        if not root_claim_is_available(registry, LANE_CONSUMPTION_SHA256):
            raise DevelopTeamCausalRunError("lane_already_consumed")
        root = _select_first_develop_team_root(readiness, registry)
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
        "freeze_execution_manifest_sha256": gate.manifest_sha256,
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
                "episode_id": f"red-develop-team-causal-{campaign_id[:32]}-00",
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
        raise DevelopTeamCausalRunError("campaign_freeze_write") from error
    return _zero_result(
        schema="pokemon.red.develop-team-causal-goal-outcome-freeze.v1",
        status="one_train_develop_team_root_frozen_without_prediction_or_action",
        gate=gate,
        campaign_plan_sha256=hashlib.sha256(_canonical_line(plan)).hexdigest(),
    )


def _select_first_develop_team_root(
    readiness: _Readiness,
    registry: Path,
) -> development._Root:
    entry_index, entry, assignment, prior_state_envelope = _first_static_candidate(
        readiness,
        registry,
    )
    inspected = development._inspect_root(
        readiness.paired.development,
        entry,
        entry_index=entry_index,
        ordering_assignment_id=assignment.assignment_id,
    )
    if not _root_is_eligible(inspected, prior_state_envelope):
        raise DevelopTeamCausalRunError("action_free_develop_team_root_inventory")
    return cast(development._Root, inspected)


def _first_static_candidate(
    readiness: _Readiness,
    registry: Path,
) -> tuple[int, Any, Any, set[tuple[str, str]]]:
    base = readiness.paired.development
    prior_lineages, prior_state_envelope = multiroot._prior_root_identities(
        readiness.paired.prior_campaigns
    )
    for entry_index, entry in enumerate(base.entries):
        assignment = base.candidate.registry.assignment(entry.slot_id)
        if (
            assignment.partition == "train"
            and assignment.focus_kind is GoalKind.DEVELOP_TEAM
            and assignment.root_lineage_id not in prior_lineages
            and development._historical_root_is_open(base, entry, registry)
        ):
            return entry_index, entry, assignment, prior_state_envelope
    raise DevelopTeamCausalRunError("action_free_develop_team_root_inventory")


def _root_is_eligible(
    inspected: development._Root | None,
    prior_state_envelope: set[tuple[str, str]],
) -> bool:
    if inspected is None:
        return False
    physical = (inspected.capture.state_sha256, inspected.capture.envelope_sha256)
    return bool(
        inspected.assignment.partition == "train"
        and inspected.assignment.focus_kind is GoalKind.DEVELOP_TEAM
        and physical not in prior_state_envelope
        and GoalKind.DEVELOP_TEAM.value in inspected.available_goal_kinds
        and len(inspected.available_goal_kinds) >= 2
        and GoalKind.EVOLVE_SPECIES.value not in inspected.available_goal_kinds
    )


def _qualify(
    readiness: _Readiness,
    gate: _PublicGate,
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
        raise DevelopTeamCausalRunError("campaign_authentication")
    plan = development._canonical_document(payload, subject="develop team causal campaign")
    _validate_plan(
        readiness,
        plan,
        private_root_identity=private_root_identity,
        expected_freeze_execution_manifest_sha256=_sha(
            gate.freeze_manifest_sha256,
            "freeze execution manifest",
        ),
    )
    root_record = _mapping(_root_records(plan)[0].get("root"), "root")
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        inspected = _reconstruct_plan_root(
            readiness,
            root_record,
            registry=registry,
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
            claims = (
                LANE_CONSUMPTION_SHA256,
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
                raise DevelopTeamCausalRunError("campaign_already_consumed")
    return qualified


def _reconstruct_plan_root(
    readiness: _Readiness,
    root_record: Mapping[str, object],
    *,
    registry: Path,
    require_unclaimed: bool,
) -> development._Root:
    base = readiness.paired.development
    entry_index = _integer(root_record.get("entry_index"), "entry index")
    if entry_index >= len(base.entries):
        raise DevelopTeamCausalRunError("root_authentication")
    prior_state = multiroot._prior_root_identities(readiness.paired.prior_campaigns)[1]
    if require_unclaimed:
        expected_index, entry, assignment, prior_state = _first_static_candidate(
            readiness,
            registry,
        )
        if entry_index != expected_index:
            raise DevelopTeamCausalRunError("root_selection_authentication")
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
        not _root_is_eligible(inspected, prior_state)
        or inspected is None
        or development._private_root_record(inspected) != root_record
    ):
        raise DevelopTeamCausalRunError("root_drift")
    return inspected


def _preflight(
    readiness: _Readiness,
    gate: _PublicGate,
    qualified: multiroot._QualifiedCampaign,
) -> dict[str, object]:
    return _zero_result(
        schema="pokemon.red.develop-team-causal-goal-outcome-preflight.v1",
        status="ready_without_prediction_or_action",
        gate=gate,
        campaign_plan_sha256=qualified.plan_sha256,
    )


def _execute(
    readiness: _Readiness,
    gate: _PublicGate,
    qualified: multiroot._QualifiedCampaign,
) -> dict[str, object]:
    base = readiness.paired.development
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        if not root_claim_is_available(registry, LANE_CONSUMPTION_SHA256):
            raise DevelopTeamCausalRunError("lane_already_consumed")
        try:
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
        except Exception as error:
            raise DevelopTeamCausalRunError("lane_claim_before_prediction") from error
    inherited = multiroot._execute(_execution_readiness(readiness), qualified, resume=False)
    trials = inherited.get("trials")
    if not isinstance(trials, list) or len(trials) != 1 or not isinstance(trials[0], Mapping):
        raise DevelopTeamCausalRunError("execution_summary_authentication")
    row = dict(cast(Mapping[str, object], trials[0]))
    if row.get("failure_stage") == "unexpected_failure":
        row["failure_stage"] = "develop_team_execution"
    return {
        "schema": "pokemon.red.develop-team-causal-goal-outcome-execution.v1",
        "status": "single_trial_consumed_pending_strict_admission",
        "campaign_plan_sha256": qualified.plan_sha256,
        "execution_manifest_sha256": gate.manifest_sha256,
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
    gate: _PublicGate,
    qualified: multiroot._QualifiedCampaign,
) -> dict[str, object]:
    registry = open_fixed_account_claim_registry()
    if root_claim_is_available(registry, LANE_CONSUMPTION_SHA256):
        raise DevelopTeamCausalRunError("lane_claim_authentication")
    if read_root_claim(registry, LANE_CONSUMPTION_SHA256) != _expected_lane_claim(
        readiness,
        qualified,
    ):
        raise DevelopTeamCausalRunError("lane_claim_authentication")
    inherited = _execution_readiness(readiness)
    try:
        multiroot._require_campaign_terminal(inherited, qualified, registry)
    except Exception as error:
        raise DevelopTeamCausalRunError("campaign_terminal_authentication") from error
    episodes, invalid = multiroot._load_partition(inherited, qualified, partition="train")
    if len(episodes) > 1 or sum(invalid.values()) + len(episodes) != 1:
        raise DevelopTeamCausalRunError("train_outcome_admission")
    admitted = episodes[0] if episodes else None
    positive = 0
    negative = 0
    selected_goal_kind: str | None = None
    if admitted is not None:
        if admitted.verified_outcomes != 1 or len(admitted.dataset.examples) != 1:
            raise DevelopTeamCausalRunError("train_outcome_admission")
        example = admitted.dataset.examples[0]
        if not isinstance(example.selected_kind, GoalKind):
            raise DevelopTeamCausalRunError("train_outcome_admission")
        selected_goal_kind = example.selected_kind.value
        if example.outcome_status is GoalDecisionOutcome.INTERRUPTED:
            if admitted.targets:
                raise DevelopTeamCausalRunError("train_outcome_admission")
        else:
            if len(admitted.targets) != 1:
                raise DevelopTeamCausalRunError("train_outcome_admission")
            target = admitted.targets[0]
            expected_reward = (
                1.0 if example.outcome_status is GoalDecisionOutcome.SUCCEEDED else -1.0
            )
            if (
                example.outcome_status
                not in {GoalDecisionOutcome.SUCCEEDED, GoalDecisionOutcome.FAILED}
                or target.selected_candidate_index != example.selected_candidate_index
                or target.reward != expected_reward
            ):
                raise DevelopTeamCausalRunError("train_outcome_admission")
            positive = int(expected_reward == 1.0)
            negative = int(expected_reward == -1.0)
    causal = positive + negative
    return {
        "schema": "pokemon.red.develop-team-causal-goal-outcome-admission.v1",
        "status": (
            "single_train_causal_outcome_admitted_from_develop_team_focused_root"
            if causal == 1
            else "single_train_trial_retained_without_settled_target"
        ),
        "campaign_plan_sha256": qualified.plan_sha256,
        "execution_manifest_sha256": gate.manifest_sha256,
        "planned_trials": 1,
        "complete_episodes": len(episodes),
        "invalid_trials": sum(invalid.values()),
        "invalid_trial_states": invalid,
        "claimed_train_roots": 1,
        "settled_positive_examples_added": positive,
        "settled_negative_examples_added": negative,
        "selected_goal_kind": selected_goal_kind,
        "causal_train_examples_added": causal,
        "atomic_goal_episodes_added": causal,
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


def _zero_result(
    *,
    schema: str,
    status: str,
    gate: _PublicGate,
    campaign_plan_sha256: str,
) -> dict[str, object]:
    return {
        "schema": schema,
        "status": status,
        "campaign_plan_sha256": campaign_plan_sha256,
        "execution_manifest_sha256": gate.manifest_sha256,
        "root_focus_kind": GoalKind.DEVELOP_TEAM.value,
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
        "atomic_goal_episodes_added": 0,
        "model_fits": 0,
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
    return multiroot._Readiness(paired=readiness.paired, runner_sha256=readiness.runner_sha256)


def _validate_plan(
    readiness: _Readiness,
    plan: Mapping[str, object],
    *,
    private_root_identity: str,
    expected_freeze_execution_manifest_sha256: str,
) -> None:
    base = readiness.paired.development
    expected_keys = {
        "base_model_canonical_sha256",
        "campaign_consumption_sha256",
        "campaign_id",
        "context_plan_sha256",
        "freeze_execution_manifest_sha256",
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
    if (
        set(plan) != expected_keys
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
        raise DevelopTeamCausalRunError("campaign_authentication")
    if (
        _sha(plan.get("freeze_execution_manifest_sha256"), "freeze execution manifest")
        != expected_freeze_execution_manifest_sha256
    ):
        raise DevelopTeamCausalRunError("campaign_authentication")
    roots = _root_records(plan)
    trials = _trials(plan)
    if len(roots) != 1 or len(trials) != 1:
        raise DevelopTeamCausalRunError("campaign_layout")
    root_payload = roots[0]
    if set(root_payload) != {"partition", "root", "root_consumption_sha256"}:
        raise DevelopTeamCausalRunError("campaign_layout")
    root = _mapping(root_payload.get("root"), "root")
    state = _sha(root.get("state_sha256"), "state")
    envelope = _sha(root.get("envelope_sha256"), "envelope")
    if (
        root_payload.get("partition") != "train"
        or root.get("focus_kind") != GoalKind.DEVELOP_TEAM.value
        or root_payload.get("root_consumption_sha256")
        != root_consumption_sha256(state_sha256=state, envelope_sha256=envelope)
    ):
        raise DevelopTeamCausalRunError("campaign_layout")
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
        or trial.get("episode_id") != f"red-develop-team-causal-{campaign_id[:32]}-00"
        or trial.get("trial_claim_sha256")
        != canonical_sha256(
            {"campaign_id": campaign_id, "schema": TRIAL_CLAIM_SCHEMA, "trial_index": 0}
        )
    ):
        raise DevelopTeamCausalRunError("campaign_layout")
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
        raise DevelopTeamCausalRunError("campaign_authentication")


def _root_records(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("roots")
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise DevelopTeamCausalRunError("campaign_layout")
    return tuple(cast(Mapping[str, object], item) for item in value)


def _trials(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("trials")
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise DevelopTeamCausalRunError("campaign_layout")
    return tuple(cast(Mapping[str, object], item) for item in value)


def _at_stage(stage: str, operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except DevelopTeamCausalRunError:
        raise
    except Exception as error:
        raise DevelopTeamCausalRunError(stage) from error


def _binding(bindings: Mapping[str, str], name: str) -> str:
    value = bindings.get(name)
    if not isinstance(value, str):
        raise DevelopTeamCausalRunError("public_manifest_authentication")
    return value


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise DevelopTeamCausalRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise DevelopTeamCausalRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise DevelopTeamCausalRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise DevelopTeamCausalRunError(f"{subject.replace(' ', '_')}_authentication")
    return value


def _canonical_line(value: object) -> bytes:
    return (
        json.dumps(
            value, allow_nan=False, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("ascii")
        + b"\n"
    )


def _failure_stage(error: Exception, *, default: str) -> str:
    if isinstance(error, DevelopTeamCausalRunError):
        return error.stage
    candidate = getattr(error, "stage", None)
    if isinstance(candidate, str) and _SAFE_STAGE.fullmatch(candidate) is not None:
        return candidate
    return default if _SAFE_STAGE.fullmatch(default) is not None else "develop_team_execution"


if __name__ == "__main__":
    raise SystemExit(main())
