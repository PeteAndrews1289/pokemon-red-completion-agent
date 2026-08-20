"""Proposed rootless representation for living-Dex dependency decisions.

Production source defines eight public train scenarios and an opaque four-row
development commitment roster. Development inputs exist only as externally supplied
opening bytes and are read only after a completed fit manifest authenticates.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pokemon_red_completion.goal_manager import GoalKind
from pokemon_red_completion.provenance import canonical_sha256

ROOTLESS_DEPENDENCY_DESIGN_SCHEMA = "pokemon.core.proposed-rootless-living-dex-dependency-design.v3"
ROOTLESS_DEPENDENCY_FEATURE_SCHEMA = (
    "pokemon.core.proposed-rootless-living-dex-dependency-features.v3"
)
ROOTLESS_DEPENDENCY_OUTCOME_SCHEMA = (
    "pokemon.core.proposed-rootless-living-dex-dependency-outcome.v3"
)
DEVELOPMENT_COMMITMENT_ROSTER_SCHEMA = "pokemon.core.rootless-dependency-development-commitments.v1"
DEVELOPMENT_OPENING_SCHEMA = "pokemon.core.rootless-dependency-development-opening.v1"
COMPLETED_FIT_MANIFEST_SCHEMA = "pokemon.core.rootless-fit-bundle-manifest.v2"
COMPLETED_FIT_TERMINAL_SCHEMA = "pokemon.core.completed-rootless-fit-terminal.v1"

_TRAIN_STRUCTURES = ((1, 1), (2, 1), (1, 2), (2, 2))
_ALLOWED_ACTIONS = frozenset({GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES})
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SAFE_DEVELOPMENT_ID = re.compile(r"rootless-development-[0-9a-z]{16,32}")
_SAFE_FAMILY_ID = re.compile(r"development-family-[0-9a-z]{16,32}")
_MAX_MANIFEST_BYTES = 16 * 1024
_MAX_OPENING_BYTES = 16 * 1024


class LivingDexDependencyCurriculumError(ValueError):
    """The proposed curriculum or a pure comparison input is invalid."""


class DependencyMultiplicity(StrEnum):
    SCARCE = "scarce"
    DUPLICATE_READY = "duplicate_ready"


@dataclass(frozen=True, slots=True)
class DependencyStructure:
    required_precursor_count: int
    required_evolved_count: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value <= 0  # noqa: E721
            for value in (
                self.required_precursor_count,
                self.required_evolved_count,
            )
        ):
            raise LivingDexDependencyCurriculumError(
                "dependency requirements must be positive integers"
            )

    def public_dict(self) -> dict[str, int]:
        return {
            "required_precursor_count": self.required_precursor_count,
            "required_evolved_count": self.required_evolved_count,
        }


@dataclass(frozen=True, slots=True)
class DependencyMultiset:
    precursor_count: int
    evolved_count: int

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 0  # noqa: E721
            for value in (self.precursor_count, self.evolved_count)
        ):
            raise LivingDexDependencyCurriculumError(
                "dependency multiset counts must be non-negative integers"
            )

    def public_dict(self) -> dict[str, int]:
        return {
            "precursor_count": self.precursor_count,
            "evolved_count": self.evolved_count,
        }


@dataclass(frozen=True, slots=True)
class DependencyPredecisionFeatures:
    """Proposed identity-free representation for future game adapters."""

    precursor_count: int
    evolved_count: int
    required_precursor_count: int
    required_evolved_count: int
    precursor_surplus: int
    unresolved_evolution_count: int
    dependency_distance: int

    def __post_init__(self) -> None:
        values = (
            self.precursor_count,
            self.evolved_count,
            self.required_precursor_count,
            self.required_evolved_count,
            self.precursor_surplus,
            self.unresolved_evolution_count,
            self.dependency_distance,
        )
        if any(type(value) is not int or value < 0 for value in values):  # noqa: E721
            raise LivingDexDependencyCurriculumError(
                "dependency features must be non-negative integers"
            )
        state = DependencyMultiset(self.precursor_count, self.evolved_count)
        structure = DependencyStructure(self.required_precursor_count, self.required_evolved_count)
        if (
            self.precursor_surplus != max(0, self.precursor_count - self.required_precursor_count)
            or self.unresolved_evolution_count
            != max(0, self.required_evolved_count - self.evolved_count)
            or self.dependency_distance != dependency_distance(state, structure)
        ):
            raise LivingDexDependencyCurriculumError(
                "dependency features do not derive from the predecision multiset"
            )

    def policy_dict(self) -> dict[str, int | str]:
        return {
            "schema": ROOTLESS_DEPENDENCY_FEATURE_SCHEMA,
            "precursor_count": self.precursor_count,
            "evolved_count": self.evolved_count,
            "required_precursor_count": self.required_precursor_count,
            "required_evolved_count": self.required_evolved_count,
            "precursor_surplus": self.precursor_surplus,
            "unresolved_evolution_count": self.unresolved_evolution_count,
            "dependency_distance": self.dependency_distance,
        }


@dataclass(frozen=True, slots=True)
class DependencyCandidateFeatures:
    state: DependencyPredecisionFeatures
    adds_precursor: int
    consumes_precursor: int
    adds_evolved: int

    def __post_init__(self) -> None:
        if not isinstance(self.state, DependencyPredecisionFeatures):
            raise LivingDexDependencyCurriculumError("candidate state differs")
        semantics = (self.adds_precursor, self.consumes_precursor, self.adds_evolved)
        if any(type(value) is not int for value in semantics) or semantics not in {
            (1, 0, 0),
            (0, 1, 1),
        }:
            raise LivingDexDependencyCurriculumError("candidate semantics differ")

    def policy_dict(self) -> dict[str, int | str]:
        return {
            **self.state.policy_dict(),
            "adds_precursor": self.adds_precursor,
            "consumes_precursor": self.consumes_precursor,
            "adds_evolved": self.adds_evolved,
        }


@dataclass(frozen=True, slots=True)
class RootlessDependencyScenario:
    """One of the eight canonical public train scenarios."""

    scenario_id: str
    family_ordinal: int
    multiplicity: DependencyMultiplicity
    partition: Literal["train"]
    structure: DependencyStructure
    before: DependencyMultiset
    assigned_action: GoalKind

    def __post_init__(self) -> None:
        if type(self.family_ordinal) is not int or not (  # noqa: E721
            0 <= self.family_ordinal < len(_TRAIN_STRUCTURES)
        ):
            raise LivingDexDependencyCurriculumError("family ordinal differs")
        if not isinstance(self.multiplicity, DependencyMultiplicity):
            raise LivingDexDependencyCurriculumError("scenario multiplicity differs")
        if self.scenario_id != _train_scenario_id(self.family_ordinal, self.multiplicity):
            raise LivingDexDependencyCurriculumError("scenario identity differs")
        if self.partition != "train":
            raise LivingDexDependencyCurriculumError("scenario partition differs")
        if self.structure != _train_structure(self.family_ordinal):
            raise LivingDexDependencyCurriculumError("scenario structure differs")
        if self.before != dependency_multiset(self.multiplicity, self.structure):
            raise LivingDexDependencyCurriculumError("scenario multiset differs")
        if self.assigned_action is not _train_action(self.family_ordinal, self.multiplicity):
            raise LivingDexDependencyCurriculumError("scenario action differs")

    @property
    def predecision_features(self) -> DependencyPredecisionFeatures:
        return dependency_predecision_features(self.before, self.structure)

    def candidate_features(self, action: GoalKind) -> DependencyCandidateFeatures:
        if action is GoalKind.ACQUIRE_SPECIES:
            semantics = (1, 0, 0)
        elif action is GoalKind.EVOLVE_SPECIES:
            semantics = (0, 1, 1)
        else:
            raise LivingDexDependencyCurriculumError("candidate action differs")
        return DependencyCandidateFeatures(
            self.predecision_features, semantics[0], semantics[1], semantics[2]
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "family_ordinal": self.family_ordinal,
            "multiplicity": self.multiplicity.value,
            "partition": self.partition,
            "structure": self.structure.public_dict(),
            "before": self.before.public_dict(),
            "assigned_action": self.assigned_action.value,
            "outcome_embedded": False,
        }


@dataclass(frozen=True, slots=True)
class DevelopmentCommitmentRow:
    scenario_id: str
    opening_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scenario_id, str)
            or _SAFE_DEVELOPMENT_ID.fullmatch(self.scenario_id) is None
        ):
            raise LivingDexDependencyCurriculumError("development scenario identity is unsafe")
        if (
            not isinstance(self.opening_sha256, str)
            or _SHA256.fullmatch(self.opening_sha256) is None
        ):
            raise LivingDexDependencyCurriculumError("development opening commitment is invalid")

    def public_dict(self) -> dict[str, str]:
        return {
            "scenario_id": self.scenario_id,
            "opening_sha256": self.opening_sha256,
        }


@dataclass(frozen=True, slots=True)
class DevelopmentCommitmentRoster:
    rows: tuple[DevelopmentCommitmentRow, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rows, tuple)
            or len(self.rows) != 4
            or len({row.scenario_id for row in self.rows}) != 4
            or len({row.opening_sha256 for row in self.rows}) != 4
        ):
            raise LivingDexDependencyCurriculumError(
                "development roster must contain four distinct commitments"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": DEVELOPMENT_COMMITMENT_ROSTER_SCHEMA,
            "row_count": 4,
            "rows": [row.public_dict() for row in self.rows],
        }


@dataclass(frozen=True, slots=True)
class DependencyTransition:
    before: DependencyMultiset
    action: GoalKind
    after: DependencyMultiset
    action_applied: bool

    def __post_init__(self) -> None:
        expected_after, expected_applied = _derive_transition(self.before, self.action)
        if self.after != expected_after or self.action_applied is not expected_applied:
            raise LivingDexDependencyCurriculumError("dependency transition is not derived")


@dataclass(frozen=True, slots=True)
class RootlessDependencyOutcome:
    scenario_id: str
    structure: DependencyStructure
    status: Literal["settled", "interrupted"]
    action: GoalKind
    before: DependencyMultiset
    after: DependencyMultiset | None
    dependency_distance_before: int
    dependency_distance_after: int | None
    preserved_required_living_species: bool | None
    reward: int | None

    def __post_init__(self) -> None:
        scenario = _canonical_train_scenario(self.scenario_id)
        if (
            self.structure != scenario.structure
            or self.before != scenario.before
            or self.action is not scenario.assigned_action
            or self.dependency_distance_before != dependency_distance(self.before, self.structure)
        ):
            raise LivingDexDependencyCurriculumError(
                "dependency outcome is not bound to its train scenario"
            )
        if self.status == "interrupted":
            if any(
                value is not None
                for value in (
                    self.after,
                    self.dependency_distance_after,
                    self.preserved_required_living_species,
                    self.reward,
                )
            ):
                raise LivingDexDependencyCurriculumError(
                    "interrupted dependency outcome must remain censored"
                )
            return
        if (
            self.status != "settled"
            or self.after is None
            or self.dependency_distance_after is None
            or self.preserved_required_living_species is None
            or self.reward not in {-1, 1}
        ):
            raise LivingDexDependencyCurriculumError("settled dependency outcome differs")
        transition = transition_dependency_multiset(self.before, self.action)
        after_distance = dependency_distance(transition.after, self.structure)
        preserved = preserves_required_living_species(self.before, transition.after, self.structure)
        if (
            self.after != transition.after
            or self.dependency_distance_after != after_distance
            or self.preserved_required_living_species is not preserved
        ):
            raise LivingDexDependencyCurriculumError("settled dependency outcome is not derived")
        expected_reward = (
            1 if preserved and after_distance < self.dependency_distance_before else -1
        )
        if self.reward != expected_reward:
            raise LivingDexDependencyCurriculumError("dependency reward is not derived")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": ROOTLESS_DEPENDENCY_OUTCOME_SCHEMA,
            "scenario_id": self.scenario_id,
            "status": self.status,
            "action": self.action.value,
            "structure": self.structure.public_dict(),
            "before": self.before.public_dict(),
            "after": None if self.after is None else self.after.public_dict(),
            "dependency_distance_before": self.dependency_distance_before,
            "dependency_distance_after": self.dependency_distance_after,
            "preserved_required_living_species": self.preserved_required_living_species,
            "reward": self.reward,
        }


@dataclass(frozen=True, slots=True)
class VerifiedDevelopmentOpening:
    scenario_id: str
    family_id: str
    nonce: str
    multiplicity: DependencyMultiplicity
    structure: DependencyStructure
    before: DependencyMultiset
    assigned_action: GoalKind
    derived_reward: int


@dataclass(frozen=True, slots=True)
class AuthenticatedDependencyFit:
    """Opaque proof that the externally pinned fit bundle completed for this design."""

    design_sha256: str
    fit_manifest_sha256: str
    fit_terminal_sha256: str
    canonical_fit_sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedDevelopmentComparison:
    fit_manifest_sha256: str
    fit_terminal_sha256: str
    canonical_fit_sha256: str
    openings: tuple[VerifiedDevelopmentOpening, ...]


@dataclass(frozen=True, slots=True)
class RootlessLivingDexDependencyDesign:
    train_scenarios: tuple[RootlessDependencyScenario, ...]
    development_roster: DevelopmentCommitmentRoster

    def __post_init__(self) -> None:
        expected = tuple(
            _build_train_scenario(family, multiplicity)
            for family in range(len(_TRAIN_STRUCTURES))
            for multiplicity in (
                DependencyMultiplicity.SCARCE,
                DependencyMultiplicity.DUPLICATE_READY,
            )
        )
        if not isinstance(self.train_scenarios, tuple) or self.train_scenarios != expected:
            raise LivingDexDependencyCurriculumError(
                "train design differs from its canonical eight scenarios"
            )
        action_counts = Counter(row.assigned_action for row in self.train_scenarios)
        rewards = Counter(
            materialize_train_dependency_outcome(row).reward for row in self.train_scenarios
        )
        if action_counts != {
            GoalKind.ACQUIRE_SPECIES: 4,
            GoalKind.EVOLVE_SPECIES: 4,
        } or rewards != {-1: 4, 1: 4}:
            raise LivingDexDependencyCurriculumError("train counterbalance differs")

    @property
    def design_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": ROOTLESS_DEPENDENCY_DESIGN_SCHEMA,
            "train_family_count": 4,
            "train_scenario_count": 8,
            "train_scenarios": [row.public_dict() for row in self.train_scenarios],
            "development_commitment_roster": self.development_roster.public_dict(),
        }


def build_rootless_living_dex_dependency_design(
    development_roster: DevelopmentCommitmentRoster,
) -> RootlessLivingDexDependencyDesign:
    if not isinstance(development_roster, DevelopmentCommitmentRoster):
        raise TypeError("development_roster must be a DevelopmentCommitmentRoster")
    train = tuple(
        _build_train_scenario(family, multiplicity)
        for family in range(len(_TRAIN_STRUCTURES))
        for multiplicity in (
            DependencyMultiplicity.SCARCE,
            DependencyMultiplicity.DUPLICATE_READY,
        )
    )
    return RootlessLivingDexDependencyDesign(train, development_roster)


def verify_development_openings_for_comparison(
    design: RootlessLivingDexDependencyDesign,
    *,
    completed_fit_manifest_bytes: bytes,
    expected_fit_manifest_sha256: str,
    completed_fit_terminal_bytes: bytes,
    expected_fit_terminal_sha256: str,
    opening_payloads: tuple[bytes, ...],
) -> VerifiedDevelopmentComparison:
    """Authenticate two externally pinned fit records, then read openings."""

    if not isinstance(design, RootlessLivingDexDependencyDesign):
        raise TypeError("design must be a RootlessLivingDexDependencyDesign")
    authenticated_fit = authenticate_completed_dependency_fit_bundle(
        design,
        completed_fit_manifest_bytes,
        expected_fit_manifest_sha256,
        completed_fit_terminal_bytes,
        expected_fit_terminal_sha256,
    )
    return verify_development_openings_after_fit(
        design,
        authenticated_fit=authenticated_fit,
        opening_payloads=opening_payloads,
    )


def authenticate_completed_dependency_fit_bundle(
    design: RootlessLivingDexDependencyDesign,
    completed_fit_manifest_bytes: bytes,
    expected_fit_manifest_sha256: str,
    completed_fit_terminal_bytes: bytes,
    expected_fit_terminal_sha256: str,
) -> AuthenticatedDependencyFit:
    """Authenticate the completed fit before a caller is allowed to open dev payloads."""

    if not isinstance(design, RootlessLivingDexDependencyDesign):
        raise TypeError("design must be a RootlessLivingDexDependencyDesign")
    fit_sha = _authenticate_completed_fit_bundle(
        completed_fit_manifest_bytes,
        expected_fit_manifest_sha256,
        completed_fit_terminal_bytes,
        expected_fit_terminal_sha256,
        design.design_sha256,
    )
    return AuthenticatedDependencyFit(
        design_sha256=design.design_sha256,
        fit_manifest_sha256=expected_fit_manifest_sha256,
        fit_terminal_sha256=expected_fit_terminal_sha256,
        canonical_fit_sha256=fit_sha,
    )


def verify_development_openings_after_fit(
    design: RootlessLivingDexDependencyDesign,
    *,
    authenticated_fit: AuthenticatedDependencyFit,
    opening_payloads: tuple[bytes, ...],
) -> VerifiedDevelopmentComparison:
    """Decode the fixed development roster only after independent fit authentication."""

    if not isinstance(design, RootlessLivingDexDependencyDesign):
        raise TypeError("design must be a RootlessLivingDexDependencyDesign")
    if (
        not isinstance(authenticated_fit, AuthenticatedDependencyFit)
        or authenticated_fit.design_sha256 != design.design_sha256
    ):
        raise LivingDexDependencyCurriculumError("authenticated fit design differs")
    if not isinstance(opening_payloads, tuple) or len(opening_payloads) != 4:
        raise LivingDexDependencyCurriculumError(
            "comparison requires exactly four opening payloads"
        )
    commitments = {row.scenario_id: row.opening_sha256 for row in design.development_roster.rows}
    openings = tuple(_parse_opening(payload, commitments) for payload in opening_payloads)
    _validate_opening_set(openings, design.train_scenarios)
    return VerifiedDevelopmentComparison(
        fit_manifest_sha256=authenticated_fit.fit_manifest_sha256,
        fit_terminal_sha256=authenticated_fit.fit_terminal_sha256,
        canonical_fit_sha256=authenticated_fit.canonical_fit_sha256,
        openings=openings,
    )


def dependency_multiset(
    multiplicity: DependencyMultiplicity,
    structure: DependencyStructure,
) -> DependencyMultiset:
    if not isinstance(structure, DependencyStructure):
        raise TypeError("structure must be a DependencyStructure")
    if multiplicity is DependencyMultiplicity.SCARCE:
        return DependencyMultiset(structure.required_precursor_count, 0)
    if multiplicity is DependencyMultiplicity.DUPLICATE_READY:
        return DependencyMultiset(
            structure.required_precursor_count + structure.required_evolved_count,
            0,
        )
    raise LivingDexDependencyCurriculumError("dependency multiplicity differs")


def dependency_distance(
    state: DependencyMultiset,
    structure: DependencyStructure,
) -> int:
    if not isinstance(state, DependencyMultiset) or not isinstance(structure, DependencyStructure):
        raise TypeError("state and structure must be dependency values")
    unresolved = max(0, structure.required_evolved_count - state.evolved_count)
    precursor_demand = structure.required_precursor_count + unresolved
    return max(0, precursor_demand - state.precursor_count) + unresolved


def dependency_predecision_features(
    state: DependencyMultiset,
    structure: DependencyStructure,
) -> DependencyPredecisionFeatures:
    if not isinstance(state, DependencyMultiset) or not isinstance(structure, DependencyStructure):
        raise TypeError("state and structure must be dependency values")
    return DependencyPredecisionFeatures(
        precursor_count=state.precursor_count,
        evolved_count=state.evolved_count,
        required_precursor_count=structure.required_precursor_count,
        required_evolved_count=structure.required_evolved_count,
        precursor_surplus=max(0, state.precursor_count - structure.required_precursor_count),
        unresolved_evolution_count=max(0, structure.required_evolved_count - state.evolved_count),
        dependency_distance=dependency_distance(state, structure),
    )


def transition_dependency_multiset(
    state: DependencyMultiset,
    action: GoalKind,
) -> DependencyTransition:
    after, applied = _derive_transition(state, action)
    return DependencyTransition(state, action, after, applied)


def preserves_required_living_species(
    before: DependencyMultiset,
    after: DependencyMultiset,
    structure: DependencyStructure,
) -> bool:
    if not isinstance(before, DependencyMultiset) or not isinstance(after, DependencyMultiset):
        raise TypeError("before and after must be DependencyMultiset values")
    if not isinstance(structure, DependencyStructure):
        raise TypeError("structure must be a DependencyStructure")
    return all(
        after_count >= min(before_count, required)
        for before_count, after_count, required in (
            (
                before.precursor_count,
                after.precursor_count,
                structure.required_precursor_count,
            ),
            (
                before.evolved_count,
                after.evolved_count,
                structure.required_evolved_count,
            ),
        )
    )


def materialize_train_dependency_outcome(
    scenario: RootlessDependencyScenario,
    *,
    interrupted: bool = False,
) -> RootlessDependencyOutcome:
    if not isinstance(scenario, RootlessDependencyScenario):
        raise TypeError("scenario must be a RootlessDependencyScenario")
    if scenario != _canonical_train_scenario(scenario.scenario_id):
        raise LivingDexDependencyCurriculumError("train scenario is not canonical")
    before_distance = dependency_distance(scenario.before, scenario.structure)
    if interrupted:
        return RootlessDependencyOutcome(
            scenario.scenario_id,
            scenario.structure,
            "interrupted",
            scenario.assigned_action,
            scenario.before,
            None,
            before_distance,
            None,
            None,
            None,
        )
    transition = transition_dependency_multiset(scenario.before, scenario.assigned_action)
    after_distance = dependency_distance(transition.after, scenario.structure)
    preserved = preserves_required_living_species(
        scenario.before, transition.after, scenario.structure
    )
    return RootlessDependencyOutcome(
        scenario.scenario_id,
        scenario.structure,
        "settled",
        scenario.assigned_action,
        scenario.before,
        transition.after,
        before_distance,
        after_distance,
        preserved,
        1 if preserved and after_distance < before_distance else -1,
    )


def _derive_transition(
    state: DependencyMultiset, action: GoalKind
) -> tuple[DependencyMultiset, bool]:
    if not isinstance(state, DependencyMultiset):
        raise TypeError("state must be a DependencyMultiset")
    if action is GoalKind.ACQUIRE_SPECIES:
        return DependencyMultiset(state.precursor_count + 1, state.evolved_count), True
    if action is GoalKind.EVOLVE_SPECIES:
        if state.precursor_count == 0:
            return state, False
        return DependencyMultiset(state.precursor_count - 1, state.evolved_count + 1), True
    raise LivingDexDependencyCurriculumError("dependency transition action differs")


def _train_structure(family: int) -> DependencyStructure:
    precursor, evolved = _TRAIN_STRUCTURES[family]
    return DependencyStructure(precursor, evolved)


def _train_action(family: int, multiplicity: DependencyMultiplicity) -> GoalKind:
    return (
        GoalKind.ACQUIRE_SPECIES
        if (multiplicity is DependencyMultiplicity.SCARCE) == (family % 2 == 0)
        else GoalKind.EVOLVE_SPECIES
    )


def _train_scenario_id(family: int, multiplicity: DependencyMultiplicity) -> str:
    row = 1 if multiplicity is DependencyMultiplicity.SCARCE else 2
    return f"rootless-train-{family + 1:02d}-{row:02d}"


def _build_train_scenario(
    family: int, multiplicity: DependencyMultiplicity
) -> RootlessDependencyScenario:
    structure = _train_structure(family)
    return RootlessDependencyScenario(
        _train_scenario_id(family, multiplicity),
        family,
        multiplicity,
        "train",
        structure,
        dependency_multiset(multiplicity, structure),
        _train_action(family, multiplicity),
    )


def _canonical_train_scenario(scenario_id: str) -> RootlessDependencyScenario:
    if not isinstance(scenario_id, str):
        raise LivingDexDependencyCurriculumError("train scenario identity differs")
    for family in range(len(_TRAIN_STRUCTURES)):
        for multiplicity in DependencyMultiplicity:
            if scenario_id == _train_scenario_id(family, multiplicity):
                return _build_train_scenario(family, multiplicity)
    raise LivingDexDependencyCurriculumError("train scenario identity differs")


def _authenticate_completed_fit_bundle(
    manifest_payload: bytes,
    expected_manifest_sha256: str,
    terminal_payload: bytes,
    expected_terminal_sha256: str,
    design_sha256: str,
) -> str:
    for digest in (expected_manifest_sha256, expected_terminal_sha256):
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise LivingDexDependencyCurriculumError("pinned fit digest is invalid")
    if expected_manifest_sha256 == expected_terminal_sha256:
        raise LivingDexDependencyCurriculumError("pinned fit digests must be distinct")
    manifest = _parse_canonical_document(manifest_payload, _MAX_MANIFEST_BYTES, "fit manifest")
    if hashlib.sha256(manifest_payload).hexdigest() != expected_manifest_sha256:
        raise LivingDexDependencyCurriculumError("fit manifest pin differs")
    manifest_keys = {
        "schema",
        "design_sha256",
        "fit_sha256",
        "train_dataset_sha256",
        "executable_bundle_sha256",
    }
    if set(manifest) != manifest_keys:
        raise LivingDexDependencyCurriculumError("fit manifest fields differ")
    fit_sha = manifest["fit_sha256"]
    if not isinstance(fit_sha, str):
        raise LivingDexDependencyCurriculumError("fit bundle identity differs")
    if (
        manifest["schema"] != COMPLETED_FIT_MANIFEST_SCHEMA
        or manifest["design_sha256"] != design_sha256
        or not _is_sha256(fit_sha)
        or any(
            not _is_sha256(manifest[field])
            for field in ("train_dataset_sha256", "executable_bundle_sha256")
        )
    ):
        raise LivingDexDependencyCurriculumError("fit bundle identity differs")
    terminal = _parse_canonical_document(terminal_payload, _MAX_MANIFEST_BYTES, "fit terminal")
    if hashlib.sha256(terminal_payload).hexdigest() != expected_terminal_sha256:
        raise LivingDexDependencyCurriculumError("fit terminal pin differs")
    if set(terminal) != {
        "schema",
        "status",
        "design_sha256",
        "fit_sha256",
        "fit_manifest_sha256",
    }:
        raise LivingDexDependencyCurriculumError("fit terminal fields differ")
    if (
        terminal["schema"] != COMPLETED_FIT_TERMINAL_SCHEMA
        or terminal["status"] != "completed"
        or terminal["design_sha256"] != design_sha256
        or terminal["fit_sha256"] != fit_sha
        or terminal["fit_manifest_sha256"] != expected_manifest_sha256
    ):
        raise LivingDexDependencyCurriculumError("fit terminal relationship differs")
    return fit_sha


def _parse_opening(
    payload: bytes,
    commitments: dict[str, str],
) -> VerifiedDevelopmentOpening:
    document = _parse_canonical_document(payload, _MAX_OPENING_BYTES, "opening")
    expected_keys = {
        "schema",
        "scenario_id",
        "family_id",
        "nonce",
        "partition",
        "multiplicity",
        "structure",
        "before",
        "assigned_action",
    }
    if set(document) != expected_keys or document["schema"] != DEVELOPMENT_OPENING_SCHEMA:
        raise LivingDexDependencyCurriculumError("development opening fields differ")
    scenario_id = document["scenario_id"]
    family_id = document["family_id"]
    nonce = document["nonce"]
    if (
        not isinstance(scenario_id, str)
        or _SAFE_DEVELOPMENT_ID.fullmatch(scenario_id) is None
        or not isinstance(family_id, str)
        or _SAFE_FAMILY_ID.fullmatch(family_id) is None
        or not isinstance(nonce, str)
        or _SHA256.fullmatch(nonce) is None
        or len(set(nonce)) < 8
        or document["partition"] != "development"
    ):
        raise LivingDexDependencyCurriculumError("development opening identity differs")
    if commitments.get(scenario_id) != hashlib.sha256(payload).hexdigest():
        raise LivingDexDependencyCurriculumError("development opening commitment differs")
    try:
        multiplicity_value = document["multiplicity"]
        action_value = document["assigned_action"]
        if not isinstance(multiplicity_value, str) or not isinstance(action_value, str):
            raise ValueError
        multiplicity = DependencyMultiplicity(multiplicity_value)
        assigned_action = GoalKind(action_value)
        structure_doc = document["structure"]
        before_doc = document["before"]
        if not isinstance(structure_doc, dict) or set(structure_doc) != {
            "required_precursor_count",
            "required_evolved_count",
        }:
            raise ValueError
        if not isinstance(before_doc, dict) or set(before_doc) != {
            "precursor_count",
            "evolved_count",
        }:
            raise ValueError
        structure = DependencyStructure(
            structure_doc["required_precursor_count"],
            structure_doc["required_evolved_count"],
        )
        before = DependencyMultiset(before_doc["precursor_count"], before_doc["evolved_count"])
    except (KeyError, TypeError, ValueError):
        raise LivingDexDependencyCurriculumError("development opening values differ") from None
    if assigned_action not in _ALLOWED_ACTIONS:
        raise LivingDexDependencyCurriculumError("development action differs")
    if before != dependency_multiset(multiplicity, structure):
        raise LivingDexDependencyCurriculumError("development multiset differs")
    transition = transition_dependency_multiset(before, assigned_action)
    preserved = preserves_required_living_species(before, transition.after, structure)
    derived_reward = (
        1
        if preserved
        and dependency_distance(transition.after, structure)
        < dependency_distance(before, structure)
        else -1
    )
    return VerifiedDevelopmentOpening(
        scenario_id,
        family_id,
        nonce,
        multiplicity,
        structure,
        before,
        assigned_action,
        derived_reward,
    )


def _validate_opening_set(
    openings: tuple[VerifiedDevelopmentOpening, ...],
    train: tuple[RootlessDependencyScenario, ...],
) -> None:
    if len({row.scenario_id for row in openings}) != 4 or len({row.nonce for row in openings}) != 4:
        raise LivingDexDependencyCurriculumError(
            "development identities and nonces must be distinct"
        )
    families: dict[str, list[VerifiedDevelopmentOpening]] = {}
    for row in openings:
        families.setdefault(row.family_id, []).append(row)
    if len(families) != 2:
        raise LivingDexDependencyCurriculumError("development openings must contain two families")
    structures: set[DependencyStructure] = set()
    for rows in families.values():
        if (
            len(rows) != 2
            or {row.multiplicity for row in rows} != set(DependencyMultiplicity)
            or len({row.structure for row in rows}) != 1
        ):
            raise LivingDexDependencyCurriculumError(
                "each development family must contain both multiplicities"
            )
        structures.add(rows[0].structure)
    if len(structures) != 2 or structures & {row.structure for row in train}:
        raise LivingDexDependencyCurriculumError(
            "development structures must be distinct and held out"
        )
    if Counter(row.assigned_action for row in openings) != {
        GoalKind.ACQUIRE_SPECIES: 2,
        GoalKind.EVOLVE_SPECIES: 2,
    }:
        raise LivingDexDependencyCurriculumError("development actions are not counterbalanced")
    if Counter(row.derived_reward for row in openings) != {-1: 2, 1: 2}:
        raise LivingDexDependencyCurriculumError("development rewards are not counterbalanced")


def _parse_canonical_document(
    payload: bytes,
    maximum_bytes: int,
    subject: str,
) -> dict[str, object]:
    if not isinstance(payload, bytes) or not 0 < len(payload) <= maximum_bytes:
        raise LivingDexDependencyCurriculumError(f"{subject} bytes are invalid")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise LivingDexDependencyCurriculumError(f"{subject} is invalid") from None
    if not isinstance(document, dict) or _canonical_bytes(document) != payload:
        raise LivingDexDependencyCurriculumError(f"{subject} is not canonical")
    return document


def _canonical_bytes(document: object) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        + b"\n"
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None
