"""Bounded, teacher-free model decisions inside an authenticated Red trainer battle.

The isolated factory may set the starting state. After the capture is loaded,
only this controller's game actions can change it. Policy callbacks own every
attack, voluntary switch, replacement prompt, and forced replacement choice.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from typing import Protocol, cast

from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_recovery import (
    resolve_trainer_switch_prompt,
    switch_active_battler,
)
from pokemon_red_completion.battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.battle_scenario_capture import BattleScenarioCapture
from pokemon_red_completion.executor import ControllerTiming, FrameSafeExecutor
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    PokemonRedStateReader,
    ReadOnlyMemory,
)
from pokemon_red_completion.provenance import canonical_sha256
from pokemon_red_completion.red_battle_scenario import (
    PreparedRedBattleScenario,
    prepare_red_battle_scenario,
    project_red_battle_turn_outcome,
)
from pokemon_red_completion.red_trajectory import PokemonRedObservationEncoder


class TrainerPracticeSession(Protocol):
    def load_state_bytes(self, payload: bytes) -> None: ...

    def press(self, button: str) -> None: ...

    def release(self, button: str) -> None: ...

    def tick(self, frames: int) -> None: ...

    def read_u8(self, address: int) -> int: ...


class TrainerPracticePolicy(Protocol):
    @property
    def policy_id(self) -> str: ...

    def choose_main(
        self,
        observation: Mapping[str, object],
        prepared: PreparedRedBattleScenario,
    ) -> BattleAction: ...

    def choose_switch(
        self,
        observation: Mapping[str, object],
        legal_party_slots: tuple[int, ...],
        *,
        forced: bool,
        may_decline: bool,
    ) -> int | None: ...


class RedTrainerPracticeEpisodeError(RuntimeError):
    """A model action or cartridge transition crossed the declared boundary."""


@dataclass(frozen=True, slots=True)
class RedTrainerPracticeEpisode:
    capture_id: str
    manifest_sha256: str
    policy_id: str
    decisions: tuple[dict[str, object], ...]
    battle_won: bool
    final_battle_state: int
    stop_reason: str
    final_observation: dict[str, object] | None = None

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.trainer-practice-model-episode.v3",
            "capture_id": self.capture_id,
            "manifest_sha256": self.manifest_sha256,
            "policy_id": self.policy_id,
            "decisions": list(self.decisions),
            "decision_count": len(self.decisions),
            "player_turn_count": sum(
                step.get("kind") in {"attack", "voluntary_switch"} for step in self.decisions
            ),
            "battle_won": self.battle_won,
            "final_battle_state": self.final_battle_state,
            "stop_reason": self.stop_reason,
            "final_observation": self.final_observation,
            "final_observation_sha256": (
                canonical_sha256(self.final_observation)
                if self.final_observation is not None
                else None
            ),
            "teacher_queries": 0,
            "memory_write_actions": 0,
            "authority_promotions": 0,
        }


def run_red_trainer_practice_episode(
    capture: BattleScenarioCapture,
    *,
    session_factory: Callable[[], AbstractContextManager[TrainerPracticeSession]],
    policy: TrainerPracticePolicy,
    max_decisions: int = 24,
    max_player_turns: int | None = None,
    controller_timing: ControllerTiming | None = None,
) -> RedTrainerPracticeEpisode:
    """Let one model policy play a complete captured trainer battle, or fail closed."""

    if (
        not isinstance(capture, BattleScenarioCapture)
        or capture.manifest.expected_battle_state != 2
    ):
        raise RedTrainerPracticeEpisodeError(
            "trainer episode needs an authenticated trainer capture"
        )
    policy_id = getattr(policy, "policy_id", None)
    if not callable(session_factory) or not isinstance(policy_id, str) or not policy_id:
        raise RedTrainerPracticeEpisodeError("trainer episode needs a named policy and session")
    if type(max_decisions) is not int or max_decisions < 1:  # noqa: E721
        raise RedTrainerPracticeEpisodeError("trainer episode decision budget is invalid")
    if max_player_turns is not None and (
        type(max_player_turns) is not int  # noqa: E721
        or not 1 <= max_player_turns <= max_decisions
    ):
        raise RedTrainerPracticeEpisodeError("trainer episode player-turn budget is invalid")
    decisions: list[dict[str, object]] = []
    player_turns = 0
    with session_factory() as session:
        session.load_state_bytes(capture.state_bytes)
        reader = PokemonRedStateReader(cast(ReadOnlyMemory, session))
        encoder = PokemonRedObservationEncoder.from_state_reader(reader)
        initial = reader.read()
        if (
            initial.map_id != capture.manifest.expected_map
            or initial.battle_state != 2
            or reader.read_battle_menu_state(initial).phase is not BattleMenuPhase.MAIN
            or prepare_red_battle_scenario(encoder, initial).initial_observation_sha256
            != capture.manifest.initial_observation_sha256
        ):
            raise RedTrainerPracticeEpisodeError("trainer capture differs from its model boundary")
        actions = FrameSafeExecutor(session, controller_timing)
        for decision_index in range(1, max_decisions + 1):
            raw = reader.read()
            if raw.map_id != capture.manifest.expected_map or raw.battle_state not in {0, 2}:
                raise RedTrainerPracticeEpisodeError("trainer episode left its authenticated map")
            if raw.battle_state == 0:
                return _receipt(
                    capture,
                    policy.policy_id,
                    decisions,
                    raw,
                    reader.read_enemy_party_roster_hp(),
                    encoder.snapshot_from_raw(raw).to_dict(),
                )
            if (
                raw.battler_hp is None
                or raw.party_hp is None
                or raw.active_party_index is None
                or not 0 <= raw.active_party_index < len(raw.party_hp)
            ):
                raise RedTrainerPracticeEpisodeError("trainer player party is unavailable")
            observation = encoder.snapshot_from_raw(raw).to_dict()
            observation_sha256 = canonical_sha256(observation)
            options = tuple(
                index + 1
                for index, hp in enumerate(raw.party_hp)
                if hp > 0 and index != raw.active_party_index
            )
            forced = raw.battler_hp == 0
            prompt = reader.trainer_switch_prompt_visible(raw)
            if forced and not options:
                return RedTrainerPracticeEpisode(
                    capture_id=capture.manifest.capture_id,
                    manifest_sha256=capture.manifest_sha256,
                    policy_id=policy.policy_id,
                    decisions=tuple(decisions),
                    battle_won=False,
                    final_battle_state=raw.battle_state,
                    stop_reason="party_defeated",
                    final_observation=observation,
                )
            if max_player_turns is not None and player_turns >= max_player_turns:
                return RedTrainerPracticeEpisode(
                    capture_id=capture.manifest.capture_id,
                    manifest_sha256=capture.manifest_sha256,
                    policy_id=policy.policy_id,
                    decisions=tuple(decisions),
                    battle_won=False,
                    final_battle_state=raw.battle_state,
                    stop_reason="player_turn_budget",
                    final_observation=observation,
                )
            if forced or prompt:
                chosen_slot = policy.choose_switch(
                    observation,
                    options,
                    forced=forced,
                    may_decline=not forced,
                )
                if chosen_slot is not None and (
                    type(chosen_slot) is not int or chosen_slot not in options  # noqa: E721
                ):
                    raise RedTrainerPracticeEpisodeError("model chose an illegal switch target")
                if forced and chosen_slot is None:
                    raise RedTrainerPracticeEpisodeError("model declined a forced switch")
                if prompt:
                    resolve_trainer_switch_prompt(
                        actions,
                        reader,
                        session,
                        target_index=None if chosen_slot is None else chosen_slot - 1,
                        label="model trainer practice prompt",
                    )
                    kind = "switch_prompt"
                else:
                    assert chosen_slot is not None
                    switch_active_battler(
                        actions,
                        reader,
                        session,
                        chosen_slot - 1,
                        expected_battle_state=2,
                        label="model trainer practice forced switch",
                    )
                    kind = "forced_switch"
                after_switch = reader.read()
                decisions.append(
                    {
                        "decision_index": decision_index,
                        "observation": observation,
                        "observation_sha256": observation_sha256,
                        "kind": kind,
                        "party_slot": chosen_slot,
                        "legal_party_slots": list(options),
                        "after_observation_sha256": canonical_sha256(
                            encoder.snapshot_from_raw(after_switch).to_dict()
                        ),
                        "party_hp_before": list(raw.party_hp or ()),
                        "party_hp_after": list(after_switch.party_hp or ()),
                        "opponent_hp_before": raw.enemy_hp,
                        "opponent_hp_after": after_switch.enemy_hp,
                    }
                )
                continue
            if reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN:
                raise RedTrainerPracticeEpisodeError("trainer episode has no model-owned decision")
            prepared = prepare_red_battle_scenario(encoder, raw)
            action = policy.choose_main(observation, prepared)
            if not isinstance(action, BattleAction):
                raise RedTrainerPracticeEpisodeError("model returned no semantic battle action")
            if action.kind is BattleActionKind.SWITCH:
                if action.party_slot not in options:
                    raise RedTrainerPracticeEpisodeError("model chose an illegal voluntary switch")
                assert action.party_slot is not None
                switch_active_battler(
                    actions,
                    reader,
                    session,
                    action.party_slot - 1,
                    expected_battle_state=2,
                    label="model trainer practice voluntary switch",
                )
                after_switch = reader.read()
                decisions.append(
                    {
                        "decision_index": decision_index,
                        "observation": observation,
                        "observation_sha256": observation_sha256,
                        "kind": "voluntary_switch",
                        "party_slot": action.party_slot,
                        "legal_party_slots": list(options),
                        "after_observation_sha256": canonical_sha256(
                            encoder.snapshot_from_raw(after_switch).to_dict()
                        ),
                        "party_hp_before": list(raw.party_hp or ()),
                        "party_hp_after": list(after_switch.party_hp or ()),
                        "opponent_hp_before": raw.enemy_hp,
                        "opponent_hp_after": after_switch.enemy_hp,
                    }
                )
                player_turns += 1
                continue
            if action.kind is not BattleActionKind.SELECT_MOVE or action.move_slot is None:
                raise RedTrainerPracticeEpisodeError(
                    "trainer practice supports attacks and switches"
                )
            candidate_index = action.move_slot - 1
            if (
                candidate_index not in prepared.features.slot_indices
                or not prepared.supported_candidate_mask[candidate_index]
            ):
                raise RedTrainerPracticeEpisodeError("model chose an unsupported move")
            execution = execute_bounded_battle_move_turn(
                reader,
                actions,
                expected_map=capture.manifest.expected_map,
                selected_slot=action.move_slot,
                expected_battle_state=2,
                settle_to_next_decision=True,
                timing=replace(DEFAULT_BATTLE_RUNTIME_TIMING, max_post_attack_transition_pulses=40),
                label="model trainer practice attack",
            )
            outcome = project_red_battle_turn_outcome(execution)
            decisions.append(
                {
                    "decision_index": decision_index,
                    "observation": observation,
                    "observation_sha256": observation_sha256,
                    "kind": "attack",
                    "move_slot": action.move_slot,
                    "outcome": outcome.public_dict(),
                }
            )
            player_turns += 1
        final = reader.read()
        if final.battle_state == 0:
            return _receipt(
                capture,
                policy.policy_id,
                decisions,
                final,
                reader.read_enemy_party_roster_hp(),
                encoder.snapshot_from_raw(final).to_dict(),
            )
        if final.battle_state != 2:
            raise RedTrainerPracticeEpisodeError("trainer episode left battle at its decision cap")
        return RedTrainerPracticeEpisode(
            capture_id=capture.manifest.capture_id,
            manifest_sha256=capture.manifest_sha256,
            policy_id=policy.policy_id,
            decisions=tuple(decisions),
            battle_won=False,
            final_battle_state=final.battle_state,
            stop_reason="decision_budget",
            final_observation=encoder.snapshot_from_raw(final).to_dict(),
        )


def _receipt(
    capture, policy_id, decisions, final, enemy_hp, observation
) -> RedTrainerPracticeEpisode:
    if enemy_hp is None:
        raise RedTrainerPracticeEpisodeError("trainer terminal lacks authenticated roster HP")
    won = bool(
        all(hp == 0 for hp in enemy_hp)
        and final.party_hp is not None
        and any(hp > 0 for hp in final.party_hp)
    )
    return RedTrainerPracticeEpisode(
        capture_id=capture.manifest.capture_id,
        manifest_sha256=capture.manifest_sha256,
        policy_id=policy_id,
        decisions=tuple(decisions),
        battle_won=won,
        final_battle_state=final.battle_state,
        stop_reason="battle_won" if won else "battle_exited_without_win",
        final_observation=observation,
    )
