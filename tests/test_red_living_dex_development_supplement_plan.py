from __future__ import annotations

import json
from dataclasses import replace
from functools import cache

import pytest
from test_red_living_dex_clustered_train_runner import _successor_clustered_fixture

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_development_supplement_plan import (
    RedLivingDexDevelopmentSupplementBindings,
    RedLivingDexDevelopmentSupplementPlanError,
    RedLivingDexDevelopmentSupplementPrivatePlan,
    audit_red_living_dex_development_supplement_binding_capacity,
    audit_red_living_dex_development_supplement_capacity,
    freeze_red_living_dex_development_supplement_plan,
)
from pokemon_red_completion.red_living_dex_development_supply import (
    RedLivingDexDevelopmentRoot,
    RedLivingDexDevelopmentSupplyInventory,
    RedLivingDexDevelopmentSupplyResult,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


@cache
def _inputs(*, reverse_capabilities: bool = False):  # type: ignore[no-untyped-def]
    historical, _binding = _successor_clustered_fixture()
    red_capabilities = tuple(
        item.capability
        for item in historical.assignments
        if item.assignment.capability.partition == "development"
    )
    if reverse_capabilities:
        red_capabilities = tuple(reversed(red_capabilities))
    contexts = {
        item.capability.root.root.root_consumption_sha256: item.context_identity_sha256
        for item in historical.assignments
        if item.assignment.capability.partition == "development"
    }
    bindings = RedLivingDexDevelopmentSupplementBindings(
        source_commit="a" * 40,
        source_bundle_sha256=_sha("source-bundle"),
        rom_sha256=_sha("rom"),
        goal_registry_sha256=_sha("goal-registry"),
        route_registry_sha256=_sha("route-registry"),
        context_catalog_sha256=_sha("context-catalog"),
        context_plan_sha256=_sha("context-plan"),
        runtime_identity_sha256=_sha("runtime"),
        supply_audit_evidence_sha256=_sha("supply-audit"),
        model_sha256=_sha("model"),
        model_record_sha256=_sha("model-record"),
    )
    roots = tuple(
        RedLivingDexDevelopmentRoot(
            lineage_sha256=_sha(("held-lineage", ordinal)),
            logical_root_sha256=_sha(("held-logical", ordinal)),
            physical_root_sha256=_sha(("held-physical", ordinal)),
            state_sha256=_sha(("held-state", ordinal)),
            envelope_sha256=_sha(("held-envelope", ordinal)),
            option_kinds=frozenset(
                {
                    "acquire",
                    "develop",
                    "evolve",
                    "explore",
                    "resupply",
                    "unlock_access",
                }
            ),
        )
        for ordinal in range(4)
    )
    supply = RedLivingDexDevelopmentSupplyInventory(
        result=RedLivingDexDevelopmentSupplyResult(
            authenticated_train_examples=18,
            model_sha256=bindings.model_sha256,
            model_record_sha256=bindings.model_record_sha256,
            model_settled_examples=18,
            schedules_authenticated=2,
            scheduled_development_assignments=8,
            unique_development_roots=4,
            duplicate_schedule_assignments=4,
            available_development_roots=2,
            unavailable_development_roots=2,
            available_development_lineages=2,
            available_option_kinds=(
                "acquire",
                "develop",
                "evolve",
                "explore",
                "resupply",
                "unlock_access",
            ),
            lineage_overlap_with_train=0,
            state_overlap_with_train=0,
        ),
        train_lineages=frozenset(_sha(("train-lineage", ordinal)) for ordinal in range(18)),
        train_states=frozenset(
            (
                _sha(("train-state", ordinal)),
                _sha(("train-envelope", ordinal)),
            )
            for ordinal in range(18)
        ),
        historical_roots=roots,
        available_roots=roots[:2],
    )
    return red_capabilities, supply, contexts, bindings


@cache
def _plan(*, reverse_capabilities: bool = False) -> RedLivingDexDevelopmentSupplementPrivatePlan:
    red_capabilities, supply, contexts, bindings = _inputs(
        reverse_capabilities=reverse_capabilities
    )
    return freeze_red_living_dex_development_supplement_plan(
        red_capabilities,
        supply=supply,
        context_identities=contexts,
        bindings=bindings,
    )


def test_private_plan_binds_exact_three_development_recipes_without_behavior() -> None:
    plan = _plan()
    document = plan.private_dict()

    assert len(plan.assignments) == 3
    assert [item["ordinal"] for item in document["assignments"]] == [0, 1, 2]
    assert all(item["partition"] == "development" for item in document["assignments"])
    assert document["private_plan_sha256"] == plan.private_plan_sha256
    assert document["supplement_plan_sha256"] == plan.supplement.plan_sha256
    assert document["behavior_commitments"] == 0
    assert document["model_predictions"] == 0
    assert document["training_targets"] == 0


def test_red_capability_input_order_cannot_change_the_frozen_plan() -> None:
    assert _plan(reverse_capabilities=True).private_dict() == _plan().private_dict()


def test_public_projection_is_path_free_and_hides_root_identity() -> None:
    plan = _plan()
    public = plan.public_dict()
    encoded = json.dumps(public, sort_keys=True)

    assert public["new_roots"] == 3
    assert public["coverage_survives_any_allowed_censor"] is True
    assert public["controller_actions"] == 0
    assert public["outcomes_opened"] == 0
    assert public["model_sha256"] == plan.bindings.model_sha256
    assert all(
        frozen.assignment.lineage_sha256 not in encoded
        and frozen.assignment.physical_root_sha256 not in encoded
        and frozen.context_identity_sha256 not in encoded
        for frozen in plan.assignments
    )


def test_plan_rejects_assignment_reorder_and_red_capability_substitution() -> None:
    plan = _plan()
    with pytest.raises(
        RedLivingDexDevelopmentSupplementPlanError,
        match="order",
    ):
        RedLivingDexDevelopmentSupplementPrivatePlan(
            bindings=plan.bindings,
            supplement=plan.supplement,
            assignments=(plan.assignments[1], plan.assignments[0], plan.assignments[2]),
        )

    first = plan.assignments[0]
    with pytest.raises(
        RedLivingDexDevelopmentSupplementPlanError,
        match="does not join",
    ):
        replace(first, capability=plan.assignments[1].capability)


def test_capacity_audit_reports_feasibility_without_private_identity() -> None:
    capabilities, supply, _contexts, _bindings = _inputs()
    result = audit_red_living_dex_development_supplement_capacity(
        capabilities,
        supply=supply,
    )
    public = result.public_dict()
    encoded = json.dumps(public, sort_keys=True)

    assert result.eligible_capabilities == 4
    assert result.eligible_physical_roots == 4
    assert result.feasible_supplements > 0
    assert result.selection_ready is True
    assert public["status"] == "supplement_capacity_ready"
    assert all(
        item.capability.root.root.physical_root_sha256 not in encoded
        for item in _plan().assignments
    )


def test_capacity_audit_distinguishes_insufficient_root_count() -> None:
    capabilities, supply, _contexts, _bindings = _inputs()
    result = audit_red_living_dex_development_supplement_capacity(
        capabilities[:2],
        supply=supply,
    )

    assert result.eligible_physical_roots == 2
    assert result.candidate_root_sets == 0
    assert result.candidate_scenario_combinations == 0
    assert result.feasible_supplements == 0
    assert result.selection_ready is False


def test_binding_capacity_uses_the_same_red_binding_boundary() -> None:
    capabilities, supply, contexts, bindings = _inputs()
    result = audit_red_living_dex_development_supplement_binding_capacity(
        capabilities,
        supply=supply,
        context_identities=contexts,
        bindings=bindings,
    )
    public = result.public_dict()
    encoded = json.dumps(public, sort_keys=True)

    assert result.binding_ready_supplements == result.capacity.feasible_supplements
    assert result.binding_failure_counts == ()
    assert result.binding_ready is True
    assert public["status"] == "supplement_binding_ready"
    assert all(value not in encoded for value in contexts.values())


def test_red_binding_ignores_authenticated_non_development_capabilities() -> None:
    historical, _binding = _successor_clustered_fixture()
    all_capabilities = tuple(item.capability for item in historical.assignments)
    development_capabilities, supply, contexts, bindings = _inputs()

    expected = audit_red_living_dex_development_supplement_binding_capacity(
        development_capabilities,
        supply=supply,
        context_identities=contexts,
        bindings=bindings,
    )
    observed = audit_red_living_dex_development_supplement_binding_capacity(
        all_capabilities,
        supply=supply,
        context_identities=contexts,
        bindings=bindings,
    )
    plan = freeze_red_living_dex_development_supplement_plan(
        all_capabilities,
        supply=supply,
        context_identities=contexts,
        bindings=bindings,
    )

    assert observed == expected
    assert len(plan.assignments) == 3
    assert all(
        item.capability.slot.partition.value == "development"
        for item in plan.assignments
    )


def test_binding_capacity_aggregates_missing_context_rejections() -> None:
    capabilities, supply, _contexts, bindings = _inputs()
    result = audit_red_living_dex_development_supplement_binding_capacity(
        capabilities,
        supply=supply,
        context_identities={},
        bindings=bindings,
    )

    assert result.binding_ready_supplements == 0
    assert result.binding_failure_counts == (
        ("missing_red_context", result.capacity.feasible_supplements),
    )
    assert result.binding_ready is False
