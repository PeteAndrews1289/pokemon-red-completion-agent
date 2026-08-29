"""Lineage-locked short-scenario scheduling for living-Pokedex learning.

Sequential training rows do not need to pretend that every observation is an
independent game.  They do need an honest generalization boundary.  This
module therefore allows bounded repeated scenarios inside one upstream
episode lineage while requiring that every descendant of that lineage stays
in exactly one partition.  Public summaries expose only aggregate coverage;
lineage and physical-root identities remain private provenance and never
become policy features or targets.

The scheduler is action-free.  It does not open a game, choose an arm, observe
an outcome, query a teacher, fit a model, or promote authority.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind
from pokemon_red_completion.provenance import canonical_sha256

LIVING_DEX_CLUSTERED_CURRICULUM_SCHEMA = (
    "pokemon.core.living-dex-clustered-curriculum.v1"
)
LIVING_DEX_CLUSTERED_PRIVATE_SCHEDULE_SCHEMA = (
    "pokemon.core.private-living-dex-clustered-schedule.v1"
)
LIVING_DEX_CLUSTERED_PUBLIC_SCHEDULE_SCHEMA = (
    "pokemon.core.living-dex-clustered-schedule.v1"
)

LivingDexClusterPartition = Literal["train", "development"]

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PARTITIONS = frozenset({"train", "development"})
_KIND_ORDER = {kind: index for index, kind in enumerate(LivingDexOptionKind)}


class LivingDexClusteredCurriculumError(ValueError):
    """A clustered schedule leaked, dominated, or lacked useful coverage."""


@dataclass(frozen=True, slots=True)
class LivingDexClusteredCurriculumPolicy:
    """Small integration gate followed by an explicitly larger fit target."""

    train_scenarios: int = 8
    development_scenarios: int = 4
    minimum_train_lineages: int = 4
    minimum_development_lineages: int = 2
    minimum_train_option_kinds: int = 4
    minimum_development_option_kinds: int = 3
    maximum_scenarios_per_lineage: int = 2
    eventual_minimum_train_outcomes: int = 60

    def __post_init__(self) -> None:
        for value, subject in (
            (self.train_scenarios, "train scenarios"),
            (self.development_scenarios, "development scenarios"),
            (self.minimum_train_lineages, "minimum train lineages"),
            (self.minimum_development_lineages, "minimum development lineages"),
            (self.minimum_train_option_kinds, "minimum train option kinds"),
            (
                self.minimum_development_option_kinds,
                "minimum development option kinds",
            ),
            (
                self.maximum_scenarios_per_lineage,
                "maximum scenarios per lineage",
            ),
            (
                self.eventual_minimum_train_outcomes,
                "eventual minimum train outcomes",
            ),
        ):
            if type(value) is not int or value <= 0:  # noqa: E721
                raise LivingDexClusteredCurriculumError(f"{subject} must be positive")
        if (
            self.minimum_train_lineages > self.train_scenarios
            or self.minimum_development_lineages > self.development_scenarios
            or self.minimum_train_option_kinds > len(LivingDexOptionKind)
            or self.minimum_development_option_kinds > len(LivingDexOptionKind)
            or self.eventual_minimum_train_outcomes < self.train_scenarios
        ):
            raise LivingDexClusteredCurriculumError(
                "clustered curriculum integration bounds are inconsistent"
            )

    @property
    def policy_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "cluster_weighting": "equal_total_weight_per_lineage",
            "development_scenarios": self.development_scenarios,
            "eventual_minimum_train_outcomes": (
                self.eventual_minimum_train_outcomes
            ),
            "maximum_scenarios_per_lineage": (
                self.maximum_scenarios_per_lineage
            ),
            "minimum_development_lineages": self.minimum_development_lineages,
            "minimum_development_option_kinds": (
                self.minimum_development_option_kinds
            ),
            "minimum_train_lineages": self.minimum_train_lineages,
            "minimum_train_option_kinds": self.minimum_train_option_kinds,
            "schema": LIVING_DEX_CLUSTERED_CURRICULUM_SCHEMA,
            "train_scenarios": self.train_scenarios,
        }


@dataclass(frozen=True, slots=True)
class LivingDexClusteredScenarioCapability:
    """One private upstream root can expose one title-neutral menu template."""

    lineage_sha256: str
    physical_root_sha256: str
    partition: LivingDexClusterPartition
    template_sha256: str
    available_option_kinds: tuple[LivingDexOptionKind, ...]

    def __post_init__(self) -> None:
        for value, subject in (
            (self.lineage_sha256, "cluster lineage"),
            (self.physical_root_sha256, "cluster physical root"),
            (self.template_sha256, "cluster template"),
        ):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise LivingDexClusteredCurriculumError(f"{subject} differs")
        if self.partition not in _PARTITIONS:
            raise LivingDexClusteredCurriculumError(
                "cluster capability partition differs"
            )
        if (
            not isinstance(self.available_option_kinds, tuple)
            or len(self.available_option_kinds) < 2
            or len(set(self.available_option_kinds))
            != len(self.available_option_kinds)
            or any(
                not isinstance(kind, LivingDexOptionKind)
                for kind in self.available_option_kinds
            )
            or tuple(sorted(self.available_option_kinds, key=_KIND_ORDER.__getitem__))
            != self.available_option_kinds
        ):
            raise LivingDexClusteredCurriculumError(
                "cluster capability option menu differs"
            )

    @property
    def scenario_sha256(self) -> str:
        return canonical_sha256(
            {
                "lineage_sha256": self.lineage_sha256,
                "partition": self.partition,
                "physical_root_sha256": self.physical_root_sha256,
                "schema": "pokemon.core.private-living-dex-cluster-capability.v1",
                "template_sha256": self.template_sha256,
            }
        )

    def private_dict(self) -> dict[str, object]:
        return {
            "available_option_kinds": [
                kind.value for kind in self.available_option_kinds
            ],
            "lineage_sha256": self.lineage_sha256,
            "partition": self.partition,
            "physical_root_sha256": self.physical_root_sha256,
            "scenario_sha256": self.scenario_sha256,
            "template_sha256": self.template_sha256,
        }


@dataclass(frozen=True, slots=True)
class LivingDexClusteredScenarioAssignment:
    """One action-free scenario assignment with private provenance only."""

    ordinal: int
    capability: LivingDexClusteredScenarioCapability
    within_lineage_ordinal: int

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 0:  # noqa: E721
            raise LivingDexClusteredCurriculumError(
                "cluster assignment ordinal differs"
            )
        if not isinstance(
            self.capability,
            LivingDexClusteredScenarioCapability,
        ):
            raise TypeError("cluster assignment capability differs")
        self.capability.__post_init__()
        if (
            type(self.within_lineage_ordinal) is not int  # noqa: E721
            or self.within_lineage_ordinal < 0
        ):
            raise LivingDexClusteredCurriculumError(
                "cluster within-lineage ordinal differs"
            )

    def private_dict(self) -> dict[str, object]:
        return {
            "capability": self.capability.private_dict(),
            "ordinal": self.ordinal,
            "within_lineage_ordinal": self.within_lineage_ordinal,
        }


@dataclass(frozen=True, slots=True)
class LivingDexClusteredCurriculumSchedule:
    """One identity-bearing private schedule with a path-free public summary."""

    policy: LivingDexClusteredCurriculumPolicy
    assignments: tuple[LivingDexClusteredScenarioAssignment, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy, LivingDexClusteredCurriculumPolicy):
            raise TypeError("clustered schedule policy differs")
        self.policy.__post_init__()
        if not isinstance(self.assignments, tuple) or any(
            not isinstance(item, LivingDexClusteredScenarioAssignment)
            for item in self.assignments
        ):
            raise TypeError("clustered schedule assignments differ")
        for item in self.assignments:
            item.__post_init__()
        expected_count = (
            self.policy.train_scenarios + self.policy.development_scenarios
        )
        if len(self.assignments) != expected_count or tuple(
            item.ordinal for item in self.assignments
        ) != tuple(range(expected_count)):
            raise LivingDexClusteredCurriculumError(
                "clustered schedule is incomplete or reordered"
            )
        scenario_ids = tuple(
            item.capability.scenario_sha256 for item in self.assignments
        )
        if len(set(scenario_ids)) != len(scenario_ids):
            raise LivingDexClusteredCurriculumError(
                "clustered schedule repeats an exact root-template scenario"
            )
        lineage_partitions: dict[str, str] = {}
        physical_owners: dict[str, tuple[str, str]] = {}
        for item in self.assignments:
            capability = item.capability
            prior_partition = lineage_partitions.setdefault(
                capability.lineage_sha256,
                capability.partition,
            )
            if prior_partition != capability.partition:
                raise LivingDexClusteredCurriculumError(
                    "one lineage crosses train and development"
                )
            owner = (
                capability.lineage_sha256,
                capability.partition,
            )
            prior_owner = physical_owners.setdefault(
                capability.physical_root_sha256,
                owner,
            )
            if prior_owner != owner:
                raise LivingDexClusteredCurriculumError(
                    "one physical root crosses lineage or partition"
                )
        for partition, expected, minimum_lineages, minimum_kinds in (
            (
                "train",
                self.policy.train_scenarios,
                self.policy.minimum_train_lineages,
                self.policy.minimum_train_option_kinds,
            ),
            (
                "development",
                self.policy.development_scenarios,
                self.policy.minimum_development_lineages,
                self.policy.minimum_development_option_kinds,
            ),
        ):
            selected = tuple(
                item
                for item in self.assignments
                if item.capability.partition == partition
            )
            if len(selected) != expected:
                raise LivingDexClusteredCurriculumError(
                    f"clustered {partition} count differs"
                )
            counts = Counter(
                item.capability.lineage_sha256 for item in selected
            )
            if (
                len(counts) < minimum_lineages
                or max(counts.values(), default=0)
                > self.policy.maximum_scenarios_per_lineage
            ):
                raise LivingDexClusteredCurriculumError(
                    f"clustered {partition} lineage coverage differs"
                )
            kinds = {
                kind
                for item in selected
                for kind in item.capability.available_option_kinds
            }
            if len(kinds) < minimum_kinds:
                raise LivingDexClusteredCurriculumError(
                    f"clustered {partition} option-kind coverage differs"
                )
            observed_ordinals: dict[str, list[int]] = {}
            for item in selected:
                observed_ordinals.setdefault(
                    item.capability.lineage_sha256,
                    [],
                ).append(item.within_lineage_ordinal)
            if any(
                tuple(values) != tuple(range(len(values)))
                for values in observed_ordinals.values()
            ):
                raise LivingDexClusteredCurriculumError(
                    f"clustered {partition} within-lineage order differs"
                )

    @property
    def schedule_sha256(self) -> str:
        return canonical_sha256(self.private_dict())

    def scenario_weight(
        self,
        assignment: LivingDexClusteredScenarioAssignment,
    ) -> Fraction:
        """Give every upstream lineage equal total fitting weight."""

        if assignment not in self.assignments:
            raise LivingDexClusteredCurriculumError(
                "cluster weight requested for an unassigned scenario"
            )
        count = sum(
            item.capability.lineage_sha256
            == assignment.capability.lineage_sha256
            for item in self.assignments
        )
        return Fraction(1, count)

    def private_dict(self) -> dict[str, object]:
        return {
            "assignments": [item.private_dict() for item in self.assignments],
            "outcomes_observed": 0,
            "policy": self.policy.public_dict(),
            "schema": LIVING_DEX_CLUSTERED_PRIVATE_SCHEDULE_SCHEMA,
            "teacher_queries": 0,
        }

    def public_dict(self) -> dict[str, object]:
        by_partition = {
            partition: tuple(
                item
                for item in self.assignments
                if item.capability.partition == partition
            )
            for partition in ("train", "development")
        }
        counts = Counter(
            item.capability.lineage_sha256 for item in self.assignments
        )
        return {
            "cluster_weighting": "equal_total_weight_per_lineage",
            "controller_actions": 0,
            "development_lineages": len(
                {
                    item.capability.lineage_sha256
                    for item in by_partition["development"]
                }
            ),
            "development_option_kinds": sorted(
                {
                    kind.value
                    for item in by_partition["development"]
                    for kind in item.capability.available_option_kinds
                }
            ),
            "development_scenarios": len(by_partition["development"]),
            "emulator_frames": 0,
            "lineage_overlap": 0,
            "maximum_observed_scenarios_per_lineage": max(counts.values()),
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes_observed": 0,
            "policy_sha256": self.policy.policy_sha256,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "root_claims": 0,
            "schedule_sha256": self.schedule_sha256,
            "schema": LIVING_DEX_CLUSTERED_PUBLIC_SCHEDULE_SCHEMA,
            "teacher_queries": 0,
            "train_lineages": len(
                {
                    item.capability.lineage_sha256
                    for item in by_partition["train"]
                }
            ),
            "train_option_kinds": sorted(
                {
                    kind.value
                    for item in by_partition["train"]
                    for kind in item.capability.available_option_kinds
                }
            ),
            "train_scenarios": len(by_partition["train"]),
            "unselected_action_targets": 0,
        }


def schedule_living_dex_clustered_curriculum(
    capabilities: tuple[LivingDexClusteredScenarioCapability, ...],
    *,
    policy: LivingDexClusteredCurriculumPolicy | None = None,
) -> LivingDexClusteredCurriculumSchedule:
    """Select a deterministic, outcome-blind integration tranche."""

    active_policy = (
        LivingDexClusteredCurriculumPolicy() if policy is None else policy
    )
    if not isinstance(active_policy, LivingDexClusteredCurriculumPolicy):
        raise TypeError("clustered scheduler policy differs")
    active_policy.__post_init__()
    if not isinstance(capabilities, tuple) or any(
        not isinstance(item, LivingDexClusteredScenarioCapability)
        for item in capabilities
    ):
        raise TypeError("clustered scheduler capabilities differ")
    for item in capabilities:
        item.__post_init__()
    keys = tuple(
        (item.physical_root_sha256, item.template_sha256)
        for item in capabilities
    )
    if len(set(keys)) != len(keys):
        raise LivingDexClusteredCurriculumError(
            "clustered scheduler repeats a root-template capability"
        )
    lineage_partitions: dict[str, str] = {}
    physical_owners: dict[str, tuple[str, str]] = {}
    for item in capabilities:
        prior = lineage_partitions.setdefault(item.lineage_sha256, item.partition)
        if prior != item.partition:
            raise LivingDexClusteredCurriculumError(
                "one capability lineage crosses partitions"
            )
        owner = (item.lineage_sha256, item.partition)
        prior_owner = physical_owners.setdefault(item.physical_root_sha256, owner)
        if prior_owner != owner:
            raise LivingDexClusteredCurriculumError(
                "one capability root crosses lineage or partition"
            )

    selected = (
        *_select_partition(
            capabilities,
            partition="train",
            target=active_policy.train_scenarios,
            minimum_lineages=active_policy.minimum_train_lineages,
            minimum_kinds=active_policy.minimum_train_option_kinds,
            maximum_per_lineage=active_policy.maximum_scenarios_per_lineage,
        ),
        *_select_partition(
            capabilities,
            partition="development",
            target=active_policy.development_scenarios,
            minimum_lineages=active_policy.minimum_development_lineages,
            minimum_kinds=active_policy.minimum_development_option_kinds,
            maximum_per_lineage=active_policy.maximum_scenarios_per_lineage,
        ),
    )
    lineage_ordinals: Counter[str] = Counter()
    assignments: list[LivingDexClusteredScenarioAssignment] = []
    for ordinal, capability in enumerate(selected):
        within = lineage_ordinals[capability.lineage_sha256]
        lineage_ordinals[capability.lineage_sha256] += 1
        assignments.append(
            LivingDexClusteredScenarioAssignment(
                ordinal=ordinal,
                capability=capability,
                within_lineage_ordinal=within,
            )
        )
    return LivingDexClusteredCurriculumSchedule(
        policy=active_policy,
        assignments=tuple(assignments),
    )


def _select_partition(
    capabilities: tuple[LivingDexClusteredScenarioCapability, ...],
    *,
    partition: LivingDexClusterPartition,
    target: int,
    minimum_lineages: int,
    minimum_kinds: int,
    maximum_per_lineage: int,
) -> tuple[LivingDexClusteredScenarioCapability, ...]:
    candidates = tuple(
        sorted(
            (item for item in capabilities if item.partition == partition),
            key=lambda item: item.scenario_sha256,
        )
    )
    if (
        len(candidates) < target
        or len({item.lineage_sha256 for item in candidates}) < minimum_lineages
        or len(
            {
                kind
                for item in candidates
                for kind in item.available_option_kinds
            }
        )
        < minimum_kinds
    ):
        raise LivingDexClusteredCurriculumError(
            f"clustered {partition} inventory is insufficient"
        )
    selected: list[LivingDexClusteredScenarioCapability] = []
    lineage_counts: Counter[str] = Counter()
    covered_kinds: set[LivingDexOptionKind] = set()
    while len(selected) < target:
        remaining_after_choice = target - len(selected) - 1
        missing_lineages = max(0, minimum_lineages - len(lineage_counts))
        eligible = tuple(
            item
            for item in candidates
            if item not in selected
            and lineage_counts[item.lineage_sha256] < maximum_per_lineage
            and not (
                remaining_after_choice < missing_lineages
                and item.lineage_sha256 in lineage_counts
            )
        )
        if not eligible:
            raise LivingDexClusteredCurriculumError(
                f"clustered {partition} inventory cannot satisfy its bounds"
            )
        choice = min(
            eligible,
            key=lambda item: (
                -len(set(item.available_option_kinds) - covered_kinds),
                -(item.lineage_sha256 not in lineage_counts),
                lineage_counts[item.lineage_sha256],
                item.scenario_sha256,
            ),
        )
        selected.append(choice)
        lineage_counts[choice.lineage_sha256] += 1
        covered_kinds.update(choice.available_option_kinds)
    if len(lineage_counts) < minimum_lineages or len(covered_kinds) < minimum_kinds:
        raise LivingDexClusteredCurriculumError(
            f"clustered {partition} selection missed its declared coverage"
        )
    return tuple(selected)


__all__ = [
    "LIVING_DEX_CLUSTERED_CURRICULUM_SCHEMA",
    "LIVING_DEX_CLUSTERED_PRIVATE_SCHEDULE_SCHEMA",
    "LIVING_DEX_CLUSTERED_PUBLIC_SCHEDULE_SCHEMA",
    "LivingDexClusterPartition",
    "LivingDexClusteredCurriculumError",
    "LivingDexClusteredCurriculumPolicy",
    "LivingDexClusteredCurriculumSchedule",
    "LivingDexClusteredScenarioAssignment",
    "LivingDexClusteredScenarioCapability",
    "schedule_living_dex_clustered_curriculum",
]
