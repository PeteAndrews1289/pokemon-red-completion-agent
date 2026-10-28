"""Bounded, teacher-free model decisions inside an authenticated Red trainer battle.

The isolated factory may set the starting state. After the capture is loaded,
only this controller's game actions can change it. Policy callbacks own every
attack, voluntary switch, replacement prompt, and forced replacement choice.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
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
    BattleActionExecutor,
    execute_bounded_battle_move_turn,
    settle_trainer_double_knockout,
    settle_wild_double_knockout,
    trainer_double_knockout_roster_pending,
)
from pokemon_red_completion.battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    BattleScenarioCapture,
)
from pokemon_red_completion.executor import (
    BorrowedLiveController,
    ControllerTiming,
    FrameSafeExecutor,
)
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

from .red_forced_struggle import (
    disabled_forced_struggle_available,
    execute_disabled_forced_struggle_turn,
    execute_forced_struggle_turn,
    execute_model_struggle_turn,
    forced_struggle_available,
    model_struggle_available,
)
from .scenario_lab import ScenarioPartition


def validate_opening_idle_frames(value: int) -> None:
    """Shared action-free timing contract for native execution and preflight."""
    if type(value) is not int or not 0 <= value <= 12:  # noqa: E721
        raise RedTrainerPracticeEpisodeError("trainer opening timing is outside its bound")


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


class LiveTrainerSession(TrainerPracticeSession, Protocol):
    def save_state_bytes(self) -> bytes: ...

    @property
    def frame_count(self) -> int: ...


def _BorrowedTrainerSession(session: LiveTrainerSession) -> BorrowedLiveController:
    return BorrowedLiveController(session, error_type=RedTrainerPracticeEpisodeError)


def run_live_red_trainer_practice_episode(
    capture: BattleScenarioCapture,
    *,
    session: LiveTrainerSession,
    policy: TrainerPracticePolicy,
    max_decisions: int = 80,
    event_sink: Callable[[Mapping[str, object]], None] | None = None,
    public_species_base_stats: Mapping[int, tuple[int, int, int, int, int]] | None = None,
    action_executor: BattleActionExecutor | None = None,
    decision_guard: Callable[[RawGameState], None] | None = None,
    allow_stranded_accuracy_move: bool = False,
    allow_status_moves: bool = False,
    include_status_context: bool = False,
    wild_training: bool = False,
    allow_forced_struggle: bool = False,
    train_wild_diagnostic: bool = False,
) -> RedTrainerPracticeEpisode:
    """Use the existing actor in-place; caller retains the game even on failure.

    Capture bytes must be the exact current live state, not a reset target.
    The caller owns frame limits, durable endpoint capture and fresh verification.
    """
    borrowed = _BorrowedTrainerSession(session)

    @contextmanager
    def session_factory() -> Iterator[TrainerPracticeSession]:
        yield borrowed

    return run_red_trainer_practice_episode(
        capture,
        session_factory=session_factory,
        policy=policy,
        max_decisions=max_decisions,
        event_sink=event_sink,
        public_species_base_stats=public_species_base_stats,
        action_executor=action_executor,
        decision_guard=decision_guard,
        allow_stranded_accuracy_move=allow_stranded_accuracy_move,
        allow_status_moves=allow_status_moves,
        include_status_context=include_status_context,
        wild_training=wild_training,
        allow_forced_struggle=allow_forced_struggle,
        train_wild_diagnostic=train_wild_diagnostic,
    )


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
                + (
                    ("forced_struggle",)
                    if any(d.get("kind") == "forced_struggle" for d in self.decisions)
                    else ()
                )
                + (
                    ("model_struggle",)
                    if any(d.get("kind") == "model_struggle" for d in self.decisions)
                    else ()
                )
            },
            "failed_move_executions": sum(
                step.get("kind") == "attack"
                and isinstance(outcome := step.get("outcome"), dict)
                and outcome.get("move_executed") is False
                for step in self.decisions
            ),
            "metrics": _episode_metrics(self.decisions),
            "player_turn_count": sum(
                step.get("kind")
                in {"attack", "voluntary_switch", "forced_struggle", "model_struggle"}
                for step in self.decisions
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
    action_executor: BattleActionExecutor | None = None,
    decision_guard: Callable[[RawGameState], None] | None = None,
    allow_stranded_accuracy_move: bool = False,
    allow_status_moves: bool = False,
    include_status_context: bool = False,
    wild_training: bool = False,
    allow_forced_struggle: bool = False,
    train_wild_diagnostic: bool = False,
) -> RedTrainerPracticeEpisode:
    """Let one model policy play a complete captured trainer battle, or fail closed."""

    if type(allow_forced_struggle) is not bool or (
        allow_forced_struggle
        and (
            not isinstance(capture, BattleScenarioCapture)
            or capture.manifest.partition
            not in (ScenarioPartition.TRAIN, ScenarioPartition.DEVELOPMENT)
            or wild_training
        )
    ):
        raise RedTrainerPracticeEpisodeError(
            "forced Struggle requires explicit trainer TRAIN/DEVELOPMENT opt-in"
        )
    if type(wild_training) is not bool:
        raise RedTrainerPracticeEpisodeError("wild training opt-in must be boolean")
    expected_battle_state = 1 if wild_training else 2
    if type(train_wild_diagnostic) is not bool or (
        train_wild_diagnostic
        and (
            not wild_training
            or not isinstance(capture, BattleScenarioCapture)
            or capture.manifest.partition is not ScenarioPartition.TRAIN
        )
    ):
        raise RedTrainerPracticeEpisodeError("TRAIN wild diagnostic needs explicit TRAIN capture")
    if wild_training and (
        not isinstance(capture, BattleScenarioCapture)
        or (
            capture.manifest.partition is not ScenarioPartition.DEVELOPMENT
            and not train_wild_diagnostic
        )
    ):
        raise RedTrainerPracticeEpisodeError("wild training requires DEVELOPMENT capture")
    if (
        not isinstance(capture, BattleScenarioCapture)
        or capture.manifest.expected_battle_state != expected_battle_state
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
    validate_opening_idle_frames(opening_idle_frames)
    if type(allow_status_moves) is not bool:
        raise RedTrainerPracticeEpisodeError("status move opt-in must be boolean")
    if type(include_status_context) is not bool:
        raise RedTrainerPracticeEpisodeError("status observation opt-in must be boolean")
    if (allow_status_moves or include_status_context) and (
        capture.manifest.observation_schema != OBSERVATION_SCHEMA_V2
    ):
        raise RedTrainerPracticeEpisodeError("status context requires rich battle observations")
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
        # Keep capture authentication on its original schema, while all policy
        # observations (including switch aftermath and terminals) use one view.
        # Observing status/stages does not authorize selecting status moves.
        # Keep original capture authentication and action masks unchanged.
        policy_encoder = (
            replace(encoder, include_status_context=True)
            if allow_status_moves or include_status_context
            else encoder
        )
        if wild_training and (initial.enemy_hp is None or initial.enemy_hp <= 0):
            raise RedTrainerPracticeEpisodeError("wild training needs a living opponent")
        _require_plausible_hp(initial)
        if (
            initial.map_id != capture.manifest.expected_map
            or initial.battle_state != expected_battle_state
        ):
            raise RedTrainerPracticeEpisodeError("trainer capture differs from its model boundary")
        initial_prompt = reader.trainer_switch_prompt_visible(initial)
        initial_forced = (
            initial.battler_hp == 0
            and initial.party_hp is not None
            and initial.active_party_index is not None
            and any(
                hp > 0 and index != initial.active_party_index
                for index, hp in enumerate(initial.party_hp)
            )
        )
        initial_sha256 = (
            canonical_sha256(encoder.snapshot_from_raw(initial).to_dict())
            if initial_prompt or initial_forced
            else prepare_red_battle_scenario(
                encoder, initial, allow_no_attack=True
            ).initial_observation_sha256
        )
        if (
            not (initial_prompt or initial_forced)
            and reader.read_battle_menu_state(initial).phase is not BattleMenuPhase.MAIN
        ) or initial_sha256 != capture.manifest.initial_observation_sha256:
            raise RedTrainerPracticeEpisodeError("trainer capture differs from its model boundary")
        actions = action_executor or FrameSafeExecutor(session, controller_timing)
        if opening_idle_frames:
            _emit(
                event_sink,
                {
                    "event": "opening_timing_started",
                    "idle_frames": opening_idle_frames,
                    "initial_observation_sha256": initial_sha256,
                },
            )
            # Opening timing historically means an absolute number of frames for
            # direct episode callers.  A supplied executor is the runner's
            # shared, metered authority, so retain that path unchanged.
            (action_executor or FrameSafeExecutor(session)).execute(
                MacroAction(MacroActionKind.WAIT, repeat=opening_idle_frames)
            )
            settled = reader.read()
            _require_plausible_hp(settled)
            if (
                settled.battle_state != expected_battle_state
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
                **({"allow_forced_struggle": True} if allow_forced_struggle else {}),
                **({"wild_training": True, "train_wild_diagnostic": True}
                   if train_wild_diagnostic else {}),
            },
        )
        for decision_index in range(1, max_decisions + 1):
            raw = reader.read()
            if (
                wild_training
                and raw.battle_state == 1
                and raw.battler_hp == 0
                and raw.enemy_hp == 0
                and raw.party_hp is not None
                and any(hp > 0 for hp in raw.party_hp)
            ):
                # A voluntary switch can also receive a simultaneous KO.
                # This is terminal dialogue, not a new forced-switch choice.
                raw = settle_wild_double_knockout(
                    reader,
                    actions,
                    expected_map=capture.manifest.expected_map,
                )
            if (
                not wild_training
                and raw.battle_state == 2
                and raw.battler_hp == 0
                and raw.enemy_hp == 0
                and raw.party_hp is not None
                and any(hp > 0 for hp in raw.party_hp)
            ):
                enemy_roster = reader.read_enemy_party_roster_hp()
                pending = trainer_double_knockout_roster_pending(raw, enemy_roster)
                if pending or (
                    enemy_roster and all(type(hp) is int and hp == 0 for hp in enemy_roster)
                ):
                    raw = settle_trainer_double_knockout(
                        reader,
                        actions,
                        expected_map=capture.manifest.expected_map,
                        **({"allow_pending_active_hp": True} if pending else {}),
                    )
            _require_plausible_hp(raw)
            if raw.map_id != capture.manifest.expected_map or raw.battle_state not in {
                0,
                expected_battle_state,
            }:
                raise RedTrainerPracticeEpisodeError("trainer episode left its authenticated map")
            if raw.battle_state == 0:
                return _receipt(
                    capture,
                    policy.policy_id,
                    decisions,
                    raw,
                    ((raw.enemy_hp,) if wild_training else reader.read_enemy_party_roster_hp()),
                    policy_encoder.snapshot_from_raw(raw).to_dict(),
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
            if raw.party_hp and not any(raw.party_hp):
                # This is an observed terminal, not another live choice. Preserve
                # the loss before a living-party guard refuses further decisions;
                # only the caller may subsequently settle native blackout input.
                return RedTrainerPracticeEpisode(
                    capture_id=capture.manifest.capture_id,
                    manifest_sha256=capture.manifest_sha256,
                    policy_id=policy.policy_id,
                    decisions=tuple(decisions),
                    battle_won=False,
                    final_battle_state=raw.battle_state,
                    stop_reason="party_defeated",
                    final_observation=policy_encoder.snapshot_from_raw(raw).to_dict(),
                    elapsed_ns=perf_counter_ns() - episode_started_ns,
                    opening_idle_frames=opening_idle_frames,
                )
            if decision_guard is not None:
                decision_guard(raw)
            # Authenticate the old capture with its original projection. Augment
            # only the new policy view; historical semantic hashes stay unchanged.
            observation = policy_encoder.snapshot_from_raw(raw).to_dict()
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
            if (
                not forced
                and not prompt
                and (reader.read_battle_menu_state(raw).phase is BattleMenuPhase.MAIN)
            ):
                prepared_main = prepare_red_battle_scenario(
                    policy_encoder,
                    raw,
                    allow_no_attack=True,
                    allow_stranded_accuracy_move=allow_stranded_accuracy_move,
                    allow_status_moves=allow_status_moves,
                )
                if (
                    not any(prepared_main.supported_candidate_mask)
                    and not options
                    and not (allow_forced_struggle and (
                        forced_struggle_available(raw) or disabled_forced_struggle_available(raw)
                    ))
                ):
                    _emit(
                        event_sink,
                        {
                            "event": "unsupported_action_boundary",
                            "decision_index": decision_index,
                            "reason": "struggle_required_no_living_reserve",
                        },
                    )
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
            if (
                allow_forced_struggle
                and not forced
                and not prompt
                and prepared_main is not None
                and (forced_struggle_available(raw) or disabled_forced_struggle_available(raw))
            ):
                _emit(
                    event_sink,
                    {
                        "event": "choice_recorded",
                        "decision_index": decision_index,
                        "selected_action": "forced_struggle",
                        "authority": "forced_mechanic",
                        "policy_elapsed_ns": 0,
                        "model_diagnostics": {},
                    },
                )
                execution_started_ns = perf_counter_ns()
                frames_before = _frame_count(session)
                struggle_executor = (
                    execute_disabled_forced_struggle_turn
                    if disabled_forced_struggle_available(raw) else execute_forced_struggle_turn
                )
                execution = struggle_executor(
                    reader,
                    actions,
                    expected_map=capture.manifest.expected_map,
                )
                after = execution.final_state
                decision = {
                    "decision_index": decision_index,
                    "observation": observation,
                    "observation_sha256": observation_sha256,
                    "kind": "forced_struggle",
                    "authority": "forced_mechanic",
                    "model_diagnostics": {},
                    "legal_party_slots": [],
                    "outcome": execution.public_dict(),
                    **execution.terminal_referee_evidence(),
                    "after_observation_sha256": canonical_sha256(
                        policy_encoder.snapshot_from_raw(after).to_dict()
                    ),
                    "party_hp_before": list(raw.party_hp or ()),
                    "party_hp_after": list(after.party_hp or ()),
                    "opponent_hp_before": raw.enemy_hp,
                    "opponent_hp_after": after.enemy_hp,
                }
                _complete_decision(
                    decisions,
                    decision,
                    raw,
                    after,
                    0,
                    execution_started_ns,
                    session,
                    frames_before,
                    event_sink,
                    policy,
                )
                player_turns += 1
                continue
            if forced or prompt:
                if decision_guard is not None:
                    decision_guard(raw)
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
                        expected_battle_state=expected_battle_state,
                        label="model trainer practice forced switch",
                        allow_trainer_prompt_outcome=expected_battle_state == 2,
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
                        policy_encoder.snapshot_from_raw(after_switch).to_dict()
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
                    policy,
                )
                continue
            if reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN:
                raise RedTrainerPracticeEpisodeError("trainer episode has no model-owned decision")
            prepared = prepared_main or prepare_red_battle_scenario(
                policy_encoder,
                raw,
                allow_no_attack=True,
                allow_stranded_accuracy_move=allow_stranded_accuracy_move,
                allow_status_moves=allow_status_moves,
            )
            _emit(
                event_sink,
                {
                    "event": "model_input_prepared",
                    "decision_index": decision_index,
                    "model_input": _main_model_input(prepared),
                },
            )
            if decision_guard is not None:
                decision_guard(raw)
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
            if action.kind is BattleActionKind.STRUGGLE:
                if (
                    not allow_forced_struggle
                    or wild_training
                    or capture.manifest.partition is not ScenarioPartition.DEVELOPMENT
                    or not model_struggle_available(raw)
                ):
                    raise RedTrainerPracticeEpisodeError(
                        "model Struggle lacks exact DEVELOPMENT zero-PP authority"
                    )
                execution_started_ns = perf_counter_ns()
                frames_before = _frame_count(session)
                execution = execute_model_struggle_turn(
                    reader, actions, expected_map=capture.manifest.expected_map
                )
                after = execution.final_state
                decision = {
                    "decision_index": decision_index,
                    "observation": observation,
                    "observation_sha256": observation_sha256,
                    "kind": "model_struggle",
                    "authority": "learner",
                    "semantic_action": action.public_dict(),
                    "model_diagnostics": diagnostics,
                    "legal_party_slots": list(options),
                    "outcome": execution.public_dict(),
                    **execution.terminal_referee_evidence(),
                    "after_observation_sha256": canonical_sha256(
                        policy_encoder.snapshot_from_raw(after).to_dict()
                    ),
                    "opponent_hp_before": raw.enemy_hp,
                    "opponent_hp_after": after.enemy_hp,
                }
                _complete_decision(
                    decisions,
                    decision,
                    raw,
                    after,
                    policy_elapsed_ns,
                    execution_started_ns,
                    session,
                    frames_before,
                    event_sink,
                    policy,
                )
                player_turns += 1
                continue
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
                    expected_battle_state=expected_battle_state,
                    label="model trainer practice voluntary switch",
                    allow_faint_outcome=True,
                    allow_trainer_prompt_outcome=True,
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
                        policy_encoder.snapshot_from_raw(after_switch).to_dict()
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
                    policy,
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
                expected_battle_state=expected_battle_state,
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
                policy,
            )
            player_turns += 1
        final = reader.read()
        if final.battle_state == 0:
            return _receipt(
                capture,
                policy.policy_id,
                decisions,
                final,
                ((final.enemy_hp,) if wild_training else reader.read_enemy_party_roster_hp()),
                policy_encoder.snapshot_from_raw(final).to_dict(),
                elapsed_ns=perf_counter_ns() - episode_started_ns,
                opening_idle_frames=opening_idle_frames,
            )
        if final.battle_state != expected_battle_state:
            raise RedTrainerPracticeEpisodeError("trainer episode left battle at its decision cap")
        return RedTrainerPracticeEpisode(
            capture_id=capture.manifest.capture_id,
            manifest_sha256=capture.manifest_sha256,
            policy_id=policy.policy_id,
            decisions=tuple(decisions),
            battle_won=False,
            final_battle_state=final.battle_state,
            stop_reason="decision_budget",
            final_observation=policy_encoder.snapshot_from_raw(final).to_dict(),
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
    if enemy_hp is None or not enemy_hp or any(hp is None for hp in enemy_hp):
        raise RedTrainerPracticeEpisodeError("trainer terminal lacks authenticated roster HP")
    won = bool(
        all(hp == 0 for hp in enemy_hp)
        and (capture.manifest.expected_battle_state != 1 or final.battle_result == 0)
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
        "battle_state": raw.battle_state,
        "active_status": raw.battler_status,
        "opponent_status": raw.enemy_status if raw.battle_state in (1, 2) else None,
        "player_disabled_move_slot": raw.player_disabled_move_slot,
        "player_disable_turns": raw.player_disable_turns,
        "player_confused": raw.player_confused,
        "enemy_confused": raw.enemy_confused if raw.battle_state in (1, 2) else None,
        "player_stat_stages": raw.player_stat_stages,
        "enemy_stat_stages": raw.enemy_stat_stages if raw.battle_state in (1, 2) else None,
        "enemy_using_trapping_move": raw.enemy_using_trapping_move,
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
        "unsupported_candidate_reasons": list(prepared.unsupported_candidate_reasons),
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
    policy: TrainerPracticePolicy,
) -> None:
    _require_plausible_hp(after)
    if (
        before.enemy_party_hp is not None
        and after.enemy_party_hp is not None
        and (len(before.enemy_party_hp) == len(after.enemy_party_hp))
    ):
        # Referee evidence is retained only with the completed decision. It is
        # never placed in the actor observation or passed to the policy.
        decision["referee_opponent_roster_hp_before"] = list(before.enemy_party_hp)
        decision["referee_opponent_roster_hp_after"] = list(after.enemy_party_hp)
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
            "failure_context": battle_failure_diagnostics(decision, before, after),
        }
    )
    decisions.append(decision)
    _emit(event_sink, {"event": "decision_completed", "decision": decision})
    transition = getattr(policy, "observe_opponent_transition", None)
    if (
        callable(transition)
        and type(before.enemy_party_position) is int
        and type(after.enemy_party_position) is int
    ):
        transition(before.enemy_party_position, after.enemy_party_position)


def battle_failure_diagnostics(decision, before, after):
    """Observed status/Disable and endpoint damage, never inferred RNG causes."""
    outcome = decision.get("outcome") or {}
    same_battle = before.battle_state in (1, 2) and after.battle_state == before.battle_state
    player_comparable = (
        same_battle
        and type(before.active_party_index) is int
        and before.active_party_index == after.active_party_index
    )
    enemy_comparable = (
        same_battle
        and before.enemy_species_id == after.enemy_species_id
        and before.enemy_party_position == after.enemy_party_position
        and (before.battle_state == 1 or type(before.enemy_party_position) is int)
    )

    def decrease(a, b, comparable):
        return max(0, a - b) if comparable and type(a) is int and type(b) is int else None

    return dict(
        schema="pokemon.red.battle-failure-context.v1",
        diagnostic_only=True,
        move_executed=outcome.get("move_executed"),
        active_status_before=before.battler_status,
        active_status_after=after.battler_status,
        disabled_move_slot_before=before.player_disabled_move_slot,
        disable_turns_before=before.player_disable_turns,
        confused_before=before.player_confused,
        opponent_trapping_before=before.enemy_using_trapping_move,
        observed_player_hp_decrease=decrease(
            before.battler_hp, after.battler_hp, player_comparable
        ),
        observed_enemy_hp_decrease=decrease(before.enemy_hp, after.enemy_hp, enemy_comparable),
        endpoint_damage_is_not_causal_move_damage=True,
        critical_hit_observed=None,
        miss_observed=None,
        immunity_message_observed=None,
        unexecuted_move_reason=None,
        unobserved_causes_not_inferred=True,
        training_admission=False,
    )


def _emit(sink: Callable[[Mapping[str, object]], None] | None, event: Mapping[str, object]) -> None:
    if sink is not None:
        sink(event)


def _sum_int(decisions: tuple[dict[str, object], ...], key: str) -> int:
    return sum(value for step in decisions if type(value := step.get(key)) is int)


def _policy_diagnostics(policy: TrainerPracticePolicy) -> dict[str, object] | None:
    details = getattr(policy, "last_decision_diagnostics", None)
    return dict(details) if isinstance(details, dict) else None


def _episode_metrics(decisions: tuple[dict[str, object], ...]) -> dict[str, object]:
    """Outcome and cost measures that can compare policies without teacher labels.

    party_pp_spent is the historical positive endpoint depletion, which can hide
    spending when a native post-battle script restores PP. selected_move_pp_spends
    counts exact-spend proofs from the bounded executor, independently of healing.
    Keep both measures explicit; do not rewrite historical outcome records.
    """
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
        "selected_move_pp_spends": sum(
            isinstance(outcome := step.get("outcome"), dict)
            and outcome.get("move_executed") is True
            for step in attacks
        ),
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
