#!/usr/bin/env python3
"""Fit one diagnostic goal-manager update from an admitted Red outcome episode."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import cast

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerExample,
)
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    fixed_account_claim_registry_root,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_dataset import load_assigned_goal_manager_episode
from pokemon_red_completion.goal_manager_development import GoalManagerDevelopmentTarget
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
)
from pokemon_red_completion.goal_manager_outcome_learning import (
    OUTCOME_UPDATE_MENU_KL_CAP,
    fit_goal_manager_outcome_update,
    maximum_policy_kl,
    outcome_update_configuration,
    require_unchanged_guard_winners,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerCollectionRegistry,
    load_committed_goal_manager_registry,
)
from pokemon_red_completion.goal_manager_trajectory import load_goal_manager_episode
from pokemon_red_completion.private_artifacts import open_private_root
from pokemon_red_completion.provenance import (
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_RESULT_SCHEMA = "pokemon.red.repeatable-goal-manager-development-result-receipt.v2"
_FIT_CLAIM_SCHEMA = "pokemon.red.repeatable-goal-manager-outcome-fit-claim.v1"
_FIT_SUMMARY_SCHEMA = "pokemon.red.repeatable-goal-manager-outcome-fit-summary.v1"
_FIT_PLAN_SCHEMA = "pokemon.red.repeatable-goal-manager-outcome-fit-plan.v1"
_GUARD_KINDS = {
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.EVOLVE_SPECIES,
    GoalKind.ADVANCE_STORY,
}


class GoalManagerOutcomeFitError(RuntimeError):
    """Raised before an unauthenticated or repeated outcome update."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--campaign-plan", type=Path, required=True)
    parser.add_argument("--result-receipt", type=Path, required=True)
    parser.add_argument("--fit-plan", type=Path, required=True)
    parser.add_argument("--out-model", type=Path, required=True)
    parser.add_argument("--out-summary", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--expected-result-receipt-sha256", required=True)
    parser.add_argument("--expected-fit-plan-sha256", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        readiness = _readiness(args)
        if args.preflight_only:
            print(json.dumps(_preflight(readiness), indent=2, sort_keys=True))
            return 0
        registry = fixed_account_claim_registry_root()
        with fixed_account_claim_registry_lease(registry, exclusive=True):
            claim = _write_fit_claim(readiness)
            result = _fit(readiness, claim=claim)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except GoalManagerOutcomeFitError as error:
        print(
            json.dumps(
                {
                    "schema": "pokemon.red.repeatable-goal-manager-outcome-fit-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": str(error),
                    "private_path_fields": 0,
                    "model_fits": 0,
                    "authority_promotions": 0,
                    "sealed_red_accesses": 0,
                    "crystal_accesses": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _readiness(args: argparse.Namespace) -> dict[str, object]:
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    runner_sha256 = _file_sha256(Path(__file__).resolve())
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    if (
        source.git_commit != _commit(args.expected_source_commit, "expected source")
        or source_bundle_sha256
        != _sha(args.expected_source_bundle_sha256, "expected source bundle")
        or runner_sha256 != _sha(args.expected_runner_sha256, "expected runner")
    ):
        raise GoalManagerOutcomeFitError("executable_attestation")

    receipt_payload = _read_regular(args.result_receipt, "result receipt")
    receipt_sha256 = hashlib.sha256(receipt_payload).hexdigest()
    if receipt_sha256 != _sha(
        args.expected_result_receipt_sha256,
        "expected result receipt",
    ):
        raise GoalManagerOutcomeFitError("result_receipt_attestation")
    receipt = _document(receipt_payload, "result receipt")
    if (
        receipt.get("schema") != _RESULT_SCHEMA
        or receipt.get("status") != "fixed_denominator_admitted_with_partial_success"
    ):
        raise GoalManagerOutcomeFitError("result_receipt_contract")

    fit_plan_payload = _read_regular(args.fit_plan, "fit plan")
    fit_plan_sha256 = hashlib.sha256(fit_plan_payload).hexdigest()
    if fit_plan_sha256 != _sha(args.expected_fit_plan_sha256, "expected fit plan"):
        raise GoalManagerOutcomeFitError("fit_plan_attestation")
    fit_plan = _document(fit_plan_payload, "fit plan")
    if (
        fit_plan.get("schema") != _FIT_PLAN_SCHEMA
        or fit_plan.get("configuration") != outcome_update_configuration()
        or fit_plan.get("result_receipt_sha256") != receipt_sha256
    ):
        raise GoalManagerOutcomeFitError("fit_plan_contract")

    campaign_payload = _read_regular(args.campaign_plan, "campaign plan")
    campaign_sha256 = hashlib.sha256(campaign_payload).hexdigest()
    campaign = _document(campaign_payload, "campaign plan")
    context_plan_payload = _read_regular(args.context_plan, "context plan")
    context_plan_sha256 = hashlib.sha256(context_plan_payload).hexdigest()
    context_plan = _document(context_plan_payload, "context plan")
    input_bindings = _mapping(receipt.get("input_bindings"), "input bindings")
    admitted = _mapping(receipt.get("admitted_evidence"), "admitted evidence")
    if (
        campaign_sha256 != input_bindings.get("campaign_plan_sha256")
        or context_plan_sha256 != input_bindings.get("context_plan_sha256")
        or admitted.get("verified_outcomes") != 2
        or admitted.get("complete_episode_manifest_sha256")
        != fit_plan.get("complete_episode_manifest_sha256")
        or fit_plan.get("campaign_plan_sha256") != campaign_sha256
        or fit_plan.get("eligible_targets") != 2
        or fit_plan.get("complete_episodes") != 1
        or fit_plan.get("independent_roots") != 1
    ):
        raise GoalManagerOutcomeFitError("fit_input_contract")

    base_payload = _read_regular(args.base_model, "base model")
    base = GoalManagerLinearModel.from_dict(_document(base_payload, "base model"))
    base_sha256 = canonical_goal_manager_model_sha256(base)
    if (
        base_sha256 != input_bindings.get("model_canonical_sha256")
        or base_sha256 != fit_plan.get("base_model_canonical_sha256")
    ):
        raise GoalManagerOutcomeFitError("base_model_attestation")

    trials = _list(campaign.get("trials"), "campaign trials")
    complete_trial_index = _integer(fit_plan.get("complete_trial_index"), "complete trial")
    trial = next(
        (
            _mapping(value, "campaign trial")
            for value in trials
            if _mapping(value, "campaign trial").get("trial_index")
            == complete_trial_index
        ),
        None,
    )
    if trial is None or trial.get("episode_id") != args.episode_id:
        raise GoalManagerOutcomeFitError("complete_episode_identity")
    roots = _list(campaign.get("roots"), "campaign roots")
    root_index = _integer(trial.get("root_index"), "root index")
    if root_index >= len(roots):
        raise GoalManagerOutcomeFitError("campaign_root_identity")
    root = _mapping(roots[root_index], "campaign root")
    entry_index = _integer(root.get("entry_index"), "entry index")
    entries = _list(context_plan.get("entries"), "context entries")
    if entry_index >= len(entries):
        raise GoalManagerOutcomeFitError("campaign_root_identity")
    slot_id = _text(_mapping(entries[entry_index], "context entry").get("slot_id"), "slot")
    registry = load_committed_goal_manager_registry(PROJECT_ROOT)
    assignment = registry.assignment(slot_id)
    if assignment.partition != "train":
        raise GoalManagerOutcomeFitError("historical_train_partition")

    out_model = _new_private_output(args.out_model, args.private_root, "model output")
    out_summary = _new_private_output(args.out_summary, args.private_root, "summary output")
    if out_model == out_summary:
        raise GoalManagerOutcomeFitError("output_collision")
    fit_identity = canonical_sha256(
        {
            "schema": "pokemon.red.repeatable-goal-manager-outcome-fit-identity.v1",
            "campaign_plan_sha256": campaign_sha256,
            "complete_episode_manifest_sha256": admitted.get(
                "complete_episode_manifest_sha256"
            ),
        }
    )
    claim_path = _claim_path(fit_identity)
    return {
        "source_commit": source.git_commit,
        "source_bundle_sha256": source_bundle_sha256,
        "runner_sha256": runner_sha256,
        "receipt": receipt,
        "receipt_sha256": receipt_sha256,
        "fit_plan": fit_plan,
        "fit_plan_sha256": fit_plan_sha256,
        "campaign": campaign,
        "campaign_sha256": campaign_sha256,
        "context_plan": context_plan,
        "context_plan_sha256": context_plan_sha256,
        "base": base,
        "base_sha256": base_sha256,
        "registry": registry,
        "trial": trial,
        "root": root,
        "assignment": assignment,
        "fit_identity": fit_identity,
        "claim_path": claim_path,
        "private_root": args.private_root,
        "episode_id": args.episode_id,
        "context_catalog_path": args.context_catalog,
        "out_model": out_model,
        "out_summary": out_summary,
    }


def _preflight(readiness: Mapping[str, object]) -> dict[str, object]:
    claim_path = _path(readiness.get("claim_path"), "claim path")
    return {
        "schema": "pokemon.red.repeatable-goal-manager-outcome-fit-preflight.v1",
        "status": "ready_for_one_train_only_update" if not claim_path.exists() else "consumed",
        "fit_identity_sha256": readiness["fit_identity"],
        "base_model_canonical_sha256": readiness["base_sha256"],
        "campaign_plan_sha256": readiness["campaign_sha256"],
        "result_receipt_sha256": readiness["receipt_sha256"],
        "fit_plan_sha256": readiness["fit_plan_sha256"],
        "expected_targets": 2,
        "expected_complete_episodes": 1,
        "expected_independent_roots": 1,
        "outcomes_decoded": 0,
        "model_predictions": 0,
        "model_fits": 0,
        "authority_promotions": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "private_path_fields": 0,
    }


def _write_fit_claim(readiness: Mapping[str, object]) -> Mapping[str, object]:
    claim_path = _path(readiness.get("claim_path"), "claim path")
    payload = {
        "schema": _FIT_CLAIM_SCHEMA,
        "fit_identity_sha256": readiness["fit_identity"],
        "base_model_canonical_sha256": readiness["base_sha256"],
        "campaign_plan_sha256": readiness["campaign_sha256"],
        "complete_episode_manifest_sha256": _mapping(
            _mapping(readiness["receipt"], "receipt").get("admitted_evidence"),
            "admitted evidence",
        )["complete_episode_manifest_sha256"],
        "fit_plan_sha256": readiness["fit_plan_sha256"],
        "result_receipt_sha256": readiness["receipt_sha256"],
        "runner_sha256": readiness["runner_sha256"],
        "source_commit": readiness["source_commit"],
    }
    data = _canonical_line(payload)
    descriptor = -1
    directory_descriptor = -1
    try:
        directory_descriptor = os.open(claim_path.parent, os.O_RDONLY)
        descriptor = os.open(
            claim_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        if os.write(descriptor, data) != len(data):
            raise OSError("short claim write")
        os.fsync(descriptor)
        os.fsync(directory_descriptor)
    except FileExistsError:
        raise GoalManagerOutcomeFitError("fit_identity_consumed") from None
    except OSError:
        raise GoalManagerOutcomeFitError("fit_claim_durability") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if directory_descriptor >= 0:
            with suppress(OSError):
                os.close(directory_descriptor)
    return payload


def _fit(
    readiness: Mapping[str, object],
    *,
    claim: Mapping[str, object],
) -> dict[str, object]:
    private_root = _path(readiness.get("private_root"), "private root")
    store = open_private_root(private_root, repository_root=PROJECT_ROOT)
    episode_id = _text(readiness.get("episode_id"), "episode")
    reader = store.open_episode(episode_id)
    receipt = _mapping(readiness.get("receipt"), "receipt")
    admitted = _mapping(receipt.get("admitted_evidence"), "admitted evidence")
    if reader.manifest_sha256 != admitted.get("complete_episode_manifest_sha256"):
        raise GoalManagerOutcomeFitError("complete_episode_manifest")
    dataset = load_goal_manager_episode(reader)
    trial = _mapping(readiness.get("trial"), "trial")
    root = _mapping(readiness.get("root"), "root")
    campaign = _mapping(readiness.get("campaign"), "campaign")
    if (
        dataset.episode_id != episode_id
        or dataset.partition != "development"
        or dataset.actor != "exploratory_goal_manager"
        or dataset.policy_id != "red-goal-manager-outcome-development-v1"
        or dataset.collection_id != campaign.get("campaign_id")
        or dataset.assignment_id != trial.get("trial_claim_sha256")
        or dataset.root_lineage_id != root.get("root_lineage_id")
        or dataset.capture_state_sha256 != root.get("state_sha256")
        or dataset.capture_envelope_sha256 != root.get("envelope_sha256")
        or dataset.binding_manifest_sha256 != root.get("binding_manifest_sha256")
        or dataset.source_commit
        != _mapping(receipt.get("source_verification"), "source verification").get(
            "execution_source_commit"
        )
        or len(dataset.examples) != 2
    ):
        raise GoalManagerOutcomeFitError("complete_episode_provenance")
    if (
        dataset.examples[0].question.ordered_policy_input_sha256
        != root.get("question_sha256")
        or dataset.examples[0].question.policy_context_sha256
        != root.get("policy_context_sha256")
        or dataset.examples[0].question.available_menu_sha256
        != root.get("available_menu_sha256")
    ):
        raise GoalManagerOutcomeFitError("complete_episode_first_question")

    rows: list[tuple[GoalManagerExample, GoalManagerDevelopmentTarget]] = []
    for example in dataset.examples:
        probability = example.behavior_probability
        if (
            example.outcome_status is GoalDecisionOutcome.INTERRUPTED
            or probability is None
            or example.behavior_policy_id
            != "pokemon.core.goal-manager.exploratory-softmax.v1"
        ):
            raise GoalManagerOutcomeFitError("outcome_target_contract")
        rows.append(
            (
                example,
                GoalManagerDevelopmentTarget(
                    decision_id=example.decision_id,
                    selected_candidate_index=example.selected_candidate_index,
                    reward=(
                        1.0
                        if example.outcome_status is GoalDecisionOutcome.SUCCEEDED
                        else -1.0
                    ),
                    behavior_probability=float(probability),
                    importance_weight=min(4.0, 1.0 / float(probability)),
                ),
            )
        )
    if len(rows) != 2 or len({row[0].decision_id for row in rows}) != 2:
        raise GoalManagerOutcomeFitError("outcome_target_count")

    registry = cast(GoalManagerCollectionRegistry, readiness["registry"])
    context_catalog = parse_goal_manager_context_catalog(
        _read_regular(
            _path(readiness["context_catalog_path"], "context catalog"),
            "context catalog",
        ),
        registry,
    )
    train_examples: list[GoalManagerExample] = []
    guard_examples: list[GoalManagerExample] = []
    for slot in registry.slots:
        if slot.partition != "train":
            continue
        loaded = load_assigned_goal_manager_episode(
            store.open_episode(registry.assignment(slot.slot_id).episode_id),
            registry.assignment(slot.slot_id),
            context_catalog=context_catalog,
        )
        train_examples.extend(loaded.examples)
        if slot.focus_kind in _GUARD_KINDS:
            guard_examples.extend(loaded.examples)
    if len(train_examples) != 54:
        raise GoalManagerOutcomeFitError("train_guard_count")
    guards = tuple(guard_examples)
    if len(guards) != 18:
        raise GoalManagerOutcomeFitError("semantic_guard_count")

    base = cast(GoalManagerLinearModel, readiness["base"])
    update = fit_goal_manager_outcome_update(base, rows)
    require_unchanged_guard_winners(base, update.model, guards)
    maximum_kl = maximum_policy_kl(base, update.model, tuple(train_examples))
    if maximum_kl > OUTCOME_UPDATE_MENU_KL_CAP:
        raise GoalManagerOutcomeFitError("train_menu_kl_cap")

    model_payload = _canonical_line(update.model.to_dict())
    reloaded = GoalManagerLinearModel.from_dict(json.loads(model_payload))
    if reloaded.to_dict() != update.model.to_dict():
        raise GoalManagerOutcomeFitError("candidate_round_trip")
    model_sha256 = canonical_goal_manager_model_sha256(reloaded)
    summary = {
        "schema": _FIT_SUMMARY_SCHEMA,
        "status": "diagnostic_candidate_fit_complete",
        "fit_identity_sha256": readiness["fit_identity"],
        "claim_sha256": canonical_sha256(claim),
        "source_commit": readiness["source_commit"],
        "source_bundle_sha256": readiness["source_bundle_sha256"],
        "runner_sha256": readiness["runner_sha256"],
        "result_receipt_sha256": readiness["receipt_sha256"],
        "fit_plan_sha256": readiness["fit_plan_sha256"],
        "campaign_plan_sha256": readiness["campaign_sha256"],
        "base_model_canonical_sha256": readiness["base_sha256"],
        "candidate_model_canonical_sha256": model_sha256,
        "candidate_model_file_sha256": hashlib.sha256(model_payload).hexdigest(),
        "targets": 2,
        "complete_episodes": 1,
        "independent_roots": 1,
        "excluded_failed_prefix_choices": 19,
        "train_guard_menus": len(train_examples),
        "semantic_winner_guard_menus": len(guards),
        "maximum_train_menu_kl": maximum_kl,
        "configuration": outcome_update_configuration(),
        "update": update.public_dict(),
        "evaluation": None,
        "promotion_authorized": False,
        "authority_delta": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "private_path_fields": 0,
    }
    _publish_private(_path(readiness["out_model"], "model output"), model_payload)
    _publish_private(
        _path(readiness["out_summary"], "summary output"),
        _canonical_line(summary),
    )
    return {
        "schema": "pokemon.red.repeatable-goal-manager-outcome-fit-result.v1",
        "status": "diagnostic_candidate_fit_complete",
        "fit_identity_sha256": readiness["fit_identity"],
        "base_model_canonical_sha256": readiness["base_sha256"],
        "candidate_model_canonical_sha256": model_sha256,
        "targets": 2,
        "complete_episodes": 1,
        "independent_roots": 1,
        "excluded_failed_prefix_choices": 19,
        "maximum_train_menu_kl": maximum_kl,
        "training_loss_before": update.before.weighted_binary_cross_entropy,
        "training_loss_after": update.after.weighted_binary_cross_entropy,
        "promotion_authorized": False,
        "authority_delta": 0,
        "sealed_red_accesses": 0,
        "crystal_accesses": 0,
        "private_path_fields": 0,
    }


def _claim_path(fit_identity: str) -> Path:
    root = fixed_account_claim_registry_root()
    metadata = root.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise GoalManagerOutcomeFitError("fit_claim_registry")
    return root / f"goal-manager-outcome-fit-{fit_identity}.json"


def _new_private_output(path: Path, root: Path, subject: str) -> Path:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=False)
    if not resolved.is_relative_to(resolved_root) or resolved.exists():
        raise GoalManagerOutcomeFitError(subject.replace(" ", "_"))
    return resolved


def _publish_private(path: Path, payload: bytes) -> None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short output write")
        os.fsync(descriptor)
    except OSError:
        raise GoalManagerOutcomeFitError("private_output_durability") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)


def _read_regular(path: Path, subject: str) -> bytes:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise OSError("not a regular file")
        return path.read_bytes()
    except OSError:
        raise GoalManagerOutcomeFitError(subject.replace(" ", "_")) from None


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(_read_regular(path, "runner source")).hexdigest()


def _document(payload: bytes, subject: str) -> Mapping[str, object]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GoalManagerOutcomeFitError(subject.replace(" ", "_")) from None
    return _mapping(value, subject)


def _mapping(value: object, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise GoalManagerOutcomeFitError(subject.replace(" ", "_"))
    return value


def _list(value: object, subject: str) -> list[object]:
    if not isinstance(value, list):
        raise GoalManagerOutcomeFitError(subject.replace(" ", "_"))
    return value


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise GoalManagerOutcomeFitError(subject.replace(" ", "_"))
    return value


def _sha(value: object, subject: str) -> str:
    result = _text(value, subject)
    if _SHA256.fullmatch(result) is None:
        raise GoalManagerOutcomeFitError(subject.replace(" ", "_"))
    return result


def _commit(value: object, subject: str) -> str:
    result = _text(value, subject)
    if _GIT_COMMIT.fullmatch(result) is None:
        raise GoalManagerOutcomeFitError(subject.replace(" ", "_"))
    return result


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise GoalManagerOutcomeFitError(subject.replace(" ", "_"))
    return value


def _path(value: object, subject: str) -> Path:
    if not isinstance(value, Path):
        raise GoalManagerOutcomeFitError(subject.replace(" ", "_"))
    return value


def _canonical_line(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


if __name__ == "__main__":
    raise SystemExit(main())
