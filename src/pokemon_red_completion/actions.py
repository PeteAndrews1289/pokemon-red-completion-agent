from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pokemon_red_completion.quest import Specialist


class MacroActionKind(StrEnum):
    MOVE = "move"
    INTERACT = "interact"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    OPEN_MENU = "open_menu"
    WAIT = "wait"
    BATTLE_MOVE = "battle_move"
    SWITCH_PARTY = "switch_party"
    USE_ITEM = "use_item"
    RECOVER = "recover"


@dataclass(frozen=True, slots=True)
class MacroAction:
    """A semantic action that a frame-safe executor will later translate to buttons."""

    kind: MacroActionKind
    value: str | int | None = None
    repeat: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.kind, MacroActionKind):
            raise TypeError("kind must be a MacroActionKind")
        if isinstance(self.value, bool) or not isinstance(self.value, (str, int, type(None))):
            raise TypeError("value must be a string, integer, or None")
        if not isinstance(self.repeat, int) or isinstance(self.repeat, bool) or self.repeat <= 0:
            raise ValueError("repeat must be a positive integer")


class SkillOutcome(StrEnum):
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    RETRY = "retry"
    REPLAN = "replan"
    FATAL = "fatal"


@dataclass(frozen=True, slots=True)
class SkillPlan:
    objective_id: str
    specialist: Specialist
    outcome: SkillOutcome
    actions: tuple[MacroAction, ...] = ()
    expected_facts: frozenset[str] = field(default_factory=frozenset)
    max_executor_steps: int = 1
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.objective_id:
            raise ValueError("objective_id must be non-empty")
        if not isinstance(self.specialist, Specialist):
            raise TypeError("specialist must be a Specialist")
        if not isinstance(self.outcome, SkillOutcome):
            raise TypeError("outcome must be a SkillOutcome")
        if (
            not isinstance(self.max_executor_steps, int)
            or isinstance(self.max_executor_steps, bool)
            or self.max_executor_steps <= 0
        ):
            raise ValueError("max_executor_steps must be a positive integer")
        if self.outcome is SkillOutcome.IN_PROGRESS and not self.actions:
            raise ValueError("an in-progress plan must contain at least one action")
