"""Actor-only three-head trainer policy trained on whole-party outcomes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar

from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_control_features import BattleControlHistoryTracker
from pokemon_red_completion.battle_semantics import BattleFeatureProjector
from pokemon_red_completion.red_battle_catalog import PokemonRedBattleCatalog
from pokemon_red_completion.wild_training_objective import WildTrainingObjective
from pokemon_red_completion.red_battle_mechanics_boundary import (
    capped_stat_choices,
    immunity_choices,
    productive_reserve_slots,
)
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
    switch_guard_revision: ClassVar[str | None] = "attack-obligation-v2"
    policy_id: str
    battle_plan_id: str
    model: TrainerPracticeThreeHeadModel
    catalog: PokemonRedBattleCatalog = field(default_factory=PokemonRedBattleCatalog)
    history: BattleControlHistoryTracker = field(default_factory=BattleControlHistoryTracker)
    allow_immune_switch_recovery: bool = False
    mechanics_aware_choices: bool = False
    pp_depleted_switch_screen: bool = False
    diagnostic_stay_when_productive: bool = False
    diagnostic_status_release: bool = False
    diagnostic_prompt_stay: bool = False
    screen_capped_status_moves: bool = False
    allow_model_struggle: bool = False
    training_objective: WildTrainingObjective | None = None
    last_decision_diagnostics: dict[str, object] = field(default_factory=dict, init=False)
    _unanswered_voluntary_switch_opponent: int | None = field(default=None, init=False)
    _immune_switch_escape_opponent: int | None = field(default=None, init=False)
    _mechanics_escape_opponent: int | None = field(default=None, init=False)
    _mechanics_escaped_members: set[int] = field(default_factory=set, init=False)
    _pp_depleted_members: set[int] = field(default_factory=set, init=False)
    _unsupported_move_members: dict[int, tuple[tuple[int, str], ...]] = field(
        default_factory=dict, init=False
    )

    def __post_init__(self) -> None:
        if self.training_objective is not None and type(self.training_objective) is not WildTrainingObjective:
            raise TrainerOutcomePolicyError("typed selected wild training objective required")
        if not self.policy_id or not self.battle_plan_id:
            raise TrainerOutcomePolicyError("outcome policy identity is missing")
        if type(self.allow_model_struggle) is not bool or (
            self.allow_model_struggle
            and not (self.mechanics_aware_choices and self.pp_depleted_switch_screen)
        ):
            raise TrainerOutcomePolicyError("model Struggle requires explicit scoped mechanics")
        if type(self.screen_capped_status_moves) is not bool or (
            self.screen_capped_status_moves and not self.mechanics_aware_choices
        ):
            raise TrainerOutcomePolicyError("Capped status screen requires explicit mechanics")
        if type(self.allow_immune_switch_recovery) is not bool:
            raise TrainerOutcomePolicyError("immune switch recovery must be explicit boolean")
        if type(self.mechanics_aware_choices) is not bool:
            raise TrainerOutcomePolicyError("mechanics boundary must be explicit boolean")
        if type(self.pp_depleted_switch_screen) is not bool:
            raise TrainerOutcomePolicyError("PP reentry screen must be explicit boolean")
        if type(self.diagnostic_stay_when_productive) is not bool or (
            self.diagnostic_stay_when_productive and not self.mechanics_aware_choices
        ):
            raise TrainerOutcomePolicyError("diagnostic stay requires explicit mechanics boundary")
        if type(self.diagnostic_status_release) is not bool or (
            self.diagnostic_status_release and not self.diagnostic_stay_when_productive
        ):
            raise TrainerOutcomePolicyError("status release requires explicit diagnostic stay")
        if type(self.diagnostic_prompt_stay) is not bool or (
            self.diagnostic_prompt_stay and not self.diagnostic_stay_when_productive
        ):
            raise TrainerOutcomePolicyError("prompt stay requires explicit diagnostic stay")

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
        elif action.kind in {BattleActionKind.SELECT_MOVE, BattleActionKind.STRUGGLE}:
            self._unanswered_voluntary_switch_opponent = None
        self.history.advance(action, observation)

    def _pending_attack_masked(self, history, prepared, legal_moves):
        # An opposing switch is not our attack. Preserve the obligation across
        # replacements, except the existing all-immune new-opponent escape.
        return (
            bool(legal_moves)
            and self._unanswered_voluntary_switch_opponent is not None
            and (
                self._unanswered_voluntary_switch_opponent == history.opponent_index
                or not _all_supported_attacks_immune(prepared)
            )
        )

    def choose_main(
        self, observation: Mapping[str, object], prepared: PreparedRedBattleScenario
    ) -> BattleAction:
        history = self.history.before(self.battle_plan_id, observation)
        if self.allow_model_struggle and _semantic_struggle_available(observation):
            return self._choose_model_struggle(observation, history)
        legal_moves = tuple(
            slot + 1
            for slot, legal in zip(
                prepared.features.slot_indices, prepared.supported_candidate_mask, strict=True
            )
            if legal
        )
        mechanically_removed = ()
        productive_reserves = ()
        # Diagnostic-only intervention: leave move ranking and forced replacements
        # untouched. This is supplied control, never evidence of learned control.
        names = prepared.features.feature_names
        productive_attack = (
            any(
                row[names.index("move.power_fraction")] > 0
                and row[names.index("move.category.status")] == 0
                and row[names.index("move.effect.fixed_damage")] == 0
                and row[names.index("move.type_effectiveness_fraction")] > 0
                for slot, row in zip(
                    prepared.features.slot_indices, prepared.features.candidate_vectors, strict=True
                )
                if slot + 1 in legal_moves
            )
            if self.diagnostic_stay_when_productive
            else False
        )
        if self.mechanics_aware_choices:
            legal_moves, productive_reserves, mechanically_removed = immunity_choices(
                observation, prepared, self.catalog, legal_moves
            )
        capped_removed = ()
        if self.screen_capped_status_moves:
            legal_moves, capped_removed = capped_stat_choices(
                observation, self.catalog, legal_moves
            )
        damage_reference = getattr(self.model, "damage_reference", None)
        if damage_reference is not None:
            projected = project_for_head(observation, prepared.features, self.model.move)
            legal_moves = status_choice_slots(projected, legal_moves, damage_reference)
        switch_masked = self._pending_attack_masked(history, prepared, legal_moves)
        if productive_reserves:
            # Escape only to a reserve with usable nonimmune ordinary damage.
            # The next ordinary attack boundary restores the existing anti-loop rule.
            switch_masked = False
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
        switch_slots = (
            tuple(s for s in switches.candidate_slots if s in productive_reserves)
            if switches is not None and productive_reserves
            else (() if switches is None else switches.candidate_slots)
        )
        if self.mechanics_aware_choices:
            switch_slots = self._mechanics_switch_slots(observation, switch_slots, history)
            if not switch_slots:
                switches = None
        unsupported_removed = ()
        if self.pp_depleted_switch_screen:
            screened = self._unsupported_switch_slots(observation, switch_slots)
            # Keep the last escape if nobody has an executable move. Do not
            # manufacture an attack or turn this screen into a forced target.
            if legal_moves or screened:
                unsupported_removed = tuple(s for s in switch_slots if s not in screened)
                switch_slots = screened
                if not switch_slots:
                    switches = None
        depleted_removed = ()
        if self.pp_depleted_switch_screen:
            screened = self._pp_switch_slots(observation, switch_slots)
            # Never create an all-party-depletion dead end. Mandatory native
            # replacements are also kept outside this voluntary reentry screen.
            if legal_moves or screened:
                depleted_removed = tuple(s for s in switch_slots if s not in screened)
                switch_slots = screened
                if not switch_slots:
                    switches = None
        if not legal_moves:
            if switches is None:
                raise TrainerOutcomePolicyError(
                    "Struggle/all-party attack depletion is outside the first trainer segment"
                )
            action = BattleAction.switch(self._choose_target(switches, switch_slots))
            self.last_decision_diagnostics[
                "forced_by_mechanics" if mechanically_removed else "forced_by_legality"
            ] = True
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
                    switch_slots=switch_slots,
                )
                control_candidates = proposal.candidate_vectors
            learned_control_index = (
                self.model.control.predict_index(control_candidates) if switches is not None else 0
            )
            status_release = False
            if self.diagnostic_status_release and switches is not None:
                proposed_slot = (
                    proposal.switch_slot
                    if proposal is not None
                    else switch_slots[
                        self.model.switch.predict_index(
                            tuple(
                                switches.candidate_vectors[switches.candidate_slots.index(s)]
                                for s in switch_slots
                            )
                        )
                    ]
                )
                features = observation.get("features")
                party = features.get("party") if isinstance(features, Mapping) else None
                battle = features.get("battle") if isinstance(features, Mapping) else None
                lead = party.get("lead") if isinstance(party, Mapping) else None
                members = party.get("members") if isinstance(party, Mapping) else None
                context = battle.get("status_context", {}) if isinstance(battle, Mapping) else None
                if (
                    not isinstance(lead, Mapping)
                    or not isinstance(members, (tuple, list))
                    or not isinstance(context, Mapping)
                    or not 1 <= proposed_slot <= len(members)
                    or not isinstance(members[proposed_slot - 1], Mapping)
                ):
                    raise TrainerOutcomePolicyError(
                        "diagnostic status release needs coherent party state"
                    )
                impaired = (
                    lead.get("status") == "paralysis" or context.get("player_confused") is True
                )
                reserve = members[proposed_slot - 1]
                status_release = (
                    impaired
                    and reserve.get("status") is None
                    and proposed_slot in productive_reserve_slots(observation, self.catalog)
                )
            diagnostic_stay = (
                self.diagnostic_stay_when_productive and productive_attack and not status_release
            )
            if switches is None or diagnostic_stay or learned_control_index == 0:
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
                action = BattleAction.switch(self._choose_target(switches, switch_slots))
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
            if self.diagnostic_stay_when_productive:
                diagnostic_control = {
                    "schema": "pokemon.red.diagnostic-stay.v1",
                    "supplied_not_learned": True,
                    "productive_attack_available": productive_attack,
                    "forced_attack": diagnostic_stay,
                    "overrode_learned_switch": diagnostic_stay and learned_control_index == 1,
                }
                if self.diagnostic_status_release:
                    diagnostic_control.update(
                        {
                            "schema": "pokemon.red.diagnostic-stay.status-release.v1",
                            "status_release_eligible": status_release,
                            "released_learned_switch": status_release
                            and learned_control_index == 1,
                        }
                    )
                self.last_decision_diagnostics["diagnostic_control"] = diagnostic_control
        if action.kind is BattleActionKind.SELECT_MOVE:
            self._unanswered_voluntary_switch_opponent = None
        elif action.kind is BattleActionKind.SWITCH:
            self._unanswered_voluntary_switch_opponent = history.opponent_index
            if immune_recovery_offered:
                self._immune_switch_escape_opponent = history.opponent_index
            if self.pp_depleted_switch_screen and not legal_moves:
                active = observation["features"]["party"]["active_index"] + 1
                if self._supported_attacks_pp_depleted(observation, active):
                    self._pp_depleted_members.add(active)
                if self._unsupported_moves_only(prepared):
                    self._unsupported_move_members[active] = self._member_move_signature(
                        observation, active
                    )
        if self.allow_immune_switch_recovery:
            self.last_decision_diagnostics["immune_switch_recovery_offered"] = (
                immune_recovery_offered
            )
        if self.mechanics_aware_choices:
            if action.kind is BattleActionKind.SWITCH and productive_reserves:
                self._mechanics_escaped_members.add(
                    observation["features"]["party"]["active_index"] + 1
                )
            self.last_decision_diagnostics["mechanics_boundary"] = {
                "schema": "pokemon.red.immunity-screen.v2",
                "removed_move_slots": list(mechanically_removed),
                "productive_reserve_slots": list(productive_reserves),
                "escaped_ineffective_members": sorted(self._mechanics_escaped_members),
                "supplied_rules_not_learned": True,
            }
        if self.switch_guard_revision is not None:
            self.last_decision_diagnostics["switch_guard_revision"] = self.switch_guard_revision
        self._record_pp_screen(depleted_removed)
        self._record_unsupported_screen(unsupported_removed)
        if self.screen_capped_status_moves:
            self.last_decision_diagnostics["capped_status_screen"] = {
                "schema": "pokemon.red.capped-stat-screen.v1",
                "removed_move_slots": list(capped_removed),
                "supplied_rules_not_learned": True,
            }
        self.history.advance(action, observation)
        return action

    def _choose_model_struggle(self, observation, history):
        """Rank a public zero-PP attack proposal against genuine living reserves.

        This is an action-specific feature view, never changed cartridge PP or a
        claimed learned move slot. The original observation remains untouched;
        the generic zero-PP move mask stays FALSE. The native executor separately
        proves four depleted slots before any controller input.
        """
        features = observation["features"]
        party = features["party"]
        projection = {
            **observation,
            "features": {
                **features,
                "party": {
                    **party,
                    "lead": {
                        **party["lead"],
                        "moves": [
                            {
                                "slot_index": 0,
                                "move_ref": "pokemon.red.gb.us.rev0:move:165",
                                "pp": 0,
                            }
                        ],
                    },
                },
                "battle": {**features["battle"], "player_disabled_move_slot": None},
            },
        }
        base = BattleFeatureProjector(self.catalog).project(projection)
        # Keep the existing post-switch attack obligation; Struggle now makes
        # that obligation executable rather than reopening an empty-PP loop.
        masked = self._unanswered_voluntary_switch_opponent is not None
        switches = (
            project_trainer_switch_features(observation, self.catalog)
            if _has_living_reserve(observation) and not masked
            else None
        )
        candidates = control_action_candidates(
            tuple(
                project_trainer_control_features(
                    projection, catalog=self.catalog, move_batch=base
                ).tolist()
            )
        )
        proposal = None
        if switches is not None and self.model.control.schema_id == PROPOSED_CONTROL_SCHEMA:
            proposal = proposed_control(
                projection,
                catalog=self.catalog,
                move_head=self.model.move,
                switch_head=self.model.switch,
                move_batch=base,
                move_slots=(1,),
                switch_slots=switches.candidate_slots,
            )
            candidates = proposal.candidate_vectors
        selected = self.model.control.predict_index(candidates) if switches is not None else 0
        if selected == 0:
            action = BattleAction.struggle()
            self.last_decision_diagnostics = {}
            self._unanswered_voluntary_switch_opponent = None
        else:
            action = BattleAction.switch(self._choose_target(switches, switches.candidate_slots))
            self._unanswered_voluntary_switch_opponent = history.opponent_index
        self.last_decision_diagnostics.update(
            {
                "decision_mode": "main",
                "control_choice": "struggle" if selected == 0 else "switch",
                "control_input_schema": self.model.control.schema_id,
            "control_candidate_vectors": (
                [list(row) for row in candidates]
                if switches is not None or self.model.control.schema_id != PROPOSED_CONTROL_SCHEMA
                else []
            ),
                "control_probabilities": self.model.control.probabilities(candidates).tolist()
                if switches is not None
                else [1.0, 0.0],
                "switch_masked_until_attack": masked,
                "struggle_proposal": {
                    "schema": "pokemon.red.model-struggle-proposal.v1",
                    "semantic_action": BattleAction.struggle().semantic_ref,
                    "public_move_ref": "pokemon.red.gb.us.rev0:move:165",
                    "pp_independent_native_action": True,
                    "source_visible_pp": [m["pp"] for m in party["lead"]["moves"]],
                    "projection_pp": list(base.current_pp),
                    "ordinary_move_legal_mask": list(base.legal_mask),
                    "candidate_vectors": [list(row) for row in base.candidate_vectors],
                    "observation_modified": False,
                    "supplied_action": False,
                },
            }
        )
        if proposal is not None:
            self.last_decision_diagnostics["proposed_switch_slot"] = proposal.switch_slot
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
            self._record_pp_screen(())
            return None
        candidates = project_trainer_switch_features(observation, self.catalog)
        legal = tuple(slot for slot in candidates.candidate_slots if slot in legal_party_slots)
        unsupported_removed = ()
        if self.pp_depleted_switch_screen and may_decline:
            screened = self._unsupported_switch_slots(observation, legal)
            unsupported_removed = tuple(s for s in legal if s not in screened)
            legal = screened
            if not legal:
                self.last_decision_diagnostics = {
                    "decision_mode": "prompt",
                    "control_choice": "decline",
                    "reason": "unsupported_move_reentry_guard",
                }
                self._record_pp_screen(())
                self._record_unsupported_screen(unsupported_removed)
                return None
        depleted_removed = ()
        if self.pp_depleted_switch_screen and may_decline:
            screened = self._pp_switch_slots(observation, legal)
            depleted_removed = tuple(s for s in legal if s not in screened)
            legal = screened
            if not legal:
                self.last_decision_diagnostics = {
                    "decision_mode": "prompt",
                    "control_choice": "decline",
                    "reason": "pp_depleted_reentry_guard",
                }
                self._record_pp_screen(depleted_removed)
                self._record_unsupported_screen(unsupported_removed)
                return None
        if self.mechanics_aware_choices and may_decline:
            legal = self._mechanics_switch_slots(observation, legal, history)
            if not legal:
                self.last_decision_diagnostics = {
                    "decision_mode": "prompt",
                    "control_choice": "decline",
                    "reason": "mechanics_ineffective_reentry_guard",
                }
                self._record_pp_screen(depleted_removed)
                self._record_unsupported_screen(unsupported_removed)
                return None
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
            learned_stay = int(probabilities.argmax()) == 0
            diagnostic_stay = self.diagnostic_prompt_stay and self._productive_prompt_lead(
                observation
            )
            if learned_stay or diagnostic_stay:
                self.last_decision_diagnostics = {
                    "decision_mode": "prompt",
                    "control_choice": "decline",
                    "control_input_schema": self.model.control.schema_id,
                    "control_candidate_vectors": [list(row) for row in options],
                    "control_probabilities": probabilities.tolist(),
                }
                if self.diagnostic_prompt_stay:
                    self.last_decision_diagnostics["diagnostic_control"] = {
                        "schema": "pokemon.red.diagnostic-prompt-stay.v1",
                        "supplied_not_learned": True,
                        "productive_attack_available": diagnostic_stay,
                        "forced_decline": diagnostic_stay,
                        "overrode_learned_switch": diagnostic_stay and not learned_stay,
                    }
                self._record_pp_screen(depleted_removed)
                self._record_unsupported_screen(unsupported_removed)
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
        self._record_pp_screen(depleted_removed)
        self._record_unsupported_screen(unsupported_removed)
        return target

    @staticmethod
    def _unsupported_moves_only(prepared):
        # These are the adapter's scope exclusions, not poor move values or
        # transient PP/Disable/immunity. Status-capable actors keep their moves.
        reasons = getattr(prepared, "unsupported_candidate_reasons", ())
        return bool(reasons) and all(reason in {
            "status_or_non_damaging_outside_segment",
            "counter_needs_prior_damage",
            "self_destruct_outside_segment",
        } for reason in reasons)

    @staticmethod
    def _member_move_signature(observation, slot):
        moves = observation["features"]["party"]["members"][slot - 1]["moves"]
        return tuple((m["slot_index"], m["move_ref"]) for m in moves)

    def _unsupported_switch_slots(self, observation, slots):
        # Remember only an observed no-move exit in this exact policy scope.
        # A legitimately changed moveset readmits the member; mandatory native
        # replacements never call this voluntary/prompt reentry screen.
        self._unsupported_move_members = {
            s: signature for s, signature in self._unsupported_move_members.items()
            if self._member_move_signature(observation, s) == signature
        }
        return tuple(s for s in slots if s not in self._unsupported_move_members)

    def _record_unsupported_screen(self, removed):
        if self.pp_depleted_switch_screen and (self._unsupported_move_members or removed):
            self.last_decision_diagnostics["unsupported_move_reentry_screen"] = {
                "schema": "pokemon.red.unsupported-move-reentry.v1",
                "removed_party_slots": list(removed),
                "observed_unsupported_members": sorted(self._unsupported_move_members),
                "supplied_rules_not_learned": True,
            }

    def _supported_attacks_pp_depleted(self, observation, slot):
        from .red_battle_scenario import red_battle_move_is_refreshable_model_supported

        member = observation["features"]["party"]["members"][slot - 1]
        attacks = tuple(
            m
            for m in member["moves"]
            if red_battle_move_is_refreshable_model_supported(
                int(m["move_ref"].rsplit(":", 1)[1]), catalog=self.catalog
            )
        )
        # Positive-PP attacks temporarily disabled, immunity and status-only
        # members are not PP depletion. Mark only an actually observed escape.
        return bool(attacks) and all(m["pp"] == 0 for m in attacks)

    def _pp_switch_slots(self, observation, slots):
        self._pp_depleted_members = {
            s
            for s in self._pp_depleted_members
            if self._supported_attacks_pp_depleted(observation, s)
        }
        return tuple(s for s in slots if s not in self._pp_depleted_members)

    def _record_pp_screen(self, removed):
        if self.training_objective is not None:
            self.last_decision_diagnostics["wild_training_objective"] = self.training_objective.diagnostics()
        if self.pp_depleted_switch_screen:
            self.last_decision_diagnostics["pp_depleted_switch_screen"] = {
                "schema": "pokemon.red.pp-depleted-reentry.v1",
                "removed_party_slots": list(removed),
                "observed_depleted_members": sorted(self._pp_depleted_members),
                "supplied_rules_not_learned": True,
            }

    def _productive_prompt_lead(self, observation) -> bool:
        """Optional development support only; never choose a replacement or a move."""
        party = observation["features"]["party"]
        battle = observation["features"]["battle"]
        lead = party["lead"]
        if lead["hp"] <= 0:
            return False
        if self.diagnostic_status_release and (
            lead.get("status") == "paralysis"
            or battle.get("status_context", {}).get("player_confused") is True
        ):
            return False
        foe = self.catalog.resolve_species(battle["opponent_species_ref"])
        disabled = battle.get("player_disabled_move_slot")
        for item in lead["moves"]:
            if item["slot_index"] + 1 == disabled:
                continue
            move = self.catalog.resolve_move(item["move_ref"])
            from .red_battle_scenario import red_battle_move_is_model_supported

            if (
                item["pp"] > 0
                and move.category != "status"
                and move.power > 0
                and "fixed_damage" not in move.effect_flags
                and red_battle_move_is_model_supported(
                    int(item["move_ref"].rsplit(":", 1)[1]), item["pp"], catalog=self.catalog
                )
                and self.catalog.type_effectiveness(move.type_name, foe.types) > 0
            ):
                return True
        return False

    def _mechanics_switch_slots(self, observation, slots, history):
        if self._mechanics_escape_opponent != history.opponent_index:
            self._mechanics_escape_opponent = history.opponent_index
            self._mechanics_escaped_members.clear()
        productive = productive_reserve_slots(observation, self.catalog)
        # This is an explicit anti-loop heuristic, not a claim that a status-only
        # reserve can never be tactically useful. Forced replacements stay legal.
        return tuple(
            s for s in slots if s not in self._mechanics_escaped_members or s in productive
        )

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


def _semantic_struggle_available(observation):
    features = observation.get("features")
    party = features.get("party") if isinstance(features, Mapping) else None
    battle = features.get("battle") if isinstance(features, Mapping) else None
    menu = features.get("menu") if isinstance(features, Mapping) else None
    lead = party.get("lead") if isinstance(party, Mapping) else None
    moves = lead.get("moves") if isinstance(lead, Mapping) else None
    return (
        observation.get("mode") == "battle"
        and isinstance(menu, Mapping)
        and menu.get("kind") == "battle_main"
        and isinstance(battle, Mapping)
        and battle.get("active") is True
        and battle.get("kind") == "trainer"
        and isinstance(lead, Mapping)
        and type(lead.get("hp")) is int
        and lead["hp"] > 0
        and isinstance(moves, list)
        and 1 <= len(moves) <= 4
        and all(
            isinstance(m, Mapping)
            and type(m.get("pp")) is int
            and m["pp"] == 0
            and type(m.get("slot_index")) is int
            and 0 <= m["slot_index"] <= 3
            for m in moves
        )
        and len({m["slot_index"] for m in moves}) == len(moves)
    )
