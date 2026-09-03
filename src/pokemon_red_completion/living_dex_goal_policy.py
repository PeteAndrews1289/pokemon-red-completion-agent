"""Shadow bridge from the learned living-Dex value model to semantic goals.

The causal living-Dex learner predicts separate success, progress, cost, and
safety outcomes for portable collection options.  The bounded player consumes
``GoalManagerQuestion`` objects.  This module connects those two title-neutral
interfaces without exposing binding references or granting the small model
unrestricted control.

Recovery, restoration, critical storage, and critical supply remain
deterministic safety decisions.  Every other supported choice is projected into
the same living-Dex feature vocabulary used by the causal learner and scored
with one explicit, immutable utility contract.  The policy is intentionally
shadow-only until held Red outcomes demonstrate an advantage over the
deterministic completion-first manager.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum

from pokemon_red_completion.goal_manager import (
    BoundGoalSelection,
    GoalAvailability,
    GoalKind,
    GoalManagerQuestion,
    bind_goal_selection,
)
from pokemon_red_completion.goal_manager_runtime import CompletionFirstGoalTeacher
from pokemon_red_completion.living_dex_option_value import (
    LIVING_DEX_OPTION_OUTCOME_NAMES,
    LivingDexOptionAvailability,
    LivingDexOptionCandidate,
    LivingDexOptionKind,
    LivingDexOptionMenu,
    LivingDexOptionUtility,
    LivingDexOptionValueModel,
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.red_living_dex_setup_policy import (
    red_living_dex_setup_candidate_features,
)


class LivingDexGoalPolicyError(ValueError):
    """A semantic question cannot cross the living-Dex shadow boundary."""


class LivingDexGoalDecisionMode(StrEnum):
    """Why the hybrid policy returned one semantic goal."""

    MODEL_SHADOW = "model_shadow"
    DETERMINISTIC_SAFETY = "deterministic_safety"
    DETERMINISTIC_UNSUPPORTED = "deterministic_unsupported"


_SHA256 = re.compile(r"[0-9a-f]{64}")


_OPTION_BY_GOAL = {
    GoalKind.ADVANCE_STORY: LivingDexOptionKind.UNLOCK_ACCESS,
    GoalKind.ACQUIRE_SPECIES: LivingDexOptionKind.ACQUIRE,
    GoalKind.DEVELOP_TEAM: LivingDexOptionKind.DEVELOP,
    GoalKind.EVOLVE_SPECIES: LivingDexOptionKind.EVOLVE,
    GoalKind.RESUPPLY: LivingDexOptionKind.RESUPPLY,
    GoalKind.MANAGE_STORAGE: LivingDexOptionKind.MANAGE_STORAGE,
    GoalKind.EXPLORE: LivingDexOptionKind.EXPLORE,
}

# Benefits dominate routine cost, while irreversible loss is as important as
# verified success.  These weights are fixed policy governance, not fitted
# parameters and not tuned on development outcomes.
DEFAULT_LIVING_DEX_GOAL_UTILITY = LivingDexOptionUtility(
    success_weight=4.0,
    completion_gain_weight=4.0,
    dependency_unlock_weight=3.0,
    action_cost_weight=0.20,
    frame_cost_weight=0.10,
    resource_cost_weight=0.50,
    party_cost_weight=1.0,
    storage_cost_weight=0.50,
    irreversible_loss_weight=4.0,
)


@dataclass(frozen=True, slots=True)
class LivingDexGoalCandidateScore:
    """One path-free shadow prediction aligned to the original goal menu."""

    goal_kind: GoalKind
    goal_candidate_index: int
    utility: float
    predicted_outcomes: tuple[float, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.goal_kind, GoalKind):
            raise LivingDexGoalPolicyError("shadow score goal kind differs")
        if type(self.goal_candidate_index) is not int or self.goal_candidate_index < 0:  # noqa: E721
            raise LivingDexGoalPolicyError("shadow score candidate index differs")
        if not isinstance(self.utility, float) or not math.isfinite(self.utility):
            raise LivingDexGoalPolicyError("shadow utility is not finite")
        if (
            not isinstance(self.predicted_outcomes, tuple)
            or len(self.predicted_outcomes) != 9
            or any(
                not isinstance(value, float) or not math.isfinite(value)
                for value in self.predicted_outcomes
            )
        ):
            raise LivingDexGoalPolicyError("shadow outcome prediction differs")

    def public_dict(self) -> dict[str, object]:
        return {
            "goal_candidate_index": self.goal_candidate_index,
            "goal_kind": self.goal_kind.value,
            "predicted_outcomes": dict(
                zip(
                    LIVING_DEX_OPTION_OUTCOME_NAMES,
                    self.predicted_outcomes,
                    strict=True,
                )
            ),
            "utility": self.utility,
        }


@dataclass(frozen=True, slots=True)
class LivingDexGoalShadowDecision:
    """Auditable choice made without title or private binding identity."""

    mode: LivingDexGoalDecisionMode
    selected_kind: GoalKind
    selected_candidate_index: int
    model_sha256: str
    menu_sha256: str | None
    scores: tuple[LivingDexGoalCandidateScore, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.mode, LivingDexGoalDecisionMode):
            raise LivingDexGoalPolicyError("shadow decision mode differs")
        if not isinstance(self.selected_kind, GoalKind):
            raise LivingDexGoalPolicyError("shadow selected kind differs")
        if type(self.selected_candidate_index) is not int or self.selected_candidate_index < 0:  # noqa: E721
            raise LivingDexGoalPolicyError("shadow selected index differs")
        if not isinstance(self.model_sha256, str) or _SHA256.fullmatch(self.model_sha256) is None:
            raise LivingDexGoalPolicyError("shadow model identity differs")
        if self.mode is LivingDexGoalDecisionMode.MODEL_SHADOW:
            if not isinstance(self.menu_sha256, str) or _SHA256.fullmatch(self.menu_sha256) is None:
                raise LivingDexGoalPolicyError("shadow menu identity differs")
            if not self.scores or self.selected_kind not in {
                item.goal_kind for item in self.scores
            }:
                raise LivingDexGoalPolicyError("shadow model scores differ")
        elif self.menu_sha256 is not None or self.scores:
            raise LivingDexGoalPolicyError("deterministic choice retained model output")

    def public_dict(self) -> dict[str, object]:
        return {
            "binding_identity_fields": 0,
            "menu_sha256": self.menu_sha256,
            "mode": self.mode.value,
            "model_sha256": self.model_sha256,
            "private_path_fields": 0,
            "scores": [item.public_dict() for item in self.scores],
            "selected_candidate_index": self.selected_candidate_index,
            "selected_kind": self.selected_kind.value,
        }


@dataclass(slots=True)
class LivingDexGoalShadowPolicy:
    """Use causal outcome predictions only inside a deterministic safety shell."""

    model: LivingDexOptionValueModel
    utility: LivingDexOptionUtility = DEFAULT_LIVING_DEX_GOAL_UTILITY
    safety: CompletionFirstGoalTeacher = field(default_factory=CompletionFirstGoalTeacher)
    decisions: int = field(default=0, init=False)
    model_decisions: int = field(default=0, init=False)
    deterministic_decisions: int = field(default=0, init=False)
    last_decision: LivingDexGoalShadowDecision | None = field(default=None, init=False)
    _decision_history: list[LivingDexGoalShadowDecision] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.model, LivingDexOptionValueModel):
            raise TypeError("living-Dex shadow policy needs an option-value model")
        if not isinstance(self.utility, LivingDexOptionUtility):
            raise TypeError("living-Dex shadow policy needs a utility contract")
        if not isinstance(self.safety, CompletionFirstGoalTeacher):
            raise TypeError("living-Dex shadow policy needs a deterministic safety policy")

    @property
    def decision_history(self) -> tuple[LivingDexGoalShadowDecision, ...]:
        """Return every decision in order without exposing a mutable log."""

        return tuple(self._decision_history)

    def select(self, question: GoalManagerQuestion) -> BoundGoalSelection:
        if not isinstance(question, GoalManagerQuestion):
            raise TypeError("question must be a GoalManagerQuestion")
        deterministic = self.safety.select(question)
        deterministic_safety_gate = (
            deterministic.kind in {GoalKind.RECOVER_CONTROL, GoalKind.RESTORE_TEAM}
            or (
                deterministic.kind is GoalKind.MANAGE_STORAGE
                and question.situation.storage_pressure >= self.safety.storage_gate
            )
            or (
                deterministic.kind is GoalKind.RESUPPLY
                and question.situation.resource_pressure >= self.safety.resource_gate
            )
        )
        if deterministic_safety_gate:
            return self._record_deterministic(
                question,
                deterministic,
                LivingDexGoalDecisionMode.DETERMINISTIC_SAFETY,
            )

        projected: list[tuple[int, GoalKind, LivingDexOptionCandidate]] = []
        context = living_dex_option_context_from_goal_situation(question.situation)
        for index in question.available_indices:
            opportunity = question.opportunities[index]
            option_kind = _OPTION_BY_GOAL.get(opportunity.kind)
            if option_kind is None:
                continue
            if (
                opportunity.availability is not GoalAvailability.AVAILABLE
                or opportunity.estimated_effort is None
                or opportunity.estimated_risk is None
            ):
                raise LivingDexGoalPolicyError("available goal lacks bounded estimates")
            features = red_living_dex_setup_candidate_features(
                option_kind,
                # The goal-manager boundary has a bounded aggregate effort but
                # no separately measured route.  Do not invent route actions or
                # double-charge the aggregate estimate in shadow scoring.
                route_controller_actions=0,
                maximum_controller_actions=1,
                estimated_effort=opportunity.estimated_effort,
                estimated_risk=opportunity.estimated_risk,
                storage_unit=question.situation.storage_pressure,
            )
            projected.append(
                (
                    index,
                    opportunity.kind,
                    LivingDexOptionCandidate(
                        binding_ref=f"policy-row-{len(projected)}",
                        features=features,
                        availability=LivingDexOptionAvailability.AVAILABLE,
                    ),
                )
            )
        if len(projected) < 2:
            return self._record_deterministic(
                question,
                deterministic,
                LivingDexGoalDecisionMode.DETERMINISTIC_UNSUPPORTED,
            )

        menu = LivingDexOptionMenu(context, tuple(item[2] for item in projected))
        utilities = self.model.scores(menu, self.utility)
        scored: list[LivingDexGoalCandidateScore] = []
        for menu_index, (question_index, kind, candidate) in enumerate(projected):
            utility = utilities[menu_index]
            if utility is None or not math.isfinite(utility):
                raise LivingDexGoalPolicyError("living-Dex model returned an invalid score")
            outcome = self.model.predict_candidate(context, candidate)
            scored.append(
                LivingDexGoalCandidateScore(
                    goal_kind=kind,
                    goal_candidate_index=question_index,
                    utility=float(utility),
                    predicted_outcomes=outcome.vector(),
                )
            )
        selected = max(scored, key=lambda item: (item.utility, item.goal_kind.value))
        bound = bind_goal_selection(question, selected.goal_candidate_index)
        self.decisions += 1
        self.model_decisions += 1
        decision = LivingDexGoalShadowDecision(
            mode=LivingDexGoalDecisionMode.MODEL_SHADOW,
            selected_kind=bound.kind,
            selected_candidate_index=bound.selected_index,
            model_sha256=self.model.model_sha256,
            menu_sha256=menu.policy_sha256,
            scores=tuple(scored),
        )
        self.last_decision = decision
        self._decision_history.append(decision)
        return bound

    def _record_deterministic(
        self,
        question: GoalManagerQuestion,
        selection: BoundGoalSelection,
        mode: LivingDexGoalDecisionMode,
    ) -> BoundGoalSelection:
        rebound = bind_goal_selection(question, selection.selected_index)
        if rebound != selection:
            raise LivingDexGoalPolicyError("deterministic choice belongs to another question")
        self.decisions += 1
        self.deterministic_decisions += 1
        decision = LivingDexGoalShadowDecision(
            mode=mode,
            selected_kind=selection.kind,
            selected_candidate_index=selection.selected_index,
            model_sha256=self.model.model_sha256,
            menu_sha256=None,
            scores=(),
        )
        self.last_decision = decision
        self._decision_history.append(decision)
        return selection


__all__ = [
    "DEFAULT_LIVING_DEX_GOAL_UTILITY",
    "LivingDexGoalCandidateScore",
    "LivingDexGoalDecisionMode",
    "LivingDexGoalPolicyError",
    "LivingDexGoalShadowDecision",
    "LivingDexGoalShadowPolicy",
]
