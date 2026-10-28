"""Matched short-horizon TRAIN branches for attack and switch choices.

The trainer factory constructs the state. This collector reloads that exact
capture for each declared first choice, then a fresh continuation policy owns
all later decisions. Sibling branches share one upstream lineage, not an
independent evaluation set.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import TypedDict

from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_runtime import BattleActionExecutor
from pokemon_red_completion.battle_scenario_capture import BattleScenarioCapture
from pokemon_red_completion.observation import RawGameState
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_scenario import PreparedRedBattleScenario
from pokemon_red_completion.red_trainer_practice_episode import (
    RedTrainerPracticeEpisode,
    TrainerPracticePolicy,
    TrainerPracticeSession,
    run_red_trainer_practice_episode,
)
from pokemon_red_completion.red_trainer_practice_log import TrainerPracticeEventLog
from pokemon_red_completion.scenario_lab import ScenarioPartition


class TrainerPracticeCounterfactualError(ValueError):
    """A declared action or continuation policy crossed the TRAIN boundary."""


class _StatusOptions(TypedDict, total=False):
    allow_status_moves: bool


class _StruggleOptions(TypedDict, total=False):
    allow_forced_struggle: bool


@dataclass(frozen=True, slots=True)
class TrainerPracticeFirstChoice:
    """One initial move/switch, or an explicit decline of a trainer prompt."""

    action: BattleAction | None

    def __post_init__(self) -> None:
        if self.action is not None and (
            not isinstance(self.action, BattleAction)
            or self.action.kind not in {BattleActionKind.SELECT_MOVE, BattleActionKind.SWITCH}
            or (self.action.kind is BattleActionKind.SWITCH and self.action.party_slot is None)
        ):
            raise TrainerPracticeCounterfactualError("first choice must be move or exact switch")

    @property
    def semantic_ref(self) -> str:
        if self.action is not None:
            return self.action.semantic_ref
        return "pokemon.core:battle:decline-switch"


@dataclass(frozen=True, slots=True)
class TrainerPracticeCounterfactualSet:
    capture_id: str
    manifest_sha256: str
    root_lineage_id: str
    player_turn_horizon: int
    branches: tuple[tuple[TrainerPracticeFirstChoice, RedTrainerPracticeEpisode], ...]
    train_wild_diagnostic: bool = False
    train_wild_limits: tuple[int, int] | None = None
    train_wild_choice_scope: str | None = None

    def public_dict(self) -> dict[str, object]:
        if self.train_wild_choice_scope is not None and (
            type(self.train_wild_choice_scope) is not str
            or self.train_wild_choice_scope != "switch_selection"
            or self.train_wild_diagnostic is not True
            or self.train_wild_limits != (8, 32)
            or len(self.branches) != 2
            or any(choice.action is None or choice.action.kind is not BattleActionKind.SWITCH
                   for choice, _ in self.branches)
            or len({choice.semantic_ref for choice, _ in self.branches}) != 2
        ):
            raise TrainerPracticeCounterfactualError("switch-selection metadata differs")
        if self.train_wild_limits is not None and (
            self.train_wild_diagnostic is not True or type(self.train_wild_limits) is not tuple
            or len(self.train_wild_limits) != 2
            or any(type(value) is not int for value in self.train_wild_limits)
            or self.train_wild_limits != (8, 32)
            or type(self.player_turn_horizon) is not int or self.player_turn_horizon != 8
        ):
            raise TrainerPracticeCounterfactualError("explicit TRAIN wild limits metadata differs")
        return {
            "schema": ("pokemon.red.wild-practice-counterfactual-set.v1" if self.train_wild_diagnostic
                       else "pokemon.red.trainer-practice-counterfactual-set.v1"),
            "capture_id": self.capture_id,
            "manifest_sha256": self.manifest_sha256,
            "root_lineage_id": self.root_lineage_id,
            "partition": "train",
            **({"wild_training": True, "train_wild_diagnostic": True, "expected_battle_state": 1}
               if self.train_wild_diagnostic else {}),
            "player_turn_horizon": self.player_turn_horizon,
            "branch_count": len(self.branches),
            "branches": [
                {"first_choice_ref": choice.semantic_ref, "episode": episode.public_dict()}
                for choice, episode in self.branches
            ],
            **({"train_wild_limits": {"player_turn_horizon": 8, "max_decisions": 32}}
               if self.train_wild_limits is not None else {}),
            **({"train_wild_choice_scope": self.train_wild_choice_scope}
               if self.train_wild_choice_scope is not None else {}),
            "new_independent_upstream_roots": 0,
            "teacher_choice_targets": 0,
            "model_updates": 0,
            "authority_promotions": 0,
        }


@dataclass(slots=True)
class _FirstChoicePolicy:
    first: TrainerPracticeFirstChoice
    continuation: TrainerPracticePolicy
    consumed: bool = False
    first_just_consumed: bool = False

    @property
    def last_decision_diagnostics(self) -> dict[str, object] | None:
        if self.first_just_consumed:
            return {"forced_first_choice_ref": self.first.semantic_ref}
        value = getattr(self.continuation, "last_decision_diagnostics", None)
        return dict(value) if isinstance(value, dict) else None

    def _record_first(self, observation: Mapping[str, object], action: BattleAction | None) -> None:
        self.consumed = True
        self.first_just_consumed = True
        observer = getattr(self.continuation, "observe_forced_choice", None)
        if callable(observer) and action is not None:
            observer(observation, action)

    @property
    def policy_id(self) -> str:
        return f"{self.continuation.policy_id}:first={self.first.semantic_ref}"

    def observe_opponent_transition(self, before: int, after: int) -> None:
        observer = getattr(self.continuation, "observe_opponent_transition", None)
        if callable(observer):
            observer(before, after)

    def choose_main(
        self, observation: Mapping[str, object], prepared: PreparedRedBattleScenario
    ) -> BattleAction:
        if not self.consumed:
            if self.first.action is None:
                raise TrainerPracticeCounterfactualError("cannot decline a MAIN battle menu")
            self._record_first(observation, self.first.action)
            return self.first.action
        self.first_just_consumed = False
        return self.continuation.choose_main(observation, prepared)

    def choose_switch(
        self,
        observation: Mapping[str, object],
        legal_party_slots: tuple[int, ...],
        *,
        forced: bool,
        may_decline: bool,
    ) -> int | None:
        if not self.consumed:
            action = self.first.action
            if action is None:
                if not may_decline or forced:
                    raise TrainerPracticeCounterfactualError("cannot decline a forced switch")
                self._record_first(observation, None)
                return None
            if action.kind is not BattleActionKind.SWITCH or action.party_slot is None:
                raise TrainerPracticeCounterfactualError("prompt needs a switch or decline")
            self._record_first(observation, action)
            return action.party_slot
        self.first_just_consumed = False
        return self.continuation.choose_switch(
            observation, legal_party_slots, forced=forced, may_decline=may_decline
        )


def collect_trainer_practice_counterfactuals(
    capture: BattleScenarioCapture,
    *,
    session_factory: Callable[[], AbstractContextManager[TrainerPracticeSession]],
    continuation_policy_factory: Callable[[], TrainerPracticePolicy],
    first_choices: tuple[TrainerPracticeFirstChoice, ...],
    max_decisions: int = 8,
    player_turn_horizon: int = 2,
    branch_sink: Callable[[int, TrainerPracticeFirstChoice, RedTrainerPracticeEpisode], None]
    | None = None,
    branch_event_log_factory: Callable[[int, TrainerPracticeFirstChoice], TrainerPracticeEventLog]
    | None = None,
    public_species_base_stats: Mapping[int, tuple[int, int, int, int, int]] | None = None,
    opening_idle_frames: int = 0,
    action_executor: BattleActionExecutor | None = None,
    decision_guard: Callable[[RawGameState], None] | None = None,
    allow_status_moves: bool = False,
    allow_forced_struggle: bool = False,
    train_wild_diagnostic: bool = False,
    train_wild_limits: tuple[int, int] | None = None,
    train_wild_choice_scope: str | None = None,
) -> TrainerPracticeCounterfactualSet:
    """Run matched TRAIN branches, preserving every valid failure and tie.

    ``switch_selection`` explicitly measures two switch targets under the 8/32
    wild contract; its returns cannot be relabeled as an attack/control pair.
    """

    if type(train_wild_diagnostic) is not bool:
        raise TrainerPracticeCounterfactualError("TRAIN wild diagnostic opt-in must be boolean")
    if (
        not isinstance(capture, BattleScenarioCapture)
        or capture.manifest.partition is not ScenarioPartition.TRAIN
        or capture.manifest.expected_battle_state != (1 if train_wild_diagnostic else 2)
    ):
        raise TrainerPracticeCounterfactualError("counterfactuals require trainer TRAIN capture")
    if (
        type(allow_status_moves) is not bool
        or type(allow_forced_struggle) is not bool
        or not isinstance(first_choices, tuple)
        or not 2 <= len(first_choices) <= 10
        or any(not isinstance(choice, TrainerPracticeFirstChoice) for choice in first_choices)
        or len({choice.semantic_ref for choice in first_choices}) != len(first_choices)
        or type(max_decisions) is not int  # noqa: E721
        or not 2 <= max_decisions <= 160
        or type(player_turn_horizon) is not int  # noqa: E721
        # Admission accepts at most80turns. Reject an incompatible collection
        # before opening a policy, event log, emulator or native branch.
        or not 1 <= player_turn_horizon <= min(80, max_decisions)
    ):
        raise TrainerPracticeCounterfactualError("counterfactual branch inventory differs")
    if train_wild_limits is not None and (
        not train_wild_diagnostic or type(train_wild_limits) is not tuple
        or len(train_wild_limits) != 2
        or any(type(value) is not int for value in train_wild_limits)
        or train_wild_limits != (8, 32)
    ):
        raise TrainerPracticeCounterfactualError("explicit TRAIN wild limits must be (8, 32)")
    if train_wild_choice_scope is not None and (
        type(train_wild_choice_scope) is not str
        or train_wild_choice_scope != "switch_selection"
        or train_wild_diagnostic is not True or train_wild_limits != (8, 32)
    ):
        raise TrainerPracticeCounterfactualError("switch-selection scope requires explicit TRAIN wild (8, 32)")
    wild_horizon, wild_decisions = (2, 8) if train_wild_limits is None else train_wild_limits
    if train_wild_diagnostic and (
        allow_forced_struggle or len(first_choices) != 2 or player_turn_horizon != wild_horizon
        or max_decisions > wild_decisions
        or (train_wild_limits is not None and max_decisions != wild_decisions)
        or any(c.action is None for c in first_choices)
        or {c.action.kind for c in first_choices} != (
            {BattleActionKind.SWITCH} if train_wild_choice_scope == "switch_selection"
            else {BattleActionKind.SELECT_MOVE, BattleActionKind.SWITCH}
        )
    ):
        raise TrainerPracticeCounterfactualError("wild diagnostic requires bounded attack/switch contrast")
    branches: list[tuple[TrainerPracticeFirstChoice, RedTrainerPracticeEpisode]] = []
    for index, choice in enumerate(first_choices):
        continuation = continuation_policy_factory()
        if not isinstance(getattr(continuation, "policy_id", None), str):
            raise TrainerPracticeCounterfactualError("continuation policy is unnamed")
        wrapped = _FirstChoicePolicy(choice, continuation)
        branch_log = (
            branch_event_log_factory(index, choice)
            if branch_event_log_factory is not None
            else None
        )
        try:
            episode = run_red_trainer_practice_episode(
                capture,
                session_factory=session_factory,
                policy=wrapped,
                max_decisions=max_decisions,
                max_player_turns=player_turn_horizon,
                event_sink=branch_log.emit if branch_log is not None else None,
                public_species_base_stats=public_species_base_stats,
                opening_idle_frames=opening_idle_frames,
                action_executor=action_executor,
                decision_guard=decision_guard,
                **({"wild_training": True, "train_wild_diagnostic": True}
                   if train_wild_diagnostic else {}),
                **(
                    _StruggleOptions(allow_forced_struggle=True)
                    if allow_forced_struggle
                    else _StruggleOptions()
                ),
                **(
                    _StatusOptions(allow_status_moves=True)
                    if allow_status_moves
                    else _StatusOptions()
                ),
            )
        except Exception as error:
            if branch_log is not None:
                branch_log.fail(error)
            raise
        if not wrapped.consumed or not episode.decisions or episode.final_observation is None:
            incomplete_error = TrainerPracticeCounterfactualError(
                "counterfactual branch outcome is incomplete"
            )
            if branch_log is not None:
                branch_log.fail(incomplete_error)
            raise incomplete_error
        player_turns = sum(
            step.get("kind") in {"attack", "voluntary_switch", "forced_struggle"}
            for step in episode.decisions
        )
        if episode.stop_reason == "decision_budget" or (
            episode.stop_reason == "player_turn_budget" and player_turns != player_turn_horizon
        ):
            horizon_error = TrainerPracticeCounterfactualError(
                "counterfactual branch missed its turn horizon"
            )
            if branch_log is not None:
                branch_log.fail(horizon_error)
            raise horizon_error
        if branch_log is not None:
            branch_log.finish(
                {
                    "first_choice_ref": choice.semantic_ref,
                    "episode_sha256": canonical_sha256(episode.public_dict()),
                    "stop_reason": episode.stop_reason,
                }
            )
        branches.append((choice, episode))
        if branch_sink is not None:
            branch_sink(index, choice, episode)
    return TrainerPracticeCounterfactualSet(
        capture_id=capture.manifest.capture_id,
        manifest_sha256=capture.manifest_sha256,
        root_lineage_id=capture.manifest.root_lineage_id,
        player_turn_horizon=player_turn_horizon,
        branches=tuple(branches),
        train_wild_diagnostic=train_wild_diagnostic,
        train_wild_limits=train_wild_limits,
        train_wild_choice_scope=train_wild_choice_scope,
    )
