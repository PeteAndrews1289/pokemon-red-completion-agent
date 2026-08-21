#!/usr/bin/env python3
"""One-shot fit or aggregate-only sealed comparison stages for rootless V2."""

# ruff: noqa: E402 -- script-local manifest helpers precede package imports.

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Never

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
while str(SCRIPTS_ROOT) in sys.path:
    sys.path.remove(str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT))

from freeze_rootless_execution_manifest import _current_public_bindings
from public_execution_manifest import canonical_manifest_line, read_public_manifest
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
from pokemon_red_completion.living_dex_dependency_comparison_v2 import (
    DEPENDENCY_COMPARISON_FAILURE_KIND_V2,
    DEPENDENCY_COMPARISON_FAILURE_SCHEMA_V2,
    DEPENDENCY_COMPARISON_RESULT_KIND_V2,
    DEPENDENCY_COMPARISON_TERMINAL_KIND_V2,
    claim_v2_comparison_before_payload_open,
    materialize_claimed_v2_comparison,
    preflight_v2_comparison,
    publish_claimed_v2_comparison,
    v2_comparison_failure_record_id,
    v2_comparison_record_ids,
)
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
    DependencyComparisonClaimV2,
    DependencyFitClaimV2,
    EvaluationExecutionBindingV2,
    RootlessDependencyEvaluationDesignV2,
    build_dependency_comparison_claim_v2,
    build_dependency_fit_claim_v2,
    rootless_dependency_counter_contract_v2,
)
from pokemon_red_completion.living_dex_dependency_integrity import (
    DependencyEvaluationBundlePins,
    DependencyEvaluationFitIdentity,
)
from pokemon_red_completion.living_dex_dependency_integrity_v2 import (
    DEPENDENCY_EVALUATION_FIT_FAILURE_KIND_V2,
    DEPENDENCY_EVALUATION_FIT_MANIFEST_KIND_V2,
    DEPENDENCY_EVALUATION_FIT_RECORD_KIND_V2,
    DEPENDENCY_EVALUATION_FIT_TERMINAL_KIND_V2,
    authenticate_v2_dependency_evaluation_fit_bundle,
    claim_v2_fit_before_computation,
    dependency_fit_claim_from_manifest_document_v2,
    inventory_v2_development_metadata,
    materialize_claimed_v2_fit_bundle,
    publish_v2_fit_bundle,
    v2_fit_failure_record_id,
    v2_fit_record_ids,
)
from pokemon_red_completion.private_artifacts import PrivateArtifactRoot, open_private_root
from pokemon_red_completion.provenance import canonical_sha256

RUNNER_RELATIVE = "scripts/run_rootless_living_dex_dependency_learning_v2.py"
DEPENDENCIES = (
    "comparison_core=src/pokemon_red_completion/living_dex_dependency_comparison_v2.py",
    "design_core=src/pokemon_red_completion/living_dex_dependency_evaluation_v2.py",
    "integrity_core=src/pokemon_red_completion/living_dex_dependency_integrity_v2.py",
    "manifest_core=scripts/rootless_execution_manifest.py",
    "private_store=src/pokemon_red_completion/private_artifacts.py",
    "ranker=src/pokemon_red_completion/living_dex_dependency_ranker.py",
)


class RootlessDependencyLearningV2Error(RuntimeError):
    """The V2 fit or comparison preflight failed closed at a named stage."""


@dataclass(slots=True)
class _ComparisonRunState:
    """Retain only the facts needed for honest postclaim failure handling."""

    failure_stage: str = "comparison_authentication"
    claim_attempted: bool = False
    claim_consumed: bool = False
    completed: bool = False
    store: PrivateArtifactRoot | None = None
    claim: DependencyComparisonClaimV2 | None = None
    execution_manifest_sha256: str | None = None


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise RootlessDependencyLearningV2Error("arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("fit-preflight", "fit", "comparison-preflight", "comparison"),
        required=True,
    )
    parser.add_argument("--execution-manifest", type=Path, required=True)
    parser.add_argument("--expected-execution-manifest-sha256", required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--expected-design-document-sha256", required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--fit-source-commit")
    parser.add_argument("--fit-source-bundle-sha256")
    parser.add_argument("--fit-runner-sha256")
    parser.add_argument("--fit-runtime-sha256")
    parser.add_argument("--fit-claim-sha256")
    parser.add_argument("--fit-execution-identity-sha256")
    parser.add_argument("--train-dataset-sha256")
    parser.add_argument("--fit-record-sha256")
    parser.add_argument("--fit-sha256")
    parser.add_argument("--model-sha256")
    parser.add_argument("--fit-execution-manifest-sha256")
    parser.add_argument("--executable-bundle-sha256")
    parser.add_argument("--fit-manifest-record-sha256")
    parser.add_argument("--fit-terminal-record-sha256")
    parser.add_argument("--comparison-claim-sha256")
    parser.add_argument("--comparison-execution-identity-sha256")
    return parser


def main(argv: list[str] | None = None) -> int:
    stage = "public_design_authentication"
    claim_attempted = False
    claim_consumed = False
    store: PrivateArtifactRoot | None = None
    fit_claim: DependencyFitClaimV2 | None = None
    comparison_state = _ComparisonRunState()
    comparison_selected = False
    try:
        args = _parser().parse_args(argv)
        comparison_selected = args.mode in {"comparison-preflight", "comparison"}
        if comparison_selected:
            comparison_state.failure_stage = "comparison_public_design_authentication"
        design_document = _read_public_document(
            args.design,
            expected_sha256=args.expected_design_document_sha256,
        )
        design = RootlessDependencyEvaluationDesignV2.from_dict(design_document)
        stage = "public_manifest_authentication"
        if comparison_selected:
            comparison_state.failure_stage = "comparison_public_source_authentication"
        public_bindings = _current_public_bindings(
            lane_id=ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
            runner=RUNNER_RELATIVE,
            dependencies=list(DEPENDENCIES),
        )
        if args.mode in {"comparison-preflight", "comparison"}:
            result = _comparison_stage(
                args,
                design,
                public_bindings,
                execute=args.mode == "comparison",
                run_state=comparison_state,
            )
        else:
            fit_binding = _execution_binding("fit", public_bindings)
            fit_claim = build_dependency_fit_claim_v2(
                design,
                execution_binding=fit_binding,
            )
            semantic = _fit_semantic_bindings(
                design,
                fit_claim,
                design_document_sha256=args.expected_design_document_sha256,
            )
            gate_sha256 = _authenticate_gate(
                args,
                operation="fit",
                semantic_bindings=semantic,
                public_bindings=public_bindings,
                private_roles=(
                    "claim_registry",
                    "private_artifact_root",
                    "sealed_development_manifests",
                ),
            )
            stage = "metadata_only_fit_inventory"
            store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
            inventory_v2_development_metadata(design.development_roster, store=store)
            registry = open_fixed_account_claim_registry()
            with fixed_account_claim_registry_lease(
                registry,
                exclusive=args.mode == "fit",
            ):
                if not _fit_local_namespace_is_available(store, fit_claim):
                    raise RootlessDependencyLearningV2Error("fit_local_namespace")
                available = root_claim_is_available(
                    registry,
                    fit_claim.semantic_claim_sha256,
                )
                if not available:
                    raise RootlessDependencyLearningV2Error("fit_claim")
                if args.mode == "fit-preflight":
                    result = {
                        "schema": "pokemon.core.rootless-dependency-fit-preflight.v2",
                        "status": "ready_identity_unclaimed",
                        "design_sha256": design.design_sha256,
                        "development_roster_sha256": design.development_roster.roster_sha256,
                        "fit_claim_sha256": fit_claim.semantic_claim_sha256,
                        "fit_execution_identity_sha256": fit_claim.execution_identity_sha256,
                        "execution_manifest_sha256": gate_sha256,
                        "development_manifest_rows_authenticated": 4,
                        "development_payloads_opened": 0,
                        "development_payloads_decoded": 0,
                        "fit_claim_consumed": False,
                        "model_fits_added": 0,
                    }
                else:
                    stage = "fit_claim_before_computation"

                    def claim_writer(value: DependencyFitClaimV2) -> None:
                        nonlocal claim_attempted, claim_consumed
                        if value is not fit_claim:
                            raise RootlessDependencyLearningV2Error("fit_claim")
                        expected = {
                            "schema": "pokemon.red.fresh-composition-root-claim.v1",
                            "root_consumption_sha256": fit_claim.semantic_claim_sha256,
                            "execution_identity_sha256": fit_claim.execution_identity_sha256,
                            "source_commit": public_bindings["source_commit"],
                            "runner_sha256": public_bindings["runner_sha256"],
                        }
                        claim_attempted = True
                        try:
                            write_root_claim(
                                registry,
                                root_consumption_sha256=fit_claim.semantic_claim_sha256,
                                execution_identity_sha256=(fit_claim.execution_identity_sha256),
                                source_commit=public_bindings["source_commit"],
                                runner_sha256=public_bindings["runner_sha256"],
                            )
                        except Exception:
                            try:
                                claim_consumed = (
                                    read_root_claim(
                                        registry,
                                        fit_claim.semantic_claim_sha256,
                                    )
                                    == expected
                                )
                            except Exception:
                                claim_consumed = False
                            raise
                        claim_consumed = True

                    claimed = claim_v2_fit_before_computation(
                        fit_claim,
                        claim_writer=claim_writer,
                    )
                    stage = "fit_computation_and_publication"
                    bundle = materialize_claimed_v2_fit_bundle(
                        design,
                        claimed_fit=claimed,
                        fit_execution_manifest_sha256=gate_sha256,
                        executable_bundle_sha256=canonical_sha256(
                            {
                                "schema": "pokemon.core.rootless-dependency-fit-executable.v2",
                                "public_bindings": public_bindings,
                            }
                        ),
                    )
                    published = publish_v2_fit_bundle(store, bundle)
                    result = {
                        **published.bundle.public_dict(),
                        "status": "completed_compliance_replacement_fit",
                        "fit_record_manifest_sha256": (published.fit_record_manifest_sha256),
                        "fit_manifest_manifest_sha256": (published.fit_manifest_manifest_sha256),
                        "fit_terminal_manifest_sha256": (published.fit_terminal_manifest_sha256),
                        "fit_claim_consumed": True,
                    }
        print(json.dumps({**result, "private_path_fields": 0}, sort_keys=True))
        return 0
    except Exception:
        comparison_attempted = comparison_state.claim_attempted
        comparison_consumed = comparison_state.claim_consumed
        any_attempted = claim_attempted or comparison_attempted
        any_consumed = claim_consumed or comparison_consumed
        failure_stage = comparison_state.failure_stage if comparison_selected else stage
        if (
            comparison_consumed
            and not comparison_state.completed
            and comparison_state.store is not None
            and comparison_state.claim is not None
        ):
            _retain_failed_comparison_terminal(
                comparison_state.store,
                comparison_state.claim,
                failure_stage,
                execution_manifest_sha256=comparison_state.execution_manifest_sha256,
            )
        elif claim_consumed and store is not None and fit_claim is not None:
            _retain_failed_fit_terminal(store, fit_claim, stage)
        print(
            json.dumps(
                {
                    "schema": "pokemon.core.rootless-dependency-learning-failure.v2",
                    "status": "failed_closed",
                    "failure_stage": failure_stage,
                    "claim_state": (
                        "consumed"
                        if any_consumed
                        else "uncertain"
                        if any_attempted
                        else "not_attempted"
                    ),
                    "claim_consumed": any_consumed,
                    "effects": ("not_attested" if any_attempted else "verified_zero"),
                    "retry_allowed": not any_attempted,
                    **_comparison_counter_deltas(completed=False),
                    "private_path_fields": 0,
                },
                sort_keys=True,
            )
        )
        return 1


def _comparison_preflight(
    args: argparse.Namespace,
    design: RootlessDependencyEvaluationDesignV2,
    public_bindings: Mapping[str, str],
) -> dict[str, object]:
    """Compatibility wrapper for the metadata-only comparison preflight."""

    return _comparison_stage(
        args,
        design,
        public_bindings,
        execute=False,
        run_state=_ComparisonRunState(),
    )


def _comparison_stage(
    args: argparse.Namespace,
    design: RootlessDependencyEvaluationDesignV2,
    public_bindings: Mapping[str, str],
    *,
    execute: bool,
    run_state: _ComparisonRunState,
) -> dict[str, object]:
    run_state.failure_stage = "comparison_identity_authentication"
    fit_binding = EvaluationExecutionBindingV2(
        operation="fit",
        source_commit=_commit(args.fit_source_commit),
        source_bundle_sha256=_sha(args.fit_source_bundle_sha256),
        runner_sha256=_sha(args.fit_runner_sha256),
        runtime_sha256=_sha(args.fit_runtime_sha256),
    )
    fit_claim = build_dependency_fit_claim_v2(design, execution_binding=fit_binding)
    if fit_claim.semantic_claim_sha256 != _sha(
        args.fit_claim_sha256
    ) or fit_claim.execution_identity_sha256 != _sha(args.fit_execution_identity_sha256):
        raise RootlessDependencyLearningV2Error("fit_claim_authentication")
    fit_identity = DependencyEvaluationFitIdentity(
        design_sha256=design.design_sha256,
        train_dataset_sha256=_sha(args.train_dataset_sha256),
        fit_record_sha256=_sha(args.fit_record_sha256),
        fit_sha256=_sha(args.fit_sha256),
        model_sha256=_sha(args.model_sha256),
        fit_execution_manifest_sha256=_sha(args.fit_execution_manifest_sha256),
        executable_bundle_sha256=_sha(args.executable_bundle_sha256),
    )
    pins = DependencyEvaluationBundlePins(
        fit_identity=fit_identity,
        fit_manifest_record_sha256=_sha(args.fit_manifest_record_sha256),
        fit_terminal_record_sha256=_sha(args.fit_terminal_record_sha256),
    )
    comparison_binding = _execution_binding("comparison", public_bindings)
    comparison_claim = build_dependency_comparison_claim_v2(
        design,
        fit_claim=fit_claim,
        fit_bundle_pins=pins,
        execution_binding=comparison_binding,
    )
    if comparison_claim.semantic_claim_sha256 != _sha(
        args.comparison_claim_sha256
    ) or comparison_claim.execution_identity_sha256 != _sha(
        args.comparison_execution_identity_sha256
    ):
        raise RootlessDependencyLearningV2Error("comparison_claim_authentication")
    run_state.claim = comparison_claim
    semantic = {
        "comparison_claim_sha256": comparison_claim.semantic_claim_sha256,
        "comparison_execution_identity_sha256": (comparison_claim.execution_identity_sha256),
        "design_document_sha256": _sha(args.expected_design_document_sha256),
        "design_sha256": design.design_sha256,
        "development_roster_sha256": design.development_roster.roster_sha256,
        "fit_claim_sha256": fit_claim.semantic_claim_sha256,
        "fit_execution_identity_sha256": fit_claim.execution_identity_sha256,
        "fit_execution_manifest_sha256": pins.fit_identity.fit_execution_manifest_sha256,
        "fit_sha256": pins.fit_identity.fit_sha256,
        "fit_manifest_record_sha256": pins.fit_manifest_record_sha256,
        "fit_record_sha256": pins.fit_identity.fit_record_sha256,
        "fit_terminal_record_sha256": pins.fit_terminal_record_sha256,
        "model_sha256": pins.fit_identity.model_sha256,
        "train_dataset_sha256": pins.fit_identity.train_dataset_sha256,
        "executable_bundle_sha256": pins.fit_identity.executable_bundle_sha256,
    }
    run_state.failure_stage = "comparison_public_manifest_authentication"
    gate_sha256 = _authenticate_gate(
        args,
        operation="comparison" if execute else "comparison-preflight",
        semantic_bindings=semantic,
        public_bindings=public_bindings,
        private_roles=tuple(
            sorted(
                (
                    "claim_registry",
                    "fit_bundle_records",
                    "private_artifact_root",
                    ("sealed_development_payloads" if execute else "sealed_development_manifests"),
                )
            )
        ),
    )
    run_state.execution_manifest_sha256 = gate_sha256
    registry = open_fixed_account_claim_registry()
    with fixed_account_claim_registry_lease(registry, exclusive=execute):
        run_state.failure_stage = "comparison_fit_claim_authentication"
        expected_fit_claim = {
            "schema": "pokemon.red.fresh-composition-root-claim.v1",
            "root_consumption_sha256": fit_claim.semantic_claim_sha256,
            "execution_identity_sha256": fit_claim.execution_identity_sha256,
            "source_commit": fit_claim.execution_binding.source_commit,
            "runner_sha256": fit_claim.execution_binding.runner_sha256,
        }
        if read_root_claim(registry, fit_claim.semantic_claim_sha256) != expected_fit_claim:
            raise RootlessDependencyLearningV2Error("fit_claim_authentication")
        store = open_private_root(args.private_root, repository_root=PROJECT_ROOT)
        run_state.store = store
        run_state.failure_stage = "comparison_fit_bundle_authentication"
        fit_id, manifest_id, terminal_id = v2_fit_record_ids(fit_claim.execution_identity_sha256)
        fit_record = store.find_sealed_record(
            fit_id,
            expected_kind=DEPENDENCY_EVALUATION_FIT_RECORD_KIND_V2,
        )
        manifest_record = store.find_sealed_record(
            manifest_id,
            expected_kind=DEPENDENCY_EVALUATION_FIT_MANIFEST_KIND_V2,
        )
        terminal_record = store.find_sealed_record(
            terminal_id,
            expected_kind=DEPENDENCY_EVALUATION_FIT_TERMINAL_KIND_V2,
        )
        if fit_record is None or manifest_record is None or terminal_record is None:
            raise RootlessDependencyLearningV2Error("fit_bundle_authentication")
        parsed_claim = dependency_fit_claim_from_manifest_document_v2(manifest_record.read())
        if parsed_claim.public_dict() != fit_claim.public_dict():
            raise RootlessDependencyLearningV2Error("fit_bundle_authentication")
        authenticated = authenticate_v2_dependency_evaluation_fit_bundle(
            design,
            fit_claim=fit_claim,
            pins=pins,
            fit_record_bytes=canonical_manifest_line(fit_record.read()),
            fit_manifest_record_bytes=canonical_manifest_line(manifest_record.read()),
            fit_terminal_record_bytes=canonical_manifest_line(terminal_record.read()),
        )
        prepared = preflight_v2_comparison(
            design,
            comparison_claim,
            authenticated_fit=authenticated,
            metadata_store=store,
            claim_is_available=lambda identity: root_claim_is_available(
                registry,
                identity,
            ),
        )
        if not execute:
            return {
                **prepared.public_dict(),
                "execution_manifest_sha256": gate_sha256,
            }
        run_state.failure_stage = "comparison_local_namespace_authentication"
        if not _comparison_local_namespace_is_available(store, comparison_claim):
            raise RootlessDependencyLearningV2Error("comparison_local_namespace")

        run_state.failure_stage = "comparison_claim_before_payload_open"

        def comparison_claim_writer(value: DependencyComparisonClaimV2) -> None:
            if value is not comparison_claim:
                raise RootlessDependencyLearningV2Error("comparison_claim")
            expected = _root_claim_document(
                comparison_claim.semantic_claim_sha256,
                comparison_claim.execution_identity_sha256,
                source_commit=public_bindings["source_commit"],
                runner_sha256=public_bindings["runner_sha256"],
            )
            run_state.claim_attempted = True
            try:
                write_root_claim(
                    registry,
                    root_consumption_sha256=comparison_claim.semantic_claim_sha256,
                    execution_identity_sha256=comparison_claim.execution_identity_sha256,
                    source_commit=public_bindings["source_commit"],
                    runner_sha256=public_bindings["runner_sha256"],
                )
            except Exception:
                try:
                    run_state.claim_consumed = (
                        read_root_claim(
                            registry,
                            comparison_claim.semantic_claim_sha256,
                        )
                        == expected
                    )
                except Exception:
                    run_state.claim_consumed = False
                raise
            run_state.claim_consumed = True

        claimed = claim_v2_comparison_before_payload_open(
            prepared,
            claim_writer=comparison_claim_writer,
        )
        run_state.failure_stage = "comparison_payload_open_and_aggregate"
        materialized = materialize_claimed_v2_comparison(claimed, store=store)
        run_state.failure_stage = "comparison_result_and_terminal_publication"
        published = publish_claimed_v2_comparison(
            store,
            materialized,
            comparison_execution_manifest_sha256=gate_sha256,
        )
        run_state.completed = True
    return {
        "schema": "pokemon.core.rootless-dependency-comparison-execution.v2",
        "status": "completed_descriptive_v2_comparison",
        "design_sha256": design.design_sha256,
        "development_roster_sha256": design.development_roster.roster_sha256,
        "comparison_claim_sha256": comparison_claim.semantic_claim_sha256,
        "comparison_execution_identity_sha256": (comparison_claim.execution_identity_sha256),
        "execution_manifest_sha256": gate_sha256,
        "comparison_claim_consumed": True,
        "development_payloads_opened": 4,
        "development_payloads_decoded": 4,
        "aggregate": published.result.public_dict(),
        "comparison_result_record_sha256": published.result_record_sha256,
        "comparison_result_manifest_sha256": published.result_manifest_sha256,
        "comparison_terminal_record_sha256": published.terminal_record_sha256,
        "comparison_terminal_manifest_sha256": published.terminal_manifest_sha256,
        **_comparison_counter_deltas(completed=True),
        "claim_boundary": (
            "one descriptive four-row synthetic held-out comparison; not statistical "
            "promotion, gameplay competence, authority, or cross-title transfer"
        ),
    }


def _comparison_local_namespace_is_available(
    store: PrivateArtifactRoot,
    claim: DependencyComparisonClaimV2,
) -> bool:
    result_id, terminal_id = v2_comparison_record_ids(claim.execution_identity_sha256)
    checks = (
        (result_id, DEPENDENCY_COMPARISON_RESULT_KIND_V2),
        (terminal_id, DEPENDENCY_COMPARISON_TERMINAL_KIND_V2),
        (
            v2_comparison_failure_record_id(claim.execution_identity_sha256),
            DEPENDENCY_COMPARISON_FAILURE_KIND_V2,
        ),
    )
    return all(
        store.inspect_sealed_record_metadata(record_id, expected_kind=kind) is None
        for record_id, kind in checks
    )


def _comparison_counter_deltas(*, completed: bool) -> dict[str, int]:
    contract = rootless_dependency_counter_contract_v2()
    key = "completed_comparison" if completed else "failed_or_interrupted_comparison"
    selected = contract[key]
    if not isinstance(selected, dict) or any(
        not isinstance(name, str) or type(value) is not int  # noqa: E721
        for name, value in selected.items()
    ):
        raise RootlessDependencyLearningV2Error("comparison_counter_contract")
    return dict(selected)


def _fit_local_namespace_is_available(
    store: PrivateArtifactRoot,
    fit_claim: DependencyFitClaimV2,
) -> bool:
    fit_id, manifest_id, terminal_id = v2_fit_record_ids(fit_claim.execution_identity_sha256)
    checks = (
        (fit_id, DEPENDENCY_EVALUATION_FIT_RECORD_KIND_V2),
        (manifest_id, DEPENDENCY_EVALUATION_FIT_MANIFEST_KIND_V2),
        (terminal_id, DEPENDENCY_EVALUATION_FIT_TERMINAL_KIND_V2),
        (
            v2_fit_failure_record_id(fit_claim.execution_identity_sha256),
            DEPENDENCY_EVALUATION_FIT_FAILURE_KIND_V2,
        ),
    )
    return all(
        store.inspect_sealed_record_metadata(record_id, expected_kind=kind) is None
        for record_id, kind in checks
    )


def _root_claim_document(
    semantic_claim_sha256: str,
    execution_identity_sha256: str,
    *,
    source_commit: str,
    runner_sha256: str,
) -> dict[str, str]:
    return {
        "schema": "pokemon.red.fresh-composition-root-claim.v1",
        "root_consumption_sha256": semantic_claim_sha256,
        "execution_identity_sha256": execution_identity_sha256,
        "source_commit": source_commit,
        "runner_sha256": runner_sha256,
    }


def _fit_semantic_bindings(
    design: RootlessDependencyEvaluationDesignV2,
    fit_claim: DependencyFitClaimV2,
    *,
    design_document_sha256: str,
) -> dict[str, str]:
    return {
        "design_document_sha256": _sha(design_document_sha256),
        "design_sha256": design.design_sha256,
        "development_roster_sha256": design.development_roster.roster_sha256,
        "fit_claim_sha256": fit_claim.semantic_claim_sha256,
        "fit_execution_identity_sha256": fit_claim.execution_identity_sha256,
        "train_revalidation_sha256": design.train_revalidation_sha256,
    }


def _authenticate_gate(
    args: argparse.Namespace,
    *,
    operation: str,
    semantic_bindings: Mapping[str, str],
    public_bindings: Mapping[str, str],
    private_roles: tuple[str, ...],
) -> str:
    invocation = rootless_execution_invocation(
        lane_id=ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
        operation=operation,
        semantic_bindings=semantic_bindings,
        public_bindings=public_bindings,
        private_input_roles=tuple(sorted(private_roles)),
    )
    payload = read_public_manifest(
        args.execution_manifest,
        repository_root=PROJECT_ROOT,
    )
    authenticate_rootless_execution_manifest(
        payload,
        expected_manifest_sha256=args.expected_execution_manifest_sha256,
        invocation=invocation,
        current_public_bindings=public_bindings,
    )
    return hashlib.sha256(payload).hexdigest()


def _execution_binding(
    operation: str,
    public_bindings: Mapping[str, str],
) -> EvaluationExecutionBindingV2:
    return EvaluationExecutionBindingV2(
        operation=operation,  # type: ignore[arg-type]
        source_commit=public_bindings["source_commit"],
        source_bundle_sha256=public_bindings["source_bundle_sha256"],
        runner_sha256=public_bindings["runner_sha256"],
        runtime_sha256=public_bindings["runtime_sha256"],
    )


def _read_public_document(path: Path, *, expected_sha256: str) -> dict[str, object]:
    expected = _sha(expected_sha256)
    try:
        root = PROJECT_ROOT.resolve(strict=True)
        named = path.lstat()
        resolved = path.resolve(strict=True)
        payload = resolved.read_bytes()
        after = resolved.stat()
    except OSError:
        raise RootlessDependencyLearningV2Error("public_design_authentication") from None
    if (
        path.is_symlink()
        or not stat.S_ISREG(named.st_mode)
        or named.st_nlink != 1
        or root not in resolved.parents
        or named.st_dev != after.st_dev
        or named.st_ino != after.st_ino
        or not 1 <= len(payload) <= 128 * 1024
        or hashlib.sha256(payload).hexdigest() != expected
    ):
        raise RootlessDependencyLearningV2Error("public_design_authentication")
    try:
        document = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RootlessDependencyLearningV2Error("public_design_authentication") from None
    if not isinstance(document, dict) or canonical_manifest_line(document) != payload:
        raise RootlessDependencyLearningV2Error("public_design_authentication")
    return document


def _retain_failed_fit_terminal(
    store: PrivateArtifactRoot,
    fit_claim: DependencyFitClaimV2,
    failure_stage: str,
) -> None:
    try:
        execution_identity = fit_claim.execution_identity_sha256
        failure_id = v2_fit_failure_record_id(execution_identity)
        store.publish_sealed_record(
            failure_id,
            kind=DEPENDENCY_EVALUATION_FIT_FAILURE_KIND_V2,
            record={
                "schema": "pokemon-private.rootless-dependency-fit-failure-terminal.v2",
                "status": "failed",
                "fit_claim_sha256": fit_claim.semantic_claim_sha256,
                "fit_execution_identity_sha256": execution_identity,
                "failure_stage": failure_stage,
                "retry_allowed": False,
                "private_path_fields": 0,
            },
        )
    except Exception:
        return


def _retain_failed_comparison_terminal(
    store: PrivateArtifactRoot,
    comparison_claim: DependencyComparisonClaimV2,
    failure_stage: str,
    *,
    execution_manifest_sha256: str | None,
) -> None:
    """Best-effort immutable evidence for every consumed comparison failure."""

    try:
        manifest_sha256 = _sha(execution_manifest_sha256)
        execution_identity = comparison_claim.execution_identity_sha256
        failure_id = v2_comparison_failure_record_id(execution_identity)
        store.publish_sealed_record(
            failure_id,
            kind=DEPENDENCY_COMPARISON_FAILURE_KIND_V2,
            record={
                "schema": DEPENDENCY_COMPARISON_FAILURE_SCHEMA_V2,
                "status": "failed",
                "comparison_claim_sha256": comparison_claim.semantic_claim_sha256,
                "comparison_execution_identity_sha256": execution_identity,
                "comparison_execution_manifest_sha256": manifest_sha256,
                "design_sha256": comparison_claim.design_sha256,
                "development_roster_sha256": (comparison_claim.development_roster_sha256),
                "fit_claim_sha256": comparison_claim.fit_claim_sha256,
                "fit_execution_identity_sha256": (comparison_claim.fit_execution_identity_sha256),
                "fit_manifest_record_sha256": (
                    comparison_claim.fit_bundle_pins.fit_manifest_record_sha256
                ),
                "fit_terminal_record_sha256": (
                    comparison_claim.fit_bundle_pins.fit_terminal_record_sha256
                ),
                "fit_sha256": comparison_claim.fit_bundle_pins.fit_identity.fit_sha256,
                "model_sha256": comparison_claim.fit_bundle_pins.fit_identity.model_sha256,
                "train_dataset_sha256": (
                    comparison_claim.fit_bundle_pins.fit_identity.train_dataset_sha256
                ),
                "failure_stage": failure_stage,
                "development_payload_access": "not_attested",
                "development_rows_publicly_disclosed": 0,
                "retry_allowed": False,
                "private_path_fields": 0,
            },
        )
    except Exception:
        return


def _sha(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise RootlessDependencyLearningV2Error("public_binding_authentication")
    try:
        int(value, 16)
    except ValueError:
        raise RootlessDependencyLearningV2Error("public_binding_authentication") from None
    return value


def _commit(value: object) -> str:
    if not isinstance(value, str) or len(value) != 40:
        raise RootlessDependencyLearningV2Error("public_binding_authentication")
    try:
        int(value, 16)
    except ValueError:
        raise RootlessDependencyLearningV2Error("public_binding_authentication") from None
    return value


if __name__ == "__main__":
    raise SystemExit(main())
