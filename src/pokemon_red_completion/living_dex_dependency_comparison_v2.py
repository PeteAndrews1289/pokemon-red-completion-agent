"""Claim-before-open comparison boundary for sealed V2 dependency rows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.living_dex_dependency_comparison import (
    DependencyComparisonResult,
    compare_dependency_ranker,
)
from pokemon_red_completion.living_dex_dependency_curriculum import (
    DependencyStructure,
    VerifiedDevelopmentComparison,
    VerifiedDevelopmentOpening,
)
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

DEPENDENCY_COMPARISON_RESULT_KIND_V2 = "rootless-dependency-comparison-result-v2"
DEPENDENCY_COMPARISON_TERMINAL_KIND_V2 = "rootless-dependency-comparison-terminal-v2"
DEPENDENCY_COMPARISON_FAILURE_KIND_V2 = "rootless-dependency-comparison-failure-v2"
DEPENDENCY_COMPARISON_RESULT_SCHEMA_V2 = "pokemon.private.rootless-dependency-comparison-result.v2"
DEPENDENCY_COMPARISON_TERMINAL_SCHEMA_V2 = (
    "pokemon.private.rootless-dependency-comparison-terminal.v2"
)
DEPENDENCY_COMPARISON_FAILURE_SCHEMA_V2 = (
    "pokemon.private.rootless-dependency-comparison-failure-terminal.v2"
)
_PREFLIGHT_TOKEN = object()
_CLAIMED_COMPARISON_TOKEN = object()
_MATERIALIZED_COMPARISON_TOKEN = object()


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


class V2ComparisonPublisher(Protocol):
    """Narrow immutable publisher used only after comparison claim consumption."""

    def publish_sealed_record(
        self,
        record_id: str,
        *,
        kind: str,
        record: dict[str, object],
    ) -> PrivateSealedRecord: ...


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


@dataclass(frozen=True, slots=True)
class PublishedV2Comparison:
    """Path-free proof that the aggregate and completed terminal were published."""

    result: DependencyComparisonResult
    result_record_sha256: str
    result_manifest_sha256: str
    terminal_record_sha256: str
    terminal_manifest_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.result, DependencyComparisonResult) or any(
            not _is_sha256(value)
            for value in (
                self.result_record_sha256,
                self.result_manifest_sha256,
                self.terminal_record_sha256,
                self.terminal_manifest_sha256,
            )
        ):
            raise LivingDexDependencyComparisonV2Error("published V2 comparison identity differs")


@dataclass(frozen=True, slots=True)
class MaterializedV2Comparison:
    """Opaque join between one claimed identity and its aggregate result."""

    claimed: ClaimedV2Comparison
    result: DependencyComparisonResult
    _validation_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if (
            self._validation_token is not _MATERIALIZED_COMPARISON_TOKEN
            or not isinstance(self.claimed, ClaimedV2Comparison)
            or not isinstance(self.result, DependencyComparisonResult)
        ):
            raise LivingDexDependencyComparisonV2Error(
                "V2 comparison materialization must come from claimed evaluation"
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


def materialize_claimed_v2_comparison(
    claimed: ClaimedV2Comparison,
    *,
    store: V2ComparisonStore,
) -> MaterializedV2Comparison:
    """Open the exact four rows after claim and compute one aggregate-only result."""

    if not isinstance(claimed, ClaimedV2Comparison):
        raise TypeError("claimed must be a ClaimedV2Comparison")
    openings = open_v2_development_after_claim(claimed, store=store)
    authenticated = claimed.prepared.authenticated_fit
    verified = VerifiedDevelopmentComparison(
        fit_manifest_sha256=authenticated.pins.fit_manifest_record_sha256,
        fit_terminal_sha256=authenticated.pins.fit_terminal_record_sha256,
        canonical_fit_sha256=authenticated.fit.fit_sha256,
        openings=tuple(_verified_v1_opening(row) for row in openings),
    )
    result = compare_dependency_ranker(
        design_sha256=claimed.prepared.design.design_sha256,
        model=authenticated.fit.model,
        verified=verified,
    )
    if (
        result.model_sha256 != authenticated.model_sha256
        or result.fit_manifest_sha256 != authenticated.pins.fit_manifest_record_sha256
        or result.fit_terminal_sha256 != authenticated.pins.fit_terminal_record_sha256
        or result.row_count != 4
        or result.family_count != 2
    ):
        raise LivingDexDependencyComparisonV2Error("V2 comparison aggregate identity differs")
    return MaterializedV2Comparison(
        claimed,
        result,
        _MATERIALIZED_COMPARISON_TOKEN,
    )


def publish_claimed_v2_comparison(
    publisher: V2ComparisonPublisher,
    materialized: MaterializedV2Comparison,
    *,
    comparison_execution_manifest_sha256: str,
) -> PublishedV2Comparison:
    """Publish one aggregate result followed by its binding completed terminal."""

    if not isinstance(materialized, MaterializedV2Comparison):
        raise TypeError("materialized must be a MaterializedV2Comparison")
    if not _is_sha256(comparison_execution_manifest_sha256):
        raise LivingDexDependencyComparisonV2Error("comparison execution manifest identity differs")
    claimed = materialized.claimed
    result = materialized.result
    claim = claimed.prepared.claim
    if (
        result.design_sha256 != claim.design_sha256
        or result.model_sha256 != claim.fit_bundle_pins.fit_identity.model_sha256
        or result.fit_manifest_sha256 != claim.fit_bundle_pins.fit_manifest_record_sha256
        or result.fit_terminal_sha256 != claim.fit_bundle_pins.fit_terminal_record_sha256
    ):
        raise LivingDexDependencyComparisonV2Error("V2 comparison result and claim differ")
    result_id, terminal_id = v2_comparison_record_ids(claim.execution_identity_sha256)
    result_record = publisher.publish_sealed_record(
        result_id,
        kind=DEPENDENCY_COMPARISON_RESULT_KIND_V2,
        record={
            "schema": DEPENDENCY_COMPARISON_RESULT_SCHEMA_V2,
            "status": "completed",
            "comparison_claim_sha256": claim.semantic_claim_sha256,
            "comparison_execution_identity_sha256": claim.execution_identity_sha256,
            "comparison_execution_manifest_sha256": comparison_execution_manifest_sha256,
            "comparison_sha256": result.comparison_sha256,
            "aggregate": result.public_dict(),
            "development_rows_disclosed": 0,
            "private_path_fields": 0,
        },
    )
    terminal_record = publisher.publish_sealed_record(
        terminal_id,
        kind=DEPENDENCY_COMPARISON_TERMINAL_KIND_V2,
        record={
            "schema": DEPENDENCY_COMPARISON_TERMINAL_SCHEMA_V2,
            "status": "completed",
            "comparison_claim_sha256": claim.semantic_claim_sha256,
            "comparison_execution_identity_sha256": claim.execution_identity_sha256,
            "comparison_execution_manifest_sha256": comparison_execution_manifest_sha256,
            "design_sha256": claim.design_sha256,
            "development_roster_sha256": claim.development_roster_sha256,
            "fit_claim_sha256": claim.fit_claim_sha256,
            "fit_execution_identity_sha256": claim.fit_execution_identity_sha256,
            "fit_manifest_record_sha256": claim.fit_bundle_pins.fit_manifest_record_sha256,
            "fit_terminal_record_sha256": claim.fit_bundle_pins.fit_terminal_record_sha256,
            "fit_sha256": claim.fit_bundle_pins.fit_identity.fit_sha256,
            "model_sha256": claim.fit_bundle_pins.fit_identity.model_sha256,
            "train_dataset_sha256": claim.fit_bundle_pins.fit_identity.train_dataset_sha256,
            "comparison_sha256": result.comparison_sha256,
            "comparison_result_record_sha256": result_record.summary.record_sha256,
            "comparison_result_manifest_sha256": result_record.summary.manifest_sha256,
            "row_count": 4,
            "development_rows_disclosed": 0,
            "retry_allowed": False,
            "private_path_fields": 0,
        },
    )
    return PublishedV2Comparison(
        result=result,
        result_record_sha256=result_record.summary.record_sha256,
        result_manifest_sha256=result_record.summary.manifest_sha256,
        terminal_record_sha256=terminal_record.summary.record_sha256,
        terminal_manifest_sha256=terminal_record.summary.manifest_sha256,
    )


def v2_comparison_record_ids(execution_identity_sha256: str) -> tuple[str, str]:
    """Return deterministic immutable result and terminal record IDs."""

    if not _is_sha256(execution_identity_sha256):
        raise LivingDexDependencyComparisonV2Error("comparison execution identity differs")
    suffix = execution_identity_sha256[:24]
    return (
        f"rootless-v2-comparison-{suffix}",
        f"rootless-v2-comparison-terminal-{suffix}",
    )


def v2_comparison_failure_record_id(execution_identity_sha256: str) -> str:
    """Return the distinct retained-failure namespace for a consumed comparison."""

    if not _is_sha256(execution_identity_sha256):
        raise LivingDexDependencyComparisonV2Error("comparison execution identity differs")
    return f"rootless-v2-comparison-failure-{execution_identity_sha256[:24]}"


def _verified_v1_opening(row: FreshDevelopmentOpeningV2) -> VerifiedDevelopmentOpening:
    return VerifiedDevelopmentOpening(
        scenario_id=row.scenario_id,
        family_id=row.family_id,
        nonce=row.nonce,
        multiplicity=row.multiplicity,
        structure=DependencyStructure(
            row.structure.required_precursor_count,
            row.structure.required_evolved_count,
        ),
        before=row.before,
        assigned_action=row.assigned_action,
        derived_reward=row.derived_reward,
    )


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
