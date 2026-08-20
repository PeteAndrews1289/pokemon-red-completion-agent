"""Teacher-free live evaluation of an authenticated goal-manager candidate."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from pokemon_red_completion.executor import CountingExecutor
from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
    GoalKind,
    bind_goal_selection,
)
from pokemon_red_completion.goal_manager_collection_runtime import (
    GoalActionPort,
    GoalEnumeratorFactory,
    goal_binding_manifest_sha256,
)
from pokemon_red_completion.goal_manager_context_catalog import (
    GoalManagerContextCapture,
    GoalManagerContextCatalog,
)
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    LearnedGoalManagerPolicy,
)
from pokemon_red_completion.goal_manager_protocol import GoalManagerAssignment
from pokemon_red_completion.goal_manager_runtime import (
    GoalExecutionReport,
    GoalManagerExecutionResult,
    GoalVerification,
)
from pokemon_red_completion.goal_manager_trajectory import (
    ordered_goal_manager_question,
)
from pokemon_red_completion.red_goal_manager import PokemonRedGoalStateAdapter


class GoalManagerPromotionRuntimeError(RuntimeError):
    """Raised before a live result can be accepted as promotion evidence."""


@dataclass(frozen=True, slots=True)
class GoalManagerPromotionContextResult:
    mode: str
    slot_id: str
    context_id: str
    question_sha256: str
    policy_context_sha256: str
    reference_candidate_index: int
    reference_kind: GoalKind
    model_candidate_index: int
    model_kind: GoalKind
    model_confidence: float
    model_reference_agreement: bool
    model_had_execution_authority: bool
    reference_had_execution_authority: bool
    execution: GoalManagerExecutionResult

    def __post_init__(self) -> None:
        if self.mode not in {"shadow", "causal"}:
            raise GoalManagerPromotionRuntimeError("goal-manager evaluation mode is invalid")
        if not math.isfinite(self.model_confidence) or not 0.0 <= self.model_confidence <= 1.0:
            raise GoalManagerPromotionRuntimeError("goal-manager confidence is invalid")
        if self.model_had_execution_authority is (self.mode != "causal"):
            raise GoalManagerPromotionRuntimeError("goal-manager authority declaration differs")
        if self.reference_had_execution_authority is (self.mode != "shadow"):
            raise GoalManagerPromotionRuntimeError("goal-manager reference authority differs")
        expected_index = (
            self.model_candidate_index
            if self.model_had_execution_authority
            else self.reference_candidate_index
        )
        if self.execution.selected_candidate_index != expected_index:
            raise GoalManagerPromotionRuntimeError("goal-manager executed selection differs")

    @property
    def passed(self) -> bool:
        return self.execution.passed

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon-red-goal-manager-promotion-context-v1",
            "mode": self.mode,
            "slot_id": self.slot_id,
            "context_id": self.context_id,
            "question_sha256": self.question_sha256,
            "policy_context_sha256": self.policy_context_sha256,
            "reference": {
                "candidate_index": self.reference_candidate_index,
                "kind": self.reference_kind.value,
            },
            "model": {
                "candidate_index": self.model_candidate_index,
                "confidence": self.model_confidence,
                "kind": self.model_kind.value,
                "reference_agreement": self.model_reference_agreement,
            },
            "authority": {
                "model_had_execution_authority": self.model_had_execution_authority,
                "reference_had_execution_authority": (
                    self.reference_had_execution_authority
                ),
                "teacher_queries": 0,
                "teacher_fallbacks": 0,
            },
            "execution": self.execution.public_dict(),
            "counted": False,
            "episode_created": False,
            "private_binding_fields": 0,
            "private_path_fields": 0,
        }


@dataclass(frozen=True, slots=True)
class GoalManagerPromotionBatchResult:
    mode: str
    planned_contexts: int
    evaluated_contexts: int
    agreements: int
    successful_contexts: int
    minimum_confidence: float
    mean_confidence: float
    actions_executed: int
    frames_executed: int
    selected_kind_counts: tuple[tuple[str, int], ...]
    results: tuple[GoalManagerPromotionContextResult, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "planned_contexts": self.planned_contexts,
            "evaluated_contexts": self.evaluated_contexts,
            "agreements": self.agreements,
            "successful_contexts": self.successful_contexts,
            "minimum_confidence": self.minimum_confidence,
            "mean_confidence": self.mean_confidence,
            "actions_executed": self.actions_executed,
            "frames_executed": self.frames_executed,
            "selected_kind_counts": dict(self.selected_kind_counts),
            "teacher_queries": 0,
            "teacher_fallbacks": 0,
            "episodes_created": 0,
            "counted": False,
            "contexts": [item.public_dict() for item in self.results],
            "private_path_fields": 0,
        }


def evaluate_goal_manager_promotion_context(
    *,
    mode: str,
    assignment: GoalManagerAssignment,
    capture: GoalManagerContextCapture,
    context_catalog: GoalManagerContextCatalog,
    adapter: PokemonRedGoalStateAdapter,
    action_delegate: GoalActionPort,
    enumerator_factory: GoalEnumeratorFactory,
    model: GoalManagerLinearModel,
    confidence_threshold: float,
) -> GoalManagerPromotionContextResult:
    """Evaluate one frozen context with explicit shadow or model authority.

    Shadow mode executes the already-frozen catalog choice.  It does not call
    the teacher and cannot fall back based on the model prediction.  Causal
    mode executes exactly the learned choice and contains no teacher object or
    callback at all.
    """

    if mode not in {"shadow", "causal"}:
        raise GoalManagerPromotionRuntimeError("goal-manager evaluation mode is invalid")
    if not isinstance(assignment, GoalManagerAssignment) or assignment.source_commit is None:
        raise GoalManagerPromotionRuntimeError(
            "goal-manager promotion requires a committed assignment"
        )
    if assignment.partition != "validation":
        raise GoalManagerPromotionRuntimeError(
            "goal-manager promotion accepts validation contexts only"
        )
    if not isinstance(capture, GoalManagerContextCapture):
        raise TypeError("capture must be a verified goal-manager context capture")
    context = context_catalog.entry(assignment.slot_id)
    if (
        context.assignment_id != assignment.assignment_id
        or context.capture_id != capture.capture_id
        or context.state_sha256 != capture.state_sha256
        or context.envelope_sha256 != capture.envelope_sha256
    ):
        raise GoalManagerPromotionRuntimeError(
            "live promotion capture differs from the frozen context"
        )

    actions = CountingExecutor(action_delegate)
    observation = adapter.observe()
    binding_set = enumerator_factory(actions).enumerate(observation)
    if actions.actions_executed:
        raise GoalManagerPromotionRuntimeError(
            "goal-manager promotion enumeration attempted an action"
        )
    question = ordered_goal_manager_question(
        assignment_id=assignment.assignment_id,
        decision_index=0,
        situation=observation.situation,
        opportunities=binding_set.opportunities,
    )
    available_kinds = tuple(
        kind
        for kind in GoalKind
        if any(
            index in question.available_indices
            and opportunity.kind is kind
            for index, opportunity in enumerate(question.opportunities)
        )
    )
    if (
        question.ordered_policy_input_sha256 != context.question_sha256
        or question.policy_context_sha256 != context.policy_context_sha256
        or question.available_menu_sha256 != context.available_menu_sha256
        or tuple(item.kind for item in question.opportunities)
        != context.candidate_goal_kinds
        or available_kinds != context.available_goal_kinds
        or goal_binding_manifest_sha256(binding_set)
        != context.binding_manifest_sha256
    ):
        raise GoalManagerPromotionRuntimeError(
            "live promotion question differs from the frozen context"
        )

    policy = LearnedGoalManagerPolicy(
        model,
        confidence_threshold=(confidence_threshold if mode == "causal" else 0.0),
    )
    model_selection = policy.select(question)
    model_confidence = policy.minimum_confidence
    reference_index = context.selected_candidate_index
    selection_index = (
        model_selection.selected_index if mode == "causal" else reference_index
    )
    selected = (
        model_selection
        if mode == "causal"
        else bind_goal_selection(question, reference_index)
    )
    if selected.selected_index != selection_index:  # pragma: no cover - construction above
        raise AssertionError("goal-manager selected index did not bind")

    binding = binding_set.require(selected.binding_ref)
    report = binding.execute()
    if not isinstance(report, GoalExecutionReport):
        raise GoalManagerPromotionRuntimeError(
            "goal-manager promotion executor returned an invalid report"
        )
    verification = binding.verify(report)
    if not isinstance(verification, GoalVerification):
        raise GoalManagerPromotionRuntimeError(
            "goal-manager promotion verifier returned an invalid verdict"
        )
    if report.actions_executed != actions.actions_executed:
        raise GoalManagerPromotionRuntimeError(
            "goal-manager promotion action accounting differs from execution"
        )
    execution = GoalManagerExecutionResult(
        selected_kind=selected.kind,
        selected_candidate_index=selected.selected_index,
        execution=report,
        verification=verification,
        decision_recorded=False,
        outcome_recorded=False,
    )
    return GoalManagerPromotionContextResult(
        mode=mode,
        slot_id=assignment.slot_id,
        context_id=context.context_id,
        question_sha256=question.ordered_policy_input_sha256,
        policy_context_sha256=question.policy_context_sha256,
        reference_candidate_index=reference_index,
        reference_kind=context.selected_kind,
        model_candidate_index=model_selection.selected_index,
        model_kind=model_selection.kind,
        model_confidence=model_confidence,
        model_reference_agreement=model_selection.selected_index == reference_index,
        model_had_execution_authority=mode == "causal",
        reference_had_execution_authority=mode == "shadow",
        execution=execution,
    )


def summarize_goal_manager_promotion_results(
    *,
    mode: str,
    planned_contexts: int,
    results: tuple[GoalManagerPromotionContextResult, ...],
) -> GoalManagerPromotionBatchResult:
    if mode not in {"shadow", "causal"} or any(item.mode != mode for item in results):
        raise GoalManagerPromotionRuntimeError("goal-manager result modes differ")
    if (
        type(planned_contexts) is not int  # noqa: E721
        or planned_contexts < 1
        or len(results) != planned_contexts
        or len({item.slot_id for item in results}) != len(results)
        or len({item.context_id for item in results}) != len(results)
    ):
        raise GoalManagerPromotionRuntimeError("goal-manager result coverage differs")
    confidences = tuple(item.model_confidence for item in results)
    executions = tuple(item.execution.execution for item in results)
    if any(item is None for item in executions):  # pragma: no cover - runtime constructs them
        raise GoalManagerPromotionRuntimeError("goal-manager execution report is absent")
    reports = tuple(item for item in executions if item is not None)
    selected = Counter(item.execution.selected_kind.value for item in results)
    return GoalManagerPromotionBatchResult(
        mode=mode,
        planned_contexts=planned_contexts,
        evaluated_contexts=len(results),
        agreements=sum(item.model_reference_agreement for item in results),
        successful_contexts=sum(
            item.execution.verification.status is GoalDecisionOutcome.SUCCEEDED
            for item in results
        ),
        minimum_confidence=min(confidences),
        mean_confidence=sum(confidences) / len(confidences),
        actions_executed=sum(item.actions_executed for item in reports),
        frames_executed=sum(item.frames_executed for item in reports),
        selected_kind_counts=tuple(sorted(selected.items())),
        results=results,
    )


__all__ = [
    "GoalManagerPromotionBatchResult",
    "GoalManagerPromotionContextResult",
    "GoalManagerPromotionRuntimeError",
    "evaluate_goal_manager_promotion_context",
    "summarize_goal_manager_promotion_results",
]
