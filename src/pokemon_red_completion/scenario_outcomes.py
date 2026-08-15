"""Title-neutral outcome preferences for bounded scenario experiments.

The battle, navigation, and party-development policies do not share one feature
schema and should not pretend to share one raw outcome record.  They do share a
learner-facing question: given an identity-free candidate menu, which candidates
produced the best independently verified result?

This module owns that narrow boundary.  Domain adapters retain their own
measurements and declare an ordered objective before collection.  The common
contract validates lineage separation, preserves censored or incomplete evidence,
and exposes a target distribution only when every available candidate was
measured.  It never turns a teacher choice into an outcome label.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.scenario_lab import ScenarioFamily, ScenarioPartition

_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ScenarioOutcomeError(ValueError):
    """Raised when outcome evidence cannot safely become a preference target."""


class OutcomeDirection(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class OutcomeEvidenceStatus(StrEnum):
    MEASURED = "measured"
    CENSORED = "censored"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class OutcomeCriterion:
    """One prospectively ordered verifier measurement.

    Values are rounded to ``decimal_places`` before lexicographic comparison.
    This makes equivalence deterministic and transitive instead of relying on a
    chain of pairwise floating-point tolerances.
    """

    name: str
    direction: OutcomeDirection
    decimal_places: int

    def __post_init__(self) -> None:
        _safe_id(self.name, subject="outcome criterion")
        if not isinstance(self.direction, OutcomeDirection):
            raise ScenarioOutcomeError("outcome criterion direction is invalid")
        if type(self.decimal_places) is not int or not 0 <= self.decimal_places <= 12:  # noqa: E721
            raise ScenarioOutcomeError(
                "outcome criterion decimal places must be an integer from zero through twelve"
            )

    def preference_value(self, value: float) -> float:
        rounded = round(float(value), self.decimal_places)
        return rounded if self.direction is OutcomeDirection.MAXIMIZE else -rounded

    def public_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "direction": self.direction.value,
            "decimal_places": self.decimal_places,
        }


@dataclass(frozen=True, slots=True)
class OutcomeObjective:
    """A frozen, family-specific ordering over title-neutral measurements."""

    objective_id: str
    family: ScenarioFamily
    criteria: tuple[OutcomeCriterion, ...]

    def __post_init__(self) -> None:
        _safe_id(self.objective_id, subject="outcome objective")
        if not isinstance(self.family, ScenarioFamily):
            raise ScenarioOutcomeError("outcome objective family is invalid")
        if not self.criteria or any(
            not isinstance(item, OutcomeCriterion) for item in self.criteria
        ):
            raise ScenarioOutcomeError("outcome objective needs typed criteria")
        names = tuple(item.name for item in self.criteria)
        if len(names) != len(set(names)):
            raise ScenarioOutcomeError("outcome objective repeats a criterion")

    @property
    def objective_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def preference_key(self, values: tuple[float, ...]) -> tuple[float, ...]:
        if len(values) != len(self.criteria):
            raise ScenarioOutcomeError("outcome values do not match the frozen objective")
        return tuple(
            criterion.preference_value(value)
            for criterion, value in zip(self.criteria, values, strict=True)
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.outcome-objective.v1",
            "objective_id": self.objective_id,
            "family": self.family.value,
            "criteria": [item.public_dict() for item in self.criteria],
        }


@dataclass(frozen=True, slots=True)
class OutcomeCandidate:
    """One identity-free candidate vector and its availability at decision time."""

    candidate_index: int
    features: tuple[float, ...]
    available: bool = True

    def __post_init__(self) -> None:
        if type(self.candidate_index) is not int or self.candidate_index < 0:  # noqa: E721
            raise ScenarioOutcomeError("outcome candidate index is invalid")
        if not isinstance(self.features, tuple) or not self.features:
            raise ScenarioOutcomeError("outcome candidate needs an immutable feature vector")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in self.features
        ):
            raise ScenarioOutcomeError("outcome candidate features must be finite numbers")
        if not isinstance(self.available, bool):
            raise ScenarioOutcomeError("outcome candidate availability must be boolean")


@dataclass(frozen=True, slots=True)
class CandidateOutcome:
    """Verifier evidence for one candidate, without game-specific identity."""

    status: OutcomeEvidenceStatus
    criterion_values: tuple[float, ...] = ()
    actions_executed: int | None = None
    frames_executed: int | None = None
    evidence_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, OutcomeEvidenceStatus):
            raise ScenarioOutcomeError("candidate outcome status is invalid")
        if not isinstance(self.criterion_values, tuple) or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in self.criterion_values
        ):
            raise ScenarioOutcomeError("candidate outcome values must be finite numbers")
        if self.status is OutcomeEvidenceStatus.MEASURED:
            if not self.criterion_values:
                raise ScenarioOutcomeError("a measured outcome needs criterion values")
        elif self.criterion_values:
            raise ScenarioOutcomeError("censored or invalid outcomes cannot carry measurements")
        for value, name in (
            (self.actions_executed, "action count"),
            (self.frames_executed, "frame count"),
        ):
            if value is not None and (type(value) is not int or value < 0):  # noqa: E721
                raise ScenarioOutcomeError(f"candidate outcome {name} is invalid")
        if self.evidence_sha256 is not None and (
            not isinstance(self.evidence_sha256, str)
            or _SHA256.fullmatch(self.evidence_sha256) is None
        ):
            raise ScenarioOutcomeError("candidate outcome evidence digest is invalid")

    @property
    def measured(self) -> bool:
        return self.status is OutcomeEvidenceStatus.MEASURED


@dataclass(frozen=True, slots=True)
class ScenarioOutcomeExample:
    """One counterfactual candidate menu joined to domain-verifier outcomes."""

    scenario_id: str
    root_lineage_id: str
    initial_state_sha256: str
    partition: ScenarioPartition
    objective: OutcomeObjective
    feature_schema_id: str
    feature_names: tuple[str, ...]
    candidates: tuple[OutcomeCandidate, ...]
    outcomes: tuple[CandidateOutcome | None, ...]
    prospective_binding_sha256: str | None = None

    def __post_init__(self) -> None:
        _safe_id(self.scenario_id, subject="outcome scenario")
        _safe_id(self.root_lineage_id, subject="outcome root lineage")
        if (
            not isinstance(self.initial_state_sha256, str)
            or _SHA256.fullmatch(self.initial_state_sha256) is None
        ):
            raise ScenarioOutcomeError("outcome initial-state digest is invalid")
        if not isinstance(self.partition, ScenarioPartition):
            raise ScenarioOutcomeError("outcome partition is invalid")
        if not isinstance(self.objective, OutcomeObjective):
            raise ScenarioOutcomeError("outcome objective is invalid")
        if self.prospective_binding_sha256 is not None and (
            not isinstance(self.prospective_binding_sha256, str)
            or _SHA256.fullmatch(self.prospective_binding_sha256) is None
        ):
            raise ScenarioOutcomeError("outcome prospective-binding digest is invalid")
        _safe_id(self.feature_schema_id, subject="outcome feature schema")
        if (
            not isinstance(self.feature_names, tuple)
            or not self.feature_names
            or any(
                not isinstance(name, str) or _SAFE_ID.fullmatch(name) is None
                for name in self.feature_names
            )
            or len(self.feature_names) != len(set(self.feature_names))
        ):
            raise ScenarioOutcomeError("outcome feature names are invalid")
        if not isinstance(self.candidates, tuple) or len(self.candidates) < 2:
            raise ScenarioOutcomeError("an outcome example needs at least two candidates")
        if any(not isinstance(item, OutcomeCandidate) for item in self.candidates):
            raise ScenarioOutcomeError("outcome candidates must use the typed contract")
        if tuple(item.candidate_index for item in self.candidates) != tuple(
            range(len(self.candidates))
        ):
            raise ScenarioOutcomeError("outcome candidate indexes must be contiguous")
        if any(len(item.features) != len(self.feature_names) for item in self.candidates):
            raise ScenarioOutcomeError("outcome candidate feature width differs from its schema")
        if not isinstance(self.outcomes, tuple) or len(self.outcomes) != len(self.candidates):
            raise ScenarioOutcomeError("candidate outcomes do not match the candidate menu")
        available = 0
        for candidate, outcome in zip(self.candidates, self.outcomes, strict=True):
            if candidate.available:
                available += 1
                if outcome is not None and not isinstance(outcome, CandidateOutcome):
                    raise ScenarioOutcomeError("available candidate outcome is invalid")
                if (
                    outcome is not None
                    and outcome.measured
                    and len(outcome.criterion_values) != len(self.objective.criteria)
                ):
                    raise ScenarioOutcomeError(
                        "measured candidate outcome differs from its objective"
                    )
            elif outcome is not None:
                raise ScenarioOutcomeError(
                    "an unavailable candidate cannot carry execution evidence"
                )
        if available < 2:
            raise ScenarioOutcomeError(
                "an outcome preference needs at least two available candidates"
            )

    @property
    def family(self) -> ScenarioFamily:
        return self.objective.family

    @property
    def available_candidate_indices(self) -> tuple[int, ...]:
        return tuple(item.candidate_index for item in self.candidates if item.available)

    @property
    def fully_measured(self) -> bool:
        return all(
            outcome is not None and outcome.measured
            for candidate, outcome in zip(self.candidates, self.outcomes, strict=True)
            if candidate.available
        )

    @property
    def best_candidate_indices(self) -> tuple[int, ...]:
        if not self.fully_measured:
            return ()
        keys = {
            index: self.objective.preference_key(outcome.criterion_values)
            for index, (candidate, outcome) in enumerate(
                zip(self.candidates, self.outcomes, strict=True)
            )
            if candidate.available and outcome is not None
        }
        best = max(keys.values())
        return tuple(index for index, key in keys.items() if key == best)

    @property
    def learner_update_eligible(self) -> bool:
        return self.fully_measured and len(self.best_candidate_indices) < len(
            self.available_candidate_indices
        )

    @property
    def target_distribution(self) -> NDArray[np.float64]:
        winners = self.best_candidate_indices
        if not winners:
            raise ScenarioOutcomeError(
                "an incomplete or censored outcome has no preference distribution"
            )
        target = np.zeros(len(self.candidates), dtype=np.float64)
        target[list(winners)] = 1.0 / len(winners)
        return target

    @property
    def example_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def public_dict(self) -> dict[str, object]:
        status_counts = Counter(
            "unmeasured" if outcome is None else outcome.status.value
            for candidate, outcome in zip(self.candidates, self.outcomes, strict=True)
            if candidate.available
        )
        document: dict[str, object] = {
            "schema": (
                "pokemon.core.scenario-outcome-example.v2"
                if self.prospective_binding_sha256 is not None
                else "pokemon.core.scenario-outcome-example.v1"
            ),
            "scenario_id": self.scenario_id,
            "root_lineage_id": self.root_lineage_id,
            "initial_state_sha256": self.initial_state_sha256,
            "partition": self.partition.value,
            "family": self.family.value,
            "objective": self.objective.public_dict(),
            "feature_schema_id": self.feature_schema_id,
            "feature_names": list(self.feature_names),
            "candidate_count": len(self.candidates),
            "available_candidate_count": len(self.available_candidate_indices),
            "outcome_status_counts": dict(sorted(status_counts.items())),
            "fully_measured": self.fully_measured,
            "best_candidate_indices": list(self.best_candidate_indices),
            "learner_update_eligible": self.learner_update_eligible,
            "candidate_feature_values_public": False,
            "teacher_choice_targets": 0,
            "private_path_fields": 0,
        }
        if self.prospective_binding_sha256 is not None:
            document["prospective_binding_sha256"] = self.prospective_binding_sha256
        return document


@dataclass(frozen=True, slots=True)
class ScenarioOutcomeCatalog:
    """Leakage-audited multi-family outcome inventory."""

    examples: tuple[ScenarioOutcomeExample, ...]

    def __post_init__(self) -> None:
        if not self.examples or any(
            not isinstance(item, ScenarioOutcomeExample) for item in self.examples
        ):
            raise ScenarioOutcomeError("outcome catalog needs typed examples")
        scenario_ids = tuple(item.scenario_id for item in self.examples)
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ScenarioOutcomeError("outcome catalog repeats a scenario identity")
        _require_partition_isolation(
            self.examples,
            attribute="root_lineage_id",
            subject="root lineage",
        )
        _require_partition_isolation(
            self.examples,
            attribute="initial_state_sha256",
            subject="initial state",
        )

    @property
    def families(self) -> frozenset[ScenarioFamily]:
        return frozenset(item.family for item in self.examples)

    @property
    def catalog_sha256(self) -> str:
        return canonical_sha256(self.public_dict())

    def require_family_coverage(
        self,
        required: tuple[ScenarioFamily, ...] = tuple(ScenarioFamily),
    ) -> None:
        if (
            not isinstance(required, tuple)
            or not required
            or any(not isinstance(item, ScenarioFamily) for item in required)
            or len(required) != len(set(required))
        ):
            raise ScenarioOutcomeError("required outcome families are invalid")
        missing = tuple(item.value for item in required if item not in self.families)
        if missing:
            raise ScenarioOutcomeError(f"outcome catalog is missing family {missing[0]}")

    def public_dict(self) -> dict[str, object]:
        counts = Counter((item.partition.value, item.family.value) for item in self.examples)
        return {
            "schema": "pokemon.core.scenario-outcome-catalog.v1",
            "examples": [item.public_dict() for item in self.examples],
            "partition_family_counts": {
                f"{partition}:{family}": count
                for (partition, family), count in sorted(counts.items())
            },
            "fully_measured_examples": sum(item.fully_measured for item in self.examples),
            "learner_update_eligible_examples": sum(
                item.learner_update_eligible for item in self.examples
            ),
            "lineage_partition_overlap": 0,
            "initial_state_partition_overlap": 0,
            "teacher_choice_targets": 0,
            "private_path_fields": 0,
        }


def _safe_id(value: object, *, subject: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ScenarioOutcomeError(f"{subject} identity is invalid")
    return value


def _require_partition_isolation(
    examples: tuple[ScenarioOutcomeExample, ...],
    *,
    attribute: str,
    subject: str,
) -> None:
    assignments: dict[str, ScenarioPartition] = {}
    for example in examples:
        identity = getattr(example, attribute)
        prior = assignments.setdefault(identity, example.partition)
        if prior is not example.partition:
            raise ScenarioOutcomeError(f"{subject} crosses outcome partitions")


__all__ = [
    "CandidateOutcome",
    "OutcomeCandidate",
    "OutcomeCriterion",
    "OutcomeDirection",
    "OutcomeEvidenceStatus",
    "OutcomeObjective",
    "ScenarioOutcomeCatalog",
    "ScenarioOutcomeError",
    "ScenarioOutcomeExample",
]
