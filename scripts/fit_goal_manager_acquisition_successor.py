#!/usr/bin/env python3
"""Fit one fixed goal-manager successor from the retained acquisition outcome."""

# ruff: noqa: E402 -- pin the reviewed workspace source before project imports

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

from pokemon_red_completion.collection_protocol import working_source_bundle_sha256
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind, GoalManagerExample
from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    fixed_account_claim_registry_root,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCatalog,
    parse_goal_manager_context_catalog,
)
from pokemon_red_completion.goal_manager_dataset import load_assigned_goal_manager_episode
from pokemon_red_completion.goal_manager_development import (
    AdmittedGoalManagerDevelopmentEpisode,
    goal_manager_development_numpy_runtime_sha256,
    load_repeatable_goal_manager_development_episode,
    repeatable_goal_manager_trial_execution_identity,
)
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    canonical_goal_manager_model_sha256,
)
from pokemon_red_completion.goal_manager_outcome_learning import (
    OUTCOME_UPDATE_MENU_KL_CAP,
    fit_goal_manager_outcome_successor_update,
    maximum_policy_kl,
    outcome_update_configuration,
    require_unchanged_guard_winners,
)
from pokemon_red_completion.goal_manager_protocol import (
    GoalManagerCollectionRegistry,
    load_committed_goal_manager_registry_at_revision,
)
from pokemon_red_completion.paired_goal_manager_screen import (
    paired_screen_arm_execution_identity,
    paired_screen_execution_identity,
)
from pokemon_red_completion.private_artifacts import (
    PrivateEpisodeReader,
    open_private_root,
)
from pokemon_red_completion.private_artifacts import (
    _rename_no_replace as atomic_no_replace_rename,
)
from pokemon_red_completion.provenance import (
    canonical_sha256,
    detect_source_identity,
    require_clean_source,
    require_published_source,
)

PROJECT_ROOT = _BOOTSTRAP_PROJECT_ROOT
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_GUARD_KINDS = {
    GoalKind.ACQUIRE_SPECIES,
    GoalKind.EVOLVE_SPECIES,
    GoalKind.ADVANCE_STORY,
}
_PLAN_SCHEMA = "pokemon.red.goal-manager-acquisition-successor-fit-plan.v1"
_SUMMARY_SCHEMA = "pokemon.red.goal-manager-acquisition-successor-fit-summary.v1"
_CLAIM_SCHEMA = "pokemon.red.goal-manager-acquisition-successor-fit-claim.v1"


class AcquisitionSuccessorFitError(RuntimeError):
    """A path-free failure at a declared offline-fit boundary."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--anchor-episode-id", required=True)
    parser.add_argument("--candidate-episode-id", required=True)
    parser.add_argument("--anchor-model", type=Path, required=True)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--base-fit-summary", type=Path, required=True)
    parser.add_argument("--context-catalog", type=Path, required=True)
    parser.add_argument("--context-plan", type=Path, required=True)
    parser.add_argument("--anchor-campaign-plan", type=Path, required=True)
    parser.add_argument("--pair-plan", type=Path, required=True)
    parser.add_argument("--anchor-result-receipt", type=Path, required=True)
    parser.add_argument("--pair-result-receipt", type=Path, required=True)
    parser.add_argument("--prior-fit-result-receipt", type=Path, required=True)
    parser.add_argument("--fit-plan", type=Path, required=True)
    parser.add_argument("--out-bundle", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--expected-source-bundle-sha256", required=True)
    parser.add_argument("--expected-runner-sha256", required=True)
    parser.add_argument("--expected-learner-sha256", required=True)
    parser.add_argument("--expected-numpy-runtime-sha256", required=True)
    parser.add_argument("--expected-fit-plan-sha256", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    phase = "readiness"
    try:
        ready = _readiness(args)
        if args.preflight_only:
            print(json.dumps(_preflight(ready), indent=2, sort_keys=True))
            return 0
        registry_path = fixed_account_claim_registry_root()
        with fixed_account_claim_registry_lease(registry_path, exclusive=True):
            phase = "preclaim_authentication"
            readers = _prepare_private_readers(ready)
            claim = _write_claim(ready)
            phase = "outcome_decode"
            prepared = _prepare_fit_inputs(ready, readers)
            phase = "fit_attempted"
            result = _fit(ready, claim, prepared)
            phase = "complete"
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as error:
        safe_stage = (
            str(error) if isinstance(error, AcquisitionSuccessorFitError) else "unexpected_failure"
        )
        print(
            json.dumps(
                {
                    "schema": "pokemon.red.goal-manager-acquisition-successor-fit-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": safe_stage,
                    "phase": phase,
                    "model_fit_attempts": int(phase in {"fit_attempted", "complete"}),
                    "model_fits": 0 if phase != "complete" else "not_attested",
                    "authority_promotions": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _readiness(args: argparse.Namespace) -> dict[str, Any]:
    _require_project_import_origins()
    source = detect_source_identity(PROJECT_ROOT, include_untracked=True)
    require_clean_source(source)
    require_published_source(PROJECT_ROOT, source)
    runner_sha256 = _file_sha256(Path(__file__).resolve())
    learner_sha256 = _file_sha256(
        PROJECT_ROOT / "src/pokemon_red_completion/goal_manager_outcome_learning.py"
    )
    numpy_runtime_sha256 = goal_manager_development_numpy_runtime_sha256()
    source_bundle_sha256 = working_source_bundle_sha256(PROJECT_ROOT)
    if (
        source.git_commit != _commit(args.expected_source_commit, "source")
        or source_bundle_sha256 != _sha(args.expected_source_bundle_sha256, "source bundle")
        or runner_sha256 != _sha(args.expected_runner_sha256, "runner")
        or learner_sha256 != _sha(args.expected_learner_sha256, "learner")
        or numpy_runtime_sha256 != _sha(args.expected_numpy_runtime_sha256, "NumPy runtime")
    ):
        raise AcquisitionSuccessorFitError("executable_attestation")

    fit_plan_bytes, fit_plan = _read_document(args.fit_plan, "fit plan")
    fit_plan_sha256 = hashlib.sha256(fit_plan_bytes).hexdigest()
    if (
        fit_plan_sha256 != _sha(args.expected_fit_plan_sha256, "fit plan")
        or fit_plan.get("schema") != _PLAN_SCHEMA
        or fit_plan.get("status") != "frozen_before_private_outcome_decode"
        or fit_plan.get("configuration") != outcome_update_configuration()
    ):
        raise AcquisitionSuccessorFitError("fit_plan_attestation")

    inputs = _mapping(fit_plan.get("input_bindings"), "input bindings")
    if (
        inputs.get("learner_sha256") != learner_sha256
        or inputs.get("numpy_runtime_sha256") != numpy_runtime_sha256
    ):
        raise AcquisitionSuccessorFitError("fit_plan_executable_attestation")
    documents: dict[str, tuple[bytes, Mapping[str, object]]] = {}
    for key, path in (
        ("anchor_campaign_plan_sha256", args.anchor_campaign_plan),
        ("pair_plan_sha256", args.pair_plan),
        ("anchor_result_receipt_sha256", args.anchor_result_receipt),
        ("pair_result_receipt_sha256", args.pair_result_receipt),
        ("prior_fit_result_receipt_sha256", args.prior_fit_result_receipt),
        ("context_plan_sha256", args.context_plan),
    ):
        payload, document = _read_document(path, key)
        if hashlib.sha256(payload).hexdigest() != inputs.get(key):
            raise AcquisitionSuccessorFitError("input_attestation")
        documents[key] = (payload, document)

    catalog_bytes, _catalog_document = _read_document(args.context_catalog, "catalog")
    if hashlib.sha256(catalog_bytes).hexdigest() != inputs.get("context_catalog_sha256"):
        raise AcquisitionSuccessorFitError("input_attestation")
    anchor_model = GoalManagerLinearModel.from_dict(
        _document(_read_regular(args.anchor_model, "anchor model"), "anchor model")
    )
    base_model_bytes = _read_regular(args.base_model, "base model")
    base_model = GoalManagerLinearModel.from_dict(_document(base_model_bytes, "base model"))
    base_summary_bytes, base_summary = _read_document(args.base_fit_summary, "base summary")
    if (
        _file_sha256(args.anchor_model) != inputs.get("anchor_model_file_sha256")
        or canonical_goal_manager_model_sha256(anchor_model)
        != inputs.get("anchor_model_canonical_sha256")
        or hashlib.sha256(base_model_bytes).hexdigest() != inputs.get("base_model_file_sha256")
        or canonical_goal_manager_model_sha256(base_model)
        != inputs.get("base_model_canonical_sha256")
        or hashlib.sha256(base_summary_bytes).hexdigest() != inputs.get("base_fit_summary_sha256")
        or base_summary.get("candidate_model_canonical_sha256")
        != inputs.get("base_model_canonical_sha256")
    ):
        raise AcquisitionSuccessorFitError("model_attestation")

    prior_fit = documents["prior_fit_result_receipt_sha256"][1]
    pair_result = documents["pair_result_receipt_sha256"][1]
    anchor_result = documents["anchor_result_receipt_sha256"][1]
    anchor_campaign = documents["anchor_campaign_plan_sha256"][1]
    pair_plan = documents["pair_plan_sha256"][1]
    anchor_inputs = _mapping(anchor_result.get("input_bindings"), "anchor inputs")
    anchor_evidence = _mapping(anchor_result.get("admitted_evidence"), "anchor evidence")
    prior_model = _mapping(prior_fit.get("model"), "prior fit model")
    prior_inputs = _mapping(prior_fit.get("input_bindings"), "prior fit inputs")
    pair_bindings = _mapping(pair_result.get("bindings"), "pair bindings")
    pair_arms = _list(pair_result.get("arms"), "pair result arms")
    frozen_arms = _list(pair_plan.get("arms"), "frozen pair arms")
    frozen_candidate = _mapping(pair_plan.get("candidate"), "frozen candidate")
    frozen_base = _mapping(pair_plan.get("base"), "frozen base")
    training_source = _commit(inputs.get("base_training_source_commit"), "training source")
    registry = load_committed_goal_manager_registry_at_revision(PROJECT_ROOT, training_source)
    catalog = parse_goal_manager_context_catalog(catalog_bytes, registry)
    if catalog.catalog_sha256 != inputs.get("context_catalog_sha256"):
        raise AcquisitionSuccessorFitError("catalog_attestation")
    _require_prior_fit_provenance(prior_inputs, inputs, registry)
    if (
        prior_fit.get("schema")
        != "pokemon.red.repeatable-goal-manager-outcome-fit-result-receipt.v1"
        or prior_model.get("candidate_canonical_sha256")
        != inputs.get("base_model_canonical_sha256")
        or prior_model.get("candidate_file_sha256") != inputs.get("base_model_file_sha256")
        or prior_model.get("private_summary_sha256") != inputs.get("base_fit_summary_sha256")
        or prior_inputs.get("campaign_plan_sha256") != inputs.get("anchor_campaign_plan_sha256")
        or prior_inputs.get("complete_episode_manifest_sha256")
        != inputs.get("anchor_manifest_sha256")
        or pair_result.get("schema") != "pokemon.red.paired-goal-manager-outcome-screen-result.v1"
        or _mapping(pair_result.get("adjudication"), "pair adjudication").get("result") != "tie"
        or pair_bindings.get("screen_plan_sha256") != inputs.get("pair_plan_sha256")
        or len(pair_arms) != 2
        or pair_arms[0].get("arm") != "base"
        or pair_arms[0].get("manifest_sha256") != inputs.get("excluded_base_arm_manifest_sha256")
        or pair_arms[0].get("admitted") is not True
        or pair_arms[0].get("successful_retained_acquisitions") != 1
        or pair_arms[1].get("arm") != "candidate"
        or pair_arms[1].get("manifest_sha256")
        != inputs.get("candidate_acquisition_manifest_sha256")
        or pair_arms[1].get("admitted") is not True
        or pair_arms[1].get("successful_retained_acquisitions") != 1
        or len(frozen_arms) != 2
        or frozen_arms[0].get("arm") != "base"
        or frozen_arms[0].get("model_canonical_sha256")
        != inputs.get("anchor_model_canonical_sha256")
        or frozen_arms[1].get("arm") != "candidate"
        or frozen_arms[1].get("model_canonical_sha256") != inputs.get("base_model_canonical_sha256")
        or frozen_base.get("model_canonical_sha256") != inputs.get("anchor_model_canonical_sha256")
        or frozen_candidate.get("model_canonical_sha256")
        != inputs.get("base_model_canonical_sha256")
        or frozen_candidate.get("fit_result_receipt_sha256")
        != inputs.get("prior_fit_result_receipt_sha256")
        or frozen_candidate.get("fit_summary_sha256") != inputs.get("base_fit_summary_sha256")
        or anchor_result.get("schema")
        != "pokemon.red.repeatable-goal-manager-development-result-receipt.v2"
        or anchor_inputs.get("campaign_plan_sha256") != inputs.get("anchor_campaign_plan_sha256")
        or anchor_inputs.get("context_plan_sha256") != inputs.get("context_plan_sha256")
        or anchor_inputs.get("model_canonical_sha256")
        != inputs.get("anchor_model_canonical_sha256")
        or anchor_evidence.get("complete_episode_manifest_sha256")
        != inputs.get("anchor_manifest_sha256")
        or anchor_evidence.get("verified_outcomes") != 2
        or anchor_evidence.get("selected_goal_kinds") != ["manage_storage", "restore_team"]
        or base_summary.get("base_model_canonical_sha256")
        != inputs.get("anchor_model_canonical_sha256")
        or base_summary.get("candidate_model_file_sha256") != inputs.get("base_model_file_sha256")
        or base_summary.get("result_receipt_sha256") != inputs.get("anchor_result_receipt_sha256")
        or base_summary.get("campaign_plan_sha256") != inputs.get("anchor_campaign_plan_sha256")
        or base_summary.get("targets") != 2
        or base_summary.get("excluded_failed_prefix_choices") != 19
    ):
        raise AcquisitionSuccessorFitError("public_evidence_contract")

    anchor_trial = next(
        (
            row
            for row in _list(anchor_campaign.get("trials"), "anchor trials")
            if row.get("trial_index") == 8
        ),
        None,
    )
    if (
        anchor_trial is None
        or anchor_trial.get("episode_id") != args.anchor_episode_id
        or frozen_arms[1].get("episode_id") != args.candidate_episode_id
    ):
        raise AcquisitionSuccessorFitError("episode_identity_contract")

    private_root = args.private_root.resolve(strict=True)
    out_bundle = _new_output_bundle(args.out_bundle, private_root)
    fit_identity = canonical_sha256(
        {
            "schema": "pokemon.red.goal-manager-acquisition-successor-fit-identity.v1",
            "base_model_canonical_sha256": inputs["base_model_canonical_sha256"],
            "candidate_acquisition_manifest_sha256": inputs[
                "candidate_acquisition_manifest_sha256"
            ],
            "objective_id": outcome_update_configuration()["objective_id"],
        }
    )
    return {
        "source_commit": source.git_commit,
        "source_bundle_sha256": source_bundle_sha256,
        "runner_sha256": runner_sha256,
        "learner_sha256": learner_sha256,
        "numpy_runtime_sha256": numpy_runtime_sha256,
        "fit_plan": fit_plan,
        "fit_plan_sha256": fit_plan_sha256,
        "inputs": inputs,
        "documents": documents,
        "anchor_model": anchor_model,
        "base_model": base_model,
        "registry": registry,
        "catalog": catalog,
        "catalog_bytes": catalog_bytes,
        "private_root": private_root,
        "anchor_episode_id": args.anchor_episode_id,
        "candidate_episode_id": args.candidate_episode_id,
        "out_bundle": out_bundle,
        "fit_identity": fit_identity,
        "claim_path": fixed_account_claim_registry_root()
        / f"goal-manager-acquisition-successor-{fit_identity}.json",
    }


def _require_prior_fit_provenance(
    prior_inputs: Mapping[str, Any],
    inputs: Mapping[str, Any],
    registry: GoalManagerCollectionRegistry,
) -> None:
    if (
        prior_inputs.get("result_receipt_sha256") != inputs.get("anchor_result_receipt_sha256")
        or prior_inputs.get("base_training_source_commit")
        != inputs.get("base_training_source_commit")
        or prior_inputs.get("base_context_catalog_sha256") != inputs.get("context_catalog_sha256")
        or prior_inputs.get("base_registry_sha256") != registry.registry_sha256
    ):
        raise AcquisitionSuccessorFitError("prior_fit_provenance_contract")


def _preflight(ready: Mapping[str, Any]) -> dict[str, object]:
    _prepare_private_readers(ready)
    return {
        "schema": "pokemon.red.goal-manager-acquisition-successor-fit-preflight.v1",
        "status": (
            "ready_for_one_offline_successor_update"
            if not cast(Path, ready["claim_path"]).exists()
            else "consumed"
        ),
        "fit_identity_sha256": ready["fit_identity"],
        "fit_plan_sha256": ready["fit_plan_sha256"],
        "learner_sha256": ready["learner_sha256"],
        "numpy_runtime_sha256": ready["numpy_runtime_sha256"],
        "fresh_targets_expected": 1,
        "anchor_targets_expected": 2,
        "outcomes_decoded": 0,
        "model_fits": 0,
        "controller_actions": 0,
        "teacher_queries": 0,
        "private_path_fields": 0,
    }


def _prepare_private_readers(
    ready: Mapping[str, Any],
) -> dict[str, PrivateEpisodeReader]:
    store = open_private_root(cast(Path, ready["private_root"]), repository_root=PROJECT_ROOT)
    inputs = _mapping(ready.get("inputs"), "inputs")
    expected_manifests = dict(
        (
            (ready["anchor_episode_id"], inputs["anchor_manifest_sha256"]),
            (
                ready["candidate_episode_id"],
                inputs["candidate_acquisition_manifest_sha256"],
            ),
        )
    )
    registry = cast(GoalManagerCollectionRegistry, ready["registry"])
    episode_ids = [
        cast(str, ready["anchor_episode_id"]),
        cast(str, ready["candidate_episode_id"]),
    ]
    episode_ids.extend(
        registry.assignment(slot.slot_id).episode_id
        for slot in registry.slots
        if slot.partition == "train"
    )
    if len(episode_ids) != 56 or len(set(episode_ids)) != 56:
        raise AcquisitionSuccessorFitError("episode_roster_contract")
    readers: dict[str, PrivateEpisodeReader] = {}
    for episode_id in episode_ids:
        reader = store.open_episode(episode_id)
        expected = expected_manifests.get(episode_id)
        if expected is not None and reader.manifest_sha256 != expected:
            raise AcquisitionSuccessorFitError("episode_manifest_attestation")
        readers[episode_id] = reader
    return readers


def _prepare_fit_inputs(
    ready: Mapping[str, Any], readers: Mapping[str, PrivateEpisodeReader]
) -> dict[str, object]:
    anchor = _load_anchor(ready, readers[cast(str, ready["anchor_episode_id"])])
    acquisition = _load_candidate_acquisition(
        ready, readers[cast(str, ready["candidate_episode_id"])]
    )
    if (
        len(anchor.targets) != 2
        or tuple(example.selected_kind for example in anchor.dataset.examples)
        != (GoalKind.MANAGE_STORAGE, GoalKind.RESTORE_TEAM)
        or any(target.reward != 1.0 for target in anchor.targets)
        or len(acquisition.targets) != 1
        or acquisition.targets[0].reward != 1.0
        or acquisition.dataset.examples[0].selected_kind is not GoalKind.ACQUIRE_SPECIES
        or acquisition.dataset.examples[0].outcome_status is not GoalDecisionOutcome.SUCCEEDED
        or acquisition.successful_retained_acquisitions != 1
        or anchor.dataset.root_lineage_id == acquisition.dataset.root_lineage_id
        or anchor.dataset.capture_state_sha256 == acquisition.dataset.capture_state_sha256
        or anchor.dataset.capture_envelope_sha256 == acquisition.dataset.capture_envelope_sha256
    ):
        raise AcquisitionSuccessorFitError("settled_target_contract")
    registry = cast(GoalManagerCollectionRegistry, ready["registry"])
    catalog = cast(GoalManagerContextCatalog, ready["catalog"])
    train_examples: list[GoalManagerExample] = []
    guard_examples: list[GoalManagerExample] = []
    guard_manifests: list[str] = []
    for slot in registry.slots:
        if slot.partition != "train":
            continue
        assigned = registry.assignment(slot.slot_id)
        reader = readers[assigned.episode_id]
        guard_manifests.append(reader.manifest_sha256)
        loaded = load_assigned_goal_manager_episode(reader, assigned, context_catalog=catalog)
        train_examples.extend(loaded.examples)
        if slot.focus_kind in _GUARD_KINDS:
            guard_examples.extend(loaded.examples)
    if (
        len(train_examples) != 54
        or len(guard_examples) != 18
        or len(guard_manifests) != 54
        or len(set(guard_manifests)) != 54
    ):
        raise AcquisitionSuccessorFitError("guard_set_contract")
    return {
        "anchor": anchor,
        "acquisition": acquisition,
        "train_examples": tuple(train_examples),
        "guard_examples": tuple(guard_examples),
        "guard_manifest_roster_sha256": canonical_sha256(
            {
                "schema": "pokemon.red.goal-manager-successor-guard-manifests.v1",
                "manifest_sha256": guard_manifests,
            }
        ),
    }


def _write_claim(ready: Mapping[str, Any]) -> Mapping[str, object]:
    path = cast(Path, ready["claim_path"])
    payload = {
        "schema": _CLAIM_SCHEMA,
        "fit_identity_sha256": ready["fit_identity"],
        "fit_plan_sha256": ready["fit_plan_sha256"],
        "base_model_canonical_sha256": _mapping(ready.get("inputs"), "inputs")[
            "base_model_canonical_sha256"
        ],
        "source_commit": ready["source_commit"],
        "runner_sha256": ready["runner_sha256"],
        "learner_sha256": ready["learner_sha256"],
        "numpy_runtime_sha256": ready["numpy_runtime_sha256"],
    }
    data = _canonical_line(payload)
    descriptor = -1
    directory = -1
    try:
        directory = os.open(path.parent, os.O_RDONLY)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        if os.write(descriptor, data) != len(data):
            raise OSError("short write")
        os.fsync(descriptor)
        os.fsync(directory)
    except FileExistsError:
        raise AcquisitionSuccessorFitError("fit_identity_consumed") from None
    except OSError:
        raise AcquisitionSuccessorFitError("fit_claim_durability") from None
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        if directory >= 0:
            with suppress(OSError):
                os.close(directory)
    return payload


def _fit(
    ready: Mapping[str, Any],
    claim: Mapping[str, object],
    prepared: Mapping[str, object],
) -> dict[str, object]:
    anchor = cast(AdmittedGoalManagerDevelopmentEpisode, prepared["anchor"])
    acquisition = cast(AdmittedGoalManagerDevelopmentEpisode, prepared["acquisition"])
    fresh_rows = tuple(zip(acquisition.dataset.examples, acquisition.targets, strict=True))
    anchor_rows = tuple(zip(anchor.dataset.examples, anchor.targets, strict=True))
    base = cast(GoalManagerLinearModel, ready["base_model"])
    successor = fit_goal_manager_outcome_successor_update(base, fresh_rows, anchor_rows)
    train_examples = cast(tuple[GoalManagerExample, ...], prepared["train_examples"])
    guard_examples = cast(tuple[GoalManagerExample, ...], prepared["guard_examples"])
    require_unchanged_guard_winners(base, successor.update.model, guard_examples)
    maximum_kl = maximum_policy_kl(base, successor.update.model, train_examples)
    if maximum_kl > OUTCOME_UPDATE_MENU_KL_CAP:
        raise AcquisitionSuccessorFitError("train_menu_kl_cap")
    model_payload = _canonical_line(successor.update.model.to_dict())
    reloaded = GoalManagerLinearModel.from_dict(json.loads(model_payload))
    if reloaded.to_dict() != successor.update.model.to_dict():
        raise AcquisitionSuccessorFitError("candidate_round_trip")
    candidate_sha = canonical_goal_manager_model_sha256(reloaded)
    summary = {
        "schema": _SUMMARY_SCHEMA,
        "status": "shadow_successor_fit_complete",
        "fit_identity_sha256": ready["fit_identity"],
        "claim_sha256": canonical_sha256(claim),
        "source_commit": ready["source_commit"],
        "source_bundle_sha256": ready["source_bundle_sha256"],
        "runner_sha256": ready["runner_sha256"],
        "learner_sha256": ready["learner_sha256"],
        "numpy_runtime_sha256": ready["numpy_runtime_sha256"],
        "fit_plan_sha256": ready["fit_plan_sha256"],
        "base_model_canonical_sha256": _mapping(ready.get("inputs"), "inputs")[
            "base_model_canonical_sha256"
        ],
        "candidate_model_canonical_sha256": candidate_sha,
        "candidate_model_file_sha256": hashlib.sha256(model_payload).hexdigest(),
        "fresh_targets": 1,
        "anchor_targets": 2,
        "excluded_duplicate_base_arm": 1,
        "excluded_failed_prefix_choices": 19,
        "guard_manifest_roster_sha256": prepared["guard_manifest_roster_sha256"],
        "maximum_train_menu_kl": maximum_kl,
        "configuration": outcome_update_configuration(),
        "successor_update": successor.public_dict(),
        "evaluation": None,
        "promotion_authorized": False,
        "authority_delta": 0,
        "private_path_fields": 0,
    }
    bundle_manifest_sha256 = _publish_bundle(
        cast(Path, ready["out_bundle"]),
        model_payload=model_payload,
        summary_payload=_canonical_line(summary),
        fit_identity_sha256=cast(str, ready["fit_identity"]),
    )
    return {
        "schema": "pokemon.red.goal-manager-acquisition-successor-fit-result.v1",
        "status": "shadow_successor_fit_complete",
        "fit_identity_sha256": ready["fit_identity"],
        "base_model_canonical_sha256": summary["base_model_canonical_sha256"],
        "candidate_model_canonical_sha256": candidate_sha,
        "bundle_manifest_sha256": bundle_manifest_sha256,
        "fresh_targets": 1,
        "anchor_targets": 2,
        "training_loss_before": successor.update.before.weighted_binary_cross_entropy,
        "training_loss_after": successor.update.after.weighted_binary_cross_entropy,
        "acquisition_probability_before": successor.update.before.selected_probabilities[0],
        "acquisition_probability_after": successor.update.after.selected_probabilities[0],
        "anchor_probabilities_before": list(successor.anchor_before.selected_probabilities),
        "anchor_probabilities_after": list(successor.anchor_after.selected_probabilities),
        "protected_winner_flips": 0,
        "maximum_train_menu_kl": maximum_kl,
        "model_fits_added": 1,
        "authority_delta": 0,
        "promotion_authorized": False,
        "private_path_fields": 0,
    }


def _load_anchor(
    ready: Mapping[str, Any], reader: PrivateEpisodeReader
) -> AdmittedGoalManagerDevelopmentEpisode:
    plan = ready["documents"]["anchor_campaign_plan_sha256"][1]
    result = ready["documents"]["anchor_result_receipt_sha256"][1]
    trial = next(row for row in _list(plan.get("trials"), "trials") if row.get("trial_index") == 8)
    root = _list(plan.get("roots"), "roots")[_integer(trial.get("root_index"), "root")]
    context_plan = ready["documents"]["context_plan_sha256"][1]
    entry = _list(context_plan.get("entries"), "entries")[
        _integer(root.get("entry_index"), "entry")
    ]
    slot_id = _text(entry.get("slot_id"), "slot")
    source_commit = _text(
        _mapping(result.get("source_verification"), "source").get("execution_source_commit"),
        "execution source",
    )
    execution_identity = repeatable_goal_manager_trial_execution_identity(
        campaign_id=_sha(plan.get("campaign_id"), "campaign"),
        campaign_plan_sha256=hashlib.sha256(
            ready["documents"]["anchor_campaign_plan_sha256"][0]
        ).hexdigest(),
        model_canonical_sha256=canonical_goal_manager_model_sha256(ready["anchor_model"]),
        numpy_runtime_sha256=_sha(plan.get("numpy_runtime_sha256"), "NumPy"),
        root_lineage_id=_text(root.get("root_lineage_id"), "root lineage"),
        runtime_sha256=_sha(plan.get("runtime_sha256"), "runtime"),
        source_commit=source_commit,
        trial_index=8,
        trial_claim_sha256=_sha(trial.get("trial_claim_sha256"), "trial claim"),
    )
    return load_repeatable_goal_manager_development_episode(
        reader,
        expected_campaign_id=_sha(plan.get("campaign_id"), "campaign"),
        expected_trial_claim_sha256=_sha(trial.get("trial_claim_sha256"), "trial claim"),
        expected_episode_id=cast(str, ready["anchor_episode_id"]),
        expected_root_lineage_id=_text(root.get("root_lineage_id"), "root lineage"),
        expected_seed=_integer(trial.get("seed"), "seed"),
        expected_execution_identity_sha256=execution_identity,
        expected_context_catalog_sha256=cast(
            GoalManagerContextCatalog, ready["catalog"]
        ).catalog_sha256,
        expected_context_id=cast(GoalManagerContextCatalog, ready["catalog"])
        .entry(slot_id)
        .context_id,
        expected_binding_manifest_sha256=_sha(root.get("binding_manifest_sha256"), "binding"),
        expected_state_sha256=_sha(root.get("state_sha256"), "state"),
        expected_envelope_sha256=_sha(root.get("envelope_sha256"), "envelope"),
        expected_first_question_sha256=_sha(root.get("question_sha256"), "question"),
        expected_first_policy_context_sha256=_sha(
            root.get("policy_context_sha256"), "policy context"
        ),
        expected_first_available_menu_sha256=_sha(root.get("available_menu_sha256"), "menu"),
        expected_model=cast(GoalManagerLinearModel, ready["anchor_model"]),
        expected_source_commit=source_commit,
    )


def _load_candidate_acquisition(
    ready: Mapping[str, Any], reader: PrivateEpisodeReader
) -> AdmittedGoalManagerDevelopmentEpisode:
    plan_bytes, plan = ready["documents"]["pair_plan_sha256"]
    result = ready["documents"]["pair_result_receipt_sha256"][1]
    arms = _list(plan.get("arms"), "arms")
    arm = next(row for row in arms if row.get("arm") == "candidate")
    root = _mapping(plan.get("root"), "pair root")
    claims = tuple(_sha(row.get("claim_sha256"), "arm claim") for row in arms)
    pair_identity = paired_screen_execution_identity(
        screen_plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
        screen_id=_sha(plan.get("screen_id"), "screen"),
        execution_source_commit=_text(
            _mapping(result.get("source_verification"), "source").get("execution_git_commit"),
            "execution source",
        ),
        execution_runner_sha256=_sha(
            _mapping(result.get("bindings"), "bindings").get("runner_sha256"), "runner"
        ),
        runtime_sha256=_sha(plan.get("runtime_sha256"), "runtime"),
        root_consumption_sha256=_sha(plan.get("root_consumption_sha256"), "root consumption"),
        arm_claim_sha256=cast(tuple[str, str], claims),
    )
    execution_identity = paired_screen_arm_execution_identity(
        pair_execution_identity_sha256=pair_identity,
        arm="candidate",
        model_canonical_sha256=canonical_goal_manager_model_sha256(ready["base_model"]),
        arm_claim_sha256=_sha(arm.get("claim_sha256"), "candidate claim"),
        episode_id=_text(arm.get("episode_id"), "candidate episode"),
    )
    bound_identities = _string_list(
        _mapping(result.get("bindings"), "bindings").get("arm_execution_identity_sha256"),
        "arm identities",
    )
    if len(bound_identities) != 2:
        raise AcquisitionSuccessorFitError("arm_identities")
    if (
        pair_identity
        != _mapping(result.get("bindings"), "bindings").get("pair_execution_identity_sha256")
        or execution_identity != bound_identities[1]
    ):
        raise AcquisitionSuccessorFitError("paired_execution_identity")
    slot_id = _text(root.get("capture_id"), "capture")
    source_commit = _text(
        _mapping(result.get("source_verification"), "source").get("execution_git_commit"),
        "execution source",
    )
    return load_repeatable_goal_manager_development_episode(
        reader,
        expected_campaign_id=_sha(plan.get("screen_id"), "screen"),
        expected_trial_claim_sha256=_sha(arm.get("claim_sha256"), "candidate claim"),
        expected_episode_id=cast(str, ready["candidate_episode_id"]),
        expected_root_lineage_id=_text(root.get("root_lineage_id"), "root lineage"),
        expected_seed=_integer(_mapping(plan.get("behavior"), "behavior").get("seed"), "seed"),
        expected_execution_identity_sha256=execution_identity,
        expected_context_catalog_sha256=cast(
            GoalManagerContextCatalog, ready["catalog"]
        ).catalog_sha256,
        expected_context_id=cast(GoalManagerContextCatalog, ready["catalog"])
        .entry(slot_id)
        .context_id,
        expected_binding_manifest_sha256=_sha(root.get("binding_manifest_sha256"), "binding"),
        expected_state_sha256=_sha(root.get("state_sha256"), "state"),
        expected_envelope_sha256=_sha(root.get("envelope_sha256"), "envelope"),
        expected_first_question_sha256=_sha(root.get("question_sha256"), "question"),
        expected_first_policy_context_sha256=_sha(
            root.get("policy_context_sha256"), "policy context"
        ),
        expected_first_available_menu_sha256=_sha(root.get("available_menu_sha256"), "menu"),
        expected_model=cast(GoalManagerLinearModel, ready["base_model"]),
        expected_source_commit=source_commit,
    )


def _new_output_bundle(path: Path, root: Path) -> Path:
    resolved_parent = path.parent.resolve(strict=True)
    resolved = resolved_parent / path.name
    if (
        not resolved.is_relative_to(root)
        or resolved.exists()
        or path.is_symlink()
        or not path.name.startswith("goal-manager-acquisition-successor-")
    ):
        raise AcquisitionSuccessorFitError("output_contract")
    return resolved


def _publish_bundle(
    destination: Path,
    *,
    model_payload: bytes,
    summary_payload: bytes,
    fit_identity_sha256: str,
) -> str:
    temporary: Path | None = None
    try:
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.partial-", dir=destination.parent)
        )
        os.chmod(temporary, 0o700)
        model_sha256 = _write_bundle_file(temporary / "model.json", model_payload)
        summary_sha256 = _write_bundle_file(temporary / "summary.json", summary_payload)
        manifest = {
            "schema": "pokemon.red.goal-manager-acquisition-successor-bundle.v1",
            "status": "complete",
            "fit_identity_sha256": fit_identity_sha256,
            "files": {
                "model.json": model_sha256,
                "summary.json": summary_sha256,
            },
        }
        manifest_payload = _canonical_line(manifest)
        manifest_sha256 = _write_bundle_file(temporary / "manifest.json", manifest_payload)
        directory = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        atomic_no_replace_rename(temporary, destination)
        parent = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        return manifest_sha256
    except OSError:
        raise AcquisitionSuccessorFitError("bundle_publication") from None
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)


def _write_bundle_file(path: Path, payload: bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise OSError("short write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return hashlib.sha256(payload).hexdigest()


def _read_document(path: Path, subject: str) -> tuple[bytes, Mapping[str, object]]:
    payload = _read_regular(path, subject)
    return payload, _document(payload, subject)


def _require_project_import_origins() -> None:
    if _PRELOADED_PROJECT_MODULES:
        raise AcquisitionSuccessorFitError("source_import_authentication")
    package_root = (_BOOTSTRAP_SRC / "pokemon_red_completion").resolve()
    for name, module in tuple(sys.modules.items()):
        if name != "pokemon_red_completion" and not name.startswith("pokemon_red_completion."):
            continue
        raw = getattr(module, "__file__", None)
        if not isinstance(raw, str):
            raise AcquisitionSuccessorFitError("source_import_authentication")
        path = Path(raw)
        try:
            metadata = path.lstat()
            resolved = path.resolve(strict=True)
        except OSError:
            raise AcquisitionSuccessorFitError("source_import_authentication") from None
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or not resolved.is_relative_to(package_root)
        ):
            raise AcquisitionSuccessorFitError("source_import_authentication")


def _read_regular(path: Path, subject: str) -> bytes:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not path.is_file() or metadata.st_size > 8 * 1024 * 1024:
            raise OSError
        return path.read_bytes()
    except OSError:
        raise AcquisitionSuccessorFitError(f"{subject.replace(' ', '_')}_read") from None


def _document(payload: bytes, subject: str) -> Mapping[str, object]:
    try:
        value = json.loads(
            payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except (ValueError, UnicodeDecodeError):
        raise AcquisitionSuccessorFitError(f"{subject.replace(' ', '_')}_json") from None
    return _mapping(value, subject)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    del value
    raise ValueError("non-finite JSON")


def _mapping(value: object, subject: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AcquisitionSuccessorFitError(f"{subject.replace(' ', '_')}_contract")
    return cast(Mapping[str, Any], value)


def _list(value: object, subject: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise AcquisitionSuccessorFitError(f"{subject.replace(' ', '_')}_contract")
    return cast(list[Mapping[str, Any]], value)


def _string_list(value: object, subject: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(row, str) for row in value):
        raise AcquisitionSuccessorFitError(f"{subject.replace(' ', '_')}_contract")
    return cast(list[str], value)


def _text(value: object, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise AcquisitionSuccessorFitError(f"{subject.replace(' ', '_')}_contract")
    return value


def _sha(value: object, subject: str) -> str:
    text = _text(value, subject)
    if _SHA256.fullmatch(text) is None:
        raise AcquisitionSuccessorFitError(f"{subject.replace(' ', '_')}_contract")
    return text


def _commit(value: object, subject: str) -> str:
    text = _text(value, subject)
    if _COMMIT.fullmatch(text) is None:
        raise AcquisitionSuccessorFitError(f"{subject.replace(' ', '_')}_contract")
    return text


def _integer(value: object, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise AcquisitionSuccessorFitError(f"{subject.replace(' ', '_')}_contract")
    return value


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_line(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


if __name__ == "__main__":
    raise SystemExit(main())
