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
from pokemon_red_completion.objective_skills import (
    ObjectiveSkillAvailability,
    ObjectiveSkillExecution,
    ObjectiveSkillRegistry,
)
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
        "schema": "pokemon-portable-player-loop-v2",
        "decisions": 2,
        "actions_executed": 2,
        "objectives_completed": 2,
        "replans": 0,
    }


@dataclass
class _IllegalPolicy:
    def select(
        self,
        state: GameState,
        candidates: tuple[Objective, ...] | None = None,
    ) -> str:
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

    with pytest.raises(PlayerLoopError, match="non-executable objective"):
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


@dataclass
class _CompositeSkill:
    world: _World
    objective_id: str = "first"
    specialist: Specialist = Specialist.INTERACTION
    expected_facts: frozenset[str] = frozenset({"done:first"})
    additional_effect_facts: frozenset[str] = frozenset({"effect:extra"})
    max_actions: int = 4
    max_frames: int = 40
    expose_effects: bool = True
    executable: bool = True

    def availability(self, state: GameState) -> ObjectiveSkillAvailability:
        return ObjectiveSkillAvailability(self.executable, "Test skill availability.")

    def execute(self) -> ObjectiveSkillExecution:
        if self.expose_effects:
            self.world.state = self.world.state.with_facts("done:first", "effect:extra")
        return ObjectiveSkillExecution(
            actions_executed=3,
            frames_executed=30,
            evidence={"mechanic_gate": "passed"},
        )


def test_portable_loop_dispatches_and_independently_verifies_composite_skill() -> None:
    graph = _graph()
    world = _World(GameState(GameMode.OVERWORLD), [])
    skill = _CompositeSkill(world)
    loop = PortablePlayerLoop(
        graph=graph,
        observer=world,
        objective_policy=DeterministicObjectivePolicy(graph),
        specialists=SpecialistRegistry((_InteractionPlanner(),)),
        executor=world,
        objective_skills=ObjectiveSkillRegistry((skill,)),
    )

    result = loop.step()

    assert result.kind is PlayerStepKind.SKILL_COMPLETED
    assert result.objective_id == "first"
    assert result.skill_actions_executed == 3
    assert result.skill_frames_executed == 30
    assert result.skill_evidence == {"mechanic_gate": "passed"}
    assert result.facts_added == frozenset({"done:first", "effect:extra"})
    assert world.actions == []
    assert loop.actions_executed == 3
    assert loop.objectives_completed == 1


def test_portable_loop_rejects_unobserved_composite_skill_claims() -> None:
    graph = _graph()
    world = _World(GameState(GameMode.OVERWORLD), [])
    skill = _CompositeSkill(world, expose_effects=False)
    policy = DeterministicObjectivePolicy(graph)
    loop = PortablePlayerLoop(
        graph=graph,
        observer=world,
        objective_policy=policy,
        specialists=SpecialistRegistry((_InteractionPlanner(),)),
        executor=world,
        objective_skills=ObjectiveSkillRegistry((skill,)),
    )

    with pytest.raises(PlayerLoopError, match="independently observed"):
        loop.step()

    assert policy._active_objective_id is None
    assert loop.objectives_completed == 0


def test_portable_loop_enforces_composite_skill_execution_bounds() -> None:
    graph = _graph()
    world = _World(GameState(GameMode.OVERWORLD), [])
    skill = _CompositeSkill(world, max_actions=2)
    loop = PortablePlayerLoop(
        graph=graph,
        observer=world,
        objective_policy=DeterministicObjectivePolicy(graph),
        specialists=SpecialistRegistry((_InteractionPlanner(),)),
        executor=world,
        objective_skills=ObjectiveSkillRegistry((skill,)),
    )

    with pytest.raises(PlayerLoopError, match="action bound"):
        loop.step()


@dataclass
class _CandidateRecordingPolicy:
    candidates_seen: tuple[str, ...] = ()
    active: str | None = None

    def select(
        self,
        state: GameState,
        candidates: tuple[Objective, ...] | None = None,
    ) -> str:
        assert candidates is not None
        self.candidates_seen = tuple(objective.id for objective in candidates)
        self.active = candidates[0].id
        return candidates[0].id

    def complete(self, objective_id: str) -> None:
        assert objective_id == self.active
        self.active = None

    def abandon(self, objective_id: str) -> None:
        assert objective_id == self.active
        self.active = None


def test_portable_loop_masks_dependency_legal_but_unexecutable_objectives() -> None:
    graph = QuestGraph(
        (
            Objective(
                id="first",
                title="First",
                completion_facts=frozenset({"done:first"}),
                specialist=Specialist.INTERACTION,
            ),
            Objective(
                id="parallel",
                title="Parallel",
                completion_facts=frozenset({"done:parallel"}),
                specialist=Specialist.BATTLE,
            ),
        )
    )
    world = _World(GameState(GameMode.OVERWORLD), [])
    policy = _CandidateRecordingPolicy()
    skill = _CompositeSkill(world)
    loop = PortablePlayerLoop(
        graph=graph,
        observer=world,
        objective_policy=policy,
        specialists=SpecialistRegistry(()),
        executor=world,
        objective_skills=ObjectiveSkillRegistry((skill,)),
    )

    result = loop.step()

    assert policy.candidates_seen == ("first",)
    assert result.dependency_legal_objectives == ("first", "parallel")
    assert result.executable_objectives == ("first",)
    assert result.excluded_objectives == (
        ("parallel", "No objective skill or specialist planner is registered."),
    )
    assert result.public_dict()["excluded_objectives"] == [
        {
            "objective_id": "parallel",
            "reason": "No objective skill or specialist planner is registered.",
        }
    ]


def test_portable_loop_fails_before_policy_when_no_objective_is_executable() -> None:
    graph = _graph()
    world = _World(GameState(GameMode.OVERWORLD), [])
    policy = _CandidateRecordingPolicy()
    loop = PortablePlayerLoop(
        graph=graph,
        observer=world,
        objective_policy=policy,
        specialists=SpecialistRegistry(()),
        executor=world,
    )

    with pytest.raises(PlayerLoopError, match="no dependency-legal objective is executable"):
        loop.step()

    assert policy.candidates_seen == ()
