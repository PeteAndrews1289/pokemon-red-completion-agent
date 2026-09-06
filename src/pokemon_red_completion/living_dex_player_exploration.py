"""Prospective, fully logged exploration over the existing goal-value learner.

Safety and unsupported choices remain deterministic and explicitly ineligible
for full-support outcome fitting. This policy does not execute the game.
"""

from __future__ import annotations

import math
import random
from copy import deepcopy
from dataclasses import dataclass, field, replace

from pokemon_red_completion.goal_manager import (
    BoundGoalSelection,
    GoalKind,
    GoalManagerQuestion,
    bind_goal_selection,
)
from pokemon_red_completion.living_dex_goal_policy import (
    LivingDexGoalDecisionMode,
    LivingDexGoalShadowPolicy,
)

EXPLORATION_POLICY_ID = "living-dex-player-full-support-v1"
DETERMINISTIC_POLICY_ID = "living-dex-player-nontraining-v1"


@dataclass(slots=True)
class ExploringLivingDexGoalPolicy(LivingDexGoalShadowPolicy):
    """Sample once from a 25% uniform / 75% model-softmax mixture.

    Seed and policy identity belong in the prospective run header. Exact
    probabilities belong in the durable decision before any controller input.
    A sample is not a greedy model prediction and must be displayed as such.
    """

    seed: int = 0
    _rng: random.Random = field(init=False, repr=False)
    _metadata: dict[str, object] | None = field(default=None, init=False, repr=False)
    training_eligible: bool = field(default=False, init=False)
    option_probabilities: tuple[float, ...] = field(default=(), init=False)
    last_question_sha256: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        LivingDexGoalShadowPolicy.__post_init__(self)
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("exploration seed must be a non-negative integer")
        self._rng = random.Random(self.seed)

    def select(self, question: GoalManagerQuestion) -> BoundGoalSelection:
        if any(
            question.opportunities[index].kind is GoalKind.RESUPPLY
            and question.opportunities[index].resource_quote is None
            for index in question.available_indices
        ):
            raise ValueError("native player exploration requires quoted resupply costs")
        self._metadata = None
        self.training_eligible = False
        self.option_probabilities = ()
        self.last_question_sha256 = question.ordered_policy_input_sha256
        greedy = LivingDexGoalShadowPolicy.select(self, question)
        decision = self.last_decision
        assert decision is not None
        probabilities = [0.0] * len(question.opportunities)
        base_probability = 1.0
        mix = 0.0
        selected_index = greedy.selected_index
        if decision.mode is LivingDexGoalDecisionMode.MODEL_SHADOW and set(
            self.last_menu_indices
        ) == set(question.available_indices):
            utilities = [item.utility for item in decision.scores]
            peak = max(utilities)
            exponentials = [math.exp(value - peak) for value in utilities]
            total = sum(exponentials)
            base = [value / total for value in exponentials]
            mix = 0.25
            mixed = [(1.0 - mix) * value + mix / len(base) for value in base]
            position = self._rng.choices(range(len(mixed)), weights=mixed, k=1)[0]
            selected_index = self.last_menu_indices[position]
            base_probability = base[position]
            for index, probability in zip(self.last_menu_indices, mixed, strict=True):
                probabilities[index] = probability
            self.option_probabilities = tuple(mixed)
            self.training_eligible = True
            self.last_decision = replace(
                decision,
                selected_candidate_index=selected_index,
                selected_kind=question.opportunities[selected_index].kind,
            )
            self._decision_history[-1] = self.last_decision
        else:
            probabilities[selected_index] = 1.0
        self._metadata = {
            "schema": "pokemon.core.goal-manager-behavior-policy.v1",
            "behavior_policy_id": EXPLORATION_POLICY_ID
            if self.training_eligible
            else DETERMINISTIC_POLICY_ID,
            "candidate_probabilities": probabilities,
            "selected_probability": probabilities[selected_index],
            "base_selected_probability": base_probability,
            "exploration_mix": mix,
            "temperature": 1.0,
        }
        return bind_goal_selection(question, selected_index)

    def selection_metadata(self) -> dict[str, object]:
        if self._metadata is None:
            raise ValueError("no exploration decision has been selected")
        return deepcopy(self._metadata)
