"""Actor-only three-head trainer policy trained on whole-party outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_control_features import BattleControlHistoryTracker
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario
from pokemon_red_completion.red_status_battle_features import project_for_head, status_choice_slots
from pokemon_red_completion.red_trainer_practice_features import (
    project_trainer_control_features,
    project_trainer_switch_features,
)
from pokemon_red_completion.red_trainer_practice_fit import (
    TrainerPracticeThreeHeadModel,
    control_action_candidates,
)
from pokemon_red_completion.red_trainer_proposed_control import (
    PROPOSED_CONTROL_SCHEMA,
    proposed_control,
)


class TrainerOutcomePolicyError(ValueError):
    """A learned choice is not legal at the observed battle boundary."""


@dataclass(slots=True)
class RedTrainerPracticeOutcomePolicy:
    policy_id: str
    battle_plan_id: str
    model: TrainerPracticeThreeHeadModel
    catalog: PokemonRedBattleCatalog = field(default_factory=PokemonRedBattleCatalog)
    history: BattleControlHistoryTracker = field(default_factory=BattleControlHistoryTracker)
    allow_immune_switch_recovery: bool = False
    last_decision_diagnostics: dict[str, object] = field(default_factory=dict, init=False)
    _unanswered_voluntary_switch_opponent: int | None = field(default=None, init=False)
    _immune_switch_escape_opponent: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not self.policy_id or not self.battle_plan_id:
            raise TrainerOutcomePolicyError("outcome policy identity is missing")
        if type(self.allow_immune_switch_recovery) is not bool:
            raise TrainerOutcomePolicyError("immune switch recovery must be explicit boolean")

    def observe_opponent_transition(self, before_position: int, after_position: int) -> None:
        """Consume an observed send-out event without exposing a hidden roster."""

        if before_position != after_position:
            self.history.note_opponent_replacement()

    def observe_forced_choice(
        self, observation: Mapping[str, object], action: BattleAction
    ) -> None:
        history = self.history.before(self.battle_plan_id, observation)
        features = observation.get("features")
        party = features.get("party") if isinstance(features, Mapping) else None
        lead = party.get("lead") if isinstance(party, Mapping) else None
        hp = lead.get("hp") if isinstance(lead, Mapping) else None
        if type(hp) is not int or hp < 0:  # noqa: E721
            raise TrainerOutcomePolicyError("forced-choice lead HP is invalid")
        if action.kind is BattleActionKind.SWITCH and hp > 0:
            self._unanswered_voluntary_switch_opponent = history.opponent_index
        elif action.kind is BattleActionKind.SELECT_MOVE:
            self._unanswered_voluntary_switch_opponent = None
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
        damage_reference = getattr(self.model, "damage_reference", None)
        if damage_reference is not None:
            projected = project_for_head(observation, prepared.features, self.model.move)
            legal_moves = status_choice_slots(projected, legal_moves, damage_reference)
        switch_masked = (
            bool(legal_moves)
            and self._unanswered_voluntary_switch_opponent == history.opponent_index
        )
        immune_recovery_offered = (
            self.allow_immune_switch_recovery
            and switch_masked
            and _has_living_reserve(observation)
            and _all_supported_attacks_immune(prepared)
        )
        if immune_recovery_offered:
            if self._immune_switch_escape_opponent == history.opponent_index:
                raise TrainerOutcomePolicyError("immune switch recovery budget exhausted")
            # Expose the normal learned choice once; do not select a target or
            # replace the model's attack. The ordinary anti-loop guard is unchanged.
            switch_masked = False
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
                ).tolist()
            )
            control_candidates = control_action_candidates(control)
            proposal = None
            # No control prediction is needed when switching is impossible.
            if self.model.control.schema_id == PROPOSED_CONTROL_SCHEMA and switches is not None:
                proposal = proposed_control(
                    observation,
                    catalog=self.catalog,
                    move_head=self.model.move,
                    switch_head=self.model.switch,
                    move_batch=prepared.features,
                    move_slots=legal_moves,
                    switch_slots=switches.candidate_slots,
                )
                control_candidates = proposal.candidate_vectors
            if switches is None or self.model.control.predict_index(control_candidates) == 0:
                moves = project_for_head(observation, prepared.features, self.model.move)
                slots = tuple(slot for slot in moves.candidate_slots if slot in legal_moves)
                rows = tuple(
                    moves.candidate_vectors[moves.candidate_slots.index(slot)] for slot in slots
                )
                index = self.model.move.predict_index(rows)
                action = BattleAction.move(slots[index])
                self.last_decision_diagnostics = {
                    "decision_mode": "main",
                    "control_choice": "attack",
                    "move_input_schema": moves.schema_id,
                    "move_candidate_slots": list(slots),
                    "move_candidate_vectors": [list(row) for row in rows],
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
                if switches is not None or self.model.control.schema_id != PROPOSED_CONTROL_SCHEMA
                else [1.0, 0.0]
            )
            self.last_decision_diagnostics["control_input_schema"] = self.model.control.schema_id
            self.last_decision_diagnostics["control_candidate_vectors"] = (
                [list(row) for row in control_candidates]
                if switches is not None or self.model.control.schema_id != PROPOSED_CONTROL_SCHEMA
                else []
            )
            if proposal is not None:
                self.last_decision_diagnostics["proposed_move_slot"] = proposal.move_slot
                self.last_decision_diagnostics["proposed_switch_slot"] = proposal.switch_slot
        if action.kind is BattleActionKind.SELECT_MOVE:
            self._unanswered_voluntary_switch_opponent = None
        elif action.kind is BattleActionKind.SWITCH:
            self._unanswered_voluntary_switch_opponent = history.opponent_index
            if immune_recovery_offered:
                self._immune_switch_escape_opponent = history.opponent_index
        if self.allow_immune_switch_recovery:
            self.last_decision_diagnostics["immune_switch_recovery_offered"] = (
                immune_recovery_offered
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
                ).tolist()
            )
            options = control_action_candidates(control)
            if self.model.control.schema_id == PROPOSED_CONTROL_SCHEMA:
                proposal = proposed_control(
                    observation,
                    catalog=self.catalog,
                    move_head=self.model.move,
                    switch_head=self.model.switch,
                    move_batch=None,
                    move_slots=(),
                    switch_slots=legal,
                )
                options = proposal.candidate_vectors
            probabilities = self.model.control.probabilities(options)
            if int(probabilities.argmax()) == 0:
                self.last_decision_diagnostics = {
                    "decision_mode": "prompt",
                    "control_choice": "decline",
                    "control_input_schema": self.model.control.schema_id,
                    "control_candidate_vectors": [list(row) for row in options],
                    "control_probabilities": probabilities.tolist(),
                }
                return None
        target = self._choose_target(candidates, legal)
        self.last_decision_diagnostics.update(
            {
                "decision_mode": "forced_switch" if forced else "prompt",
                "control_choice": "switch",
                **(
                    {
                        "control_input_schema": self.model.control.schema_id,
                        "control_candidate_vectors": [list(row) for row in options],
                        "control_probabilities": probabilities.tolist(),
                    }
                    if may_decline
                    else {}
                ),
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
            "switch_input_schema": candidates.schema_id,
            "switch_candidate_slots": list(slots),
            "switch_candidate_vectors": [list(row) for row in rows],
            "switch_probabilities": self.model.switch.probabilities(rows).tolist(),
        }
        return slots[index]


def _all_supported_attacks_immune(prepared: PreparedRedBattleScenario) -> bool:
    """Only ordinary damaging moves with explicit zero effectiveness qualify.

    Fixed-damage/status/zero-power mechanics are deliberately not inferred here.
    Unsupported or PP-depleted alternatives cannot falsely count as usable.
    """
    batch = prepared.features
    names = batch.feature_names
    relevant = tuple(
        row
        for row, allowed in zip(
            batch.candidate_vectors, prepared.supported_candidate_mask, strict=True
        )
        if allowed
    )
    return bool(relevant) and all(
        row[names.index("move.power_fraction")] > 0
        and row[names.index("move.type_effectiveness_fraction")] == 0
        and row[names.index("move.category.status")] == 0
        and row[names.index("move.effect.fixed_damage")] == 0
        for row in relevant
    )


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
