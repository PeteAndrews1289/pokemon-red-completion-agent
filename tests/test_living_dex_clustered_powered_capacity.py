from __future__ import annotations

from dataclasses import replace

import pytest

from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
)
from pokemon_red_completion.living_dex_clustered_powered_capacity import (
    LivingDexClusteredPoweredCapacityError,
    LivingDexClusteredPoweredLineageAllocation,
    LivingDexClusteredPoweredLineageCapacity,
    LivingDexClusteredPoweredQuestionAllocation,
    LivingDexClusteredPoweredScenarioCapability,
    audit_living_dex_clustered_powered_capacity,
    build_living_dex_clustered_powered_allocation,
)
from pokemon_red_completion.living_dex_clustered_powered_design import (
    LivingDexClusteredPoweredDesign,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256


def _sha(*values: object) -> str:
    return canonical_sha256({"values": list(values)})


def _scenarios() -> tuple[LivingDexClusteredPoweredScenarioCapability, ...]:
    kinds = RED_DIRECT_CAUSAL_OPTION_KINDS
    return tuple(
        LivingDexClusteredPoweredScenarioCapability(
            template_sha256=_sha("template", index),
            location_sha256=_sha("location", index % 7),
            semantic_family_sha256s=tuple(_sha("family", index, offset) for offset in range(3)),
            option_kinds=tuple(kinds[(index + offset) % len(kinds)] for offset in range(3)),
        )
        for index in range(15)
    )


def _lineages(
    train: int = 36,
    development: int = 103,
) -> tuple[LivingDexClusteredPoweredLineageCapacity, ...]:
    scenarios = _scenarios()
    result: list[LivingDexClusteredPoweredLineageCapacity] = []
    for partition, count, pressure_modulus in (
        ("train", train, 3),
        ("development", development, 2),
    ):
        for index in range(count):
            result.append(
                LivingDexClusteredPoweredLineageCapacity(
                    physical_root_sha256=_sha("root", partition, index),
                    independence_lineage_sha256=_sha("lineage", partition, index),
                    partition=partition,  # type: ignore[arg-type]
                    pressure_vector=tuple(
                        ((index + axis) % pressure_modulus) / (pressure_modulus - 1)
                        for axis in range(7)
                    ),
                    scenarios=scenarios,
                    same_reset_policy_forks_feasible=True,
                )
            )
    return tuple(result)


def _expanded_kind_schedule(
    rows: tuple[tuple[LivingDexOptionKind, int], ...],
) -> list[LivingDexOptionKind]:
    return [kind for kind, count in rows for _ in range(count)]


def _expanded_position_schedule(rows: tuple[tuple[int, int], ...]) -> list[int]:
    return [position for position, count in rows for _ in range(count)]


def _template_for_kind(
    scenarios: tuple[LivingDexClusteredPoweredScenarioCapability, ...],
    kind: LivingDexOptionKind,
    offset: int,
) -> str:
    options = [item for item in scenarios if kind in item.option_kinds]
    return options[offset % len(options)].template_sha256


def _allocation(
    lineages: tuple[LivingDexClusteredPoweredLineageCapacity, ...],
) -> tuple[LivingDexClusteredPoweredLineageAllocation, ...]:
    design = LivingDexClusteredPoweredDesign()
    train = [item for item in lineages if item.partition == "train"]
    development = [item for item in lineages if item.partition == "development"]
    train_kinds = _expanded_kind_schedule(design.prospective_selected_kind_counts)
    train_positions = _expanded_position_schedule(design.prospective_candidate_position_counts)
    development_kinds = _expanded_kind_schedule(design.development_focus_kind_counts)
    development_positions = _expanded_position_schedule(design.development_focus_position_counts)
    result: list[LivingDexClusteredPoweredLineageAllocation] = []
    for index, lineage in enumerate(train):
        questions = tuple(
            LivingDexClusteredPoweredQuestionAllocation(
                template_sha256=_template_for_kind(
                    lineage.scenarios,
                    train_kinds[index * 2 + offset],
                    index * 2 + offset,
                ),
                focus_kind=train_kinds[index * 2 + offset],
                candidate_position=train_positions[index * 2 + offset],
            )
            for offset in range(2)
        )
        result.append(
            LivingDexClusteredPoweredLineageAllocation(
                independence_lineage_sha256=lineage.independence_lineage_sha256,
                role="train",
                questions=questions,
            )
        )
    for index, lineage in enumerate(development[:100]):
        kind = development_kinds[index]
        result.append(
            LivingDexClusteredPoweredLineageAllocation(
                independence_lineage_sha256=lineage.independence_lineage_sha256,
                role="development",
                questions=(
                    LivingDexClusteredPoweredQuestionAllocation(
                        template_sha256=_template_for_kind(
                            lineage.scenarios,
                            kind,
                            index,
                        ),
                        focus_kind=kind,
                        candidate_position=development_positions[index],
                    ),
                ),
            )
        )
    result.extend(
        LivingDexClusteredPoweredLineageAllocation(
            independence_lineage_sha256=lineage.independence_lineage_sha256,
            role="contingency",
            questions=(),
        )
        for lineage in development[100:103]
    )
    return tuple(result)


def test_exact_139_lineage_witness_proves_capacity_without_effects() -> None:
    lineages = _lineages()
    audit = audit_living_dex_clustered_powered_capacity(
        lineages,
        allocation=_allocation(lineages),
    )
    public = audit.public_dict()

    assert audit.capacity_proven is True
    assert audit.reasons == ()
    assert audit.train_lineages_available == 36
    assert audit.development_lineages_available == 103
    assert audit.contingency_lineage_upper_bound == 3
    assert audit.allocation_train_lineages == 36
    assert audit.allocation_development_lineages == 100
    assert audit.allocation_contingency_lineages == 3
    assert public["private_identity_fields"] == 0
    assert public["private_path_fields"] == 0
    for field in (
        "behavior_commitments",
        "controller_actions",
        "emulator_frames",
        "model_fits",
        "model_predictions",
        "outcomes",
        "provider_executions",
        "red_gameplay_executions",
        "root_claims",
        "teacher_queries",
    ):
        assert public[field] == 0


def test_constructor_builds_and_reaudits_one_exact_outcome_blind_witness() -> None:
    lineages = _lineages()
    allocation = build_living_dex_clustered_powered_allocation(lineages)

    assert allocation is not None
    audit = audit_living_dex_clustered_powered_capacity(
        lineages,
        allocation=allocation,
    )
    assert audit.capacity_proven is True
    assert audit.reasons == ()
    assert build_living_dex_clustered_powered_allocation(_lineages(development=23)) is None


def test_59_lineage_inventory_fails_at_the_cheapest_decisive_bound() -> None:
    audit = audit_living_dex_clustered_powered_capacity(_lineages(development=23))

    assert audit.capacity_proven is False
    assert audit.train_lineage_deficit == 0
    assert audit.development_lineage_deficit == 77
    assert audit.contingency_lineage_deficit == 3
    assert audit.total_lineage_deficit == 80
    assert "insufficient_development_lineages" in audit.reasons
    assert "insufficient_development_contingency_lineages" in audit.reasons
    assert "insufficient_total_lineages" in audit.reasons
    assert "exact_allocation_witness_absent" not in audit.reasons


def test_raw_139_lineage_pool_cannot_open_collection_without_exact_allocation() -> None:
    audit = audit_living_dex_clustered_powered_capacity(_lineages())

    assert audit.capacity_proven is False
    assert audit.reasons == ("exact_allocation_witness_absent",)
    assert audit.public_dict()["collection_authorized"] is False


def test_witness_rejects_a_cross_partition_lineage() -> None:
    lineages = _lineages()
    allocation = list(_allocation(lineages))
    train_identity = allocation[0].independence_lineage_sha256
    contingency_identity = allocation[-1].independence_lineage_sha256
    allocation[0] = replace(
        allocation[0],
        independence_lineage_sha256=contingency_identity,
    )
    allocation[-1] = replace(
        allocation[-1],
        independence_lineage_sha256=train_identity,
    )

    audit = audit_living_dex_clustered_powered_capacity(
        lineages,
        allocation=tuple(allocation),
    )
    assert audit.capacity_proven is False
    assert "allocation_crosses_immutable_partition" in audit.reasons


def test_duplicate_root_or_lineage_is_rejected_before_aggregate_counting() -> None:
    lineages = _lineages()

    with pytest.raises(LivingDexClusteredPoweredCapacityError, match="physical root"):
        audit_living_dex_clustered_powered_capacity(
            (*lineages, replace(lineages[-1], independence_lineage_sha256=_sha("new")))
        )
    with pytest.raises(LivingDexClusteredPoweredCapacityError, match="independence"):
        audit_living_dex_clustered_powered_capacity(
            (*lineages, replace(lineages[-1], physical_root_sha256=_sha("new")))
        )


def test_mutated_kind_schedule_does_not_survive_the_exact_witness() -> None:
    lineages = _lineages()
    allocation = list(_allocation(lineages))
    first = allocation[0]
    question = first.questions[0]
    replacement_kind = next(
        kind
        for kind in LivingDexOptionKind
        if kind != question.focus_kind
        and kind
        in next(
            scenario
            for scenario in lineages[0].scenarios
            if scenario.template_sha256 == question.template_sha256
        ).option_kinds
    )
    allocation[0] = replace(
        first,
        questions=(replace(question, focus_kind=replacement_kind), first.questions[1]),
    )

    audit = audit_living_dex_clustered_powered_capacity(
        lineages,
        allocation=tuple(allocation),
    )
    assert "allocation_train_kind_schedule_differs" in audit.reasons


def test_same_reset_mutation_removes_development_and_contingency_capacity() -> None:
    lineages = list(_lineages())
    development_index = next(
        index for index, item in enumerate(lineages) if item.partition == "development"
    )
    lineages[development_index] = replace(
        lineages[development_index],
        same_reset_policy_forks_feasible=False,
    )

    audit = audit_living_dex_clustered_powered_capacity(tuple(lineages))
    assert audit.development_same_reset_lineages_available == 102
    assert audit.contingency_lineage_upper_bound == 2
    assert audit.contingency_lineage_deficit == 1
    assert "insufficient_development_contingency_lineages" in audit.reasons


def test_position_or_contingency_mutation_does_not_survive_the_exact_witness() -> None:
    lineages = _lineages()
    allocation = list(_allocation(lineages))
    first = allocation[0]
    first_question = first.questions[0]
    allocation[0] = replace(
        first,
        questions=(
            replace(
                first_question,
                candidate_position=(first_question.candidate_position + 1) % 3,
            ),
            first.questions[1],
        ),
    )

    position_audit = audit_living_dex_clustered_powered_capacity(
        lineages,
        allocation=tuple(allocation),
    )
    assert "allocation_train_position_schedule_differs" in position_audit.reasons

    missing_contingency = audit_living_dex_clustered_powered_capacity(
        lineages,
        allocation=_allocation(lineages)[:-1],
    )
    assert "allocation_role_counts_differ" in missing_contingency.reasons


def test_red_capacity_scenario_rejects_transfer_only_trade_kind() -> None:
    scenario = _scenarios()[0]

    with pytest.raises(LivingDexClusteredPoweredCapacityError, match="option kinds"):
        replace(
            scenario,
            option_kinds=(
                LivingDexOptionKind.TRADE,
                LivingDexOptionKind.ACQUIRE,
                LivingDexOptionKind.EVOLVE,
            ),
        )
