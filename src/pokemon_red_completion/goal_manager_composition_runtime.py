"""Bounded three-decision composition around the existing goal-manager seams.

The promoted model chooses only a high-level goal.  Existing bindings execute that choice, an
independent verifier settles it, and the adapter must reobserve changed semantic and collection
state before the next choice.  This module adds no teacher, route, registry, or fitting path.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pokemon_red_completion.goal_manager import GoalKind, GoalSituation
from pokemon_red_completion.goal_manager_model import (
    GoalManagerLinearModel,
    LearnedGoalManagerPolicy,
    canonical_goal_manager_model_record_sha256,
)
from pokemon_red_completion.goal_manager_runtime import (
    GoalBindingSet,
    GoalManagerExecutionResult,
    execute_goal_manager_decision,
)
from pokemon_red_completion.goal_manager_trajectory import GoalManagerTrajectoryObserver

FRESH_COMPOSITION_DECISIONS = 3
FRESH_COMPOSITION_CONFIDENCE_FLOOR = 0.80
FRESH_COMPOSITION_ACTIONS_PER_DECISION = 6_000
FRESH_COMPOSITION_FRAMES_PER_DECISION = 600_000
FRESH_COMPOSITION_MAX_ACTIONS = 18_000
FRESH_COMPOSITION_MAX_FRAMES = 1_800_000
FRESH_COMPOSITION_REQUIRED_KINDS = frozenset(
    {
        GoalKind.ACQUIRE_SPECIES,
        GoalKind.EXPLORE,
        GoalKind.RESTORE_TEAM,
    }
)
FROZEN_RED_GOAL_MANAGER_SHA256 = (
    "af29d7e7f72e9921e638c88664b17e6fbbf6334468609ab66bda41c9f3dad66d"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class GoalManagerCompositionError(RuntimeError):
    """Raised when a fresh composition episode crosses its frozen boundary."""


@dataclass(frozen=True, slots=True)
class LivingCollectionCheckpoint:
    """Minimal title-neutral collection facts needed by the composition gate."""

    registered_species: int
    living_species: int
    required_specimens_remaining: int
    retained_captures: int
    undeclared_specimen_losses: int
    completion_contract_sha256: str
    specimen_ledger_sha256: str
    required_specimens_sha256: str
    specimen_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        for name in (
            "registered_species",
            "living_species",
            "required_specimens_remaining",
            "retained_captures",
            "undeclared_specimen_losses",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise GoalManagerCompositionError(
                    f"composition collection {name} must be a non-negative integer"
                )
        for name in (
            "completion_contract_sha256",
            "specimen_ledger_sha256",
            "required_specimens_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise GoalManagerCompositionError(
                    f"composition collection {name} is invalid"
                )
        if (
            not isinstance(self.specimen_counts, tuple)
            or not self.specimen_counts
            or tuple(sorted(self.specimen_counts)) != self.specimen_counts
            or len({species for species, _count in self.specimen_counts})
            != len(self.specimen_counts)
            or any(
                not isinstance(species, str)
                or not species
                or type(count) is not int  # noqa: E721
                or count <= 0
                for species, count in self.specimen_counts
            )
        ):
            raise GoalManagerCompositionError(
                "composition specimen counts must be a sorted positive inventory"
            )
        if sum(count for _species, count in self.specimen_counts) < self.living_species:
            raise GoalManagerCompositionError(
                "composition specimen inventory is smaller than its living count"
            )

    def public_dict(self) -> dict[str, object]:
        return {
            "completion_contract_sha256": self.completion_contract_sha256,
            "registered_species": self.registered_species,
            "living_species": self.living_species,
            "required_specimens_remaining": self.required_specimens_remaining,
            "retained_captures": self.retained_captures,
            "required_specimens_sha256": self.required_specimens_sha256,
            "specimen_ledger_sha256": self.specimen_ledger_sha256,
            "total_living_specimens": sum(
                count for _species, count in self.specimen_counts
            ),
            "undeclared_specimen_losses": self.undeclared_specimen_losses,
        }


@dataclass(frozen=True, slots=True)
class GoalManagerCompositionObservation:
    """One action-free adapter observation and its currently executable menu."""

    semantic_state_sha256: str
    situation: GoalSituation
    binding_set: GoalBindingSet
    collection: LivingCollectionCheckpoint

    def __post_init__(self) -> None:
        if (
            not isinstance(self.semantic_state_sha256, str)
            or _SHA256.fullmatch(self.semantic_state_sha256) is None
        ):
            raise GoalManagerCompositionError("composition semantic state digest is invalid")
        if not isinstance(self.situation, GoalSituation):
            raise TypeError("situation must be a GoalSituation")
        if not isinstance(self.binding_set, GoalBindingSet):
            raise TypeError("binding_set must be a GoalBindingSet")
        if not isinstance(self.collection, LivingCollectionCheckpoint):
            raise TypeError("collection must be a LivingCollectionCheckpoint")
        opportunities = self.binding_set.opportunities
        if len(opportunities) != len(GoalKind) or {item.kind for item in opportunities} != set(
            GoalKind
        ):
            raise GoalManagerCompositionError(
                "composition observation must enumerate all nine goal kinds"
            )


@dataclass(frozen=True, slots=True)
class CompositionBudgetCheckpoint:
    """Independent cumulative controller and emulator accounting."""

    controller_actions: int
    emulator_frames: int

    def __post_init__(self) -> None:
        for name in ("controller_actions", "emulator_frames"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:  # noqa: E721
                raise GoalManagerCompositionError(
                    f"composition budget {name} must be a non-negative integer"
                )


@runtime_checkable
class CompositionBudgetMeter(Protocol):
    """Trusted counter bound by the eventual root-safe execution runner."""

    def checkpoint(self) -> CompositionBudgetCheckpoint: ...


@dataclass(frozen=True, slots=True)
class GoalManagerCompositionStep:
    """Path-free public facts for one model-controlled verified decision."""

    decision_ordinal: int
    available_goal_count: int
    selected_kind: GoalKind
    confidence: float
    actions_executed: int
    frames_executed: int
    semantic_state_changed: bool
    collection_before: LivingCollectionCheckpoint
    collection_after: LivingCollectionCheckpoint
    policy_context_sha256: str
    available_menu_sha256: str

    def public_dict(self) -> dict[str, object]:
        return {
            "actions_executed": self.actions_executed,
            "available_goal_count": self.available_goal_count,
            "available_menu_sha256": self.available_menu_sha256,
            "collection_after": self.collection_after.public_dict(),
            "collection_before": self.collection_before.public_dict(),
            "confidence": self.confidence,
            "decision_ordinal": self.decision_ordinal,
            "frames_executed": self.frames_executed,
            "policy_context_sha256": self.policy_context_sha256,
            "selected_kind": self.selected_kind.value,
            "semantic_state_changed": self.semantic_state_changed,
        }


@dataclass(frozen=True, slots=True)
class GoalManagerCompositionResult:
    """Successful result of the frozen three-choice composition contract."""

    model_sha256: str
    steps: tuple[GoalManagerCompositionStep, ...]
    policy_context_changes: int
    available_menu_changes: int

    def public_dict(self) -> dict[str, object]:
        total_actions = sum(step.actions_executed for step in self.steps)
        total_frames = sum(step.frames_executed for step in self.steps)
        return {
            "available_menu_changes": self.available_menu_changes,
            "core_contract_only": True,
            "decisions": len(self.steps),
            "execution_receipt_required": True,
            "fixed_dispatches": 0,
            "minimum_confidence": min(step.confidence for step in self.steps),
            "model_sha256": self.model_sha256,
            "policy_context_changes": self.policy_context_changes,
            "private_binding_fields": 0,
            "private_path_fields": 0,
            "schema": "pokemon.red.fresh-goal-manager-composition-result.v1",
            "selected_goal_kinds": [step.selected_kind.value for step in self.steps],
            "status": "core_composition_contract_satisfied",
            "steps": [step.public_dict() for step in self.steps],
            "total_actions": total_actions,
            "total_frames": total_frames,
        }


CompositionObserver = Callable[[], GoalManagerCompositionObservation]


def run_goal_manager_composition_episode(
    *,
    observe: CompositionObserver,
    policy: LearnedGoalManagerPolicy,
    trajectory: GoalManagerTrajectoryObserver,
    budget_meter: CompositionBudgetMeter,
) -> GoalManagerCompositionResult:
    """Run exactly three learned choices, stopping on the first contract failure."""

    if not callable(observe):
        raise TypeError("observe must be callable")
    if type(policy) is not LearnedGoalManagerPolicy:  # noqa: E721
        raise TypeError("policy must be a LearnedGoalManagerPolicy")
    if type(policy.model) is not GoalManagerLinearModel:  # noqa: E721
        raise TypeError("composition requires the frozen linear goal-manager model")
    if not isinstance(trajectory, GoalManagerTrajectoryObserver):
        raise TypeError("trajectory must be a GoalManagerTrajectoryObserver")
    if not isinstance(budget_meter, CompositionBudgetMeter):
        raise TypeError("budget_meter must be a CompositionBudgetMeter")
    if (
        policy.decisions != 0
        or policy.learned_choice_decisions != 0
        or policy.fixed_dispatch_decisions != 0
        or not math.isfinite(policy.confidence_total)
        or policy.confidence_total != 0.0
        or not math.isfinite(policy.minimum_confidence)
        or policy.minimum_confidence != 1.0
    ):
        raise GoalManagerCompositionError("composition policy must start unused")
    if not math.isclose(
        policy.confidence_threshold,
        FRESH_COMPOSITION_CONFIDENCE_FLOOR,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise GoalManagerCompositionError("composition confidence floor differs from the design")
    if trajectory.next_decision_index != 0 or trajectory.pending_decision is not None:
        raise GoalManagerCompositionError("composition trajectory must start empty")

    model_sha256 = canonical_goal_manager_model_record_sha256(policy.model.to_dict())
    if model_sha256 != FROZEN_RED_GOAL_MANAGER_SHA256:
        raise GoalManagerCompositionError("composition model differs from the frozen design")
    initial_budget = budget_meter.checkpoint()
    current = _require_observation(observe())
    if budget_meter.checkpoint() != initial_budget:
        raise GoalManagerCompositionError("composition observation attempted emulator work")
    initial_collection = current.collection
    initial_kinds = {binding.kind for binding in current.binding_set.bindings}
    if not FRESH_COMPOSITION_REQUIRED_KINDS.issubset(initial_kinds):
        raise GoalManagerCompositionError(
            "composition root lacks the frozen field-composition menu"
        )
    steps: list[GoalManagerCompositionStep] = []
    policy_contexts: list[str] = []
    available_menus: list[str] = []
    total_actions = 0
    total_frames = 0
    last_budget = initial_budget

    for decision_index in range(FRESH_COMPOSITION_DECISIONS):
        question = trajectory.ordered_question(
            current.situation,
            current.binding_set.opportunities,
        )
        available_count = len(question.available_indices)
        if available_count < 2:
            raise GoalManagerCompositionError(
                "composition decision does not expose two executable goals"
            )
        if policy_contexts and question.policy_context_sha256 == policy_contexts[-1]:
            raise GoalManagerCompositionError(
                "composition policy context did not change before the next action"
            )
        if (
            decision_index == FRESH_COMPOSITION_DECISIONS - 1
            and available_menus
            and all(
                left == right
                for left, right in zip(
                    (*available_menus, question.available_menu_sha256),
                    (*available_menus, question.available_menu_sha256)[1:],
                    strict=False,
                )
            )
        ):
            raise GoalManagerCompositionError(
                "composition available menu never changed before the final action"
            )
        prior_total = policy.confidence_total
        final_decision = decision_index == FRESH_COMPOSITION_DECISIONS - 1

        def guard(selection: object, *, final_decision: bool = final_decision) -> None:
            selected_kind = getattr(selection, "kind", None)
            already_selected = {step.selected_kind for step in steps}
            if selected_kind not in FRESH_COMPOSITION_REQUIRED_KINDS:
                raise GoalManagerCompositionError(
                    "composition model selected outside the frozen field contract"
                )
            if selected_kind in already_selected:
                raise GoalManagerCompositionError(
                    "composition model repeated a selected goal kind"
                )
            if (
                final_decision
                and GoalKind.ACQUIRE_SPECIES not in already_selected
                and selected_kind is not GoalKind.ACQUIRE_SPECIES
            ):
                raise GoalManagerCompositionError(
                    "composition final choice cannot satisfy the acquisition contract"
                )

        try:
            execution = execute_goal_manager_decision(
                situation=current.situation,
                binding_set=current.binding_set,
                authority=policy,
                trajectory=trajectory,
                require_durable_decision=True,
                selection_guard=guard,
            )
        except Exception as error:
            raise GoalManagerCompositionError(
                "composition policy or selected binding failed"
            ) from error
        _require_success(execution)
        confidence = policy.confidence_total - prior_total
        if confidence < FRESH_COMPOSITION_CONFIDENCE_FLOOR:
            raise GoalManagerCompositionError("composition confidence is below the frozen floor")
        if execution.execution is None:  # pragma: no cover - guaranteed by successful runtime
            raise GoalManagerCompositionError("composition execution report is absent")
        reported_actions = execution.execution.actions_executed
        reported_frames = execution.execution.frames_executed
        before_budget = last_budget
        after = _require_observation(observe())
        after_budget = budget_meter.checkpoint()
        actions = after_budget.controller_actions - before_budget.controller_actions
        frames = after_budget.emulator_frames - before_budget.emulator_frames
        if actions < 0 or frames < 0:
            raise GoalManagerCompositionError("composition budget counters regressed")
        if actions != reported_actions or frames != reported_frames:
            raise GoalManagerCompositionError(
                "composition report differs from independent budget accounting"
            )
        if (
            actions > FRESH_COMPOSITION_ACTIONS_PER_DECISION
            or frames > FRESH_COMPOSITION_FRAMES_PER_DECISION
        ):
            raise GoalManagerCompositionError("composition decision exceeded its frozen budget")
        total_actions += actions
        total_frames += frames
        if (
            total_actions > FRESH_COMPOSITION_MAX_ACTIONS
            or total_frames > FRESH_COMPOSITION_MAX_FRAMES
        ):
            raise GoalManagerCompositionError("composition episode exceeded its frozen budget")
        _require_collection_transition(
            current.collection,
            after.collection,
            selected_kind=execution.selected_kind,
        )
        state_changed = after.semantic_state_sha256 != current.semantic_state_sha256
        if not state_changed:
            raise GoalManagerCompositionError("composition skill did not change semantic state")
        if execution.selected_kind is GoalKind.ACQUIRE_SPECIES and (
            after.collection.retained_captures
            - current.collection.retained_captures
            < 1
            or after.collection.required_specimens_remaining
            >= current.collection.required_specimens_remaining
        ):
            raise GoalManagerCompositionError(
                "composition acquisition did not retain a required specimen"
            )
        policy_contexts.append(question.policy_context_sha256)
        available_menus.append(question.available_menu_sha256)
        steps.append(
            GoalManagerCompositionStep(
                decision_ordinal=decision_index + 1,
                available_goal_count=available_count,
                selected_kind=execution.selected_kind,
                confidence=confidence,
                actions_executed=actions,
                frames_executed=frames,
                semantic_state_changed=state_changed,
                collection_before=current.collection,
                collection_after=after.collection,
                policy_context_sha256=question.policy_context_sha256,
                available_menu_sha256=question.available_menu_sha256,
            )
        )
        current = after
        last_budget = after_budget

    trajectory.require_settled()
    selected = tuple(step.selected_kind for step in steps)
    if set(selected) != FRESH_COMPOSITION_REQUIRED_KINDS:
        raise GoalManagerCompositionError(
            "composition did not select the three frozen field goal kinds"
        )
    acquisition = next(
        step for step in steps if step.selected_kind is GoalKind.ACQUIRE_SPECIES
    )
    if (
        acquisition.collection_after.retained_captures
        - acquisition.collection_before.retained_captures
        < 1
        or acquisition.collection_after.required_specimens_remaining
        >= acquisition.collection_before.required_specimens_remaining
    ):
        raise GoalManagerCompositionError(
            "composition acquisition step did not retain a required specimen"
        )
    if (
        current.collection.retained_captures - initial_collection.retained_captures < 1
        or current.collection.required_specimens_remaining
        >= initial_collection.required_specimens_remaining
        or current.collection.living_species < initial_collection.living_species
        or current.collection.registered_species < initial_collection.registered_species
    ):
        raise GoalManagerCompositionError("composition did not retain a verified acquisition")
    policy_changes = sum(
        left != right
        for left, right in zip(policy_contexts, policy_contexts[1:], strict=False)
    )
    menu_changes = sum(
        left != right
        for left, right in zip(available_menus, available_menus[1:], strict=False)
    )
    if policy_changes != FRESH_COMPOSITION_DECISIONS - 1 or menu_changes < 1:
        raise GoalManagerCompositionError("composition did not replan from changed policy state")
    if (
        policy.decisions != FRESH_COMPOSITION_DECISIONS
        or policy.learned_choice_decisions != FRESH_COMPOSITION_DECISIONS
        or policy.fixed_dispatch_decisions != 0
        or trajectory.next_decision_index != FRESH_COMPOSITION_DECISIONS
    ):
        raise GoalManagerCompositionError("composition authority accounting is invalid")
    return GoalManagerCompositionResult(
        model_sha256=model_sha256,
        steps=tuple(steps),
        policy_context_changes=policy_changes,
        available_menu_changes=menu_changes,
    )


def _require_observation(value: object) -> GoalManagerCompositionObservation:
    if not isinstance(value, GoalManagerCompositionObservation):
        raise GoalManagerCompositionError("composition observer returned an invalid value")
    return value


def _require_success(result: GoalManagerExecutionResult) -> None:
    if (
        not isinstance(result, GoalManagerExecutionResult)
        or not result.passed
        or not result.decision_recorded
        or not result.outcome_recorded
    ):
        raise GoalManagerCompositionError(
            "composition decision did not produce a verified durable success"
        )


def _require_collection_transition(
    before: LivingCollectionCheckpoint,
    after: LivingCollectionCheckpoint,
    *,
    selected_kind: GoalKind,
) -> None:
    before_specimens = dict(before.specimen_counts)
    after_specimens = dict(after.specimen_counts)
    lost_specimens = sum(
        max(0, count - after_specimens.get(species, 0))
        for species, count in before_specimens.items()
    )
    if (
        after.registered_species < before.registered_species
        or after.living_species < before.living_species
        or after.required_specimens_remaining > before.required_specimens_remaining
        or after.retained_captures < before.retained_captures
        or after.undeclared_specimen_losses != 0
        or before.undeclared_specimen_losses != 0
        or after.completion_contract_sha256 != before.completion_contract_sha256
        or lost_specimens
    ):
        raise GoalManagerCompositionError("composition collection state regressed")
    collection_changed = any(
        left != right
        for left, right in (
            (before.registered_species, after.registered_species),
            (before.living_species, after.living_species),
            (before.required_specimens_remaining, after.required_specimens_remaining),
            (before.retained_captures, after.retained_captures),
            (before.specimen_counts, after.specimen_counts),
        )
    )
    ledger_changed = before.specimen_ledger_sha256 != after.specimen_ledger_sha256
    if collection_changed != ledger_changed:
        raise GoalManagerCompositionError(
            "composition specimen ledger does not match the collection transition"
        )
    required_digest_changed = (
        before.required_specimens_sha256 != after.required_specimens_sha256
    )
    if selected_kind in {GoalKind.ACQUIRE_SPECIES, GoalKind.EVOLVE_SPECIES}:
        if not ledger_changed or not required_digest_changed:
            raise GoalManagerCompositionError(
                "composition collection goal did not change its authenticated ledgers"
            )
    elif (
        collection_changed
        or required_digest_changed
        or before.required_specimens_remaining != after.required_specimens_remaining
    ):
        raise GoalManagerCompositionError(
            "composition non-collection goal changed the required-specimen ledger"
        )
