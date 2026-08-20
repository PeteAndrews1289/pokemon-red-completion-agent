from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from pokemon_red_completion.living_dex_dependency_curriculum import (
    DevelopmentCommitmentRoster,
    DevelopmentCommitmentRow,
    build_rootless_living_dex_dependency_design,
    materialize_train_dependency_outcome,
)
from pokemon_red_completion.living_dex_dependency_integrity import (
    AuthenticatedDependencyEvaluationFit,
    DependencyEvaluationBundlePins,
    DependencyEvaluationFitIdentity,
    LivingDexDependencyIntegrityError,
    authenticate_dependency_evaluation_fit_bundle,
    dependency_evaluation_fit_manifest_document,
    dependency_evaluation_fit_terminal_document,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DependencyRankerFit,
    DependencyRankerModel,
    fit_dependency_ranker,
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


def _design():
    roster = DevelopmentCommitmentRoster(
        tuple(
            DevelopmentCommitmentRow(
                f"rootless-development-{index:016x}",
                f"{index + 1:064x}",
            )
            for index in range(4)
        )
    )
    return build_rootless_living_dex_dependency_design(roster)


def _bundle():
    design = _design()
    fit = fit_dependency_ranker(
        design,
        tuple(
            materialize_train_dependency_outcome(scenario) for scenario in design.train_scenarios
        ),
    )
    fit_bytes = _line(fit.to_dict())
    fit_identity = DependencyEvaluationFitIdentity(
        design_sha256=design.design_sha256,
        train_dataset_sha256=fit.train_dataset_sha256,
        fit_record_sha256=_sha(fit_bytes),
        fit_sha256=fit.fit_sha256,
        model_sha256=fit.model.model_sha256,
        fit_execution_manifest_sha256="e" * 64,
        executable_bundle_sha256="f" * 64,
    )
    manifest_bytes = _line(dependency_evaluation_fit_manifest_document(fit_identity))
    manifest_sha = _sha(manifest_bytes)
    terminal_bytes = _line(
        dependency_evaluation_fit_terminal_document(
            fit_identity,
            fit_manifest_record_sha256=manifest_sha,
        )
    )
    pins = DependencyEvaluationBundlePins(
        fit_identity=fit_identity,
        fit_manifest_record_sha256=manifest_sha,
        fit_terminal_record_sha256=_sha(terminal_bytes),
    )
    return design, fit, pins, fit_bytes, manifest_bytes, terminal_bytes


def test_exact_fit_bundle_join_authenticates_every_identity_without_development_data() -> None:
    design, fit, pins, fit_bytes, manifest_bytes, terminal_bytes = _bundle()

    authenticated = authenticate_dependency_evaluation_fit_bundle(
        design,
        pins=pins,
        fit_record_bytes=fit_bytes,
        fit_manifest_record_bytes=manifest_bytes,
        fit_terminal_record_bytes=terminal_bytes,
    )

    assert authenticated.fit == fit
    assert authenticated.model_sha256 == fit.model.model_sha256
    assert authenticated.public_dict() == {
        "schema": "pokemon.core.authenticated-rootless-dependency-evaluation-fit.v1",
        **pins.public_dict(),
        "all_semantic_bindings_joined": True,
        "development_payloads_opened": 0,
    }


@pytest.mark.parametrize(
    "field",
    (
        "design_sha256",
        "train_dataset_sha256",
        "fit_sha256",
        "model_sha256",
        "fit_execution_manifest_sha256",
        "executable_bundle_sha256",
    ),
)
def test_fit_bundle_join_rejects_each_swapped_semantic_binding(field: str) -> None:
    design, _, pins, fit_bytes, manifest_bytes, terminal_bytes = _bundle()
    altered_identity = replace(pins.fit_identity, **{field: "a" * 64})
    altered_pins = DependencyEvaluationBundlePins(
        fit_identity=altered_identity,
        fit_manifest_record_sha256=pins.fit_manifest_record_sha256,
        fit_terminal_record_sha256=pins.fit_terminal_record_sha256,
    )

    with pytest.raises(LivingDexDependencyIntegrityError):
        authenticate_dependency_evaluation_fit_bundle(
            design,
            pins=altered_pins,
            fit_record_bytes=fit_bytes,
            fit_manifest_record_bytes=manifest_bytes,
            fit_terminal_record_bytes=terminal_bytes,
        )


def test_fit_bundle_join_rejects_self_consistent_swapped_model_record() -> None:
    design, fit, pins, _, manifest_bytes, terminal_bytes = _bundle()
    swapped_model = DependencyRankerModel(
        fit.model.feature_names,
        tuple(weight + 0.25 for weight in fit.model.weights),
        fit.model.train_dataset_sha256,
    )
    swapped_fit = DependencyRankerFit(
        design_sha256=fit.design_sha256,
        train_dataset_sha256=fit.train_dataset_sha256,
        model=swapped_model,
        baseline_cross_entropy=fit.baseline_cross_entropy,
        fitted_cross_entropy=fit.fitted_cross_entropy,
        train_accuracy=fit.train_accuracy,
    )
    swapped_bytes = _line(swapped_fit.to_dict())
    record_rebound_pins = DependencyEvaluationBundlePins(
        fit_identity=replace(
            pins.fit_identity,
            fit_record_sha256=_sha(swapped_bytes),
        ),
        fit_manifest_record_sha256=pins.fit_manifest_record_sha256,
        fit_terminal_record_sha256=pins.fit_terminal_record_sha256,
    )

    with pytest.raises(LivingDexDependencyIntegrityError, match="semantic identity"):
        authenticate_dependency_evaluation_fit_bundle(
            design,
            pins=record_rebound_pins,
            fit_record_bytes=swapped_bytes,
            fit_manifest_record_bytes=manifest_bytes,
            fit_terminal_record_bytes=terminal_bytes,
        )


@pytest.mark.parametrize("record", ("manifest", "terminal"))
def test_fit_bundle_join_rejects_rehashed_binding_record_mutations(record: str) -> None:
    design, _, pins, fit_bytes, manifest_bytes, terminal_bytes = _bundle()
    if record == "manifest":
        document = json.loads(manifest_bytes)
        document["executable_bundle_sha256"] = "1" * 64
        manifest_bytes = _line(document)
        pins = DependencyEvaluationBundlePins(
            fit_identity=pins.fit_identity,
            fit_manifest_record_sha256=_sha(manifest_bytes),
            fit_terminal_record_sha256=pins.fit_terminal_record_sha256,
        )
    else:
        document = json.loads(terminal_bytes)
        document["fit_execution_manifest_sha256"] = "2" * 64
        terminal_bytes = _line(document)
        pins = DependencyEvaluationBundlePins(
            fit_identity=pins.fit_identity,
            fit_manifest_record_sha256=pins.fit_manifest_record_sha256,
            fit_terminal_record_sha256=_sha(terminal_bytes),
        )

    with pytest.raises(LivingDexDependencyIntegrityError, match="semantic identity"):
        authenticate_dependency_evaluation_fit_bundle(
            design,
            pins=pins,
            fit_record_bytes=fit_bytes,
            fit_manifest_record_bytes=manifest_bytes,
            fit_terminal_record_bytes=terminal_bytes,
        )


def test_fit_bundle_join_rejects_fresh_self_hashed_replacement_against_frozen_pins() -> None:
    design, fit, pins, _, _, _ = _bundle()
    replacement_model = DependencyRankerModel(
        fit.model.feature_names,
        tuple(weight - 0.5 for weight in fit.model.weights),
        fit.model.train_dataset_sha256,
    )
    replacement_fit = DependencyRankerFit(
        design_sha256=fit.design_sha256,
        train_dataset_sha256=fit.train_dataset_sha256,
        model=replacement_model,
        baseline_cross_entropy=fit.baseline_cross_entropy,
        fitted_cross_entropy=fit.fitted_cross_entropy,
        train_accuracy=fit.train_accuracy,
    )
    replacement_fit_bytes = _line(replacement_fit.to_dict())
    replacement_identity = replace(
        pins.fit_identity,
        fit_record_sha256=_sha(replacement_fit_bytes),
        fit_sha256=replacement_fit.fit_sha256,
        model_sha256=replacement_model.model_sha256,
    )
    replacement_manifest = _line(dependency_evaluation_fit_manifest_document(replacement_identity))
    replacement_terminal = _line(
        dependency_evaluation_fit_terminal_document(
            replacement_identity,
            fit_manifest_record_sha256=_sha(replacement_manifest),
        )
    )

    with pytest.raises(LivingDexDependencyIntegrityError):
        authenticate_dependency_evaluation_fit_bundle(
            design,
            pins=pins,
            fit_record_bytes=replacement_fit_bytes,
            fit_manifest_record_bytes=replacement_manifest,
            fit_terminal_record_bytes=replacement_terminal,
        )


def test_fit_bundle_join_rejects_noncanonical_and_duplicate_json() -> None:
    design, _, pins, fit_bytes, _, terminal_bytes = _bundle()
    duplicate_manifest = (
        b'{"schema":"pokemon.core.rootless-dependency-evaluation-fit-manifest.v1",'
        b'"schema":"pokemon.core.rootless-dependency-evaluation-fit-manifest.v1"}\n'
    )
    rebound = DependencyEvaluationBundlePins(
        fit_identity=pins.fit_identity,
        fit_manifest_record_sha256=_sha(duplicate_manifest),
        fit_terminal_record_sha256=pins.fit_terminal_record_sha256,
    )
    with pytest.raises(LivingDexDependencyIntegrityError, match="canonical JSON"):
        authenticate_dependency_evaluation_fit_bundle(
            design,
            pins=rebound,
            fit_record_bytes=fit_bytes,
            fit_manifest_record_bytes=duplicate_manifest,
            fit_terminal_record_bytes=terminal_bytes,
        )


def test_authenticated_fit_cannot_be_constructed_without_verifier() -> None:
    _, fit, pins, _, _, _ = _bundle()
    with pytest.raises(LivingDexDependencyIntegrityError):
        AuthenticatedDependencyEvaluationFit(
            fit=fit,
            pins=pins,
            _validation_token=object(),
        )
