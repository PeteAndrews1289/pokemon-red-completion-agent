"""Fit and exact-bundle integrity for rootless living-Dex dependency V2.

The V2 compliance fit may inspect only the four sealed-record manifests.  It
recomputes the eight deterministic train values, claims its identity before the
optimizer runs, and produces a three-record bundle whose model, dataset, design,
roster, claim, source, manifest, and terminal identities all join exactly.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
    ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
    DependencyFitClaimV2,
    EvaluationExecutionBindingV2,
    FreshDevelopmentCommitmentRosterV2,
    RootlessDependencyEvaluationDesignV2,
    rootless_dependency_ranker_contract_v2,
    rootless_dependency_train_revalidation_contract_v2,
)
from pokemon_red_completion.living_dex_dependency_integrity import (
    DependencyEvaluationBundlePins,
    DependencyEvaluationFitIdentity,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DependencyRankerFit,
    DependencyTrainExample,
    LivingDexDependencyRankerError,
    fit_dependency_ranker_examples,
)
from pokemon_red_completion.private_artifacts import (
    PrivateSealedRecord,
    SealedRecordManifestMetadata,
)
from pokemon_red_completion.provenance import canonical_sha256

DEPENDENCY_EVALUATION_FIT_MANIFEST_SCHEMA_V2 = (
    "pokemon.core.rootless-dependency-evaluation-fit-manifest.v2"
)
DEPENDENCY_EVALUATION_FIT_TERMINAL_SCHEMA_V2 = (
    "pokemon.core.rootless-dependency-evaluation-fit-terminal.v2"
)
DEPENDENCY_EVALUATION_FIT_RECORD_KIND_V2 = "rootless-dependency-fit-v2"
DEPENDENCY_EVALUATION_FIT_MANIFEST_KIND_V2 = "rootless-dependency-fit-manifest-v2"
DEPENDENCY_EVALUATION_FIT_TERMINAL_KIND_V2 = "rootless-dependency-fit-terminal-v2"
DEPENDENCY_EVALUATION_FIT_FAILURE_KIND_V2 = "rootless-dependency-fit-failure-v2"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_FIT_RECORD_BYTES = 256 * 1024
_MAX_BINDING_RECORD_BYTES = 64 * 1024
_AUTHENTICATED_FIT_TOKEN_V2 = object()
_CLAIMED_FIT_TOKEN_V2 = object()


class LivingDexDependencyIntegrityV2Error(ValueError):
    """A V2 fit stage or exact fit bundle violates its frozen boundary."""


class V2MetadataStore(Protocol):
    """Payload-blind private-store capability allowed before fit."""

    def inspect_sealed_record_metadata(
        self,
        record_id: str,
        *,
        expected_kind: str | None = None,
    ) -> SealedRecordManifestMetadata | None: ...


class V2FitPublisher(Protocol):
    """Narrow immutable-record publication capability used after fitting."""

    def publish_sealed_record(
        self,
        record_id: str,
        *,
        kind: str,
        record: Mapping[str, object],
    ) -> PrivateSealedRecord: ...


@dataclass(frozen=True, slots=True)
class ClaimedDependencyFitV2:
    """Opaque proof that the external one-shot claim writer returned first."""

    claim: DependencyFitClaimV2
    _validation_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._validation_token is not _CLAIMED_FIT_TOKEN_V2:
            raise LivingDexDependencyIntegrityV2Error(
                "claimed V2 fit must come from the claim-before-compute seam"
            )


@dataclass(frozen=True, slots=True)
class DependencyEvaluationFitBundleV2:
    """Canonical bytes and external pins for one completed V2 fit."""

    fit_claim: DependencyFitClaimV2
    fit: DependencyRankerFit
    fit_record_bytes: bytes
    fit_manifest_record_bytes: bytes
    fit_terminal_record_bytes: bytes
    pins: DependencyEvaluationBundlePins

    def __post_init__(self) -> None:
        if not isinstance(self.fit_claim, DependencyFitClaimV2):
            raise LivingDexDependencyIntegrityV2Error("V2 fit claim differs")
        if not isinstance(self.fit, DependencyRankerFit):
            raise LivingDexDependencyIntegrityV2Error("V2 fit differs")
        if any(
            not isinstance(payload, bytes)
            for payload in (
                self.fit_record_bytes,
                self.fit_manifest_record_bytes,
                self.fit_terminal_record_bytes,
            )
        ) or not isinstance(self.pins, DependencyEvaluationBundlePins):
            raise LivingDexDependencyIntegrityV2Error("V2 fit bundle fields differ")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.rootless-dependency-evaluation-fit-bundle.v2",
            "fit_claim_sha256": self.fit_claim.semantic_claim_sha256,
            "fit_execution_identity_sha256": self.fit_claim.execution_identity_sha256,
            **self.pins.public_dict(),
            "development_payloads_opened": 0,
            "development_payloads_decoded": 0,
            "synthetic_rootless_model_fits_added": 0,
            "model_fits_added": 0,
        }


@dataclass(frozen=True, slots=True)
class PublishedDependencyEvaluationFitV2:
    """Path-free proof that all three expected fit records were published."""

    bundle: DependencyEvaluationFitBundleV2
    fit_record_manifest_sha256: str
    fit_manifest_manifest_sha256: str
    fit_terminal_manifest_sha256: str

    def __post_init__(self) -> None:
        for value in (
            self.fit_record_manifest_sha256,
            self.fit_manifest_manifest_sha256,
            self.fit_terminal_manifest_sha256,
        ):
            _require_sha256(value, "published fit manifest")


@dataclass(frozen=True, slots=True)
class AuthenticatedDependencyEvaluationFitV2:
    """Opaque result of one complete exact-bundle authentication for V2."""

    fit: DependencyRankerFit
    fit_claim: DependencyFitClaimV2
    pins: DependencyEvaluationBundlePins
    _validation_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._validation_token is not _AUTHENTICATED_FIT_TOKEN_V2:
            raise LivingDexDependencyIntegrityV2Error(
                "authenticated V2 dependency fit must come from the bundle verifier"
            )

    @property
    def model_sha256(self) -> str:
        return self.fit.model.model_sha256

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.authenticated-rootless-dependency-evaluation-fit.v2",
            "fit_claim_sha256": self.fit_claim.semantic_claim_sha256,
            "fit_execution_identity_sha256": self.fit_claim.execution_identity_sha256,
            **self.pins.public_dict(),
            "all_semantic_bindings_joined": True,
            "development_payloads_opened": 0,
        }


def inventory_v2_development_metadata(
    roster: FreshDevelopmentCommitmentRosterV2,
    *,
    store: V2MetadataStore,
) -> tuple[SealedRecordManifestMetadata, ...]:
    """Authenticate exactly four manifests without opening any payload file."""

    if not isinstance(roster, FreshDevelopmentCommitmentRosterV2):
        raise TypeError("roster must be FreshDevelopmentCommitmentRosterV2")
    metadata: list[SealedRecordManifestMetadata] = []
    for commitment in roster.rows:
        row = store.inspect_sealed_record_metadata(
            commitment.record_id,
            expected_kind=ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2,
        )
        if row is None:
            raise LivingDexDependencyIntegrityV2Error(
                "V2 development metadata inventory is incomplete"
            )
        if (
            row.record_id != commitment.record_id
            or row.kind != ROOTLESS_DEPENDENCY_DEVELOPMENT_RECORD_KIND_V2
            or row.manifest_sha256 != commitment.manifest_sha256
            or row.declared_record_sha256 != commitment.declared_record_sha256
            or row.declared_total_bytes != commitment.declared_total_bytes
        ):
            raise LivingDexDependencyIntegrityV2Error("V2 development manifest metadata differs")
        metadata.append(row)
    if tuple(row.record_id for row in metadata) != tuple(row.record_id for row in roster.rows):
        raise LivingDexDependencyIntegrityV2Error("V2 development metadata inventory order differs")
    return tuple(metadata)


def dependency_train_examples_v2(
    design: RootlessDependencyEvaluationDesignV2,
) -> tuple[DependencyTrainExample, ...]:
    """Recompute the eight public deterministic targets without V1 artifact reads."""

    if not isinstance(design, RootlessDependencyEvaluationDesignV2):
        raise TypeError("design must be a RootlessDependencyEvaluationDesignV2")
    contract = rootless_dependency_train_revalidation_contract_v2()
    if design.train_revalidation_sha256 != canonical_sha256(contract):
        raise LivingDexDependencyIntegrityV2Error("V2 train revalidation identity differs")
    rows = contract.get("canonical_values")
    if not isinstance(rows, list) or len(rows) != 8:
        raise LivingDexDependencyIntegrityV2Error("V2 train revalidation roster differs")
    examples: list[DependencyTrainExample] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise LivingDexDependencyIntegrityV2Error("V2 train revalidation row differs")
        scenario_id = row.get("scenario_id")
        multiplicity = row.get("multiplicity")
        action_value = row.get("assigned_action")
        reward = row.get("derived_reward")
        if (
            not isinstance(scenario_id, str)
            or multiplicity not in {"scarce", "duplicate_ready"}
            or not isinstance(action_value, str)
            or type(reward) is not int  # noqa: E721
            or reward not in {-1, 1}
        ):
            raise LivingDexDependencyIntegrityV2Error("V2 train revalidation row differs")
        try:
            assigned_action = GoalKind(action_value)
        except ValueError:
            raise LivingDexDependencyIntegrityV2Error(
                "V2 train revalidation action differs"
            ) from None
        if assigned_action not in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}:
            raise LivingDexDependencyIntegrityV2Error("V2 train revalidation action differs")
        has_surplus = 0.0 if multiplicity == "scarce" else 1.0
        preferred = assigned_action if reward == 1 else _other_dependency_action(assigned_action)
        examples.append(
            DependencyTrainExample(
                scenario_id=scenario_id,
                assigned_action=assigned_action,
                preferred_action=preferred,
                reward=reward,
                acquire_minus_evolve=(1.0, -1.0, has_surplus, -has_surplus),
            )
        )
    return tuple(examples)


def claim_v2_fit_before_computation(
    fit_claim: DependencyFitClaimV2,
    *,
    claim_writer: Callable[[DependencyFitClaimV2], None],
) -> ClaimedDependencyFitV2:
    """Durably consume the exact fit identity before any optimizer call."""

    if not isinstance(fit_claim, DependencyFitClaimV2):
        raise TypeError("fit_claim must be a DependencyFitClaimV2")
    if not callable(claim_writer):
        raise TypeError("claim_writer must be callable")
    claim_writer(fit_claim)
    return ClaimedDependencyFitV2(fit_claim, _CLAIMED_FIT_TOKEN_V2)


def materialize_claimed_v2_fit_bundle(
    design: RootlessDependencyEvaluationDesignV2,
    *,
    claimed_fit: ClaimedDependencyFitV2,
    fit_execution_manifest_sha256: str,
    executable_bundle_sha256: str,
    fitter: Callable[..., DependencyRankerFit] = fit_dependency_ranker_examples,
) -> DependencyEvaluationFitBundleV2:
    """Fit once from public train values after receiving an opaque claim proof."""

    if not isinstance(design, RootlessDependencyEvaluationDesignV2):
        raise TypeError("design must be a RootlessDependencyEvaluationDesignV2")
    if not isinstance(claimed_fit, ClaimedDependencyFitV2):
        raise TypeError("claimed_fit must be a ClaimedDependencyFitV2")
    fit_claim = claimed_fit.claim
    _require_fit_claim_matches_design(design, fit_claim)
    _require_sha256(fit_execution_manifest_sha256, "fit execution manifest")
    _require_sha256(executable_bundle_sha256, "fit executable bundle")
    examples = dependency_train_examples_v2(design)
    try:
        fit = fitter(
            design_sha256=design.design_sha256,
            train_dataset_sha256=design.train_revalidation_sha256,
            examples=examples,
        )
    except (LivingDexDependencyRankerError, TypeError, ValueError):
        raise LivingDexDependencyIntegrityV2Error("V2 fit computation failed") from None
    if not isinstance(fit, DependencyRankerFit):
        raise LivingDexDependencyIntegrityV2Error("V2 fitter returned an invalid result")
    fit_record_bytes = _canonical_line_v2(fit.to_dict())
    fit_identity = DependencyEvaluationFitIdentity(
        design_sha256=design.design_sha256,
        train_dataset_sha256=design.train_revalidation_sha256,
        fit_record_sha256=hashlib.sha256(fit_record_bytes).hexdigest(),
        fit_sha256=fit.fit_sha256,
        model_sha256=fit.model.model_sha256,
        fit_execution_manifest_sha256=fit_execution_manifest_sha256,
        executable_bundle_sha256=executable_bundle_sha256,
    )
    manifest_document = dependency_evaluation_fit_manifest_document_v2(
        fit_claim,
        fit_identity,
    )
    manifest_bytes = _canonical_line_v2(manifest_document)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    terminal_bytes = _canonical_line_v2(
        dependency_evaluation_fit_terminal_document_v2(
            fit_claim,
            fit_identity,
            fit_manifest_record_sha256=manifest_sha256,
        )
    )
    pins = DependencyEvaluationBundlePins(
        fit_identity=fit_identity,
        fit_manifest_record_sha256=manifest_sha256,
        fit_terminal_record_sha256=hashlib.sha256(terminal_bytes).hexdigest(),
    )
    bundle = DependencyEvaluationFitBundleV2(
        fit_claim=fit_claim,
        fit=fit,
        fit_record_bytes=fit_record_bytes,
        fit_manifest_record_bytes=manifest_bytes,
        fit_terminal_record_bytes=terminal_bytes,
        pins=pins,
    )
    authenticate_v2_dependency_evaluation_fit_bundle(
        design,
        fit_claim=fit_claim,
        pins=pins,
        fit_record_bytes=fit_record_bytes,
        fit_manifest_record_bytes=manifest_bytes,
        fit_terminal_record_bytes=terminal_bytes,
    )
    return bundle


def publish_v2_fit_bundle(
    publisher: V2FitPublisher,
    bundle: DependencyEvaluationFitBundleV2,
) -> PublishedDependencyEvaluationFitV2:
    """Publish fit, manifest, then terminal and verify every record digest."""

    if not isinstance(bundle, DependencyEvaluationFitBundleV2):
        raise TypeError("bundle must be a DependencyEvaluationFitBundleV2")
    fit_id, manifest_id, terminal_id = v2_fit_record_ids(bundle.fit_claim.execution_identity_sha256)
    fit_record = publisher.publish_sealed_record(
        fit_id,
        kind=DEPENDENCY_EVALUATION_FIT_RECORD_KIND_V2,
        record=bundle.fit.to_dict(),
    )
    manifest_document = _parse_canonical_document_v2(
        bundle.fit_manifest_record_bytes,
        maximum_bytes=_MAX_BINDING_RECORD_BYTES,
        subject="fit manifest record",
    )
    manifest_record = publisher.publish_sealed_record(
        manifest_id,
        kind=DEPENDENCY_EVALUATION_FIT_MANIFEST_KIND_V2,
        record=manifest_document,
    )
    terminal_document = _parse_canonical_document_v2(
        bundle.fit_terminal_record_bytes,
        maximum_bytes=_MAX_BINDING_RECORD_BYTES,
        subject="fit terminal record",
    )
    terminal_record = publisher.publish_sealed_record(
        terminal_id,
        kind=DEPENDENCY_EVALUATION_FIT_TERMINAL_KIND_V2,
        record=terminal_document,
    )
    if (
        fit_record.summary.record_sha256 != bundle.pins.fit_identity.fit_record_sha256
        or manifest_record.summary.record_sha256 != bundle.pins.fit_manifest_record_sha256
        or terminal_record.summary.record_sha256 != bundle.pins.fit_terminal_record_sha256
    ):
        raise LivingDexDependencyIntegrityV2Error("published V2 fit record identity differs")
    return PublishedDependencyEvaluationFitV2(
        bundle=bundle,
        fit_record_manifest_sha256=fit_record.summary.manifest_sha256,
        fit_manifest_manifest_sha256=manifest_record.summary.manifest_sha256,
        fit_terminal_manifest_sha256=terminal_record.summary.manifest_sha256,
    )


def authenticate_v2_dependency_evaluation_fit_bundle(
    design: RootlessDependencyEvaluationDesignV2,
    *,
    fit_claim: DependencyFitClaimV2,
    pins: DependencyEvaluationBundlePins,
    fit_record_bytes: bytes,
    fit_manifest_record_bytes: bytes,
    fit_terminal_record_bytes: bytes,
) -> AuthenticatedDependencyEvaluationFitV2:
    """Join the loaded fit to every externally pinned V2 identity before dev access."""

    if not isinstance(design, RootlessDependencyEvaluationDesignV2):
        raise TypeError("design must be a RootlessDependencyEvaluationDesignV2")
    if not isinstance(fit_claim, DependencyFitClaimV2):
        raise TypeError("fit_claim must be a DependencyFitClaimV2")
    if not isinstance(pins, DependencyEvaluationBundlePins):
        raise TypeError("pins must be DependencyEvaluationBundlePins")
    _require_fit_claim_matches_design(design, fit_claim)
    identity = pins.fit_identity
    if (
        identity.design_sha256 != design.design_sha256
        or identity.train_dataset_sha256 != design.train_revalidation_sha256
    ):
        raise LivingDexDependencyIntegrityV2Error("V2 evaluation design pin differs")

    _require_record_pin_v2(fit_record_bytes, identity.fit_record_sha256, "fit record")
    _require_record_pin_v2(
        fit_manifest_record_bytes,
        pins.fit_manifest_record_sha256,
        "fit manifest record",
    )
    _require_record_pin_v2(
        fit_terminal_record_bytes,
        pins.fit_terminal_record_sha256,
        "fit terminal record",
    )
    fit_document = _parse_canonical_document_v2(
        fit_record_bytes,
        maximum_bytes=_MAX_FIT_RECORD_BYTES,
        subject="fit record",
    )
    try:
        fit = DependencyRankerFit.from_dict(fit_document)
    except (LivingDexDependencyRankerError, TypeError, ValueError):
        raise LivingDexDependencyIntegrityV2Error("fit record is invalid") from None
    if (
        fit.design_sha256 != identity.design_sha256
        or fit.train_dataset_sha256 != identity.train_dataset_sha256
        or fit.fit_sha256 != identity.fit_sha256
        or fit.model.model_sha256 != identity.model_sha256
        or fit.model.train_dataset_sha256 != identity.train_dataset_sha256
    ):
        raise LivingDexDependencyIntegrityV2Error("loaded fit semantic identity differs")

    manifest = _parse_canonical_document_v2(
        fit_manifest_record_bytes,
        maximum_bytes=_MAX_BINDING_RECORD_BYTES,
        subject="fit manifest record",
    )
    expected_manifest = dependency_evaluation_fit_manifest_document_v2(fit_claim, identity)
    if manifest != expected_manifest:
        raise LivingDexDependencyIntegrityV2Error("fit manifest semantic identity differs")
    terminal = _parse_canonical_document_v2(
        fit_terminal_record_bytes,
        maximum_bytes=_MAX_BINDING_RECORD_BYTES,
        subject="fit terminal record",
    )
    expected_terminal = dependency_evaluation_fit_terminal_document_v2(
        fit_claim,
        identity,
        fit_manifest_record_sha256=pins.fit_manifest_record_sha256,
    )
    if terminal != expected_terminal:
        raise LivingDexDependencyIntegrityV2Error("fit terminal semantic identity differs")
    return AuthenticatedDependencyEvaluationFitV2(
        fit=fit,
        fit_claim=fit_claim,
        pins=pins,
        _validation_token=_AUTHENTICATED_FIT_TOKEN_V2,
    )


def dependency_evaluation_fit_manifest_document_v2(
    fit_claim: DependencyFitClaimV2,
    fit_identity: DependencyEvaluationFitIdentity,
) -> dict[str, object]:
    """Return the exact V2 fit-manifest document."""

    return _binding_document_v2(
        fit_claim,
        fit_identity,
        fit_manifest_record_sha256=None,
    )


def dependency_evaluation_fit_terminal_document_v2(
    fit_claim: DependencyFitClaimV2,
    fit_identity: DependencyEvaluationFitIdentity,
    *,
    fit_manifest_record_sha256: str,
) -> dict[str, object]:
    """Return the exact V2 completed-terminal document."""

    _require_sha256(fit_manifest_record_sha256, "fit manifest record")
    return _binding_document_v2(
        fit_claim,
        fit_identity,
        fit_manifest_record_sha256=fit_manifest_record_sha256,
    )


def dependency_fit_claim_from_manifest_document_v2(
    value: Mapping[str, object],
) -> DependencyFitClaimV2:
    """Reconstruct the exact fit claim embedded in an externally pinned manifest."""

    execution = value.get("execution_binding") if isinstance(value, Mapping) else None
    if not isinstance(execution, Mapping) or set(execution) != {
        "operation",
        "source_commit",
        "source_bundle_sha256",
        "runner_sha256",
        "runtime_sha256",
    }:
        raise LivingDexDependencyIntegrityV2Error("fit manifest execution binding differs")
    fields = {
        name: value.get(name)
        for name in (
            "design_sha256",
            "development_roster_sha256",
            "train_revalidation_sha256",
            "ranker_contract_sha256",
        )
    }
    if any(not isinstance(item, str) for item in fields.values()) or any(
        not isinstance(execution.get(name), str)
        for name in (
            "operation",
            "source_commit",
            "source_bundle_sha256",
            "runner_sha256",
            "runtime_sha256",
        )
    ):
        raise LivingDexDependencyIntegrityV2Error("fit manifest claim fields differ")
    try:
        binding = EvaluationExecutionBindingV2(
            operation=execution["operation"],  # type: ignore[arg-type]
            source_commit=execution["source_commit"],  # type: ignore[arg-type]
            source_bundle_sha256=execution["source_bundle_sha256"],  # type: ignore[arg-type]
            runner_sha256=execution["runner_sha256"],  # type: ignore[arg-type]
            runtime_sha256=execution["runtime_sha256"],  # type: ignore[arg-type]
        )
        claim = DependencyFitClaimV2(
            design_sha256=fields["design_sha256"],  # type: ignore[arg-type]
            development_roster_sha256=fields["development_roster_sha256"],  # type: ignore[arg-type]
            train_revalidation_sha256=fields["train_revalidation_sha256"],  # type: ignore[arg-type]
            ranker_contract_sha256=fields["ranker_contract_sha256"],  # type: ignore[arg-type]
            execution_binding=binding,
        )
    except (TypeError, ValueError):
        raise LivingDexDependencyIntegrityV2Error("fit manifest claim fields differ") from None
    if (
        value.get("fit_claim_sha256") != claim.semantic_claim_sha256
        or value.get("fit_execution_identity_sha256") != claim.execution_identity_sha256
    ):
        raise LivingDexDependencyIntegrityV2Error("fit manifest claim identity differs")
    return claim


def v2_fit_record_ids(execution_identity_sha256: str) -> tuple[str, str, str]:
    """Return the deterministic immutable record IDs for one V2 fit execution."""

    suffix = _require_sha256(execution_identity_sha256, "fit execution identity")[:24]
    return (
        f"rootless-v2-fit-{suffix}",
        f"rootless-v2-fit-manifest-{suffix}",
        f"rootless-v2-fit-terminal-{suffix}",
    )


def v2_fit_failure_record_id(execution_identity_sha256: str) -> str:
    """Return the distinct retained-failure namespace for a consumed V2 fit."""

    suffix = _require_sha256(execution_identity_sha256, "fit execution identity")[:24]
    return f"rootless-v2-fit-failure-{suffix}"


def _binding_document_v2(
    fit_claim: DependencyFitClaimV2,
    fit_identity: DependencyEvaluationFitIdentity,
    *,
    fit_manifest_record_sha256: str | None,
) -> dict[str, object]:
    if not isinstance(fit_claim, DependencyFitClaimV2):
        raise TypeError("fit_claim must be a DependencyFitClaimV2")
    if not isinstance(fit_identity, DependencyEvaluationFitIdentity):
        raise TypeError("fit_identity must be a DependencyEvaluationFitIdentity")
    document: dict[str, object] = {
        "schema": (
            DEPENDENCY_EVALUATION_FIT_TERMINAL_SCHEMA_V2
            if fit_manifest_record_sha256 is not None
            else DEPENDENCY_EVALUATION_FIT_MANIFEST_SCHEMA_V2
        ),
        "status": "completed",
        "lane_id": ROOTLESS_DEPENDENCY_EVALUATION_LANE_V2,
        "fit_claim_sha256": fit_claim.semantic_claim_sha256,
        "fit_execution_identity_sha256": fit_claim.execution_identity_sha256,
        "development_roster_sha256": fit_claim.development_roster_sha256,
        "train_revalidation_sha256": fit_claim.train_revalidation_sha256,
        "ranker_contract_sha256": fit_claim.ranker_contract_sha256,
        "execution_binding": fit_claim.execution_binding.public_dict(),
        **fit_identity.public_dict(),
        "development_payloads_opened": 0,
        "development_payloads_decoded": 0,
        "completed_fit_counter_delta": 0,
        "authority_delta": 0,
        "transfer_delta": 0,
    }
    if fit_manifest_record_sha256 is not None:
        document["fit_manifest_record_sha256"] = fit_manifest_record_sha256
    return document


def _require_fit_claim_matches_design(
    design: RootlessDependencyEvaluationDesignV2,
    fit_claim: DependencyFitClaimV2,
) -> None:
    if (
        fit_claim.design_sha256 != design.design_sha256
        or fit_claim.development_roster_sha256 != design.development_roster.roster_sha256
        or fit_claim.train_revalidation_sha256 != design.train_revalidation_sha256
        or fit_claim.ranker_contract_sha256
        != canonical_sha256(rootless_dependency_ranker_contract_v2())
    ):
        raise LivingDexDependencyIntegrityV2Error("V2 fit claim and design differ")


def _other_dependency_action(action: GoalKind) -> GoalKind:
    if action is GoalKind.ACQUIRE_SPECIES:
        return GoalKind.EVOLVE_SPECIES
    if action is GoalKind.EVOLVE_SPECIES:
        return GoalKind.ACQUIRE_SPECIES
    raise LivingDexDependencyIntegrityV2Error("V2 train revalidation action differs")


def _require_sha256(value: object, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise LivingDexDependencyIntegrityV2Error(f"{subject} pin is invalid")
    return value


def _require_record_pin_v2(payload: bytes, expected_sha256: str, subject: str) -> None:
    if not isinstance(payload, bytes):
        raise TypeError(f"{subject} bytes must be bytes")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise LivingDexDependencyIntegrityV2Error(f"{subject} pin differs")


def _parse_canonical_document_v2(
    payload: bytes,
    *,
    maximum_bytes: int,
    subject: str,
) -> dict[str, object]:
    if not isinstance(payload, bytes) or not payload or len(payload) > maximum_bytes:
        raise LivingDexDependencyIntegrityV2Error(f"{subject} size differs")
    try:
        document = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object_v2,
            parse_constant=_reject_constant_v2,
        )
    except (UnicodeDecodeError, ValueError):
        raise LivingDexDependencyIntegrityV2Error(f"{subject} is not canonical JSON") from None
    if not isinstance(document, dict) or _canonical_line_v2(document) != payload:
        raise LivingDexDependencyIntegrityV2Error(f"{subject} is not canonical JSON")
    return document


def _canonical_line_v2(value: Mapping[str, object]) -> bytes:
    try:
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
    except (TypeError, ValueError, UnicodeEncodeError):
        raise LivingDexDependencyIntegrityV2Error("record contains unsupported values") from None


def _unique_object_v2(pairs: list[tuple[str, Any]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant_v2(value: str) -> object:
    del value
    raise ValueError("non-finite JSON value")
