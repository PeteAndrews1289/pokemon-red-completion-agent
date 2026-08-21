from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pokemon_red_completion.living_dex_dependency_comparison_v2 import (
    ClaimedV2Comparison,
    LivingDexDependencyComparisonV2Error,
    claim_v2_comparison_before_payload_open,
    open_v2_development_after_claim,
    preflight_v2_comparison,
)
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    EvaluationExecutionBindingV2,
    RootlessDependencyEvaluationDesignV2,
    build_dependency_comparison_claim_v2,
    build_dependency_fit_claim_v2,
)
from pokemon_red_completion.living_dex_dependency_integrity_v2 import (
    authenticate_v2_dependency_evaluation_fit_bundle,
    claim_v2_fit_before_computation,
    materialize_claimed_v2_fit_bundle,
)
from pokemon_red_completion.living_dex_dependency_provision_v2 import (
    provision_v2_development_commitments,
)
from pokemon_red_completion.private_artifacts import initialize_private_root


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _store(tmp_path: Path):
    repository = tmp_path / "repository"
    private = tmp_path / "private"
    repository.mkdir()
    private.mkdir()

    def device_id(path: Path) -> int:
        return 2 if path == private.resolve() else 1

    return initialize_private_root(
        private,
        repository_root=repository,
        device_id=device_id,
        git_worktree_probe=lambda path: False,
    )


def _prepared_values(tmp_path: Path):
    store = _store(tmp_path)
    provisioned = provision_v2_development_commitments(store)
    design = RootlessDependencyEvaluationDesignV2(provisioned.roster)
    fit_binding = EvaluationExecutionBindingV2(
        operation="fit",
        source_commit="1" * 40,
        source_bundle_sha256=_sha("fit-source"),
        runner_sha256=_sha("fit-runner"),
        runtime_sha256=_sha("fit-runtime"),
    )
    fit_claim = build_dependency_fit_claim_v2(design, execution_binding=fit_binding)
    claimed_fit = claim_v2_fit_before_computation(fit_claim, claim_writer=lambda value: None)
    bundle = materialize_claimed_v2_fit_bundle(
        design,
        claimed_fit=claimed_fit,
        fit_execution_manifest_sha256=_sha("fit-invocation"),
        executable_bundle_sha256=_sha("fit-executable-bundle"),
    )
    authenticated_fit = authenticate_v2_dependency_evaluation_fit_bundle(
        design,
        fit_claim=fit_claim,
        pins=bundle.pins,
        fit_record_bytes=bundle.fit_record_bytes,
        fit_manifest_record_bytes=bundle.fit_manifest_record_bytes,
        fit_terminal_record_bytes=bundle.fit_terminal_record_bytes,
    )
    comparison_binding = EvaluationExecutionBindingV2(
        operation="comparison",
        source_commit="2" * 40,
        source_bundle_sha256=_sha("comparison-source"),
        runner_sha256=_sha("comparison-runner"),
        runtime_sha256=_sha("comparison-runtime"),
    )
    comparison_claim = build_dependency_comparison_claim_v2(
        design,
        fit_claim=fit_claim,
        fit_bundle_pins=bundle.pins,
        execution_binding=comparison_binding,
    )
    return store, design, authenticated_fit, comparison_claim


class _ObservedStore:
    def __init__(self, store: object, events: list[str]) -> None:
        self._store = store
        self._events = events

    def inspect_sealed_record_metadata(
        self,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ):
        self._events.append(f"metadata:{record_id}")
        return self._store.inspect_sealed_record_metadata(  # type: ignore[attr-defined]
            record_id,
            expected_kind=expected_kind,
        )

    def find_sealed_record(
        self,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ):
        assert "claim" in self._events
        self._events.append(f"payload:{record_id}")
        return self._store.find_sealed_record(  # type: ignore[attr-defined]
            record_id,
            expected_kind=expected_kind,
        )


def test_preflight_is_metadata_only_and_keeps_identity_unclaimed(tmp_path: Path) -> None:
    store, design, authenticated_fit, claim = _prepared_values(tmp_path)
    events: list[str] = []
    observed = _ObservedStore(store, events)

    prepared = preflight_v2_comparison(
        design,
        claim,
        authenticated_fit=authenticated_fit,
        metadata_store=observed,
        claim_is_available=lambda identity: True,
    )

    assert len([event for event in events if event.startswith("metadata:")]) == 4
    assert not any(event.startswith("payload:") for event in events)
    assert prepared.public_dict()["development_payloads_opened"] == 0
    assert prepared.public_dict()["comparison_claim_consumed"] is False


def test_preflight_rejects_consumed_comparison_identity(tmp_path: Path) -> None:
    store, design, authenticated_fit, claim = _prepared_values(tmp_path)

    with pytest.raises(
        LivingDexDependencyComparisonV2Error,
        match="already consumed",
    ):
        preflight_v2_comparison(
            design,
            claim,
            authenticated_fit=authenticated_fit,
            metadata_store=store,
            claim_is_available=lambda identity: False,
        )


def test_payloads_cannot_open_until_claim_writer_returns(tmp_path: Path) -> None:
    store, design, authenticated_fit, claim = _prepared_values(tmp_path)
    events: list[str] = []
    observed = _ObservedStore(store, events)
    prepared = preflight_v2_comparison(
        design,
        claim,
        authenticated_fit=authenticated_fit,
        metadata_store=observed,
        claim_is_available=lambda identity: True,
    )

    claimed = claim_v2_comparison_before_payload_open(
        prepared,
        claim_writer=lambda value: events.append("claim"),
    )
    openings = open_v2_development_after_claim(claimed, store=observed)

    claim_index = events.index("claim")
    payload_indices = [index for index, value in enumerate(events) if value.startswith("payload:")]
    assert len(openings) == 4
    assert payload_indices and all(index > claim_index for index in payload_indices)


def test_claimed_comparison_token_cannot_be_fabricated(tmp_path: Path) -> None:
    store, design, authenticated_fit, claim = _prepared_values(tmp_path)
    prepared = preflight_v2_comparison(
        design,
        claim,
        authenticated_fit=authenticated_fit,
        metadata_store=store,
        claim_is_available=lambda identity: True,
    )

    with pytest.raises(
        LivingDexDependencyComparisonV2Error,
        match="claim-before-open",
    ):
        ClaimedV2Comparison(prepared, object())


def test_preflight_rejects_fit_or_claim_substitution(tmp_path: Path) -> None:
    store, design, authenticated_fit, claim = _prepared_values(tmp_path)
    different_binding = EvaluationExecutionBindingV2(
        operation="comparison",
        source_commit="3" * 40,
        source_bundle_sha256=_sha("different-source"),
        runner_sha256=_sha("different-runner"),
        runtime_sha256=_sha("different-runtime"),
    )
    replacement = type(claim)(
        design_sha256=claim.design_sha256,
        development_roster_sha256=claim.development_roster_sha256,
        fit_claim_sha256=_sha("different-fit-claim"),
        fit_execution_identity_sha256=claim.fit_execution_identity_sha256,
        fit_bundle_pins=claim.fit_bundle_pins,
        execution_binding=different_binding,
    )

    with pytest.raises(
        LivingDexDependencyComparisonV2Error,
        match="semantic identity differs",
    ):
        preflight_v2_comparison(
            design,
            replacement,
            authenticated_fit=authenticated_fit,
            metadata_store=store,
            claim_is_available=lambda identity: True,
        )
