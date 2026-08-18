#!/usr/bin/env python3
"""Freeze or preflight one descriptive Red base-versus-candidate screen."""

# ruff: noqa: E402 -- the reviewed development runner pins project imports first

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
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import run_repeatable_goal_manager_development as development

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.goal_manager_composition_qualification import (
    open_fixed_account_claim_registry,
    root_consumption_sha256,
)
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
)
from pokemon_red_completion.goal_manager_protocol import GoalManagerAssignment
from pokemon_red_completion.paired_goal_manager_screen import (
    PAIRED_SCREEN_ARM_ORDER,
    PAIRED_SCREEN_SCHEMA,
    paired_screen_arm_claim,
    paired_screen_behavior_contract,
    paired_screen_endpoint_contract,
    select_development_outcome_unused_acquisition_root,
)
from pokemon_red_completion.provenance import canonical_sha256

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
_FIT_RESULT_SCHEMA = "pokemon.red.repeatable-goal-manager-outcome-fit-result-receipt.v1"
_FIT_SUMMARY_SCHEMA = "pokemon.red.repeatable-goal-manager-outcome-fit-summary.v1"
_SAFE_STAGE = re.compile(r"[a-z0-9_]+\Z")
EXPECTED_PRIOR_CAMPAIGN_SHA256 = (
    "e99075d98cd9f3cd390b290fa336c6fe0ecbeccc6b50a643208a89b12d254d14",
    "452cff2afa25278900334b8c0e69583a0c511e943ef727593fed938653f995b9",
)
_HISTORICAL_CONTEXT_PLAN_BY_CAMPAIGN_SHA256 = {
    "e99075d98cd9f3cd390b290fa336c6fe0ecbeccc6b50a643208a89b12d254d14": (
        "74a89eafd467e44ca41ad262e5ddc40ec22a05f8368aa08487af6d139061a548"
    ),
    "452cff2afa25278900334b8c0e69583a0c511e943ef727593fed938653f995b9": (
        "74a89eafd467e44ca41ad262e5ddc40ec22a05f8368aa08487af6d139061a548"
    ),
}


class PairedScreenRunError(RuntimeError):
    """A path-free failure at one declared paired-screen stage."""


@dataclass(frozen=True, slots=True)
class _Readiness:
    development: development._Readiness
    runner_sha256: str
    candidate_model_path: Path
    candidate_model_file_sha256: str
    candidate_model: GoalManagerLinearModel
    candidate_model_canonical_sha256: str
    fit_result_receipt_sha256: str
    fit_summary_sha256: str
    prior_campaigns: tuple[Mapping[str, object], ...]
    prior_campaign_sha256: tuple[str, ...]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("freeze", "preflight"), required=True)
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
    parser.add_argument("--expected-development-runner-sha256", required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--expected-numpy-runtime-sha256", required=True)
    parser.add_argument("--expected-skill-manifest-sha256", required=True)
    parser.add_argument("--expected-context-plan-sha256", required=True)
    parser.add_argument("--rom", type=Path, default=None, help="otherwise POKEMON_RED_ROM")
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--screen-plan", type=Path, required=True)
    parser.add_argument("--expected-screen-plan-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        readiness = _readiness(args)
        if args.mode == "freeze":
            result = _freeze(readiness, args.screen_plan, args.private_root)
        else:
            if args.expected_screen_plan_sha256 is None:
                raise PairedScreenRunError("screen_plan_attestation")
            result = _preflight(
                readiness,
                args.screen_plan,
                args.private_root,
                expected_screen_plan_sha256=args.expected_screen_plan_sha256,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as error:
        stage = _sanitized_failure_stage(error)
        print(
            json.dumps(
                {
                    "schema": "pokemon.red.paired-goal-manager-screen-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": stage,
                    "model_predictions": 0,
                    "controller_actions": 0,
                    "emulator_frames": 0,
                    "teacher_queries": 0,
                    "model_fits": 0,
                    "authority_promotions": 0,
                    "protected_access_status": "not_attested_on_failure",
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _readiness(args: argparse.Namespace) -> _Readiness:
    campaign_paths = tuple(args.prior_campaign)
    campaign_shas = tuple(args.expected_prior_campaign_sha256)
    if (
        len(campaign_paths) != len(campaign_shas)
        or tuple(campaign_shas) != EXPECTED_PRIOR_CAMPAIGN_SHA256
    ):
        raise PairedScreenRunError("prior_campaign_attestation")
    expected_development_runner = (
        SCRIPTS_ROOT / "run_repeatable_goal_manager_development.py"
    ).resolve()
    development_file = getattr(development, "__file__", None)
    if (
        not isinstance(development_file, str)
        or Path(development_file).resolve(strict=True) != expected_development_runner
        or _file_sha256(expected_development_runner)
        != _sha(args.expected_development_runner_sha256, "development runner")
    ):
        raise PairedScreenRunError("development_runner_attestation")
    development_args = argparse.Namespace(
        context_plan=args.context_plan,
        context_catalog=args.context_catalog,
        model=args.base_model,
        fit_summary=args.base_fit_summary,
        expected_source_commit=args.expected_source_commit,
        expected_source_bundle_sha256=args.expected_source_bundle_sha256,
        expected_runner_sha256=args.expected_development_runner_sha256,
        expected_runtime_sha256=args.expected_runtime_sha256,
        expected_numpy_runtime_sha256=args.expected_numpy_runtime_sha256,
        expected_skill_manifest_sha256=args.expected_skill_manifest_sha256,
        expected_context_plan_sha256=args.expected_context_plan_sha256,
        rom=args.rom,
    )
    base = development._readiness(development_args)
    runner_path = Path(__file__).resolve()
    if runner_path.parent != SCRIPTS_ROOT.resolve():
        raise PairedScreenRunError("executable_attestation")
    runner_sha256 = _file_sha256(runner_path)
    if runner_sha256 != _sha(args.expected_runner_sha256, "runner"):
        raise PairedScreenRunError("executable_attestation")

    receipt_path = _tracked_regular(args.fit_result_receipt)
    receipt_payload = receipt_path.read_bytes()
    receipt_sha256 = hashlib.sha256(receipt_payload).hexdigest()
    if receipt_sha256 != _sha(
        args.expected_fit_result_receipt_sha256,
        "fit result receipt",
    ):
        raise PairedScreenRunError("shadow_candidate_attestation")
    receipt = _document(receipt_payload, subject="fit result receipt")
    receipt_model = _mapping(receipt.get("model"), "fit result model")
    if (
        receipt.get("schema") != _FIT_RESULT_SCHEMA
        or receipt.get("status") != "diagnostic_candidate_fit_complete"
        or receipt.get("evaluation") is not None
        or receipt_model.get("promotion_authorized") is not False
        or receipt_model.get("base_canonical_sha256")
        != base.candidate.plan.model_canonical_sha256
    ):
        raise PairedScreenRunError("shadow_candidate_contract")

    candidate_path = development._external_regular(
        args.candidate_model,
        rom_path=base.rom_path,
    )
    candidate_payload = candidate_path.read_bytes()
    candidate_file_sha256 = hashlib.sha256(candidate_payload).hexdigest()
    candidate_model = GoalManagerLinearModel.from_dict(
        _document(candidate_payload, subject="candidate model")
    )
    candidate_canonical_sha256 = canonical_goal_manager_model_sha256(candidate_model)
    if (
        candidate_file_sha256 != receipt_model.get("candidate_file_sha256")
        or candidate_canonical_sha256
        != receipt_model.get("candidate_canonical_sha256")
    ):
        raise PairedScreenRunError("shadow_candidate_attestation")

    fit_summary_path = development._external_regular(
        args.candidate_fit_summary,
        rom_path=base.rom_path,
    )
    fit_summary_payload = fit_summary_path.read_bytes()
    fit_summary_sha256 = hashlib.sha256(fit_summary_payload).hexdigest()
    fit_summary = _document(fit_summary_payload, subject="candidate fit summary")
    if (
        fit_summary_sha256 != receipt_model.get("private_summary_sha256")
        or fit_summary.get("schema") != _FIT_SUMMARY_SCHEMA
        or fit_summary.get("status") != "diagnostic_candidate_fit_complete"
        or fit_summary.get("base_model_canonical_sha256")
        != base.candidate.plan.model_canonical_sha256
        or fit_summary.get("candidate_model_canonical_sha256")
        != candidate_canonical_sha256
        or fit_summary.get("candidate_model_file_sha256")
        != candidate_file_sha256
        or fit_summary.get("promotion_authorized") is not False
        or fit_summary.get("evaluation") is not None
    ):
        raise PairedScreenRunError("shadow_candidate_attestation")

    campaigns: list[Mapping[str, object]] = []
    authenticated_shas: list[str] = []
    allow_historical_context_plan = bool(
        getattr(args, "allow_historical_context_plan", False)
    )
    for path, expected in zip(campaign_paths, campaign_shas, strict=True):
        resolved = development._external_regular(path, rom_path=base.rom_path)
        payload = resolved.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != _sha(expected, "prior campaign"):
            raise PairedScreenRunError("prior_campaign_attestation")
        campaign = development._canonical_document(payload, subject="prior campaign")
        _require_prior_campaign_contract(
            campaign,
            campaign_sha256=digest,
            current_context_plan_sha256=base.context_plan_sha256,
            expected_model_canonical_sha256=base.candidate.plan.model_canonical_sha256,
            allow_historical_context_plan=allow_historical_context_plan,
        )
        campaigns.append(campaign)
        authenticated_shas.append(digest)
    if len(set(authenticated_shas)) != len(authenticated_shas):
        raise PairedScreenRunError("prior_campaign_attestation")
    return _Readiness(
        development=base,
        runner_sha256=runner_sha256,
        candidate_model_path=candidate_path,
        candidate_model_file_sha256=candidate_file_sha256,
        candidate_model=candidate_model,
        candidate_model_canonical_sha256=candidate_canonical_sha256,
        fit_result_receipt_sha256=receipt_sha256,
        fit_summary_sha256=fit_summary_sha256,
        prior_campaigns=tuple(campaigns),
        prior_campaign_sha256=tuple(authenticated_shas),
    )


def _require_prior_campaign_contract(
    campaign: Mapping[str, object],
    *,
    campaign_sha256: str,
    current_context_plan_sha256: str,
    expected_model_canonical_sha256: str,
    allow_historical_context_plan: bool,
) -> None:
    expected_context_plan = current_context_plan_sha256
    if allow_historical_context_plan:
        historical = _HISTORICAL_CONTEXT_PLAN_BY_CAMPAIGN_SHA256.get(campaign_sha256)
        if historical is None:
            raise PairedScreenRunError("prior_campaign_contract")
        expected_context_plan = historical
    candidate = _mapping(campaign.get("candidate"), "prior candidate")
    if (
        campaign.get("schema") != development.CAMPAIGN_SCHEMA
        or campaign.get("context_plan_sha256") != expected_context_plan
        or candidate.get("model_canonical_sha256") != expected_model_canonical_sha256
    ):
        raise PairedScreenRunError("prior_campaign_contract")
    try:
        development._validate_campaign_layout(campaign)
    except development.RepeatableGoalManagerRunError:
        raise PairedScreenRunError("prior_campaign_contract") from None


def _freeze(
    readiness: _Readiness,
    destination: Path,
    private_root_path: Path,
) -> dict[str, object]:
    base = readiness.development
    destination = development._new_external_file(destination, rom_path=base.rom_path)
    store, private_root_identity_sha256 = development._open_bound_private_root(
        private_root_path,
        rom_path=base.rom_path,
    )
    selected = _selected_assignment(readiness)
    entry_index = next(
        index for index, entry in enumerate(base.entries) if entry.slot_id == selected.slot_id
    )
    entry = base.entries[entry_index]
    root_registry = open_fixed_account_claim_registry()
    if not development._historical_root_is_open(base, entry, root_registry):
        raise PairedScreenRunError("selected_root_closed")
    root = development._inspect_root(base, entry, entry_index=entry_index)
    if (
        root is None
        or root.assignment != selected
        or len(root.available_goal_kinds) < 2
        or GoalKind.ACQUIRE_SPECIES.value not in root.available_goal_kinds
        or GoalKind.EVOLVE_SPECIES.value in root.available_goal_kinds
    ):
        raise PairedScreenRunError("selected_root_initial_menu")
    root_record = development._private_root_record(root)
    identity_source = {
        "schema": PAIRED_SCREEN_SCHEMA,
        "source_commit": base.source.git_commit,
        "source_bundle_sha256": base.source_bundle_sha256,
        "runner_sha256": readiness.runner_sha256,
        "development_runner_sha256": base.runner_sha256,
        "runtime_sha256": base.runtime.sha256,
        "numpy_runtime_sha256": base.numpy_runtime_sha256,
        "skill_manifest_sha256": base.skill_manifest_sha256,
        "context_plan_sha256": base.context_plan_sha256,
        "private_root_identity_sha256": private_root_identity_sha256,
        "base": development._candidate_identity(base),
        "candidate": {
            "model_canonical_sha256": readiness.candidate_model_canonical_sha256,
            "model_file_sha256": readiness.candidate_model_file_sha256,
            "fit_summary_sha256": readiness.fit_summary_sha256,
            "fit_result_receipt_sha256": readiness.fit_result_receipt_sha256,
        },
        "prior_campaign_sha256": list(readiness.prior_campaign_sha256),
        "selection": _selection_contract(),
        "root": root_record,
        "root_consumption_sha256": root_consumption_sha256(
            state_sha256=root.capture.state_sha256,
            envelope_sha256=root.capture.envelope_sha256,
        ),
        "behavior": paired_screen_behavior_contract(),
        "endpoint": paired_screen_endpoint_contract(),
    }
    screen_id = canonical_sha256(identity_source)
    arms = [
        {
            "arm": arm,
            "model_canonical_sha256": (
                base.candidate.plan.model_canonical_sha256
                if arm == "base"
                else readiness.candidate_model_canonical_sha256
            ),
        }
        for arm in PAIRED_SCREEN_ARM_ORDER
    ]
    for arm in arms:
        arm_name = arm["arm"]
        model_sha = arm["model_canonical_sha256"]
        claim_sha256 = paired_screen_arm_claim(
            screen_id=screen_id,
            arm=arm_name,
            model_canonical_sha256=model_sha,
        )
        arm["claim_sha256"] = claim_sha256
        arm["episode_id"] = _arm_episode_id(claim_sha256)
    plan = {**identity_source, "screen_id": screen_id, "arms": arms}
    if any(
        store.inspect_episode_state(arm["episode_id"]).status != "absent"
        for arm in arms
    ):
        raise PairedScreenRunError("paired_output_collision")
    development._write_exclusive(destination, development._canonical_line(plan))
    return _public_freeze_result(readiness, plan=plan)


def _preflight(
    readiness: _Readiness,
    path: Path,
    private_root_path: Path,
    *,
    expected_screen_plan_sha256: str,
) -> dict[str, object]:
    base = readiness.development
    store, private_root_identity_sha256 = development._open_bound_private_root(
        private_root_path,
        rom_path=base.rom_path,
    )
    resolved = development._external_regular(path, rom_path=base.rom_path)
    payload = resolved.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != _sha(expected_screen_plan_sha256, "screen plan"):
        raise PairedScreenRunError("screen_plan_attestation")
    plan = development._canonical_document(payload, subject="screen plan")
    _validate_plan(
        readiness,
        plan,
        private_root_identity_sha256=private_root_identity_sha256,
    )
    root_record = _mapping(plan.get("root"), "screen root")
    selected = _selected_assignment(readiness)
    _require_selected_root_record(
        selected_root_lineage_id=selected.root_lineage_id,
        selected_slot_id=selected.slot_id,
        root_record=root_record,
        entries=base.entries,
    )
    entry_index = _integer(root_record.get("entry_index"), "entry index")
    if entry_index >= len(base.entries):
        raise PairedScreenRunError("screen_root_attestation")
    entry = base.entries[entry_index]
    registry = open_fixed_account_claim_registry()
    if not development._historical_root_is_open(base, entry, registry):
        raise PairedScreenRunError("selected_root_closed")
    inspected = development._open_frozen_root(
        base,
        entry,
        root_record,
        entry_index=entry_index,
    )
    if (
        inspected.assignment != selected
        or len(inspected.available_goal_kinds) < 2
        or GoalKind.ACQUIRE_SPECIES.value not in inspected.available_goal_kinds
        or GoalKind.EVOLVE_SPECIES.value in inspected.available_goal_kinds
    ):
        raise PairedScreenRunError("selected_root_initial_menu")
    arms = _arms(plan)
    if any(
        store.inspect_episode_state(_text(arm.get("episode_id"), "episode identity")).status
        != "absent"
        for arm in arms
    ):
        raise PairedScreenRunError("paired_output_collision")
    result = _public_freeze_result(readiness, plan=plan)
    result.update(
        {
            "schema": "pokemon.red.paired-goal-manager-screen-preflight.v1",
            "status": "paired_screen_ready_without_prediction_or_action",
            "screen_plan_sha256": digest,
            "pair_identity_available": True,
        }
    )
    return result


def _validate_plan(
    readiness: _Readiness,
    plan: Mapping[str, object],
    *,
    private_root_identity_sha256: str,
) -> None:
    base = readiness.development
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
        raise PairedScreenRunError("screen_plan_contract")
    identity = dict(plan)
    screen_id = _sha(identity.pop("screen_id", None), "screen identity")
    arms = identity.pop("arms", None)
    if screen_id != canonical_sha256(identity):
        raise PairedScreenRunError("screen_plan_identity")
    if (
        plan.get("source_commit") != base.source.git_commit
        or plan.get("source_bundle_sha256") != base.source_bundle_sha256
        or plan.get("runner_sha256") != readiness.runner_sha256
        or plan.get("development_runner_sha256") != base.runner_sha256
        or plan.get("runtime_sha256") != base.runtime.sha256
        or plan.get("numpy_runtime_sha256") != base.numpy_runtime_sha256
        or plan.get("skill_manifest_sha256") != base.skill_manifest_sha256
        or plan.get("context_plan_sha256") != base.context_plan_sha256
        or plan.get("private_root_identity_sha256") != private_root_identity_sha256
        or plan.get("base") != development._candidate_identity(base)
        or plan.get("candidate")
        != {
            "model_canonical_sha256": readiness.candidate_model_canonical_sha256,
            "model_file_sha256": readiness.candidate_model_file_sha256,
            "fit_summary_sha256": readiness.fit_summary_sha256,
            "fit_result_receipt_sha256": readiness.fit_result_receipt_sha256,
        }
        or plan.get("prior_campaign_sha256")
        != list(readiness.prior_campaign_sha256)
        or plan.get("selection") != _selection_contract()
        or plan.get("behavior") != paired_screen_behavior_contract()
        or plan.get("endpoint") != paired_screen_endpoint_contract()
    ):
        raise PairedScreenRunError("screen_plan_attestation")
    root = _mapping(plan.get("root"), "screen root")
    if plan.get("root_consumption_sha256") != root_consumption_sha256(
        state_sha256=_sha(root.get("state_sha256"), "root state"),
        envelope_sha256=_sha(root.get("envelope_sha256"), "root envelope"),
    ):
        raise PairedScreenRunError("screen_plan_attestation")
    validated_arms = _arms({**plan, "arms": arms})
    if tuple(_text(arm.get("arm"), "arm") for arm in validated_arms) != PAIRED_SCREEN_ARM_ORDER:
        raise PairedScreenRunError("screen_arm_contract")
    for arm in validated_arms:
        arm_name = _text(arm.get("arm"), "arm")
        expected_model = (
            base.candidate.plan.model_canonical_sha256
            if arm_name == "base"
            else readiness.candidate_model_canonical_sha256
        )
        if (
            set(arm)
            != {"arm", "claim_sha256", "episode_id", "model_canonical_sha256"}
            or arm.get("model_canonical_sha256") != expected_model
            or arm.get("claim_sha256")
            != paired_screen_arm_claim(
                screen_id=screen_id,
                arm=arm_name,
                model_canonical_sha256=expected_model,
            )
            or arm.get("episode_id")
            != _arm_episode_id(_sha(arm.get("claim_sha256"), "arm claim"))
        ):
            raise PairedScreenRunError("screen_arm_contract")


def _public_freeze_result(
    readiness: _Readiness,
    *,
    plan: Mapping[str, object],
) -> dict[str, object]:
    root = _mapping(plan.get("root"), "screen root")
    return {
        "schema": "pokemon.red.paired-goal-manager-screen-freeze.v1",
        "status": "paired_screen_frozen_without_prediction_or_action",
        "screen_plan_sha256": hashlib.sha256(
            development._canonical_line(plan)
        ).hexdigest(),
        "screen_identity_sha256": _sha(plan.get("screen_id"), "screen identity"),
        "selected_root_commitment_sha256": canonical_sha256(root),
        "root_partition": "train",
        "root_focus_kind": GoalKind.ACQUIRE_SPECIES.value,
        "root_development_outcome_unused": True,
        "supervised_train_exposure_allowed": True,
        "guard_only_exposure_allowed": True,
        "formal_distinct_roots_inspected": 1,
        "initial_available_goal_count": len(
            cast(list[object], root.get("available_goal_kinds"))
        ),
        "initial_acquisition_available": True,
        "base_model_canonical_sha256": (
            readiness.development.candidate.plan.model_canonical_sha256
        ),
        "candidate_model_canonical_sha256": (
            readiness.candidate_model_canonical_sha256
        ),
        "arm_count": 2,
        "maximum_decisions_per_arm": 3,
        "primary_endpoint": "safe_retained_acquisition",
        "unseen_comparison": False,
        "promotion_authorized": False,
        "model_predictions": 0,
        "controller_actions": 0,
        "emulator_frames": 0,
        "game_executions": 0,
        "development_episode_attempts_added": 0,
        "verified_outcome_examples_added": 0,
        "composition_attempts_added": 0,
        "verified_composition_episodes_added": 0,
        "model_fits_added": 0,
        "unseen_comparisons_added": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "teacher_queries": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "tracked_private_paths": 0,
        "tracked_private_identities": 0,
    }


def _selection_contract() -> dict[str, object]:
    return {
        "rule": (
            "first_registry_order_train_acquire_species_excluding_prior_"
            "teacher_free_campaign_states_and_closed_roots"
        ),
        "development_outcome_unused": True,
        "supervised_train_exposure_allowed": True,
        "guard_only_exposure_allowed": True,
        "model_scores_used": False,
        "replacement_root_allowed": False,
        "distinct_roots_formally_inspected": 1,
    }


def _arm_episode_id(claim_sha256: str) -> str:
    return f"red-pair-{_sha(claim_sha256, 'arm claim')}"


def _selected_assignment(readiness: _Readiness) -> GoalManagerAssignment:
    base = readiness.development
    excluded = {
        _text(root.get("root_lineage_id"), "prior root lineage")
        for campaign in readiness.prior_campaigns
        for root in development._roots(campaign)
    }
    prior_state_envelopes = {
        (
            _sha(root.get("state_sha256"), "prior root state"),
            _sha(root.get("envelope_sha256"), "prior root envelope"),
        )
        for campaign in readiness.prior_campaigns
        for root in development._roots(campaign)
    }
    root_registry = open_fixed_account_claim_registry()
    excluded.update(
        base.candidate.registry.assignment(entry.slot_id).root_lineage_id
        for entry in base.entries
        if (
            not development._historical_root_is_open(base, entry, root_registry)
            or (
                base.candidate.catalog.entry(entry.slot_id).state_sha256,
                base.candidate.catalog.entry(entry.slot_id).envelope_sha256,
            )
            in prior_state_envelopes
        )
    )
    assignments = tuple(
        base.candidate.registry.assignment(entry.slot_id) for entry in base.entries
    )
    return select_development_outcome_unused_acquisition_root(
        assignments,
        excluded_root_lineages=frozenset(excluded),
    )


def _require_selected_root_record(
    *,
    selected_root_lineage_id: str,
    selected_slot_id: str,
    root_record: Mapping[str, object],
    entries: tuple[development._ContextEntry, ...],
) -> None:
    entry_index = _integer(root_record.get("entry_index"), "entry index")
    if (
        entry_index >= len(entries)
        or entries[entry_index].slot_id != selected_slot_id
        or root_record.get("root_lineage_id") != selected_root_lineage_id
        or root_record.get("focus_kind") != GoalKind.ACQUIRE_SPECIES.value
    ):
        raise PairedScreenRunError("screen_root_selection")


def _sanitized_failure_stage(error: Exception) -> str:
    if isinstance(error, development.RepeatableGoalManagerRunError):
        candidate = error.stage
    elif isinstance(error, PairedScreenRunError):
        candidate = str(error)
    else:
        return "paired_screen_internal"
    if not isinstance(candidate, str) or _SAFE_STAGE.fullmatch(candidate) is None:
        return "paired_screen_internal"
    return candidate


def _arms(plan: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    value = plan.get("arms")
    if not isinstance(value, list) or len(value) != 2 or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise PairedScreenRunError("screen_arm_contract")
    return tuple(cast(Mapping[str, object], item) for item in value)


def _tracked_regular(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
    except OSError:
        raise PairedScreenRunError("tracked_receipt_attestation") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or not resolved.is_relative_to(PROJECT_ROOT.resolve())
    ):
        raise PairedScreenRunError("tracked_receipt_attestation")
    return resolved


def _document(payload: bytes, *, subject: str) -> dict[str, object]:
    if not payload or len(payload) > _MAX_DOCUMENT_BYTES:
        raise PairedScreenRunError(f"{subject.replace(' ', '_')}_attestation")
    try:
        value = json.loads(payload.decode("ascii"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise PairedScreenRunError(
            f"{subject.replace(' ', '_')}_attestation"
        ) from None
    if not isinstance(value, dict):
        raise PairedScreenRunError(f"{subject.replace(' ', '_')}_attestation")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PairedScreenRunError(f"{subject.replace(' ', '_')}_contract")
    return cast(Mapping[str, object], value)


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value or not value.isascii() or "\n" in value:
        raise PairedScreenRunError(f"{subject.replace(' ', '_')}_contract")
    return value


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise PairedScreenRunError(f"{subject.replace(' ', '_')}_contract")
    return value


def _sha(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise PairedScreenRunError(f"{subject.replace(' ', '_')}_attestation")
    return value


def _file_sha256(path: Path) -> str:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        raise PairedScreenRunError("executable_attestation") from None
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise PairedScreenRunError("executable_attestation")
    return hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
