"""Uncalibrated training probe: one forward choice, then one frozen-policy tail.

This composition is deliberately not native outcome-training authority. The
forward return describes a first action followed by the fitted old continuation;
it is never recursively treated as an optimal action value.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, field

from .forward_goal import ForwardGoalPlan
from .forward_goal_learning import ForwardGoalModel, ForwardGoalPrediction
from .goal_manager import BoundGoalSelection, GoalManagerQuestion, bind_goal_selection
from .goal_manager_composition_runtime import CompositionBudgetCheckpoint, CompositionBudgetMeter
from .living_dex_goal_policy import LivingDexGoalDecisionMode, LivingDexGoalShadowPolicy
from .living_dex_option_value import LivingDexOptionValueModel, option_feature_names
from .living_dex_player_exploration import ExploringLivingDexGoalPolicy, exploration_policy_id

FORWARD_FIRST_CHOICE_POLICY_ID = "forward-first-choice-training-probe-v1"


@dataclass(slots=True)
class FirstChoiceForwardTrainingPolicy:
    """Choose once with learned forward estimates, without calibrated authority.

    The append callback must durably retain each record before returning. Its
    durability is an owner responsibility; uncertain writes poison this actor.
    Singleton steps are the runtime's responsibility and must not call ``select``.
    """

    forward_model: ForwardGoalModel
    fitted_plan: ForwardGoalPlan
    tail_model: LivingDexOptionValueModel
    tail_seed: int
    observe_context: Callable[[], tuple[float, ...]]
    meter: CompositionBudgetMeter
    append_decision: Callable[[dict[str, object]], None]
    training_probe: bool
    _tail: ExploringLivingDexGoalPolicy = field(init=False, repr=False)
    _forward_sha256: str = field(init=False, repr=False)
    _tail_sha256: str = field(init=False, repr=False)
    _metadata: dict[str, object] | None = field(default=None, init=False, repr=False)
    _poisoned: bool = field(default=False, init=False)
    _selecting: bool = field(default=False, init=False, repr=False)
    _decisions: int = field(default=0, init=False)
    _forward_decisions: int = field(default=0, init=False)
    _tail_decisions: int = field(default=0, init=False)
    _last_checkpoint: CompositionBudgetCheckpoint | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        if self.training_probe is not True:
            raise ValueError("forward first-choice authority is training-probe-only")
        if (
            not isinstance(self.forward_model, ForwardGoalModel)
            or not isinstance(self.fitted_plan, ForwardGoalPlan)
            or self.forward_model.contract != self.fitted_plan.contract
            or self.fitted_plan.max_macros != 2
            or self.forward_model.candidate_names != option_feature_names(3)
        ):
            raise ValueError("forward first-choice fitted contract or features differ")
        if (
            not isinstance(self.tail_model, LivingDexOptionValueModel)
            or self.tail_model.feature_version != 3
        ):
            raise ValueError("forward first-choice tail requires a v3 model")
        if type(self.tail_seed) is not int or self.tail_seed < 0:
            raise ValueError("forward first-choice tail seed must be a nonnegative integer")
        if not callable(self.observe_context) or not callable(self.append_decision):
            raise ValueError("forward first-choice requires observation and durable append")
        if not isinstance(self.meter, CompositionBudgetMeter):
            raise ValueError("forward first-choice requires an independent budget meter")
        self._forward_sha256 = self.forward_model.sha256
        self._tail_sha256 = self.tail_model.model_sha256
        self._tail = ExploringLivingDexGoalPolicy(self.tail_model, seed=self.tail_seed)

    @property
    def training_eligible(self) -> bool:
        """Never impersonate the existing sampled-native fitting contract."""
        return False

    @property
    def poisoned(self) -> bool:
        return self._poisoned

    @property
    def decisions(self) -> int:
        return self._decisions

    @property
    def forward_decisions(self) -> int:
        return self._forward_decisions

    @property
    def tail_decisions(self) -> int:
        return self._tail_decisions

    def _checkpoint(self) -> CompositionBudgetCheckpoint:
        checkpoint = self.meter.checkpoint()
        if not isinstance(checkpoint, CompositionBudgetCheckpoint):
            raise ValueError("forward first-choice budget checkpoint differs")
        return checkpoint

    def select(self, question: GoalManagerQuestion) -> BoundGoalSelection:
        if self._poisoned or self._selecting or self._decisions >= 2:
            self._poisoned = True
            raise ValueError("forward first-choice policy is poisoned or exhausted")
        self._selecting = True
        self._metadata = None
        try:
            before = self._checkpoint()
            if self._last_checkpoint is not None and (
                before.controller_actions < self._last_checkpoint.controller_actions
                or before.emulator_frames < self._last_checkpoint.emulator_frames
            ):
                raise ValueError("forward first-choice budget counters moved backwards")
            if not isinstance(question, GoalManagerQuestion) or len(question.available_indices) < 2:
                raise ValueError("forward first-choice needs a genuine multiple-option question")
            if (
                self.forward_model.sha256 != self._forward_sha256
                or self.tail_model.model_sha256 != self._tail_sha256
            ):
                raise ValueError("forward first-choice frozen model changed")
            if self._decisions == 0:
                selection, metadata, details = self._first(question)
                role = "forward_first"
            else:
                selection = self._tail.select(question)
                metadata = self._tail.selection_metadata()
                details = {}
                role = "frozen_tail"
            record: dict[str, object] = {
                "schema": "pokemon.core.forward-first-choice-probe-decision.v1",
                "role": role,
                "authority": "uncalibrated-training-probe",
                "decision_ordinal": self._decisions + 1,
                "forward_model_sha256": self._forward_sha256,
                "fitted_plan_sha256": self.fitted_plan.sha256,
                "fitted_continuation_sha256": self.fitted_plan.continuation_sha256,
                "tail_model_sha256": self._tail_sha256,
                "tail_policy_id": exploration_policy_id(3),
                "tail_seed": self.tail_seed,
                "question_sha256": question.ordered_policy_input_sha256,
                "selected_candidate_index": selection.selected_index,
                "selection_metadata": deepcopy(metadata),
                **details,
            }
            if self._checkpoint() != before:
                raise ValueError("forward first-choice observation or prediction performed actions")
            self.append_decision(deepcopy(record))
            if self._checkpoint() != before:
                raise ValueError("forward first-choice decision append performed actions")
            if self._poisoned:
                raise ValueError("forward first-choice reentrant decision poisoned actor")
            self._metadata = deepcopy(metadata)
            self._last_checkpoint = before
            self._decisions += 1
            self._forward_decisions += int(role == "forward_first")
            self._tail_decisions += int(role == "frozen_tail")
            return selection
        except BaseException:
            self._poisoned = True
            raise
        finally:
            self._selecting = False

    def _first(
        self,
        question: GoalManagerQuestion,
    ) -> tuple[BoundGoalSelection, dict[str, object], dict[str, object]]:
        before = self._checkpoint()
        projection = LivingDexGoalShadowPolicy(self.tail_model)
        projection.select(question)  # Recommendation ignored; only safety/menu is reused.
        if self._checkpoint() != before:
            raise ValueError("forward first-choice projection performed actions")
        if (
            projection.last_decision is None
            or projection.last_decision.mode is not LivingDexGoalDecisionMode.MODEL_SHADOW
            or projection.last_menu is None
            or projection.last_menu_indices != question.available_indices
        ):
            raise ValueError("forward first-choice safety or incomplete projected menu")
        context = self.observe_context()
        if self._checkpoint() != before:
            raise ValueError("forward first-choice observation performed actions")
        candidates = tuple(
            projection.last_menu.candidate_vector(i, feature_version=3)
            for i in range(len(projection.last_menu.candidates))
        )
        predictions = self.forward_model.predict(
            plan=self.fitted_plan,
            context_names=self.forward_model.context_names,
            context=context,
            candidate_names=option_feature_names(3),
            candidates=candidates,
        )
        if (
            not isinstance(predictions, tuple)
            or len(predictions) != len(candidates)
            or any(not isinstance(value, ForwardGoalPrediction) for value in predictions)
        ):
            raise ValueError("forward first-choice predictions do not cover the complete menu")
        index = max(
            range(len(predictions)),
            key=lambda i: (predictions[i].completion, -predictions[i].cost, -i),
        )
        selected = projection.last_menu_indices[index]
        probabilities = [float(i == selected) for i in range(len(question.opportunities))]
        metadata: dict[str, object] = {
            "schema": "pokemon.core.goal-manager-behavior-policy.v1",
            "behavior_policy_id": FORWARD_FIRST_CHOICE_POLICY_ID,
            "candidate_probabilities": probabilities,
            "selected_probability": 1.0,
            "base_selected_probability": 1.0,
            "exploration_mix": 0.0,
            "temperature": 1.0,
        }
        details: dict[str, object] = {
            "selection_rule": "maximum-completion-then-minimum-cost-then-menu-index",
            "context_names": list(self.forward_model.context_names),
            "context": list(context),
            "candidate_names": list(option_feature_names(3)),
            "candidates": [list(candidate) for candidate in candidates],
            "menu_question_indices": list(projection.last_menu_indices),
            "predictions": [
                {"completion": value.completion, "cost": value.cost} for value in predictions
            ],
            "selected_menu_index": index,
        }
        return bind_goal_selection(question, selected), metadata, details

    def selection_metadata(self) -> dict[str, object]:
        if self._metadata is None or self._poisoned:
            raise ValueError("no durable forward first-choice decision is available")
        return deepcopy(self._metadata)
