"""Bounded, teacher-free model decisions inside an authenticated Red trainer battle.

The isolated factory may set the starting state. After the capture is loaded,
only this controller's game actions can change it. Policy callbacks own every
attack, voluntary switch, replacement prompt, and forced replacement choice.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from time import perf_counter_ns
from typing import Protocol, cast

from pokemon_red_completion.actions import MacroAction, MacroActionKind
from pokemon_red_completion.battle_actions import BattleAction, BattleActionKind
from pokemon_red_completion.battle_recovery import (
    resolve_trainer_switch_prompt,
    switch_active_battler,
)
from pokemon_red_completion.battle_runtime import (
    DEFAULT_BATTLE_RUNTIME_TIMING,
    execute_bounded_battle_move_turn,
)
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    BattleScenarioCapture,
)
from pokemon_red_completion.executor import ControllerTiming, FrameSafeExecutor
from pokemon_red_completion.observation import (
    BattleMenuPhase,
    PokemonRedStateReader,
    RawGameState,
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
    final_enemy_roster_hp: tuple[int, ...] | None = None
    elapsed_ns: int = 0
    opening_idle_frames: int = 0

    def public_dict(self) -> dict[str, object]:
        return {
            "schema": "pokemon.red.trainer-practice-model-episode.v4",
            "capture_id": self.capture_id,
            "manifest_sha256": self.manifest_sha256,
            "policy_id": self.policy_id,
            "decisions": list(self.decisions),
            "decision_count": len(self.decisions),
            "elapsed_ns": self.elapsed_ns,
            "opening_idle_frames": self.opening_idle_frames,
            "policy_elapsed_ns": _sum_int(self.decisions, "policy_elapsed_ns"),
            "execution_elapsed_ns": _sum_int(self.decisions, "execution_elapsed_ns"),
            "observation_and_logging_elapsed_ns": max(
                0,
                self.elapsed_ns
                - _sum_int(self.decisions, "policy_elapsed_ns")
                - _sum_int(self.decisions, "execution_elapsed_ns"),
            ),
            "frames_executed": sum(
                value
                for step in self.decisions
                if type(value := step.get("frames_executed")) is int
            ),
            "action_counts": {
                kind: sum(step.get("kind") == kind for step in self.decisions)
                for kind in ("attack", "voluntary_switch", "switch_prompt", "forced_switch")
            },
            "failed_move_executions": sum(
                step.get("kind") == "attack"
                and isinstance(outcome := step.get("outcome"), dict)
                and outcome.get("move_executed") is False
                for step in self.decisions
            ),
            "metrics": _episode_metrics(self.decisions),
            "player_turn_count": sum(
                step.get("kind") in {"attack", "voluntary_switch"} for step in self.decisions
            ),
            "battle_won": self.battle_won,
            "final_battle_state": self.final_battle_state,
            "stop_reason": self.stop_reason,
            "final_observation": self.final_observation,
            "final_enemy_roster_hp": (
                list(self.final_enemy_roster_hp) if self.final_enemy_roster_hp is not None else None
            ),
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
    event_sink: Callable[[Mapping[str, object]], None] | None = None,
    public_species_base_stats: Mapping[int, tuple[int, int, int, int, int]] | None = None,
    opening_idle_frames: int = 0,
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
    if type(opening_idle_frames) is not int or not 0 <= opening_idle_frames <= 12:  # noqa: E721
        raise RedTrainerPracticeEpisodeError("trainer opening timing is outside its bound")
    decisions: list[dict[str, object]] = []
    episode_started_ns = perf_counter_ns()
    player_turns = 0
    with session_factory() as session:
        session.load_state_bytes(capture.state_bytes)
        reader = PokemonRedStateReader(cast(ReadOnlyMemory, session))
        encoder = (
            PokemonRedObservationEncoder.from_state_reader(
                reader,
                include_battle_stats=True,
                public_species_base_stats=public_species_base_stats,
            )
            if capture.manifest.observation_schema == OBSERVATION_SCHEMA_V2
            else PokemonRedObservationEncoder.from_state_reader(reader)
        )
        initial = reader.read()
        _require_plausible_hp(initial)
        if initial.map_id != capture.manifest.expected_map or initial.battle_state != 2:
            raise RedTrainerPracticeEpisodeError("trainer capture differs from its model boundary")
        initial_prompt = reader.trainer_switch_prompt_visible(initial)
        initial_sha256 = (
            canonical_sha256(encoder.snapshot_from_raw(initial).to_dict())
            if initial_prompt
            else prepare_red_battle_scenario(
                encoder, initial, allow_no_attack=True
            ).initial_observation_sha256
        )
        if (
            not initial_prompt
            and reader.read_battle_menu_state(initial).phase is not BattleMenuPhase.MAIN
        ) or initial_sha256 != capture.manifest.initial_observation_sha256:
            raise RedTrainerPracticeEpisodeError("trainer capture differs from its model boundary")
        if opening_idle_frames:
            _emit(
                event_sink,
                {
                    "event": "opening_timing_started",
                    "idle_frames": opening_idle_frames,
                    "initial_observation_sha256": initial_sha256,
                },
            )
            FrameSafeExecutor(session).execute(
                MacroAction(MacroActionKind.WAIT, repeat=opening_idle_frames)
            )
            settled = reader.read()
            _require_plausible_hp(settled)
            if (
                settled.battle_state != 2
                or canonical_sha256(encoder.snapshot_from_raw(settled).to_dict()) != initial_sha256
            ):
                raise RedTrainerPracticeEpisodeError("opening timing changed the model observation")
            _emit(
                event_sink,
                {
                    "event": "opening_timing_completed",
                    "idle_frames": opening_idle_frames,
                    "observation_sha256": initial_sha256,
                },
            )
        actions = FrameSafeExecutor(session, controller_timing)
        _emit(
            event_sink,
            {
                "event": "episode_started",
                "capture_id": capture.manifest.capture_id,
                "manifest_sha256": capture.manifest_sha256,
                "root_lineage_id": capture.manifest.root_lineage_id,
                "partition": capture.manifest.partition.value,
                "policy_id": policy.policy_id,
                "max_decisions": max_decisions,
                "max_player_turns": max_player_turns,
                "opening_idle_frames": opening_idle_frames,
                "state_before": _resource_state(initial),
            },
        )
        for decision_index in range(1, max_decisions + 1):
            raw = reader.read()
            _require_plausible_hp(raw)
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
                    elapsed_ns=perf_counter_ns() - episode_started_ns,
                    opening_idle_frames=opening_idle_frames,
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
                    elapsed_ns=perf_counter_ns() - episode_started_ns,
                    opening_idle_frames=opening_idle_frames,
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
                    elapsed_ns=perf_counter_ns() - episode_started_ns,
                    opening_idle_frames=opening_idle_frames,
                )
            prepared_main = None
            if not forced and not prompt and (
                reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN
            ):
                prepared_main = prepare_red_battle_scenario(
                    encoder, raw, allow_no_attack=True
                )
                if not any(prepared_main.supported_candidate_mask) and not options:
                    _emit(event_sink, {
                        "event": "unsupported_action_boundary",
                        "decision_index": decision_index,
                        "reason": "struggle_required_no_living_reserve",
                    })
                    return RedTrainerPracticeEpisode(
                        capture_id=capture.manifest.capture_id,
                        manifest_sha256=capture.manifest_sha256,
                        policy_id=policy.policy_id,
                        decisions=tuple(decisions),
                        battle_won=False,
                        final_battle_state=raw.battle_state,
                        stop_reason="unsupported_struggle_boundary",
                        final_observation=observation,
                        elapsed_ns=perf_counter_ns() - episode_started_ns,
                        opening_idle_frames=opening_idle_frames,
                    )
            _emit(
                event_sink,
                {
                    "event": "decision_started",
                    "decision_index": decision_index,
                    "observation_sha256": observation_sha256,
                    "mode": "forced_switch" if forced else "switch_prompt" if prompt else "main",
                    "legal_party_slots": list(options),
                    "state_before": _resource_state(raw),
                },
            )
            if forced or prompt:
                policy_started_ns = perf_counter_ns()
                chosen_slot = policy.choose_switch(
                    observation,
                    options,
                    forced=forced,
                    may_decline=not forced,
                )
                policy_elapsed_ns = perf_counter_ns() - policy_started_ns
                diagnostics = _policy_diagnostics(policy)
                _emit(
                    event_sink,
                    {
                        "event": "choice_recorded",
                        "decision_index": decision_index,
                        "selected_action": "decline_switch" if chosen_slot is None else "switch",
                        "party_slot": chosen_slot,
                        "policy_elapsed_ns": policy_elapsed_ns,
                        "model_diagnostics": diagnostics,
                    },
                )
                if chosen_slot is not None and (
                    type(chosen_slot) is not int or chosen_slot not in options  # noqa: E721
                ):
                    raise RedTrainerPracticeEpisodeError("model chose an illegal switch target")
                if forced and chosen_slot is None:
                    raise RedTrainerPracticeEpisodeError("model declined a forced switch")
                execution_started_ns = perf_counter_ns()
                frames_before = _frame_count(session)
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
                decision = {
                    "decision_index": decision_index,
                    "observation": observation,
                    "observation_sha256": observation_sha256,
                    "kind": kind,
                    "party_slot": chosen_slot,
                    "model_diagnostics": diagnostics,
                    "legal_party_slots": list(options),
                    "after_observation_sha256": canonical_sha256(
                        encoder.snapshot_from_raw(after_switch).to_dict()
                    ),
                    "party_hp_before": list(raw.party_hp or ()),
                    "party_hp_after": list(after_switch.party_hp or ()),
                    "opponent_hp_before": raw.enemy_hp,
                    "opponent_hp_after": after_switch.enemy_hp,
                }
                _complete_decision(
                    decisions,
                    decision,
                    raw,
                    after_switch,
                    policy_elapsed_ns,
                    execution_started_ns,
                    session,
                    frames_before,
                    event_sink,
                )
                continue
            if reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN:
                raise RedTrainerPracticeEpisodeError("trainer episode has no model-owned decision")
            prepared = prepared_main or prepare_red_battle_scenario(
                encoder, raw, allow_no_attack=True
            )
            _emit(
                event_sink,
                {
                    "event": "model_input_prepared",
                    "decision_index": decision_index,
                    "model_input": _main_model_input(prepared),
                },
            )
            policy_started_ns = perf_counter_ns()
            action = policy.choose_main(observation, prepared)
            policy_elapsed_ns = perf_counter_ns() - policy_started_ns
            diagnostics = _policy_diagnostics(policy)
            _emit(
                event_sink,
                {
                    "event": "choice_recorded",
                    "decision_index": decision_index,
                    "selected_action": (
                        action.public_dict() if isinstance(action, BattleAction) else None
                    ),
                    "policy_elapsed_ns": policy_elapsed_ns,
                    "model_diagnostics": diagnostics,
                },
            )
            if not isinstance(action, BattleAction):
                raise RedTrainerPracticeEpisodeError("model returned no semantic battle action")
            if action.kind is BattleActionKind.SWITCH:
                if action.party_slot not in options:
                    raise RedTrainerPracticeEpisodeError("model chose an illegal voluntary switch")
                assert action.party_slot is not None
                execution_started_ns = perf_counter_ns()
                frames_before = _frame_count(session)
                switch_active_battler(
                    actions,
                    reader,
                    session,
                    action.party_slot - 1,
                    expected_battle_state=2,
                    label="model trainer practice voluntary switch",
                    allow_faint_outcome=True,
                )
                after_switch = reader.read()
                decision = {
                    "decision_index": decision_index,
                    "observation": observation,
                    "observation_sha256": observation_sha256,
                    "kind": "voluntary_switch",
                    "party_slot": action.party_slot,
                    "model_diagnostics": diagnostics,
                    "legal_party_slots": list(options),
                    "model_input": _main_model_input(prepared),
                    "after_observation_sha256": canonical_sha256(
                        encoder.snapshot_from_raw(after_switch).to_dict()
                    ),
                    "party_hp_before": list(raw.party_hp or ()),
                    "party_hp_after": list(after_switch.party_hp or ()),
                    "opponent_hp_before": raw.enemy_hp,
                    "opponent_hp_after": after_switch.enemy_hp,
                }
                _complete_decision(
                    decisions,
                    decision,
                    raw,
                    after_switch,
                    policy_elapsed_ns,
                    execution_started_ns,
                    session,
                    frames_before,
                    event_sink,
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
            execution_started_ns = perf_counter_ns()
            frames_before = _frame_count(session)
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
            after_attack = reader.read()
            _require_plausible_hp(after_attack)
            outcome = project_red_battle_turn_outcome(execution)
            decision = {
                "decision_index": decision_index,
                "observation": observation,
                "observation_sha256": observation_sha256,
                "kind": "attack",
                "move_slot": action.move_slot,
                "model_diagnostics": diagnostics,
                "model_input": _main_model_input(prepared),
                "legal_move_slots": [
                    slot + 1
                    for slot, legal in zip(
                        prepared.features.slot_indices,
                        prepared.supported_candidate_mask,
                        strict=True,
                    )
                    if legal
                ],
                "legal_party_slots": list(options),
                "outcome": outcome.public_dict(),
                "turn_utility": outcome.utility,
                "opponent_hp_before": raw.enemy_hp,
                "opponent_hp_after": after_attack.enemy_hp,
            }
            _complete_decision(
                decisions,
                decision,
                raw,
                after_attack,
                policy_elapsed_ns,
                execution_started_ns,
                session,
                frames_before,
                event_sink,
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
                elapsed_ns=perf_counter_ns() - episode_started_ns,
                opening_idle_frames=opening_idle_frames,
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
            elapsed_ns=perf_counter_ns() - episode_started_ns,
            opening_idle_frames=opening_idle_frames,
        )


def _receipt(
    capture,
    policy_id,
    decisions,
    final,
    enemy_hp,
    observation,
    *,
    elapsed_ns: int = 0,
    opening_idle_frames: int = 0,
) -> RedTrainerPracticeEpisode:
    if enemy_hp is None:
        raise RedTrainerPracticeEpisodeError("trainer terminal lacks authenticated roster HP")
    won = bool(
        all(hp == 0 for hp in enemy_hp)
        and final.party_hp is not None
        and any(hp > 0 for hp in final.party_hp)
    )
    defeated = bool(final.party_hp is not None and not any(hp > 0 for hp in final.party_hp))
    return RedTrainerPracticeEpisode(
        capture_id=capture.manifest.capture_id,
        manifest_sha256=capture.manifest_sha256,
        policy_id=policy_id,
        decisions=tuple(decisions),
        battle_won=won,
        final_battle_state=final.battle_state,
        stop_reason=(
            "battle_won" if won else "party_defeated" if defeated else "battle_exited_without_win"
        ),
        final_observation=observation,
        final_enemy_roster_hp=tuple(enemy_hp),
        elapsed_ns=elapsed_ns,
        opening_idle_frames=opening_idle_frames,
    )


def _resource_state(raw: RawGameState) -> dict[str, object]:
    """Record actor-visible resources, excluding hidden trainer reserve identities."""
    return {
        "active_party_slot": None if raw.active_party_index is None else raw.active_party_index + 1,
        "party_hp": list(raw.party_hp) if raw.party_hp is not None else None,
        "party_max_hp": list(raw.party_max_hp) if raw.party_max_hp is not None else None,
        "party_levels": list(raw.party_levels) if raw.party_levels is not None else None,
        "party_status": list(raw.party_status) if raw.party_status is not None else None,
        "party_pp": [list(row) for row in raw.party_pp] if raw.party_pp is not None else None,
        "active_hp": raw.battler_hp,
        "active_max_hp": raw.battler_max_hp,
        "active_level": raw.active_party_level,
        "active_pp": list(raw.battler_pp) if raw.battler_pp is not None else None,
        "opponent_hp": raw.enemy_hp,
        "opponent_species_id": raw.enemy_species_id,
        "opponent_party_position": raw.enemy_party_position,
    }


def _require_plausible_hp(raw: RawGameState) -> None:
    """Reject corrupted cartridge transitions before emitting an outcome label."""
    hp, maximum = raw.party_hp, raw.party_max_hp
    if (
        hp is not None
        and maximum is not None
        and (
            len(hp) != len(maximum)
            or any(cap <= 0 or current > cap for current, cap in zip(hp, maximum, strict=True))
        )
    ):
        raise RedTrainerPracticeEpisodeError("trainer party HP exceeds its maximum")
    if (
        raw.battler_hp is not None
        and raw.battler_max_hp is not None
        and (raw.battler_max_hp <= 0 or raw.battler_hp > raw.battler_max_hp)
    ):
        raise RedTrainerPracticeEpisodeError("trainer active HP exceeds its maximum")


def _main_model_input(prepared: PreparedRedBattleScenario) -> dict[str, object]:
    batch = prepared.features
    return {
        "schema_id": batch.schema_id,
        "feature_names": list(batch.feature_names),
        "candidate_vectors": [list(row) for row in batch.candidate_vectors],
        "candidate_move_slots": [slot + 1 for slot in batch.slot_indices],
        "legal_mask": list(batch.legal_mask),
        "supported_candidate_mask": list(prepared.supported_candidate_mask),
        "current_pp": list(batch.current_pp),
    }


def _frame_count(session: TrainerPracticeSession) -> int | None:
    value = getattr(session, "frame_count", None)
    return value if type(value) is int else None  # noqa: E721


def _complete_decision(
    decisions: list[dict[str, object]],
    decision: dict[str, object],
    before: RawGameState,
    after: RawGameState,
    policy_elapsed_ns: int,
    execution_started_ns: int,
    session: TrainerPracticeSession,
    frames_before: int | None,
    event_sink: Callable[[Mapping[str, object]], None] | None,
) -> None:
    _require_plausible_hp(after)
    if (
        before.enemy_party_hp is not None
        and after.enemy_party_hp is not None
        and (len(before.enemy_party_hp) == len(after.enemy_party_hp))
    ):
        decision["opponent_faints"] = sum(
            old > 0 and new == 0
            for old, new in zip(before.enemy_party_hp, after.enemy_party_hp, strict=True)
        )
    frames_after = _frame_count(session)
    decision.update(
        {
            "policy_elapsed_ns": policy_elapsed_ns,
            "execution_elapsed_ns": perf_counter_ns() - execution_started_ns,
            "frames_executed": (
                frames_after - frames_before
                if frames_before is not None and frames_after is not None
                else None
            ),
            "state_before": _resource_state(before),
            "state_after": _resource_state(after),
        }
    )
    decisions.append(decision)
    _emit(event_sink, {"event": "decision_completed", "decision": decision})


def _emit(sink: Callable[[Mapping[str, object]], None] | None, event: Mapping[str, object]) -> None:
    if sink is not None:
        sink(event)


def _sum_int(decisions: tuple[dict[str, object], ...], key: str) -> int:
    return sum(value for step in decisions if type(value := step.get(key)) is int)


def _policy_diagnostics(policy: TrainerPracticePolicy) -> dict[str, object] | None:
    details = getattr(policy, "last_decision_diagnostics", None)
    return dict(details) if isinstance(details, dict) else None


def _episode_metrics(decisions: tuple[dict[str, object], ...]) -> dict[str, object]:
    """Outcome and cost measures that can compare policies without teacher labels."""
    hp_lost = 0
    pp_spent = 0
    party_faints = 0
    status_changes = 0
    for step in decisions:
        before = step.get("state_before")
        after = step.get("state_after")
        if not isinstance(before, dict) or not isinstance(after, dict):
            continue
        before_hp, after_hp = before.get("party_hp"), after.get("party_hp")
        if isinstance(before_hp, list) and isinstance(after_hp, list):
            for old, new in zip(before_hp, after_hp, strict=False):
                if type(old) is int and type(new) is int:
                    hp_lost += max(0, old - new)
                    party_faints += old > 0 and new == 0
        before_pp, after_pp = before.get("party_pp"), after.get("party_pp")
        if isinstance(before_pp, list) and isinstance(after_pp, list):
            for old_row, new_row in zip(before_pp, after_pp, strict=False):
                if isinstance(old_row, list) and isinstance(new_row, list):
                    for old, new in zip(old_row, new_row, strict=False):
                        if type(old) is int and type(new) is int:
                            pp_spent += max(0, old - new)
        old_status, new_status = before.get("party_status"), after.get("party_status")
        if isinstance(old_status, list) and isinstance(new_status, list):
            status_changes += sum(
                old != new for old, new in zip(old_status, new_status, strict=False)
            )
    attacks = [step for step in decisions if step.get("kind") == "attack"]
    latencies = [value for step in decisions if type(value := step.get("policy_elapsed_ns")) is int]
    return {
        "opponent_faints": sum(
            value
            if type(value := step.get("opponent_faints")) is int
            else (
                isinstance(outcome := step.get("outcome"), dict)
                and outcome.get("opponent_fainted") is True
            )
            for step in decisions
        ),
        "party_faints": party_faints,
        "party_hp_lost": hp_lost,
        "party_pp_spent": pp_spent,
        "party_status_changes": status_changes,
        "move_suppressed_or_failed": sum(
            isinstance(outcome := step.get("outcome"), dict)
            and outcome.get("move_executed") is False
            for step in attacks
        ),
        "attack_turn_utility_sum": sum(
            float(value)
            for step in attacks
            if isinstance(value := step.get("turn_utility"), (int, float))
        ),
        "policy_latency_ns_min": min(latencies) if latencies else None,
        "policy_latency_ns_max": max(latencies) if latencies else None,
        "policy_latency_ns_mean": sum(latencies) / len(latencies) if latencies else None,
        "teacher_interventions": 0,
        "invalid_action_failures": 0,
    }
