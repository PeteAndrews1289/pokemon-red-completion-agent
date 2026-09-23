"""Role-aware, bounded preparation above the existing training executors.

This is a disclosed teacher planner, not a learned policy or battle readiness
qualification. Adapters supply stable specimen references (never party slots),
observed opposition and actual execution receipts. No game inputs occur here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from math import ceil, isfinite
from statistics import median

from .party import PartyMemberObservation, StatusCondition
from .team_training import LevelParityContract, TeamTrainingDecision, TeamTrainingDirective


class PreparationPurpose(StrEnum):
    COMBAT = "combat"
    FIELD_UTILITY = "field_utility"
    COLLECTION = "collection_evolution"
    UNDECIDED = "undecided"


def _integer(value: int, low: int, high: int, name: str) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"invalid {name}")


@dataclass(frozen=True)
class PreparationMember:
    specimen_ref: str
    observation: PartyMemberObservation
    purpose: PreparationPurpose = PreparationPurpose.UNDECIDED
    purpose_reason: str = ""
    milestone_level: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.specimen_ref, str) or not self.specimen_ref.strip():
            raise ValueError("stable specimen reference required")
        if not isinstance(self.observation, PartyMemberObservation):
            raise ValueError("party observation required")
        if not isinstance(self.purpose, PreparationPurpose):
            raise ValueError("typed preparation purpose required")
        if self.purpose != PreparationPurpose.UNDECIDED and not self.purpose_reason.strip():
            raise ValueError("an explicit purpose needs a reason")
        if self.milestone_level is not None:
            _integer(self.milestone_level, 1, 100, "milestone")
            if self.purpose != PreparationPurpose.COMBAT:
                raise ValueError("combat preparation cannot assign noncombat milestones")


@dataclass(frozen=True)
class ObservedOpponent:
    encounter_ref: str
    position: int
    level: int

    def __post_init__(self) -> None:
        if not isinstance(self.encounter_ref, str) or not self.encounter_ref.strip():
            raise ValueError("observed encounter reference required")
        _integer(self.position, 1, 6, "enemy position")
        _integer(self.level, 1, 100, "enemy level")


@dataclass(frozen=True)
class PreparationBudget:
    max_attempts: int = 12
    max_actions: int = 6000
    max_frames: int = 1_000_000
    max_seconds: int = 1800
    max_heals: int = 4
    max_no_progress: int = 3

    def __post_init__(self) -> None:
        for value in (
            self.max_attempts,
            self.max_actions,
            self.max_frames,
            self.max_seconds,
            self.max_heals,
            self.max_no_progress,
        ):
            _integer(value, 1, 100_000_000, "preparation budget")


def _members(members: tuple[PreparationMember, ...]) -> dict[str, PreparationMember]:
    if not 1 <= len(members) <= 6:
        raise ValueError("preparation requires one to six observed members")
    if len({m.specimen_ref for m in members}) != len(members):
        raise ValueError("ambiguous specimen identity")
    if sorted(m.observation.slot for m in members) != list(range(1, len(members) + 1)):
        raise ValueError("party slots must be unique and contiguous")
    return {m.specimen_ref: m for m in members}


@dataclass(frozen=True)
class PreparationPlan:
    roster: tuple[PreparationMember, ...]
    opposition_level: int | None
    observed_opponents: int
    targets: tuple[tuple[str, int], ...]
    reason: str
    budget: PreparationBudget

    def __post_init__(self) -> None:
        roster = _members(self.roster)
        if not isinstance(self.budget, PreparationBudget):
            raise ValueError("typed preparation budget required")
        _integer(self.observed_opponents, 0, 100_000_000, "observed opponent count")
        if self.opposition_level is None:
            if self.observed_opponents or self.targets:
                raise ValueError("targets require observed opposition")
        else:
            _integer(self.opposition_level, 1, 100, "opposition reference")
            if not self.observed_opponents:
                raise ValueError("opposition reference lacks observations")
        if len(dict(self.targets)) != len(self.targets):
            raise ValueError("duplicate preparation target")
        for ref, level in self.targets:
            if ref not in roster or roster[ref].purpose != PreparationPurpose.COMBAT:
                raise ValueError("target must be a declared combat specimen")
            _integer(
                level, roster[ref].observation.level + 1, self.opposition_level or 0, "target level"
            )
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("preparation reason required")

    @property
    def combat_median(self) -> float | None:
        levels = [
            m.observation.level for m in self.roster if m.purpose == PreparationPurpose.COMBAT
        ]
        return float(median(levels)) if levels else None

    @property
    def combat_spread(self) -> int | None:
        levels = [
            m.observation.level for m in self.roster if m.purpose == PreparationPurpose.COMBAT
        ]
        return max(levels) - min(levels) if levels else None


def build_preparation_plan(
    members: tuple[PreparationMember, ...],
    opponents: tuple[ObservedOpponent, ...],
    *,
    trigger_behind: int = 5,
    target_behind: int = 3,
    budget: PreparationBudget | None = None,
) -> PreparationPlan:
    """Freeze evidence, roles and targets; an overleveled carry raises no target."""
    _members(members)
    budget = budget if budget is not None else PreparationBudget()
    if not isinstance(budget, PreparationBudget):
        raise ValueError("typed preparation budget required")
    _integer(trigger_behind, 0, 99, "trigger tolerance")
    _integer(target_behind, 0, trigger_behind, "target tolerance")
    seen: dict[tuple[str, int], int] = {}
    for enemy in opponents:
        key = (enemy.encounter_ref, enemy.position)
        if key in seen and seen[key] != enemy.level:
            raise ValueError("conflicting observation of the same enemy")
        seen[key] = enemy.level
    opposition = ceil(median(seen.values())) if seen else None
    targets: tuple[tuple[str, int], ...] = ()
    combat = tuple(m for m in members if m.purpose == PreparationPurpose.COMBAT)
    reason = "no declared combat members" if not combat else "opposition evidence required"
    if combat and opposition is not None:
        if any(m.milestone_level is not None and m.milestone_level > opposition for m in combat):
            raise ValueError("milestone exceeds observed opposition; reassess separately")
        floor = LevelParityContract(trigger_behind).required_level(opposition)
        triggered = any(m.observation.level < floor for m in combat)
        target = LevelParityContract(target_behind).required_level(opposition)
        targets = tuple(
            (
                m.specimen_ref,
                max(
                    target if triggered else m.observation.level,
                    m.milestone_level or m.observation.level,
                ),
            )
            for m in combat
            if (triggered and m.observation.level < target)
            or (m.milestone_level is not None and m.observation.level < m.milestone_level)
        )
        reason = "combat preparation needed" if targets else "level preparation not needed"
    return PreparationPlan(members, opposition, len(seen), targets, reason, budget)


@dataclass(frozen=True)
class PreparationAttempt:
    """Actual cost of one bounded trainee attempt, including unsuccessful ones.

    The executor must enforce the remaining budget DURING the attempt and retain
    a receipt on failure. Accounting here cannot interrupt an emulator by itself.
    """

    specimen_ref: str
    level_before: int
    level_after: int
    xp_gained: int
    actions: int
    frames: int
    elapsed_seconds: float
    heals: int = 0
    failed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.specimen_ref, str) or not self.specimen_ref.strip():
            raise ValueError("attempt specimen reference required")
        _integer(self.level_before, 1, 100, "starting level")
        _integer(self.level_after, self.level_before, 100, "ending level")
        for value in (self.xp_gained, self.actions, self.frames, self.heals):
            _integer(value, 0, 100_000_000, "attempt cost")
        if (
            isinstance(self.elapsed_seconds, bool)
            or not isinstance(self.elapsed_seconds, (float, int))
            or not isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise ValueError("invalid elapsed time")
        if type(self.failed) is not bool:
            raise ValueError("failed must be boolean")


def next_preparation_decision(
    plan: PreparationPlan,
    members: tuple[PreparationMember, ...],
    attempts: tuple[PreparationAttempt, ...] = (),
) -> TeamTrainingDecision:
    """Rotate attempts, recover normally, and never erase costs after failure."""
    live = _members(members)
    expected = {m.specimen_ref: m for m in plan.roster}
    if live.keys() != expected.keys():
        raise ValueError("roster changed; retain costs and explicitly reassess")
    for ref, member in live.items():
        old = expected[ref]
        if (member.purpose, member.purpose_reason, member.milestone_level) != (
            old.purpose,
            old.purpose_reason,
            old.milestone_level,
        ):
            raise ValueError("preparation role or milestone changed")
    targets = dict(plan.targets)
    if any(a.specimen_ref not in targets for a in attempts):
        raise ValueError("attempt was not part of the frozen preparation plan")
    budget = plan.budget
    limits = (
        (len(attempts), budget.max_attempts, "attempt budget"),
        (sum(a.actions for a in attempts), budget.max_actions, "action budget"),
        (sum(a.frames for a in attempts), budget.max_frames, "frame budget"),
        (sum(a.elapsed_seconds for a in attempts), budget.max_seconds, "time budget"),
        (sum(a.heals for a in attempts), budget.max_heals, "healing budget"),
    )
    for spent, maximum, reason in limits:
        if spent >= maximum:
            return TeamTrainingDecision(TeamTrainingDirective.STOP, reason)
    if not targets:
        return TeamTrainingDecision(TeamTrainingDirective.STOP, plan.reason)
    deficient = [live[ref] for ref, target in plan.targets if live[ref].observation.level < target]
    if not deficient:
        return TeamTrainingDecision(TeamTrainingDirective.STOP, "all preparation targets reached")
    for member in deficient:
        history = [a for a in attempts if a.specimen_ref == member.specimen_ref]
        tail = history[-budget.max_no_progress :]
        if len(tail) == budget.max_no_progress and all(
            a.xp_gained == 0 and a.level_after == a.level_before for a in tail
        ):
            return TeamTrainingDecision(
                TeamTrainingDirective.STOP, "no XP progress; reassess training opportunity"
            )
    if any(m.observation.is_fainted for m in members):
        return TeamTrainingDecision(TeamTrainingDirective.RESTORE_TEAM, "recover fainted party")
    counts = Counter(a.specimen_ref for a in attempts)
    trainee = min(
        deficient,
        key=lambda m: (
            counts[m.specimen_ref],
            m.observation.level - targets[m.specimen_ref],
            tuple(targets).index(m.specimen_ref),
        ),
    )
    obs = trainee.observation
    if (
        obs.hp_ratio < 0.45
        or obs.status != StatusCondition.HEALTHY
        or not obs.can_battle
        or obs.total_pp <= 2
    ):
        return TeamTrainingDecision(
            TeamTrainingDirective.RESTORE_TEAM,
            "restore selected combat trainee",
            target_slot=obs.slot,
        )
    return TeamTrainingDecision(
        TeamTrainingDirective.TRAIN_MEMBER
        if obs.slot == 1
        else TeamTrainingDirective.SWITCH_TRAINEE,
        "teacher rotation toward frozen observed-opposition target",
        target_slot=obs.slot,
    )
