"""Private Red projection into the shared observed-arm living-Dex contract.

The policy boundary in :mod:`living_dex_option_value` deliberately knows no
species, map, item, route, save, or cartridge identity.  This module owns the
Red side of that boundary.  It derives normalized pressures from an independent
collection snapshot and declared scenario budgets, turns prospectively bound
semantic skills into a replayably shuffled variable-size menu, and hard-masks
unsafe or mechanically unavailable work before any behavior policy runs.

Concrete identities and executable callables stay in ``RedBoundLivingDexOption``.
Only ``LivingDexOptionMenu.policy_dict()`` may cross into a learner or dataset.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from pokemon_red_completion.collection import CollectionObservation
from pokemon_red_completion.goal_manager import GoalDecisionOutcome, GoalKind
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalExecutionReport,
    GoalVerification,
)
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_NORMALIZATION,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionContext,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionUnavailableReason,
    living_dex_option_features_from_semantic_facts,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_collection import RED_SOLO_COLLECTION_CONTRACT
from pokemon_red_completion.red_dual_capability_curriculum_runtime import (
    BoundRedDualCapabilityScenario,
    dependency_specimen_ledger,
)
from pokemon_red_completion.red_living_dex_dependency_curriculum import (
    DependencySpecimenLedger,
)

RED_LIVING_DEX_OPTION_ADAPTER_SCHEMA = (
    "pokemon.red.private-living-dex-observed-arm-adapter.v1"
)
RED_LIVING_DEX_NORMALIZATION_PROVENANCE_SCHEMA = (
    "pokemon.red.living-dex-normalization-provenance.v1"
)
RED_LIVING_DEX_PRIVATE_OPTION_BINDING_SCHEMA = (
    "pokemon.red.private-living-dex-option-binding.v1"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DERIVED_BLOCKERS = frozenset(
    {
        LivingDexOptionUnavailableReason.INVARIANT_VIOLATION,
        LivingDexOptionUnavailableReason.MISSING_RESOURCE,
        LivingDexOptionUnavailableReason.STORAGE_BLOCKED,
    }
)


class RedLivingDexOptionAdapterError(ValueError):
    """Red state cannot produce an honest observed-arm option menu."""


class RedLivingDexExecutorOrigin(StrEnum):
    """How a private option obtained its bounded execution contract."""

    SYNTHETIC_TEST = "synthetic_test"
    RED_DUAL_CAPABILITY = "red_dual_capability"
    RED_GOAL_SKILL = "red_goal_skill"


_GOAL_TO_LIVING_DEX_KIND = {
    GoalKind.ADVANCE_STORY: LivingDexOptionKind.UNLOCK_ACCESS,
    GoalKind.ACQUIRE_SPECIES: LivingDexOptionKind.ACQUIRE,
    GoalKind.DEVELOP_TEAM: LivingDexOptionKind.DEVELOP,
    GoalKind.EVOLVE_SPECIES: LivingDexOptionKind.EVOLVE,
    GoalKind.RESUPPLY: LivingDexOptionKind.RESUPPLY,
    GoalKind.MANAGE_STORAGE: LivingDexOptionKind.MANAGE_STORAGE,
    GoalKind.EXPLORE: LivingDexOptionKind.EXPLORE,
}


def _nonnegative_int(value: object, *, subject: str) -> int:
    if type(value) is not int or value < 0:  # noqa: E721
        raise RedLivingDexOptionAdapterError(f"{subject} must be a non-negative integer")
    return value


def _positive_int(value: object, *, subject: str) -> int:
    result = _nonnegative_int(value, subject=subject)
    if result == 0:
        raise RedLivingDexOptionAdapterError(f"{subject} must be positive")
    return result


def _unit_interval(value: object, *, subject: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RedLivingDexOptionAdapterError(f"{subject} must be numeric")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise RedLivingDexOptionAdapterError(f"{subject} must be between zero and one")
    return result


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0 if numerator <= 0 else 1.0
    return min(1.0, max(0.0, float(numerator) / float(denominator)))


def _require_sha256(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedLivingDexOptionAdapterError(f"{subject} SHA-256 is invalid")
    return value


def _require_private_ref(value: object, *, subject: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or any(character in value for character in "\r\n\x00")
    ):
        raise RedLivingDexOptionAdapterError(f"{subject} reference is invalid")
    return value


@dataclass(frozen=True, slots=True)
class RedLivingDexScenarioBudgets:
    """Prospectively frozen denominators for one bounded decision."""

    maximum_controller_actions: int
    maximum_emulator_frames: int

    def __post_init__(self) -> None:
        _positive_int(self.maximum_controller_actions, subject="controller-action budget")
        _positive_int(self.maximum_emulator_frames, subject="emulator-frame budget")


@dataclass(frozen=True, slots=True)
class RedLivingDexContextFacts:
    """Identity-free semantic counts not derivable from collection storage alone."""

    incomplete_dependency_frontier: int
    blocked_immediate_successors: int
    access_blocked_targets: int
    lower_bound_consumable_requirement: int
    party_readiness_requirement: int
    current_party_readiness: int
    unresolved_dependencies: int

    def __post_init__(self) -> None:
        for name in (
            "incomplete_dependency_frontier",
            "blocked_immediate_successors",
            "access_blocked_targets",
            "lower_bound_consumable_requirement",
            "party_readiness_requirement",
            "current_party_readiness",
            "unresolved_dependencies",
        ):
            _nonnegative_int(getattr(self, name), subject=name.replace("_", " "))
        if self.blocked_immediate_successors > self.incomplete_dependency_frontier:
            raise RedLivingDexOptionAdapterError(
                "blocked successors exceed the incomplete dependency frontier"
            )
        if self.unresolved_dependencies > self.incomplete_dependency_frontier:
            raise RedLivingDexOptionAdapterError(
                "unresolved dependencies exceed the incomplete dependency frontier"
            )
        if self.current_party_readiness > self.party_readiness_requirement:
            raise RedLivingDexOptionAdapterError(
                "current party readiness exceeds its declared requirement"
            )


@dataclass(frozen=True, slots=True)
class RedLivingDexOutcomeSnapshot:
    """One independent private state read used before or after a selected action."""

    scenario_identity_sha256: str
    scenario_repeatable: bool
    observation: CollectionObservation
    executable_dependency_count: int
    usable_consumable_units: int
    resource_pool_units: tuple[tuple[str, int], ...]
    party_health_units: int
    party_health_capacity: int
    irreversible_constraints_remaining: int
    controller_actions: int
    emulator_frames: int
    observer_provenance_sha256: str

    def __post_init__(self) -> None:
        _require_sha256(self.scenario_identity_sha256, subject="scenario identity")
        _require_sha256(self.observer_provenance_sha256, subject="observer provenance")
        if type(self.scenario_repeatable) is not bool:  # noqa: E721
            raise RedLivingDexOptionAdapterError("scenario repeatability must be boolean")
        if not isinstance(self.observation, CollectionObservation):
            raise TypeError("living-Dex outcome snapshot needs a collection observation")
        for name in (
            "executable_dependency_count",
            "usable_consumable_units",
            "party_health_units",
            "party_health_capacity",
            "irreversible_constraints_remaining",
            "controller_actions",
            "emulator_frames",
        ):
            _nonnegative_int(getattr(self, name), subject=name.replace("_", " "))
        if (
            not isinstance(self.resource_pool_units, tuple)
            or tuple(sorted(self.resource_pool_units)) != self.resource_pool_units
            or len({resource for resource, _units in self.resource_pool_units})
            != len(self.resource_pool_units)
        ):
            raise RedLivingDexOptionAdapterError("resource pool ordering differs")
        for resource_ref, units in self.resource_pool_units:
            _require_private_ref(resource_ref, subject="resource pool")
            _nonnegative_int(units, subject="resource pool units")
        if sum(units for _resource, units in self.resource_pool_units) != (
            self.usable_consumable_units
        ):
            raise RedLivingDexOptionAdapterError(
                "resource pools do not sum to usable consumable units"
            )
        if self.party_health_capacity <= 0:
            raise RedLivingDexOptionAdapterError("party health capacity must be positive")
        if self.party_health_units > self.party_health_capacity:
            raise RedLivingDexOptionAdapterError(
                "party health exceeds the observed party capacity"
            )

    @property
    def ledger(self) -> DependencySpecimenLedger:
        return dependency_specimen_ledger(self.observation)

    def resource_units_for(self, resource_pool_ref: str | None) -> int:
        if resource_pool_ref is None:
            return 0
        _require_private_ref(resource_pool_ref, subject="resource pool")
        return dict(self.resource_pool_units).get(resource_pool_ref, 0)

    @property
    def retained_living_species_count(self) -> int:
        return len(self.retained_living_species)

    @property
    def retained_living_species(self) -> frozenset[str]:
        """Target specimens still physically represented in the living collection."""

        targets = frozenset(
            RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species
        )
        retained = frozenset(item.species_ref for item in self.observation.specimens)
        return targets & retained

    @property
    def usable_storage_capacity(self) -> int:
        return self.observation.party_limit + (
            len(self.observation.box_counts) * self.observation.box_capacity
        )

    @property
    def usable_storage_headroom(self) -> int:
        used = self.observation.party_size + sum(self.observation.box_counts)
        return self.usable_storage_capacity - used


@dataclass(frozen=True, slots=True)
class RedLivingDexNormalizationProvenance:
    """Every numerator and denominator used in the Red policy projection."""

    living_target_count: int
    retained_living_species_count: int
    missing_living_species_count: int
    incomplete_dependency_frontier: int
    blocked_immediate_successors: int
    access_blocked_targets: int
    lower_bound_consumable_requirement: int
    usable_consumable_units: int
    usable_storage_capacity: int
    usable_storage_headroom: int
    party_readiness_requirement: int
    current_party_readiness: int
    unresolved_dependencies: int
    maximum_controller_actions: int
    maximum_emulator_frames: int

    def __post_init__(self) -> None:
        for name in (
            "living_target_count",
            "retained_living_species_count",
            "missing_living_species_count",
            "incomplete_dependency_frontier",
            "blocked_immediate_successors",
            "access_blocked_targets",
            "lower_bound_consumable_requirement",
            "usable_consumable_units",
            "usable_storage_capacity",
            "usable_storage_headroom",
            "party_readiness_requirement",
            "current_party_readiness",
            "unresolved_dependencies",
            "maximum_controller_actions",
            "maximum_emulator_frames",
        ):
            _nonnegative_int(getattr(self, name), subject=name.replace("_", " "))
        if (
            self.living_target_count <= 0
            or self.usable_storage_capacity <= 0
            or self.maximum_controller_actions <= 0
            or self.maximum_emulator_frames <= 0
        ):
            raise RedLivingDexOptionAdapterError(
                "normalization needs positive target, storage, action, and frame denominators"
            )
        if (
            self.retained_living_species_count + self.missing_living_species_count
            != self.living_target_count
            or self.blocked_immediate_successors
            > self.incomplete_dependency_frontier
            or self.unresolved_dependencies > self.incomplete_dependency_frontier
            or self.access_blocked_targets > self.missing_living_species_count
            or self.usable_storage_headroom > self.usable_storage_capacity
            or self.current_party_readiness > self.party_readiness_requirement
        ):
            raise RedLivingDexOptionAdapterError("normalization provenance counts differ")

    @property
    def provenance_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def context(self) -> LivingDexOptionContext:
        resource_pressure = (
            0.0
            if self.lower_bound_consumable_requirement == 0
            else 1.0
            - _ratio(
                self.usable_consumable_units,
                self.lower_bound_consumable_requirement,
            )
        )
        party_pressure = (
            0.0
            if self.party_readiness_requirement == 0
            else 1.0
            - _ratio(self.current_party_readiness, self.party_readiness_requirement)
        )
        return LivingDexOptionContext(
            collection_pressure=_ratio(
                self.missing_living_species_count,
                self.living_target_count,
            ),
            dependency_pressure=_ratio(
                self.blocked_immediate_successors,
                self.incomplete_dependency_frontier,
            ),
            access_pressure=_ratio(
                self.access_blocked_targets,
                self.missing_living_species_count,
            ),
            resource_pressure=resource_pressure,
            storage_pressure=1.0
            - _ratio(self.usable_storage_headroom, self.usable_storage_capacity),
            party_pressure=party_pressure,
            knowledge_pressure=_ratio(
                self.unresolved_dependencies,
                self.incomplete_dependency_frontier,
            ),
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "access_blocked_targets": self.access_blocked_targets,
            "blocked_immediate_successors": self.blocked_immediate_successors,
            "current_party_readiness": self.current_party_readiness,
            "incomplete_dependency_frontier": self.incomplete_dependency_frontier,
            "living_target_count": self.living_target_count,
            "lower_bound_consumable_requirement": self.lower_bound_consumable_requirement,
            "maximum_controller_actions": self.maximum_controller_actions,
            "maximum_emulator_frames": self.maximum_emulator_frames,
            "missing_living_species_count": self.missing_living_species_count,
            "normalization": LIVING_DEX_OPTION_NORMALIZATION,
            "retained_living_species_count": self.retained_living_species_count,
            "schema": RED_LIVING_DEX_NORMALIZATION_PROVENANCE_SCHEMA,
            "unresolved_dependencies": self.unresolved_dependencies,
            "usable_consumable_units": self.usable_consumable_units,
            "usable_storage_capacity": self.usable_storage_capacity,
            "usable_storage_headroom": self.usable_storage_headroom,
            "party_readiness_requirement": self.party_readiness_requirement,
        }


@dataclass(frozen=True, slots=True)
class RedLivingDexOptionProspect:
    """Pre-action semantic estimates for one private Red capability."""

    kind: LivingDexOptionKind
    completion_units: int
    maximum_completion_units: int
    immediate_dependency_unlocks: int
    travel_action_estimate: int
    execution_action_estimate: int
    required_consumable_units: int
    net_storage_slots: int
    party_risk: float
    irreversible_constraints_exposed: int
    irreversible_constraint_count: int
    prerequisite_confidence: float
    invariant_safe: bool = True
    mechanical_blocker: LivingDexOptionUnavailableReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, LivingDexOptionKind):
            raise RedLivingDexOptionAdapterError("Red option kind differs")
        for name in (
            "completion_units",
            "maximum_completion_units",
            "immediate_dependency_unlocks",
            "travel_action_estimate",
            "execution_action_estimate",
            "required_consumable_units",
            "irreversible_constraints_exposed",
            "irreversible_constraint_count",
        ):
            _nonnegative_int(getattr(self, name), subject=name.replace("_", " "))
        if self.maximum_completion_units <= 0:
            raise RedLivingDexOptionAdapterError(
                "maximum completion units must be positive"
            )
        if self.completion_units > self.maximum_completion_units:
            raise RedLivingDexOptionAdapterError(
                "prospective completion exceeds its declared maximum"
            )
        if type(self.net_storage_slots) is not int:  # noqa: E721
            raise RedLivingDexOptionAdapterError("net storage slots must be an integer")
        object.__setattr__(
            self,
            "party_risk",
            _unit_interval(self.party_risk, subject="party risk"),
        )
        object.__setattr__(
            self,
            "prerequisite_confidence",
            _unit_interval(
                self.prerequisite_confidence,
                subject="prerequisite confidence",
            ),
        )
        if self.irreversible_constraints_exposed > self.irreversible_constraint_count:
            raise RedLivingDexOptionAdapterError(
                "exposed irreversible constraints exceed the declared count"
            )
        if type(self.invariant_safe) is not bool:
            raise RedLivingDexOptionAdapterError("invariant safety must be boolean")
        if self.mechanical_blocker is not None:
            if not isinstance(
                self.mechanical_blocker,
                LivingDexOptionUnavailableReason,
            ):
                raise RedLivingDexOptionAdapterError("mechanical blocker differs")
            if self.mechanical_blocker in _DERIVED_BLOCKERS:
                raise RedLivingDexOptionAdapterError(
                    "invariant, resource, and storage blockers are adapter-derived"
                )


@dataclass(frozen=True, slots=True)
class RedBoundLivingDexOption:
    """One private semantic capability plus its independently checked outcome."""

    binding_ref: str
    family_ref: str
    location_ref: str
    resource_pool_ref: str | None
    prospect: RedLivingDexOptionProspect
    execute: Callable[[], object]
    verify_success: Callable[[DependencySpecimenLedger, DependencySpecimenLedger], bool]
    executor_origin: RedLivingDexExecutorOrigin = field(
        default=RedLivingDexExecutorOrigin.SYNTHETIC_TEST,
        init=False,
    )
    _consumed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        _require_private_ref(self.binding_ref, subject="option binding")
        _require_private_ref(self.family_ref, subject="transformation family")
        _require_private_ref(self.location_ref, subject="option location")
        if self.resource_pool_ref is not None:
            _require_private_ref(self.resource_pool_ref, subject="resource pool")
        if not isinstance(self.prospect, RedLivingDexOptionProspect):
            raise TypeError("bound living-Dex option needs prospective facts")
        if self.prospect.required_consumable_units > 0 and self.resource_pool_ref is None:
            raise RedLivingDexOptionAdapterError(
                "resource-consuming option needs a private resource pool"
            )
        if not callable(self.execute) or not callable(self.verify_success):
            raise TypeError("bound living-Dex option needs executor and verifier callables")
        if not isinstance(self.executor_origin, RedLivingDexExecutorOrigin):
            raise RedLivingDexOptionAdapterError("executor origin differs")

    @property
    def authenticated_executor(self) -> bool:
        return self.executor_origin is not RedLivingDexExecutorOrigin.SYNTHETIC_TEST

    @property
    def binding_sha256(self) -> str:
        return canonical_sha256(
            {
                "binding_ref": self.binding_ref,
                "family_ref": self.family_ref,
                "kind": self.prospect.kind.value,
                "location_ref": self.location_ref,
                "resource_pool_ref": self.resource_pool_ref,
                "executor_origin": self.executor_origin.value,
                "schema": RED_LIVING_DEX_PRIVATE_OPTION_BINDING_SCHEMA,
            }
        )

    @property
    def consumed(self) -> bool:
        """Whether this exact private binding has already received controller authority."""

        return self._consumed

    def execute_once(self) -> object:
        if self._consumed:
            raise RedLivingDexOptionAdapterError("selected Red option was already executed")
        object.__setattr__(self, "_consumed", True)
        return self.execute()


@dataclass(frozen=True, slots=True)
class RedLivingDexAdaptedScenario:
    """Frozen policy menu joined privately to its ordered Red executors."""

    before: RedLivingDexOutcomeSnapshot
    facts: RedLivingDexContextFacts
    budgets: RedLivingDexScenarioBudgets
    provenance: RedLivingDexNormalizationProvenance
    menu: LivingDexOptionMenu
    ordered_options: tuple[RedBoundLivingDexOption, ...]
    ordering_seed_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.before, RedLivingDexOutcomeSnapshot):
            raise TypeError("adapted scenario needs a before snapshot")
        if not isinstance(self.facts, RedLivingDexContextFacts):
            raise TypeError("adapted scenario needs Red context facts")
        if not isinstance(self.budgets, RedLivingDexScenarioBudgets):
            raise TypeError("adapted scenario needs scenario budgets")
        if not isinstance(self.provenance, RedLivingDexNormalizationProvenance):
            raise TypeError("adapted scenario needs normalization provenance")
        if not isinstance(self.menu, LivingDexOptionMenu):
            raise TypeError("adapted scenario needs a policy menu")
        _require_sha256(self.ordering_seed_sha256, subject="menu ordering seed")
        if not self.before.scenario_repeatable:
            raise RedLivingDexOptionAdapterError(
                "Red calibration scenario must be explicitly repeatable"
            )
        if (
            not isinstance(self.ordered_options, tuple)
            or len(self.ordered_options) != len(self.menu.candidates)
            or any(
                not isinstance(option, RedBoundLivingDexOption)
                for option in self.ordered_options
            )
            or tuple(option.binding_ref for option in self.ordered_options)
            != tuple(candidate.binding_ref for candidate in self.menu.candidates)
            or self.menu.context != self.provenance.context()
            or self.provenance
            != build_red_living_dex_normalization_provenance(
                self.before,
                self.facts,
                self.budgets,
            )
            or self.menu.candidates
            != tuple(
                _candidate(
                    option,
                    before=self.before,
                    provenance=self.provenance,
                )
                for option in self.ordered_options
            )
        ):
            raise RedLivingDexOptionAdapterError("adapted Red menu binding differs")
        available = self.menu.available_indices
        if len(available) < 3:
            raise RedLivingDexOptionAdapterError(
                "Red calibration menu needs at least three genuine available options"
            )
        vectors = {self.menu.candidate_vector(index) for index in available}
        if len(vectors) != len(available):
            raise RedLivingDexOptionAdapterError(
                "available Red calibration options are not policy-distinguishable"
            )

    @property
    def normalization_provenance_sha256(self) -> str:
        return canonical_sha256(self.normalization_public_dict())

    def normalization_public_dict(self) -> dict[str, object]:
        return {
            "candidate_rows": [
                _candidate_normalization_row(
                    option,
                    before=self.before,
                    provenance=self.provenance,
                )
                for option in self.ordered_options
            ],
            "context": self.provenance.public_dict(),
            "identity_fields_public": 0,
            "normalization": LIVING_DEX_OPTION_NORMALIZATION,
            "schema": "pokemon.red.living-dex-full-normalization-provenance.v1",
        }

    def public_dict(self) -> dict[str, object]:
        available = self.menu.available_indices
        return {
            "available_candidate_count": len(available),
            "authenticated_available_candidate_count": sum(
                self.ordered_options[index].authenticated_executor
                for index in available
            ),
            "candidate_count": len(self.menu.candidates),
            "distinct_available_option_kinds": len(
                {
                    self.menu.candidates[index].features.kind
                    for index in available
                }
            ),
            "distinct_private_families": len(
                {self.ordered_options[index].family_ref for index in available}
            ),
            "identity_fields_public": 0,
            "menu": self.menu.policy_dict(),
            "menu_ordering": "sha256-seeded-neutral-permutation-v1",
            "normalization_provenance": self.normalization_public_dict(),
            "normalization_provenance_sha256": self.normalization_provenance_sha256,
            "private_binding_values_public": False,
            "repeatable_scenario": True,
            "schema": RED_LIVING_DEX_OPTION_ADAPTER_SCHEMA,
        }


def build_red_living_dex_normalization_provenance(
    before: RedLivingDexOutcomeSnapshot,
    facts: RedLivingDexContextFacts,
    budgets: RedLivingDexScenarioBudgets,
) -> RedLivingDexNormalizationProvenance:
    """Derive every V1 context numerator and denominator from frozen state."""

    if not isinstance(before, RedLivingDexOutcomeSnapshot):
        raise TypeError("before must be a RedLivingDexOutcomeSnapshot")
    if not isinstance(facts, RedLivingDexContextFacts):
        raise TypeError("facts must be RedLivingDexContextFacts")
    if not isinstance(budgets, RedLivingDexScenarioBudgets):
        raise TypeError("budgets must be RedLivingDexScenarioBudgets")
    target_count = len(RED_SOLO_COLLECTION_CONTRACT.resolved_living_target_species)
    retained_count = before.retained_living_species_count
    missing_count = target_count - retained_count
    if facts.access_blocked_targets > missing_count:
        raise RedLivingDexOptionAdapterError(
            "access-blocked targets exceed missing living targets"
        )
    return RedLivingDexNormalizationProvenance(
        living_target_count=target_count,
        retained_living_species_count=retained_count,
        missing_living_species_count=missing_count,
        incomplete_dependency_frontier=facts.incomplete_dependency_frontier,
        blocked_immediate_successors=facts.blocked_immediate_successors,
        access_blocked_targets=facts.access_blocked_targets,
        lower_bound_consumable_requirement=facts.lower_bound_consumable_requirement,
        usable_consumable_units=before.usable_consumable_units,
        usable_storage_capacity=before.usable_storage_capacity,
        usable_storage_headroom=before.usable_storage_headroom,
        party_readiness_requirement=facts.party_readiness_requirement,
        current_party_readiness=facts.current_party_readiness,
        unresolved_dependencies=facts.unresolved_dependencies,
        maximum_controller_actions=budgets.maximum_controller_actions,
        maximum_emulator_frames=budgets.maximum_emulator_frames,
    )


def adapt_red_living_dex_options(
    before: RedLivingDexOutcomeSnapshot,
    facts: RedLivingDexContextFacts,
    budgets: RedLivingDexScenarioBudgets,
    options: Sequence[RedBoundLivingDexOption],
    *,
    ordering_seed_sha256: str,
) -> RedLivingDexAdaptedScenario:
    """Build one complete, replayably neutral Red calibration menu without acting."""

    _require_sha256(ordering_seed_sha256, subject="menu ordering seed")
    if (
        not isinstance(options, Sequence)
        or len(options) < 3
        or any(not isinstance(option, RedBoundLivingDexOption) for option in options)
    ):
        raise RedLivingDexOptionAdapterError(
            "Red calibration adapter needs at least three bound options"
        )
    typed = tuple(options)
    binding_ids = tuple(option.binding_sha256 for option in typed)
    if len(binding_ids) != len(set(binding_ids)):
        raise RedLivingDexOptionAdapterError("Red option bindings are duplicated")
    provenance = build_red_living_dex_normalization_provenance(before, facts, budgets)

    def ordering_key(index: int) -> str:
        return canonical_sha256(
            {
                "candidate_ordinal": index,
                "ordering_seed_sha256": ordering_seed_sha256,
                "schema": "pokemon.core.neutral-menu-permutation.v1",
            }
        )

    ordered = tuple(typed[index] for index in sorted(range(len(typed)), key=ordering_key))
    candidates = tuple(
        _candidate(option, before=before, provenance=provenance)
        for option in ordered
    )
    return RedLivingDexAdaptedScenario(
        before,
        facts,
        budgets,
        provenance,
        LivingDexOptionMenu(provenance.context(), candidates),
        ordered,
        ordering_seed_sha256,
    )


def bind_red_dual_capability_option(
    bound: BoundRedDualCapabilityScenario,
    candidate_index: int,
    before: RedLivingDexOutcomeSnapshot,
    prospect: RedLivingDexOptionProspect,
    *,
    location_ref: str,
    resource_pool_ref: str | None = None,
) -> RedBoundLivingDexOption:
    """Wrap one existing semantic acquire/evolve skill for a multiway menu."""

    if not isinstance(bound, BoundRedDualCapabilityScenario):
        raise TypeError("bound must be a BoundRedDualCapabilityScenario")
    if type(candidate_index) is not int or candidate_index not in {0, 1}:  # noqa: E721
        raise RedLivingDexOptionAdapterError("dual-capability candidate index differs")
    if not isinstance(before, RedLivingDexOutcomeSnapshot):
        raise TypeError("before must be a RedLivingDexOutcomeSnapshot")
    if not isinstance(prospect, RedLivingDexOptionProspect):
        raise TypeError("prospect must be a RedLivingDexOptionProspect")
    expected_kind = (
        LivingDexOptionKind.ACQUIRE
        if candidate_index == 0
        else LivingDexOptionKind.EVOLVE
    )
    selected_kind = (
        GoalKind.ACQUIRE_SPECIES
        if candidate_index == 0
        else GoalKind.EVOLVE_SPECIES
    )
    if prospect.kind is not expected_kind:
        raise RedLivingDexOptionAdapterError(
            "dual-capability skill and portable option kind differ"
        )
    if before.ledger != bound.before_ledger:
        raise RedLivingDexOptionAdapterError(
            "dual-capability skill and adapter snapshot start from different ledgers"
        )
    capability = bound.capabilities[candidate_index]
    if capability.evidence.mechanically_available != (prospect.mechanical_blocker is None):
        raise RedLivingDexOptionAdapterError(
            "dual-capability evidence and mechanical blocker differ"
        )

    def verify_success(
        observed_before: DependencySpecimenLedger,
        observed_after: DependencySpecimenLedger,
    ) -> bool:
        if observed_before != bound.before_ledger:
            return False
        outcome = bound.verify_outcome(
            selected_kind=selected_kind,
            after_ledger=observed_after,
        )
        return outcome.status == "settled" and outcome.reward == 1

    return _authenticate_executor(
        RedBoundLivingDexOption(
            binding_ref=(
                "red.dual-capability."
                f"{bound.species_binding.binding_sha256}.{candidate_index}."
                f"{capability.evidence.skill_binding_sha256}"
            ),
            family_ref=bound.species_binding.binding_sha256,
            location_ref=location_ref,
            resource_pool_ref=resource_pool_ref,
            prospect=prospect,
            execute=capability.execute,
            verify_success=verify_success,
        ),
        RedLivingDexExecutorOrigin.RED_DUAL_CAPABILITY,
    )


def bind_red_goal_option(
    binding: ExecutableGoalBinding,
    prospect: RedLivingDexOptionProspect,
    *,
    family_ref: str,
    location_ref: str,
    resource_pool_ref: str | None = None,
) -> RedBoundLivingDexOption:
    """Adapt one established, independently verified Red goal skill.

    The executor report is retained only for the goal skill's independent
    verifier.  It is never interpreted by the observed-arm collector as an
    outcome label; the collector still obtains costs and collection deltas from
    its own post-action snapshot.
    """

    if not isinstance(binding, ExecutableGoalBinding):
        raise TypeError("binding must be an ExecutableGoalBinding")
    if not isinstance(prospect, RedLivingDexOptionProspect):
        raise TypeError("prospect must be a RedLivingDexOptionProspect")
    expected_kind = _GOAL_TO_LIVING_DEX_KIND.get(binding.kind)
    if expected_kind is None:
        raise RedLivingDexOptionAdapterError(
            "Red goal kind has no living-Dex option mapping"
        )
    if prospect.kind is not expected_kind:
        raise RedLivingDexOptionAdapterError(
            "Red goal skill and living-Dex option kind differ"
        )
    reports: list[GoalExecutionReport] = []

    def execute() -> object:
        if reports:
            raise RedLivingDexOptionAdapterError(
                "Red goal skill report was already recorded"
            )
        report = binding.execute()
        if not isinstance(report, GoalExecutionReport):
            raise RedLivingDexOptionAdapterError(
                "Red goal skill returned invalid execution evidence"
            )
        reports.append(report)
        return report

    def verify_success(
        _observed_before: DependencySpecimenLedger,
        _observed_after: DependencySpecimenLedger,
    ) -> bool:
        if len(reports) != 1:
            return False
        result = binding.verify(reports[0])
        if not isinstance(result, GoalVerification):
            raise RedLivingDexOptionAdapterError(
                "Red goal skill returned invalid verification evidence"
            )
        return result.status is GoalDecisionOutcome.SUCCEEDED

    return _authenticate_executor(
        RedBoundLivingDexOption(
            binding_ref=f"red.goal-skill.{binding.binding_ref}",
            family_ref=family_ref,
            location_ref=location_ref,
            resource_pool_ref=resource_pool_ref,
            prospect=prospect,
            execute=execute,
            verify_success=verify_success,
        ),
        RedLivingDexExecutorOrigin.RED_GOAL_SKILL,
    )


def _authenticate_executor(
    option: RedBoundLivingDexOption,
    origin: RedLivingDexExecutorOrigin,
) -> RedBoundLivingDexOption:
    """Mark only module-owned semantic wrappers as authenticated executors."""

    if origin is RedLivingDexExecutorOrigin.SYNTHETIC_TEST:
        raise RedLivingDexOptionAdapterError(
            "synthetic executor cannot receive semantic authentication"
        )
    object.__setattr__(option, "executor_origin", origin)
    return option


def _candidate(
    option: RedBoundLivingDexOption,
    *,
    before: RedLivingDexOutcomeSnapshot,
    provenance: RedLivingDexNormalizationProvenance,
) -> LivingDexOptionCandidate:
    prospect = option.prospect
    if prospect.completion_units > provenance.missing_living_species_count:
        raise RedLivingDexOptionAdapterError(
            "prospective completion exceeds missing living targets"
        )
    if prospect.immediate_dependency_unlocks > provenance.incomplete_dependency_frontier:
        raise RedLivingDexOptionAdapterError(
            "prospective unlocks exceed the dependency frontier"
        )
    if (
        prospect.irreversible_constraints_exposed
        > before.irreversible_constraints_remaining
    ):
        raise RedLivingDexOptionAdapterError(
            "prospective irreversible exposure exceeds observed constraints"
        )
    availability, reason = _availability(option, before)
    features = living_dex_option_features_from_semantic_facts(
        kind=prospect.kind,
        completion_units=prospect.completion_units,
        maximum_completion_units=prospect.maximum_completion_units,
        immediate_dependency_unlocks=prospect.immediate_dependency_unlocks,
        incomplete_dependency_frontier=provenance.incomplete_dependency_frontier,
        travel_action_estimate=prospect.travel_action_estimate,
        execution_action_estimate=prospect.execution_action_estimate,
        maximum_controller_actions=provenance.maximum_controller_actions,
        required_resource_units=prospect.required_consumable_units,
        available_resource_units=before.resource_units_for(option.resource_pool_ref),
        net_storage_slots=prospect.net_storage_slots,
        storage_headroom=before.usable_storage_headroom,
        party_risk=prospect.party_risk,
        irreversible_constraints_exposed=(
            prospect.irreversible_constraints_exposed
        ),
        irreversible_constraint_count=prospect.irreversible_constraint_count,
        prerequisite_confidence=prospect.prerequisite_confidence,
    )
    return LivingDexOptionCandidate(
        option.binding_ref,
        features,
        availability,
        reason,
    )


def _availability(
    option: RedBoundLivingDexOption,
    before: RedLivingDexOutcomeSnapshot,
) -> tuple[
    LivingDexOptionAvailability,
    LivingDexOptionUnavailableReason | None,
]:
    prospect = option.prospect
    reason: LivingDexOptionUnavailableReason | None
    if not prospect.invariant_safe:
        reason = LivingDexOptionUnavailableReason.INVARIANT_VIOLATION
    elif prospect.mechanical_blocker is not None:
        reason = prospect.mechanical_blocker
    elif prospect.required_consumable_units > before.resource_units_for(
        option.resource_pool_ref
    ):
        reason = LivingDexOptionUnavailableReason.MISSING_RESOURCE
    elif prospect.net_storage_slots > before.usable_storage_headroom:
        reason = LivingDexOptionUnavailableReason.STORAGE_BLOCKED
    else:
        return LivingDexOptionAvailability.AVAILABLE, None
    availability = (
        LivingDexOptionAvailability.UNKNOWN
        if reason is LivingDexOptionUnavailableReason.WORLD_STATE_UNKNOWN
        else LivingDexOptionAvailability.UNAVAILABLE
    )
    return availability, reason


def _candidate_normalization_row(
    option: RedBoundLivingDexOption,
    *,
    before: RedLivingDexOutcomeSnapshot,
    provenance: RedLivingDexNormalizationProvenance,
) -> dict[str, object]:
    prospect = option.prospect
    return {
        "completion_gain": {
            "denominator": prospect.maximum_completion_units,
            "numerator": prospect.completion_units,
        },
        "dependency_unlock_gain": {
            "denominator": provenance.incomplete_dependency_frontier,
            "numerator": prospect.immediate_dependency_unlocks,
        },
        "execution_effort": {
            "denominator": provenance.maximum_controller_actions,
            "numerator": prospect.execution_action_estimate,
        },
        "irreversibility_risk": {
            "denominator": prospect.irreversible_constraint_count,
            "numerator": prospect.irreversible_constraints_exposed,
        },
        "kind": prospect.kind.value,
        "party_risk": {
            "denominator": 1.0,
            "numerator": prospect.party_risk,
        },
        "resource_cost": {
            "denominator": before.resource_units_for(option.resource_pool_ref),
            "numerator": prospect.required_consumable_units,
        },
        "storage_cost": {
            "denominator": before.usable_storage_headroom,
            "numerator": max(0, prospect.net_storage_slots),
        },
        "travel_effort": {
            "denominator": provenance.maximum_controller_actions,
            "numerator": prospect.travel_action_estimate,
        },
        "uncertainty": {
            "denominator": 1.0,
            "numerator": 1.0 - prospect.prerequisite_confidence,
        },
    }


__all__ = [
    "RED_LIVING_DEX_NORMALIZATION_PROVENANCE_SCHEMA",
    "RED_LIVING_DEX_OPTION_ADAPTER_SCHEMA",
    "RED_LIVING_DEX_PRIVATE_OPTION_BINDING_SCHEMA",
    "RedBoundLivingDexOption",
    "RedLivingDexAdaptedScenario",
    "RedLivingDexContextFacts",
    "RedLivingDexExecutorOrigin",
    "RedLivingDexNormalizationProvenance",
    "RedLivingDexOptionAdapterError",
    "RedLivingDexOptionProspect",
    "RedLivingDexOutcomeSnapshot",
    "RedLivingDexScenarioBudgets",
    "adapt_red_living_dex_options",
    "bind_red_dual_capability_option",
    "bind_red_goal_option",
    "build_red_living_dex_normalization_provenance",
]
