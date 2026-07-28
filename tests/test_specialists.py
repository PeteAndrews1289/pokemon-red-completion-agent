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
from pokemon_red_completion.navigation import Coordinate, GridMap
from pokemon_red_completion.quest import Objective, Specialist
from pokemon_red_completion.specialists import (
    BattleSpecialist,
    FirstLegalMovePolicy,
    GridNavigationSpecialist,
    InteractionSpecialist,
    NavigationContext,
    SpecialistRegistry,
    SpecialistRegistryError,
)


def _objective(specialist: Specialist) -> Objective:
    return Objective(
        id="target",
        title="Target",
        completion_facts=frozenset({"done:target"}),
        specialist=specialist,
    )


@dataclass(frozen=True)
class StaticNavigationContext:
    context: NavigationContext

    def context_for(self, state: GameState, objective: Objective) -> NavigationContext:
        return self.context


def test_macro_action_and_plan_validate_bounded_inputs() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        MacroAction(MacroActionKind.WAIT, repeat=0)
    with pytest.raises(ValueError, match="must contain"):
        SkillPlan(
            objective_id="target",
            specialist=Specialist.INTERACTION,
            outcome=SkillOutcome.IN_PROGRESS,
        )


def test_registry_rejects_duplicate_and_missing_specialists() -> None:
    planner = InteractionSpecialist()
    with pytest.raises(SpecialistRegistryError, match="duplicate"):
        SpecialistRegistry((planner, planner))

    registry = SpecialistRegistry((planner,))
    with pytest.raises(SpecialistRegistryError, match="no planner"):
        registry.require(Specialist.BATTLE)


def test_navigation_specialist_turns_shortest_path_into_macro_actions() -> None:
    provider = StaticNavigationContext(
        NavigationContext(
            grid=GridMap(width=3, height=2, blocked=frozenset({Coordinate(1, 0)})),
            start=Coordinate(0, 0),
            goal=Coordinate(2, 0),
        )
    )
    specialist = GridNavigationSpecialist(provider)

    plan = specialist.plan(
        GameState(GameMode.OVERWORLD),
        _objective(Specialist.NAVIGATION),
    )

    assert plan.outcome is SkillOutcome.IN_PROGRESS
    assert tuple(action.kind for action in plan.actions) == (
        MacroActionKind.MOVE,
        MacroActionKind.MOVE,
        MacroActionKind.MOVE,
        MacroActionKind.MOVE,
    )
    assert plan.max_executor_steps == 4


def test_battle_specialist_fails_closed_outside_battle() -> None:
    specialist = BattleSpecialist(FirstLegalMovePolicy(move_slot=2))
    objective = _objective(Specialist.BATTLE)

    outside = specialist.plan(GameState(GameMode.OVERWORLD), objective)
    inside = specialist.plan(GameState(GameMode.BATTLE), objective)

    assert outside.outcome is SkillOutcome.REPLAN
    assert inside.actions == (MacroAction(MacroActionKind.BATTLE_MOVE, 2),)
