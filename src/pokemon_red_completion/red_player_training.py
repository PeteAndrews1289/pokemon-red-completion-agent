"""Native bounded-player training evidence; no fabricated legacy setup receipts."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import cast

from pokemon_red_completion.bounded_player_dashboard import ViewerGoalTrajectory
from pokemon_red_completion.goal_manager import (
    GoalDecisionOutcome,
    GoalFailureReason,
    GoalKind,
    GoalManagerQuestion,
    GoalSelectionMode,
)
from pokemon_red_completion.goal_manager_composition_runtime import CompositionBudgetMeter
from pokemon_red_completion.goal_manager_trajectory import PendingGoalManagerDecision
from pokemon_red_completion.living_dex_goal_policy import project_living_dex_goal_candidate
from pokemon_red_completion.living_dex_option_value import (
    LivingDexCensorReason,
    LivingDexCurriculumOutcomeExample,
    LivingDexObservedArmExample,
    LivingDexObservedOutcome,
    LivingDexOptionMenu,
    LivingDexOutcomeStatus,
    living_dex_option_context_from_goal_situation,
)
from pokemon_red_completion.living_dex_player_exploration import ExploringLivingDexGoalPolicy
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_goal_manager import RedGoalObservation
from pokemon_red_completion.red_living_dex_causal_adapter import (
    red_living_dex_outcome_from_observations,
)
from pokemon_red_completion.red_player_economy import (
    ECONOMY_CONTEXT_EVENT,
    ECONOMY_CONTEXT_SCHEMA,
    ECONOMY_TRAINING_EVENT_SCHEMA,
    PlayerEconomySupply,
    restore_context,
    semantic_facts,
    snapshot_document,
)
from pokemon_red_completion.red_player_training_plan import STORY_CURRICULUM_CONTRACT
from pokemon_red_completion.resource_economy_observation import EconomySnapshot, economy_outcome
from pokemon_red_completion.trajectory import JSONValue, SparseEvent

TRAINING_EVENT = "living_dex_player_training_outcome"
TRAINING_EVENT_SCHEMA = "pokemon.red.player-training-outcome.v1"
CURRICULUM_EVENT = "living_dex_player_curriculum_outcome"
CURRICULUM_EVENT_SCHEMA = "pokemon.red.player-curriculum-outcome.v1"
REGISTERED_TRAINING_EVENT_SCHEMA = "pokemon.red.registered-player-training-outcome.v1"


@dataclass(frozen=True, slots=True)
class _PendingTraining:
    before: Mapping[str, object]
    actions: int
    frames: int
    menu: LivingDexOptionMenu | None
    option_indices: tuple[int, ...]
    probabilities: tuple[float, ...]
    selected_index: int
    start_step: int
    curriculum_features: tuple[float, ...] | None = None
    feature_version: int = 1
    before_economy: EconomySnapshot | None = None
    target_cash: int | None = None


@dataclass(slots=True)
class RedPlayerTrainingTrajectory(ViewerGoalTrajectory):
    """Record only actual stochastic choices and independently observed outcomes."""

    observe_training: Callable[[], RedGoalObservation] | None = None
    training_meter: CompositionBudgetMeter | None = None
    training_plan_sha256: str = ""
    maximum_actions: int = 6_000
    maximum_frames: int = 600_000
    curriculum_contract: str | None = None
    registration_binding_sha256: str | None = None
    economy_supply: PlayerEconomySupply | None = None
    _economy_prepared: dict[str, object] | None = field(default=None, init=False, repr=False)
    _training: _PendingTraining | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        super(RedPlayerTrainingTrajectory, self).__post_init__()
        if (
            self.partition != "train"
            or not callable(self.observe_training)
            or not isinstance(self.training_meter, CompositionBudgetMeter)
            or re.fullmatch(r"[0-9a-f]{64}", self.training_plan_sha256) is None
            or not isinstance(self.displayed_authority, ExploringLivingDexGoalPolicy)
            or type(self.maximum_actions) is not int
            or self.maximum_actions <= 0
            or type(self.maximum_frames) is not int
            or self.maximum_frames <= 0
            or self.curriculum_contract not in (None, STORY_CURRICULUM_CONTRACT)
        ):
            raise ValueError("player training requires a declared train-only observation boundary")
        if self.registration_binding_sha256 is not None and (
            not isinstance(self.registration_binding_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.registration_binding_sha256) is None
            or self.curriculum_contract is not None
        ):
            raise ValueError("registered training requires a bound non-curriculum objective")
        if self.economy_supply is not None:
            if (not isinstance(self.economy_supply, PlayerEconomySupply)
                    or self.registration_binding_sha256 is None
                    or self.displayed_authority.model.feature_version != 4
                    or self.displayed_authority.prepare_selection is not None):
                raise ValueError("economy training requires a fresh registered v4 authority")
            self.displayed_authority.prepare_selection = self._prepare_economy_selection
        elif self.displayed_authority.model.feature_version == 4:
            raise ValueError("v4 player training requires the declared economy boundary")

    def _prepare_economy_selection(self, question: GoalManagerQuestion) -> None:
        """Observe and durably bind cash before the actor scores or samples."""
        assert self.training_meter is not None and self.observe_training is not None
        assert self.economy_supply is not None
        authority = self.displayed_authority
        assert isinstance(authority, ExploringLivingDexGoalPolicy)
        self._economy_prepared = None
        counter = self.training_meter.checkpoint()
        observation = self.observe_training()
        self._require_registration(observation)
        before = observation.public_dict()
        snapshot = observation.economy_snapshot()
        budget = self.economy_supply.budget(
            snapshot, semantic_facts(before).get("capture_item_count"),
        )
        if (self.training_meter.checkpoint() != counter
                or semantic_facts(before).get("situation") != question.situation.policy_dict()):
            raise ValueError("economy preselection observation is stale or changed the game")
        if snapshot is not None and any(
            quote is not None and quote.available_funds != snapshot.cash
            for i in question.available_indices
            for quote in (question.opportunities[i].resource_quote,)
        ):
            raise ValueError("economy quote differs from freshly observed cash")
        authority.economy_snapshot = (
            EconomySnapshot(snapshot.cash, ()) if snapshot is not None and budget is not None
            else None
        )
        authority.target_cash = budget.target_cash if budget is not None else None
        authority.allow_earning_exploration = True
        payload: dict[str, object] = {
            "schema": ECONOMY_CONTEXT_SCHEMA,
            "decision_id": f"{self.episode_id}:goal-manager:{self.next_decision_index}",
            "question_sha256": question.ordered_policy_input_sha256,
            "plan_sha256": self.training_plan_sha256,
            "before": before,
            "economy_before": snapshot_document(snapshot),
            "budget": budget.public_dict() if budget is not None else None,
        }
        self.sink.record_event(SparseEvent(
            event_id=f"{payload['decision_id']}:economy-context", episode_id=self.episode_id,
            step_index=self.recorder.next_step_index, kind=ECONOMY_CONTEXT_EVENT,
            payload=cast(Mapping[str, JSONValue], payload),
        ))
        self._economy_prepared = payload

    def _require_registration(self, observation: RedGoalObservation) -> None:
        checkpoint = getattr(observation, "registered_checkpoint", None)
        if self.registration_binding_sha256 is None:
            if checkpoint is not None:
                raise ValueError("legacy training cannot consume registered observations")
        elif checkpoint is None or checkpoint.binding_sha256 != self.registration_binding_sha256:
            raise ValueError("registered training observation binding differs")

    def record_selection(
        self,
        question: GoalManagerQuestion,
        selected_candidate_index: int,
        *,
        behavior_policy: Mapping[str, object] | None = None,
        selection_mode: GoalSelectionMode = GoalSelectionMode.AUTHORITY,
    ) -> PendingGoalManagerDecision:
        self._training = None
        pending = ViewerGoalTrajectory.record_selection(
            self,
            question,
            selected_candidate_index,
            behavior_policy=behavior_policy,
            selection_mode=selection_mode,
        )
        prepared, self._economy_prepared = self._economy_prepared, None
        if (self.economy_supply is not None and selection_mode is GoalSelectionMode.AUTHORITY
                and (prepared is None or prepared["decision_id"] != pending.decision_id
                    or prepared["question_sha256"] != question.ordered_policy_input_sha256)):
            raise ValueError("economy decision lacks fresh preselection evidence")
        authority = self.displayed_authority
        assert isinstance(authority, ExploringLivingDexGoalPolicy)
        if (
            self.curriculum_contract == STORY_CURRICULUM_CONTRACT
            and selection_mode is GoalSelectionMode.FORCED_SINGLETON
            and question.opportunities[selected_candidate_index].kind is GoalKind.ADVANCE_STORY
        ):
            if behavior_policy is not None:
                raise ValueError("curriculum is not a sampled behavior decision")
            if (
                question.available_indices != (selected_candidate_index,)
                or not self.pending_was_recorded
            ):
                raise ValueError("curriculum requires one durably recorded executable story goal")
            candidate = project_living_dex_goal_candidate(
                question,
                selected_candidate_index,
                feature_version=authority.model.feature_version,
                binding_ref="curriculum-executed-option",
            )
            assert candidate is not None
            assert self.training_meter is not None and self.observe_training is not None
            counter = self.training_meter.checkpoint()
            before = self.observe_training()
            self._require_registration(before)
            if self.training_meter.checkpoint() != counter:
                raise ValueError("curriculum observation changed the game")
            self._training = _PendingTraining(
                before.public_dict(),
                counter.controller_actions,
                counter.emulator_frames,
                None,
                (),
                (),
                selected_candidate_index,
                self.recorder.next_step_index,
                candidate.vector(
                    living_dex_option_context_from_goal_situation(question.situation),
                    feature_version=authority.model.feature_version,
                ),
                authority.model.feature_version,
            )
            return pending
        if selection_mode is not GoalSelectionMode.AUTHORITY or not authority.training_eligible:
            return pending
        if not self.pending_was_recorded or authority.last_menu is None:
            raise ValueError("training decision was not durably recorded")
        if behavior_policy != authority.selection_metadata():
            raise ValueError("training behavior differs from the committed choice")
        if (
            authority.last_decision is None
            or authority.last_decision.selected_candidate_index != selected_candidate_index
            or authority.last_question_sha256 != question.ordered_policy_input_sha256
        ):
            raise ValueError("training choice does not belong to the current question")
        assert self.training_meter is not None and self.observe_training is not None
        counter = self.training_meter.checkpoint()
        before = self.observe_training()
        self._require_registration(before)
        if self.training_meter.checkpoint() != counter:
            raise ValueError("training observation changed the game")
        before_economy, target_cash = None, None
        if self.economy_supply is not None:
            assert prepared is not None
            before_economy, budget = restore_context(prepared, self.economy_supply)
            if (before.public_dict() != prepared["before"]
                    or before.economy_snapshot() != before_economy or budget is None):
                raise ValueError("economy state changed between selection and execution")
            target_cash = budget.target_cash
        self._training = _PendingTraining(
            before.public_dict(),
            counter.controller_actions,
            counter.emulator_frames,
            authority.last_menu,
            authority.last_menu_indices,
            authority.option_probabilities,
            authority.last_menu_indices.index(selected_candidate_index),
            self.recorder.next_step_index,
            before_economy=before_economy, target_cash=target_cash,
        )
        return pending

    def record_outcome(
        self,
        pending: PendingGoalManagerDecision,
        *,
        status: GoalDecisionOutcome,
        failure_reason: GoalFailureReason | None = None,
    ) -> bool:
        recorded = ViewerGoalTrajectory.record_outcome(
            self,
            pending,
            status=status,
            failure_reason=failure_reason,
        )
        training, self._training = self._training, None
        if training is None or not recorded:
            return recorded
        assert self.training_meter is not None and self.observe_training is not None
        counter = self.training_meter.checkpoint()
        after: dict[str, object] | None = None
        after_economy: EconomySnapshot | None = None
        observation_failed = False
        actions = counter.controller_actions - training.actions
        frames = counter.emulator_frames - training.frames
        if min(actions, frames) < 0:
            raise ValueError("training counters regressed")
        if status is GoalDecisionOutcome.INTERRUPTED:
            outcome = LivingDexObservedOutcome(
                LivingDexOutcomeStatus.CENSORED,
                censor_reason=LivingDexCensorReason.EXTERNAL_INTERRUPTION,
            )
        else:
            try:
                after_observation = self.observe_training()
                self._require_registration(after_observation)
                after = after_observation.public_dict()
                if self.economy_supply is not None:
                    after_economy = after_observation.economy_snapshot()
            except Exception:
                if training.curriculum_features is None:
                    raise
                observation_failed = True
            if self.training_meter.checkpoint() != counter:
                raise ValueError("training outcome observation changed the game")
            if observation_failed:
                outcome = LivingDexObservedOutcome(
                    LivingDexOutcomeStatus.CENSORED,
                    censor_reason=LivingDexCensorReason.OBSERVATION_FAILED,
                )
            else:
                assert after is not None
                if self.registration_binding_sha256 is not None:
                    from .red_registered_outcome import red_registered_outcome_from_observations

                    outcome = red_registered_outcome_from_observations(
                        training.before, after,
                        selected_kind=pending.question.opportunities[
                            pending.selected_candidate_index
                        ].kind,
                        succeeded=status is GoalDecisionOutcome.SUCCEEDED,
                        actions=actions, frames=frames,
                        maximum_actions=self.maximum_actions, maximum_frames=self.maximum_frames,
                    )
                else:
                    outcome = red_living_dex_outcome_from_observations(
                        training.before,
                        after,
                        succeeded=status is GoalDecisionOutcome.SUCCEEDED,
                        actions=actions,
                        frames=frames,
                        maximum_actions=self.maximum_actions,
                        maximum_frames=self.maximum_frames,
                    )
        if self.economy_supply is not None and outcome.status is LivingDexOutcomeStatus.SETTLED:
            assert training.target_cash is not None
            measured = economy_outcome(training.before_economy, after_economy,
                                       target_cash=training.target_cash)
            outcome = (replace(outcome, economy=measured) if measured is not None
                       else LivingDexObservedOutcome(LivingDexOutcomeStatus.CENSORED,
                            censor_reason=LivingDexCensorReason.OBSERVATION_FAILED))
        decision_sha = canonical_sha256(
            {
                "decision_id": pending.decision_id,
                "plan_sha256": self.training_plan_sha256,
                "question_sha256": pending.question.ordered_policy_input_sha256,
            }
        )
        example: LivingDexObservedArmExample | LivingDexCurriculumOutcomeExample
        if training.curriculum_features is not None:
            example = LivingDexCurriculumOutcomeExample(
                decision_sha,
                "train",
                training.feature_version,
                training.curriculum_features,
                outcome,
            )
        else:
            assert training.menu is not None
            example = LivingDexObservedArmExample(
                decision_sha256=decision_sha,
                partition="train",
                menu=training.menu,
                selected_candidate_index=training.selected_index,
                behavior_probabilities=training.probabilities,
                outcome=outcome,
            )
        curriculum = isinstance(example, LivingDexCurriculumOutcomeExample)
        self.sink.record_event(
            SparseEvent(
                event_id=f"{pending.decision_id}:training",
                episode_id=self.episode_id,
                step_index=self.recorder.next_step_index,
                kind=CURRICULUM_EVENT if curriculum else TRAINING_EVENT,
                payload=cast(
                    Mapping[str, JSONValue],
                    {
                        "schema": (ECONOMY_TRAINING_EVENT_SCHEMA if self.economy_supply is not None
                                   else REGISTERED_TRAINING_EVENT_SCHEMA
                                   if self.registration_binding_sha256 is not None
                                   else CURRICULUM_EVENT_SCHEMA if curriculum
                                   else TRAINING_EVENT_SCHEMA),
                        "decision_id": pending.decision_id,
                        "plan_sha256": self.training_plan_sha256,
                        **(
                            {
                                "curriculum_contract": self.curriculum_contract,
                                "observation_failed": observation_failed,
                            }
                            if curriculum
                            else {"option_indices": list(training.option_indices)}
                        ),
                        "example": example.public_dict(),
                        "before": dict(training.before),
                        "after": after,
                        **({"economy_after": snapshot_document(after_economy)}
                           if self.economy_supply is not None else {}),
                        "actions": actions,
                        "frames": frames,
                        "maximum_actions": self.maximum_actions,
                        "maximum_frames": self.maximum_frames,
                        "has_controller_input": actions > 0,
                        "start_step": training.start_step,
                        "end_step": self.recorder.next_step_index,
                    },
                ),
            )
        )
        return recorded
