from __future__ import annotations

import hashlib
import json

import pytest

from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    RootlessDependencyEvaluationDesignV2,
)
from pokemon_red_completion.living_dex_dependency_integrity import (
    DependencyEvaluationBundlePins,
    DependencyEvaluationFitIdentity,
)
from pokemon_red_completion.living_dex_dependency_integrity_v2 import (
    DEPENDENCY_EVALUATION_FIT_MANIFEST_SCHEMA_V2,
    DEPENDENCY_EVALUATION_FIT_TERMINAL_SCHEMA_V2,
    LivingDexDependencyIntegrityV2Error,
    authenticate_v2_dependency_evaluation_fit_bundle,
    dependency_evaluation_fit_manifest_document_v2,
    dependency_evaluation_fit_terminal_document_v2,
    inventory_v2_development_metadata,
)
from pokemon_red_completion.living_dex_dependency_provision_v2 import (
    provision_v2_development_commitments,
)


def _line(value: dict[str, object]) -> bytes:
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


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_inventory_v2_development_metadata_succeeds_on_valid_payloads() -> None:
    openings, roster = provision_v2_development_commitments()
    records = {opening.scenario_id: opening.canonical_private_bytes() for opening in openings}
    inventory_v2_development_metadata(roster, sealed_development_records=records)


def test_inventory_v2_development_metadata_fails_on_mutation() -> None:
    openings, roster = provision_v2_development_commitments()
    records = {opening.scenario_id: opening.canonical_private_bytes() for opening in openings}
    mutated_id = openings[0].scenario_id
    records[mutated_id] = records[mutated_id] + b" "
    with pytest.raises(LivingDexDependencyIntegrityV2Error, match="sealed record length differs"):
        inventory_v2_development_metadata(roster, sealed_development_records=records)


def test_v2_fit_bundle_rejects_mismatched_design() -> None:
    openings, roster = provision_v2_development_commitments()
    design = RootlessDependencyEvaluationDesignV2(roster)
    identity = DependencyEvaluationFitIdentity(
        design_sha256="0" * 64,
        train_dataset_sha256="1" * 64,
        fit_record_sha256="2" * 64,
        fit_sha256="3" * 64,
        model_sha256="4" * 64,
        fit_execution_manifest_sha256="5" * 64,
        executable_bundle_sha256="6" * 64,
    )
    pins = DependencyEvaluationBundlePins(
        fit_identity=identity,
        fit_manifest_record_sha256="7" * 64,
        fit_terminal_record_sha256="8" * 64,
    )
    with pytest.raises(
        LivingDexDependencyIntegrityV2Error, match="V2 evaluation design pin differs"
    ):
        authenticate_v2_dependency_evaluation_fit_bundle(
            design,
            pins=pins,
            fit_record_bytes=b"",
            fit_manifest_record_bytes=b"",
            fit_terminal_record_bytes=b"",
        )


def test_v2_manifest_document_uses_v2_schema() -> None:
    identity = DependencyEvaluationFitIdentity(
        design_sha256="0" * 64,
        train_dataset_sha256="1" * 64,
        fit_record_sha256="2" * 64,
        fit_sha256="3" * 64,
        model_sha256="4" * 64,
        fit_execution_manifest_sha256="5" * 64,
        executable_bundle_sha256="6" * 64,
    )
    doc = dependency_evaluation_fit_manifest_document_v2(identity)
    assert doc["schema"] == DEPENDENCY_EVALUATION_FIT_MANIFEST_SCHEMA_V2


def test_v2_terminal_document_uses_v2_schema() -> None:
    identity = DependencyEvaluationFitIdentity(
        design_sha256="0" * 64,
        train_dataset_sha256="1" * 64,
        fit_record_sha256="2" * 64,
        fit_sha256="3" * 64,
        model_sha256="4" * 64,
        fit_execution_manifest_sha256="5" * 64,
        executable_bundle_sha256="6" * 64,
    )
    doc = dependency_evaluation_fit_terminal_document_v2(
        identity, fit_manifest_record_sha256="7" * 64
    )
    assert doc["schema"] == DEPENDENCY_EVALUATION_FIT_TERMINAL_SCHEMA_V2
