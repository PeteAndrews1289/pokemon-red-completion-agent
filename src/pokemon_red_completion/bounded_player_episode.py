"""Title-neutral bounded player seam for model-led completion attempts.

The goal authority sees only the public semantic question.  Existing private
bindings perform the selected mechanic, an independent verifier settles the
attempt, and a new observation plus living-collection ledger check decides
whether play may continue.  Ordinary verified failures may trigger one changed-
context replan. Binding exceptions become independently metered, typed failures
inside this bounded research player; interruptions and evidence defects remain
fail-closed.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

from pokemon_red_completion.executor import GoalExecutionBudgetExhausted
from pokemon_red_completion.goal_manager import (
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalManagerQuestion,
    GoalSelectionMode,
)
from pokemon_red_completion.goal_manager_composition_runtime import (
    CompositionBudgetCheckpoint,
    CompositionBudgetMeter,
    GoalManagerCompositionError,
    GoalManagerCompositionObservation,
    LivingCollectionCheckpoint,
    require_living_collection_transition,
)
from pokemon_red_completion.goal_manager_runtime import (
    ExecutableGoalBinding,
    GoalBindingSet,
    GoalDecisionAuthority,
    GoalExecutionReport,
    GoalManagerExecutionResult,
    GoalVerification,
    execute_goal_manager_decision,
)
from pokemon_red_completion.goal_manager_trajectory import (
    GoalManagerTrajectoryObserver,
)


class BoundedPlayerError(RuntimeError):
    """Raised when the bounded player crosses an authority or evidence boundary."""


class _RepeatedRecoveryGoal(BoundedPlayerError):
    """The actor proposed a prohibited retry before a new decision or input."""


_PUBLIC_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class BoundedPlayerStopReason(StrEnum):
    """Typed terminal reasons that do not overclaim full-game completion."""

    COMPLETION_REACHED = "completion_reached"
    DECISION_LIMIT = "decision_limit"
    VERIFIED_FAILURE = "verified_failure"
    FAILURE_CONTEXT_UNCHANGED = "failure_context_unchanged"
    RECOVERY_GOAL_REPEATED = "recovery_goal_repeated"
    INSUFFICIENT_AVAILABLE_GOALS = "insufficient_available_goals"


@dataclass(frozen=True, slots=True)
class BoundedPlayerLimits:
    """Small explicit envelope for one resumable player episode.

    ``min_available_goals`` is the minimum menu width required to invoke the
    learned or baseline authority.  After at least one genuine choice, an
    exactly-one-option menu may execute as a separately labelled forced bridge.
    """

    max_decisions: int = 2
    max_replans: int = 1
    min_available_goals: int = 2
    max_actions_per_decision: int = 6_000
    max_frames_per_decision: int = 600_000
    max_total_actions: int = 12_000
    max_total_frames: int = 1_200_000

    def __post_init__(self) -> None:
        for name in (
            "max_decisions",
            "min_available_goals",
            "max_actions_per_decision",
            "max_frames_per_decision",
            "max_total_actions",
            "max_total_frames",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:  # noqa: E721
                raise BoundedPlayerError(f"{name} must be a positive integer")
        if type(self.max_replans) is not int or self.max_replans < 0:  # noqa: E721
            raise BoundedPlayerError("max_replans must be a non-negative integer")
        if self.max_replans >= self.max_decisions:
            raise BoundedPlayerError("max_replans must be smaller than max_decisions")
        if self.max_total_actions < self.max_actions_per_decision:
            raise BoundedPlayerError("total action budget is smaller than one decision")
        if self.max_total_frames < self.max_frames_per_decision:
            raise BoundedPlayerError("total frame budget is smaller than one decision")


@dataclass(frozen=True, slots=True)
class BoundedPlayerStep:
    """Public, path-free evidence for one durably settled goal attempt."""

    decision_ordinal: int
    selected_kind: GoalKind
    status: GoalDecisionOutcome
    failure_reason: GoalFailureReason | None
    recovery_attempt: bool
    available_goal_count: int
    actions_executed: int
    frames_executed: int
    semantic_state_changed: bool
    policy_context_sha256: str
    available_menu_sha256: str
    collection_before: LivingCollectionCheckpoint
    collection_after: LivingCollectionCheckpoint
    selection_mode: GoalSelectionMode = GoalSelectionMode.AUTHORITY

    def public_dict(self) -> dict[str, object]:
        return {
            "actions_executed": self.actions_executed,
            "available_goal_count": self.available_goal_count,
            "available_menu_sha256": self.available_menu_sha256,
            "collection_after": self.collection_after.public_dict(),
            "collection_before": self.collection_before.public_dict(),
            "decision_ordinal": self.decision_ordinal,
            "failure_reason": (
                None if self.failure_reason is None else self.failure_reason.value
            ),
            "frames_executed": self.frames_executed,
            "policy_context_sha256": self.policy_context_sha256,
            "recovery_attempt": self.recovery_attempt,
            "selected_kind": self.selected_kind.value,
            "selection_mode": self.selection_mode.value,
            "semantic_state_changed": self.semantic_state_changed,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class BoundedPlayerResult:
    """Truthful terminal summary for one bounded player episode."""

    authority_id: str
    stop_reason: BoundedPlayerStopReason
    steps: tuple[BoundedPlayerStep, ...]
    completion_satisfied: bool

    @property
    def recovery_attempts(self) -> int:
        return sum(step.recovery_attempt for step in self.steps)

    @property
    def authority_decisions(self) -> int:
        return sum(
            step.selection_mode is GoalSelectionMode.AUTHORITY
            for step in self.steps
        )

    @property
    def forced_singleton_steps(self) -> int:
        return sum(
            step.selection_mode is GoalSelectionMode.FORCED_SINGLETON
            for step in self.steps
        )

    def public_dict(self) -> dict[str, object]:
        return {
            "authority_id": self.authority_id,
            "authority_decisions": self.authority_decisions,
            "completion_satisfied": self.completion_satisfied,
            "decisions": len(self.steps),
            "forced_singleton_steps": self.forced_singleton_steps,
            "private_binding_fields": 0,
            "private_path_fields": 0,
            "recovery_attempts": self.recovery_attempts,
            "schema": "pokemon.core.bounded-player-episode-result.v1",
            "status": "durable_terminal",
            "steps": [step.public_dict() for step in self.steps],
            "stop_reason": self.stop_reason.value,
            "teacher_fallbacks": 0,
            "total_actions": sum(step.actions_executed for step in self.steps),
            "total_frames": sum(step.frames_executed for step in self.steps),
        }


PlayerObserver = Callable[[], GoalManagerCompositionObservation]
CompletionPredicate = Callable[[GoalManagerCompositionObservation], bool]


def _retain_executor_failure(
    binding: ExecutableGoalBinding,
    budget_meter: CompositionBudgetMeter,
    failure_observer: Callable[[BaseException], None] | None = None,
) -> ExecutableGoalBinding:
    """Turn an executor exception into one metered failure for bounded recovery."""

    failed = False

    def execute() -> GoalExecutionReport:
        nonlocal failed
        before = budget_meter.checkpoint()
        try:
            return binding.execute()
        except GoalExecutionBudgetExhausted as error:
            _report_executor_failure(error, failure_observer, budget_meter)
            raise
        except Exception as error:
            after = budget_meter.checkpoint()
            _report_executor_failure(error, failure_observer, budget_meter)
            failed = True
            return GoalExecutionReport(
                actions_executed=(
                    after.controller_actions - before.controller_actions
                ),
                frames_executed=after.emulator_frames - before.emulator_frames,
                evidence={},
            )

    def verify(report: GoalExecutionReport) -> GoalVerification:
        if failed:
            return GoalVerification.failed(GoalFailureReason.BINDING_FAILED)
        return binding.verify(report)

    # Wrapping execution must preserve every declared policy fact, including
    # economic quotes and future fields. Rebuilding the dataclass loses them.
    return replace(binding, execute=execute, verify=verify)


def _retaining_binding_set(
    binding_set: GoalBindingSet,
    budget_meter: CompositionBudgetMeter,
    failure_observer: Callable[[BaseException], None] | None = None,
) -> GoalBindingSet:
    return GoalBindingSet(
        opportunities=binding_set.opportunities,
        bindings=tuple(
            _retain_executor_failure(binding, budget_meter, failure_observer)
            for binding in binding_set.bindings
        ),
    )


def _report_executor_failure(
    error: BaseException,
    observer: Callable[[BaseException], None] | None,
    budget_meter: CompositionBudgetMeter,
) -> None:
    """Retain a private cause before recovery; logging cannot act or be skipped."""
    if observer is None:
        return
    before = budget_meter.checkpoint()
    observer(error)
    if budget_meter.checkpoint() != before:
        raise BoundedPlayerError("failure diagnostic observer attempted game actions")


@dataclass(frozen=True, slots=True)
class _ForcedSingletonAuthority:
    """Select the sole legal goal without consulting learned authority."""

    def select(self, question: GoalManagerQuestion) -> int:
        if not isinstance(question, GoalManagerQuestion):
            raise TypeError("question must be a GoalManagerQuestion")
        if len(question.available_indices) != 1:
            raise BoundedPlayerError(
                "forced singleton authority requires exactly one available goal"
            )
        return question.available_indices[0]


def run_bounded_player_episode(
    *,
    observe: PlayerObserver,
    authority: GoalDecisionAuthority,
    authority_id: str,
    trajectory: GoalManagerTrajectoryObserver,
    budget_meter: CompositionBudgetMeter,
    completion_satisfied: CompletionPredicate,
    limits: BoundedPlayerLimits | None = None,
    failure_observer: Callable[[BaseException], None] | None = None,
) -> BoundedPlayerResult:
    """Run a few model-led goals with fresh evidence and one bounded replan."""

    if not callable(observe):
        raise TypeError("observe must be callable")
    if not callable(getattr(authority, "select", None)):
        raise TypeError("authority must expose a callable select method")
    if not isinstance(authority_id, str) or _PUBLIC_ID.fullmatch(authority_id) is None:
        raise BoundedPlayerError("authority_id must be a path-free public identifier")
    if not isinstance(trajectory, GoalManagerTrajectoryObserver):
        raise TypeError("trajectory must be a GoalManagerTrajectoryObserver")
    if not isinstance(budget_meter, CompositionBudgetMeter):
        raise TypeError("budget_meter must be a CompositionBudgetMeter")
    if not callable(completion_satisfied):
        raise TypeError("completion_satisfied must be callable")
    if failure_observer is not None and not callable(failure_observer):
        raise TypeError("failure_observer must be callable")
    limits = BoundedPlayerLimits() if limits is None else limits
    if not isinstance(limits, BoundedPlayerLimits):
        raise TypeError("limits must be BoundedPlayerLimits")
    if trajectory.next_decision_index != 0 or trajectory.pending_decision is not None:
        raise BoundedPlayerError("bounded player trajectory must start empty")

    initial_budget = budget_meter.checkpoint()
    current = _observe_without_actions(observe, budget_meter, initial_budget)
    if _completion_without_actions(completion_satisfied, current, budget_meter):
        return BoundedPlayerResult(
            authority_id=authority_id,
            stop_reason=BoundedPlayerStopReason.COMPLETION_REACHED,
            steps=(),
            completion_satisfied=True,
        )

    steps: list[BoundedPlayerStep] = []
    last_budget = initial_budget
    failed_kind: GoalKind | None = None
    failed_context: str | None = None
    replans_used = 0

    for decision_index in range(limits.max_decisions):
        available_count = sum(
            opportunity.availability is GoalAvailability.AVAILABLE
            for opportunity in current.binding_set.opportunities
        )
        forced_singleton = (
            available_count == 1
            and limits.min_available_goals > 1
            and bool(steps)
        )
        if available_count < limits.min_available_goals and not forced_singleton:
            if not steps:
                raise BoundedPlayerError(
                    "bounded player lacks a genuine semantic choice"
                )
            trajectory.require_settled()
            return BoundedPlayerResult(
                authority_id=authority_id,
                stop_reason=(
                    BoundedPlayerStopReason.INSUFFICIENT_AVAILABLE_GOALS
                ),
                steps=tuple(steps),
                completion_satisfied=False,
            )
        question = trajectory.ordered_question(
            current.situation,
            current.binding_set.opportunities,
        )
        if len(question.available_indices) != available_count:
            raise BoundedPlayerError(
                "bounded player availability accounting differs"
            )
        recovery_attempt = failed_kind is not None
        if recovery_attempt and question.policy_context_sha256 == failed_context:
            trajectory.require_settled()
            return BoundedPlayerResult(
                authority_id=authority_id,
                stop_reason=BoundedPlayerStopReason.FAILURE_CONTEXT_UNCHANGED,
                steps=tuple(steps),
                completion_satisfied=False,
            )

        selection_mode = (
            GoalSelectionMode.FORCED_SINGLETON
            if forced_singleton
            else GoalSelectionMode.AUTHORITY
        )
        selected_authority: GoalDecisionAuthority = (
            _ForcedSingletonAuthority() if forced_singleton else authority
        )

        before_selection = budget_meter.checkpoint()
        before_decision_index = trajectory.next_decision_index
        try:
            execution = execute_goal_manager_decision(
                situation=current.situation,
                binding_set=_retaining_binding_set(
                    current.binding_set, budget_meter, failure_observer
                ),
                authority=selected_authority,
                trajectory=trajectory,
                require_durable_decision=True,
                selection_guard=_different_goal_guard(failed_kind),
                selection_mode=selection_mode,
            )
        except _RepeatedRecoveryGoal:
            # This guard runs before recording or executing another choice. Do
            # not hide other authority/evidence errors or replace the actor.
            trajectory.require_settled()
            if (
                budget_meter.checkpoint() != before_selection
                or trajectory.next_decision_index != before_decision_index
            ):
                raise BoundedPlayerError("rejected recovery selection changed state") from None
            return BoundedPlayerResult(
                authority_id=authority_id,
                stop_reason=BoundedPlayerStopReason.RECOVERY_GOAL_REPEATED,
                steps=tuple(steps),
                completion_satisfied=False,
            )
        _require_settled_execution(execution)
        executed_budget = budget_meter.checkpoint()
        actions = executed_budget.controller_actions - last_budget.controller_actions
        frames = executed_budget.emulator_frames - last_budget.emulator_frames
        if actions < 0 or frames < 0:
            raise BoundedPlayerError("bounded player budget counters regressed")
        execution_report = execution.execution
        if execution_report is not None and (
            actions != execution_report.actions_executed
            or frames != execution_report.frames_executed
        ):
            raise BoundedPlayerError(
                "bounded player report differs from independent budget accounting"
            )
        if (
            actions > limits.max_actions_per_decision
            or frames > limits.max_frames_per_decision
        ):
            raise BoundedPlayerError("bounded player decision exceeded its budget")
        if (
            executed_budget.controller_actions - initial_budget.controller_actions
            > limits.max_total_actions
            or executed_budget.emulator_frames - initial_budget.emulator_frames
            > limits.max_total_frames
        ):
            raise BoundedPlayerError("bounded player episode exceeded its budget")

        after = _observe_without_actions(observe, budget_meter, executed_budget)
        if after is current:
            raise BoundedPlayerError("bounded player observer reused a stale observation")
        try:
            require_living_collection_transition(
                current.collection,
                after.collection,
                selected_kind=execution.selected_kind,
                require_selected_goal_progress=execution.passed,
            )
        except GoalManagerCompositionError as error:
            raise BoundedPlayerError(str(error)) from error
        semantic_changed = (
            after.semantic_state_sha256 != current.semantic_state_sha256
        )
        if execution.passed and not semantic_changed:
            raise BoundedPlayerError(
                "successful bounded goal did not change semantic state"
            )
        steps.append(
            BoundedPlayerStep(
                decision_ordinal=decision_index + 1,
                selected_kind=execution.selected_kind,
                status=execution.verification.status,
                failure_reason=execution.verification.failure_reason,
                recovery_attempt=recovery_attempt,
                available_goal_count=len(question.available_indices),
                actions_executed=actions,
                frames_executed=frames,
                semantic_state_changed=semantic_changed,
                policy_context_sha256=question.policy_context_sha256,
                available_menu_sha256=question.available_menu_sha256,
                collection_before=current.collection,
                collection_after=after.collection,
                selection_mode=selection_mode,
            )
        )
        if recovery_attempt:
            replans_used += 1
            failed_kind = None
            failed_context = None
        current = after
        last_budget = executed_budget

        complete = _completion_without_actions(
            completion_satisfied,
            current,
            budget_meter,
        )
        if complete:
            trajectory.require_settled()
            return BoundedPlayerResult(
                authority_id=authority_id,
                stop_reason=BoundedPlayerStopReason.COMPLETION_REACHED,
                steps=tuple(steps),
                completion_satisfied=True,
            )
        if not execution.passed:
            if replans_used >= limits.max_replans:
                trajectory.require_settled()
                return BoundedPlayerResult(
                    authority_id=authority_id,
                    stop_reason=BoundedPlayerStopReason.VERIFIED_FAILURE,
                    steps=tuple(steps),
                    completion_satisfied=False,
                )
            failed_kind = execution.selected_kind
            failed_context = question.policy_context_sha256

    trajectory.require_settled()
    return BoundedPlayerResult(
        authority_id=authority_id,
        stop_reason=(
            BoundedPlayerStopReason.VERIFIED_FAILURE
            if steps and steps[-1].status is not GoalDecisionOutcome.SUCCEEDED
            else BoundedPlayerStopReason.DECISION_LIMIT
        ),
        steps=tuple(steps),
        completion_satisfied=False,
    )


def _observe_without_actions(
    observe: PlayerObserver,
    budget_meter: CompositionBudgetMeter,
    expected_budget: CompositionBudgetCheckpoint,
) -> GoalManagerCompositionObservation:
    value = observe()
    if not isinstance(value, GoalManagerCompositionObservation):
        raise BoundedPlayerError("bounded player observer returned an invalid value")
    if budget_meter.checkpoint() != expected_budget:
        raise BoundedPlayerError("bounded player observation attempted emulator work")
    return value


def _completion_without_actions(
    predicate: CompletionPredicate,
    observation: GoalManagerCompositionObservation,
    budget_meter: CompositionBudgetMeter,
) -> bool:
    before = budget_meter.checkpoint()
    result = predicate(observation)
    if type(result) is not bool:  # noqa: E721
        raise BoundedPlayerError("completion predicate must return a bool")
    if budget_meter.checkpoint() != before:
        raise BoundedPlayerError("completion predicate attempted emulator work")
    return result


def _require_settled_execution(result: GoalManagerExecutionResult) -> None:
    if (
        not isinstance(result, GoalManagerExecutionResult)
        or not result.decision_recorded
        or not result.outcome_recorded
    ):
        raise BoundedPlayerError(
            "bounded player decision did not produce a durable settled outcome"
        )
    if result.execution is None and (
        result.verification.status is not GoalDecisionOutcome.FAILED
        or result.verification.failure_reason
        is not GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
    ):
        raise BoundedPlayerError("bounded player execution report is absent")


def _different_goal_guard(
    failed_kind: GoalKind | None,
) -> Callable[[object], None]:
    def guard(selection: object) -> None:
        if failed_kind is not None and getattr(selection, "kind", None) is failed_kind:
            raise _RepeatedRecoveryGoal(
                "bounded player repeated the failed goal during recovery"
            )

    return guard
