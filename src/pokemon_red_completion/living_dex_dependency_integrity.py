"""Evaluation-integrity boundary for rootless living-Dex dependency fits.

The comparison stage may open development payloads only after this module joins the
exact loaded fit record to externally pinned model, dataset, manifest, terminal,
execution-manifest, and executable-bundle identities.  This module is pure: it does
not know private paths, record stores, development openings, ROMs, or controllers.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pokemon_red_completion.living_dex_dependency_curriculum import (
    RootlessLivingDexDependencyDesign,
)
from pokemon_red_completion.living_dex_dependency_ranker import (
    DependencyRankerFit,
    LivingDexDependencyRankerError,
)

DEPENDENCY_EVALUATION_FIT_MANIFEST_SCHEMA = (
    "pokemon.core.rootless-dependency-evaluation-fit-manifest.v1"
)
DEPENDENCY_EVALUATION_FIT_TERMINAL_SCHEMA = (
    "pokemon.core.rootless-dependency-evaluation-fit-terminal.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_FIT_RECORD_BYTES = 256 * 1024
_MAX_BINDING_RECORD_BYTES = 64 * 1024
_AUTHENTICATED_FIT_TOKEN = object()


class LivingDexDependencyIntegrityError(ValueError):
    """A loaded fit cannot be joined to the externally pinned evaluation bundle."""


@dataclass(frozen=True, slots=True)
class DependencyEvaluationFitIdentity:
    """Semantic and executable identity of one completed train-only fit."""

    design_sha256: str
    train_dataset_sha256: str
    fit_record_sha256: str
    fit_sha256: str
    model_sha256: str
    fit_execution_manifest_sha256: str
    executable_bundle_sha256: str

    def __post_init__(self) -> None:
        values = tuple(self.public_dict().values())
        if any(not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in values):
            raise LivingDexDependencyIntegrityError("evaluation fit identity is invalid")

    def public_dict(self) -> dict[str, str]:
        return {
            "design_sha256": self.design_sha256,
            "train_dataset_sha256": self.train_dataset_sha256,
            "fit_record_sha256": self.fit_record_sha256,
            "fit_sha256": self.fit_sha256,
            "model_sha256": self.model_sha256,
            "fit_execution_manifest_sha256": self.fit_execution_manifest_sha256,
            "executable_bundle_sha256": self.executable_bundle_sha256,
        }


@dataclass(frozen=True, slots=True)
class DependencyEvaluationBundlePins:
    """Externally frozen record pins required before development disclosure."""

    fit_identity: DependencyEvaluationFitIdentity
    fit_manifest_record_sha256: str
    fit_terminal_record_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.fit_identity, DependencyEvaluationFitIdentity) or any(
            not isinstance(value, str) or _SHA256.fullmatch(value) is None
            for value in (
                self.fit_manifest_record_sha256,
                self.fit_terminal_record_sha256,
            )
        ):
            raise LivingDexDependencyIntegrityError("evaluation bundle pin is invalid")
        if (
            len(
                {
                    self.fit_identity.fit_record_sha256,
                    self.fit_manifest_record_sha256,
                    self.fit_terminal_record_sha256,
                }
            )
            != 3
        ):
            raise LivingDexDependencyIntegrityError(
                "fit record, manifest, and terminal pins must be distinct"
            )

    def public_dict(self) -> dict[str, str]:
        return {
            **self.fit_identity.public_dict(),
            "fit_manifest_record_sha256": self.fit_manifest_record_sha256,
            "fit_terminal_record_sha256": self.fit_terminal_record_sha256,
        }


@dataclass(frozen=True, slots=True)
class AuthenticatedDependencyEvaluationFit:
    """Opaque result of one complete exact-bundle authentication."""

    fit: DependencyRankerFit
    pins: DependencyEvaluationBundlePins
    _validation_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._validation_token is not _AUTHENTICATED_FIT_TOKEN:
            raise LivingDexDependencyIntegrityError(
                "authenticated dependency fit must come from the bundle verifier"
            )

    @property
    def model_sha256(self) -> str:
        return self.fit.model.model_sha256

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.authenticated-rootless-dependency-evaluation-fit.v1",
            **self.pins.public_dict(),
            "all_semantic_bindings_joined": True,
            "development_payloads_opened": 0,
        }


def authenticate_dependency_evaluation_fit_bundle(
    design: RootlessLivingDexDependencyDesign,
    *,
    pins: DependencyEvaluationBundlePins,
    fit_record_bytes: bytes,
    fit_manifest_record_bytes: bytes,
    fit_terminal_record_bytes: bytes,
) -> AuthenticatedDependencyEvaluationFit:
    """Join one loaded fit to every external evaluation pin.

    The caller must obtain ``pins`` from an independently authenticated execution
    manifest.  Successful return proves only that these three canonical records and
    the loaded model form that exact frozen bundle.  It does not open or validate any
    development payload and grants no model authority.
    """

    if not isinstance(design, RootlessLivingDexDependencyDesign):
        raise TypeError("design must be a RootlessLivingDexDependencyDesign")
    if not isinstance(pins, DependencyEvaluationBundlePins):
        raise TypeError("pins must be DependencyEvaluationBundlePins")
    identity = pins.fit_identity
    if design.design_sha256 != identity.design_sha256:
        raise LivingDexDependencyIntegrityError("evaluation design pin differs")

    _require_record_pin(fit_record_bytes, identity.fit_record_sha256, "fit record")
    _require_record_pin(
        fit_manifest_record_bytes,
        pins.fit_manifest_record_sha256,
        "fit manifest record",
    )
    _require_record_pin(
        fit_terminal_record_bytes,
        pins.fit_terminal_record_sha256,
        "fit terminal record",
    )

    fit_document = _parse_canonical_document(
        fit_record_bytes,
        maximum_bytes=_MAX_FIT_RECORD_BYTES,
        subject="fit record",
    )
    try:
        fit = DependencyRankerFit.from_dict(fit_document)
    except (LivingDexDependencyRankerError, TypeError, ValueError):
        raise LivingDexDependencyIntegrityError("fit record is invalid") from None
    if (
        fit.design_sha256 != identity.design_sha256
        or fit.train_dataset_sha256 != identity.train_dataset_sha256
        or fit.fit_sha256 != identity.fit_sha256
        or fit.model.model_sha256 != identity.model_sha256
        or fit.model.train_dataset_sha256 != identity.train_dataset_sha256
    ):
        raise LivingDexDependencyIntegrityError("loaded fit semantic identity differs")

    manifest = _parse_canonical_document(
        fit_manifest_record_bytes,
        maximum_bytes=_MAX_BINDING_RECORD_BYTES,
        subject="fit manifest record",
    )
    _require_binding_document(
        manifest,
        schema=DEPENDENCY_EVALUATION_FIT_MANIFEST_SCHEMA,
        pins=pins,
        include_manifest_pin=False,
        subject="fit manifest record",
    )
    terminal = _parse_canonical_document(
        fit_terminal_record_bytes,
        maximum_bytes=_MAX_BINDING_RECORD_BYTES,
        subject="fit terminal record",
    )
    _require_binding_document(
        terminal,
        schema=DEPENDENCY_EVALUATION_FIT_TERMINAL_SCHEMA,
        pins=pins,
        include_manifest_pin=True,
        subject="fit terminal record",
    )
    return AuthenticatedDependencyEvaluationFit(
        fit=fit,
        pins=pins,
        _validation_token=_AUTHENTICATED_FIT_TOKEN,
    )


def dependency_evaluation_fit_manifest_document(
    fit_identity: DependencyEvaluationFitIdentity,
) -> dict[str, object]:
    """Return the exact future fit-manifest document for an already pinned bundle."""

    if not isinstance(fit_identity, DependencyEvaluationFitIdentity):
        raise TypeError("fit_identity must be DependencyEvaluationFitIdentity")
    return _binding_document(fit_identity, fit_manifest_record_sha256=None)


def dependency_evaluation_fit_terminal_document(
    fit_identity: DependencyEvaluationFitIdentity,
    *,
    fit_manifest_record_sha256: str,
) -> dict[str, object]:
    """Return the exact future completed-terminal document for a pinned bundle."""

    if not isinstance(fit_identity, DependencyEvaluationFitIdentity):
        raise TypeError("fit_identity must be DependencyEvaluationFitIdentity")
    if (
        not isinstance(fit_manifest_record_sha256, str)
        or _SHA256.fullmatch(fit_manifest_record_sha256) is None
    ):
        raise LivingDexDependencyIntegrityError("fit manifest record pin is invalid")
    return _binding_document(
        fit_identity,
        fit_manifest_record_sha256=fit_manifest_record_sha256,
    )


def _binding_document(
    fit_identity: DependencyEvaluationFitIdentity,
    *,
    fit_manifest_record_sha256: str | None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": (
            DEPENDENCY_EVALUATION_FIT_TERMINAL_SCHEMA
            if fit_manifest_record_sha256 is not None
            else DEPENDENCY_EVALUATION_FIT_MANIFEST_SCHEMA
        ),
        "status": "completed",
        **fit_identity.public_dict(),
    }
    if fit_manifest_record_sha256 is not None:
        document["fit_manifest_record_sha256"] = fit_manifest_record_sha256
    return document


def _require_binding_document(
    document: Mapping[str, object],
    *,
    schema: str,
    pins: DependencyEvaluationBundlePins,
    include_manifest_pin: bool,
    subject: str,
) -> None:
    expected = _binding_document(
        pins.fit_identity,
        fit_manifest_record_sha256=(
            pins.fit_manifest_record_sha256 if include_manifest_pin else None
        ),
    )
    if dict(document) != expected or document.get("schema") != schema:
        raise LivingDexDependencyIntegrityError(f"{subject} semantic identity differs")


def _require_record_pin(payload: bytes, expected_sha256: str, subject: str) -> None:
    if not isinstance(payload, bytes):
        raise TypeError(f"{subject} bytes must be bytes")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise LivingDexDependencyIntegrityError(f"{subject} pin differs")


def _parse_canonical_document(
    payload: bytes,
    *,
    maximum_bytes: int,
    subject: str,
) -> dict[str, object]:
    if not isinstance(payload, bytes) or not payload or len(payload) > maximum_bytes:
        raise LivingDexDependencyIntegrityError(f"{subject} size differs")
    try:
        document = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError):
        raise LivingDexDependencyIntegrityError(f"{subject} is not canonical JSON") from None
    if not isinstance(document, dict) or _canonical_line(document) != payload:
        raise LivingDexDependencyIntegrityError(f"{subject} is not canonical JSON")
    return document


def _canonical_line(value: Mapping[str, object]) -> bytes:
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
        raise LivingDexDependencyIntegrityError("record contains unsupported values") from None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    del value
    raise ValueError("non-finite JSON value")
