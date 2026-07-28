from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from pokemon_red_completion.actions import (
    MacroAction,
    MacroActionKind,
    SkillOutcome,
    SkillPlan,
)
from pokemon_red_completion.domain import GameMode, GameState
from pokemon_red_completion.navigation import (
    Coordinate,
    GridMap,
    NoPathError,
    path_to_directions,
    shortest_path,
)
from pokemon_red_completion.quest import Objective, Specialist


class SpecialistPlanner(Protocol):
    specialist: Specialist

    def plan(self, state: GameState, objective: Objective) -> SkillPlan: ...


class SpecialistRegistryError(ValueError):
    """Raised when the teacher cannot resolve one unambiguous specialist."""


class SpecialistRegistry:
    def __init__(self, planners: Iterable[SpecialistPlanner]) -> None:
        by_kind: dict[Specialist, SpecialistPlanner] = {}
        duplicates: set[Specialist] = set()
        for planner in planners:
            if planner.specialist in by_kind:
                duplicates.add(planner.specialist)
            by_kind[planner.specialist] = planner
        if duplicates:
            names = ", ".join(sorted(specialist.value for specialist in duplicates))
            raise SpecialistRegistryError(f"duplicate specialists: {names}")
        self._by_kind: Mapping[Specialist, SpecialistPlanner] = MappingProxyType(by_kind)

    def require(self, specialist: Specialist) -> SpecialistPlanner:
        try:
            return self._by_kind[specialist]
        except KeyError:
            raise SpecialistRegistryError(
                f"no planner registered for specialist: {specialist.value}"
            ) from None


@dataclass(frozen=True, slots=True)
class NavigationContext:
    grid: GridMap
    start: Coordinate
    goal: Coordinate
    allow_blocked_goal: bool = False


class NavigationContextProvider(Protocol):
    def context_for(self, state: GameState, objective: Objective) -> NavigationContext: ...


@dataclass(frozen=True, slots=True)
class GridNavigationSpecialist:
    context_provider: NavigationContextProvider
    specialist: Specialist = Specialist.NAVIGATION

    def plan(self, state: GameState, objective: Objective) -> SkillPlan:
        context = self.context_provider.context_for(state, objective)
        try:
            path = shortest_path(
                context.grid,
                context.start,
                context.goal,
                allow_blocked_goal=context.allow_blocked_goal,
            )
        except NoPathError:
            return SkillPlan(
                objective_id=objective.id,
                specialist=self.specialist,
                outcome=SkillOutcome.REPLAN,
                expected_facts=objective.completion_facts,
                rationale="No verified path exists in the current collision map.",
            )

        directions = path_to_directions(path)
        if not directions:
            return SkillPlan(
                objective_id=objective.id,
                specialist=self.specialist,
                outcome=SkillOutcome.REPLAN,
                expected_facts=objective.completion_facts,
                rationale="The target coordinate is reached but objective evidence is absent.",
            )
        return SkillPlan(
            objective_id=objective.id,
            specialist=self.specialist,
            outcome=SkillOutcome.IN_PROGRESS,
            actions=tuple(
                MacroAction(MacroActionKind.MOVE, direction.value)
                for direction in directions
            ),
            expected_facts=objective.completion_facts,
            max_executor_steps=len(directions),
            rationale="Follow the shortest verified collision-map path.",
        )


@dataclass(frozen=True, slots=True)
class InteractionSpecialist:
    specialist: Specialist = Specialist.INTERACTION

    def plan(self, state: GameState, objective: Objective) -> SkillPlan:
        action = (
            MacroAction(MacroActionKind.CONFIRM)
            if state.mode in {GameMode.DIALOGUE, GameMode.SCRIPTED_EVENT}
            else MacroAction(MacroActionKind.INTERACT)
        )
        return SkillPlan(
            objective_id=objective.id,
            specialist=self.specialist,
            outcome=SkillOutcome.IN_PROGRESS,
            actions=(action,),
            expected_facts=objective.completion_facts,
            rationale="Advance the bounded interaction and verify its semantic result.",
        )


@dataclass(frozen=True, slots=True)
class MenuSpecialist:
    specialist: Specialist = Specialist.MENU

    def plan(self, state: GameState, objective: Objective) -> SkillPlan:
        action = (
            MacroAction(MacroActionKind.CONFIRM)
            if state.mode is GameMode.MENU
            else MacroAction(MacroActionKind.OPEN_MENU)
        )
        return SkillPlan(
            objective_id=objective.id,
            specialist=self.specialist,
            outcome=SkillOutcome.IN_PROGRESS,
            actions=(action,),
            expected_facts=objective.completion_facts,
            rationale="Enter or advance the declared menu workflow.",
        )


class BattlePolicy(Protocol):
    def choose_action(self, state: GameState, objective: Objective) -> MacroAction: ...


@dataclass(frozen=True, slots=True)
class FirstLegalMovePolicy:
    """Conservative foundation policy; replaced after battle-state integration."""

    move_slot: int = 1

    def choose_action(self, state: GameState, objective: Objective) -> MacroAction:
        if state.mode is not GameMode.BATTLE:
            raise ValueError("battle policy requires battle mode")
        return MacroAction(MacroActionKind.BATTLE_MOVE, self.move_slot)


@dataclass(frozen=True, slots=True)
class BattleSpecialist:
    policy: BattlePolicy
    specialist: Specialist = Specialist.BATTLE

    def plan(self, state: GameState, objective: Objective) -> SkillPlan:
        if state.mode is not GameMode.BATTLE:
            return SkillPlan(
                objective_id=objective.id,
                specialist=self.specialist,
                outcome=SkillOutcome.REPLAN,
                expected_facts=objective.completion_facts,
                rationale="Battle objective is active, but verified state is not in battle mode.",
            )
        return SkillPlan(
            objective_id=objective.id,
            specialist=self.specialist,
            outcome=SkillOutcome.IN_PROGRESS,
            actions=(self.policy.choose_action(state, objective),),
            expected_facts=objective.completion_facts,
            rationale="Apply the current disclosed battle policy.",
        )


@dataclass(frozen=True, slots=True)
class BootstrapSpecialist:
    specialist: Specialist = Specialist.BOOTSTRAP

    def plan(self, state: GameState, objective: Objective) -> SkillPlan:
        return SkillPlan(
            objective_id=objective.id,
            specialist=self.specialist,
            outcome=SkillOutcome.IN_PROGRESS,
            actions=(MacroAction(MacroActionKind.CONFIRM),),
            expected_facts=objective.completion_facts,
            rationale="Advance from verified power-on toward the first playable state.",
        )


@dataclass(frozen=True, slots=True)
class VerificationSpecialist:
    specialist: Specialist = Specialist.VERIFICATION

    def plan(self, state: GameState, objective: Objective) -> SkillPlan:
        return SkillPlan(
            objective_id=objective.id,
            specialist=self.specialist,
            outcome=SkillOutcome.IN_PROGRESS,
            actions=(MacroAction(MacroActionKind.WAIT),),
            expected_facts=objective.completion_facts,
            rationale="Wait for independent completion evidence; do not infer success.",
        )


@dataclass(frozen=True, slots=True)
class RecoverySpecialist:
    specialist: Specialist = Specialist.RECOVERY

    def plan(self, state: GameState, objective: Objective) -> SkillPlan:
        return SkillPlan(
            objective_id=objective.id,
            specialist=self.specialist,
            outcome=SkillOutcome.REPLAN,
            actions=(MacroAction(MacroActionKind.RECOVER),),
            expected_facts=objective.completion_facts,
            rationale="Request a bounded recovery plan from fresh verified state.",
        )
