from __future__ import annotations

import json
from copy import deepcopy

import pytest
from test_red_living_dex_option_inventory import _inventory_scenarios

from pokemon_red_completion.red_living_dex_inventory_diagnostics import (
    RedLivingDexInventoryAggregateCounts,
    RedLivingDexInventoryDiagnosticError,
    RedLivingDexInventoryDiagnosticReason,
    RedLivingDexInventoryEffects,
    RedLivingDexInventoryExclusion,
    build_red_living_dex_inventory_diagnostic_receipt,
    validate_red_living_dex_inventory_diagnostic_receipt,
)
from pokemon_red_completion.red_living_dex_option_inventory import (
    RedLivingDexCoverageStatus,
    diagnose_red_living_dex_action_free_coverage,
)


def _counts(*, complete: int = 12) -> RedLivingDexInventoryAggregateCounts:
    return RedLivingDexInventoryAggregateCounts(
        authenticated_input_contexts=12,
        contexts_considered=12,
        materializer_namespaces_authenticated=12,
        emulator_states_read=12,
        historical_replays_authenticated=12,
        scenario_projection_attempts=12,
        complete_menus_projected=complete,
        zero_effect_checks=12,
        coverage_evaluations=1,
        ready_coverage_plans=1,
        private_plan_encoding_attempts=1,
        private_plan_documents_encoded=1,
        protected_integrity_attempts=1,
        protected_integrity_checks_passed=1,
        private_plan_publication_attempts=1,
        private_plan_records_confirmed=1,
    )


def _coverage_failure_counts(
    *,
    complete: int,
) -> RedLivingDexInventoryAggregateCounts:
    return RedLivingDexInventoryAggregateCounts(
        authenticated_input_contexts=complete,
        contexts_considered=complete,
        materializer_namespaces_authenticated=complete,
        emulator_states_read=complete,
        historical_replays_authenticated=complete,
        scenario_projection_attempts=complete,
        complete_menus_projected=complete,
        zero_effect_checks=complete,
        coverage_evaluations=1,
    )


def _exclusions() -> dict[RedLivingDexInventoryExclusion, int]:
    return {item: 0 for item in RedLivingDexInventoryExclusion}


def test_ready_receipt_is_exact_path_free_and_round_trips() -> None:
    coverage, plan = diagnose_red_living_dex_action_free_coverage(
        _inventory_scenarios()
    )
    assert plan is not None

    receipt = build_red_living_dex_inventory_diagnostic_receipt(
        reason=RedLivingDexInventoryDiagnosticReason.COMPLETE,
        counts=_counts(),
        exclusions=_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=coverage,
    )

    validate_red_living_dex_inventory_diagnostic_receipt(receipt)
    assert receipt["status"] == "diagnostic_complete"
    assert receipt["failure_reason"] is None
    assert receipt["effects_verified_zero"] is True
    assert receipt["protected_effect_total"] == 0
    encoded = json.dumps(receipt, allow_nan=False, sort_keys=True)
    for forbidden in (
        "/Users/",
        "/Volumes/",
        "private.family",
        "private.location",
        "red-inventory-",
    ):
        assert forbidden not in encoded


def test_exact_coverage_failure_retains_aggregate_reason() -> None:
    coverage, plan = diagnose_red_living_dex_action_free_coverage(
        _inventory_scenarios()[:-1]
    )
    assert plan is None
    assert coverage.status is (
        RedLivingDexCoverageStatus.INSUFFICIENT_DEVELOPMENT_SCENARIOS
    )

    receipt = build_red_living_dex_inventory_diagnostic_receipt(
        reason=RedLivingDexInventoryDiagnosticReason.EXACT_COVERAGE,
        counts=_coverage_failure_counts(complete=11),
        exclusions=_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=coverage,
    )

    validate_red_living_dex_inventory_diagnostic_receipt(receipt)
    assert receipt["failure_reason"] == "exact_coverage"
    assert receipt["coverage"]["status"] == "insufficient_development_scenarios"


@pytest.mark.parametrize(
    "reason",
    tuple(
        item
        for item in RedLivingDexInventoryDiagnosticReason
        if item
        not in {
            RedLivingDexInventoryDiagnosticReason.COMPLETE,
            RedLivingDexInventoryDiagnosticReason.EXACT_COVERAGE,
            RedLivingDexInventoryDiagnosticReason.PRIVATE_PLAN_ENCODING,
            RedLivingDexInventoryDiagnosticReason.PRIVATE_PLAN_PUBLICATION,
            RedLivingDexInventoryDiagnosticReason.PROTECTED_INPUT_INTEGRITY,
            RedLivingDexInventoryDiagnosticReason.ZERO_EFFECT_AUTHENTICATION,
        }
    ),
)
def test_every_precoverage_failure_reason_is_finite_and_path_free(
    reason: RedLivingDexInventoryDiagnosticReason,
) -> None:
    receipt = build_red_living_dex_inventory_diagnostic_receipt(
        reason=reason,
        counts=RedLivingDexInventoryAggregateCounts(),
        exclusions=_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=None,
    )

    validate_red_living_dex_inventory_diagnostic_receipt(receipt)
    assert receipt["failure_reason"] == reason.value


def test_nonzero_effect_is_reported_and_cannot_use_another_reason() -> None:
    effects = RedLivingDexInventoryEffects(
        controller_actions=1,
        emulator_frames_advanced=3,
    )
    receipt = build_red_living_dex_inventory_diagnostic_receipt(
        reason=RedLivingDexInventoryDiagnosticReason.ZERO_EFFECT_AUTHENTICATION,
        counts=RedLivingDexInventoryAggregateCounts(),
        exclusions=_exclusions(),
        effects=effects,
        coverage=None,
    )

    assert receipt["effects"]["controller_actions"] == 1
    assert receipt["effects"]["emulator_frames_advanced"] == 3
    assert receipt["effects_verified_zero"] is False
    assert receipt["protected_effect_total"] == 4
    validate_red_living_dex_inventory_diagnostic_receipt(receipt)
    with pytest.raises(RedLivingDexInventoryDiagnosticError, match="exact failure"):
        build_red_living_dex_inventory_diagnostic_receipt(
            reason=RedLivingDexInventoryDiagnosticReason.STATE_OBSERVATION,
            counts=RedLivingDexInventoryAggregateCounts(),
            exclusions=_exclusions(),
            effects=effects,
            coverage=None,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("failure_reason", "context-/Users/private"),
        ("protected_effect_total", 1),
        ("effects_verified_zero", False),
        ("private_path_fields", 1),
    ),
)
def test_receipt_rejects_freeform_or_false_zero_mutation(
    field: str,
    replacement: object,
) -> None:
    coverage, _plan = diagnose_red_living_dex_action_free_coverage(
        _inventory_scenarios()
    )
    receipt = build_red_living_dex_inventory_diagnostic_receipt(
        reason=RedLivingDexInventoryDiagnosticReason.COMPLETE,
        counts=_counts(),
        exclusions=_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=coverage,
    )
    mutated = deepcopy(receipt)
    mutated[field] = replacement

    with pytest.raises(RedLivingDexInventoryDiagnosticError):
        validate_red_living_dex_inventory_diagnostic_receipt(mutated)


def test_receipt_rejects_private_extra_field_and_aggregate_misordering() -> None:
    with pytest.raises(RedLivingDexInventoryDiagnosticError, match="ordering"):
        RedLivingDexInventoryAggregateCounts(
            authenticated_input_contexts=1,
            contexts_considered=1,
            materializer_namespaces_authenticated=1,
            emulator_states_read=1,
            historical_replays_authenticated=0,
            scenario_projection_attempts=1,
        )

    receipt = build_red_living_dex_inventory_diagnostic_receipt(
        reason=RedLivingDexInventoryDiagnosticReason.SOURCE_AUTHENTICATION,
        counts=RedLivingDexInventoryAggregateCounts(),
        exclusions=_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=None,
    )
    receipt["capture_id"] = "private-capture"
    with pytest.raises(RedLivingDexInventoryDiagnosticError, match="keys"):
        validate_red_living_dex_inventory_diagnostic_receipt(receipt)


@pytest.mark.parametrize(
    "field",
    (
        "authenticated_input_contexts",
        "contexts_considered",
        "materializer_namespaces_authenticated",
        "emulator_states_read",
        "historical_replays_authenticated",
        "scenario_projection_attempts",
        "complete_menus_projected",
        "zero_effect_checks",
        "coverage_evaluations",
        "ready_coverage_plans",
        "private_plan_encoding_attempts",
        "private_plan_documents_encoded",
        "protected_integrity_attempts",
        "protected_integrity_checks_passed",
        "private_plan_publication_attempts",
        "private_plan_records_confirmed",
    ),
)
def test_complete_receipt_kills_every_stage_counter_mutation(field: str) -> None:
    coverage, _plan = diagnose_red_living_dex_action_free_coverage(
        _inventory_scenarios()
    )
    receipt = build_red_living_dex_inventory_diagnostic_receipt(
        reason=RedLivingDexInventoryDiagnosticReason.COMPLETE,
        counts=_counts(),
        exclusions=_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=coverage,
    )
    mutated = deepcopy(receipt)
    current = mutated["aggregate_counts"][field]
    mutated["aggregate_counts"][field] = 0 if current == 1 else current + 1

    with pytest.raises(RedLivingDexInventoryDiagnosticError):
        validate_red_living_dex_inventory_diagnostic_receipt(mutated)


@pytest.mark.parametrize(
    "field",
    tuple(item.value for item in RedLivingDexInventoryExclusion),
)
def test_complete_receipt_kills_every_exclusion_mutation(field: str) -> None:
    coverage, _plan = diagnose_red_living_dex_action_free_coverage(
        _inventory_scenarios()
    )
    receipt = build_red_living_dex_inventory_diagnostic_receipt(
        reason=RedLivingDexInventoryDiagnosticReason.COMPLETE,
        counts=_counts(),
        exclusions=_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=coverage,
    )
    mutated = deepcopy(receipt)
    mutated["exclusions"][field] = 1

    with pytest.raises(RedLivingDexInventoryDiagnosticError):
        validate_red_living_dex_inventory_diagnostic_receipt(mutated)
