from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest
from test_red_living_dex_provider_plan import _corridors, _root, _RouteWorld, _sha

from pokemon_red_completion.living_dex_capture_curriculum import (
    LivingDexCapturePartition,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_living_dex_capture_plan import (
    build_red_living_dex_prospective_capture_plan,
)
from pokemon_red_completion.red_living_dex_causal_inventory import (
    RedLivingDexCausalRootCapability,
    schedule_red_living_dex_clustered_integration,
)
from pokemon_red_completion.red_living_dex_clustered_schedule_plan import (
    RedLivingDexClusteredFrozenScenario,
    RedLivingDexClusteredPrivatePlan,
    RedLivingDexClusteredScheduleBindings,
    RedLivingDexClusteredSchedulePlanError,
    validate_red_living_dex_clustered_private_plan,
)
from pokemon_red_completion.red_living_dex_provider_plan import (
    build_red_living_dex_provider_recipe_for_action_free_root,
)


def _bindings() -> RedLivingDexClusteredScheduleBindings:
    return RedLivingDexClusteredScheduleBindings(
        source_commit="a" * 40,
        source_bundle_sha256=_sha("source-bundle"),
        rom_sha256=_sha("rom"),
        goal_registry_sha256=_sha("goal-registry"),
        route_registry_sha256=_sha("route-registry"),
        context_catalog_sha256=_sha("catalog"),
        context_plan_sha256=_sha("context-plan"),
        runtime_identity_sha256=_sha("runtime"),
        census_receipt_sha256=_sha("census"),
    )


@lru_cache(maxsize=1)
def _plan() -> RedLivingDexClusteredPrivatePlan:
    slots = build_red_living_dex_prospective_capture_plan().slots
    roots = tuple(
        replace(
            _root(index),
            cluster_partition="train" if index < 4 else "development",
        )
        for index in range(6)
    )
    capabilities: list[RedLivingDexCausalRootCapability] = []
    for root in roots:
        for ordinal, slot in enumerate(slots):
            partition = (
                "train" if slot.partition is LivingDexCapturePartition.TRAIN else "development"
            )
            if root.cluster_partition != partition:
                continue
            capabilities.append(
                RedLivingDexCausalRootCapability(
                    root=root,
                    template_ordinal=ordinal,
                    slot=slot,
                    recipe=build_red_living_dex_provider_recipe_for_action_free_root(
                        slot,
                        root,
                        world=_RouteWorld(),
                        corridors=_corridors(),
                    ),
                )
            )
    capability_by_key = {
        (item.root.root.physical_root_sha256, item.slot.slot_sha256): item for item in capabilities
    }
    schedule = schedule_red_living_dex_clustered_integration(tuple(capabilities))
    frozen = tuple(
        RedLivingDexClusteredFrozenScenario(
            assignment=assignment,
            capability=capability_by_key[
                (
                    assignment.capability.physical_root_sha256,
                    assignment.capability.template_sha256,
                )
            ],
            context_identity_sha256=_sha(("context", assignment.capability.physical_root_sha256)),
        )
        for assignment in schedule.assignments
    )
    return RedLivingDexClusteredPrivatePlan(
        bindings=_bindings(),
        schedule=schedule,
        assignments=frozen,
    )


def _recommit(document: dict[str, object]) -> None:
    payload = {key: value for key, value in document.items() if key != "private_plan_sha256"}
    document["private_plan_sha256"] = canonical_sha256(payload)


def test_private_plan_round_trips_with_all_effects_closed() -> None:
    plan = _plan()
    document = plan.private_dict()

    reopened = validate_red_living_dex_clustered_private_plan(
        document,
        expected_bindings=_bindings(),
        expected_schedule_sha256=plan.schedule.schedule_sha256,
        expected_policy_sha256=plan.schedule.policy.policy_sha256,
    )

    assert reopened == plan.schedule
    assert document["collection_authorized"] is False
    assert document["development_outcomes_opened"] == 0
    assert document["teacher_queries"] == 0
    assert document["outcomes_observed"] == 0
    assert document["model_fits"] == 0
    assert all(
        row["recipe_sha256"] == canonical_sha256(row["recipe"])
        for row in document["assignments"]  # type: ignore[union-attr]
    )


def test_public_plan_summary_discloses_no_private_identity() -> None:
    plan = _plan()
    encoded = str(plan.public_dict())

    assert plan.public_dict()["train_scenarios"] == 8
    assert plan.public_dict()["development_scenarios"] == 4
    assert plan.public_dict()["private_identity_fields"] == 0
    assert all(item.context_identity_sha256 not in encoded for item in plan.assignments)
    assert all(
        item.assignment.capability.lineage_sha256 not in encoded for item in plan.assignments
    )


def test_validator_rejects_plan_hash_or_expected_binding_drift() -> None:
    plan = _plan()
    document = plan.private_dict()
    document["private_plan_sha256"] = "0" * 64

    with pytest.raises(
        RedLivingDexClusteredSchedulePlanError,
        match="commitment",
    ):
        validate_red_living_dex_clustered_private_plan(document)

    document = plan.private_dict()
    with pytest.raises(
        RedLivingDexClusteredSchedulePlanError,
        match="bindings",
    ):
        validate_red_living_dex_clustered_private_plan(
            document,
            expected_bindings=replace(
                _bindings(),
                context_plan_sha256=_sha("other-plan"),
            ),
        )


def test_validator_rejects_recommitted_schedule_recipe_and_effect_mutations() -> None:
    plan = _plan()

    schedule_hash = deepcopy(plan.private_dict())
    schedule_hash["clustered_schedule_sha256"] = "1" * 64
    _recommit(schedule_hash)
    with pytest.raises(RedLivingDexClusteredSchedulePlanError, match="schedule"):
        validate_red_living_dex_clustered_private_plan(schedule_hash)

    recipe = deepcopy(plan.private_dict())
    rows = recipe["assignments"]
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    recipe_document = rows[0]["recipe"]
    assert isinstance(recipe_document, dict)
    recipe_document["slot_sha256"] = _sha("other-slot")
    rows[0]["recipe_sha256"] = canonical_sha256(recipe_document)
    _recommit(recipe)
    with pytest.raises(RedLivingDexClusteredSchedulePlanError, match="recipe"):
        validate_red_living_dex_clustered_private_plan(recipe)

    effect = deepcopy(plan.private_dict())
    effect["controller_actions"] = 1
    _recommit(effect)
    with pytest.raises(RedLivingDexClusteredSchedulePlanError, match="commitment"):
        validate_red_living_dex_clustered_private_plan(effect)


def test_validator_rejects_reordered_or_arm_bearing_assignments() -> None:
    plan = _plan()

    reordered = deepcopy(plan.private_dict())
    schedule = reordered["clustered_schedule"]
    assert isinstance(schedule, dict)
    assignments = schedule["assignments"]
    assert isinstance(assignments, list)
    assignments[0], assignments[1] = assignments[1], assignments[0]
    reordered["clustered_schedule_sha256"] = canonical_sha256(schedule)
    _recommit(reordered)
    with pytest.raises(RedLivingDexClusteredSchedulePlanError, match="assignments"):
        validate_red_living_dex_clustered_private_plan(reordered)

    arm_bearing = deepcopy(plan.private_dict())
    rows = arm_bearing["assignments"]
    assert isinstance(rows, list) and isinstance(rows[0], dict)
    rows[0]["selected_candidate_index"] = 0
    _recommit(arm_bearing)
    with pytest.raises(RedLivingDexClusteredSchedulePlanError, match="fields"):
        validate_red_living_dex_clustered_private_plan(arm_bearing)


def test_plan_module_contains_no_controller_teacher_claim_or_fit_authority() -> None:
    source = __import__(
        "pokemon_red_completion.red_living_dex_clustered_schedule_plan",
        fromlist=["unused"],
    ).__file__
    assert source is not None
    payload = Path(source).read_text(encoding="utf-8")

    for forbidden in (
        "CountingExecutor",
        "write_root_claim",
        "CompletionFirstGoalTeacher",
        ".press(",
        ".tick(",
        ".execute(",
        "model.fit(",
        "selected_candidate_index",
    ):
        assert forbidden not in payload
