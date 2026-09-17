"""Actor-only three-head trainer policy trained on whole-party outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_control_features import BattleControlHistoryTracker
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario
from pokemon_red_completion.red_trainer_practice_features import (
    project_trainer_control_features,
    project_trainer_move_features,
    project_trainer_switch_features,
)
from pokemon_red_completion.red_trainer_practice_fit import TrainerPracticeThreeHeadModel


class TrainerOutcomePolicyError(ValueError):
    """A learned choice is not legal at the observed battle boundary."""


@dataclass(slots=True)
class RedTrainerPracticeOutcomePolicy:
    policy_id: str
    battle_plan_id: str
    model: TrainerPracticeThreeHeadModel
    catalog: PokemonRedBattleCatalog = field(default_factory=PokemonRedBattleCatalog)
    history: BattleControlHistoryTracker = field(default_factory=BattleControlHistoryTracker)
    last_decision_diagnostics: dict[str, object] = field(default_factory=dict, init=False)
    _unanswered_voluntary_switch_opponent: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not self.policy_id or not self.battle_plan_id:
            raise TrainerOutcomePolicyError("outcome policy identity is missing")

    def observe_forced_choice(
        self, observation: Mapping[str, object], action: BattleAction
    ) -> None:
        self.history.before(self.battle_plan_id, observation)
        self.history.advance(action, observation)

    def choose_main(
        self, observation: Mapping[str, object], prepared: PreparedRedBattleScenario
    ) -> BattleAction:
        history = self.history.before(self.battle_plan_id, observation)
        legal_moves = tuple(
            slot + 1
            for slot, legal in zip(
                prepared.features.slot_indices, prepared.supported_candidate_mask, strict=True
            )
            if legal
        )
        switch_masked = (
            bool(legal_moves)
            and self._unanswered_voluntary_switch_opponent == history.opponent_index
        )
        switches = (
            project_trainer_switch_features(observation, self.catalog)
            if _has_living_reserve(observation) and not switch_masked
            else None
        )
        if not legal_moves:
            if switches is None:
                raise TrainerOutcomePolicyError(
                    "Struggle/all-party attack depletion is outside the first trainer segment"
                )
            action = BattleAction.switch(self._choose_target(switches, switches.candidate_slots))
            self.last_decision_diagnostics["forced_by_legality"] = True
        else:
            control = tuple(
                project_trainer_control_features(
                    observation,
                    catalog=self.catalog,
                    move_batch=prepared.features,
                    history=history,
                ).tolist()
            )
            control_candidates = ((*(control), 1.0, 0.0), (*(control), 0.0, 1.0))
            if switches is None or self.model.control.predict_index(control_candidates) == 0:
                moves = project_trainer_move_features(observation, prepared.features)
                slots = tuple(slot for slot in moves.candidate_slots if slot in legal_moves)
                rows = tuple(
                    moves.candidate_vectors[moves.candidate_slots.index(slot)] for slot in slots
                )
                index = self.model.move.predict_index(rows)
                action = BattleAction.move(slots[index])
                self.last_decision_diagnostics = {
                    "decision_mode": "main",
                    "control_choice": "attack",
                    "move_candidate_slots": list(slots),
                    "move_probabilities": self.model.move.probabilities(rows).tolist(),
                    "switch_masked_until_attack": switch_masked,
                }
            else:
                action = BattleAction.switch(
                    self._choose_target(switches, switches.candidate_slots)
                )
                self.last_decision_diagnostics.update(
                    {
                        "decision_mode": "main",
                        "control_choice": "switch",
                    }
                )
            self.last_decision_diagnostics["control_probabilities"] = (
                self.model.control.probabilities(control_candidates).tolist()
            )
        if action.kind is BattleActionKind.SELECT_MOVE:
            self._unanswered_voluntary_switch_opponent = None
        elif action.kind is BattleActionKind.SWITCH:
            self._unanswered_voluntary_switch_opponent = history.opponent_index
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
        if forced == may_decline:
            raise TrainerOutcomePolicyError("switch mode differs")
        history = self.history.before(self.battle_plan_id, observation)
        if not legal_party_slots:
            if forced:
                raise TrainerOutcomePolicyError("forced switch has no legal target")
            self.last_decision_diagnostics = {
                "decision_mode": "prompt",
                "control_choice": "decline",
                "reason": "no_legal_target",
            }
            return None
        candidates = project_trainer_switch_features(observation, self.catalog)
        legal = tuple(slot for slot in candidates.candidate_slots if slot in legal_party_slots)
        if not legal:
            raise TrainerOutcomePolicyError("no legal switch candidate remains")
        if may_decline:
            control = tuple(
                project_trainer_control_features(
                    observation,
                    catalog=self.catalog,
                    history=history,
                ).tolist()
            )
            options = ((*(control), 1.0, 0.0), (*(control), 0.0, 1.0))
            probabilities = self.model.control.probabilities(options)
            if int(probabilities.argmax()) == 0:
                self.last_decision_diagnostics = {
                    "decision_mode": "prompt",
                    "control_choice": "decline",
                    "control_probabilities": probabilities.tolist(),
                }
                return None
        target = self._choose_target(candidates, legal)
        self.last_decision_diagnostics.update(
            {
                "decision_mode": "forced_switch" if forced else "prompt",
                "control_choice": "switch",
            }
        )
        self.history.advance(BattleAction.switch(target), observation)
        if not forced:
            self._unanswered_voluntary_switch_opponent = history.opponent_index
        return target

    def _choose_target(self, candidates, legal: tuple[int, ...]) -> int:
        slots = tuple(slot for slot in candidates.candidate_slots if slot in legal)
        rows = tuple(
            candidates.candidate_vectors[candidates.candidate_slots.index(slot)] for slot in slots
        )
        index = self.model.switch.predict_index(rows)
        self.last_decision_diagnostics = {
            "switch_candidate_slots": list(slots),
            "switch_probabilities": self.model.switch.probabilities(rows).tolist(),
        }
        return slots[index]


def _has_living_reserve(observation: Mapping[str, object]) -> bool:
    features = observation.get("features")
    party = features.get("party") if isinstance(features, Mapping) else None
    if not isinstance(party, Mapping):
        raise TrainerOutcomePolicyError("party observation is missing")
    members, active = party.get("members"), party.get("active_index")
    if not isinstance(members, list) or type(active) is not int:  # noqa: E721
        raise TrainerOutcomePolicyError("party inventory differs")
    return any(
        index != active
        and isinstance(member, Mapping)
        and type(member.get("hp")) is int
        and member["hp"] > 0
        for index, member in enumerate(members)
    )
