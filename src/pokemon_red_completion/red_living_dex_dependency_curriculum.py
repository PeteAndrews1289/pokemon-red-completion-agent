"""Pure contract for a resettable Red acquire-versus-evolve curriculum.

The contract deliberately stops before emulator or profile integration.  It defines
the title-neutral two-candidate menu, the evidence a later Red binding must provide
to prove that both candidates start from one restored state, and an evolution-aware
living-collection verifier.  Species and skill identities remain private and never
enter the ranker's policy rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.living_dex_dependency_curriculum import (
    ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
    DependencyCandidateFeatures,
    DependencyMultiplicity,
    DependencyMultiset,
    DependencyPredecisionFeatures,
    DependencyStructure,
    dependency_distance,
    dependency_multiset,
    dependency_predecision_features,
    preserves_required_living_species,
    transition_dependency_multiset,
)
from pokemon_red_completion.provenance import canonical_sha256

RED_DUAL_CAPABILITY_CURRICULUM_DESIGN_SCHEMA = (
    "pokemon.red.dual-capability-living-dex-curriculum-design.v1"
)
RED_DUAL_CAPABILITY_SCENARIO_SCHEMA = "pokemon.red.private-dual-capability-living-dex-scenario.v1"
RED_DUAL_CAPABILITY_OUTCOME_SCHEMA = "pokemon.red.private-dual-capability-living-dex-outcome.v1"
RED_DUAL_CAPABILITY_SPECIES_BINDING_SCHEMA = (
    "pokemon.red.private-dual-capability-species-binding.v1"
)
RED_DUAL_CAPABILITY_LEDGER_SCHEMA = "pokemon.red.private-dual-capability-specimen-ledger.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CAPABILITY_ORDER = (GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES)
_SCENARIO_MULTIPLICITIES = (
    DependencyMultiplicity.SCARCE,
    DependencyMultiplicity.DUPLICATE_READY,
)
_STRUCTURE = DependencyStructure(1, 1)


class RedDualCapabilityCurriculumError(ValueError):
    """The prospective curriculum or independently observed outcome differs."""


class RedDependencyCapabilityRole(StrEnum):
    """Species-neutral execution roles a later Red adapter must authenticate."""

    MEASURED_VENUE_CAPTURE = "measured_venue_capture"
    BOUNDED_TRAINING_EVOLUTION = "bounded_training_evolution"


@dataclass(frozen=True, slots=True)
class RedDependencyCapabilityRequirement:
    """One prospective capability, without claiming that a live binding exists."""

    kind: GoalKind
    role: RedDependencyCapabilityRole

    def __post_init__(self) -> None:
        expected = {
            GoalKind.ACQUIRE_SPECIES: RedDependencyCapabilityRole.MEASURED_VENUE_CAPTURE,
            GoalKind.EVOLVE_SPECIES: (RedDependencyCapabilityRole.BOUNDED_TRAINING_EVOLUTION),
        }
        if self.kind not in expected or self.role is not expected[self.kind]:
            raise RedDualCapabilityCurriculumError(
                "dependency capability kind and execution role differ"
            )

    def public_dict(self) -> dict[str, str]:
        return {"goal_kind": self.kind.value, "execution_role": self.role.value}


@dataclass(frozen=True, slots=True)
class RedDualCapabilityCurriculumDesign:
    """The fixed public design; it is not executable qualification evidence."""

    feature_schema: str
    capabilities: tuple[RedDependencyCapabilityRequirement, ...]
    reset_contract: str
    outcome_source: str

    def __post_init__(self) -> None:
        if (
            self.feature_schema != ROOTLESS_DEPENDENCY_FEATURE_SCHEMA
            or tuple(item.kind for item in self.capabilities) != _CAPABILITY_ORDER
            or self.capabilities
            != (
                RedDependencyCapabilityRequirement(
                    GoalKind.ACQUIRE_SPECIES,
                    RedDependencyCapabilityRole.MEASURED_VENUE_CAPTURE,
                ),
                RedDependencyCapabilityRequirement(
                    GoalKind.EVOLVE_SPECIES,
                    RedDependencyCapabilityRole.BOUNDED_TRAINING_EVOLUTION,
                ),
            )
            or self.reset_contract
            != "restore_identical_authenticated_state_before_each_selected_action"
            or self.outcome_source != "independent_post_transition_living_collection_observation"
        ):
            raise RedDualCapabilityCurriculumError("dual-capability design differs")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_DUAL_CAPABILITY_CURRICULUM_DESIGN_SCHEMA,
            "feature_schema": self.feature_schema,
            "candidate_count": 2,
            "candidate_order": [kind.value for kind in _CAPABILITY_ORDER],
            "capabilities": [item.public_dict() for item in self.capabilities],
            "reset_contract": self.reset_contract,
            "outcome_source": self.outcome_source,
            "teacher_choice_fields": 0,
            "title_identity_fields_at_policy_boundary": 0,
            "route_identity_fields_at_policy_boundary": 0,
            "executable_binding_qualified": False,
        }


@dataclass(frozen=True, slots=True)
class RedDualCapabilityScenarioSpec:
    """One identity-free scarce or duplicate-ready design fixture.

    No preferred or assigned action is stored.  A later model must score the full
    menu, and the resulting transition—not this design—supplies the target.
    """

    scenario_id: str
    ordinal: int
    multiplicity: DependencyMultiplicity
    structure: DependencyStructure
    before: DependencyMultiset

    def __post_init__(self) -> None:
        if (
            type(self.ordinal) is not int  # noqa: E721
            or not 0 <= self.ordinal < len(_SCENARIO_MULTIPLICITIES)
            or self.multiplicity is not _SCENARIO_MULTIPLICITIES[self.ordinal]
            or self.scenario_id != f"dual-capability-design-{self.ordinal + 1:02d}"
            or self.structure != _STRUCTURE
            or self.before != dependency_multiset(self.multiplicity, self.structure)
        ):
            raise RedDualCapabilityCurriculumError("scenario design fixture differs")
        _require_policy_rows(self.policy_rows())

    @property
    def predecision_features(self) -> DependencyPredecisionFeatures:
        return dependency_predecision_features(self.before, self.structure)

    def policy_rows(self) -> tuple[dict[str, int | str], ...]:
        state = self.predecision_features
        rows = (
            DependencyCandidateFeatures(state, 1, 0, 0).policy_dict(),
            DependencyCandidateFeatures(state, 0, 1, 1).policy_dict(),
        )
        _require_policy_rows(rows)
        return rows

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_DUAL_CAPABILITY_SCENARIO_SCHEMA,
            "scenario_id": self.scenario_id,
            "ordinal": self.ordinal,
            "multiplicity": self.multiplicity.value,
            "structure": self.structure.public_dict(),
            "predecision_features": self.predecision_features.policy_dict(),
            "candidate_rows": [dict(row) for row in self.policy_rows()],
            "assigned_action": None,
            "teacher_label": None,
            "binding_qualified": False,
        }


@dataclass(frozen=True, slots=True)
class ProspectiveRedCapabilityBinding:
    """Opaque evidence shape a later authenticated builder must populate."""

    kind: GoalKind
    role: RedDependencyCapabilityRole
    reset_state_sha256: str
    skill_binding_sha256: str
    mechanically_available: bool

    def __post_init__(self) -> None:
        RedDependencyCapabilityRequirement(self.kind, self.role)
        _require_sha256(self.reset_state_sha256, "reset state")
        _require_sha256(self.skill_binding_sha256, "skill binding")
        if not isinstance(self.mechanically_available, bool):
            raise TypeError("mechanically_available must be boolean")


@dataclass(frozen=True, slots=True)
class ProspectiveRedDualCapabilityScenario:
    """A future private join proving two offers came from one restored state."""

    spec: RedDualCapabilityScenarioSpec
    dependency_binding_sha256: str
    capabilities: tuple[ProspectiveRedCapabilityBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.spec, RedDualCapabilityScenarioSpec):
            raise TypeError("spec must be a RedDualCapabilityScenarioSpec")
        _require_sha256(self.dependency_binding_sha256, "dependency binding")
        if (
            tuple(item.kind for item in self.capabilities) != _CAPABILITY_ORDER
            or len({item.skill_binding_sha256 for item in self.capabilities}) != 2
            or len({item.reset_state_sha256 for item in self.capabilities}) != 1
            or not all(item.mechanically_available for item in self.capabilities)
        ):
            raise RedDualCapabilityCurriculumError(
                "both independent capabilities must be available from one reset state"
            )

    def policy_rows(self) -> tuple[dict[str, int | str], ...]:
        return self.spec.policy_rows()

    def private_dict(self) -> dict[str, object]:
        return {
            "schema": RED_DUAL_CAPABILITY_SCENARIO_SCHEMA,
            "scenario_id": self.spec.scenario_id,
            "dependency_binding_sha256": self.dependency_binding_sha256,
            "reset_state_sha256": self.capabilities[0].reset_state_sha256,
            "capabilities": [
                {
                    "goal_kind": item.kind.value,
                    "execution_role": item.role.value,
                    "skill_binding_sha256": item.skill_binding_sha256,
                    "mechanically_available": item.mechanically_available,
                }
                for item in self.capabilities
            ],
            "candidate_rows": [dict(row) for row in self.policy_rows()],
            "model_predictions": 0,
        }

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_DUAL_CAPABILITY_SCENARIO_SCHEMA,
            "scenario_id": self.spec.scenario_id,
            "candidate_count": 2,
            "candidate_order": [kind.value for kind in _CAPABILITY_ORDER],
            "same_reset_state": True,
            "independently_available_capabilities": 2,
            "identity_fields_at_policy_boundary": 0,
            "binding_qualified": True,
            "model_predictions": 0,
        }


@dataclass(frozen=True, slots=True)
class RedDependencySpeciesBinding:
    """Private species identity used only by the independent verifier."""

    precursor_species_ref: str
    evolved_species_ref: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.precursor_species_ref, str)
            or not self.precursor_species_ref
            or len(self.precursor_species_ref) > 256
            or not isinstance(self.evolved_species_ref, str)
            or not self.evolved_species_ref
            or len(self.evolved_species_ref) > 256
            or self.precursor_species_ref == self.evolved_species_ref
            or any(
                character in "\r\n\x00"
                for value in (self.precursor_species_ref, self.evolved_species_ref)
                for character in value
            )
        ):
            raise RedDualCapabilityCurriculumError("private species binding differs")

    @property
    def binding_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": RED_DUAL_CAPABILITY_SPECIES_BINDING_SCHEMA,
                "precursor_species_ref": self.precursor_species_ref,
                "evolved_species_ref": self.evolved_species_ref,
            }
        )


@dataclass(frozen=True, slots=True)
class DependencySpecimenLedger:
    """A canonical private living-specimen multiset."""

    specimen_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.specimen_counts, tuple)
            or tuple(sorted(self.specimen_counts)) != self.specimen_counts
            or len({species for species, _count in self.specimen_counts})
            != len(self.specimen_counts)
        ):
            raise RedDualCapabilityCurriculumError("specimen ledger ordering differs")
        for species, count in self.specimen_counts:
            if (
                not isinstance(species, str)
                or not species
                or len(species) > 256
                or type(count) is not int  # noqa: E721
                or count <= 0
            ):
                raise RedDualCapabilityCurriculumError("specimen ledger value differs")

    def count(self, species_ref: str) -> int:
        return dict(self.specimen_counts).get(species_ref, 0)

    @property
    def ledger_sha256(self) -> str:
        return canonical_sha256(
            {
                "schema": RED_DUAL_CAPABILITY_LEDGER_SCHEMA,
                "specimen_counts": dict(self.specimen_counts),
            }
        )


@dataclass(frozen=True, slots=True)
class RedDualCapabilityOutcome:
    """One selected action joined to an independent collection observation."""

    scenario: RedDualCapabilityScenarioSpec
    binding: RedDependencySpeciesBinding
    selected_kind: GoalKind
    status: Literal["settled", "interrupted"]
    before_ledger: DependencySpecimenLedger
    after_ledger: DependencySpecimenLedger | None
    dependency_distance_before: int
    dependency_distance_after: int | None
    exact_selected_transition: bool | None
    required_living_preserved: bool | None
    unrelated_species_preserved: bool | None
    reward: int | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scenario, RedDualCapabilityScenarioSpec)
            or not isinstance(self.binding, RedDependencySpeciesBinding)
            or self.selected_kind not in _CAPABILITY_ORDER
            or not isinstance(self.before_ledger, DependencySpecimenLedger)
        ):
            raise RedDualCapabilityCurriculumError("dependency outcome identity differs")
        before = _dependency_multiset(self.before_ledger, self.binding)
        if before != self.scenario.before or self.dependency_distance_before != dependency_distance(
            before, self.scenario.structure
        ):
            raise RedDualCapabilityCurriculumError("dependency outcome start differs")
        if self.status == "interrupted":
            if any(
                value is not None
                for value in (
                    self.after_ledger,
                    self.dependency_distance_after,
                    self.exact_selected_transition,
                    self.required_living_preserved,
                    self.unrelated_species_preserved,
                    self.reward,
                )
            ):
                raise RedDualCapabilityCurriculumError("interrupted outcome must remain censored")
            return
        if (
            self.status != "settled"
            or not isinstance(self.after_ledger, DependencySpecimenLedger)
            or self.reward not in {-1, 1}
        ):
            raise RedDualCapabilityCurriculumError("settled dependency outcome differs")
        expected = _settled_outcome_facts(
            self.scenario,
            self.binding,
            self.selected_kind,
            self.before_ledger,
            self.after_ledger,
        )
        actual = (
            self.dependency_distance_after,
            self.exact_selected_transition,
            self.required_living_preserved,
            self.unrelated_species_preserved,
            self.reward,
        )
        if actual != expected:
            raise RedDualCapabilityCurriculumError(
                "settled dependency outcome is not independently derived"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": RED_DUAL_CAPABILITY_OUTCOME_SCHEMA,
            "scenario_id": self.scenario.scenario_id,
            "selected_kind": self.selected_kind.value,
            "status": self.status,
            "dependency_distance_before": self.dependency_distance_before,
            "dependency_distance_after": self.dependency_distance_after,
            "exact_selected_transition": self.exact_selected_transition,
            "required_living_preserved": self.required_living_preserved,
            "unrelated_species_preserved": self.unrelated_species_preserved,
            "reward": self.reward,
            "species_identity_fields": 0,
            "teacher_label_fields": 0,
        }

    def private_dict(self) -> dict[str, object]:
        return {
            **self.public_dict(),
            "binding_sha256": self.binding.binding_sha256,
            "before_ledger_sha256": self.before_ledger.ledger_sha256,
            "after_ledger_sha256": (
                None if self.after_ledger is None else self.after_ledger.ledger_sha256
            ),
        }


def red_dual_capability_curriculum_design() -> RedDualCapabilityCurriculumDesign:
    """Return the one canonical public design."""

    return RedDualCapabilityCurriculumDesign(
        ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
        (
            RedDependencyCapabilityRequirement(
                GoalKind.ACQUIRE_SPECIES,
                RedDependencyCapabilityRole.MEASURED_VENUE_CAPTURE,
            ),
            RedDependencyCapabilityRequirement(
                GoalKind.EVOLVE_SPECIES,
                RedDependencyCapabilityRole.BOUNDED_TRAINING_EVOLUTION,
            ),
        ),
        "restore_identical_authenticated_state_before_each_selected_action",
        "independent_post_transition_living_collection_observation",
    )


def red_dual_capability_scenario_specs() -> tuple[RedDualCapabilityScenarioSpec, ...]:
    """Return scarce and duplicate-ready fixtures with no assigned action."""

    return tuple(
        RedDualCapabilityScenarioSpec(
            scenario_id=f"dual-capability-design-{ordinal + 1:02d}",
            ordinal=ordinal,
            multiplicity=multiplicity,
            structure=_STRUCTURE,
            before=dependency_multiset(multiplicity, _STRUCTURE),
        )
        for ordinal, multiplicity in enumerate(_SCENARIO_MULTIPLICITIES)
    )


def verify_red_dual_capability_outcome(
    scenario: RedDualCapabilityScenarioSpec,
    binding: RedDependencySpeciesBinding,
    *,
    selected_kind: GoalKind,
    before_ledger: DependencySpecimenLedger,
    after_ledger: DependencySpecimenLedger | None,
) -> RedDualCapabilityOutcome:
    """Derive a settled +/-1 target, or a censored interruption, from ledgers."""

    if not isinstance(scenario, RedDualCapabilityScenarioSpec):
        raise TypeError("scenario must be a RedDualCapabilityScenarioSpec")
    if not isinstance(binding, RedDependencySpeciesBinding):
        raise TypeError("binding must be a RedDependencySpeciesBinding")
    if selected_kind not in _CAPABILITY_ORDER:
        raise RedDualCapabilityCurriculumError("selected dependency action differs")
    if not isinstance(before_ledger, DependencySpecimenLedger):
        raise TypeError("before_ledger must be a DependencySpecimenLedger")
    before = _dependency_multiset(before_ledger, binding)
    before_distance = dependency_distance(before, scenario.structure)
    if after_ledger is None:
        return RedDualCapabilityOutcome(
            scenario,
            binding,
            selected_kind,
            "interrupted",
            before_ledger,
            None,
            before_distance,
            None,
            None,
            None,
            None,
            None,
        )
    facts = _settled_outcome_facts(
        scenario,
        binding,
        selected_kind,
        before_ledger,
        after_ledger,
    )
    return RedDualCapabilityOutcome(
        scenario,
        binding,
        selected_kind,
        "settled",
        before_ledger,
        after_ledger,
        before_distance,
        *facts,
    )


def _settled_outcome_facts(
    scenario: RedDualCapabilityScenarioSpec,
    binding: RedDependencySpeciesBinding,
    selected_kind: GoalKind,
    before_ledger: DependencySpecimenLedger,
    after_ledger: DependencySpecimenLedger,
) -> tuple[int, bool, bool, bool, int]:
    before = _dependency_multiset(before_ledger, binding)
    if before != scenario.before:
        raise RedDualCapabilityCurriculumError("observed ledger differs from scenario start")
    after = _dependency_multiset(after_ledger, binding)
    expected_after = transition_dependency_multiset(before, selected_kind).after
    unrelated_preserved = _unrelated_species_preserved(before_ledger, after_ledger, binding)
    exact_transition = after == expected_after and unrelated_preserved
    required_preserved = preserves_required_living_species(before, after, scenario.structure)
    before_distance = dependency_distance(before, scenario.structure)
    after_distance = dependency_distance(after, scenario.structure)
    reward = (
        1 if exact_transition and required_preserved and after_distance < before_distance else -1
    )
    return (
        after_distance,
        exact_transition,
        required_preserved,
        unrelated_preserved,
        reward,
    )


def _dependency_multiset(
    ledger: DependencySpecimenLedger,
    binding: RedDependencySpeciesBinding,
) -> DependencyMultiset:
    return DependencyMultiset(
        ledger.count(binding.precursor_species_ref),
        ledger.count(binding.evolved_species_ref),
    )


def _unrelated_species_preserved(
    before: DependencySpecimenLedger,
    after: DependencySpecimenLedger,
    binding: RedDependencySpeciesBinding,
) -> bool:
    excluded = {binding.precursor_species_ref, binding.evolved_species_ref}
    before_counts = dict(before.specimen_counts)
    after_counts = dict(after.specimen_counts)
    return all(
        before_counts.get(species, 0) == after_counts.get(species, 0)
        for species in set(before_counts) | set(after_counts)
        if species not in excluded
    )


def _require_policy_rows(rows: tuple[dict[str, int | str], ...]) -> None:
    if len(rows) != 2:
        raise RedDualCapabilityCurriculumError("dependency policy menu differs")
    allowed = {
        "schema",
        "precursor_count",
        "evolved_count",
        "required_precursor_count",
        "required_evolved_count",
        "precursor_surplus",
        "unresolved_evolution_count",
        "dependency_distance",
        "adds_precursor",
        "consumes_precursor",
        "adds_evolved",
    }
    if any(
        set(row) != allowed
        or row.get("schema") != ROOTLESS_DEPENDENCY_FEATURE_SCHEMA
        or any(
            isinstance(value, str) and value != ROOTLESS_DEPENDENCY_FEATURE_SCHEMA
            for value in row.values()
        )
        for row in rows
    ):
        raise RedDualCapabilityCurriculumError(
            "dependency policy menu contains a title or binding identity"
        )
    if (rows[0]["adds_precursor"], rows[0]["consumes_precursor"], rows[0]["adds_evolved"]) != (
        1,
        0,
        0,
    ) or (
        rows[1]["adds_precursor"],
        rows[1]["consumes_precursor"],
        rows[1]["adds_evolved"],
    ) != (0, 1, 1):
        raise RedDualCapabilityCurriculumError("dependency candidate order differs")


def _require_sha256(value: str, subject: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RedDualCapabilityCurriculumError(f"{subject} SHA-256 is invalid")


__all__ = [
    "RED_DUAL_CAPABILITY_CURRICULUM_DESIGN_SCHEMA",
    "RED_DUAL_CAPABILITY_OUTCOME_SCHEMA",
    "RED_DUAL_CAPABILITY_SCENARIO_SCHEMA",
    "DependencySpecimenLedger",
    "ProspectiveRedCapabilityBinding",
    "ProspectiveRedDualCapabilityScenario",
    "RedDependencyCapabilityRequirement",
    "RedDependencyCapabilityRole",
    "RedDependencySpeciesBinding",
    "RedDualCapabilityCurriculumDesign",
    "RedDualCapabilityCurriculumError",
    "RedDualCapabilityOutcome",
    "RedDualCapabilityScenarioSpec",
    "red_dual_capability_curriculum_design",
    "red_dual_capability_scenario_specs",
    "verify_red_dual_capability_outcome",
]
