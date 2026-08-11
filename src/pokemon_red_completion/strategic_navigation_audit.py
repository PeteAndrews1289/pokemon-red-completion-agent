"""Pre-featurization audits for collected strategic navigation examples."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from pokemon_red_completion.strategic_navigation import DestinationAvailability
from pokemon_red_completion.strategic_navigation_dataset import (
    CollectedStrategicNavigationDataset,
    StrategicNavigationDataset,
    StrategicNavigationDatasetError,
    StrategicNavigationPartitionAudit,
    audit_strategic_navigation_partitions,
)

StrategicNavigationLineage = (
    StrategicNavigationDataset | CollectedStrategicNavigationDataset
)


@dataclass(frozen=True, slots=True)
class StrategicNavigationCollectionAudit:
    """Coverage and simple baselines computed from identity-free examples only."""

    partition_audit: StrategicNavigationPartitionAudit
    example_count: int
    partition_example_counts: tuple[tuple[str, int], ...]
    outcome_counts: tuple[tuple[str, int], ...]
    candidate_count_counts: tuple[tuple[int, int], ...]
    candidate_availability_counts: tuple[tuple[str, int], ...]
    semantic_need_tag_counts: tuple[tuple[str, int], ...]
    selected_index_counts: tuple[tuple[int, int], ...]
    replan_reason_counts: tuple[tuple[str, int], ...]
    interruption_kind_counts: tuple[tuple[str, int], ...]
    resource_renewal_counts: tuple[tuple[str, int], ...]
    failure_reason_counts: tuple[tuple[str, int], ...]
    available_route_cost_count: int
    available_route_cost_min: int | None
    available_route_cost_max: int | None
    route_cost_unique_minimum_cases: int
    route_cost_unique_minimum_matches: int
    route_cost_ties_excluded: int
    training_shape_selected_indexes: tuple[tuple[str, int, int], ...]
    validation_shape_baseline_cases: int
    validation_shape_baseline_matches: int

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "strategic-navigation-collection-audit-v1",
            "partition_audit": self.partition_audit.public_dict(),
            "example_count": self.example_count,
            "partition_example_counts": dict(self.partition_example_counts),
            "outcomes": dict(self.outcome_counts),
            "candidate_count_counts": {
                str(count): total for count, total in self.candidate_count_counts
            },
            "candidate_availability_counts": dict(
                self.candidate_availability_counts
            ),
            "semantic_need_tag_counts": dict(self.semantic_need_tag_counts),
            "selected_index_counts": {
                str(index): total for index, total in self.selected_index_counts
            },
            "replan_reason_counts": dict(self.replan_reason_counts),
            "interruption_kind_counts": dict(self.interruption_kind_counts),
            "resource_renewal_counts": dict(self.resource_renewal_counts),
            "failure_reason_counts": dict(self.failure_reason_counts),
            "available_route_cost": {
                "count": self.available_route_cost_count,
                "min": self.available_route_cost_min,
                "max": self.available_route_cost_max,
            },
            "route_cost_only_baseline": {
                "unique_minimum_cases": self.route_cost_unique_minimum_cases,
                "matches": self.route_cost_unique_minimum_matches,
                "ties_excluded": self.route_cost_ties_excluded,
            },
            "candidate_shape_baseline": {
                "training_selected_indexes": {
                    f"{need_tags}/{candidate_count}": selected_index
                    for need_tags, candidate_count, selected_index in (
                        self.training_shape_selected_indexes
                    )
                },
                "validation_cases": self.validation_shape_baseline_cases,
                "matches": self.validation_shape_baseline_matches,
            },
            "numeric_feature_schema_frozen": False,
            "model_development_admitted": (
                self.partition_audit.ready_for_model_development
            ),
        }


def audit_strategic_navigation_collection(
    datasets: Iterable[StrategicNavigationLineage],
) -> StrategicNavigationCollectionAudit:
    """Measure coverage and naive baselines before numeric featurization."""

    rows = tuple(datasets)
    partition_audit = audit_strategic_navigation_partitions(rows)
    examples = tuple(example for dataset in rows for example in dataset.examples)
    partition_examples = Counter(example.partition for example in examples)
    outcomes = Counter(example.outcome_status.value for example in examples)
    candidate_counts = Counter(len(example.candidates) for example in examples)
    candidate_availability: Counter[str] = Counter()
    need_tags: Counter[str] = Counter()
    selected_indexes: Counter[int] = Counter()
    replan_reasons: Counter[str] = Counter()
    interruption_kinds: Counter[str] = Counter()
    resource_renewals: Counter[str] = Counter()
    failure_reasons: Counter[str] = Counter()
    available_costs: list[int] = []

    route_cost_cases = 0
    route_cost_matches = 0
    route_cost_ties = 0
    for example in examples:
        candidates = example.candidates
        selected_indexes[example.selected_candidate_index] += 1
        need_tags.update(example.semantic_need_tags)
        replan_reasons.update(reason.value for reason in example.replan_reasons)
        interruption_kinds.update(kind.value for kind in example.interruption_kinds)
        resource_renewals.update(kind.value for kind in example.resource_renewals)
        if example.failure_reason is not None:
            failure_reasons[example.failure_reason.value] += 1
        available: list[tuple[int, int]] = []
        for index, candidate in enumerate(candidates):
            availability = candidate.get("availability")
            if not isinstance(availability, str):
                raise StrategicNavigationDatasetError(
                    "validated strategic candidate lost its availability"
                )
            candidate_availability[availability] += 1
            cost = candidate.get("route_cost")
            if availability == DestinationAvailability.AVAILABLE.value:
                if type(cost) is not int:  # noqa: E721
                    raise StrategicNavigationDatasetError(
                        "available strategic candidate lost its route cost"
                    )
                available.append((index, cost))
                available_costs.append(cost)
        if example.teacher_choice_target is not None:
            minimum = min(cost for _, cost in available)
            minima = tuple(index for index, cost in available if cost == minimum)
            if len(minima) == 1:
                route_cost_cases += 1
                route_cost_matches += example.selected_candidate_index == minima[0]
            else:
                route_cost_ties += 1

    shape_counts: defaultdict[tuple[str, int], Counter[int]] = defaultdict(Counter)
    for example in examples:
        if example.partition == "train" and example.teacher_choice_target is not None:
            shape_counts[
                ("+".join(example.semantic_need_tags), len(example.candidates))
            ][example.selected_candidate_index] += 1
    shape_rules = tuple(
        (
            need_tags,
            candidate_count,
            min(labels, key=lambda index: (-labels[index], index)),
        )
        for (need_tags, candidate_count), labels in sorted(shape_counts.items())
    )
    predictions = {
        (need_tags, candidate_count): selected_index
        for need_tags, candidate_count, selected_index in shape_rules
    }
    validation_cases = 0
    validation_matches = 0
    for example in examples:
        if (
            example.partition != "validation"
            or example.teacher_choice_target is None
        ):
            continue
        candidates = example.candidates
        predicted = predictions.get(
            ("+".join(example.semantic_need_tags), len(candidates)),
            0,
        )
        if (
            predicted >= len(candidates)
            or candidates[predicted].get("availability")
            != DestinationAvailability.AVAILABLE.value
        ):
            continue
        validation_cases += 1
        validation_matches += example.selected_candidate_index == predicted

    return StrategicNavigationCollectionAudit(
        partition_audit=partition_audit,
        example_count=len(examples),
        partition_example_counts=tuple(sorted(partition_examples.items())),
        outcome_counts=tuple(sorted(outcomes.items())),
        candidate_count_counts=tuple(sorted(candidate_counts.items())),
        candidate_availability_counts=tuple(sorted(candidate_availability.items())),
        semantic_need_tag_counts=tuple(sorted(need_tags.items())),
        selected_index_counts=tuple(sorted(selected_indexes.items())),
        replan_reason_counts=tuple(sorted(replan_reasons.items())),
        interruption_kind_counts=tuple(sorted(interruption_kinds.items())),
        resource_renewal_counts=tuple(sorted(resource_renewals.items())),
        failure_reason_counts=tuple(sorted(failure_reasons.items())),
        available_route_cost_count=len(available_costs),
        available_route_cost_min=min(available_costs, default=None),
        available_route_cost_max=max(available_costs, default=None),
        route_cost_unique_minimum_cases=route_cost_cases,
        route_cost_unique_minimum_matches=route_cost_matches,
        route_cost_ties_excluded=route_cost_ties,
        training_shape_selected_indexes=shape_rules,
        validation_shape_baseline_cases=validation_cases,
        validation_shape_baseline_matches=validation_matches,
    )
