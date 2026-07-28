from __future__ import annotations

from dataclasses import dataclass

from pokemon_red_completion.actions import (
    MacroAction,
    MacroActionKind,
    SkillOutcome,
    SkillPlan,
)
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.quest import Objective, QuestGraph, Specialist
from pokemon_red_completion.specialists import SpecialistRegistry
from pokemon_red_completion.teacher import (
    DeterministicTeacher,
    TeacherDecisionKind,
)


@dataclass(frozen=True)
class StubPlanner:
    specialist: Specialist

    def plan(self, state: GameState, objective: Objective) -> SkillPlan:
        return SkillPlan(
            objective_id=objective.id,
            specialist=self.specialist,
            outcome=SkillOutcome.IN_PROGRESS,
            actions=(MacroAction(MacroActionKind.INTERACT),),
        )


def _graph() -> QuestGraph:
    return QuestGraph(
        (
            Objective(
                id="start",
                title="Start",
                completion_facts=frozenset({"done:start"}),
                specialist=Specialist.INTERACTION,
                priority=0,
            ),
            Objective(
                id="finish",
                title="Finish",
                completion_facts=frozenset({"done:finish"}),
                specialist=Specialist.VERIFICATION,
                prerequisites=frozenset({"start"}),
            ),
        )
    )


def test_teacher_dispatches_only_dependency_satisfied_objective() -> None:
    teacher = DeterministicTeacher(
        _graph(),
        SpecialistRegistry(
            (
                StubPlanner(Specialist.INTERACTION),
                StubPlanner(Specialist.VERIFICATION),
            )
        ),
    )

    first = teacher.decide(GameState(GameMode.OVERWORLD))
    second = teacher.decide(
        GameState(GameMode.OVERWORLD, facts=frozenset({"done:start"}))
    )

    assert first.kind is TeacherDecisionKind.ACT
    assert first.objective is not None and first.objective.id == "start"
    assert second.kind is TeacherDecisionKind.ACT
    assert second.objective is not None and second.objective.id == "finish"


def test_teacher_blocks_out_of_order_evidence() -> None:
    teacher = DeterministicTeacher(
        _graph(),
        SpecialistRegistry((StubPlanner(Specialist.INTERACTION),)),
    )

    decision = teacher.decide(
        GameState(GameMode.OVERWORLD, facts=frozenset({"done:finish"}))
    )

    assert decision.kind is TeacherDecisionKind.BLOCKED
    assert "violates quest prerequisites" in decision.reason


def test_teacher_reports_complete_only_after_all_evidence() -> None:
    teacher = DeterministicTeacher(_graph(), SpecialistRegistry(()))
    state = GameState(
        GameMode.HALL_OF_FAME,
        facts=frozenset({"done:start", "done:finish"}),
    )

    decision = teacher.decide(state)

    assert decision.kind is TeacherDecisionKind.COMPLETE
