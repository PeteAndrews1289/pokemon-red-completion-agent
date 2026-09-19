"""Opt-in frozen battler at the player's ordinary trainer-funding seam.

This is not a wild-capture or Elite Four override. The outer funding verifier
continues to own identity, party preservation, payout and field settlement.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .battle_runtime import (
    BattleActionExecutor,
    BattleIntent,
    BattleRuntimeTiming,
    advance_battle_to_policy_boundary,
)
from .battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from .observation import BattleMenuPhase, PokemonRedStateReader, RawGameState
from .provenance import canonical_sha256
from .red_autonomous_player import _record, _write
from .red_battle_scenario import prepare_red_battle_scenario
from .red_trainer_practice_episode import (
    LiveTrainerSession,
    RedTrainerPracticeEpisode,
    run_live_red_trainer_practice_episode,
)
from .red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from .red_trainer_practice_log import TrainerPracticeEventLog
from .red_trainer_practice_outcome_policy import RedTrainerPracticeOutcomePolicy
from .red_trajectory import PokemonRedObservationEncoder
from .scenario_lab import ScenarioPartition

FROZEN_J_SHA256 = "260b227a2fb3ba46a80be9c42e1f7e17977068e890f135407f8faafe2336fb09"


def load_frozen_trainer_model(
    payload: bytes, expected_sha256: str,
) -> TrainerPracticeThreeHeadModel:
    if expected_sha256 != FROZEN_J_SHA256 or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("player battler must match the qualified frozen J artifact")
    return TrainerPracticeThreeHeadModel.from_dict(json.loads(payload))


@dataclass
class FrozenTrainerBattler:
    session: LiveTrainerSession
    model: TrainerPracticeThreeHeadModel
    output: Path
    source_commit: str
    root_lineage_id: str
    source_state_sha256: str
    public_species_base_stats: Mapping[int, tuple[int, int, int, int, int]]
    calls: int = 0

    def run(
        self,
        reader: PokemonRedStateReader,
        executor: BattleActionExecutor,
        move_slot_policy: Callable[[RawGameState], int],
        *,
        expected_map: int,
        intent: BattleIntent,
        timing: BattleRuntimeTiming,
        label: str,
        consume_battle_start_schedule: bool,
        move_decision_guard: Callable[[RawGameState], None],
    ) -> RawGameState:
        # The old policy is deliberately never queried, including on failure.
        if consume_battle_start_schedule or intent.battle_plan_id != "ordinary-trainer-funding":
            raise ValueError("frozen battler is enabled only for ordinary trainer funding")
        self._play(
            reader, executor, expected_map=expected_map, timing=timing, label=label,
            decision_guard=move_decision_guard, resume=False, require_win=True,
        )
        return reader.read()

    def continue_battle(
        self,
        reader: PokemonRedStateReader,
        executor: BattleActionExecutor,
        *,
        expected_map: int,
        timing: BattleRuntimeTiming,
        decision_guard: Callable[[RawGameState], None],
    ) -> RedTrainerPracticeEpisode:
        """Continue an already-owned MAIN, switch-prompt or faint boundary.

        This returns a battle outcome, not a funding receipt. A caller must
        settle and independently verify the field handoff, including a loss.
        """
        return self._play(
            reader, executor, expected_map=expected_map, timing=timing,
            label="learned trainer continuation", decision_guard=decision_guard,
            resume=True, require_win=False,
        )

    def _play(
        self,
        reader: PokemonRedStateReader,
        executor: BattleActionExecutor,
        *,
        expected_map: int,
        timing: BattleRuntimeTiming,
        label: str,
        decision_guard: Callable[[RawGameState], None],
        resume: bool,
        require_win: bool,
    ) -> RedTrainerPracticeEpisode:
        self.calls += 1
        directory = self.output / f"battle-{self.calls:04d}"
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        log = TrainerPracticeEventLog(directory / "events", run_identity={
            "model_sha256": FROZEN_J_SHA256,
            "source_commit": self.source_commit,
            "root_lineage_id": self.root_lineage_id,
            "parent_state_sha256": self.source_state_sha256,
            "authority": "frozen-J-trainer-continuation" if resume else "frozen-J-ordinary-trainer",
        })
        report: dict[str, object] | None = None
        try:
            raw = reader.read()
            if raw.party_count is None or not 1 <= raw.party_count <= 3:
                raise ValueError("frozen battler v1 supports one to three own party members")
            decision_guard(raw)
            if resume:
                if raw.battle_state != 2 or raw.map_id != expected_map:
                    raise ValueError("continuation requires the retained active trainer battle")
                special_boundary = (
                    raw.battler_hp == 0 or reader.trainer_switch_prompt_visible(raw)
                )
                if not special_boundary and (
                    reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
                ):
                    raise ValueError("continuation lacks an owned policy boundary")
            else:
                special_boundary = False
                advance_battle_to_policy_boundary(
                    reader, executor, expected_map=expected_map, expected_battle_state=2,
                    timing=timing, label=label,
                )
            raw = reader.read()
            encoder = PokemonRedObservationEncoder.from_state_reader(
                reader, include_battle_stats=True,
                public_species_base_stats=self.public_species_base_stats,
            )
            observation_sha256 = (
                canonical_sha256(encoder.snapshot_from_raw(raw).to_dict())
                if special_boundary else prepare_red_battle_scenario(
                    encoder, raw, allow_no_attack=True,
                ).initial_observation_sha256
            )
            state = self.session.save_state_bytes()
            manifest = build_battle_scenario_capture_payload(
                capture_id=f"player-trainer-{self.calls:04d}",
                root_lineage_id=self.root_lineage_id,
                partition=ScenarioPartition.DEVELOPMENT,
                state_bytes=state,
                initial_observation_sha256=observation_sha256,
                source_state_sha256=self.source_state_sha256,
                source_commit=self.source_commit,
                expected_map=expected_map, expected_battle_state=2,
                observation_schema=OBSERVATION_SCHEMA_V2,
            )
            _write(directory / "initial.state", state)
            _write(directory / "initial.state.json", manifest)
            capture = open_battle_scenario_capture(
                directory / "initial.state", directory / "initial.state.json",
            )
            episode = run_live_red_trainer_practice_episode(
                capture, session=self.session,
                policy=RedTrainerPracticeOutcomePolicy(
                    policy_id="frozen-J-player-trainer", battle_plan_id=capture.manifest.capture_id,
                    model=self.model,
                ),
                max_decisions=80, event_sink=log.emit,
                public_species_base_stats=self.public_species_base_stats,
                action_executor=executor, decision_guard=decision_guard,
            )
            report = episode.public_dict()
            _record(directory / "outcome.json", report)
            if require_win and not episode.battle_won:
                raise RuntimeError(f"learned trainer stopped: {episode.stop_reason}")
            return episode
        except BaseException as error:
            log.fail(error)
            raise
        finally:
            final = self.session.save_state_bytes()
            _write(directory / "final.state", final)
            terminal = {
                "final_state_sha256": hashlib.sha256(final).hexdigest(),
                "outcome_sha256": canonical_sha256(report) if report is not None else None,
                "model_sha256": FROZEN_J_SHA256,
                "actor_returned_win": report is not None and report.get("battle_won") is True,
                "outer_goal_verification_required": True,
            }
            _record(directory / "endpoint.json", terminal)
            if not log.closed:
                log.finish(terminal)
