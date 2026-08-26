"""Path-free diagnostics for the authentic Red living-Dex inventory.

The V1 inventory failed safely but collapsed every post-authentication failure
into one public stage.  This module defines the finite V2 vocabulary and the
strict aggregate-only receipt.  It accepts no path, hash, capture identifier,
species, map, family, location, or free-form exception text.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import StrEnum

from pokemon_red_completion.red_living_dex_option_inventory import (
    RedLivingDexCoverageDiagnostic,
    RedLivingDexCoverageStatus,
)

RED_LIVING_DEX_AUTHENTIC_INVENTORY_DIAGNOSTIC_SCHEMA = (
    "pokemon.red.living-dex-authentic-inventory-diagnostic.v2"
)


class RedLivingDexInventoryDiagnosticError(ValueError):
    """The aggregate V2 diagnostic is inconsistent or could disclose identity."""


class RedLivingDexInventoryDiagnosticReason(StrEnum):
    """Finite public stages for one new-identity V2 inventory attempt."""

    COMPLETE = "complete"
    ARGUMENT_AUTHENTICATION = "argument_authentication"
    SOURCE_AUTHENTICATION = "source_authentication"
    PRIVATE_INPUT_AUTHENTICATION = "private_input_authentication"
    RUNTIME_AUTHENTICATION = "runtime_authentication"
    MATERIALIZER_NAMESPACE_AUTHENTICATION = (
        "materializer_namespace_authentication"
    )
    STATE_OBSERVATION = "state_observation"
    HISTORICAL_REPLAY = "historical_replay"
    SCENARIO_PROJECTION = "scenario_projection"
    ZERO_EFFECT_AUTHENTICATION = "zero_effect_authentication"
    EXACT_COVERAGE = "exact_coverage"
    PROTECTED_INPUT_INTEGRITY = "protected_input_integrity"
    PRIVATE_PLAN_ENCODING = "private_plan_encoding"
    PRIVATE_PLAN_PUBLICATION = "private_plan_publication"
    UNEXPECTED_FAILURE = "unexpected_failure"


class RedLivingDexInventoryExclusion(StrEnum):
    """Finite non-terminal reasons that an authenticated context was not eligible."""

    SEALED_OR_UNSUPPORTED_PARTITION = "sealed_or_unsupported_partition"
    CONSUMED_PHYSICAL_ROOT = "consumed_physical_root"
    EXISTING_MATERIALIZER_CLAIM = "existing_materializer_claim"
    FEWER_THAN_THREE_MAPPED_OPTIONS = "fewer_than_three_mapped_options"
    EMPTY_PARTY_OBSERVATION = "empty_party_observation"


_POST_COVERAGE_FAILURES = frozenset(
    {
        RedLivingDexInventoryDiagnosticReason.PROTECTED_INPUT_INTEGRITY,
        RedLivingDexInventoryDiagnosticReason.PRIVATE_PLAN_ENCODING,
        RedLivingDexInventoryDiagnosticReason.PRIVATE_PLAN_PUBLICATION,
    }
)


@dataclass(frozen=True, slots=True)
class RedLivingDexInventoryEffects:
    """All protected effects, including nonzero evidence if a guard ever trips."""

    behavior_draws: int = 0
    controller_authority_attempts: int = 0
    controller_actions: int = 0
    emulator_frames_advanced: int = 0
    model_fits: int = 0
    model_predictions: int = 0
    outcomes_observed: int = 0
    private_identity_fields_published: int = 0
    private_path_fields: int = 0
    root_claims: int = 0
    teacher_queries: int = 0

    def __post_init__(self) -> None:
        if any(
            type(getattr(self, item.name)) is not int  # noqa: E721
            or getattr(self, item.name) < 0
            for item in fields(self)
        ):
            raise RedLivingDexInventoryDiagnosticError(
                "diagnostic effect counters differ"
            )

    @property
    def total(self) -> int:
        return sum(getattr(self, item.name) for item in fields(self))

    def public_dict(self) -> dict[str, int]:
        return {
            item.name: getattr(self, item.name)
            for item in fields(self)
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexInventoryAggregateCounts:
    """Monotone aggregate counters retained across every private V2 stage."""

    authenticated_input_contexts: int = 0
    contexts_considered: int = 0
    materializer_namespaces_authenticated: int = 0
    emulator_states_read: int = 0
    historical_replays_authenticated: int = 0
    scenario_projection_attempts: int = 0
    complete_menus_projected: int = 0
    zero_effect_checks: int = 0
    coverage_evaluations: int = 0
    ready_coverage_plans: int = 0
    private_plan_encoding_attempts: int = 0
    private_plan_documents_encoded: int = 0
    protected_integrity_attempts: int = 0
    protected_integrity_checks_passed: int = 0
    private_plan_publication_attempts: int = 0
    private_plan_records_confirmed: int = 0

    def __post_init__(self) -> None:
        counts = tuple(getattr(self, item.name) for item in fields(self))
        if any(type(value) is not int or value < 0 for value in counts):  # noqa: E721
            raise RedLivingDexInventoryDiagnosticError(
                "diagnostic aggregate counters differ"
            )
        if not (
            self.contexts_considered <= self.authenticated_input_contexts
            and self.materializer_namespaces_authenticated
            <= self.contexts_considered
            and self.emulator_states_read <= self.materializer_namespaces_authenticated
            and self.historical_replays_authenticated <= self.emulator_states_read
            and self.scenario_projection_attempts
            <= self.historical_replays_authenticated
            and self.complete_menus_projected <= self.scenario_projection_attempts
            and self.zero_effect_checks <= self.emulator_states_read
            and self.ready_coverage_plans <= self.coverage_evaluations <= 1
            and self.private_plan_encoding_attempts <= self.ready_coverage_plans
            and self.private_plan_documents_encoded
            <= self.private_plan_encoding_attempts
            and self.protected_integrity_attempts
            <= self.private_plan_documents_encoded
            and self.protected_integrity_checks_passed
            <= self.protected_integrity_attempts
            and self.private_plan_publication_attempts
            <= self.protected_integrity_checks_passed
            and self.private_plan_records_confirmed
            <= self.private_plan_publication_attempts
        ):
            raise RedLivingDexInventoryDiagnosticError(
                "diagnostic aggregate ordering differs"
            )

    def public_dict(self) -> dict[str, int]:
        return {
            item.name: getattr(self, item.name)
            for item in fields(self)
        }


def build_red_living_dex_inventory_diagnostic_receipt(
    *,
    reason: RedLivingDexInventoryDiagnosticReason,
    counts: RedLivingDexInventoryAggregateCounts,
    exclusions: Mapping[RedLivingDexInventoryExclusion, int],
    effects: RedLivingDexInventoryEffects,
    coverage: RedLivingDexCoverageDiagnostic | None,
) -> dict[str, object]:
    """Build one exact-key receipt whose strings all come from finite enums."""

    if not isinstance(reason, RedLivingDexInventoryDiagnosticReason):
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic reason is not finite"
        )
    if not isinstance(counts, RedLivingDexInventoryAggregateCounts):
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic counts differ"
        )
    if not isinstance(effects, RedLivingDexInventoryEffects):
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic effects differ"
        )
    if coverage is not None and not isinstance(
        coverage,
        RedLivingDexCoverageDiagnostic,
    ):
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic coverage differs"
        )
    if (
        coverage is not None
        and coverage.scenario_count != counts.complete_menus_projected
    ):
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic coverage count differs"
        )
    normalized_exclusions = _normalize_exclusions(exclusions)
    if sum(normalized_exclusions.values()) > counts.contexts_considered:
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic exclusions exceed considered contexts"
        )
    terminal_inventory = reason in (
        _POST_COVERAGE_FAILURES
        | {
            RedLivingDexInventoryDiagnosticReason.COMPLETE,
            RedLivingDexInventoryDiagnosticReason.EXACT_COVERAGE,
        }
    )
    if terminal_inventory and not (
        counts.contexts_considered == counts.authenticated_input_contexts
        and counts.contexts_considered
        == counts.materializer_namespaces_authenticated
        + normalized_exclusions[
            RedLivingDexInventoryExclusion.SEALED_OR_UNSUPPORTED_PARTITION.value
        ]
        + normalized_exclusions[
            RedLivingDexInventoryExclusion.CONSUMED_PHYSICAL_ROOT.value
        ]
        and counts.materializer_namespaces_authenticated
        == counts.emulator_states_read
        + normalized_exclusions[
            RedLivingDexInventoryExclusion.EXISTING_MATERIALIZER_CLAIM.value
        ]
        and counts.emulator_states_read
        == counts.historical_replays_authenticated
        and counts.historical_replays_authenticated
        == counts.scenario_projection_attempts
        + normalized_exclusions[
            RedLivingDexInventoryExclusion.FEWER_THAN_THREE_MAPPED_OPTIONS.value
        ]
        + normalized_exclusions[
            RedLivingDexInventoryExclusion.EMPTY_PARTY_OBSERVATION.value
        ]
        and counts.scenario_projection_attempts == counts.complete_menus_projected
        and counts.zero_effect_checks == counts.emulator_states_read
    ):
        raise RedLivingDexInventoryDiagnosticError(
            "terminal diagnostic pipeline accounting differs"
        )
    coverage_ready = (
        coverage is not None and coverage.status is RedLivingDexCoverageStatus.READY
    )
    if reason is RedLivingDexInventoryDiagnosticReason.COMPLETE:
        if (
            not coverage_ready
            or effects.total != 0
            or counts.coverage_evaluations != 1
            or counts.ready_coverage_plans != 1
            or counts.private_plan_encoding_attempts != 1
            or counts.private_plan_documents_encoded != 1
            or counts.protected_integrity_attempts != 1
            or counts.protected_integrity_checks_passed != 1
            or counts.private_plan_publication_attempts != 1
            or counts.private_plan_records_confirmed != 1
        ):
            raise RedLivingDexInventoryDiagnosticError(
                "complete diagnostic lacks ready zero-effect coverage"
            )
    elif reason is RedLivingDexInventoryDiagnosticReason.EXACT_COVERAGE:
        if (
            coverage is None
            or coverage_ready
            or effects.total != 0
            or counts.coverage_evaluations != 1
            or counts.ready_coverage_plans != 0
            or counts.private_plan_encoding_attempts != 0
        ):
            raise RedLivingDexInventoryDiagnosticError(
                "coverage failure diagnostic differs"
            )
    elif reason in _POST_COVERAGE_FAILURES:
        expected = {
            RedLivingDexInventoryDiagnosticReason.PRIVATE_PLAN_ENCODING: (
                1,
                0,
                0,
                0,
                0,
                0,
            ),
            RedLivingDexInventoryDiagnosticReason.PROTECTED_INPUT_INTEGRITY: (
                1,
                1,
                1,
                0,
                0,
                0,
            ),
            RedLivingDexInventoryDiagnosticReason.PRIVATE_PLAN_PUBLICATION: (
                1,
                1,
                1,
                1,
                1,
                0,
            ),
        }[reason]
        observed = (
            counts.private_plan_encoding_attempts,
            counts.private_plan_documents_encoded,
            counts.protected_integrity_attempts,
            counts.protected_integrity_checks_passed,
            counts.private_plan_publication_attempts,
            counts.private_plan_records_confirmed,
        )
        if (
            not coverage_ready
            or effects.total != 0
            or counts.coverage_evaluations != 1
            or counts.ready_coverage_plans != 1
            or observed != expected
        ):
            raise RedLivingDexInventoryDiagnosticError(
                "post-coverage diagnostic differs"
            )
    elif coverage is not None:
        raise RedLivingDexInventoryDiagnosticError(
            "pre-coverage diagnostic cannot publish coverage"
        )
    if effects.total != 0 and reason is not (
        RedLivingDexInventoryDiagnosticReason.ZERO_EFFECT_AUTHENTICATION
    ):
        raise RedLivingDexInventoryDiagnosticError(
            "nonzero effects need the exact failure reason"
        )

    receipt: dict[str, object] = {
        "aggregate_counts": counts.public_dict(),
        "coverage": None if coverage is None else coverage.public_dict(),
        "effects": effects.public_dict(),
        "effects_verified_zero": effects.total == 0,
        "exclusions": normalized_exclusions,
        "failure_reason": (
            None
            if reason is RedLivingDexInventoryDiagnosticReason.COMPLETE
            else reason.value
        ),
        "private_identity_fields_published": effects.private_identity_fields_published,
        "private_path_fields": effects.private_path_fields,
        "protected_effect_total": effects.total,
        "schema": RED_LIVING_DEX_AUTHENTIC_INVENTORY_DIAGNOSTIC_SCHEMA,
        "status": (
            "diagnostic_complete"
            if reason is RedLivingDexInventoryDiagnosticReason.COMPLETE
            else "failed_closed"
        ),
    }
    return receipt


def validate_red_living_dex_inventory_diagnostic_receipt(
    value: object,
) -> None:
    """Reject free-form strings, missing counters, false zeroes, and extra fields."""

    if not isinstance(value, Mapping) or set(value) != {
        "aggregate_counts",
        "coverage",
        "effects",
        "effects_verified_zero",
        "exclusions",
        "failure_reason",
        "private_identity_fields_published",
        "private_path_fields",
        "protected_effect_total",
        "schema",
        "status",
    }:
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic receipt keys differ"
        )
    try:
        counts = RedLivingDexInventoryAggregateCounts(
            **_exact_integer_mapping(
                value.get("aggregate_counts"),
                {item.name for item in fields(RedLivingDexInventoryAggregateCounts)},
                "aggregate counts",
            )
        )
        effects = RedLivingDexInventoryEffects(
            **_exact_integer_mapping(
                value.get("effects"),
                {item.name for item in fields(RedLivingDexInventoryEffects)},
                "effects",
            )
        )
        exclusions = _parse_exclusions(value.get("exclusions"))
        raw_failure = value.get("failure_reason")
        reason = (
            RedLivingDexInventoryDiagnosticReason.COMPLETE
            if raw_failure is None
            else RedLivingDexInventoryDiagnosticReason(raw_failure)
        )
        coverage = _parse_coverage(value.get("coverage"))
    except (TypeError, ValueError):
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic receipt values differ"
        ) from None
    if (
        value.get("schema")
        != RED_LIVING_DEX_AUTHENTIC_INVENTORY_DIAGNOSTIC_SCHEMA
        or value.get("status")
        != (
            "diagnostic_complete"
            if reason is RedLivingDexInventoryDiagnosticReason.COMPLETE
            else "failed_closed"
        )
        or value.get("private_identity_fields_published")
        != effects.private_identity_fields_published
        or value.get("private_path_fields") != effects.private_path_fields
        or value.get("protected_effect_total") != effects.total
        or value.get("effects_verified_zero") is not (effects.total == 0)
    ):
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic receipt binding differs"
        )
    rebuilt = build_red_living_dex_inventory_diagnostic_receipt(
        reason=reason,
        counts=counts,
        exclusions=exclusions,
        effects=effects,
        coverage=coverage,
    )
    if dict(value) != rebuilt:
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic receipt is not canonical"
        )


def _normalize_exclusions(
    exclusions: Mapping[RedLivingDexInventoryExclusion, int],
) -> dict[str, int]:
    if not isinstance(exclusions, Mapping) or any(
        not isinstance(key, RedLivingDexInventoryExclusion)
        or type(value) is not int  # noqa: E721
        or value < 0
        for key, value in exclusions.items()
    ):
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic exclusions differ"
        )
    return {
        reason.value: exclusions.get(reason, 0)
        for reason in RedLivingDexInventoryExclusion
    }


def _parse_exclusions(value: object) -> dict[RedLivingDexInventoryExclusion, int]:
    expected = {item.value for item in RedLivingDexInventoryExclusion}
    parsed = _exact_integer_mapping(value, expected, "exclusions")
    return {RedLivingDexInventoryExclusion(key): count for key, count in parsed.items()}


def _parse_coverage(value: object) -> RedLivingDexCoverageDiagnostic | None:
    if value is None:
        return None
    expected = {
        "candidate_development_subset_count",
        "development_family_count",
        "development_location_count",
        "development_offered_option_kind_count",
        "development_scenario_count",
        "exact_plan_scenario_count",
        "identity_fields_public",
        "maximum_disjoint_train_family_count",
        "maximum_disjoint_train_option_kind_count",
        "maximum_disjoint_train_scenario_count",
        "minimum_train_development_family_overlap",
        "minimum_train_development_location_overlap",
        "private_path_fields",
        "qualifying_development_subset_count",
        "scenario_count",
        "schema",
        "status",
        "train_family_count",
        "train_location_count",
        "train_offered_option_kind_count",
        "train_scenario_count",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic coverage keys differ"
        )
    if (
        value.get("schema")
        != "pokemon.red.living-dex-action-free-coverage-diagnostic.v2"
        or value.get("identity_fields_public") != 0
        or value.get("private_path_fields") != 0
    ):
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic coverage boundary differs"
        )
    counts = _exact_integer_mapping(
        value,
        expected
        - {
            "identity_fields_public",
            "private_path_fields",
            "schema",
            "status",
        },
        "coverage counters",
        allow_extra=expected
        - {
            "candidate_development_subset_count",
            "development_family_count",
            "development_location_count",
            "development_offered_option_kind_count",
            "development_scenario_count",
            "exact_plan_scenario_count",
            "maximum_disjoint_train_family_count",
            "maximum_disjoint_train_option_kind_count",
            "maximum_disjoint_train_scenario_count",
            "minimum_train_development_family_overlap",
            "minimum_train_development_location_overlap",
            "qualifying_development_subset_count",
            "scenario_count",
            "train_family_count",
            "train_location_count",
            "train_offered_option_kind_count",
            "train_scenario_count",
        },
    )
    raw_status = value.get("status")
    if not isinstance(raw_status, str):
        raise RedLivingDexInventoryDiagnosticError(
            "diagnostic coverage status differs"
        )
    return RedLivingDexCoverageDiagnostic(
        status=RedLivingDexCoverageStatus(raw_status),
        **counts,
    )


def _exact_integer_mapping(
    value: object,
    expected: set[str],
    subject: str,
    *,
    allow_extra: set[str] | None = None,
) -> dict[str, int]:
    allowed_extra = set() if allow_extra is None else allow_extra
    if not isinstance(value, Mapping) or set(value) != expected | allowed_extra:
        raise RedLivingDexInventoryDiagnosticError(
            f"diagnostic {subject} differ"
        )
    parsed: dict[str, int] = {}
    for key in expected:
        raw = value.get(key)
        if type(raw) is not int or raw < 0:  # noqa: E721
            raise RedLivingDexInventoryDiagnosticError(
                f"diagnostic {subject} differ"
            )
        parsed[key] = raw
    return parsed


__all__ = [
    "RED_LIVING_DEX_AUTHENTIC_INVENTORY_DIAGNOSTIC_SCHEMA",
    "RedLivingDexInventoryAggregateCounts",
    "RedLivingDexInventoryDiagnosticError",
    "RedLivingDexInventoryDiagnosticReason",
    "RedLivingDexInventoryEffects",
    "RedLivingDexInventoryExclusion",
    "build_red_living_dex_inventory_diagnostic_receipt",
    "validate_red_living_dex_inventory_diagnostic_receipt",
]
