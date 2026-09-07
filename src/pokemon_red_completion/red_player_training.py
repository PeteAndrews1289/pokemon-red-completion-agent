"""Native bounded-player training evidence; no fabricated legacy setup receipts."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import cast

from pokemon_red_completion.bounded_player_dashboard import ViewerGoalTrajectory
from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalManagerQuestion,
    GoalSelectionMode,
)
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetMeter
from pokemon_red_completion.goal_manager_trajectory import PendingGoalManagerDecision
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionMenu,
    LivingDexOutcomeStatus,
)
from pokemon_red_completion.living_dex_player_exploration import ExploringLivingDexGoalPolicy
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_living_dex_causal_adapter import (
    red_living_dex_outcome_from_observations,
)
from pokemon_red_completion.trajectory import JSONValue, SparseEvent

TRAINING_EVENT = "living_dex_player_training_outcome"
TRAINING_EVENT_SCHEMA = "pokemon.red.player-training-outcome.v1"


@dataclass(frozen=True, slots=True)
class _PendingTraining:
    before: Mapping[str, object]
    actions: int
    frames: int
    menu: LivingDexOptionMenu
    option_indices: tuple[int, ...]
    probabilities: tuple[float, ...]
    selected_index: int
    start_step: int


@dataclass(slots=True)
class RedPlayerTrainingTrajectory(ViewerGoalTrajectory):
    """Record only actual stochastic choices and independently observed outcomes."""

    observe_training: Callable[[], RedGoalObservation] | None = None
    training_meter: CompositionBudgetMeter | None = None
    training_plan_sha256: str = ""
    maximum_actions: int = 6_000
    maximum_frames: int = 600_000
    _training: _PendingTraining | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        super(RedPlayerTrainingTrajectory, self).__post_init__()
        if (
            self.partition != "train"
            or not callable(self.observe_training)
            or not isinstance(self.training_meter, CompositionBudgetMeter)
            or re.fullmatch(r"[0-9a-f]{64}", self.training_plan_sha256) is None
            or not isinstance(self.displayed_authority, ExploringLivingDexGoalPolicy)
            or type(self.maximum_actions) is not int
            or self.maximum_actions <= 0
            or type(self.maximum_frames) is not int
            or self.maximum_frames <= 0
        ):
            raise ValueError("player training requires a declared train-only observation boundary")

    def record_selection(
        self,
        question: GoalManagerQuestion,
        selected_candidate_index: int,
        *,
        behavior_policy: Mapping[str, object] | None = None,
        selection_mode: GoalSelectionMode = GoalSelectionMode.AUTHORITY,
    ) -> PendingGoalManagerDecision:
        self._training = None
        pending = ViewerGoalTrajectory.record_selection(
            self,
            question,
            selected_candidate_index,
            behavior_policy=behavior_policy,
            selection_mode=selection_mode,
        )
        authority = self.displayed_authority
        assert isinstance(authority, ExploringLivingDexGoalPolicy)
        if selection_mode is not GoalSelectionMode.AUTHORITY or not authority.training_eligible:
            return pending
        if not self.pending_was_recorded or authority.last_menu is None:
            raise ValueError("training decision was not durably recorded")
        if behavior_policy != authority.selection_metadata():
            raise ValueError("training behavior differs from the committed choice")
        if (
            authority.last_decision is None
            or authority.last_decision.selected_candidate_index != selected_candidate_index
            or authority.last_question_sha256 != question.ordered_policy_input_sha256
        ):
            raise ValueError("training choice does not belong to the current question")
        assert self.training_meter is not None and self.observe_training is not None
        counter = self.training_meter.checkpoint()
        before = self.observe_training()
        if self.training_meter.checkpoint() != counter:
            raise ValueError("training observation changed the game")
        self._training = _PendingTraining(
            before.public_dict(),
            counter.controller_actions,
            counter.emulator_frames,
            authority.last_menu,
            authority.last_menu_indices,
            authority.option_probabilities,
            authority.last_menu_indices.index(selected_candidate_index),
            self.recorder.next_step_index,
        )
        return pending

    def record_outcome(
        self,
        pending: PendingGoalManagerDecision,
        *,
        status: GoalDecisionOutcome,
        failure_reason: GoalFailureReason | None = None,
    ) -> bool:
        recorded = ViewerGoalTrajectory.record_outcome(
            self,
            pending,
            status=status,
            failure_reason=failure_reason,
        )
        training, self._training = self._training, None
        if training is None or not recorded:
            return recorded
        assert self.training_meter is not None and self.observe_training is not None
        counter = self.training_meter.checkpoint()
        after: dict[str, object] | None = None
        actions = counter.controller_actions - training.actions
        frames = counter.emulator_frames - training.frames
        if min(actions, frames) < 0:
            raise ValueError("training counters regressed")
        if status is GoalDecisionOutcome.INTERRUPTED:
            outcome = LivingDexObservedOutcome(
                LivingDexOutcomeStatus.CENSORED,
                censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
            )
        else:
            after = self.observe_training().public_dict()
            if self.training_meter.checkpoint() != counter:
                raise ValueError("training outcome observation changed the game")
            outcome = red_living_dex_outcome_from_observations(
                training.before,
                after,
                succeeded=status is GoalDecisionOutcome.SUCCEEDED,
                actions=actions,
                frames=frames,
                maximum_actions=self.maximum_actions,
                maximum_frames=self.maximum_frames,
            )
        example = LivingDexObservedArmExample(
            decision_sha256=canonical_sha256(
                {
                    "decision_id": pending.decision_id,
                    "plan_sha256": self.training_plan_sha256,
                    "question_sha256": pending.question.ordered_policy_input_sha256,
                }
            ),
            partition="train",
            menu=training.menu,
            selected_candidate_index=training.selected_index,
            behavior_probabilities=training.probabilities,
            outcome=outcome,
        )
        self.sink.record_event(
            SparseEvent(
                event_id=f"{pending.decision_id}:training",
                episode_id=self.episode_id,
                step_index=self.recorder.next_step_index,
                kind=TRAINING_EVENT,
                payload=cast(
                    Mapping[str, JSONValue],
                    {
                        "schema": TRAINING_EVENT_SCHEMA,
                        "decision_id": pending.decision_id,
                        "plan_sha256": self.training_plan_sha256,
                        "option_indices": list(training.option_indices),
                        "example": example.public_dict(),
                        "before": dict(training.before),
                        "after": after,
                        "actions": actions,
                        "frames": frames,
                        "maximum_actions": self.maximum_actions,
                        "maximum_frames": self.maximum_frames,
                        "has_controller_input": actions > 0,
                        "start_step": training.start_step,
                        "end_step": self.recorder.next_step_index,
                    },
                ),
            )
        )
        return recorded
