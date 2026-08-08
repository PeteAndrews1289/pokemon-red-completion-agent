"""Typed contracts for bounded, chapter-sized objective skills."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol

from pokemon_red_completion.quest import Objective, Specialist


class ObjectiveSkillError(RuntimeError):
    """Raised when a composite skill violates its declared authority or bound."""


@dataclass(frozen=True, slots=True)
class ObjectiveSkillExecution:
    """Mechanics evidence returned by a bounded skill, before semantic verification."""

    actions_executed: int
    frames_executed: int
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("actions_executed", self.actions_executed),
            ("frames_executed", self.frames_executed),
        ):
            if type(value) is not int or value < 0:  # noqa: E721
                raise ValueError(f"{name} must be a non-negative integer")


class ObjectiveSkill(Protocol):
    """A fixed, bounded mechanic executor selected by objective ID."""

    objective_id: str
    specialist: Specialist
    expected_facts: frozenset[str]
    additional_effect_facts: frozenset[str]
    max_actions: int
    max_frames: int

    def execute(self) -> ObjectiveSkillExecution: ...


class ObjectiveSkillRegistry:
    """Explicit allow-list for composite skills; absence never implies fallback."""

    def __init__(self, skills: Iterable[ObjectiveSkill] = ()) -> None:
        by_objective: dict[str, ObjectiveSkill] = {}
        for skill in skills:
            if not skill.objective_id:
                raise ValueError("objective skill ID must be non-empty")
            if skill.objective_id in by_objective:
                raise ValueError(f"duplicate objective skill: {skill.objective_id}")
            if type(skill.max_actions) is not int or skill.max_actions <= 0:  # noqa: E721
                raise ValueError("objective skill max_actions must be positive")
            if type(skill.max_frames) is not int or skill.max_frames <= 0:  # noqa: E721
                raise ValueError("objective skill max_frames must be positive")
            if skill.expected_facts.intersection(skill.additional_effect_facts):
                raise ValueError("additional objective skill effects overlap expected facts")
            by_objective[skill.objective_id] = skill
        self._by_objective = by_objective

    def get(self, objective_id: str) -> ObjectiveSkill | None:
        return self._by_objective.get(objective_id)

    def require_for(self, objective: Objective) -> ObjectiveSkill:
        skill = self.get(objective.id)
        if skill is None:
            raise ObjectiveSkillError(f"no composite skill registered for {objective.id}")
        if skill.specialist is not objective.specialist:
            raise ObjectiveSkillError("objective skill specialist does not match quest authority")
        if skill.expected_facts != objective.completion_facts:
            raise ObjectiveSkillError("objective skill evidence does not match quest contract")
        return skill

    @staticmethod
    def execute_bounded(skill: ObjectiveSkill) -> ObjectiveSkillExecution:
        result = skill.execute()
        if result.actions_executed > skill.max_actions:
            raise ObjectiveSkillError("objective skill exceeded its declared action bound")
        if result.frames_executed > skill.max_frames:
            raise ObjectiveSkillError("objective skill exceeded its declared frame bound")
        return result
