from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pokemon_red_completion.actions import SkillPlan
from pokemon_red_completion.domain import GameState
from pokemon_red_completion.quest import Objective, QuestGraph
from pokemon_red_completion.specialists import SpecialistRegistry, SpecialistRegistryError


class TeacherDecisionKind(StrEnum):
    ACT = "act"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class TeacherDecision:
    kind: TeacherDecisionKind
    objective: Objective | None = None
    plan: SkillPlan | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.kind is TeacherDecisionKind.ACT and (self.objective is None or self.plan is None):
            raise ValueError("an ACT decision requires both objective and plan")
        if self.kind is not TeacherDecisionKind.ACT and self.plan is not None:
            raise ValueError("only an ACT decision may contain a plan")


@dataclass(frozen=True, slots=True)
class DeterministicTeacher:
    graph: QuestGraph
    specialists: SpecialistRegistry

    def decide(self, state: GameState) -> TeacherDecision:
        inconsistent = self._inconsistent_completed_objectives(state)
        if inconsistent:
            return TeacherDecision(
                kind=TeacherDecisionKind.BLOCKED,
                reason=(
                    "Completion evidence violates quest prerequisites: "
                    + ", ".join(inconsistent)
                ),
            )
        if self.graph.is_complete(state):
            return TeacherDecision(
                kind=TeacherDecisionKind.COMPLETE,
                reason="Every objective has verified semantic completion evidence.",
            )

        objective = self.graph.next_objective(state)
        if objective is None:
            return TeacherDecision(
                kind=TeacherDecisionKind.BLOCKED,
                reason="No dependency-satisfied objective is available.",
            )
        try:
            planner = self.specialists.require(objective.specialist)
        except SpecialistRegistryError as error:
            return TeacherDecision(kind=TeacherDecisionKind.BLOCKED, reason=str(error))

        plan = planner.plan(state, objective)
        if plan.objective_id != objective.id or plan.specialist is not objective.specialist:
            return TeacherDecision(
                kind=TeacherDecisionKind.BLOCKED,
                objective=objective,
                reason="Specialist returned a plan for the wrong objective or authority.",
            )
        return TeacherDecision(
            kind=TeacherDecisionKind.ACT,
            objective=objective,
            plan=plan,
            reason=plan.rationale,
        )

    def _inconsistent_completed_objectives(self, state: GameState) -> tuple[str, ...]:
        completed = self.graph.completed_ids(state)
        return tuple(
            objective.id
            for objective in self.graph
            if objective.id in completed
            and not objective.prerequisites.issubset(completed)
        )
