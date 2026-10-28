"""Opt-in strategic input, not a policy, fit, or permission to play.

Recent outcomes are observations, never labels for unexecuted alternatives.
Legacy goal models cannot score this schema implicitly. Existing goal bindings
remain the sole execution boundary; this module only prepares/scores inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from math import isfinite
from statistics import median

import numpy as np

from .goal_manager import (
    GoalAvailability,
    GoalKind,
    GoalOpportunity,
    GoalSituation,
    GoalUnavailableReason,
)
from .goal_manager_model import GOAL_MANAGER_FEATURE_NAMES, goal_manager_feature_matrix
from .goal_manager_runtime import GoalBindingSet
from .party import StatusCondition
from .party_preparation import (
    PreparationAttempt,
    PreparationMember,
    PreparationPlan,
    PreparationPurpose,
    next_preparation_decision,
)
from .team_training import TeamTrainingDirective

STRATEGY_SCHEMA = "pokemon.core.post-battle-strategy.v1"


class BattleResult(StrEnum):
    WON = "won"
    LOST = "lost"
    UNRESOLVED = "unresolved"


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"invalid {name}")


def _ratio(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid {name}")
    if not isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"invalid {name}")


@dataclass(frozen=True)
class BattleAftermath:
    """Identity-free facts from one completed or interrupted observed battle."""

    result: BattleResult
    opponent_levels: tuple[int, ...]  # Once per observed opponent, not per turn.
    opponent_count: int
    opponents_defeated: int
    engaged_levels: tuple[int, ...]  # First observed active level per own member.
    party_size: int
    terminal_fainted_count: int
    terminal_hp_fraction: float
    pp_spent_fraction: float
    exhausted_move_fraction: float
    voluntary_switch_fraction: float
    suppressed_attack_fraction: float
    last_opponent_hp_fraction: float | None

    def __post_init__(self):
        if not isinstance(self.result, BattleResult):
            raise ValueError("explicit battle result required")
        _integer(self.opponent_count, 1, 6, "opponent count")
        _integer(self.party_size, 1, 6, "party size")
        for values, maximum in (
            (self.opponent_levels, self.opponent_count),
            (self.engaged_levels, self.party_size),
        ):
            if not isinstance(values, tuple) or not 1 <= len(values) <= maximum:
                raise ValueError("observed level coverage required")
            for value in values:
                _integer(value, 1, 100, "observed level")
        # Trainer switching can hide a member's level at policy boundaries while
        # referee roster-HP transitions still prove its knockout. Keep level
        # coverage partial; never invent a level merely to count a verified faint.
        _integer(self.opponents_defeated, 0, self.opponent_count, "defeated count")
        _integer(self.terminal_fainted_count, 0, self.party_size, "fainted count")
        for name in (
            "terminal_hp_fraction",
            "pp_spent_fraction",
            "exhausted_move_fraction",
            "voluntary_switch_fraction",
            "suppressed_attack_fraction",
        ):
            _ratio(getattr(self, name), name)
        if self.last_opponent_hp_fraction is not None:
            _ratio(self.last_opponent_hp_fraction, "last opponent health")
        if self.result is BattleResult.WON and self.opponents_defeated != self.opponent_count:
            raise ValueError("victory requires complete defeated roster")
        if self.result is BattleResult.LOST and (
            self.terminal_fainted_count != self.party_size or self.terminal_hp_fraction != 0
        ):
            raise ValueError("loss requires defeated party")
        if (self.terminal_fainted_count == self.party_size) != (self.terminal_hp_fraction == 0):
            raise ValueError("terminal health and faints conflict")


@dataclass(frozen=True)
class PostBattleContext:
    """Recent battle remains distinct from current party recovery/level facts."""

    battle: BattleAftermath
    current_combat_levels: tuple[int, ...]
    current_hp_fraction: float
    current_fainted_fraction: float
    current_status_fraction: float
    current_pp_fraction: float | None

    def __post_init__(self):
        if not isinstance(self.battle, BattleAftermath):
            raise TypeError("battle aftermath required")
        if (
            not isinstance(self.current_combat_levels, tuple)
            or not 1 <= len(self.current_combat_levels) <= 6
        ):
            raise ValueError("declared combat levels required")
        for level in self.current_combat_levels:
            _integer(level, 1, 100, "combat level")
        for name in ("current_hp_fraction", "current_fainted_fraction", "current_status_fraction"):
            _ratio(getattr(self, name), name)
        if self.current_pp_fraction is not None:
            _ratio(self.current_pp_fraction, "current PP")
        if (self.current_fainted_fraction == 1) != (self.current_hp_fraction == 0):
            raise ValueError("current health and faints conflict")

    def features(self) -> dict[str, float]:
        b = self.battle
        enemy = median(b.opponent_levels)
        return {
            **{f"recent.{result.value}": float(b.result is result) for result in BattleResult},
            "recent.opposition_coverage": len(b.opponent_levels) / b.opponent_count,
            "recent.defeated_fraction": b.opponents_defeated / b.opponent_count,
            "recent.engaged_level_gap": (enemy - median(b.engaged_levels)) / 100,
            "recent.fainted_fraction": b.terminal_fainted_count / b.party_size,
            "recent.hp_fraction": b.terminal_hp_fraction,
            "recent.pp_spent_fraction": b.pp_spent_fraction,
            "recent.exhausted_move_fraction": b.exhausted_move_fraction,
            "recent.voluntary_switch_fraction": b.voluntary_switch_fraction,
            "recent.suppressed_attack_fraction": b.suppressed_attack_fraction,
            "recent.last_opponent_hp_known": float(b.last_opponent_hp_fraction is not None),
            "recent.last_opponent_hp_fraction": b.last_opponent_hp_fraction or 0.0,
            "current.median_combat_level_gap": (enemy - median(self.current_combat_levels)) / 100,
            "current.lowest_combat_level_gap": (enemy - min(self.current_combat_levels)) / 100,
            "current.combat_level_spread": (
                max(self.current_combat_levels) - min(self.current_combat_levels)
            )
            / 100,
            "current.hp_fraction": self.current_hp_fraction,
            "current.fainted_fraction": self.current_fainted_fraction,
            "current.status_fraction": self.current_status_fraction,
            "current.pp_known": float(self.current_pp_fraction is not None),
            "current.pp_fraction": self.current_pp_fraction or 0.0,
        }


def context_after_recovery(battle: BattleAftermath, members: tuple[PreparationMember, ...]):
    """Roles are disclosed adapter inputs; a new low-level catch is not a target."""
    return PostBattleContext(battle, *current_party_measurements(members))


def current_party_measurements(members: tuple[PreparationMember, ...]):
    """Current facts shared by post-battle and explicitly history-free readiness."""
    if (
        not members
        or len(members) > 6
        or any(not isinstance(m, PreparationMember) for m in members)
    ):
        raise ValueError("observed preparation members required")
    if len({m.specimen_ref for m in members}) != len(members):
        raise ValueError("ambiguous current party")
    combat = tuple(m.observation.level for m in members if m.purpose is PreparationPurpose.COMBAT)
    if not combat:
        raise ValueError("declared combat levels required")
    hp, maximum = sum(m.observation.hp for m in members), sum(m.observation.max_hp for m in members)
    moves = [move for m in members for move in m.observation.known_moves]
    pp_max = sum(move.max_pp or 0 for move in moves)
    pp = (
        sum(move.current_pp for move in moves) / pp_max
        if moves and pp_max and all(move.max_pp is not None for move in moves)
        else None
    )
    return (
        combat,
        hp / maximum if maximum else 0.0,
        sum(m.observation.is_fainted for m in members) / len(members),
        sum(m.observation.status is not StatusCondition.HEALTHY for m in members) / len(members),
        pp,
    )


@dataclass(frozen=True)
class PreparationCostTotals:
    """Whole-envelope costs, including failures without an attempt receipt.

    The caller must authenticate completeness against the retained stage ledger.
    This minimum consistency check cannot discover an omitted stage by itself.
    """

    attempts: int
    actions: int
    frames: int
    seconds: float
    heals: int

    def __post_init__(self):
        for name in ("attempts", "actions", "frames", "heals"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"invalid cumulative {name}")
        if (
            isinstance(self.seconds, bool)
            or not isinstance(self.seconds, (int, float))
            or not isfinite(self.seconds)
            or self.seconds < 0
        ):
            raise ValueError("invalid cumulative seconds")

    def values(self):
        return (self.attempts, self.actions, self.frames, self.seconds, self.heals)


@dataclass(frozen=True)
class PostBattleStrategyMenu:
    """A new model input beside existing private, validated executor bindings."""

    bindings: GoalBindingSet
    situation: GoalSituation
    context: PostBattleContext
    remaining_budget: tuple[float, ...]
    preparation_block_reason: str | None = None

    def __post_init__(self):
        if not isinstance(self.bindings, GoalBindingSet) or not isinstance(
            self.context, PostBattleContext
        ):
            raise TypeError("bound offers and post-battle context required")
        self.bindings.question(self.situation)
        if not isinstance(self.remaining_budget, tuple) or len(self.remaining_budget) != 5:
            raise ValueError("five remaining budget fractions required")
        for value in self.remaining_budget:
            _ratio(value, "remaining budget")

    def policy_dict(self):
        question = self.bindings.question(self.situation)
        return {
            "schema": STRATEGY_SCHEMA,
            "goals": {
                "schema": question.policy_input["schema"],
                "situation": question.situation.policy_dict(),
                "candidates": [o.policy_dict() for o in question.opportunities],
            },
            "aftermath": self.context.features(),
            "preparation_budget_remaining": dict(
                zip(
                    ("attempts", "actions", "frames", "seconds", "heals"),
                    self.remaining_budget,
                    strict=True,
                )
            ),
        }

    def feature_names(self):
        # Common additive context would cancel in a linear candidate comparison.
        # Kind interactions permit learning different responses, without weights
        # or a hand-coded preference for training after a loss.
        names = (
            *self.context.features(),
            "budget.attempts",
            "budget.actions",
            "budget.frames",
            "budget.seconds",
            "budget.heals",
        )
        return (
            *GOAL_MANAGER_FEATURE_NAMES,
            *(f"{kind.value}_x_{name}" for kind in GoalKind for name in names),
        )

    def feature_matrix(self):
        question = self.bindings.question(self.situation)
        common = (*self.context.features().values(), *self.remaining_budget)
        rows = []
        for opportunity in question.opportunities:
            rows.append(
                [
                    value if opportunity.kind is kind else 0.0
                    for kind in GoalKind
                    for value in common
                ]
            )
        return np.column_stack((goal_manager_feature_matrix(question), np.asarray(rows)))

    def diagnostic_scores(self, scorer):
        """No dispatch; reject legacy/incorrect models before asking for scores."""
        if (
            getattr(scorer, "feature_schema_id", None) != STRATEGY_SCHEMA
            or getattr(scorer, "feature_names", None) != self.feature_names()
        ):
            raise ValueError("compatible separately trained strategy scorer required")
        values = np.asarray(scorer.score_features(self.feature_matrix()), dtype=float)
        if values.shape != (len(self.bindings.opportunities),) or not np.all(np.isfinite(values)):
            raise ValueError("invalid strategy scores")
        return tuple(
            float(v) if o.availability is GoalAvailability.AVAILABLE else None
            for v, o in zip(values, self.bindings.opportunities, strict=True)
        )


def build_post_battle_strategy_menu(
    *,
    bindings: GoalBindingSet,
    situation: GoalSituation,
    battle: BattleAftermath,
    plan: PreparationPlan,
    members: tuple[PreparationMember, ...],
    attempts: tuple[PreparationAttempt, ...],
    cumulative_costs: PreparationCostTotals,
    field_ready: bool,
) -> PostBattleStrategyMenu:
    """Mask blocked training; never fabricate a binding or refill its budget.

    Callers supply an authenticated terminal, its battle record and current
    provider offers. This composition check is NOT native provider qualification.
    Existing preparation rules check eligibility; this does not dispatch their
    suggested trainee or replace a model choice. Whole-envelope costs are required
    separately because some failed stages may lack a completed attempt receipt.
    """
    if field_ready is not True:
        raise ValueError("settled input-ready field required")
    if not isinstance(bindings, GoalBindingSet):
        raise TypeError("actual goal binding set required")
    if not isinstance(attempts, tuple) or any(
        not isinstance(a, PreparationAttempt) for a in attempts
    ):
        raise ValueError("retained preparation attempt ledger required")
    if not isinstance(cumulative_costs, PreparationCostTotals):
        raise TypeError("whole-envelope preparation costs required")
    receipt_costs = (
        len(attempts),
        sum(a.actions for a in attempts),
        sum(a.frames for a in attempts),
        sum(a.elapsed_seconds for a in attempts),
        sum(a.heals for a in attempts),
    )
    spent = cumulative_costs.values()
    if any(total < known for total, known in zip(spent, receipt_costs, strict=True)):
        raise ValueError("cumulative costs omit retained attempt costs")
    budget = plan.budget
    maxima = (
        budget.max_attempts,
        budget.max_actions,
        budget.max_frames,
        budget.max_seconds,
        budget.max_heals,
    )
    exhausted = any(used >= limit for used, limit in zip(spent, maxima, strict=True))
    decision = next_preparation_decision(plan, members, attempts)
    allowed = decision.directive in {
        TeamTrainingDirective.TRAIN_MEMBER,
        TeamTrainingDirective.SWITCH_TRAINEE,
    }
    # All members matter to an excursion, not just the rule-selected trainee.
    needs_recovery = any(
        m.observation.is_fainted or m.observation.status is not StatusCondition.HEALTHY
        for m in members
    )
    if needs_recovery or exhausted:
        allowed = False
    reason = None if allowed else ("party recovery required" if needs_recovery else decision.reason)
    if exhausted:
        reason = "cumulative preparation budget exhausted"
    if not allowed:
        opportunities = tuple(
            GoalOpportunity(
                o.binding_ref,
                o.kind,
                GoalAvailability.UNAVAILABLE,
                unavailable_reason=GoalUnavailableReason.TEMPORARILY_BLOCKED,
            )
            if o.kind is GoalKind.DEVELOP_TEAM
            else o
            for o in bindings.opportunities
        )
        bindings = replace(
            bindings,
            opportunities=opportunities,
            bindings=tuple(b for b in bindings.bindings if b.kind is not GoalKind.DEVELOP_TEAM),
        )
    remaining = tuple(max(0.0, 1 - used / limit) for used, limit in zip(spent, maxima, strict=True))
    return PostBattleStrategyMenu(
        bindings,
        situation,
        context_after_recovery(battle, members),
        remaining,
        reason,
    )
