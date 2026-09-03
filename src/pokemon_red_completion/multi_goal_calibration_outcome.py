"""One-decision outcome collection for a frozen multi-goal calibration arm.

The campaign enumerates every supported semantic option before outcomes.  This module
executes exactly one of those preassigned options, records the decision before the
binding may act, and derives its result from an independent observation and budget
meter.  It contains no teacher and performs no model-based selection.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.goal_manager import (
    BoundGoalSelection,
    GoalDecisionOutcome,
    GoalKind,
    GoalManagerQuestion,
    bind_goal_selection,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    FRESH_COMPOSITION_ACTIONS_PER_DECISION,
    FRESH_COMPOSITION_FRAMES_PER_DECISION,
    CompositionBudgetMeter,
    GoalManagerCompositionError,
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
    require_living_collection_transition,
)
from pokemon_red_completion.goal_manager_runtime import execute_goal_manager_decision
from pokemon_red_completion.goal_manager_trajectory import GoalManagerTrajectoryObserver

FORCED_CALIBRATION_POLICY_ID = "pokemon.core.goal-manager.forced-calibration-arm.v1"


class MultiGoalCalibrationOutcomeError(RuntimeError):
    """Raised when a frozen calibration arm crosses its declared boundary."""


@dataclass(slots=True)
class ForcedCalibrationPolicy:
    """Select one preregistered candidate and expose its one-hot assignment law."""

    selected_candidate_index: int
    selected_goal_kind: GoalKind
    expected_question_sha256: str
    expected_policy_context_sha256: str
    expected_available_menu_sha256: str
    decisions: int = field(default=0, init=False)
    _last_metadata: dict[str, object] | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if type(self.selected_candidate_index) is not int or (  # noqa: E721
            self.selected_candidate_index < 0
        ):
            raise MultiGoalCalibrationOutcomeError(
                "forced calibration candidate index is invalid"
            )
        if not isinstance(self.selected_goal_kind, GoalKind):
            raise MultiGoalCalibrationOutcomeError(
                "forced calibration goal kind is invalid"
            )
        for value in (
            self.expected_question_sha256,
            self.expected_policy_context_sha256,
            self.expected_available_menu_sha256,
        ):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
            ):
                raise MultiGoalCalibrationOutcomeError(
                    "forced calibration question identity is invalid"
                )

    def select(self, question: GoalManagerQuestion) -> BoundGoalSelection:
        if not isinstance(question, GoalManagerQuestion):
            raise TypeError("question must be a GoalManagerQuestion")
        if self.decisions:
            raise MultiGoalCalibrationOutcomeError(
                "forced calibration policy may decide only once"
            )
        if (
            question.ordered_policy_input_sha256 != self.expected_question_sha256
            or question.policy_context_sha256 != self.expected_policy_context_sha256
            or question.available_menu_sha256 != self.expected_available_menu_sha256
            or self.selected_candidate_index not in question.available_indices
            or question.opportunities[self.selected_candidate_index].kind
            is not self.selected_goal_kind
        ):
            raise MultiGoalCalibrationOutcomeError(
                "forced calibration question differs from the frozen arm"
            )
        probabilities = [0.0] * len(question.opportunities)
        probabilities[self.selected_candidate_index] = 1.0
        self._last_metadata = {
            "schema": "pokemon.core.goal-manager-behavior-policy.v1",
            "behavior_policy_id": FORCED_CALIBRATION_POLICY_ID,
            "candidate_probabilities": probabilities,
            "selected_probability": 1.0,
            "base_selected_probability": 0.0,
            "exploration_mix": 0.0,
            "temperature": 1.0,
        }
        self.decisions += 1
        return bind_goal_selection(question, self.selected_candidate_index)

    def selection_metadata(self) -> Mapping[str, object]:
        if self._last_metadata is None:
            raise MultiGoalCalibrationOutcomeError(
                "forced calibration selection metadata is unavailable"
            )
        return dict(self._last_metadata)


@dataclass(frozen=True, slots=True)
class MultiGoalCalibrationOutcome:
    """Public-safe evidence from one preregistered semantic intervention."""

    selected_candidate_index: int
    selected_goal_kind: GoalKind
    status: GoalDecisionOutcome
    actions_executed: int
    frames_executed: int
    semantic_state_changed: bool
    policy_context_sha256: str
    available_menu_sha256: str
    collection_before: LivingCollectionCheckpoint
    collection_after: LivingCollectionCheckpoint

    def public_dict(self) -> dict[str, object]:
        return {
            "actions_executed": self.actions_executed,
            "available_menu_sha256": self.available_menu_sha256,
            "collection_after": _collection_evidence(self.collection_after),
            "collection_before": _collection_evidence(self.collection_before),
            "frames_executed": self.frames_executed,
            "policy_context_sha256": self.policy_context_sha256,
            "schema": "pokemon.red.multi-goal-calibration-outcome.v1",
            "selected_candidate_index": self.selected_candidate_index,
            "selected_goal_kind": self.selected_goal_kind.value,
            "semantic_state_changed": self.semantic_state_changed,
            "status": self.status.value,
            "teacher_queries": 0,
        }


def run_forced_calibration_outcome(
    *,
    observe: Callable[[], GoalManagerCompositionObservation],
    policy: ForcedCalibrationPolicy,
    trajectory: GoalManagerTrajectoryObserver,
    budget_meter: CompositionBudgetMeter,
) -> MultiGoalCalibrationOutcome:
    """Execute one frozen option and retain its independently verified consequence."""

    if not callable(observe):
        raise TypeError("observe must be callable")
    if not isinstance(policy, ForcedCalibrationPolicy):
        raise TypeError("policy must be a ForcedCalibrationPolicy")
    if not isinstance(trajectory, GoalManagerTrajectoryObserver):
        raise TypeError("trajectory must be a GoalManagerTrajectoryObserver")
    if not isinstance(budget_meter, CompositionBudgetMeter):
        raise TypeError("budget_meter must be a CompositionBudgetMeter")
    if policy.decisions or trajectory.next_decision_index:
        raise MultiGoalCalibrationOutcomeError(
            "forced calibration outcome must start unused"
        )

    initial_budget = budget_meter.checkpoint()
    before = _observation(observe())
    if budget_meter.checkpoint() != initial_budget:
        raise MultiGoalCalibrationOutcomeError(
            "forced calibration observation attempted emulator work"
        )
    execution = execute_goal_manager_decision(
        situation=before.situation,
        binding_set=before.binding_set,
        authority=policy,
        trajectory=trajectory,
        require_durable_decision=True,
    )
    if (
        not execution.decision_recorded
        or not execution.outcome_recorded
        or execution.selected_candidate_index != policy.selected_candidate_index
        or execution.selected_kind is not policy.selected_goal_kind
    ):
        raise MultiGoalCalibrationOutcomeError(
            "forced calibration decision did not settle durably"
        )

    after = _observation(observe())
    terminal_budget = budget_meter.checkpoint()
    actions = terminal_budget.controller_actions - initial_budget.controller_actions
    frames = terminal_budget.emulator_frames - initial_budget.emulator_frames
    if (
        actions < 0
        or frames < 0
        or actions > FRESH_COMPOSITION_ACTIONS_PER_DECISION
        or frames > FRESH_COMPOSITION_FRAMES_PER_DECISION
    ):
        raise MultiGoalCalibrationOutcomeError(
            "forced calibration budget evidence is invalid"
        )
    if execution.execution is not None and (
        actions != execution.execution.actions_executed
        or frames != execution.execution.frames_executed
    ):
        raise MultiGoalCalibrationOutcomeError(
            "forced calibration report differs from independent accounting"
        )
    try:
        require_living_collection_transition(
            before.collection,
            after.collection,
            selected_kind=execution.selected_kind,
            require_selected_goal_progress=execution.passed,
        )
    except GoalManagerCompositionError as error:
        raise MultiGoalCalibrationOutcomeError(
            "forced calibration collection transition is invalid"
        ) from error
    changed = after.semantic_state_sha256 != before.semantic_state_sha256
    if execution.passed and not changed:
        raise MultiGoalCalibrationOutcomeError(
            "successful forced calibration arm did not change semantic state"
        )
    trajectory.require_settled()
    return MultiGoalCalibrationOutcome(
        selected_candidate_index=execution.selected_candidate_index,
        selected_goal_kind=execution.selected_kind,
        status=execution.verification.status,
        actions_executed=actions,
        frames_executed=frames,
        semantic_state_changed=changed,
        policy_context_sha256=policy.expected_policy_context_sha256,
        available_menu_sha256=policy.expected_available_menu_sha256,
        collection_before=before.collection,
        collection_after=after.collection,
    )


def _observation(value: object) -> GoalManagerCompositionObservation:
    if not isinstance(value, GoalManagerCompositionObservation):
        raise MultiGoalCalibrationOutcomeError(
            "forced calibration observer returned an invalid observation"
        )
    return value


def _collection_evidence(
    checkpoint: LivingCollectionCheckpoint,
) -> dict[str, object]:
    result = checkpoint.public_dict()
    result["specimen_counts"] = [list(item) for item in checkpoint.specimen_counts]
    return result


__all__ = [
    "FORCED_CALIBRATION_POLICY_ID",
    "ForcedCalibrationPolicy",
    "MultiGoalCalibrationOutcome",
    "MultiGoalCalibrationOutcomeError",
    "run_forced_calibration_outcome",
]
