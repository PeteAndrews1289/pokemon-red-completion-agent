"""Opt-in forward-goal recording alongside unchanged immediate Red outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .forward_goal import ForwardGoalChoice
from .goal_manager import (
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalManagerQuestion,
    GoalSelectionMode,
)
from .goal_manager_trajectory import PendingGoalManagerDecision
from .living_dex_option_value import option_feature_names
from .living_dex_player_exploration import ExploringLivingDexGoalPolicy
from .provenance import canonical_sha256
from .red_forward_goal import (
    RED_FORWARD_CONTEXT_NAMES,
    RedForwardGoalCollector,
    red_forward_context,
)
from .red_player_training import RedPlayerTrainingTrajectory


@dataclass(slots=True)
class RedForwardTrainingTrajectory(RedPlayerTrainingTrajectory):
    """Record first-choice forward credit; singleton continuations are not choices.

    All actual immediate outcome records still come from the parent observer.
    The caller prepares the separately header-bound collector before running and
    honors its terminal result through the player's independent stop predicate.
    """

    forward: RedForwardGoalCollector | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        super(RedForwardTrainingTrajectory, self).__post_init__()
        if not isinstance(self.forward, RedForwardGoalCollector):
            raise ValueError("forward training requires its explicit Red collector")
        if self.curriculum_contract is not None:
            raise ValueError("forward first-choice credit does not relabel singleton curriculum")

    def record_selection(
        self,
        question: GoalManagerQuestion,
        selected_candidate_index: int,
        *,
        behavior_policy: Mapping[str, object] | None = None,
        selection_mode: GoalSelectionMode = GoalSelectionMode.AUTHORITY,
    ) -> PendingGoalManagerDecision:
        assert self.forward is not None
        if self.forward.outcome is not None:
            raise ValueError("forward goal is already terminal; no additional choice allowed")
        if any(
            question.opportunities[i].kind not in {GoalKind.ADVANCE_STORY, GoalKind.RESTORE_TEAM}
            for i in question.available_indices
        ):
            raise ValueError("forward story pilot only supports story and field recovery")
        authority = self.displayed_authority
        if self.next_decision_index == 0 and (
            selection_mode is not GoalSelectionMode.AUTHORITY
            or not isinstance(authority, ExploringLivingDexGoalPolicy)
            or not authority.training_eligible
            or authority.model.feature_version != 3
        ):
            raise ValueError("forward anchor requires one real sampled v3 choice")
        pending = super(RedForwardTrainingTrajectory, self).record_selection(
            question,
            selected_candidate_index,
            behavior_policy=behavior_policy,
            selection_mode=selection_mode,
        )
        if pending.decision_index == 0:
            assert isinstance(authority, ExploringLivingDexGoalPolicy)
            assert authority.last_menu is not None and self.observe_training is not None
            before = self.forward.meter.checkpoint()
            observation = self.observe_training()
            if self.forward.meter.checkpoint() != before:
                raise ValueError("forward anchor observation attempted actions")
            self.forward.anchor(
                ForwardGoalChoice(
                    canonical_sha256(
                        {
                            "decision_id": pending.decision_id,
                            "training_plan_sha256": self.training_plan_sha256,
                        }
                    ),
                    canonical_sha256({"root_lineage_id": self.root_lineage_id}),
                    "train",
                    RED_FORWARD_CONTEXT_NAMES,
                    red_forward_context(observation),
                    option_feature_names(3),
                    tuple(
                        authority.last_menu.candidate_vector(i, feature_version=3)
                        for i in range(len(authority.last_menu.candidates))
                    ),
                    authority.last_menu_indices.index(selected_candidate_index),
                    authority.option_probabilities,
                )
            )
        return pending

    def record_outcome(
        self,
        pending: PendingGoalManagerDecision,
        *,
        status: GoalDecisionOutcome,
        failure_reason: GoalFailureReason | None = None,
    ) -> bool:
        recorded = super(RedForwardTrainingTrajectory, self).record_outcome(
            pending,
            status=status,
            failure_reason=failure_reason,
        )
        assert self.forward is not None
        if not recorded:
            raise ValueError("forward macro outcome was not durably recorded")
        if status is GoalDecisionOutcome.INTERRUPTED:
            self.forward.finish(interrupted=True)
        else:
            self.forward.after_macro()
        return recorded
