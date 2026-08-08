"""Portable supervision for the training loop's strategic decisions.

The Red teacher knows how to grind safely, but a transferable player must not
learn Red map numbers, species identifiers, or memory addresses as shortcuts.
This module records only the reusable question at each training boundary:
seek another encounter, fight, flee, heal, or stop.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from pokemon_red_completion.party import (
    MAX_LEVEL,
    PartyMemberObservation,
    PartyObservation,
    StatusCondition,
)
from pokemon_red_completion.team_training import (
    BalancedTeamPolicy,
    GrindingArea,
    TeamTrainingProgress,
    training_safety_ceiling,
)


class TrainingControlError(ValueError):
    """Raised when training supervision is incomplete or inconsistent."""


class TrainingControlAction(StrEnum):
    """One game-neutral action at a training-strategy boundary."""

    SEEK = "seek"
    FIGHT = "fight"
    FLEE = "flee"
    HEAL = "heal"
    STOP = "stop"


class TrainingControlPhase(StrEnum):
    """The two phases that expose different legal training actions."""

    OVERWORLD = "overworld"
    BATTLE = "battle"


TRAINING_CONTROL_CLASS_REFS = tuple(action.value for action in TrainingControlAction)
TRAINING_CONTROL_FEATURE_NAMES = (
    "phase.battle",
    "party.fill_ratio",
    "party.fainted_ratio",
    "party.minimum_level",
    "party.level_floor_deficit",
    "party.level_spread",
    "party.spread_excess",
    "trainee.is_lead",
    "trainee.level",
    "trainee.hp_ratio",
    "trainee.status_healthy",
    "trainee.attack_pp",
    "trainee.attack_pp_margin",
    "enemy.observed",
    "enemy.level",
    "enemy.level_delta",
    "venue.fightable_share",
    "progress.battle_ratio",
    "progress.step_ratio",
    "progress.healing_ratio",
    "progress.consecutive_flee_ratio",
)
TRAINING_CONTROL_FEATURE_SCHEMA_ID = "pokemon.core.training.control.features.v1"


@dataclass(frozen=True, slots=True)
class TrainingControlObservation:
    """A normalized, cross-game view of one training decision boundary."""

    phase: TrainingControlPhase
    features: tuple[float, ...]
    candidate_actions: tuple[TrainingControlAction, ...]
    feature_schema_id: str = TRAINING_CONTROL_FEATURE_SCHEMA_ID

    def __post_init__(self) -> None:
        if not isinstance(self.phase, TrainingControlPhase):
            raise TrainingControlError("training phase is invalid")
        if self.feature_schema_id != TRAINING_CONTROL_FEATURE_SCHEMA_ID:
            raise TrainingControlError("training feature schema is unsupported")
        if len(self.features) != len(TRAINING_CONTROL_FEATURE_NAMES):
            raise TrainingControlError("training feature vector has the wrong width")
        values = np.asarray(self.features, dtype=np.float64)
        if not np.all(np.isfinite(values)) or np.any(values < -1.0) or np.any(values > 1.0):
            raise TrainingControlError("training features must be finite and normalized")
        phase_actions = (
            (TrainingControlAction.FIGHT, TrainingControlAction.FLEE)
            if self.phase is TrainingControlPhase.BATTLE
            else (
                TrainingControlAction.SEEK,
                TrainingControlAction.HEAL,
                TrainingControlAction.STOP,
            )
        )
        if (
            not self.candidate_actions
            or any(action not in phase_actions for action in self.candidate_actions)
            or tuple(action for action in phase_actions if action in self.candidate_actions)
            != self.candidate_actions
        ):
            raise TrainingControlError("candidate actions do not match the training phase")

    def vector(self) -> NDArray[np.float64]:
        """Return a detached numeric vector for model training or inference."""

        return np.asarray(self.features, dtype=np.float64).copy()

    def public_dict(self) -> dict[str, object]:
        """Serialize without game-private or adapter-private identifiers."""

        return {
            "feature_schema_id": self.feature_schema_id,
            "phase": self.phase.value,
            "features": dict(zip(TRAINING_CONTROL_FEATURE_NAMES, self.features, strict=True)),
            "candidate_actions": [action.value for action in self.candidate_actions],
        }


@dataclass(frozen=True, slots=True)
class TrainingControlDecision:
    """One teacher label emitted before the corresponding mechanic executes."""

    decision_index: int
    action: TrainingControlAction
    observation: TrainingControlObservation
    reason: str

    def __post_init__(self) -> None:
        if type(self.decision_index) is not int or self.decision_index < 0:  # noqa: E721
            raise TrainingControlError("training decision index is invalid")
        if not isinstance(self.action, TrainingControlAction):
            raise TrainingControlError("training action is invalid")
        if self.action not in self.observation.candidate_actions:
            raise TrainingControlError("training action is illegal in the observed phase")
        if not self.reason.strip():
            raise TrainingControlError("training decision needs a reason")

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-training-control-decision-v1",
            "decision_index": self.decision_index,
            "action": self.action.value,
            "reason": self.reason,
            "observation": self.observation.public_dict(),
        }


def project_training_control_observation(
    party: PartyObservation,
    policy: BalancedTeamPolicy,
    progress: TeamTrainingProgress,
    *,
    phase: TrainingControlPhase,
    trainee: PartyMemberObservation | None,
    attack_pp: int | None = None,
    attack_pp_reserve: int | None = None,
    enemy_level: int | None = None,
    venue: GrindingArea | None = None,
    consecutive_flees: int = 0,
    max_consecutive_flees: int = 1,
    fight_allowed: bool = True,
) -> TrainingControlObservation:
    """Project a teacher boundary without retaining game-specific identity."""

    if type(consecutive_flees) is not int or consecutive_flees < 0:  # noqa: E721
        raise TrainingControlError("consecutive flee count is invalid")
    if type(max_consecutive_flees) is not int or max_consecutive_flees < 1:  # noqa: E721
        raise TrainingControlError("maximum consecutive flee count is invalid")
    if type(fight_allowed) is not bool:  # noqa: E721
        raise TrainingControlError("fight-allowed flag is invalid")
    for name, value in (("attack_pp", attack_pp), ("attack_pp_reserve", attack_pp_reserve)):
        if value is not None and (type(value) is not int or value < 0):
            raise TrainingControlError(f"{name} is invalid")
    if enemy_level is not None and (
        type(enemy_level) is not int or not 1 <= enemy_level <= MAX_LEVEL
    ):
        raise TrainingControlError("enemy level is invalid")

    minimum = party.minimum_level or 0
    spread = party.level_spread or 0
    trainee_level = trainee.level if trainee else 0
    pp = attack_pp or 0
    reserve = attack_pp_reserve or 0
    enemy = enemy_level or 0
    values = (
        float(phase is TrainingControlPhase.BATTLE),
        _ratio(party.size, policy.required_size),
        _ratio(party.fainted_count, max(1, party.size)),
        _ratio(minimum, MAX_LEVEL),
        _ratio(max(0, policy.minimum_level - minimum), MAX_LEVEL),
        _ratio(spread, MAX_LEVEL - 1),
        _ratio(max(0, spread - policy.maximum_level_spread), MAX_LEVEL - 1),
        float(trainee is not None and trainee.slot == 1),
        _ratio(trainee_level, MAX_LEVEL),
        trainee.hp_ratio if trainee else 0.0,
        float(
            trainee is not None
            and not trainee.is_fainted
            and trainee.status is StatusCondition.HEALTHY
        ),
        _ratio(pp, 64),
        _signed_ratio(pp - reserve, 64),
        float(enemy_level is not None),
        _ratio(enemy, MAX_LEVEL),
        _signed_ratio(trainee_level - enemy, MAX_LEVEL),
        venue.fightable_share(training_safety_ceiling(trainee, policy))
        if venue and trainee
        else 0.0,
        _ratio(progress.battles_completed, max(1, policy.max_battles)),
        _ratio(progress.steps_taken, max(1, policy.max_steps)),
        _ratio(progress.healing_trips, max(1, policy.max_healing_trips)),
        _ratio(consecutive_flees, max_consecutive_flees),
    )
    candidates = (
        (
            (TrainingControlAction.FIGHT, TrainingControlAction.FLEE)
            if fight_allowed
            else (TrainingControlAction.FLEE,)
        )
        if phase is TrainingControlPhase.BATTLE
        else (
            TrainingControlAction.SEEK,
            TrainingControlAction.HEAL,
            TrainingControlAction.STOP,
        )
    )
    return TrainingControlObservation(phase, values, candidates)


def _ratio(numerator: int, denominator: int) -> float:
    return min(1.0, max(0.0, numerator / denominator))


def _signed_ratio(numerator: int, denominator: int) -> float:
    return min(1.0, max(-1.0, numerator / denominator))
