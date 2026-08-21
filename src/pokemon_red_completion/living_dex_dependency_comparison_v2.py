"""Claim-before-open comparison boundary for sealed V2 dependency rows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
    DependencyComparisonClaimV2,
    FreshDevelopmentOpeningV2,
    RootlessDependencyEvaluationDesignV2,
    require_fresh_development_opening_set_v2,
)
from pokemon_red_completion.living_dex_dependency_integrity_v2 import (
    AuthenticatedDependencyEvaluationFitV2,
    LivingDexDependencyIntegrityV2Error,
    V2MetadataStore,
    inventory_v2_development_metadata,
)
from pokemon_red_completion.living_dex_dependency_provision_v2 import (
    LivingDexDependencyProvisionV2Error,
    parse_v2_development_opening,
)
from pokemon_red_completion.private_artifacts import PrivateSealedRecord

_PREFLIGHT_TOKEN = object()
_CLAIMED_COMPARISON_TOKEN = object()


class LivingDexDependencyComparisonV2Error(ValueError):
    """The V2 comparison preflight, claim, or sealed opening set is invalid."""


class V2ComparisonStore(V2MetadataStore, Protocol):
    """Private-store capabilities separated across preflight and postclaim use."""

    def find_sealed_record(
        self,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ) -> PrivateSealedRecord | None: ...


@dataclass(frozen=True, slots=True)
class PreparedV2Comparison:
    """Opaque proof that fit and metadata joined while the claim remained unused."""

    design: RootlessDependencyEvaluationDesignV2
    claim: DependencyComparisonClaimV2
    authenticated_fit: AuthenticatedDependencyEvaluationFitV2
    _validation_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._validation_token is not _PREFLIGHT_TOKEN:
            raise LivingDexDependencyComparisonV2Error(
                "V2 comparison preparation must come from preflight"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.rootless-dependency-comparison-preflight.v2",
            "status": "ready_identity_unclaimed",
            "design_sha256": self.design.design_sha256,
            "development_roster_sha256": self.design.development_roster.roster_sha256,
            "comparison_claim_sha256": self.claim.semantic_claim_sha256,
            "comparison_execution_identity_sha256": self.claim.execution_identity_sha256,
            "fit_bundle_authenticated": True,
            "development_manifest_rows_authenticated": 4,
            "development_payloads_opened": 0,
            "development_payloads_decoded": 0,
            "comparison_claim_consumed": False,
        }


@dataclass(frozen=True, slots=True)
class ClaimedV2Comparison:
    """Opaque proof that the comparison identity was durably consumed."""

    prepared: PreparedV2Comparison
    _validation_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._validation_token is not _CLAIMED_COMPARISON_TOKEN:
            raise LivingDexDependencyComparisonV2Error(
                "V2 comparison claim must come from claim-before-open"
            )


def preflight_v2_comparison(
    design: RootlessDependencyEvaluationDesignV2,
    claim: DependencyComparisonClaimV2,
    *,
    authenticated_fit: AuthenticatedDependencyEvaluationFitV2,
    metadata_store: V2MetadataStore,
    claim_is_available: Callable[[str], bool],
) -> PreparedV2Comparison:
    """Authenticate the exact fit and four manifests without opening payloads."""

    if not isinstance(design, RootlessDependencyEvaluationDesignV2):
        raise TypeError("design must be a RootlessDependencyEvaluationDesignV2")
    if not isinstance(claim, DependencyComparisonClaimV2):
        raise TypeError("claim must be a DependencyComparisonClaimV2")
    if not isinstance(authenticated_fit, AuthenticatedDependencyEvaluationFitV2):
        raise TypeError("authenticated_fit must be AuthenticatedDependencyEvaluationFitV2")
    if not callable(claim_is_available):
        raise TypeError("claim_is_available must be callable")
    if (
        claim.design_sha256 != design.design_sha256
        or claim.development_roster_sha256 != design.development_roster.roster_sha256
        or claim.fit_claim_sha256 != authenticated_fit.fit_claim.semantic_claim_sha256
        or claim.fit_execution_identity_sha256
        != authenticated_fit.fit_claim.execution_identity_sha256
        or claim.fit_bundle_pins.public_dict() != authenticated_fit.pins.public_dict()
    ):
        raise LivingDexDependencyComparisonV2Error(
            "V2 comparison preflight semantic identity differs"
        )
    try:
        inventory_v2_development_metadata(
            design.development_roster,
            store=metadata_store,
        )
    except LivingDexDependencyIntegrityV2Error:
        raise LivingDexDependencyComparisonV2Error(
            "V2 comparison preflight metadata differs"
        ) from None
    if claim_is_available(claim.semantic_claim_sha256) is not True:
        raise LivingDexDependencyComparisonV2Error("V2 comparison identity is already consumed")
    return PreparedV2Comparison(
        design,
        claim,
        authenticated_fit,
        _PREFLIGHT_TOKEN,
    )


def claim_v2_comparison_before_payload_open(
    prepared: PreparedV2Comparison,
    *,
    claim_writer: Callable[[DependencyComparisonClaimV2], None],
) -> ClaimedV2Comparison:
    """Consume the comparison identity before any development payload can open."""

    if not isinstance(prepared, PreparedV2Comparison):
        raise TypeError("prepared must be a PreparedV2Comparison")
    if not callable(claim_writer):
        raise TypeError("claim_writer must be callable")
    claim_writer(prepared.claim)
    return ClaimedV2Comparison(prepared, _CLAIMED_COMPARISON_TOKEN)


def open_v2_development_after_claim(
    claimed: ClaimedV2Comparison,
    *,
    store: V2ComparisonStore,
) -> tuple[FreshDevelopmentOpeningV2, ...]:
    """Fully open exactly four committed payloads after the opaque claim proof.

    The return type is intentionally opaque at this boundary.  A later separately
    authorized comparison runner may pass the typed rows into aggregate scoring;
    qualification code must stop before calling this function on real storage.
    """

    if not isinstance(claimed, ClaimedV2Comparison):
        raise TypeError("claimed must be a ClaimedV2Comparison")
    openings = []
    for commitment in claimed.prepared.design.development_roster.rows:
        record = store.find_sealed_record(
            commitment.record_id,
            expected_kind=ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
        )
        if record is None:
            raise LivingDexDependencyComparisonV2Error(
                "V2 comparison opening is absent after claim"
            )
        if (
            record.summary.record_id != commitment.record_id
            or record.summary.kind != ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2
            or record.summary.manifest_sha256 != commitment.manifest_sha256
            or record.summary.record_sha256 != commitment.declared_record_sha256
            or record.summary.total_bytes != commitment.declared_total_bytes
        ):
            raise LivingDexDependencyComparisonV2Error(
                "V2 comparison opening commitment differs after claim"
            )
        try:
            opening = parse_v2_development_opening(record.read())
        except LivingDexDependencyProvisionV2Error:
            raise LivingDexDependencyComparisonV2Error(
                "V2 comparison opening is invalid after claim"
            ) from None
        if opening.scenario_id != commitment.record_id:
            raise LivingDexDependencyComparisonV2Error(
                "V2 comparison opening identity differs after claim"
            )
        openings.append(opening)
    typed = tuple(openings)
    try:
        require_fresh_development_opening_set_v2(typed)
    except ValueError:
        raise LivingDexDependencyComparisonV2Error(
            "V2 comparison opening set differs after claim"
        ) from None
    return typed
