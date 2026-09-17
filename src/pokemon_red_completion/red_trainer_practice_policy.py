"""Compose validated learner heads for trainer-practice attack/switch authority."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from pokemon_red_completion.battle_actions import BattleAction
from pokemon_red_completion.battle_control_features import (
    CONTROL_CLASS_REFS,
    BattleControlHistoryTracker,
    project_control_features,
)
from pokemon_red_completion.battle_semantics import BattleFeatureBatch
from pokemon_red_completion.battle_switch_target import (
    BattleSwitchTargetSet,
    project_switch_target_candidates,
)
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario


class MoveRanker(Protocol):
    def predict(self, candidate_features, *, legal_mask, current_pp) -> int: ...


class ControlClassifier(Protocol):
    def predict_ref(self, features) -> str: ...


class SwitchRanker(Protocol):
    def probabilities(self, observation: BattleSwitchTargetSet): ...


class TrainerPracticeModelPolicyError(ValueError):
    """A learned head requested an unsupported or unavailable trainer action."""


@dataclass(slots=True)
class RedTrainerPracticeModelPolicy:
    """Three model heads own control class, move slot, and switch target.

    The Red adapter validates every selected action before touching a button.
    Recovery, boosts, capture, and flee remain outside this attack/switch lab
    and fail closed rather than silently asking a teacher to decide.
    """

    policy_id: str
    battle_plan_id: str
    move_model: MoveRanker
    control_model: ControlClassifier
    switch_model: SwitchRanker
    catalog: PokemonRedBattleCatalog = field(default_factory=PokemonRedBattleCatalog)
    history: BattleControlHistoryTracker = field(default_factory=BattleControlHistoryTracker)

    def __post_init__(self) -> None:
        if not self.policy_id or not self.battle_plan_id:
            raise TrainerPracticeModelPolicyError("trainer model identity is missing")

    def choose_main(
        self,
        observation: Mapping[str, object],
        prepared: PreparedRedBattleScenario,
    ) -> BattleAction:
        history = self.history.before(self.battle_plan_id, observation)
        features = project_control_features(
            observation,
            move_batch=prepared.features,
            history=history,
            catalog=self.catalog,
        )
        control_ref = self.control_model.predict_ref(features)
        if control_ref == CONTROL_CLASS_REFS[0]:
            action = self._attack(prepared.features)
        elif control_ref == CONTROL_CLASS_REFS[5]:
            action = BattleAction.switch(self._target(observation, None))
        else:
            raise TrainerPracticeModelPolicyError(
                f"trainer model requested unsupported class {control_ref!r}"
            )
        self.history.advance(action, observation)
        return action

    def choose_switch(
        self,
        observation: Mapping[str, object],
        legal_party_slots: tuple[int, ...],
        *,
        forced: bool,
        may_decline: bool,
    ) -> int | None:
        if forced is may_decline:
            raise TrainerPracticeModelPolicyError("trainer switch decision mode is inconsistent")
        history = self.history.before(self.battle_plan_id, observation)
        if not forced:
            features = project_control_features(
                observation,
                history=history,
                catalog=self.catalog,
            )
            control_ref = self.control_model.predict_ref(features)
            if control_ref == CONTROL_CLASS_REFS[0]:
                return None
            if control_ref != CONTROL_CLASS_REFS[5]:
                raise TrainerPracticeModelPolicyError(
                    f"trainer prompt model requested unsupported class {control_ref!r}"
                )
        target = self._target(observation, legal_party_slots)
        self.history.advance(BattleAction.switch(target), observation)
        return target

    def _attack(self, features: BattleFeatureBatch) -> BattleAction:
        index = self.move_model.predict(
            features.candidate_vectors,
            legal_mask=features.legal_mask,
            current_pp=features.current_pp,
        )
        if (
            type(index) is not int  # noqa: E721
            or not 0 <= index < len(features.slot_indices)
            or not features.legal_mask[index]
            or features.current_pp[index] <= 0
        ):
            raise TrainerPracticeModelPolicyError("trainer move model selected an illegal slot")
        return BattleAction.move(features.slot_indices[index] + 1)

    def _target(
        self, observation: Mapping[str, object], legal_party_slots: tuple[int, ...] | None
    ) -> int:
        candidates = project_switch_target_candidates(observation, self.catalog)
        probabilities = np.asarray(self.switch_model.probabilities(candidates), dtype=np.float64)
        if probabilities.shape != (len(candidates.candidates),) or not np.all(
            np.isfinite(probabilities)
        ):
            raise TrainerPracticeModelPolicyError("trainer switch model probabilities are invalid")
        eligible = tuple(
            index
            for index, candidate in enumerate(candidates.candidates)
            if legal_party_slots is None or candidate.party_slot in legal_party_slots
        )
        if not eligible:
            raise TrainerPracticeModelPolicyError("trainer switch model has no legal target")
        chosen = max(eligible, key=lambda index: (probabilities[index], -index))
        return candidates.candidates[chosen].party_slot
