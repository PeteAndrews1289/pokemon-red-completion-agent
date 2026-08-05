"""Validated completion objectives and deterministic quest selection."""

from __future__ import annotations

import heapq
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from pokemon_red_completion.domain import Fact, GameState

_OBJECTIVE_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_SEMANTIC_REGION = re.compile(r"^[a-z][a-z0-9_]*$")


class Specialist(StrEnum):
    """Primary executor responsible for an objective."""

    BOOTSTRAP = "bootstrap"
    NAVIGATION = "navigation"
    INTERACTION = "interaction"
    MENU = "menu"
    BATTLE = "battle"
    RECOVERY = "recovery"
    VERIFICATION = "verification"


class QuestGraphValidationError(ValueError):
    """Raised when an objective collection cannot form a safe quest graph."""


def _as_string_set(values: Iterable[str], field_name: str) -> frozenset[str]:
    result = frozenset(values)
    invalid = sorted(repr(value) for value in result if not isinstance(value, str) or not value)
    if invalid:
        raise ValueError(f"{field_name} must contain non-empty strings: {', '.join(invalid)}")
    return result


@dataclass(frozen=True, slots=True)
class Objective:
    """One verifiable unit of progress in the completion plan.

    Lower ``priority`` values are selected first when multiple objectives are
    available.  ``id`` is the stable final tie-breaker, so selection never
    depends on construction order.
    """

    id: str
    title: str
    completion_facts: frozenset[Fact]
    specialist: Specialist
    prerequisites: frozenset[str] = field(default_factory=frozenset)
    priority: int = 100
    description: str = ""
    target_region: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _OBJECTIVE_ID.fullmatch(self.id):
            raise ValueError(
                "objective id must start with a lowercase letter and contain only "
                "lowercase letters, digits, and underscores"
            )
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("objective title must be non-empty")
        if not isinstance(self.specialist, Specialist):
            raise TypeError("specialist must be a Specialist")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise TypeError("priority must be an integer")
        if self.priority < 0:
            raise ValueError("priority must be non-negative")
        if self.target_region is not None and (
            not isinstance(self.target_region, str)
            or _SEMANTIC_REGION.fullmatch(self.target_region) is None
        ):
            raise ValueError("target_region must be a lowercase semantic region or None")

        facts = _as_string_set(self.completion_facts, "completion_facts")
        if not facts:
            raise ValueError("objective must define at least one completion fact")
        prerequisites = _as_string_set(self.prerequisites, "prerequisites")
        if self.id in prerequisites:
            raise ValueError(f"objective {self.id!r} cannot depend on itself")

        object.__setattr__(self, "completion_facts", facts)
        object.__setattr__(self, "prerequisites", prerequisites)

    def is_complete(self, state: GameState) -> bool:
        """Return whether the objective's evidence is present in ``state``."""

        return state.has_all(self.completion_facts)


@dataclass(frozen=True, slots=True, init=False)
class QuestGraph:
    """An immutable, validated directed acyclic graph of objectives."""

    objectives: tuple[Objective, ...]
    _by_id: Mapping[str, Objective] = field(repr=False, compare=False)

    def __init__(self, objectives: Iterable[Objective]) -> None:
        supplied = tuple(objectives)
        by_id: dict[str, Objective] = {}
        duplicates: set[str] = set()
        for objective in supplied:
            if objective.id in by_id:
                duplicates.add(objective.id)
            by_id[objective.id] = objective
        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise QuestGraphValidationError(f"duplicate objective ids: {duplicate_list}")

        missing = sorted(
            (objective.id, prerequisite)
            for objective in supplied
            for prerequisite in objective.prerequisites
            if prerequisite not in by_id
        )
        if missing:
            details = ", ".join(
                f"{objective_id} -> {prerequisite}"
                for objective_id, prerequisite in missing
            )
            raise QuestGraphValidationError(f"missing prerequisite objectives: {details}")

        self._validate_acyclic(by_id)
        ordered = tuple(sorted(supplied, key=lambda objective: (objective.priority, objective.id)))
        object.__setattr__(self, "objectives", ordered)
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))

    @staticmethod
    def _validate_acyclic(by_id: Mapping[str, Objective]) -> None:
        state: dict[str, int] = {objective_id: 0 for objective_id in by_id}
        trail: list[str] = []

        def visit(objective_id: str) -> None:
            if state[objective_id] == 2:
                return
            if state[objective_id] == 1:
                cycle_start = trail.index(objective_id)
                cycle = [*trail[cycle_start:], objective_id]
                raise QuestGraphValidationError(
                    f"objective cycle detected: {' -> '.join(cycle)}"
                )

            state[objective_id] = 1
            trail.append(objective_id)
            for prerequisite in sorted(by_id[objective_id].prerequisites):
                visit(prerequisite)
            trail.pop()
            state[objective_id] = 2

        for objective_id in sorted(by_id):
            visit(objective_id)

    def __iter__(self) -> Iterator[Objective]:
        return iter(self.objectives)

    def __len__(self) -> int:
        return len(self.objectives)

    def objective(self, objective_id: str) -> Objective:
        """Look up an objective by stable identifier."""

        try:
            return self._by_id[objective_id]
        except KeyError:
            raise KeyError(f"unknown objective: {objective_id}") from None

    def completed_ids(self, state: GameState) -> frozenset[str]:
        """Return all objectives whose completion evidence is present."""

        return frozenset(
            objective.id for objective in self.objectives if objective.is_complete(state)
        )

    def available_objectives(self, state: GameState) -> tuple[Objective, ...]:
        """Return incomplete, dependency-satisfied objectives in stable order."""

        completed = self.completed_ids(state)
        return tuple(
            objective
            for objective in self.objectives
            if objective.id not in completed and objective.prerequisites.issubset(completed)
        )

    def next_objective(self, state: GameState) -> Objective | None:
        """Select the next objective deterministically, or ``None`` at completion."""

        available = self.available_objectives(state)
        return available[0] if available else None

    def is_complete(self, state: GameState) -> bool:
        """Return whether every objective has its required completion evidence."""

        return len(self.completed_ids(state)) == len(self.objectives)

    def terminal_objectives(self) -> tuple[Objective, ...]:
        """Return objectives with no dependants, in deterministic order."""

        referenced = frozenset(
            prerequisite
            for objective in self.objectives
            for prerequisite in objective.prerequisites
        )
        return tuple(objective for objective in self.objectives if objective.id not in referenced)

    def direct_dependant_count(self, objective_id: str) -> int:
        """Return how many immediate objectives one completion unlocks."""

        self.objective(objective_id)
        return sum(
            objective_id in objective.prerequisites for objective in self.objectives
        )

    def topological_order(self) -> tuple[Objective, ...]:
        """Return a deterministic dependency-first ordering of all objectives."""

        dependants: dict[str, list[str]] = {
            objective.id: [] for objective in self.objectives
        }
        remaining = {
            objective.id: len(objective.prerequisites) for objective in self.objectives
        }
        for objective in self.objectives:
            for prerequisite in objective.prerequisites:
                dependants[prerequisite].append(objective.id)

        ready = [
            (objective.priority, objective.id)
            for objective in self.objectives
            if remaining[objective.id] == 0
        ]
        heapq.heapify(ready)
        ordered: list[Objective] = []
        while ready:
            _, objective_id = heapq.heappop(ready)
            objective = self._by_id[objective_id]
            ordered.append(objective)
            for dependant_id in sorted(dependants[objective_id]):
                remaining[dependant_id] -= 1
                if remaining[dependant_id] == 0:
                    dependant = self._by_id[dependant_id]
                    heapq.heappush(ready, (dependant.priority, dependant.id))

        return tuple(ordered)
