"""Game-neutral policy primitives for bounded experience training.

The policy describes *why* to fight, heal, or stop.  Individual game adapters
remain responsible for navigation, battle menus, and reaching a healer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TrainingDirective(StrEnum):
    """One semantic action requested by a training policy."""

    SEEK_ENCOUNTER = "seek_encounter"
    FIGHT = "fight"
    FLEE = "flee"
    RETURN_TO_HEAL = "return_to_heal"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class TrainingPolicy:
    """Reusable stop, safety, and opponent-selection rules."""

    target_level: int
    preferred_move_slots: tuple[int, ...]
    retreat_hp_ratio: float = 0.45
    reserve_total_pp: int = 2
    max_enemy_level_delta: int = 4
    max_battles: int = 80
    max_steps: int = 6_000
    max_healing_trips: int = 12

    def __post_init__(self) -> None:
        if not 2 <= self.target_level <= 100:
            raise ValueError("target_level must be between 2 and 100")
        if not self.preferred_move_slots or any(
            type(slot) is not int or not 1 <= slot <= 4
            for slot in self.preferred_move_slots
        ):
            raise ValueError("preferred_move_slots must contain one-based move slots")
        if len(set(self.preferred_move_slots)) != len(self.preferred_move_slots):
            raise ValueError("preferred_move_slots cannot contain duplicates")
        if not 0 < self.retreat_hp_ratio < 1:
            raise ValueError("retreat_hp_ratio must be between zero and one")
        for name in (
            "reserve_total_pp",
            "max_enemy_level_delta",
            "max_battles",
            "max_steps",
            "max_healing_trips",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class TrainingObservation:
    """Minimal cross-game state needed by the training policy."""

    level: int
    hp: int
    max_hp: int
    pp: tuple[int, ...]
    in_battle: bool
    status: int = 0
    enemy_level: int | None = None
    battles_completed: int = 0
    steps_taken: int = 0
    healing_trips: int = 0

    @property
    def hp_ratio(self) -> float:
        return self.hp / self.max_hp if self.max_hp > 0 else 0.0


@dataclass(frozen=True, slots=True)
class TrainingReport:
    """Portable receipt proving a bounded training block's outcome."""

    area_id: str
    starting_level: int
    target_level: int
    final_level: int
    battles_won: int
    battles_fled: int
    steps_taken: int
    healing_trips: int
    fainted: bool

    @property
    def passed(self) -> bool:
        return (
            self.final_level >= self.target_level
            and self.battles_won > 0
            and not self.fainted
        )


def choose_training_directive(
    observation: TrainingObservation,
    policy: TrainingPolicy,
) -> TrainingDirective:
    """Choose the next semantic training action from portable state."""

    if observation.level >= policy.target_level:
        return TrainingDirective.STOP
    if observation.battles_completed >= policy.max_battles:
        return TrainingDirective.STOP
    if observation.steps_taken >= policy.max_steps:
        return TrainingDirective.STOP

    usable_pp = sum(
        observation.pp[slot - 1]
        for slot in policy.preferred_move_slots
        if slot <= len(observation.pp)
    )
    unsafe = (
        observation.hp_ratio <= policy.retreat_hp_ratio
        or observation.status != 0
        or usable_pp <= policy.reserve_total_pp
    )
    if observation.in_battle:
        enemy_too_strong = (
            observation.enemy_level is None
            or observation.enemy_level
            > observation.level + policy.max_enemy_level_delta
        )
        return (
            TrainingDirective.FLEE
            if unsafe or enemy_too_strong
            else TrainingDirective.FIGHT
        )
    if unsafe:
        return TrainingDirective.RETURN_TO_HEAL
    return TrainingDirective.SEEK_ENCOUNTER


def choose_training_move_slot(
    pp: tuple[int, ...],
    preferred_move_slots: tuple[int, ...],
) -> int:
    """Return the first preferred move with current PP."""

    for slot in preferred_move_slots:
        if slot <= len(pp) and pp[slot - 1] > 0:
            return slot
    raise ValueError("training policy has no usable preferred move")
