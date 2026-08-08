from __future__ import annotations

from dataclasses import dataclass

import pytest

from pokemon_red_completion.actions import (
    MacroAction,
    MacroActionKind,
    SkillOutcome,
    SkillPlan,
)
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.player_loop import (
    DeterministicObjectivePolicy,
    PlayerLoopError,
    PlayerStepKind,
    PortablePlayerLoop,
)
from pokemon_red_completion.quest import Objective, QuestGraph, Specialist
from pokemon_red_completion.specialists import SpecialistRegistry


def _graph() -> QuestGraph:
    return QuestGraph(
        (
            Objective(
                id="first",
                title="First",
                completion_facts=frozenset({"done:first"}),
                specialist=Specialist.INTERACTION,
                priority=0,
            ),
            Objective(
                id="second",
                title="Second",
                completion_facts=frozenset({"done:second"}),
                specialist=Specialist.INTERACTION,
                prerequisites=frozenset({"first"}),
                priority=1,
            ),
        )
    )


@dataclass
class _World:
    state: GameState
    actions: list[MacroAction]

    def observe(self) -> GameState:
        return self.state

    def execute(self, action: MacroAction) -> object:
        self.actions.append(action)
        fact = "done:first" if "done:first" not in self.state.facts else "done:second"
        self.state = self.state.with_facts(fact)
        return action


@dataclass(frozen=True)
class _InteractionPlanner:
    specialist: Specialist = Specialist.INTERACTION

    def plan(self, state: GameState, objective: Objective) -> SkillPlan:
        return SkillPlan(
            objective_id=objective.id,
            specialist=self.specialist,
            outcome=SkillOutcome.IN_PROGRESS,
            actions=(MacroAction(MacroActionKind.INTERACT),),
            expected_facts=objective.completion_facts,
            rationale="Apply one bounded interaction.",
        )


def _loop(world: _World) -> PortablePlayerLoop:
    graph = _graph()
    return PortablePlayerLoop(
        graph=graph,
        observer=world,
        objective_policy=DeterministicObjectivePolicy(graph),
        specialists=SpecialistRegistry((_InteractionPlanner(),)),
        executor=world,
    )


def test_portable_loop_observes_selects_dispatches_and_replans_to_completion() -> None:
    world = _World(GameState(GameMode.OVERWORLD), [])
    loop = _loop(world)

    report = loop.run(max_steps=3)

    assert report.passed
    assert [step.kind for step in report.steps] == [
        PlayerStepKind.OBJECTIVE_COMPLETED,
        PlayerStepKind.OBJECTIVE_COMPLETED,
        PlayerStepKind.COMPLETE,
    ]
    assert [step.objective_id for step in report.steps[:2]] == ["first", "second"]
    assert len(world.actions) == 2
    assert loop.public_dict() == {
        "schema": "pokemon-portable-player-loop-v1",
        "decisions": 2,
        "actions_executed": 2,
        "objectives_completed": 2,
        "replans": 0,
    }


@dataclass
class _IllegalPolicy:
    def select(self, state: GameState) -> str:
        return "second"

    def complete(self, objective_id: str) -> None:
        raise AssertionError("illegal authority must not complete")

    def abandon(self, objective_id: str) -> None:
        raise AssertionError("illegal authority must not be abandoned")


def test_portable_loop_rejects_unavailable_objective_authority() -> None:
    graph = _graph()
    world = _World(GameState(GameMode.OVERWORLD), [])
    loop = PortablePlayerLoop(
        graph=graph,
        observer=world,
        objective_policy=_IllegalPolicy(),
        specialists=SpecialistRegistry((_InteractionPlanner(),)),
        executor=world,
    )

    with pytest.raises(PlayerLoopError, match="unavailable objective"):
        loop.step()
    assert world.actions == []


def test_portable_loop_fails_when_verified_progress_regresses() -> None:
    graph = _graph()

    @dataclass
    class RegressingWorld(_World):
        def execute(self, action: MacroAction) -> object:
            self.actions.append(action)
            self.state = GameState(GameMode.OVERWORLD)
            return action

    world = RegressingWorld(
        GameState(GameMode.OVERWORLD, facts=frozenset({"done:first"})),
        [],
    )
    loop = PortablePlayerLoop(
        graph=graph,
        observer=world,
        objective_policy=DeterministicObjectivePolicy(graph),
        specialists=SpecialistRegistry((_InteractionPlanner(),)),
        executor=world,
    )

    with pytest.raises(PlayerLoopError, match="evidence regressed"):
        loop.step()


def test_skill_plan_rejects_actions_beyond_its_execution_bound() -> None:
    with pytest.raises(ValueError, match="exceed"):
        SkillPlan(
            objective_id="first",
            specialist=Specialist.INTERACTION,
            outcome=SkillOutcome.IN_PROGRESS,
            actions=(
                MacroAction(MacroActionKind.INTERACT),
                MacroAction(MacroActionKind.CONFIRM),
            ),
            max_executor_steps=1,
        )


def test_portable_loop_rejects_a_mismatched_evidence_contract() -> None:
    @dataclass(frozen=True)
    class WrongEvidencePlanner:
        specialist: Specialist = Specialist.INTERACTION

        def plan(self, state: GameState, objective: Objective) -> SkillPlan:
            return SkillPlan(
                objective_id=objective.id,
                specialist=self.specialist,
                outcome=SkillOutcome.IN_PROGRESS,
                actions=(MacroAction(MacroActionKind.INTERACT),),
                expected_facts=frozenset({"done:something_else"}),
            )

    graph = _graph()
    world = _World(GameState(GameMode.OVERWORLD), [])
    loop = PortablePlayerLoop(
        graph=graph,
        observer=world,
        objective_policy=DeterministicObjectivePolicy(graph),
        specialists=SpecialistRegistry((WrongEvidencePlanner(),)),
        executor=world,
    )

    with pytest.raises(PlayerLoopError, match="evidence contract"):
        loop.step()
    assert world.actions == []
