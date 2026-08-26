from __future__ import annotations

import json
from copy import deepcopy

import pytest
from test_red_living_dex_option_inventory import _inventory_scenarios

from pokemon_red_completion.red_living_dex_exhaustive_inventory_diagnostics import (
    RedLivingDexExhaustiveInventoryCounts,
    RedLivingDexExhaustiveInventoryDiagnosticError,
    RedLivingDexExhaustiveInventoryExclusion,
    RedLivingDexExhaustiveInventoryReason,
    build_red_living_dex_exhaustive_inventory_receipt,
    validate_red_living_dex_exhaustive_inventory_receipt,
)
from pokemon_red_completion.red_living_dex_inventory_diagnostics import (
    RedLivingDexInventoryEffects,
)
from pokemon_red_completion.red_living_dex_option_inventory import (
    diagnose_red_living_dex_action_free_coverage,
)


def _zero_exclusions() -> dict[RedLivingDexExhaustiveInventoryExclusion, int]:
    return {item: 0 for item in RedLivingDexExhaustiveInventoryExclusion}


def _ready_counts() -> RedLivingDexExhaustiveInventoryCounts:
    return RedLivingDexExhaustiveInventoryCounts(
        authenticated_input_contexts=12,
        contexts_considered=12,
        materializer_namespaces_authenticated=12,
        state_restore_attempts=12,
        emulator_states_restored=12,
        observation_attempts=12,
        observations_completed=12,
        binding_enumeration_attempts=12,
        binding_enumerations_completed=12,
        historical_replay_attempts=12,
        historical_replays_authenticated=12,
        scenario_projection_attempts=12,
        complete_menus_projected=12,
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


def _mixed_exclusions() -> dict[RedLivingDexExhaustiveInventoryExclusion, int]:
    return {item: 1 for item in RedLivingDexExhaustiveInventoryExclusion}


def _mixed_counts() -> RedLivingDexExhaustiveInventoryCounts:
    return RedLivingDexExhaustiveInventoryCounts(
        authenticated_input_contexts=11,
        contexts_considered=11,
        materializer_namespaces_authenticated=9,
        state_restore_attempts=8,
        emulator_states_restored=7,
        observation_attempts=7,
        observations_completed=6,
        binding_enumeration_attempts=6,
        binding_enumerations_completed=5,
        historical_replay_attempts=5,
        historical_replays_authenticated=4,
        scenario_projection_attempts=2,
        complete_menus_projected=1,
        zero_effect_checks=8,
        coverage_evaluations=1,
    )


def test_complete_exhaustive_receipt_is_exact_path_free_and_canonical() -> None:
    coverage, plan = diagnose_red_living_dex_action_free_coverage(
        _inventory_scenarios()
    )
    assert plan is not None

    receipt = build_red_living_dex_exhaustive_inventory_receipt(
        reason=RedLivingDexExhaustiveInventoryReason.COMPLETE,
        counts=_ready_counts(),
        exclusions=_zero_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=coverage,
    )

    validate_red_living_dex_exhaustive_inventory_receipt(receipt)
    assert receipt["status"] == "diagnostic_complete"
    assert receipt["failure_reason"] is None
    assert receipt["protected_effect_total"] == 0
    encoded = json.dumps(receipt, allow_nan=False, sort_keys=True)
    for forbidden in (
        "/Users/",
        "/Volumes/",
        "private.family",
        "private.location",
        "capture_id",
    ):
        assert forbidden not in encoded


def test_every_context_local_disposition_reconciles_in_one_terminal() -> None:
    coverage, plan = diagnose_red_living_dex_action_free_coverage(
        _inventory_scenarios()[:1]
    )
    assert plan is None

    receipt = build_red_living_dex_exhaustive_inventory_receipt(
        reason=RedLivingDexExhaustiveInventoryReason.EXACT_COVERAGE,
        counts=_mixed_counts(),
        exclusions=_mixed_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=coverage,
    )

    validate_red_living_dex_exhaustive_inventory_receipt(receipt)
    assert receipt["failure_reason"] == "exact_coverage"
    assert receipt["coverage"]["scenario_count"] == 1
    assert set(receipt["exclusions"].values()) == {1}


@pytest.mark.parametrize(
    "field",
    (
        "authenticated_input_contexts",
        "contexts_considered",
        "materializer_namespaces_authenticated",
        "state_restore_attempts",
        "emulator_states_restored",
        "observation_attempts",
        "observations_completed",
        "binding_enumeration_attempts",
        "binding_enumerations_completed",
        "historical_replay_attempts",
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
def test_complete_receipt_kills_every_aggregate_counter_mutation(field: str) -> None:
    coverage, _plan = diagnose_red_living_dex_action_free_coverage(
        _inventory_scenarios()
    )
    receipt = build_red_living_dex_exhaustive_inventory_receipt(
        reason=RedLivingDexExhaustiveInventoryReason.COMPLETE,
        counts=_ready_counts(),
        exclusions=_zero_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=coverage,
    )
    mutated = deepcopy(receipt)
    current = mutated["aggregate_counts"][field]
    mutated["aggregate_counts"][field] = 0 if current == 1 else current + 1

    with pytest.raises(RedLivingDexExhaustiveInventoryDiagnosticError):
        validate_red_living_dex_exhaustive_inventory_receipt(mutated)


@pytest.mark.parametrize(
    "field",
    tuple(item.value for item in RedLivingDexExhaustiveInventoryExclusion),
)
def test_mixed_receipt_kills_every_exclusion_mutation(field: str) -> None:
    coverage, _plan = diagnose_red_living_dex_action_free_coverage(
        _inventory_scenarios()[:1]
    )
    receipt = build_red_living_dex_exhaustive_inventory_receipt(
        reason=RedLivingDexExhaustiveInventoryReason.EXACT_COVERAGE,
        counts=_mixed_counts(),
        exclusions=_mixed_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=coverage,
    )
    mutated = deepcopy(receipt)
    mutated["exclusions"][field] = 0

    with pytest.raises(RedLivingDexExhaustiveInventoryDiagnosticError):
        validate_red_living_dex_exhaustive_inventory_receipt(mutated)


@pytest.mark.parametrize(
    "reason",
    tuple(
        item
        for item in RedLivingDexExhaustiveInventoryReason
        if item
        not in {
            RedLivingDexExhaustiveInventoryReason.COMPLETE,
            RedLivingDexExhaustiveInventoryReason.EXACT_COVERAGE,
            RedLivingDexExhaustiveInventoryReason.PRIVATE_PLAN_ENCODING,
            RedLivingDexExhaustiveInventoryReason.PROTECTED_INPUT_INTEGRITY,
            RedLivingDexExhaustiveInventoryReason.PRIVATE_PLAN_PUBLICATION,
            RedLivingDexExhaustiveInventoryReason.ZERO_EFFECT_AUTHENTICATION,
        }
    ),
)
def test_every_precoverage_global_reason_is_finite_and_path_free(
    reason: RedLivingDexExhaustiveInventoryReason,
) -> None:
    receipt = build_red_living_dex_exhaustive_inventory_receipt(
        reason=reason,
        counts=RedLivingDexExhaustiveInventoryCounts(),
        exclusions=_zero_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=None,
    )

    validate_red_living_dex_exhaustive_inventory_receipt(receipt)
    assert receipt["failure_reason"] == reason.value


def test_nonzero_effect_requires_the_global_effect_terminal() -> None:
    effects = RedLivingDexInventoryEffects(
        controller_authority_attempts=1,
        controller_actions=2,
        emulator_frames_advanced=3,
    )
    receipt = build_red_living_dex_exhaustive_inventory_receipt(
        reason=RedLivingDexExhaustiveInventoryReason.ZERO_EFFECT_AUTHENTICATION,
        counts=RedLivingDexExhaustiveInventoryCounts(),
        exclusions=_zero_exclusions(),
        effects=effects,
        coverage=None,
    )
    validate_red_living_dex_exhaustive_inventory_receipt(receipt)
    assert receipt["protected_effect_total"] == 6
    assert receipt["effects_verified_zero"] is False

    with pytest.raises(
        RedLivingDexExhaustiveInventoryDiagnosticError,
        match="exact exhaustive failure",
    ):
        build_red_living_dex_exhaustive_inventory_receipt(
            reason=RedLivingDexExhaustiveInventoryReason.UNEXPECTED_FAILURE,
            counts=RedLivingDexExhaustiveInventoryCounts(),
            exclusions=_zero_exclusions(),
            effects=effects,
            coverage=None,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("failure_reason", "state-/Users/private"),
        ("protected_effect_total", 1),
        ("effects_verified_zero", False),
        ("private_path_fields", 1),
    ),
)
def test_receipt_rejects_free_text_false_zero_or_privacy_mutation(
    field: str,
    replacement: object,
) -> None:
    receipt = build_red_living_dex_exhaustive_inventory_receipt(
        reason=RedLivingDexExhaustiveInventoryReason.SOURCE_AUTHENTICATION,
        counts=RedLivingDexExhaustiveInventoryCounts(),
        exclusions=_zero_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=None,
    )
    mutated = deepcopy(receipt)
    mutated[field] = replacement

    with pytest.raises(RedLivingDexExhaustiveInventoryDiagnosticError):
        validate_red_living_dex_exhaustive_inventory_receipt(mutated)


def test_receipt_rejects_private_extra_field_and_boolean_counter() -> None:
    receipt = build_red_living_dex_exhaustive_inventory_receipt(
        reason=RedLivingDexExhaustiveInventoryReason.SOURCE_AUTHENTICATION,
        counts=RedLivingDexExhaustiveInventoryCounts(),
        exclusions=_zero_exclusions(),
        effects=RedLivingDexInventoryEffects(),
        coverage=None,
    )
    receipt["capture_id"] = "private-capture"
    with pytest.raises(
        RedLivingDexExhaustiveInventoryDiagnosticError,
        match="keys",
    ):
        validate_red_living_dex_exhaustive_inventory_receipt(receipt)

    with pytest.raises(RedLivingDexExhaustiveInventoryDiagnosticError):
        RedLivingDexExhaustiveInventoryCounts(authenticated_input_contexts=True)
