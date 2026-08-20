#!/usr/bin/env python3
"""Fit the train-only dependency ranker or compare it once on sealed openings."""

# ruff: noqa: E402 -- script-local manifest and campaign modules load first.

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

import run_rootless_living_dex_dependency_campaign as campaign_runner
from freeze_rootless_execution_manifest import _bindings, _current_public_bindings
from public_execution_manifest import read_public_manifest
from rootless_execution_manifest import (
    authenticate_rootless_execution_manifest,
    rootless_execution_invocation,
)

from pokemon_red_completion.goal_manager_composition_qualification import (
    fixed_account_claim_registry_lease,
    open_fixed_account_claim_registry,
    read_root_claim,
    root_claim_is_available,
    write_root_claim,
)
from pokemon_red_completion.living_dex_dependency_comparison import (
    DependencyComparisonResult,
    compare_dependency_ranker,
)
from pokemon_red_completion.living_dex_dependency_curriculum import (
    COMPLETED_FIT_MANIFEST_SCHEMA,
    COMPLETED_FIT_TERMINAL_SCHEMA,
    DevelopmentCommitmentRoster,
    DevelopmentCommitmentRow,
    RootlessLivingDexDependencyDesign,
    authenticate_completed_dependency_fit_bundle,
    build_rootless_living_dex_dependency_design,
    materialize_train_dependency_outcome,
    verify_development_openings_after_fit,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DependencyRankerFit,
    DependencyRankerModel,
    fit_dependency_ranker,
)
from pokemon_red_completion.private_artifacts import (
    PrivateArtifactRoot,
    PrivateSealedRecord,
    open_private_root,
)
from pokemon_red_completion.provenance import canonical_sha256

LANE_ID = "rootless-living-dex-dependency-learning-v1"
RUNNER_RELATIVE = "scripts/run_rootless_living_dex_dependency_learning.py"
FIT_KIND = "rootless-dependency-ranker-fit"
FIT_MANIFEST_KIND = "rootless-dependency-fit-manifest"
FIT_TERMINAL_KIND = "rootless-dependency-fit-terminal"
COMPARISON_KIND = "rootless-dependency-comparison"
COMPARISON_TERMINAL_KIND = "rootless-dependency-comparison-terminal"
COMPARISON_TERMINAL_SCHEMA = "pokemon.private.rootless-dependency-comparison-terminal.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class RootlessLearningError(RuntimeError):
    """The one-shot dependency fit or comparison failed closed."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RootlessLearningError("arguments")


@dataclass(frozen=True, slots=True)
class _Gate:
    execution_manifest_sha256: str
    public_bindings: dict[str, str]
    semantic_bindings: dict[str, str]


@dataclass(frozen=True, slots=True)
class _Inventory:
    design: RootlessLivingDexDependencyDesign
    campaign_sha256: str
    plan_record_sha256: str
    admission: dict[str, object]
    opening_record_ids: tuple[str, ...]


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("preflight-fit", "fit", "preflight-compare", "compare"),
        required=True,
    )
    parser.add_argument("--execution-manifest", type=Path, required=True)
    parser.add_argument("--expected-execution-manifest-sha256", required=True)
    parser.add_argument("--dependency", action="append", required=True)
    parser.add_argument("--semantic-binding", action="append", required=True)
    parser.add_argument("--private-input-role", action="append", required=True)
    parser.add_argument("--public-roster", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--expected-campaign-sha256", required=True)
    parser.add_argument("--expected-fit-manifest-record-sha256")
    parser.add_argument("--expected-fit-terminal-record-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "arguments"
    try:
        args = _parser().parse_args(argv)
        compare_mode = args.mode in {"preflight-compare", "compare"}
        if compare_mode != bool(
            args.expected_fit_manifest_record_sha256 and args.expected_fit_terminal_record_sha256
        ):
            raise RootlessLearningError(stage)
        stage = "public_manifest_authentication"
        gate = _public_gate(args)
        stage = "learning_inventory_authentication"
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        inventory = _inventory(args, store, gate)
        if args.mode == "preflight-fit":
            stage = "fit_preflight"
            result = _preflight_fit(store, inventory, gate)
        elif args.mode == "fit":
            stage = "dependency_ranker_fit"
            result = _fit(store, inventory, gate)
        elif args.mode == "preflight-compare":
            stage = "comparison_preflight"
            result = _preflight_compare(args, store, inventory, gate)
        else:
            stage = "sealed_dependency_comparison"
            result = _compare(args, store, inventory, gate)
        print(json.dumps(result, allow_nan=False, sort_keys=True))
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "schema": "pokemon.core.rootless-dependency-learning-failure.v1",
                    "status": "failed_closed",
                    "failure_stage": stage,
                    "development_opening_payloads_disclosed_to_stage": (
                        "not_attested" if stage == "sealed_dependency_comparison" else 0
                    ),
                    "model_fits_added": 0,
                    "unseen_comparisons_added": 0,
                    "authority_promotions_added": 0,
                    "transfer_results_added": 0,
                    "rom_accesses": 0,
                    "controller_actions": 0,
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _public_gate(args: argparse.Namespace) -> _Gate:
    semantic = _bindings(args.semantic_binding)
    public = _current_public_bindings(
        lane_id=LANE_ID,
        runner=RUNNER_RELATIVE,
        dependencies=args.dependency,
    )
    invocation = rootless_execution_invocation(
        lane_id=LANE_ID,
        operation=args.mode,
        semantic_bindings=semantic,
        public_bindings=public,
        private_input_roles=tuple(sorted(args.private_input_role)),
    )
    payload = read_public_manifest(
        args.execution_manifest,
        repository_root=PROJECT_ROOT,
        forbidden_aliases=(args.public_roster,),
    )
    authenticate_rootless_execution_manifest(
        payload,
        expected_manifest_sha256=args.expected_execution_manifest_sha256,
        invocation=invocation,
        current_public_bindings=public,
    )
    return _Gate(args.expected_execution_manifest_sha256, public, semantic)


def _inventory(
    args: argparse.Namespace,
    store: PrivateArtifactRoot,
    gate: _Gate,
) -> _Inventory:
    roster_document, roster_sha = campaign_runner._load_public_roster(args.public_roster)
    if gate.semantic_bindings.get("development_roster_sha256") != roster_sha:
        raise RootlessLearningError("learning_inventory_authentication")
    commitments: list[DevelopmentCommitmentRow] = []
    opening_ids: list[str] = []
    for row in campaign_runner._roster_rows(roster_document):
        record = store.find_sealed_record(
            row["scenario_id"],
            expected_kind=campaign_runner.OPENING_KIND,
        )
        if record is None or (
            record.summary.record_sha256 != row["opening_sha256"]
            or record.summary.manifest_sha256 != row["record_manifest_sha256"]
        ):
            raise RootlessLearningError("learning_inventory_authentication")
        commitments.append(DevelopmentCommitmentRow(row["scenario_id"], row["opening_sha256"]))
        opening_ids.append(row["scenario_id"])
    design = build_rootless_living_dex_dependency_design(
        DevelopmentCommitmentRoster(tuple(commitments))
    )
    campaign_identity = canonical_sha256(
        {
            "schema": "pokemon.core.rootless-dependency-campaign-identity.v1",
            "design_sha256": design.design_sha256,
            "development_roster_sha256": roster_sha,
            "train_scenario_ids": [row.scenario_id for row in design.train_scenarios],
            "assigned_actions": [row.assigned_action.value for row in design.train_scenarios],
        }
    )
    if campaign_identity != args.expected_campaign_sha256:
        raise RootlessLearningError("learning_inventory_authentication")
    plan = store.find_sealed_record(
        f"rootless-dependency-plan-{campaign_identity[:24]}",
        expected_kind=campaign_runner.CAMPAIGN_PLAN_KIND,
    )
    if plan is None or (
        gate.semantic_bindings.get("campaign_plan_record_sha256") != plan.summary.record_sha256
    ):
        raise RootlessLearningError("learning_inventory_authentication")
    plan_document = plan.read()
    if (
        plan_document.get("campaign_sha256") != campaign_identity
        or plan_document.get("design_sha256") != design.design_sha256
        or plan_document.get("development_roster_sha256") != roster_sha
        or plan_document.get("train_scenario_ids")
        != [row.scenario_id for row in design.train_scenarios]
    ):
        raise RootlessLearningError("learning_inventory_authentication")
    admission = store.find_sealed_record(
        f"rootless-dependency-admission-{campaign_identity[:24]}",
        expected_kind=campaign_runner.TRAIN_ADMISSION_KIND,
    )
    if admission is None or (
        gate.semantic_bindings.get("train_admission_record_sha256")
        != admission.summary.record_sha256
    ):
        raise RootlessLearningError("learning_inventory_authentication")
    admission_document = admission.read()
    if (
        admission_document.get("schema") != campaign_runner.TRAIN_ADMISSION_SCHEMA
        or admission_document.get("status") != "admitted"
        or admission_document.get("campaign_sha256") != campaign_identity
        or admission_document.get("design_sha256") != design.design_sha256
        or admission_document.get("settled_outcomes") != 8
        or admission_document.get("positive_outcomes") != 4
        or admission_document.get("negative_outcomes") != 4
        or admission_document.get("development_opening_payloads_disclosed_to_stage") != 0
    ):
        raise RootlessLearningError("learning_inventory_authentication")
    return _Inventory(
        design,
        campaign_identity,
        plan.summary.record_sha256,
        admission_document,
        tuple(opening_ids),
    )


def _preflight_fit(
    store: PrivateArtifactRoot,
    inventory: _Inventory,
    gate: _Gate,
) -> dict[str, object]:
    del store
    identity = _fit_claim_identity(inventory)
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        available = root_claim_is_available(registry, identity)
    if not available:
        raise RootlessLearningError("fit_preflight")
    return {
        "schema": "pokemon.core.rootless-dependency-fit-preflight.v1",
        "status": "fit_ready_train_only",
        "campaign_sha256": inventory.campaign_sha256,
        "design_sha256": inventory.design.design_sha256,
        "train_examples": 8,
        "fit_identity_available": True,
        "development_opening_payloads_disclosed_to_stage": 0,
        "model_fits": 0,
        "unseen_comparisons": 0,
        "rom_accesses": 0,
        "controller_actions": 0,
        "private_path_fields": 0,
    }


def _fit(
    store: PrivateArtifactRoot,
    inventory: _Inventory,
    gate: _Gate,
) -> dict[str, object]:
    identity = _fit_claim_identity(inventory)
    execution_identity = _execution_identity("fit", inventory, gate)
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        if not root_claim_is_available(registry, identity):
            raise RootlessLearningError("dependency_ranker_fit")
        write_root_claim(
            registry,
            root_consumption_sha256=identity,
            execution_identity_sha256=execution_identity,
            source_commit=gate.public_bindings["source_commit"],
            runner_sha256=gate.public_bindings["runner_sha256"],
        )
        try:
            fit, fit_record, manifest_record, terminal_record = _materialize_fit_bundle(
                store,
                inventory,
                gate,
            )
        except Exception:
            _retain_learning_failure_terminal(
                store,
                inventory,
                operation="fit",
                failure_stage="dependency_ranker_fit",
            )
            raise RootlessLearningError("dependency_ranker_fit") from None
    return {
        "schema": "pokemon.core.rootless-dependency-fit-result.v1",
        "status": "completed_train_only_fit",
        "campaign_sha256": inventory.campaign_sha256,
        "design_sha256": inventory.design.design_sha256,
        "fit_sha256": fit.fit_sha256,
        "model_sha256": fit.model.model_sha256,
        "train_dataset_sha256": fit.train_dataset_sha256,
        "fit_record_sha256": fit_record.summary.record_sha256,
        "fit_manifest_record_sha256": manifest_record.summary.record_sha256,
        "fit_terminal_record_sha256": terminal_record.summary.record_sha256,
        "train_accuracy": fit.train_accuracy,
        "baseline_cross_entropy": fit.baseline_cross_entropy,
        "fitted_cross_entropy": fit.fitted_cross_entropy,
        "model_fits_added": 1,
        "rootless_dependency_fits_added": 1,
        "development_opening_payloads_disclosed_to_stage": 0,
        "unseen_comparisons_added": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "rom_accesses": 0,
        "controller_actions": 0,
        "private_path_fields": 0,
    }


def _materialize_fit_bundle(
    store: PrivateArtifactRoot,
    inventory: _Inventory,
    gate: _Gate,
) -> tuple[
    DependencyRankerFit,
    PrivateSealedRecord,
    PrivateSealedRecord,
    PrivateSealedRecord,
]:
    outcomes = []
    expected_hashes = inventory.admission.get("outcome_record_sha256")
    if not isinstance(expected_hashes, list) or len(expected_hashes) != 8:
        raise RootlessLearningError("dependency_ranker_fit")
    for scenario, expected_sha in zip(
        inventory.design.train_scenarios,
        expected_hashes,
        strict=True,
    ):
        record = store.find_sealed_record(
            campaign_runner._outcome_record_id(scenario.scenario_id),
            expected_kind=campaign_runner.OUTCOME_KIND,
        )
        outcome = materialize_train_dependency_outcome(scenario)
        if (
            record is None
            or record.summary.record_sha256 != expected_sha
            or record.read() != outcome.public_dict()
        ):
            raise RootlessLearningError("dependency_ranker_fit")
        outcomes.append(outcome)
    fit = fit_dependency_ranker(inventory.design, tuple(outcomes))
    fit_record = store.publish_sealed_record(
        _fit_record_id(inventory),
        kind=FIT_KIND,
        record=fit.to_dict(),
    )
    manifest_document = {
        "schema": COMPLETED_FIT_MANIFEST_SCHEMA,
        "design_sha256": inventory.design.design_sha256,
        "fit_sha256": fit.fit_sha256,
        "train_dataset_sha256": fit.train_dataset_sha256,
        "executable_bundle_sha256": canonical_sha256(gate.public_bindings),
    }
    manifest_record = store.publish_sealed_record(
        _fit_manifest_record_id(inventory),
        kind=FIT_MANIFEST_KIND,
        record=manifest_document,
    )
    terminal_document = {
        "schema": COMPLETED_FIT_TERMINAL_SCHEMA,
        "status": "completed",
        "design_sha256": inventory.design.design_sha256,
        "fit_sha256": fit.fit_sha256,
        "fit_manifest_sha256": manifest_record.summary.record_sha256,
    }
    terminal_record = store.publish_sealed_record(
        _fit_terminal_record_id(inventory),
        kind=FIT_TERMINAL_KIND,
        record=terminal_document,
    )
    return fit, fit_record, manifest_record, terminal_record


def _preflight_compare(
    args: argparse.Namespace,
    store: PrivateArtifactRoot,
    inventory: _Inventory,
    gate: _Gate,
) -> dict[str, object]:
    _, manifest_record, terminal_record = _authenticated_fit_records(
        args,
        store,
        inventory,
        gate,
    )
    registry = open_fixed_account_claim_registry()
    identity = _comparison_claim_identity(inventory, manifest_record.summary.record_sha256)
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        available = root_claim_is_available(registry, identity)
    if not available:
        raise RootlessLearningError("comparison_preflight")
    return {
        "schema": "pokemon.core.rootless-dependency-comparison-preflight.v1",
        "status": "sealed_comparison_ready",
        "campaign_sha256": inventory.campaign_sha256,
        "design_sha256": inventory.design.design_sha256,
        "fit_manifest_record_sha256": manifest_record.summary.record_sha256,
        "fit_terminal_record_sha256": terminal_record.summary.record_sha256,
        "comparison_identity_available": True,
        "development_commitments": 4,
        "development_opening_payloads_disclosed_to_stage": 0,
        "model_fits_added": 0,
        "unseen_comparisons_added": 0,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "rom_accesses": 0,
        "controller_actions": 0,
        "private_path_fields": 0,
    }


def _compare(
    args: argparse.Namespace,
    store: PrivateArtifactRoot,
    inventory: _Inventory,
    gate: _Gate,
) -> dict[str, object]:
    fit, manifest_record, terminal_record = _authenticated_fit_records(
        args,
        store,
        inventory,
        gate,
    )
    identity = _comparison_claim_identity(inventory, manifest_record.summary.record_sha256)
    execution_identity = _execution_identity("compare", inventory, gate)
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=True):
        if not root_claim_is_available(registry, identity):
            raise RootlessLearningError("sealed_dependency_comparison")
        write_root_claim(
            registry,
            root_consumption_sha256=identity,
            execution_identity_sha256=execution_identity,
            source_commit=gate.public_bindings["source_commit"],
            runner_sha256=gate.public_bindings["runner_sha256"],
        )
        try:
            comparison, terminal = _materialize_comparison(
                store,
                inventory,
                fit,
                manifest_record,
                terminal_record,
            )
        except Exception:
            _retain_learning_failure_terminal(
                store,
                inventory,
                operation="compare",
                failure_stage="sealed_dependency_comparison",
            )
            raise RootlessLearningError("sealed_dependency_comparison") from None
    return {
        **comparison.public_dict(),
        "status": "completed_descriptive_sealed_comparison",
        "comparison_terminal_record_sha256": terminal.summary.record_sha256,
        "development_opening_payloads_disclosed_to_stage": 4,
        "model_fits_added": 0,
        "unseen_comparisons_added": 1,
        "rootless_dependency_comparisons_added": 1,
        "authority_promotions_added": 0,
        "transfer_results_added": 0,
        "rom_accesses": 0,
        "controller_actions": 0,
        "private_path_fields": 0,
    }


def _materialize_comparison(
    store: PrivateArtifactRoot,
    inventory: _Inventory,
    fit: DependencyRankerFit,
    manifest_record: PrivateSealedRecord,
    terminal_record: PrivateSealedRecord,
) -> tuple[DependencyComparisonResult, PrivateSealedRecord]:
    authenticated = authenticate_completed_dependency_fit_bundle(
        inventory.design,
        _line(manifest_record.read()),
        manifest_record.summary.record_sha256,
        _line(terminal_record.read()),
        terminal_record.summary.record_sha256,
    )
    opening_payloads = []
    for record_id in inventory.opening_record_ids:
        record = store.find_sealed_record(
            record_id,
            expected_kind=campaign_runner.OPENING_KIND,
        )
        if record is None:
            raise RootlessLearningError("sealed_dependency_comparison")
        opening_payloads.append(_line(record.read()))
    verified = verify_development_openings_after_fit(
        inventory.design,
        authenticated_fit=authenticated,
        opening_payloads=tuple(opening_payloads),
    )
    comparison = compare_dependency_ranker(
        design_sha256=inventory.design.design_sha256,
        model=fit.model,
        verified=verified,
    )
    result_record = store.publish_sealed_record(
        _comparison_record_id(inventory),
        kind=COMPARISON_KIND,
        record=comparison.public_dict(),
    )
    terminal_document = {
        "schema": COMPARISON_TERMINAL_SCHEMA,
        "status": "completed",
        "campaign_sha256": inventory.campaign_sha256,
        "design_sha256": inventory.design.design_sha256,
        "fit_sha256": fit.fit_sha256,
        "comparison_sha256": comparison.comparison_sha256,
        "comparison_record_sha256": result_record.summary.record_sha256,
    }
    terminal = store.publish_sealed_record(
        _comparison_terminal_record_id(inventory),
        kind=COMPARISON_TERMINAL_KIND,
        record=terminal_document,
    )
    return comparison, terminal


def _retain_learning_failure_terminal(
    store: PrivateArtifactRoot,
    inventory: _Inventory,
    *,
    operation: str,
    failure_stage: str,
) -> None:
    if operation == "fit":
        record_id = _fit_terminal_record_id(inventory)
        kind = FIT_TERMINAL_KIND
    elif operation == "compare":
        record_id = _comparison_terminal_record_id(inventory)
        kind = COMPARISON_TERMINAL_KIND
    else:
        return
    try:
        store.publish_sealed_record(
            record_id,
            kind=kind,
            record={
                "schema": "pokemon.private.rootless-dependency-learning-failure-terminal.v1",
                "status": "failed",
                "operation": operation,
                "failure_stage": failure_stage,
                "campaign_sha256": inventory.campaign_sha256,
                "design_sha256": inventory.design.design_sha256,
                "private_path_fields": 0,
            },
        )
    except Exception:
        return


def _authenticated_fit_records(
    args: argparse.Namespace,
    store: PrivateArtifactRoot,
    inventory: _Inventory,
    gate: _Gate,
) -> tuple[DependencyRankerFit, PrivateSealedRecord, PrivateSealedRecord]:
    fit_execution_manifest_sha256 = gate.semantic_bindings.get("fit_execution_manifest_sha256")
    if not _is_sha(fit_execution_manifest_sha256):
        raise RootlessLearningError("fit_bundle_authentication")
    registry = open_fixed_account_claim_registry()
    expected_execution_identity = _execution_identity(
        "fit",
        inventory,
        gate,
        execution_manifest_sha256=fit_execution_manifest_sha256,
    )
    with fixed_account_claim_registry_lease(registry, exclusive=False):
        claim = read_root_claim(registry, _fit_claim_identity(inventory))
    if claim.get("execution_identity_sha256") != expected_execution_identity:
        raise RootlessLearningError("fit_bundle_authentication")
    fit_record = store.find_sealed_record(_fit_record_id(inventory), expected_kind=FIT_KIND)
    manifest_record = store.find_sealed_record(
        _fit_manifest_record_id(inventory), expected_kind=FIT_MANIFEST_KIND
    )
    terminal_record = store.find_sealed_record(
        _fit_terminal_record_id(inventory), expected_kind=FIT_TERMINAL_KIND
    )
    if fit_record is None or manifest_record is None or terminal_record is None:
        raise RootlessLearningError("fit_bundle_authentication")
    if (
        manifest_record.summary.record_sha256 != args.expected_fit_manifest_record_sha256
        or terminal_record.summary.record_sha256 != args.expected_fit_terminal_record_sha256
    ):
        raise RootlessLearningError("fit_bundle_authentication")
    fit = _fit_from_document(fit_record.read())
    authenticate_completed_dependency_fit_bundle(
        inventory.design,
        _line(manifest_record.read()),
        manifest_record.summary.record_sha256,
        _line(terminal_record.read()),
        terminal_record.summary.record_sha256,
    )
    return fit, manifest_record, terminal_record


def _fit_from_document(document: dict[str, object]) -> DependencyRankerFit:
    model_raw = document.get("model")
    if not isinstance(model_raw, dict):
        raise RootlessLearningError("fit_bundle_authentication")
    model = DependencyRankerModel.from_dict(model_raw)
    try:
        fit = DependencyRankerFit(
            design_sha256=document["design_sha256"],
            train_dataset_sha256=document["train_dataset_sha256"],
            model=model,
            baseline_cross_entropy=document["baseline_cross_entropy"],
            fitted_cross_entropy=document["fitted_cross_entropy"],
            train_accuracy=document["train_accuracy"],
        )
    except (KeyError, TypeError, ValueError):
        raise RootlessLearningError("fit_bundle_authentication") from None
    if document != fit.to_dict():
        raise RootlessLearningError("fit_bundle_authentication")
    return fit


def _fit_claim_identity(inventory: _Inventory) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.core.rootless-dependency-fit-claim.v1",
            "campaign_sha256": inventory.campaign_sha256,
            "design_sha256": inventory.design.design_sha256,
            "train_dataset_sha256": inventory.admission.get("train_dataset_sha256"),
        }
    )


def _comparison_claim_identity(inventory: _Inventory, fit_manifest_sha256: str) -> str:
    return canonical_sha256(
        {
            "schema": "pokemon.core.rootless-dependency-comparison-claim.v1",
            "campaign_sha256": inventory.campaign_sha256,
            "design_sha256": inventory.design.design_sha256,
            "fit_manifest_sha256": fit_manifest_sha256,
        }
    )


def _execution_identity(
    operation: str,
    inventory: _Inventory,
    gate: _Gate,
    *,
    execution_manifest_sha256: str | None = None,
) -> str:
    manifest_sha256 = execution_manifest_sha256 or gate.execution_manifest_sha256
    if not _is_sha(manifest_sha256):
        raise RootlessLearningError("claim_authentication")
    return canonical_sha256(
        {
            "schema": "pokemon.core.rootless-dependency-learning-execution.v1",
            "operation": operation,
            "campaign_sha256": inventory.campaign_sha256,
            "execution_manifest_sha256": manifest_sha256,
            "source_commit": gate.public_bindings["source_commit"],
            "runner_sha256": gate.public_bindings["runner_sha256"],
        }
    )


def _fit_record_id(inventory: _Inventory) -> str:
    return f"rootless-dependency-fit-{inventory.campaign_sha256[:24]}"


def _fit_manifest_record_id(inventory: _Inventory) -> str:
    return f"rootless-dependency-fit-manifest-{inventory.campaign_sha256[:24]}"


def _fit_terminal_record_id(inventory: _Inventory) -> str:
    return f"rootless-dependency-fit-terminal-{inventory.campaign_sha256[:24]}"


def _comparison_record_id(inventory: _Inventory) -> str:
    return f"rootless-dependency-comparison-{inventory.campaign_sha256[:24]}"


def _comparison_terminal_record_id(inventory: _Inventory) -> str:
    return f"rootless-dependency-comparison-terminal-{inventory.campaign_sha256[:16]}"


def _line(document: dict[str, object]) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        + b"\n"
    )


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


if __name__ == "__main__":
    raise SystemExit(main())
