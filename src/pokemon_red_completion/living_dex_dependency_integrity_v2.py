"""Evaluation-integrity boundary for rootless living-Dex dependency V2 fits."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pokemon_red_completion.living_dex_dependency_evaluation_v2 import (
    FreshDevelopmentCommitmentRosterV2,
    RootlessDependencyEvaluationDesignV2,
)
from pokemon_red_completion.living_dex_dependency_integrity import (
    DependencyEvaluationBundlePins,
    DependencyEvaluationFitIdentity,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DependencyRankerFit,
    LivingDexDependencyRankerError,
)

DEPENDENCY_EVALUATION_FIT_MANIFEST_SCHEMA_V2 = (
    "pokemon.core.rootless-dependency-evaluation-fit-manifest.v2"
)
DEPENDENCY_EVALUATION_FIT_TERMINAL_SCHEMA_V2 = (
    "pokemon.core.rootless-dependency-evaluation-fit-terminal.v2"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_FIT_RECORD_BYTES = 256 * 1024
_MAX_BINDING_RECORD_BYTES = 64 * 1024
_AUTHENTICATED_FIT_TOKEN_V2 = object()


class LivingDexDependencyIntegrityV2Error(ValueError):
    """A loaded V2 fit cannot be joined to the externally pinned evaluation bundle."""


@dataclass(frozen=True, slots=True)
class AuthenticatedDependencyEvaluationFitV2:
    """Opaque result of one complete exact-bundle authentication for V2."""

    fit: DependencyRankerFit
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
            **self.pins.public_dict(),
            "all_semantic_bindings_joined": True,
            "development_payloads_opened": 0,
        }


def authenticate_v2_dependency_evaluation_fit_bundle(
    design: RootlessDependencyEvaluationDesignV2,
    *,
    pins: DependencyEvaluationBundlePins,
    fit_record_bytes: bytes,
    fit_manifest_record_bytes: bytes,
    fit_terminal_record_bytes: bytes,
) -> AuthenticatedDependencyEvaluationFitV2:
    """Join one loaded V2 fit to every external evaluation pin.

    The caller must obtain ``pins`` from an independently authenticated execution
    manifest. Successful return proves only that these three canonical records and
    the loaded model form that exact frozen bundle. It does not open or validate any
    development payload and grants no model authority.
    """

    if not isinstance(design, RootlessDependencyEvaluationDesignV2):
        raise TypeError("design must be a RootlessDependencyEvaluationDesignV2")
    if not isinstance(pins, DependencyEvaluationBundlePins):
        raise TypeError("pins must be DependencyEvaluationBundlePins")
    identity = pins.fit_identity
    if design.design_sha256 != identity.design_sha256:
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
    _require_binding_document_v2(
        manifest,
        schema=DEPENDENCY_EVALUATION_FIT_MANIFEST_SCHEMA_V2,
        pins=pins,
        include_manifest_pin=False,
        subject="fit manifest record",
    )
    terminal = _parse_canonical_document_v2(
        fit_terminal_record_bytes,
        maximum_bytes=_MAX_BINDING_RECORD_BYTES,
        subject="fit terminal record",
    )
    _require_binding_document_v2(
        terminal,
        schema=DEPENDENCY_EVALUATION_FIT_TERMINAL_SCHEMA_V2,
        pins=pins,
        include_manifest_pin=True,
        subject="fit terminal record",
    )
    return AuthenticatedDependencyEvaluationFitV2(
        fit=fit,
        pins=pins,
        _validation_token=_AUTHENTICATED_FIT_TOKEN_V2,
    )


def dependency_evaluation_fit_manifest_document_v2(
    fit_identity: DependencyEvaluationFitIdentity,
) -> dict[str, object]:
    """Return the exact future fit-manifest document for an already pinned V2 bundle."""

    if not isinstance(fit_identity, DependencyEvaluationFitIdentity):
        raise TypeError("fit_identity must be DependencyEvaluationFitIdentity")
    return _binding_document_v2(fit_identity, fit_manifest_record_sha256=None)


def dependency_evaluation_fit_terminal_document_v2(
    fit_identity: DependencyEvaluationFitIdentity,
    *,
    fit_manifest_record_sha256: str,
) -> dict[str, object]:
    """Return the exact future completed-terminal document for a pinned V2 bundle."""

    if not isinstance(fit_identity, DependencyEvaluationFitIdentity):
        raise TypeError("fit_identity must be DependencyEvaluationFitIdentity")
    if (
        not isinstance(fit_manifest_record_sha256, str)
        or _SHA256.fullmatch(fit_manifest_record_sha256) is None
    ):
        raise LivingDexDependencyIntegrityV2Error("fit manifest record pin is invalid")
    return _binding_document_v2(
        fit_identity,
        fit_manifest_record_sha256=fit_manifest_record_sha256,
    )


def _binding_document_v2(
    fit_identity: DependencyEvaluationFitIdentity,
    *,
    fit_manifest_record_sha256: str | None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": (
            DEPENDENCY_EVALUATION_FIT_TERMINAL_SCHEMA_V2
            if fit_manifest_record_sha256 is not None
            else DEPENDENCY_EVALUATION_FIT_MANIFEST_SCHEMA_V2
        ),
        "status": "completed",
        **fit_identity.public_dict(),
    }
    if fit_manifest_record_sha256 is not None:
        document["fit_manifest_record_sha256"] = fit_manifest_record_sha256
    return document


def _require_binding_document_v2(
    document: Mapping[str, object],
    *,
    schema: str,
    pins: DependencyEvaluationBundlePins,
    include_manifest_pin: bool,
    subject: str,
) -> None:
    expected = _binding_document_v2(
        pins.fit_identity,
        fit_manifest_record_sha256=(
            pins.fit_manifest_record_sha256 if include_manifest_pin else None
        ),
    )
    if dict(document) != expected or document.get("schema") != schema:
        raise LivingDexDependencyIntegrityV2Error(f"{subject} semantic identity differs")


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


def inventory_v2_development_metadata(
    roster: FreshDevelopmentCommitmentRosterV2,
    *,
    sealed_development_records: Mapping[str, bytes],
) -> None:
    """Validate sealed V2 development openings without decoding their payloads.

    Proves that the V2 pipeline can inventory the dependencies for fit preflight
    by comparing canonical size and cryptographic identity only, without opening
    the private JSON payload or decoding its contents.
    """
    if not isinstance(roster, FreshDevelopmentCommitmentRosterV2):
        raise TypeError("roster must be FreshDevelopmentCommitmentRosterV2")
    if not isinstance(sealed_development_records, Mapping):
        raise TypeError("sealed_development_records must be Mapping")

    expected_ids = {row.record_id for row in roster.rows}
    if set(sealed_development_records.keys()) != expected_ids:
        raise LivingDexDependencyIntegrityV2Error(
            "inventory exactly requires the four roster commitments"
        )

    for row in roster.rows:
        payload = sealed_development_records[row.record_id]
        if not isinstance(payload, bytes):
            raise TypeError("sealed record must be bytes")

        if len(payload) != row.declared_total_bytes:
            raise LivingDexDependencyIntegrityV2Error("sealed record length differs")

        payload_sha256 = hashlib.sha256(payload).hexdigest()
        if payload_sha256 != row.declared_record_sha256:
            raise LivingDexDependencyIntegrityV2Error(
                "sealed record cryptographic identity differs"
            )
