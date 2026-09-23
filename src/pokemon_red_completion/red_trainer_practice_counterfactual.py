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

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.trainer-practice-counterfactual-set.v1",
            "capture_id": self.capture_id,
            "manifest_sha256": self.manifest_sha256,
            "root_lineage_id": self.root_lineage_id,
            "partition": "train",
            "player_turn_horizon": self.player_turn_horizon,
            "branch_count": len(self.branches),
            "branches": [
                {"first_choice_ref": choice.semantic_ref, "episode": episode.public_dict()}
                for choice, episode in self.branches
            ],
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
) -> TrainerPracticeCounterfactualSet:
    """Run matched branches from one TRAIN capture, preserving failures as outcomes."""

    if (
        not isinstance(capture, BattleScenarioCapture)
        or capture.manifest.partition is not ScenarioPartition.TRAIN
        or capture.manifest.expected_battle_state != 2
    ):
        raise TrainerPracticeCounterfactualError("counterfactuals require trainer TRAIN capture")
    if (
        not isinstance(first_choices, tuple)
        or not 2 <= len(first_choices) <= 10
        or any(not isinstance(choice, TrainerPracticeFirstChoice) for choice in first_choices)
        or len({choice.semantic_ref for choice in first_choices}) != len(first_choices)
        or type(max_decisions) is not int  # noqa: E721
        or not 2 <= max_decisions <= 160
        or type(player_turn_horizon) is not int  # noqa: E721
        or not 1 <= player_turn_horizon <= max_decisions
    ):
        raise TrainerPracticeCounterfactualError("counterfactual branch inventory differs")
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
            step.get("kind") in {"attack", "voluntary_switch"} for step in episode.decisions
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
    )
