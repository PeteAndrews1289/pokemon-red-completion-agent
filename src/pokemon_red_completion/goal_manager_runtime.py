"""Causal execution boundary for portable high-level goal choices.

The model chooses only a semantic candidate index.  This module rebinds that
index to one adapter-private bounded skill, records the decision before the
skill can act, and lets a separate verifier determine the outcome.  Callers
that require fail-closed durability must enable the durable-decision guard.
The executor cannot manufacture its own successful label.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from pokemon_red_completion.executor import GoalExecutionBudgetExhausted
from pokemon_red_completion.goal_manager import (
    BoundGoalSelection,
    GoalAvailability,
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalManagerError,
    GoalManagerQuestion,
    GoalOpportunity,
    GoalSelectionMode,
    GoalSituation,
    bind_goal_selection,
)
from pokemon_red_completion.goal_manager_trajectory import (
    GoalManagerTrajectoryObserver,
)
from pokemon_red_completion.goal_resource_quote import GoalResourceQuote
from pokemon_red_completion.goal_search_memory import GoalSearchHistory


class GoalManagerRuntimeError(RuntimeError):
    """Raised when execution crosses a goal-manager authority boundary."""


@dataclass(frozen=True, slots=True)
class GoalExecutionReport:
    """Bounded mechanic evidence returned before independent verification."""

    actions_executed: int
    frames_executed: int
    evidence: Mapping[str, object]

    def __post_init__(self) -> None:
        for name in ("actions_executed", "frames_executed"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise GoalManagerRuntimeError(f"{name} must be a non-negative integer")
        if not isinstance(self.evidence, Mapping):
            raise GoalManagerRuntimeError("goal execution evidence must be a mapping")
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))


@dataclass(frozen=True, slots=True)
class GoalVerification:
    """Independent semantic verdict for one completed mechanic attempt."""

    status: GoalDecisionOutcome
    failure_reason: GoalFailureReason | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GoalDecisionOutcome):
            raise GoalManagerRuntimeError("goal verification status is invalid")
        if self.status is GoalDecisionOutcome.SUCCEEDED:
            if self.failure_reason is not None:
                raise GoalManagerRuntimeError(
                    "successful goal verification cannot have a failure reason"
                )
        elif not isinstance(self.failure_reason, GoalFailureReason):
            raise GoalManagerRuntimeError(
                "failed or interrupted goal verification needs a failure reason"
            )

    @classmethod
    def succeeded(cls) -> GoalVerification:
        return cls(GoalDecisionOutcome.SUCCEEDED)

    @classmethod
    def failed(cls, reason: GoalFailureReason) -> GoalVerification:
        return cls(GoalDecisionOutcome.FAILED, reason)


class GoalDecisionAuthority(Protocol):
    """Teacher or learned policy that receives only the public question."""

    def select(self, question: GoalManagerQuestion) -> int | BoundGoalSelection: ...


@dataclass(frozen=True, slots=True)
class CompletionFirstGoalTeacher:
    """Deterministic portable teacher for high-level curriculum collection.

    Emergency control, survival, storage and supply constraints are hard gates.
    Ordinary choices then trade off the normalized pressures a goal addresses
    against measured effort and risk.  This is intentionally richer than the
    preregistered highest-pressure and lowest-cost baselines while remaining
    independent of title, binding identity and candidate position.
    """

    recovery_gate: float = 0.50
    safety_gate: float = 0.55
    storage_gate: float = 0.75
    resource_gate: float = 0.75
    effort_penalty: float = 0.20
    risk_penalty: float = 0.35

    def __post_init__(self) -> None:
        for name in (
            "recovery_gate",
            "safety_gate",
            "storage_gate",
            "resource_gate",
            "effort_penalty",
            "risk_penalty",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise GoalManagerRuntimeError(f"{name} must be numeric")
            if not 0.0 <= float(value) <= 1.0:
                raise GoalManagerRuntimeError(f"{name} must be between zero and one")

    def select(self, question: GoalManagerQuestion) -> BoundGoalSelection:
        if not isinstance(question, GoalManagerQuestion):
            raise TypeError("question must be a GoalManagerQuestion")
        available_by_kind = {
            opportunity.kind: index
            for index, opportunity in enumerate(question.opportunities)
            if opportunity.availability is GoalAvailability.AVAILABLE
        }
        gates = (
            (GoalKind.RECOVER_CONTROL, question.situation.recovery_pressure, self.recovery_gate),
            (GoalKind.RESTORE_TEAM, question.situation.safety_pressure, self.safety_gate),
            (GoalKind.MANAGE_STORAGE, question.situation.storage_pressure, self.storage_gate),
            (GoalKind.RESUPPLY, question.situation.resource_pressure, self.resource_gate),
        )
        for kind, pressure, threshold in gates:
            index = available_by_kind.get(kind)
            if index is not None and pressure >= threshold:
                return bind_goal_selection(question, index)

        def score(index: int) -> tuple[float, str]:
            opportunity = question.opportunities[index]
            pressures = tuple(
                question.situation.pressure(need) for need in opportunity.addressed_needs
            )
            assert opportunity.estimated_effort is not None
            assert opportunity.estimated_risk is not None
            utility = (
                max(pressures)
                + 0.25 * (sum(pressures) / len(pressures))
                - self.effort_penalty * opportunity.estimated_effort
                - self.risk_penalty * opportunity.estimated_risk
            )
            # A semantic string is a stable, position-free final tie break.
            return utility, opportunity.kind.value

        selected_index = max(question.available_indices, key=score)
        return bind_goal_selection(question, selected_index)

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.completion-first-goal-teacher.v1",
            "recovery_gate": self.recovery_gate,
            "safety_gate": self.safety_gate,
            "storage_gate": self.storage_gate,
            "resource_gate": self.resource_gate,
            "effort_penalty": self.effort_penalty,
            "risk_penalty": self.risk_penalty,
            "uses_title_identity": False,
            "uses_binding_identity": False,
            "uses_candidate_position": False,
        }


GoalExecutor = Callable[[], GoalExecutionReport]
GoalVerifier = Callable[[GoalExecutionReport], GoalVerification]
GoalSelectionGuard = Callable[[BoundGoalSelection], None]


@dataclass(frozen=True, slots=True)
class ExecutableGoalBinding:
    """One adapter-private bounded skill and its independent verifier."""

    binding_ref: str
    kind: GoalKind
    estimated_effort: float
    estimated_risk: float
    execute: GoalExecutor
    verify: GoalVerifier
    resource_quote: GoalResourceQuote | None = None
    search_history: GoalSearchHistory | None = None
    search_source_ref: str | None = None

    def __post_init__(self) -> None:
        if self.search_source_ref is not None and (
            not isinstance(self.search_source_ref, str) or not self.search_source_ref
            or self.kind is not GoalKind.ACQUIRE_SPECIES
        ):
            raise GoalManagerRuntimeError("search source must bind an acquisition")
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise GoalManagerRuntimeError("goal binding reference must be non-empty")
        if not isinstance(self.kind, GoalKind):
            raise GoalManagerRuntimeError("goal binding kind is invalid")
        if not callable(self.execute) or not callable(self.verify):
            raise GoalManagerRuntimeError("goal binding requires executor and verifier callables")
        # Reuse the policy contract's strict normalized-metric validation.
        _ = self.opportunity

    @property
    def search_memory_source(self) -> str:
        # Routing identities authenticate the current origin; source memory must
        # survive movement and unrelated resource changes. Never project this key.
        return self.binding_ref if self.search_source_ref is None else self.search_source_ref

    @property
    def opportunity(self) -> GoalOpportunity:
        return GoalOpportunity(
            binding_ref=self.binding_ref,
            kind=self.kind,
            availability=GoalAvailability.AVAILABLE,
            estimated_effort=self.estimated_effort,
            estimated_risk=self.estimated_risk,
            resource_quote=self.resource_quote,
            search_history=self.search_history,
        )


@dataclass(frozen=True, slots=True)
class GoalBindingSet:
    """Exact available bindings beside the complete masked candidate menu."""

    opportunities: tuple[GoalOpportunity, ...]
    bindings: tuple[ExecutableGoalBinding, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.opportunities, tuple) or len(self.opportunities) < 2:
            raise GoalManagerRuntimeError("goal binding set needs at least two opportunities")
        if any(not isinstance(item, GoalOpportunity) for item in self.opportunities):
            raise GoalManagerRuntimeError("goal binding set contains an invalid opportunity")
        if any(not isinstance(item, ExecutableGoalBinding) for item in self.bindings):
            raise GoalManagerRuntimeError("goal binding set contains an invalid binding")
        opportunity_refs = tuple(item.binding_ref for item in self.opportunities)
        if len(opportunity_refs) != len(set(opportunity_refs)):
            raise GoalManagerRuntimeError("goal opportunity binding references must be unique")
        binding_refs = tuple(item.binding_ref for item in self.bindings)
        if len(binding_refs) != len(set(binding_refs)):
            raise GoalManagerRuntimeError("executable goal binding references must be unique")
        available = {
            item.binding_ref: item
            for item in self.opportunities
            if item.availability is GoalAvailability.AVAILABLE
        }
        if set(available) != set(binding_refs):
            raise GoalManagerRuntimeError(
                "available opportunities and executable bindings must match exactly"
            )
        for binding in self.bindings:
            if available[binding.binding_ref] != binding.opportunity:
                raise GoalManagerRuntimeError(
                    "goal binding metrics or kind differ from their policy opportunity"
                )

    def require(self, binding_ref: str) -> ExecutableGoalBinding:
        try:
            return next(item for item in self.bindings if item.binding_ref == binding_ref)
        except StopIteration as error:
            raise GoalManagerRuntimeError("selected goal has no executable binding") from error


@dataclass(frozen=True, slots=True)
class GoalManagerExecutionResult:
    """Public-safe outcome of one recorded high-level arbitration."""

    selected_kind: GoalKind
    selected_candidate_index: int
    execution: GoalExecutionReport | None
    verification: GoalVerification
    decision_recorded: bool
    outcome_recorded: bool

    @property
    def passed(self) -> bool:
        return self.verification.status is GoalDecisionOutcome.SUCCEEDED

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.core.goal-manager-execution.v1",
            "selected_kind": self.selected_kind.value,
            "selected_candidate_index": self.selected_candidate_index,
            "status": self.verification.status.value,
            "failure_reason": (
                None
                if self.verification.failure_reason is None
                else self.verification.failure_reason.value
            ),
            "actions_executed": (
                None if self.execution is None else self.execution.actions_executed
            ),
            "frames_executed": (
                None if self.execution is None else self.execution.frames_executed
            ),
            "decision_recorded": self.decision_recorded,
            "outcome_recorded": self.outcome_recorded,
            "private_binding_fields": 0,
        }


def execute_goal_manager_decision(
    *,
    situation: GoalSituation,
    binding_set: GoalBindingSet,
    authority: GoalDecisionAuthority,
    trajectory: GoalManagerTrajectoryObserver,
    require_durable_decision: bool = False,
    selection_guard: GoalSelectionGuard | None = None,
    selection_mode: GoalSelectionMode = GoalSelectionMode.AUTHORITY,
) -> GoalManagerExecutionResult:
    """Choose, record, execute and independently verify exactly one goal."""

    if not isinstance(situation, GoalSituation):
        raise TypeError("situation must be a GoalSituation")
    if not isinstance(binding_set, GoalBindingSet):
        raise TypeError("binding_set must be a GoalBindingSet")
    if not isinstance(trajectory, GoalManagerTrajectoryObserver):
        raise TypeError("trajectory must be a GoalManagerTrajectoryObserver")
    if type(require_durable_decision) is not bool:  # noqa: E721
        raise TypeError("require_durable_decision must be a bool")
    if selection_guard is not None and not callable(selection_guard):
        raise TypeError("selection_guard must be callable")
    if not isinstance(selection_mode, GoalSelectionMode):
        raise TypeError("selection_mode must be GoalSelectionMode")
    question = trajectory.ordered_question(situation, binding_set.opportunities)
    selected = authority.select(question)
    if isinstance(selected, BoundGoalSelection):
        rebound = bind_goal_selection(question, selected.selected_index)
        if rebound != selected:
            raise GoalManagerRuntimeError(
                "goal authority returned a selection bound to a different question"
            )
        selected_index = selected.selected_index
    elif type(selected) is int:  # noqa: E721
        selected_index = selected
    else:
        raise GoalManagerRuntimeError("goal authority returned an invalid selection")
    try:
        bound = bind_goal_selection(question, selected_index)
    except GoalManagerError as error:
        raise GoalManagerRuntimeError(str(error)) from error
    if selection_guard is not None:
        selection_guard(bound)
    binding = binding_set.require(bound.binding_ref)
    behavior_policy: Mapping[str, object] | None = None
    metadata_provider = getattr(authority, "selection_metadata", None)
    if metadata_provider is not None:
        if not callable(metadata_provider):
            raise GoalManagerRuntimeError(
                "goal authority selection metadata provider is invalid"
            )
        provided = metadata_provider()
        if not isinstance(provided, Mapping):
            raise GoalManagerRuntimeError("goal authority selection metadata is invalid")
        behavior_policy = provided
    pending = trajectory.record_selection(
        question,
        selected_index,
        behavior_policy=behavior_policy,
        selection_mode=selection_mode,
    )
    decision_recorded = trajectory.pending_was_recorded
    if require_durable_decision and not decision_recorded:
        trajectory.abandon_unrecorded_selection(pending)
        trajectory.require_settled()
        raise GoalManagerRuntimeError(
            "goal decision was not durably recorded before execution"
        )
    execution: GoalExecutionReport | None = None
    try:
        execution = binding.execute()
        if not isinstance(execution, GoalExecutionReport):
            raise GoalManagerRuntimeError("goal executor returned an invalid report")
        verification = binding.verify(execution)
        if not isinstance(verification, GoalVerification):
            raise GoalManagerRuntimeError("goal verifier returned an invalid verdict")
    except (KeyboardInterrupt, SystemExit):
        verification = GoalVerification(
            GoalDecisionOutcome.INTERRUPTED,
            GoalFailureReason.EXTERNAL_INTERRUPTION,
        )
        trajectory.record_outcome(
            pending,
            status=verification.status,
            failure_reason=verification.failure_reason,
        )
        trajectory.require_settled()
        raise
    except GoalExecutionBudgetExhausted:
        verification = GoalVerification.failed(
            GoalFailureReason.EXECUTION_BUDGET_EXHAUSTED
        )
        outcome_recorded = trajectory.record_outcome(
            pending,
            status=verification.status,
            failure_reason=verification.failure_reason,
        )
        trajectory.require_settled()
        return GoalManagerExecutionResult(
            selected_kind=bound.kind,
            selected_candidate_index=selected_index,
            execution=None,
            verification=verification,
            decision_recorded=decision_recorded,
            outcome_recorded=outcome_recorded,
        )
    except Exception:
        verification = GoalVerification.failed(GoalFailureReason.BINDING_FAILED)
        trajectory.record_outcome(
            pending,
            status=verification.status,
            failure_reason=verification.failure_reason,
        )
        trajectory.require_settled()
        raise
    outcome_recorded = trajectory.record_outcome(
        pending,
        status=verification.status,
        failure_reason=verification.failure_reason,
    )
    trajectory.require_settled()
    return GoalManagerExecutionResult(
        selected_kind=bound.kind,
        selected_candidate_index=selected_index,
        execution=execution,
        verification=verification,
        decision_recorded=decision_recorded,
        outcome_recorded=outcome_recorded,
    )
