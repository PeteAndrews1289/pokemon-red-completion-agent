"""Outcome-blind finite-capacity gate for the clustered powered curriculum.

The powered V2 design needs more than a large collection of save states.  Its
independent unit is an authenticated upstream episode lineage, train and
development ownership is immutable, and the three contingency lineages must
be untouched development replacements.  This module turns those rules into a
small, title-neutral audit which can reject an impossible private inventory
without executing a controller, reading an outcome, or fitting a model.

The audit is intentionally conservative.  It proves only necessary capacity
bounds unless an exact allocation witness is supplied.  Consequently a large
but unallocated inventory cannot accidentally open gameplay.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import cache
from itertools import combinations_with_replacement
from typing import Literal

from pokemon_red_completion.living_dex_causal_curriculum import (
    RED_DIRECT_CAUSAL_OPTION_KINDS,
)
from pokemon_red_completion.living_dex_clustered_powered_design import (
    LivingDexClusteredPoweredDesign,
)
from pokemon_red_completion.living_dex_option_value import LivingDexOptionKind

LIVING_DEX_CLUSTERED_POWERED_CAPACITY_SCHEMA = (
    "pokemon.core.living-dex-clustered-powered-capacity-audit.v1"
)

LivingDexPoweredPartition = Literal["train", "development"]
LivingDexPoweredAllocationRole = Literal["train", "development", "contingency"]

_SHA256_LENGTH = 64
_PRESSURE_AXIS_COUNT = 7


class LivingDexClusteredPoweredCapacityError(ValueError):
    """Capacity input or allocation witness is malformed or contradictory."""


@dataclass(frozen=True, slots=True)
class LivingDexClusteredPoweredScenarioCapability:
    """One authentic lineage can expose one three-option question template."""

    template_sha256: str
    location_sha256: str
    semantic_family_sha256s: tuple[str, ...]
    option_kinds: tuple[LivingDexOptionKind, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.template_sha256, "template")
        _require_sha256(self.location_sha256, "location")
        if (
            not isinstance(self.semantic_family_sha256s, tuple)
            or len(self.semantic_family_sha256s) != 3
            or len(set(self.semantic_family_sha256s)) != 3
        ):
            raise LivingDexClusteredPoweredCapacityError(
                "scenario needs three distinct semantic families"
            )
        for value in self.semantic_family_sha256s:
            _require_sha256(value, "semantic family")
        if (
            not isinstance(self.option_kinds, tuple)
            or len(self.option_kinds) != 3
            or len(set(self.option_kinds)) != 3
            or any(kind not in RED_DIRECT_CAUSAL_OPTION_KINDS for kind in self.option_kinds)
        ):
            raise LivingDexClusteredPoweredCapacityError(
                "scenario needs three distinct option kinds"
            )


@dataclass(frozen=True, slots=True)
class LivingDexClusteredPoweredLineageCapacity:
    """One unused, authenticated, outcome-unread upstream lineage."""

    physical_root_sha256: str
    independence_lineage_sha256: str
    partition: LivingDexPoweredPartition
    pressure_vector: tuple[float, ...]
    scenarios: tuple[LivingDexClusteredPoweredScenarioCapability, ...]
    same_reset_policy_forks_feasible: bool

    def __post_init__(self) -> None:
        _require_sha256(self.physical_root_sha256, "physical root")
        _require_sha256(self.independence_lineage_sha256, "independence lineage")
        if self.partition not in {"train", "development"}:
            raise LivingDexClusteredPoweredCapacityError("capacity partition differs")
        if (
            not isinstance(self.pressure_vector, tuple)
            or len(self.pressure_vector) != _PRESSURE_AXIS_COUNT
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0.0 <= float(value) <= 1.0
                for value in self.pressure_vector
            )
        ):
            raise LivingDexClusteredPoweredCapacityError(
                "capacity lineage needs seven normalized pressure values"
            )
        if not isinstance(self.scenarios, tuple) or any(
            not isinstance(item, LivingDexClusteredPoweredScenarioCapability)
            for item in self.scenarios
        ):
            raise TypeError("capacity scenarios differ")
        for scenario in self.scenarios:
            scenario.__post_init__()
        template_ids = tuple(item.template_sha256 for item in self.scenarios)
        if len(template_ids) != len(set(template_ids)):
            raise LivingDexClusteredPoweredCapacityError(
                "capacity lineage repeats a template capability"
            )
        if type(self.same_reset_policy_forks_feasible) is not bool:  # noqa: E721
            raise TypeError("same-reset fork feasibility must be boolean")


@dataclass(frozen=True, slots=True)
class LivingDexClusteredPoweredQuestionAllocation:
    """One outcome-blind question selected inside an allocation witness."""

    template_sha256: str
    focus_kind: LivingDexOptionKind
    candidate_position: int

    def __post_init__(self) -> None:
        _require_sha256(self.template_sha256, "allocated template")
        if not isinstance(self.focus_kind, LivingDexOptionKind):
            raise TypeError("allocated focus kind differs")
        if type(self.candidate_position) is not int or not 0 <= self.candidate_position < 3:  # noqa: E721
            raise LivingDexClusteredPoweredCapacityError("allocated candidate position differs")


@dataclass(frozen=True, slots=True)
class LivingDexClusteredPoweredLineageAllocation:
    """One lineage's frozen role and zero, one, or two questions."""

    independence_lineage_sha256: str
    role: LivingDexPoweredAllocationRole
    questions: tuple[LivingDexClusteredPoweredQuestionAllocation, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.independence_lineage_sha256, "allocated lineage")
        if self.role not in {"train", "development", "contingency"}:
            raise LivingDexClusteredPoweredCapacityError("allocation role differs")
        if not isinstance(self.questions, tuple) or any(
            not isinstance(item, LivingDexClusteredPoweredQuestionAllocation)
            for item in self.questions
        ):
            raise TypeError("allocated questions differ")
        for question in self.questions:
            question.__post_init__()
        expected = {"train": 2, "development": 1, "contingency": 0}[self.role]
        if len(self.questions) != expected:
            raise LivingDexClusteredPoweredCapacityError(
                "allocation question count differs from its role"
            )
        identities = tuple(
            (item.template_sha256, item.focus_kind, item.candidate_position)
            for item in self.questions
        )
        if len(identities) != len(set(identities)):
            raise LivingDexClusteredPoweredCapacityError(
                "allocation repeats a question inside one lineage"
            )


@dataclass(frozen=True, slots=True)
class LivingDexClusteredPoweredCapacityAudit:
    """Aggregate, path-free proof or falsification of powered V2 capacity."""

    design_sha256: str
    required_new_lineage_supply: int
    lineages_observed: int
    lineages_with_any_scenario: int
    train_lineages_available: int
    development_lineages_available: int
    development_same_reset_lineages_available: int
    train_attempt_upper_bound: int
    development_question_upper_bound: int
    contingency_lineage_upper_bound: int
    train_lineage_deficit: int
    development_lineage_deficit: int
    contingency_lineage_deficit: int
    total_lineage_deficit: int
    train_kind_capacity: tuple[tuple[str, int], ...]
    development_kind_capacity: tuple[tuple[str, int], ...]
    train_template_count: int
    development_template_count: int
    train_location_count: int
    development_location_count: int
    train_semantic_family_count: int
    development_semantic_family_count: int
    train_pressure_value_counts: tuple[int, ...]
    development_pressure_value_counts: tuple[int, ...]
    allocation_witness_supplied: bool
    allocation_witness_valid: bool
    allocation_train_lineages: int
    allocation_development_lineages: int
    allocation_contingency_lineages: int
    reasons: tuple[str, ...]

    @property
    def capacity_proven(self) -> bool:
        return self.allocation_witness_valid and not self.reasons

    def public_dict(self) -> dict[str, object]:
        """Return only aggregate facts and explicit zero-effect counters."""

        return {
            "allocation_contingency_lineages": self.allocation_contingency_lineages,
            "allocation_development_lineages": self.allocation_development_lineages,
            "allocation_train_lineages": self.allocation_train_lineages,
            "allocation_witness_supplied": self.allocation_witness_supplied,
            "allocation_witness_valid": self.allocation_witness_valid,
            "behavior_commitments": 0,
            "capacity_proven": self.capacity_proven,
            "collection_authorized": False,
            "contingency_lineage_deficit": self.contingency_lineage_deficit,
            "contingency_lineage_upper_bound": self.contingency_lineage_upper_bound,
            "controller_actions": 0,
            "design_sha256": self.design_sha256,
            "development_kind_capacity": dict(self.development_kind_capacity),
            "development_lineage_deficit": self.development_lineage_deficit,
            "development_lineages_available": self.development_lineages_available,
            "development_location_count": self.development_location_count,
            "development_pressure_value_counts": list(self.development_pressure_value_counts),
            "development_question_upper_bound": self.development_question_upper_bound,
            "development_same_reset_lineages_available": (
                self.development_same_reset_lineages_available
            ),
            "development_semantic_family_count": (self.development_semantic_family_count),
            "development_template_count": self.development_template_count,
            "emulator_frames": 0,
            "lineages_observed": self.lineages_observed,
            "lineages_with_any_scenario": self.lineages_with_any_scenario,
            "model_fits": 0,
            "model_predictions": 0,
            "outcomes": 0,
            "private_identity_fields": 0,
            "private_path_fields": 0,
            "provider_executions": 0,
            "reasons": list(self.reasons),
            "red_gameplay_executions": 0,
            "required_new_lineage_supply": self.required_new_lineage_supply,
            "root_claims": 0,
            "schema": LIVING_DEX_CLUSTERED_POWERED_CAPACITY_SCHEMA,
            "teacher_queries": 0,
            "total_lineage_deficit": self.total_lineage_deficit,
            "train_attempt_upper_bound": self.train_attempt_upper_bound,
            "train_kind_capacity": dict(self.train_kind_capacity),
            "train_lineage_deficit": self.train_lineage_deficit,
            "train_lineages_available": self.train_lineages_available,
            "train_location_count": self.train_location_count,
            "train_pressure_value_counts": list(self.train_pressure_value_counts),
            "train_semantic_family_count": self.train_semantic_family_count,
            "train_template_count": self.train_template_count,
        }


def audit_living_dex_clustered_powered_capacity(
    lineages: tuple[LivingDexClusteredPoweredLineageCapacity, ...],
    *,
    allocation: tuple[LivingDexClusteredPoweredLineageAllocation, ...] | None = None,
    design: LivingDexClusteredPoweredDesign | None = None,
) -> LivingDexClusteredPoweredCapacityAudit:
    """Audit necessary bounds and, when supplied, an exact allocation witness."""

    active_design = LivingDexClusteredPoweredDesign() if design is None else design
    if not isinstance(active_design, LivingDexClusteredPoweredDesign):
        raise TypeError("powered capacity needs the frozen V2 design")
    active_design.__post_init__()
    if not isinstance(lineages, tuple) or any(
        not isinstance(item, LivingDexClusteredPoweredLineageCapacity) for item in lineages
    ):
        raise TypeError("powered capacity lineages differ")
    for lineage in lineages:
        lineage.__post_init__()
    _require_unique_lineages(lineages)

    usable = tuple(lineage for lineage in lineages if lineage.scenarios)
    train = tuple(lineage for lineage in usable if lineage.partition == "train")
    development = tuple(lineage for lineage in usable if lineage.partition == "development")
    development_same_reset = tuple(
        lineage for lineage in development if lineage.same_reset_policy_forks_feasible
    )
    train_kind_capacity = _kind_capacity(train, attempts_per_lineage=2)
    development_kind_capacity = _kind_capacity(
        development_same_reset,
        attempts_per_lineage=1,
    )
    train_templates, train_locations, train_families = _support_sets(train)
    development_templates, development_locations, development_families = _support_sets(
        development_same_reset
    )
    train_pressures = _pressure_value_counts(train)
    development_pressures = _pressure_value_counts(development_same_reset)

    train_deficit = max(0, active_design.prospective_train_lineages - len(train))
    development_deficit = max(
        0,
        active_design.development_lineages - len(development_same_reset),
    )
    contingency_capacity = max(
        0,
        len(development_same_reset) - active_design.development_lineages,
    )
    contingency_deficit = max(
        0,
        active_design.contingency_lineages - contingency_capacity,
    )
    total_deficit = max(0, active_design.required_new_lineage_supply - len(usable))
    reasons: list[str] = []
    if train_deficit:
        reasons.append("insufficient_train_lineages")
    if development_deficit:
        reasons.append("insufficient_development_lineages")
    if contingency_deficit:
        reasons.append("insufficient_development_contingency_lineages")
    if total_deficit:
        reasons.append("insufficient_total_lineages")
    if len(train) * active_design.maximum_train_attempts_per_lineage < (
        active_design.prospective_train_attempts
    ):
        reasons.append("insufficient_train_attempt_capacity")
    _append_support_reasons(
        reasons,
        active_design,
        train_kind_capacity=train_kind_capacity,
        development_kind_capacity=development_kind_capacity,
        train_templates=train_templates,
        development_templates=development_templates,
        train_locations=train_locations,
        development_locations=development_locations,
        train_families=train_families,
        development_families=development_families,
        train_pressures=train_pressures,
        development_pressures=development_pressures,
    )

    allocation_supplied = allocation is not None
    allocation_valid = False
    allocation_counts: Counter[str] = Counter()
    if allocation is not None:
        allocation_counts, allocation_reasons = _audit_allocation(
            lineages,
            allocation,
            design=active_design,
        )
        reasons.extend(allocation_reasons)
        allocation_valid = not allocation_reasons
    elif not reasons:
        reasons.append("exact_allocation_witness_absent")

    return LivingDexClusteredPoweredCapacityAudit(
        design_sha256=active_design.design_sha256,
        required_new_lineage_supply=active_design.required_new_lineage_supply,
        lineages_observed=len(lineages),
        lineages_with_any_scenario=len(usable),
        train_lineages_available=len(train),
        development_lineages_available=len(development),
        development_same_reset_lineages_available=len(development_same_reset),
        train_attempt_upper_bound=(len(train) * active_design.maximum_train_attempts_per_lineage),
        development_question_upper_bound=len(development_same_reset),
        contingency_lineage_upper_bound=contingency_capacity,
        train_lineage_deficit=train_deficit,
        development_lineage_deficit=development_deficit,
        contingency_lineage_deficit=contingency_deficit,
        total_lineage_deficit=total_deficit,
        train_kind_capacity=_counter_rows(train_kind_capacity),
        development_kind_capacity=_counter_rows(development_kind_capacity),
        train_template_count=len(train_templates),
        development_template_count=len(development_templates),
        train_location_count=len(train_locations),
        development_location_count=len(development_locations),
        train_semantic_family_count=len(train_families),
        development_semantic_family_count=len(development_families),
        train_pressure_value_counts=train_pressures,
        development_pressure_value_counts=development_pressures,
        allocation_witness_supplied=allocation_supplied,
        allocation_witness_valid=allocation_valid,
        allocation_train_lineages=allocation_counts["train"],
        allocation_development_lineages=allocation_counts["development"],
        allocation_contingency_lineages=allocation_counts["contingency"],
        reasons=tuple(sorted(set(reasons))),
    )


def build_living_dex_clustered_powered_allocation(
    lineages: tuple[LivingDexClusteredPoweredLineageCapacity, ...],
    *,
    design: LivingDexClusteredPoweredDesign | None = None,
) -> tuple[LivingDexClusteredPoweredLineageAllocation, ...] | None:
    """Construct one deterministic outcome-blind witness when the pool permits it.

    This is a feasibility constructor, not a behavior draw.  It sees only the
    same action-free capacity metadata audited above.  A returned witness is
    re-audited against every simultaneous floor; ``None`` never means that no
    mathematical allocation exists, only that this bounded constructor did not
    establish one.  Callers must therefore fail closed rather than infer a
    private cause or weaken the design.
    """

    active_design = LivingDexClusteredPoweredDesign() if design is None else design
    if not isinstance(active_design, LivingDexClusteredPoweredDesign):
        raise TypeError("powered allocation needs the frozen V2 design")
    active_design.__post_init__()
    if not isinstance(lineages, tuple) or any(
        not isinstance(item, LivingDexClusteredPoweredLineageCapacity) for item in lineages
    ):
        raise TypeError("powered allocation lineages differ")
    for lineage in lineages:
        lineage.__post_init__()
    _require_unique_lineages(lineages)

    train = tuple(
        sorted(
            (item for item in lineages if item.partition == "train" and item.scenarios),
            key=_allocation_lineage_order,
        )
    )
    development = tuple(
        sorted(
            (
                item
                for item in lineages
                if item.partition == "development"
                and item.scenarios
                and item.same_reset_policy_forks_feasible
            ),
            key=_allocation_lineage_order,
        )
    )
    if (
        len(train) < active_design.prospective_train_lineages
        or len(development)
        < active_design.development_lineages + active_design.contingency_lineages
    ):
        return None

    kind_order = tuple(kind for kind, _ in active_design.prospective_selected_kind_counts)
    train_solution = _solve_train_kind_allocation(
        train,
        kind_order=kind_order,
        target=tuple(
            dict(active_design.prospective_selected_kind_counts)[kind] for kind in kind_order
        ),
        required_lineages=active_design.prospective_train_lineages,
    )
    if train_solution is None:
        return None
    development_kind_order = tuple(kind for kind, _ in active_design.development_focus_kind_counts)
    development_solution = _solve_development_kind_allocation(
        development,
        kind_order=development_kind_order,
        target=tuple(
            dict(active_design.development_focus_kind_counts)[kind]
            for kind in development_kind_order
        ),
        required_lineages=active_design.development_lineages,
    )
    if development_solution is None:
        return None

    selected_development = {index for index, _ in development_solution}
    contingency_indices = tuple(
        index for index in range(len(development)) if index not in selected_development
    )[: active_design.contingency_lineages]
    if len(contingency_indices) != active_design.contingency_lineages:
        return None

    train_positions = _expanded_positions(active_design.prospective_candidate_position_counts)
    development_positions = _expanded_positions(active_design.development_focus_position_counts)
    support_seen: dict[str, tuple[set[str], set[str], set[str]]] = {
        "train": (set(), set(), set()),
        "development": (set(), set(), set()),
    }
    allocation: list[LivingDexClusteredPoweredLineageAllocation] = []
    train_question_ordinal = 0
    for lineage_index, assigned_kinds in train_solution:
        lineage = train[lineage_index]
        questions: list[LivingDexClusteredPoweredQuestionAllocation] = []
        used_identities: set[tuple[str, LivingDexOptionKind, int]] = set()
        for kind in assigned_kinds:
            position = train_positions[train_question_ordinal]
            train_question_ordinal += 1
            scenario = _choose_scenario(
                lineage,
                kind=kind,
                position=position,
                seen=support_seen["train"],
                used_identities=used_identities,
            )
            if scenario is None:
                return None
            used_identities.add((scenario.template_sha256, kind, position))
            _observe_scenario_support(support_seen["train"], scenario)
            questions.append(
                LivingDexClusteredPoweredQuestionAllocation(
                    template_sha256=scenario.template_sha256,
                    focus_kind=kind,
                    candidate_position=position,
                )
            )
        allocation.append(
            LivingDexClusteredPoweredLineageAllocation(
                independence_lineage_sha256=lineage.independence_lineage_sha256,
                role="train",
                questions=tuple(questions),
            )
        )
    for question_ordinal, (lineage_index, kind) in enumerate(development_solution):
        lineage = development[lineage_index]
        position = development_positions[question_ordinal]
        scenario = _choose_scenario(
            lineage,
            kind=kind,
            position=position,
            seen=support_seen["development"],
            used_identities=set(),
        )
        if scenario is None:
            return None
        _observe_scenario_support(support_seen["development"], scenario)
        allocation.append(
            LivingDexClusteredPoweredLineageAllocation(
                independence_lineage_sha256=lineage.independence_lineage_sha256,
                role="development",
                questions=(
                    LivingDexClusteredPoweredQuestionAllocation(
                        template_sha256=scenario.template_sha256,
                        focus_kind=kind,
                        candidate_position=position,
                    ),
                ),
            )
        )
    allocation.extend(
        LivingDexClusteredPoweredLineageAllocation(
            independence_lineage_sha256=development[index].independence_lineage_sha256,
            role="contingency",
            questions=(),
        )
        for index in contingency_indices
    )
    witness = tuple(allocation)
    audit = audit_living_dex_clustered_powered_capacity(
        lineages,
        allocation=witness,
        design=active_design,
    )
    return witness if audit.capacity_proven else None


def _solve_train_kind_allocation(
    lineages: tuple[LivingDexClusteredPoweredLineageCapacity, ...],
    *,
    kind_order: tuple[LivingDexOptionKind, ...],
    target: tuple[int, ...],
    required_lineages: int,
) -> tuple[tuple[int, tuple[LivingDexOptionKind, LivingDexOptionKind]], ...] | None:
    supported = tuple(
        tuple(
            index
            for index, kind in enumerate(kind_order)
            if any(kind in scenario.option_kinds for scenario in lineage.scenarios)
        )
        for lineage in lineages
    )

    @cache
    def solve(
        index: int,
        remaining_lineages: int,
        remaining: tuple[int, ...],
    ) -> tuple[tuple[int, tuple[int, int]], ...] | None:
        if remaining_lineages == 0:
            return () if not any(remaining) else None
        if len(lineages) - index < remaining_lineages or sum(remaining) != 2 * remaining_lineages:
            return None
        if any(
            remaining[kind_index]
            > 2 * sum(kind_index in supported[future] for future in range(index, len(lineages)))
            for kind_index in range(len(kind_order))
        ):
            return None
        options = sorted(
            combinations_with_replacement(supported[index], 2),
            key=lambda pair: (
                pair[0] == pair[1],
                -(remaining[pair[0]] + remaining[pair[1]]),
                pair,
            ),
        )
        for first, second in options:
            if remaining[first] <= 0 or remaining[second] <= (1 if first == second else 0):
                continue
            next_remaining = list(remaining)
            next_remaining[first] -= 1
            next_remaining[second] -= 1
            tail = solve(index + 1, remaining_lineages - 1, tuple(next_remaining))
            if tail is not None:
                return ((index, (first, second)), *tail)
        if len(lineages) - index > remaining_lineages:
            return solve(index + 1, remaining_lineages, remaining)
        return None

    solved = solve(0, required_lineages, target)
    if solved is None:
        return None
    return tuple(
        (index, (kind_order[first], kind_order[second])) for index, (first, second) in solved
    )


def _solve_development_kind_allocation(
    lineages: tuple[LivingDexClusteredPoweredLineageCapacity, ...],
    *,
    kind_order: tuple[LivingDexOptionKind, ...],
    target: tuple[int, ...],
    required_lineages: int,
) -> tuple[tuple[int, LivingDexOptionKind], ...] | None:
    supported = tuple(
        tuple(
            index
            for index, kind in enumerate(kind_order)
            if any(kind in scenario.option_kinds for scenario in lineage.scenarios)
        )
        for lineage in lineages
    )

    @cache
    def solve(
        index: int,
        remaining_lineages: int,
        remaining: tuple[int, ...],
    ) -> tuple[tuple[int, int], ...] | None:
        if remaining_lineages == 0:
            return () if not any(remaining) else None
        if len(lineages) - index < remaining_lineages or sum(remaining) != remaining_lineages:
            return None
        if any(
            remaining[kind_index]
            > sum(kind_index in supported[future] for future in range(index, len(lineages)))
            for kind_index in range(len(kind_order))
        ):
            return None
        for kind_index in sorted(
            supported[index],
            key=lambda item: (-remaining[item], item),
        ):
            if remaining[kind_index] <= 0:
                continue
            next_remaining = list(remaining)
            next_remaining[kind_index] -= 1
            tail = solve(index + 1, remaining_lineages - 1, tuple(next_remaining))
            if tail is not None:
                return ((index, kind_index), *tail)
        if len(lineages) - index > remaining_lineages:
            return solve(index + 1, remaining_lineages, remaining)
        return None

    solved = solve(0, required_lineages, target)
    if solved is None:
        return None
    return tuple((index, kind_order[kind_index]) for index, kind_index in solved)


def _allocation_lineage_order(
    lineage: LivingDexClusteredPoweredLineageCapacity,
) -> tuple[int, tuple[int, ...], str]:
    kinds = {kind for scenario in lineage.scenarios for kind in scenario.option_kinds}
    pressure_signature = tuple(int(round(value * 1_000_000)) for value in lineage.pressure_vector)
    return (-len(kinds), pressure_signature, lineage.independence_lineage_sha256)


def _expanded_positions(rows: tuple[tuple[int, int], ...]) -> tuple[int, ...]:
    return tuple(position for position, count in rows for _ in range(count))


def _choose_scenario(
    lineage: LivingDexClusteredPoweredLineageCapacity,
    *,
    kind: LivingDexOptionKind,
    position: int,
    seen: tuple[set[str], set[str], set[str]],
    used_identities: set[tuple[str, LivingDexOptionKind, int]],
) -> LivingDexClusteredPoweredScenarioCapability | None:
    templates, locations, families = seen
    compatible = tuple(
        scenario
        for scenario in lineage.scenarios
        if kind in scenario.option_kinds
        and (scenario.template_sha256, kind, position) not in used_identities
    )
    if not compatible:
        return None
    return min(
        compatible,
        key=lambda scenario: (
            -(
                int(scenario.template_sha256 not in templates)
                + int(scenario.location_sha256 not in locations)
                + sum(family not in families for family in scenario.semantic_family_sha256s)
            ),
            scenario.template_sha256,
        ),
    )


def _observe_scenario_support(
    seen: tuple[set[str], set[str], set[str]],
    scenario: LivingDexClusteredPoweredScenarioCapability,
) -> None:
    templates, locations, families = seen
    templates.add(scenario.template_sha256)
    locations.add(scenario.location_sha256)
    families.update(scenario.semantic_family_sha256s)


def _append_support_reasons(
    reasons: list[str],
    design: LivingDexClusteredPoweredDesign,
    *,
    train_kind_capacity: Counter[str],
    development_kind_capacity: Counter[str],
    train_templates: set[str],
    development_templates: set[str],
    train_locations: set[str],
    development_locations: set[str],
    train_families: set[str],
    development_families: set[str],
    train_pressures: tuple[int, ...],
    development_pressures: tuple[int, ...],
) -> None:
    if any(
        train_kind_capacity[kind.value] < count
        for kind, count in design.prospective_selected_kind_counts
    ):
        reasons.append("insufficient_train_kind_capacity")
    if any(
        development_kind_capacity[kind.value] < count
        for kind, count in design.development_focus_kind_counts
    ):
        reasons.append("insufficient_development_kind_capacity")
    for observed, minimum, reason in (
        (len(train_templates), design.minimum_train_menu_templates, "insufficient_train_templates"),
        (
            len(development_templates),
            design.minimum_development_menu_templates,
            "insufficient_development_templates",
        ),
        (len(train_locations), design.minimum_train_locations, "insufficient_train_locations"),
        (
            len(development_locations),
            design.minimum_development_locations,
            "insufficient_development_locations",
        ),
        (
            len(train_families),
            design.minimum_train_semantic_families,
            "insufficient_train_semantic_families",
        ),
        (
            len(development_families),
            design.minimum_development_semantic_families,
            "insufficient_development_semantic_families",
        ),
    ):
        if observed < minimum:
            reasons.append(reason)
    if any(count < design.minimum_train_pressure_values_per_axis for count in train_pressures):
        reasons.append("insufficient_train_pressure_variation")
    if any(
        count < design.minimum_development_pressure_values_per_axis
        for count in development_pressures
    ):
        reasons.append("insufficient_development_pressure_variation")


def _audit_allocation(
    lineages: tuple[LivingDexClusteredPoweredLineageCapacity, ...],
    allocation: tuple[LivingDexClusteredPoweredLineageAllocation, ...],
    *,
    design: LivingDexClusteredPoweredDesign,
) -> tuple[Counter[str], list[str]]:
    if not isinstance(allocation, tuple) or any(
        not isinstance(item, LivingDexClusteredPoweredLineageAllocation) for item in allocation
    ):
        raise TypeError("powered capacity allocation differs")
    for item in allocation:
        item.__post_init__()
    allocated_ids = tuple(item.independence_lineage_sha256 for item in allocation)
    if len(allocated_ids) != len(set(allocated_ids)):
        raise LivingDexClusteredPoweredCapacityError("allocation repeats an independence lineage")
    by_id = {item.independence_lineage_sha256: item for item in lineages}
    if any(identity not in by_id for identity in allocated_ids):
        raise LivingDexClusteredPoweredCapacityError(
            "allocation names a lineage outside the census"
        )

    reasons: list[str] = []
    counts: Counter[str] = Counter(item.role for item in allocation)
    expected_counts = {
        "train": design.prospective_train_lineages,
        "development": design.development_lineages,
        "contingency": design.contingency_lineages,
    }
    if counts != Counter(expected_counts):
        reasons.append("allocation_role_counts_differ")
    selected_support: dict[
        str,
        list[
            tuple[
                LivingDexClusteredPoweredLineageCapacity,
                LivingDexClusteredPoweredScenarioCapability,
            ]
        ],
    ] = {
        "train": [],
        "development": [],
    }
    kind_counts: dict[str, Counter[str]] = {
        "train": Counter(),
        "development": Counter(),
    }
    position_counts: dict[str, Counter[int]] = {
        "train": Counter(),
        "development": Counter(),
    }
    for item in allocation:
        lineage = by_id[item.independence_lineage_sha256]
        expected_partition = "train" if item.role == "train" else "development"
        if lineage.partition != expected_partition:
            reasons.append("allocation_crosses_immutable_partition")
        if item.role in {"development", "contingency"} and not (
            lineage.same_reset_policy_forks_feasible
        ):
            reasons.append("allocation_lacks_same_reset_policy_forks")
        scenario_by_template = {
            scenario.template_sha256: scenario for scenario in lineage.scenarios
        }
        for question in item.questions:
            scenario = scenario_by_template.get(question.template_sha256)
            if scenario is None or question.focus_kind not in scenario.option_kinds:
                reasons.append("allocation_question_is_not_supported")
                continue
            selected_support[item.role].append((lineage, scenario))
            kind_counts[item.role][question.focus_kind.value] += 1
            position_counts[item.role][question.candidate_position] += 1

    if kind_counts["train"] != Counter(
        {kind.value: count for kind, count in design.prospective_selected_kind_counts}
    ):
        reasons.append("allocation_train_kind_schedule_differs")
    if position_counts["train"] != Counter(dict(design.prospective_candidate_position_counts)):
        reasons.append("allocation_train_position_schedule_differs")
    if kind_counts["development"] != Counter(
        {kind.value: count for kind, count in design.development_focus_kind_counts}
    ):
        reasons.append("allocation_development_kind_schedule_differs")
    if position_counts["development"] != Counter(dict(design.development_focus_position_counts)):
        reasons.append("allocation_development_position_schedule_differs")

    for role, minimum_templates, minimum_locations, minimum_families, minimum_pressure in (
        (
            "train",
            design.minimum_train_menu_templates,
            design.minimum_train_locations,
            design.minimum_train_semantic_families,
            design.minimum_train_pressure_values_per_axis,
        ),
        (
            "development",
            design.minimum_development_menu_templates,
            design.minimum_development_locations,
            design.minimum_development_semantic_families,
            design.minimum_development_pressure_values_per_axis,
        ),
    ):
        selected = selected_support[role]
        templates = {scenario.template_sha256 for _, scenario in selected}
        locations = {scenario.location_sha256 for _, scenario in selected}
        families = {
            family for _, scenario in selected for family in scenario.semantic_family_sha256s
        }
        selected_lineages = tuple(
            {lineage.independence_lineage_sha256: lineage for lineage, _ in selected}.values()
        )
        pressure_counts = _pressure_value_counts(selected_lineages)
        if len(templates) < minimum_templates:
            reasons.append(f"allocation_{role}_templates_insufficient")
        if len(locations) < minimum_locations:
            reasons.append(f"allocation_{role}_locations_insufficient")
        if len(families) < minimum_families:
            reasons.append(f"allocation_{role}_semantic_families_insufficient")
        if any(count < minimum_pressure for count in pressure_counts):
            reasons.append(f"allocation_{role}_pressure_variation_insufficient")
    return counts, reasons


def _kind_capacity(
    lineages: tuple[LivingDexClusteredPoweredLineageCapacity, ...],
    *,
    attempts_per_lineage: int,
) -> Counter[str]:
    result: Counter[str] = Counter()
    for lineage in lineages:
        supported = {kind.value for scenario in lineage.scenarios for kind in scenario.option_kinds}
        for kind in supported:
            result[kind] += attempts_per_lineage
    return result


def _support_sets(
    lineages: tuple[LivingDexClusteredPoweredLineageCapacity, ...],
) -> tuple[set[str], set[str], set[str]]:
    templates = {scenario.template_sha256 for lineage in lineages for scenario in lineage.scenarios}
    locations = {scenario.location_sha256 for lineage in lineages for scenario in lineage.scenarios}
    families = {
        family
        for lineage in lineages
        for scenario in lineage.scenarios
        for family in scenario.semantic_family_sha256s
    }
    return templates, locations, families


def _pressure_value_counts(
    lineages: tuple[LivingDexClusteredPoweredLineageCapacity, ...],
) -> tuple[int, ...]:
    if not lineages:
        return (0,) * _PRESSURE_AXIS_COUNT
    return tuple(
        len({float(item.pressure_vector[index]) for item in lineages})
        for index in range(_PRESSURE_AXIS_COUNT)
    )


def _counter_rows(counter: Counter[str]) -> tuple[tuple[str, int], ...]:
    return tuple((key, counter[key]) for key in sorted(counter))


def _require_unique_lineages(
    lineages: tuple[LivingDexClusteredPoweredLineageCapacity, ...],
) -> None:
    for values, subject in (
        ((item.physical_root_sha256 for item in lineages), "physical root"),
        (
            (item.independence_lineage_sha256 for item in lineages),
            "independence lineage",
        ),
    ):
        materialized = tuple(values)
        if len(materialized) != len(set(materialized)):
            raise LivingDexClusteredPoweredCapacityError(f"capacity repeats a {subject}")


def _require_sha256(value: object, subject: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise LivingDexClusteredPoweredCapacityError(f"{subject} SHA-256 differs")
    return value


__all__ = [
    "LIVING_DEX_CLUSTERED_POWERED_CAPACITY_SCHEMA",
    "LivingDexClusteredPoweredCapacityAudit",
    "LivingDexClusteredPoweredCapacityError",
    "LivingDexClusteredPoweredLineageAllocation",
    "LivingDexClusteredPoweredLineageCapacity",
    "LivingDexClusteredPoweredQuestionAllocation",
    "LivingDexClusteredPoweredScenarioCapability",
    "audit_living_dex_clustered_powered_capacity",
    "build_living_dex_clustered_powered_allocation",
]
