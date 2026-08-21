from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    EvaluationExecutionBindingV2,
    RootlessDependencyEvaluationDesignV2,
    build_dependency_fit_claim_v2,
)
from pokemon_red_completion.living_dex_dependency_integrity import (
    DependencyEvaluationBundlePins,
)
from pokemon_red_completion.living_dex_dependency_integrity_v2 import (
    LivingDexDependencyIntegrityV2Error,
    authenticate_v2_dependency_evaluation_fit_bundle,
    claim_v2_fit_before_computation,
    dependency_train_examples_v2,
    inventory_v2_development_metadata,
    materialize_claimed_v2_fit_bundle,
    publish_v2_fit_bundle,
)
from pokemon_red_completion.living_dex_dependency_provision_v2 import (
    commitment_roster_from_metadata_v2,
    generate_v2_development_openings,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    fit_dependency_ranker_examples,
)
from pokemon_red_completion.private_artifacts import (
    SealedRecordManifestMetadata,
    initialize_private_root,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


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


def _metadata_design():
    openings = generate_v2_development_openings()
    metadata = tuple(
        SealedRecordManifestMetadata(
            record_id=opening.scenario_id,
            kind="rootless-living-dex-dependency-development-opening-v2",
            declared_record_sha256=hashlib.sha256(opening.canonical_private_bytes()).hexdigest(),
            manifest_sha256=_sha(f"manifest:{opening.scenario_id}"),
            declared_total_bytes=len(opening.canonical_private_bytes()),
        )
        for opening in openings
    )
    roster = commitment_roster_from_metadata_v2(metadata)
    return RootlessDependencyEvaluationDesignV2(roster), metadata


def _fit_claim(design: RootlessDependencyEvaluationDesignV2):
    binding = EvaluationExecutionBindingV2(
        operation="fit",
        source_commit="1" * 40,
        source_bundle_sha256=_sha("source-bundle-v2"),
        runner_sha256=_sha("runner-v2"),
        runtime_sha256=_sha("runtime-v2"),
    )
    return build_dependency_fit_claim_v2(design, execution_binding=binding)


def _bundle():
    design, metadata = _metadata_design()
    claim = _fit_claim(design)
    claimed = claim_v2_fit_before_computation(claim, claim_writer=lambda value: None)
    bundle = materialize_claimed_v2_fit_bundle(
        design,
        claimed_fit=claimed,
        fit_execution_manifest_sha256=_sha("public-fit-invocation-v2"),
        executable_bundle_sha256=_sha("executable-bundle-v2"),
    )
    return design, metadata, claim, bundle


class _MetadataOnlyStore:
    def __init__(self, rows: tuple[SealedRecordManifestMetadata, ...]) -> None:
        self._rows = {row.record_id: row for row in rows}
        self.inspected: list[str] = []

    def inspect_sealed_record_metadata(
        self,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ) -> SealedRecordManifestMetadata | None:
        self.inspected.append(record_id)
        row = self._rows.get(record_id)
        assert row is None or row.kind == expected_kind
        return row

    def find_sealed_record(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("fit inventory attempted to open a development payload")


def test_inventory_is_manifest_only_and_exact() -> None:
    design, metadata = _metadata_design()
    store = _MetadataOnlyStore(metadata)

    result = inventory_v2_development_metadata(design.development_roster, store=store)

    assert result == metadata
    assert store.inspected == [row.record_id for row in design.development_roster.rows]


def test_inventory_rejects_manifest_mutation_without_payload_read() -> None:
    design, metadata = _metadata_design()
    mutated = list(metadata)
    row = mutated[0]
    mutated[0] = SealedRecordManifestMetadata(
        record_id=row.record_id,
        kind=row.kind,
        declared_record_sha256=row.declared_record_sha256,
        manifest_sha256=_sha("different-manifest"),
        declared_total_bytes=row.declared_total_bytes,
    )

    with pytest.raises(
        LivingDexDependencyIntegrityV2Error,
        match="manifest metadata differs",
    ):
        inventory_v2_development_metadata(
            design.development_roster,
            store=_MetadataOnlyStore(tuple(mutated)),
        )


def test_claim_is_written_before_fitter_runs() -> None:
    design, _ = _metadata_design()
    claim = _fit_claim(design)
    events: list[str] = []
    claimed = claim_v2_fit_before_computation(
        claim,
        claim_writer=lambda value: events.append("claim"),
    )

    def fitter(**kwargs: object):
        assert events == ["claim"]
        events.append("fit")
        return fit_dependency_ranker_examples(**kwargs)  # type: ignore[arg-type]

    bundle = materialize_claimed_v2_fit_bundle(
        design,
        claimed_fit=claimed,
        fit_execution_manifest_sha256=_sha("fit-invocation"),
        executable_bundle_sha256=_sha("bundle"),
        fitter=fitter,
    )

    assert events == ["claim", "fit"]
    assert bundle.fit.train_accuracy == 1.0
    assert bundle.fit.design_sha256 == design.design_sha256
    assert bundle.fit.train_dataset_sha256 == design.train_revalidation_sha256


def test_train_revalidation_is_exactly_balanced_and_public() -> None:
    design, _ = _metadata_design()
    examples = dependency_train_examples_v2(design)

    assert len(examples) == 8
    assert sum(row.reward == 1 for row in examples) == 4
    assert sum(row.reward == -1 for row in examples) == 4
    assert sum(row.assigned_action.value == "acquire_species" for row in examples) == 4
    assert {row.acquire_minus_evolve for row in examples} == {
        (1.0, -1.0, 0.0, -0.0),
        (1.0, -1.0, 1.0, -1.0),
    }


def test_exact_fit_bundle_authenticates_every_join() -> None:
    design, _, claim, bundle = _bundle()

    authenticated = authenticate_v2_dependency_evaluation_fit_bundle(
        design,
        fit_claim=claim,
        pins=bundle.pins,
        fit_record_bytes=bundle.fit_record_bytes,
        fit_manifest_record_bytes=bundle.fit_manifest_record_bytes,
        fit_terminal_record_bytes=bundle.fit_terminal_record_bytes,
    )

    assert authenticated.model_sha256 == bundle.fit.model.model_sha256
    assert authenticated.public_dict()["all_semantic_bindings_joined"] is True
    assert authenticated.public_dict()["development_payloads_opened"] == 0


@pytest.mark.parametrize(
    ("record_name", "field"),
    (
        ("fit_manifest_record_bytes", "fit_claim_sha256"),
        ("fit_manifest_record_bytes", "development_roster_sha256"),
        ("fit_manifest_record_bytes", "train_revalidation_sha256"),
        ("fit_manifest_record_bytes", "ranker_contract_sha256"),
        ("fit_manifest_record_bytes", "fit_execution_identity_sha256"),
        ("fit_manifest_record_bytes", "model_sha256"),
        ("fit_manifest_record_bytes", "fit_record_sha256"),
        ("fit_manifest_record_bytes", "fit_execution_manifest_sha256"),
        ("fit_manifest_record_bytes", "executable_bundle_sha256"),
        ("fit_terminal_record_bytes", "fit_manifest_record_sha256"),
    ),
)
def test_semantic_mutation_fails_even_with_rehashed_record_pin(
    record_name: str,
    field: str,
) -> None:
    design, _, claim, bundle = _bundle()
    fit_bytes = bundle.fit_record_bytes
    manifest_bytes = bundle.fit_manifest_record_bytes
    terminal_bytes = bundle.fit_terminal_record_bytes
    original = manifest_bytes if record_name == "fit_manifest_record_bytes" else terminal_bytes
    document = json.loads(original)
    document[field] = _sha(f"mutated:{field}")
    mutated = _line(document)
    if record_name == "fit_manifest_record_bytes":
        manifest_bytes = mutated
        pins = DependencyEvaluationBundlePins(
            fit_identity=bundle.pins.fit_identity,
            fit_manifest_record_sha256=hashlib.sha256(mutated).hexdigest(),
            fit_terminal_record_sha256=bundle.pins.fit_terminal_record_sha256,
        )
    else:
        terminal_bytes = mutated
        pins = DependencyEvaluationBundlePins(
            fit_identity=bundle.pins.fit_identity,
            fit_manifest_record_sha256=bundle.pins.fit_manifest_record_sha256,
            fit_terminal_record_sha256=hashlib.sha256(mutated).hexdigest(),
        )

    with pytest.raises(LivingDexDependencyIntegrityV2Error, match="semantic identity differs"):
        authenticate_v2_dependency_evaluation_fit_bundle(
            design,
            fit_claim=claim,
            pins=pins,
            fit_record_bytes=fit_bytes,
            fit_manifest_record_bytes=manifest_bytes,
            fit_terminal_record_bytes=terminal_bytes,
        )


def test_external_pins_reject_self_consistent_replacement_fit_record() -> None:
    design, _, claim, bundle = _bundle()
    document = json.loads(bundle.fit_record_bytes)
    model = document["model"]
    assert isinstance(model, dict)
    weights = model["weights"]
    assert isinstance(weights, list)
    weights[0] = float(weights[0]) + 0.01
    model["model_sha256"] = _sha("not-a-field")
    replacement = _line(document)

    with pytest.raises(LivingDexDependencyIntegrityV2Error, match="fit record pin differs"):
        authenticate_v2_dependency_evaluation_fit_bundle(
            design,
            fit_claim=claim,
            pins=bundle.pins,
            fit_record_bytes=replacement,
            fit_manifest_record_bytes=bundle.fit_manifest_record_bytes,
            fit_terminal_record_bytes=bundle.fit_terminal_record_bytes,
        )


def test_fit_records_publish_in_order_with_exact_pins(tmp_path: Path) -> None:
    design, _, claim, bundle = _bundle()
    repository = tmp_path / "repository"
    private = tmp_path / "private"
    repository.mkdir()
    private.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == private.resolve() else 1

    store = initialize_private_root(
        private,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda path: False,
    )

    published = publish_v2_fit_bundle(store, bundle)

    assert published.bundle.pins == bundle.pins
    assert published.fit_record_manifest_sha256 != published.fit_manifest_manifest_sha256
    authenticate_v2_dependency_evaluation_fit_bundle(
        design,
        fit_claim=claim,
        pins=bundle.pins,
        fit_record_bytes=bundle.fit_record_bytes,
        fit_manifest_record_bytes=bundle.fit_manifest_record_bytes,
        fit_terminal_record_bytes=bundle.fit_terminal_record_bytes,
    )
