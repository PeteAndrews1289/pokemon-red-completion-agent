"""Strict title-neutral codecs for living-Pokedex policy menus.

The option-value contract deliberately omits private execution references from
``LivingDexOptionMenu.policy_dict()``.  Durable title adapters still need two
different round trips:

* a policy-only learner document whose reconstructed references are inert row
  positions; and
* a private menu document that retains the exact ordered binding references
  beside that same learner-visible policy.

Both decoders reconstruct the typed menu and require byte-for-byte semantic
equality with the supplied canonical document.  They never accept an extra
field, silently normalize a malformed vector, or expose a private reference in
the policy projection.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import cast

from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_CONTEXT_SCHEMA,
    LIVING_DEX_OPTION_FEATURE_NAMES,
    LIVING_DEX_OPTION_FEATURE_SCHEMA,
    LIVING_DEX_OPTION_MENU_SCHEMA,
    LIVING_DEX_OPTION_NORMALIZATION,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionFeatures,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionUnavailableReason,
)

LIVING_DEX_PRIVATE_MENU_SCHEMA = "pokemon.core.private-living-dex-option-menu.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CONTEXT_FIELDS = (
    "collection_pressure",
    "dependency_pressure",
    "access_pressure",
    "resource_pressure",
    "storage_pressure",
    "party_pressure",
    "knowledge_pressure",
)
_CANDIDATE_FIELDS = (
    "completion_gain",
    "dependency_unlock_gain",
    "travel_effort",
    "execution_effort",
    "resource_cost",
    "storage_cost",
    "party_risk",
    "irreversibility_risk",
    "uncertainty",
)


class LivingDexPolicyCodecError(ValueError):
    """A durable policy document cannot reconstruct one exact typed menu."""


def living_dex_private_menu_dict(menu: LivingDexOptionMenu) -> dict[str, object]:
    """Encode one exact policy menu plus its private ordered binding seam."""

    if not isinstance(menu, LivingDexOptionMenu):
        raise TypeError("private menu codec needs a LivingDexOptionMenu")
    menu.__post_init__()
    return {
        "binding_refs": [candidate.binding_ref for candidate in menu.candidates],
        "policy": menu.policy_dict(),
        "policy_sha256": menu.policy_sha256,
        "schema": LIVING_DEX_PRIVATE_MENU_SCHEMA,
    }


def restore_living_dex_private_menu(document: Mapping[str, object]) -> LivingDexOptionMenu:
    """Restore one exact private menu after an outer artifact integrity check."""

    _exact_keys(
        document,
        {"binding_refs", "policy", "policy_sha256", "schema"},
        subject="private living-Dex menu",
    )
    if document["schema"] != LIVING_DEX_PRIVATE_MENU_SCHEMA:
        raise LivingDexPolicyCodecError("private living-Dex menu schema differs")
    bindings = _strings(document["binding_refs"], subject="private menu bindings")
    policy = _mapping(document["policy"], subject="private menu policy")
    menu = restore_living_dex_policy_menu(policy, binding_refs=bindings)
    digest = _sha256(document["policy_sha256"], subject="private menu policy")
    if digest != menu.policy_sha256 or living_dex_private_menu_dict(menu) != dict(document):
        raise LivingDexPolicyCodecError("private living-Dex menu does not replay")
    return menu


def restore_living_dex_policy_menu(
    document: Mapping[str, object],
    *,
    binding_refs: Sequence[str] | None = None,
) -> LivingDexOptionMenu:
    """Restore a learner-visible policy menu with inert references by default."""

    _exact_keys(document, {"candidates", "context", "schema"}, subject="policy menu")
    if document["schema"] != LIVING_DEX_OPTION_MENU_SCHEMA:
        raise LivingDexPolicyCodecError("living-Dex policy menu schema differs")
    context_document = _mapping(document["context"], subject="policy context")
    context = _restore_context(context_document)
    rows = _sequence(document["candidates"], subject="policy candidates")
    if binding_refs is None:
        bindings = tuple(f"policy-row-{index}" for index in range(len(rows)))
    else:
        bindings = tuple(binding_refs)
        if len(bindings) != len(rows):
            raise LivingDexPolicyCodecError("policy binding census differs")
        if any(not isinstance(item, str) or not item for item in bindings):
            raise LivingDexPolicyCodecError("policy binding reference differs")
    candidates = tuple(
        _restore_candidate(
            _mapping(row, subject="policy candidate"),
            context=context,
            binding_ref=bindings[index],
        )
        for index, row in enumerate(rows)
    )
    try:
        menu = LivingDexOptionMenu(context, candidates)
    except (TypeError, ValueError) as error:
        raise LivingDexPolicyCodecError(str(error)) from None
    if menu.policy_dict() != dict(document):
        raise LivingDexPolicyCodecError("living-Dex policy menu does not replay")
    return menu


def _restore_context(document: Mapping[str, object]) -> LivingDexOptionContext:
    _exact_keys(
        document,
        {"schema", *_CONTEXT_FIELDS},
        subject="policy context",
    )
    if document["schema"] != LIVING_DEX_OPTION_CONTEXT_SCHEMA:
        raise LivingDexPolicyCodecError("living-Dex policy context schema differs")
    values = {field: _number(document[field], subject=field) for field in _CONTEXT_FIELDS}
    try:
        context = LivingDexOptionContext(**values)
    except (TypeError, ValueError) as error:
        raise LivingDexPolicyCodecError(str(error)) from None
    if context.policy_dict() != dict(document):
        raise LivingDexPolicyCodecError("living-Dex policy context does not replay")
    return context


def _restore_candidate(
    document: Mapping[str, object],
    *,
    context: LivingDexOptionContext,
    binding_ref: str,
) -> LivingDexOptionCandidate:
    _exact_keys(
        document,
        {"availability", "features", "unavailable_reason"},
        subject="policy candidate",
    )
    feature_document = _mapping(document["features"], subject="candidate features")
    _exact_keys(
        feature_document,
        {"feature_names", "kind", "normalization", "schema", "values"},
        subject="candidate features",
    )
    if (
        feature_document["schema"] != LIVING_DEX_OPTION_FEATURE_SCHEMA
        or feature_document["normalization"] != LIVING_DEX_OPTION_NORMALIZATION
        or tuple(_strings(feature_document["feature_names"], subject="feature names"))
        != LIVING_DEX_OPTION_FEATURE_NAMES
    ):
        raise LivingDexPolicyCodecError("living-Dex candidate feature contract differs")
    values = _numbers(feature_document["values"], subject="candidate feature values")
    if len(values) != len(LIVING_DEX_OPTION_FEATURE_NAMES):
        raise LivingDexPolicyCodecError("living-Dex candidate feature width differs")
    try:
        kind = LivingDexOptionKind(_string(feature_document["kind"], subject="option kind"))
        availability = LivingDexOptionAvailability(
            _string(document["availability"], subject="option availability")
        )
    except ValueError:
        raise LivingDexPolicyCodecError("living-Dex candidate enum differs") from None
    kind_count = len(LivingDexOptionKind)
    feature_values = values[kind_count : kind_count + len(_CANDIDATE_FIELDS)]
    try:
        features = LivingDexOptionFeatures(
            kind=kind,
            **dict(zip(_CANDIDATE_FIELDS, feature_values, strict=True)),
        )
    except (TypeError, ValueError) as error:
        raise LivingDexPolicyCodecError(str(error)) from None
    reason_value = document["unavailable_reason"]
    try:
        reason = (
            None
            if reason_value is None
            else LivingDexOptionUnavailableReason(
                _string(reason_value, subject="unavailable reason")
            )
        )
        candidate = LivingDexOptionCandidate(
            binding_ref,
            features,
            availability,
            reason,
        )
    except (TypeError, ValueError) as error:
        raise LivingDexPolicyCodecError(str(error)) from None
    if candidate.policy_dict(context) != dict(document):
        raise LivingDexPolicyCodecError("living-Dex candidate does not replay")
    return candidate


def _exact_keys(
    document: Mapping[str, object],
    expected: set[str],
    *,
    subject: str,
) -> None:
    if not isinstance(document, Mapping) or set(document) != expected:
        raise LivingDexPolicyCodecError(f"{subject} fields differ")


def _mapping(value: object, *, subject: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise LivingDexPolicyCodecError(f"{subject} differs")
    return value


def _sequence(value: object, *, subject: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise LivingDexPolicyCodecError(f"{subject} differ")
    return tuple(value)


def _strings(value: object, *, subject: str) -> tuple[str, ...]:
    values = _sequence(value, subject=subject)
    if any(not isinstance(item, str) or not item for item in values):
        raise LivingDexPolicyCodecError(f"{subject} differ")
    return cast(tuple[str, ...], values)


def _numbers(value: object, *, subject: str) -> tuple[float, ...]:
    values = _sequence(value, subject=subject)
    return tuple(_number(item, subject=subject) for item in values)


def _number(value: object, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LivingDexPolicyCodecError(f"{subject} differs")
    return float(value)


def _string(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or not value:
        raise LivingDexPolicyCodecError(f"{subject} differs")
    return value


def _sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise LivingDexPolicyCodecError(f"{subject} SHA-256 differs")
    return value


__all__ = [
    "LIVING_DEX_PRIVATE_MENU_SCHEMA",
    "LivingDexPolicyCodecError",
    "living_dex_private_menu_dict",
    "restore_living_dex_policy_menu",
    "restore_living_dex_private_menu",
]
