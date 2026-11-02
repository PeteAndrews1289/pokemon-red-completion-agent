"""Explicit support boundaries, never fabricated two-option model questions."""

import re
from dataclasses import dataclass

from .goal_manager import GoalKind
from .goal_manager_runtime import GoalBindingSet
from .player_readiness import PlayerReadiness
from .provenance import canonical_sha256
from .red_live_option_menu import RedLiveOptionSelectionMode


@dataclass(frozen=True)
class PlayerBudgetStop:
    """A remaining mechanic needs exhausted experimental allowance, not a retry."""

    state_sha256: str
    reason: str = "restoration_budget"

    def __post_init__(self):
        if (not isinstance(self.state_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.state_sha256) is None
            or type(self.reason) is not str
            or self.reason not in {"restoration_budget", "settlement_budget"}):
            raise ValueError("player budget stop needs an authenticated exhaustion boundary")

    def public_dict(self):
        return dict(schema="pokemon.red.player-budget-stop.v1", reason=self.reason,
                    state_sha256=self.state_sha256, model_queries=0,
                    curriculum_complete=False, full_game_completion=False)


@dataclass(frozen=True)
class RedPlayerSupport:
    bindings: GoalBindingSet
    readiness: PlayerReadiness

    def __post_init__(self):
        control = [b for b in self.bindings.bindings if b.kind is GoalKind.RECOVER_CONTROL]
        if not control and len(self.bindings.bindings) != 1:
            raise ValueError("support requires mandatory control recovery or one executable goal")
        if len(control) > 1 or not isinstance(self.readiness, PlayerReadiness):
            raise ValueError("support boundary is ambiguous")

    @property
    def binding(self):
        return next(
            (b for b in self.bindings.bindings if b.kind is GoalKind.RECOVER_CONTROL),
            self.bindings.bindings[0],
        )

    @property
    def support_role(self):
        return (
            "deterministic_control_recovery"
            if self.binding.kind is GoalKind.RECOVER_CONTROL
            else "forced_singleton"
        )

    def public_dict(self):
        return dict(
            schema="pokemon.red.player-support.v1",
            support_role=self.support_role,
            selected_kind=self.binding.kind.value,
            readiness=self.readiness.public_dict(),
            available_goal_kinds=[b.kind.value for b in self.bindings.bindings],
            model_queries=0,
            comparative_choice=False,
        )

    @property
    def policy_sha256(self):
        return canonical_sha256(self.public_dict())


@dataclass(frozen=True)
class RedPlayerSupportChoice:
    options: RedPlayerSupport

    @property
    def selected_binding(self):
        return self.options.binding

    @property
    def mode(self):
        return RedLiveOptionSelectionMode.DETERMINISTIC_SAFETY

    def public_dict(self):
        return {**self.options.public_dict(), "menu_sha256": self.options.policy_sha256}
