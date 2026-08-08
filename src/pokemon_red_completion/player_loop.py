"""Game-neutral closed loop for objective and bounded-skill execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from pokemon_red_completion.actions import MacroAction, SkillOutcome
from pokemon_red_completion.domain import GameState
from pokemon_red_completion.objective_skills import (
    ObjectiveSkillError,
    ObjectiveSkillRegistry,
)
from pokemon_red_completion.quest import Objective, QuestGraph, Specialist
from pokemon_red_completion.specialists import SpecialistRegistry, SpecialistRegistryError


class PlayerLoopError(RuntimeError):
    """Raised when an authority or semantic-safety boundary is violated."""


class StateObserver(Protocol):
    def observe(self) -> GameState: ...


class ObjectivePolicy(Protocol):
    def select(self, state: GameState) -> str: ...

    def complete(self, objective_id: str) -> None: ...

    def abandon(self, objective_id: str) -> None: ...


class ActionExecutor(Protocol):
    def execute(self, action: MacroAction) -> object: ...


class PlayerStepKind(StrEnum):
    ACTED = "acted"
    SKILL_COMPLETED = "skill_completed"
    OBJECTIVE_COMPLETED = "objective_completed"
    REPLAN = "replan"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class PlayerStepResult:
    kind: PlayerStepKind
    objective_id: str | None = None
    specialist: Specialist | None = None
    action: MacroAction | None = None
    skill_actions_executed: int = 0
    skill_frames_executed: int = 0
    skill_evidence: Mapping[str, object] | None = None
    facts_added: frozenset[str] = field(default_factory=frozenset)
    reason: str = ""

    def public_dict(self) -> dict[str, object]:
        action = self.action
        return {
            "kind": self.kind.value,
            "objective_id": self.objective_id,
            "specialist": self.specialist.value if self.specialist is not None else None,
            "action": (
                {
                    "kind": action.kind.value,
                    "value": action.value,
                    "repeat": action.repeat,
                }
                if action is not None
                else None
            ),
            "skill_actions_executed": self.skill_actions_executed,
            "skill_frames_executed": self.skill_frames_executed,
            "skill_evidence": self.skill_evidence,
            "facts_added": sorted(self.facts_added),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PlayerRunReport:
    steps: tuple[PlayerStepResult, ...]
    terminal_state: GameState
    graph_complete: bool
    exhausted_step_budget: bool

    @property
    def passed(self) -> bool:
        return self.graph_complete and not self.exhausted_step_budget

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-portable-player-run-v1",
            "status": "complete" if self.passed else "step_budget_exhausted",
            "graph_complete": self.graph_complete,
            "exhausted_step_budget": self.exhausted_step_budget,
            "step_count": len(self.steps),
            "steps": [step.public_dict() for step in self.steps],
            "terminal": {
                "mode": self.terminal_state.mode.value,
                "location": self.terminal_state.location,
                "facts": sorted(self.terminal_state.facts),
            },
        }


@dataclass(slots=True)
class DeterministicObjectivePolicy:
    """Explicit teacher baseline for the same player-loop interface."""

    graph: QuestGraph
    _active_objective_id: str | None = field(default=None, init=False)
    decisions: int = field(default=0, init=False)
    completions: int = field(default=0, init=False)

    def select(self, state: GameState) -> str:
        if self._active_objective_id is not None:
            raise PlayerLoopError("an objective is already active")
        objective = self.graph.next_objective(state)
        if objective is None:
            raise PlayerLoopError("no dependency-satisfied objective is available")
        self.decisions += 1
        self._active_objective_id = objective.id
        return objective.id

    def complete(self, objective_id: str) -> None:
        if objective_id != self._active_objective_id:
            raise PlayerLoopError("completed objective does not match policy authority")
        self.completions += 1
        self._active_objective_id = None

    def abandon(self, objective_id: str) -> None:
        if objective_id != self._active_objective_id:
            raise PlayerLoopError("abandoned objective does not match policy authority")
        self._active_objective_id = None


@dataclass(slots=True)
class PortablePlayerLoop:
    """Observe, choose, dispatch one typed action, observe its result, and replan."""

    graph: QuestGraph
    observer: StateObserver
    objective_policy: ObjectivePolicy
    specialists: SpecialistRegistry
    executor: ActionExecutor
    objective_skills: ObjectiveSkillRegistry = field(default_factory=ObjectiveSkillRegistry)
    decisions: int = field(default=0, init=False)
    actions_executed: int = field(default=0, init=False)
    objectives_completed: int = field(default=0, init=False)
    replans: int = field(default=0, init=False)

    def step(self) -> PlayerStepResult:
        before = self.observer.observe()
        self._require_consistent_progress(before)
        if self.graph.is_complete(before):
            return PlayerStepResult(
                kind=PlayerStepKind.COMPLETE,
                reason="Every objective has verified semantic completion evidence.",
            )

        objective = self._select_legal_objective(before)
        composite = self.objective_skills.get(objective.id)
        if composite is not None:
            return self._execute_objective_skill(before, objective)
        try:
            specialist = self.specialists.require(objective.specialist)
        except SpecialistRegistryError as error:
            raise PlayerLoopError(str(error)) from error
        plan = specialist.plan(before, objective)
        if plan.objective_id != objective.id or plan.specialist is not objective.specialist:
            raise PlayerLoopError("specialist returned a plan outside its objective authority")
        if plan.expected_facts != objective.completion_facts:
            raise PlayerLoopError(
                "specialist plan does not preserve the objective evidence contract"
            )
        if plan.outcome is SkillOutcome.FATAL:
            raise PlayerLoopError(plan.rationale or "specialist reported a fatal outcome")
        if plan.outcome in {SkillOutcome.REPLAN, SkillOutcome.RETRY}:
            self.replans += 1
            self._abandon_unfinished_objective(objective.id)
            return PlayerStepResult(
                kind=PlayerStepKind.REPLAN,
                objective_id=objective.id,
                specialist=objective.specialist,
                reason=plan.rationale,
            )
        if plan.outcome is SkillOutcome.SUCCESS:
            raise PlayerLoopError(
                "specialist claimed success before objective evidence was observed"
            )

        action = plan.actions[0]
        self.executor.execute(action)
        self.actions_executed += 1
        after = self.observer.observe()
        self._require_no_progress_regression(before, after)
        facts_added = after.facts.difference(before.facts)
        missing_effects = plan.additional_effect_facts.difference(after.facts)
        if missing_effects:
            raise PlayerLoopError(
                "specialist did not produce declared additional effects: "
                + ", ".join(sorted(missing_effects))
            )
        if objective.is_complete(after):
            self.objective_policy.complete(objective.id)
            self.objectives_completed += 1
            kind = PlayerStepKind.OBJECTIVE_COMPLETED
        else:
            self._abandon_unfinished_objective(objective.id)
            kind = PlayerStepKind.ACTED
        return PlayerStepResult(
            kind=kind,
            objective_id=objective.id,
            specialist=objective.specialist,
            action=action,
            facts_added=frozenset(facts_added),
            reason=plan.rationale,
        )

    def _execute_objective_skill(
        self,
        before: GameState,
        objective: Objective,
    ) -> PlayerStepResult:
        try:
            skill = self.objective_skills.require_for(objective)
            execution = self.objective_skills.execute_bounded(skill)
        except ObjectiveSkillError as error:
            self._abandon_unfinished_objective(objective.id)
            raise PlayerLoopError(str(error)) from error
        except Exception:
            self._abandon_unfinished_objective(objective.id)
            raise
        after = self.observer.observe()
        self._require_no_progress_regression(before, after)
        missing = objective.completion_facts.difference(after.facts)
        missing_effects = skill.additional_effect_facts.difference(after.facts)
        if missing or missing_effects:
            self._abandon_unfinished_objective(objective.id)
            absent = sorted(missing.union(missing_effects))
            raise PlayerLoopError(
                "objective skill lacks independently observed effects: " + ", ".join(absent)
            )
        self.objective_policy.complete(objective.id)
        self.actions_executed += execution.actions_executed
        self.objectives_completed += 1
        return PlayerStepResult(
            kind=PlayerStepKind.SKILL_COMPLETED,
            objective_id=objective.id,
            specialist=objective.specialist,
            skill_actions_executed=execution.actions_executed,
            skill_frames_executed=execution.frames_executed,
            skill_evidence=execution.evidence,
            facts_added=frozenset(after.facts.difference(before.facts)),
            reason="Executed a registered bounded objective skill and independently verified it.",
        )

    def run(self, *, max_steps: int) -> PlayerRunReport:
        if type(max_steps) is not int or max_steps <= 0:  # noqa: E721
            raise ValueError("max_steps must be a positive integer")
        results: list[PlayerStepResult] = []
        for _ in range(max_steps):
            result = self.step()
            results.append(result)
            if result.kind is PlayerStepKind.COMPLETE:
                terminal = self.observer.observe()
                return PlayerRunReport(
                    steps=tuple(results),
                    terminal_state=terminal,
                    graph_complete=True,
                    exhausted_step_budget=False,
                )
        terminal = self.observer.observe()
        return PlayerRunReport(
            steps=tuple(results),
            terminal_state=terminal,
            graph_complete=self.graph.is_complete(terminal),
            exhausted_step_budget=not self.graph.is_complete(terminal),
        )

    def public_dict(self) -> Mapping[str, object]:
        return {
            "schema": "pokemon-portable-player-loop-v1",
            "decisions": self.decisions,
            "actions_executed": self.actions_executed,
            "objectives_completed": self.objectives_completed,
            "replans": self.replans,
        }

    def _select_legal_objective(self, state: GameState) -> Objective:
        available = self.graph.available_objectives(state)
        available_by_id = {objective.id: objective for objective in available}
        selected_id = self.objective_policy.select(state)
        self.decisions += 1
        if not isinstance(selected_id, str) or selected_id not in available_by_id:
            raise PlayerLoopError("objective policy selected an unavailable objective")
        return available_by_id[selected_id]

    def _abandon_unfinished_objective(self, objective_id: str) -> None:
        self.objective_policy.abandon(objective_id)

    def _require_consistent_progress(self, state: GameState) -> None:
        completed = self.graph.completed_ids(state)
        inconsistent = tuple(
            objective.id
            for objective in self.graph
            if objective.id in completed and not objective.prerequisites.issubset(completed)
        )
        if inconsistent:
            raise PlayerLoopError(
                "completion evidence violates quest prerequisites: " + ", ".join(inconsistent)
            )

    def _require_no_progress_regression(
        self,
        before: GameState,
        after: GameState,
    ) -> None:
        lost = self.graph.completed_ids(before).difference(self.graph.completed_ids(after))
        if lost:
            raise PlayerLoopError(
                "verified objective evidence regressed after action: " + ", ".join(sorted(lost))
            )
