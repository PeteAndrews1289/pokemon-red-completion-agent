from __future__ import annotations

import json
from dataclasses import replace

import pytest
from test_red_living_dex_clustered_train_runner import _successor_clustered_fixture

from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
)
from pokemon_red_completion.living_dex_development_supplement import (
    LivingDexDevelopmentSupplementPolicy,
    select_living_dex_development_supplement,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_development_supplement_plan import (
    RedLivingDexDevelopmentSupplementBindings,
    RedLivingDexDevelopmentSupplementFrozenScenario,
    RedLivingDexDevelopmentSupplementPlanError,
    RedLivingDexDevelopmentSupplementPrivatePlan,
)
from pokemon_red_completion.red_living_dex_development_supply import (
    build_red_living_dex_development_supplement_capabilities,
)


def _sha(value: object) -> str:
    return canonical_sha256({"value": value})


def _plan() -> RedLivingDexDevelopmentSupplementPrivatePlan:
    historical, _binding = _successor_clustered_fixture()
    red_capabilities = tuple(
        item.capability
        for item in historical.assignments
        if item.assignment.capability.partition == "development"
    )
    shared = build_red_living_dex_development_supplement_capabilities(
        red_capabilities
    )
    policy = LivingDexDevelopmentSupplementPolicy(
        new_roots=3,
        minimum_surviving_roots=2,
        minimum_new_families=3,
        minimum_new_locations=3,
        held_root_count=2,
        required_total_roots=4,
        held_option_kinds=(
            LivingDexOptionKind.ACQUIRE,
            LivingDexOptionKind.EVOLVE,
            LivingDexOptionKind.DEVELOP,
            LivingDexOptionKind.RESUPPLY,
            LivingDexOptionKind.UNLOCK_ACCESS,
            LivingDexOptionKind.EXPLORE,
        ),
        required_option_kinds=RED_DIRECT_CAUSAL_OPTION_KINDS,
    )
    supplement = select_living_dex_development_supplement(
        shared,
        policy=policy,
    )
    by_scenario = {
        projected.scenario_sha256: capability
        for capability, projected in zip(red_capabilities, shared, strict=True)
    }
    contexts = {
        item.assignment.capability.scenario_sha256: item.context_identity_sha256
        for item in historical.assignments
        if item.assignment.capability.partition == "development"
    }
    frozen = tuple(
        RedLivingDexDevelopmentSupplementFrozenScenario(
            ordinal=ordinal,
            assignment=assignment,
            capability=by_scenario[assignment.scenario_sha256],
            context_identity_sha256=contexts[assignment.scenario_sha256],
        )
        for ordinal, assignment in enumerate(supplement.assignments)
    )
    return RedLivingDexDevelopmentSupplementPrivatePlan(
        bindings=RedLivingDexDevelopmentSupplementBindings(
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
        ),
        supplement=supplement,
        assignments=frozen,
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
