"""Game-neutral capture policy backing the ``RECRUIT_MEMBER`` directive.

:func:`~pokemon_red_completion.team_training.plan_team_training` can ask for a
new party member, but it has no mechanism for acquiring one.  This module
supplies that mechanism as reusable Pokémon concepts: weaken the target, apply a
status if the game offers one, then spend a bounded number of balls.

The rules are expressed in health ratios, ball counts, and party room—never in
map tiles or item identifiers—so the same policy applies to any mainline title.
Which ball, which weakening move, and how to reach the encounter remain the
adapter's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .party import MAX_LEVEL, MIN_LEVEL, PartyMemberObservation, StatusCondition


class CaptureDirective(StrEnum):
    """One semantic action requested by the capture policy."""

    WEAKEN_TARGET = "weaken_target"
    INFLICT_STATUS = "inflict_status"
    THROW_BALL = "throw_ball"
    RESTORE_CATCHER = "restore_catcher"
    ABANDON = "abandon"


@dataclass(frozen=True, slots=True)
class CapturePolicy:
    """Bounded weaken-then-throw rules for acquiring a party member."""

    throw_at_or_below_hp_ratio: float = 0.20
    prefer_status_first: bool = True
    max_throws: int = 20
    retreat_hp_ratio: float = 0.35

    def __post_init__(self) -> None:
        if not 0 < self.throw_at_or_below_hp_ratio < 1:
            raise ValueError("throw_at_or_below_hp_ratio must be between zero and one")
        if not 0 < self.retreat_hp_ratio < 1:
            raise ValueError("retreat_hp_ratio must be between zero and one")
        if type(self.max_throws) is not int or self.max_throws <= 0:
            raise ValueError("max_throws must be a positive integer")


@dataclass(frozen=True, slots=True)
class CaptureObservation:
    """Everything the capture policy needs about one live encounter."""

    target_species_id: int
    target_level: int
    target_hp: int
    target_max_hp: int
    catcher: PartyMemberObservation
    balls_available: int
    party_has_room: bool
    storage_has_room: bool = False
    target_status: StatusCondition = StatusCondition.HEALTHY
    throws_used: int = 0

    def __post_init__(self) -> None:
        if type(self.target_species_id) is not int or self.target_species_id <= 0:
            raise ValueError("target_species_id must be a positive integer")
        if type(self.target_level) is not int or not MIN_LEVEL <= self.target_level <= MAX_LEVEL:
            raise ValueError(f"target_level must be between {MIN_LEVEL} and {MAX_LEVEL}")
        if type(self.target_max_hp) is not int or self.target_max_hp <= 0:
            raise ValueError("target_max_hp must be a positive integer")
        if type(self.target_hp) is not int or not 0 <= self.target_hp <= self.target_max_hp:
            raise ValueError("target_hp must be between zero and target_max_hp")
        if not isinstance(self.catcher, PartyMemberObservation):
            raise TypeError("catcher must be a PartyMemberObservation")
        if not isinstance(self.target_status, StatusCondition):
            raise TypeError("target_status must be a StatusCondition")
        for name in ("party_has_room", "storage_has_room"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a bool")
        for name in ("balls_available", "throws_used"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    @property
    def target_hp_ratio(self) -> float:
        """The target's remaining health as a fraction of its maximum."""

        return self.target_hp / self.target_max_hp if self.target_max_hp > 0 else 0.0

    @property
    def target_is_fainted(self) -> bool:
        """Whether the encounter has already been lost to a knockout."""

        return self.target_hp == 0


@dataclass(frozen=True, slots=True)
class CaptureDecision:
    """One capture directive plus the reasoning that produced it."""

    directive: CaptureDirective
    reason: str

    @property
    def is_terminal(self) -> bool:
        """Whether the encounter cannot continue."""

        return self.directive is CaptureDirective.ABANDON


def plan_capture(
    observation: CaptureObservation,
    policy: CapturePolicy,
) -> CaptureDecision:
    """Choose the next semantic action for a bounded capture attempt.

    A knocked-out target, a full party, an empty bag, and an exhausted throw
    budget all end the attempt rather than looping.  The catcher's own safety is
    checked before any further damage is dealt, so a capture cannot cascade into
    a blackout.
    """

    if observation.target_is_fainted:
        return CaptureDecision(
            CaptureDirective.ABANDON,
            "target fainted before it could be caught",
        )
    if not observation.party_has_room and not observation.storage_has_room:
        return CaptureDecision(
            CaptureDirective.ABANDON,
            "no open slot exists in either the party or verified storage",
        )
    if observation.balls_available <= 0:
        return CaptureDecision(CaptureDirective.ABANDON, "no balls remain")
    if observation.throws_used >= policy.max_throws:
        return CaptureDecision(
            CaptureDirective.ABANDON,
            f"throw budget of {policy.max_throws} exhausted",
        )

    catcher = observation.catcher
    if (
        catcher.is_fainted
        or catcher.hp_ratio <= policy.retreat_hp_ratio
        or catcher.status is not StatusCondition.HEALTHY
        or not catcher.usable_moves
    ):
        return CaptureDecision(
            CaptureDirective.RESTORE_CATCHER,
            f"slot {catcher.slot} cannot safely continue the encounter",
        )

    if observation.target_hp_ratio > policy.throw_at_or_below_hp_ratio:
        return CaptureDecision(
            CaptureDirective.WEAKEN_TARGET,
            f"target is above {policy.throw_at_or_below_hp_ratio:.0%} health",
        )
    if policy.prefer_status_first and observation.target_status is StatusCondition.HEALTHY:
        return CaptureDecision(
            CaptureDirective.INFLICT_STATUS,
            "target is weakened but carries no status",
        )
    return CaptureDecision(
        CaptureDirective.THROW_BALL,
        f"target is at {observation.target_hp_ratio:.0%} health with "
        f"{observation.balls_available} ball(s) in reserve",
    )


def balls_required_estimate(policy: CapturePolicy, safety_factor: int = 2) -> int:
    """A conservative reserve to carry into a bounded capture attempt.

    This is a planning aid for the shopping step, not a probability model: it
    scales the throw budget so a single unlucky sequence does not strand the
    route without balls.
    """

    if type(safety_factor) is not int or safety_factor <= 0:
        raise ValueError("safety_factor must be a positive integer")
    return policy.max_throws * safety_factor
