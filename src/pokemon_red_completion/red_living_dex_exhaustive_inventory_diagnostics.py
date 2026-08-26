"""Exhaustive path-free diagnostics for the authentic Red living-Dex bank.

V2 stopped on the first context-local state-observation exception.  V3 keeps
global safety failures terminal but accounts finite context-local failures as
anonymous exclusions so every authenticated context can still be censused.
No receipt field can carry a path, capture identity, species, map, family,
location, ordering clue, or free-form exception text.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from enum import StrEnum

from pokemon_red_completion.red_living_dex_inventory_diagnostics import (
    RedLivingDexInventoryEffects,
)
from pokemon_red_completion.red_living_dex_option_inventory import (
    RedLivingDexCoverageDiagnostic,
    RedLivingDexCoverageStatus,
)

RED_LIVING_DEX_EXHAUSTIVE_INVENTORY_DIAGNOSTIC_SCHEMA = (
    "pokemon.red.living-dex-exhaustive-inventory-diagnostic.v3"
)


class RedLivingDexExhaustiveInventoryDiagnosticError(ValueError):
    """The exhaustive aggregate receipt is inconsistent or can disclose identity."""


class RedLivingDexExhaustiveInventoryReason(StrEnum):
    """Finite global terminals for one V3 exhaustive inventory identity."""

    COMPLETE = "complete"
    ARGUMENT_AUTHENTICATION = "argument_authentication"
    SOURCE_AUTHENTICATION = "source_authentication"
    PRIVATE_INPUT_AUTHENTICATION = "private_input_authentication"
    RUNTIME_AUTHENTICATION = "runtime_authentication"
    MATERIALIZER_NAMESPACE_AUTHENTICATION = (
        "materializer_namespace_authentication"
    )
    ZERO_EFFECT_AUTHENTICATION = "zero_effect_authentication"
    EXHAUSTIVE_ACCOUNTING = "exhaustive_accounting"
    EXACT_COVERAGE = "exact_coverage"
    PROTECTED_INPUT_INTEGRITY = "protected_input_integrity"
    PRIVATE_PLAN_ENCODING = "private_plan_encoding"
    PRIVATE_PLAN_PUBLICATION = "private_plan_publication"
    UNEXPECTED_FAILURE = "unexpected_failure"


class RedLivingDexExhaustiveInventoryExclusion(StrEnum):
    """Finite anonymous disposition of one authenticated context."""

    SEALED_OR_UNSUPPORTED_PARTITION = "sealed_or_unsupported_partition"
    CONSUMED_PHYSICAL_ROOT = "consumed_physical_root"
    EXISTING_MATERIALIZER_CLAIM = "existing_materializer_claim"
    STATE_RESTORE_FAILURE = "state_restore_failure"
    STATE_OBSERVATION_FAILURE = "state_observation_failure"
    BINDING_ENUMERATION_FAILURE = "binding_enumeration_failure"
    HISTORICAL_REPLAY_FAILURE = "historical_replay_failure"
    FEWER_THAN_THREE_MAPPED_OPTIONS = "fewer_than_three_mapped_options"
    EMPTY_PARTY_OBSERVATION = "empty_party_observation"
    SCENARIO_PROJECTION_FAILURE = "scenario_projection_failure"


_POST_COVERAGE_FAILURES = frozenset(
    {
        RedLivingDexExhaustiveInventoryReason.PROTECTED_INPUT_INTEGRITY,
        RedLivingDexExhaustiveInventoryReason.PRIVATE_PLAN_ENCODING,
        RedLivingDexExhaustiveInventoryReason.PRIVATE_PLAN_PUBLICATION,
    }
)


@dataclass(frozen=True, slots=True)
class RedLivingDexExhaustiveInventoryCounts:
    """Monotone counters for the whole authenticated V3 context pipeline."""

    authenticated_input_contexts: int = 0
    contexts_considered: int = 0
    materializer_namespaces_authenticated: int = 0
    state_restore_attempts: int = 0
    emulator_states_restored: int = 0
    observation_attempts: int = 0
    observations_completed: int = 0
    binding_enumeration_attempts: int = 0
    binding_enumerations_completed: int = 0
    historical_replay_attempts: int = 0
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
            raise RedLivingDexExhaustiveInventoryDiagnosticError(
                "exhaustive aggregate counters differ"
            )
        if not (
            self.contexts_considered <= self.authenticated_input_contexts
            and self.materializer_namespaces_authenticated
            <= self.contexts_considered
            and self.state_restore_attempts
            <= self.materializer_namespaces_authenticated
            and self.emulator_states_restored <= self.state_restore_attempts
            and self.observation_attempts <= self.emulator_states_restored
            and self.observations_completed <= self.observation_attempts
            and self.binding_enumeration_attempts <= self.observations_completed
            and self.binding_enumerations_completed
            <= self.binding_enumeration_attempts
            and self.historical_replay_attempts
            <= self.binding_enumerations_completed
            and self.historical_replays_authenticated
            <= self.historical_replay_attempts
            and self.scenario_projection_attempts
            <= self.historical_replays_authenticated
            and self.complete_menus_projected <= self.scenario_projection_attempts
            and self.zero_effect_checks <= self.state_restore_attempts
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
            raise RedLivingDexExhaustiveInventoryDiagnosticError(
                "exhaustive aggregate ordering differs"
            )

    def public_dict(self) -> dict[str, int]:
        return {item.name: getattr(self, item.name) for item in fields(self)}


def build_red_living_dex_exhaustive_inventory_receipt(
    *,
    reason: RedLivingDexExhaustiveInventoryReason,
    counts: RedLivingDexExhaustiveInventoryCounts,
    exclusions: Mapping[RedLivingDexExhaustiveInventoryExclusion, int],
    effects: RedLivingDexInventoryEffects,
    coverage: RedLivingDexCoverageDiagnostic | None,
) -> dict[str, object]:
    """Build one exact-key V3 receipt from finite values and aggregate counts."""

    if not isinstance(reason, RedLivingDexExhaustiveInventoryReason):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive reason is not finite"
        )
    if not isinstance(counts, RedLivingDexExhaustiveInventoryCounts):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive counts differ"
        )
    if not isinstance(effects, RedLivingDexInventoryEffects):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive effects differ"
        )
    if coverage is not None and not isinstance(
        coverage,
        RedLivingDexCoverageDiagnostic,
    ):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive coverage differs"
        )
    if coverage is not None and coverage.scenario_count != (
        counts.complete_menus_projected
    ):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive coverage count differs"
        )
    normalized = _normalize_exclusions(exclusions)
    if sum(normalized.values()) > counts.contexts_considered:
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive exclusions exceed considered contexts"
        )

    terminal_inventory = reason in (
        _POST_COVERAGE_FAILURES
        | {
            RedLivingDexExhaustiveInventoryReason.COMPLETE,
            RedLivingDexExhaustiveInventoryReason.EXACT_COVERAGE,
        }
    )
    if terminal_inventory:
        _require_exhaustive_accounting(counts, normalized)

    coverage_ready = (
        coverage is not None and coverage.status is RedLivingDexCoverageStatus.READY
    )
    if reason is RedLivingDexExhaustiveInventoryReason.COMPLETE:
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
            raise RedLivingDexExhaustiveInventoryDiagnosticError(
                "complete exhaustive diagnostic differs"
            )
    elif reason is RedLivingDexExhaustiveInventoryReason.EXACT_COVERAGE:
        if (
            coverage is None
            or coverage_ready
            or effects.total != 0
            or counts.coverage_evaluations != 1
            or counts.ready_coverage_plans != 0
            or counts.private_plan_encoding_attempts != 0
        ):
            raise RedLivingDexExhaustiveInventoryDiagnosticError(
                "exhaustive coverage failure differs"
            )
    elif reason in _POST_COVERAGE_FAILURES:
        expected = {
            RedLivingDexExhaustiveInventoryReason.PRIVATE_PLAN_ENCODING: (
                1,
                0,
                0,
                0,
                0,
                0,
            ),
            RedLivingDexExhaustiveInventoryReason.PROTECTED_INPUT_INTEGRITY: (
                1,
                1,
                1,
                0,
                0,
                0,
            ),
            RedLivingDexExhaustiveInventoryReason.PRIVATE_PLAN_PUBLICATION: (
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
            raise RedLivingDexExhaustiveInventoryDiagnosticError(
                "post-coverage exhaustive diagnostic differs"
            )
    elif coverage is not None:
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "pre-coverage exhaustive diagnostic cannot publish coverage"
        )
    if effects.total != 0 and reason is not (
        RedLivingDexExhaustiveInventoryReason.ZERO_EFFECT_AUTHENTICATION
    ):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "nonzero effects need the exact exhaustive failure reason"
        )

    return {
        "aggregate_counts": counts.public_dict(),
        "coverage": None if coverage is None else coverage.public_dict(),
        "effects": effects.public_dict(),
        "effects_verified_zero": effects.total == 0,
        "exclusions": normalized,
        "failure_reason": (
            None if reason is RedLivingDexExhaustiveInventoryReason.COMPLETE else reason.value
        ),
        "private_identity_fields_published": effects.private_identity_fields_published,
        "private_path_fields": effects.private_path_fields,
        "protected_effect_total": effects.total,
        "schema": RED_LIVING_DEX_EXHAUSTIVE_INVENTORY_DIAGNOSTIC_SCHEMA,
        "status": (
            "diagnostic_complete"
            if reason is RedLivingDexExhaustiveInventoryReason.COMPLETE
            else "failed_closed"
        ),
    }


def validate_red_living_dex_exhaustive_inventory_receipt(value: object) -> None:
    """Reject noncanonical fields, free text, false zeroes, and count drift."""

    expected_keys = {
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
    }
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive receipt keys differ"
        )
    try:
        counts = RedLivingDexExhaustiveInventoryCounts(
            **_exact_integer_mapping(
                value.get("aggregate_counts"),
                {item.name for item in fields(RedLivingDexExhaustiveInventoryCounts)},
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
            RedLivingDexExhaustiveInventoryReason.COMPLETE
            if raw_failure is None
            else RedLivingDexExhaustiveInventoryReason(raw_failure)
        )
        coverage = _parse_coverage(value.get("coverage"))
    except (TypeError, ValueError):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive receipt values differ"
        ) from None
    if (
        value.get("schema")
        != RED_LIVING_DEX_EXHAUSTIVE_INVENTORY_DIAGNOSTIC_SCHEMA
        or value.get("status")
        != (
            "diagnostic_complete"
            if reason is RedLivingDexExhaustiveInventoryReason.COMPLETE
            else "failed_closed"
        )
        or value.get("private_identity_fields_published")
        != effects.private_identity_fields_published
        or value.get("private_path_fields") != effects.private_path_fields
        or value.get("protected_effect_total") != effects.total
        or value.get("effects_verified_zero") is not (effects.total == 0)
    ):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive receipt binding differs"
        )
    rebuilt = build_red_living_dex_exhaustive_inventory_receipt(
        reason=reason,
        counts=counts,
        exclusions=exclusions,
        effects=effects,
        coverage=coverage,
    )
    if dict(value) != rebuilt:
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive receipt is not canonical"
        )


def require_red_living_dex_exhaustive_inventory_accounting(
    counts: RedLivingDexExhaustiveInventoryCounts,
    exclusions: Mapping[RedLivingDexExhaustiveInventoryExclusion, int],
) -> None:
    """Require an exact anonymous disposition for every authenticated context."""

    if not isinstance(counts, RedLivingDexExhaustiveInventoryCounts):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive counts differ"
        )
    _require_exhaustive_accounting(counts, _normalize_exclusions(exclusions))


def _require_exhaustive_accounting(
    counts: RedLivingDexExhaustiveInventoryCounts,
    exclusions: Mapping[str, int],
) -> None:
    def excluded(reason: RedLivingDexExhaustiveInventoryExclusion) -> int:
        return exclusions[reason.value]

    if not (
        counts.contexts_considered == counts.authenticated_input_contexts
        and counts.contexts_considered
        == counts.materializer_namespaces_authenticated
        + excluded(
            RedLivingDexExhaustiveInventoryExclusion.SEALED_OR_UNSUPPORTED_PARTITION
        )
        + excluded(RedLivingDexExhaustiveInventoryExclusion.CONSUMED_PHYSICAL_ROOT)
        and counts.materializer_namespaces_authenticated
        == counts.state_restore_attempts
        + excluded(
            RedLivingDexExhaustiveInventoryExclusion.EXISTING_MATERIALIZER_CLAIM
        )
        and counts.state_restore_attempts
        == counts.emulator_states_restored
        + excluded(RedLivingDexExhaustiveInventoryExclusion.STATE_RESTORE_FAILURE)
        and counts.emulator_states_restored == counts.observation_attempts
        and counts.observation_attempts
        == counts.observations_completed
        + excluded(
            RedLivingDexExhaustiveInventoryExclusion.STATE_OBSERVATION_FAILURE
        )
        and counts.observations_completed == counts.binding_enumeration_attempts
        and counts.binding_enumeration_attempts
        == counts.binding_enumerations_completed
        + excluded(
            RedLivingDexExhaustiveInventoryExclusion.BINDING_ENUMERATION_FAILURE
        )
        and counts.binding_enumerations_completed == counts.historical_replay_attempts
        and counts.historical_replay_attempts
        == counts.historical_replays_authenticated
        + excluded(
            RedLivingDexExhaustiveInventoryExclusion.HISTORICAL_REPLAY_FAILURE
        )
        and counts.historical_replays_authenticated
        == counts.scenario_projection_attempts
        + excluded(
            RedLivingDexExhaustiveInventoryExclusion.FEWER_THAN_THREE_MAPPED_OPTIONS
        )
        + excluded(RedLivingDexExhaustiveInventoryExclusion.EMPTY_PARTY_OBSERVATION)
        and counts.scenario_projection_attempts
        == counts.complete_menus_projected
        + excluded(
            RedLivingDexExhaustiveInventoryExclusion.SCENARIO_PROJECTION_FAILURE
        )
        and counts.zero_effect_checks == counts.state_restore_attempts
    ):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive terminal pipeline accounting differs"
        )


def _normalize_exclusions(
    exclusions: Mapping[RedLivingDexExhaustiveInventoryExclusion, int],
) -> dict[str, int]:
    if not isinstance(exclusions, Mapping) or any(
        not isinstance(key, RedLivingDexExhaustiveInventoryExclusion)
        or type(value) is not int  # noqa: E721
        or value < 0
        for key, value in exclusions.items()
    ):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive exclusions differ"
        )
    return {
        reason.value: exclusions.get(reason, 0)
        for reason in RedLivingDexExhaustiveInventoryExclusion
    }


def _parse_exclusions(
    value: object,
) -> dict[RedLivingDexExhaustiveInventoryExclusion, int]:
    expected = {item.value for item in RedLivingDexExhaustiveInventoryExclusion}
    parsed = _exact_integer_mapping(value, expected, "exclusions")
    return {
        RedLivingDexExhaustiveInventoryExclusion(key): count
        for key, count in parsed.items()
    }


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
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive coverage keys differ"
        )
    if (
        value.get("schema")
        != "pokemon.red.living-dex-action-free-coverage-diagnostic.v2"
        or value.get("identity_fields_public") != 0
        or value.get("private_path_fields") != 0
    ):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive coverage boundary differs"
        )
    count_keys = expected - {
        "identity_fields_public",
        "private_path_fields",
        "schema",
        "status",
    }
    counts = _exact_integer_mapping(
        value,
        count_keys,
        "coverage counters",
        allow_extra=expected - count_keys,
    )
    raw_status = value.get("status")
    if not isinstance(raw_status, str):
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            "exhaustive coverage status differs"
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
        raise RedLivingDexExhaustiveInventoryDiagnosticError(
            f"exhaustive {subject} differ"
        )
    parsed: dict[str, int] = {}
    for key in expected:
        raw = value.get(key)
        if type(raw) is not int or raw < 0:  # noqa: E721
            raise RedLivingDexExhaustiveInventoryDiagnosticError(
                f"exhaustive {subject} differ"
            )
        parsed[key] = raw
    return parsed


__all__ = [
    "RED_LIVING_DEX_EXHAUSTIVE_INVENTORY_DIAGNOSTIC_SCHEMA",
    "RedLivingDexExhaustiveInventoryCounts",
    "RedLivingDexExhaustiveInventoryDiagnosticError",
    "RedLivingDexExhaustiveInventoryExclusion",
    "RedLivingDexExhaustiveInventoryReason",
    "build_red_living_dex_exhaustive_inventory_receipt",
    "require_red_living_dex_exhaustive_inventory_accounting",
    "validate_red_living_dex_exhaustive_inventory_receipt",
]
