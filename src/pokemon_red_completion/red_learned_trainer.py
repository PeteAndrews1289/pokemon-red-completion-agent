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
FROZEN_K_SHA256 = "e626e3435d1aa75654593535acf0e5e52a7eb7430481217a80aff3a53c191472"
K_QUALIFICATION_SHA256 = "5fc8b4283d36e6f4ca272ff7fa5291b984e9c7a2cd85e5c16c1a34304467370f"
ADDITIVE_STORY_SHA256 = "8ef6a8512bc6c2b4e21b6a95e98ed769bc1634ea90f997961f2e6fd3f7227a12"
ADDITIVE_STORY_ADMISSION_SHA256 = "4e68390900853e1213a540d0a044cca379d8700926f3a784c65de1819e3b56bd"


def story_party_limit(model_sha256, admission_sha256):
    """Owner-admitted development scope, not ordinary funding qualification."""
    if (model_sha256, admission_sha256) in {
        (FROZEN_K_SHA256, K_QUALIFICATION_SHA256),
        (ADDITIVE_STORY_SHA256, ADDITIVE_STORY_ADMISSION_SHA256),
    }:
        return 6
    return 0


def load_story_trainer_model(payload: bytes, admission: bytes) -> TrainerPracticeThreeHeadModel:
    if not story_party_limit(hashlib.sha256(payload).hexdigest(),
                             hashlib.sha256(admission).hexdigest()):
        raise ValueError("story model requires exact checkpoint and development admission")
    return TrainerPracticeThreeHeadModel.from_dict(json.loads(payload))


def qualified_party_limit(model_sha256: str | None, qualification_sha256: str | None = None) -> int:
    """Execution coverage only; never waive the outer funding-cost verifier."""
    if model_sha256 == FROZEN_J_SHA256:
        return 3
    if model_sha256 == FROZEN_K_SHA256 and qualification_sha256 == K_QUALIFICATION_SHA256:
        return 6
    return 0


def load_frozen_trainer_model(
    payload: bytes,
    expected_sha256: str,
    *,
    qualification: bytes | None = None,
) -> TrainerPracticeThreeHeadModel:
    receipt_sha = hashlib.sha256(qualification).hexdigest() if qualification is not None else None
    if (
        not qualified_party_limit(expected_sha256, receipt_sha)
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise ValueError("player battler must match frozen J or receipt-bound qualified K")
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
    model_sha256: str = FROZEN_J_SHA256
    qualification_sha256: str | None = None

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
            reader,
            executor,
            expected_map=expected_map,
            timing=timing,
            label=label,
            decision_guard=move_decision_guard,
            resume=False,
            require_win=True,
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
        maximum_decisions: int = 80,
        story_authority: bool = False,
    ) -> RedTrainerPracticeEpisode:
        """Continue an already-owned MAIN, switch-prompt or faint boundary.

        This returns a battle outcome, not a funding receipt. A caller must
        settle and independently verify the field handoff, including a loss.
        """
        if type(story_authority) is not bool or (
            story_authority
            and not story_party_limit(self.model_sha256, self.qualification_sha256)
        ):
            raise ValueError("story authority requires exact qualified K or admitted additive")
        return self._play(
            reader,
            executor,
            expected_map=expected_map,
            timing=timing,
            label="learned trainer continuation",
            decision_guard=decision_guard,
            resume=True,
            require_win=False,
            maximum_decisions=maximum_decisions,
            authority=("frozen-additive-story-development"
                       if story_authority and self.model_sha256 == ADDITIVE_STORY_SHA256
                       else "frozen-k-story-development" if story_authority else None),
        )

    def run_wild_training(
        self, reader, executor, *, expected_map, timing, decision_guard,
        maximum_decisions=80,
    ) -> RedTrainerPracticeEpisode:
        """Explicit DEVELOPMENT knockout probe; never a capture-policy override."""
        if (self.model_sha256, self.qualification_sha256) != (
            FROZEN_K_SHA256, K_QUALIFICATION_SHA256,
        ):
            raise ValueError("wild training requires exact K and its identity receipt")
        raw = reader.read()
        if raw.battle_state != 1 or raw.map_id != expected_map:
            raise ValueError("wild training requires an active wild encounter")
        return self._play(
            reader, executor, expected_map=expected_map, timing=timing,
            label="learned wild training", decision_guard=decision_guard,
            resume=False, require_win=False, maximum_decisions=maximum_decisions,
            authority="frozen-k-wild-training-development", wild_training=True,
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
        authority: str | None = None,
        maximum_decisions: int = 80,
        allow_immune_switch_recovery: bool = False,
        wild_training: bool = False,
    ) -> RedTrainerPracticeEpisode:
        if type(wild_training) is not bool or (wild_training and (
            authority != "frozen-k-wild-training-development"
            or self.model_sha256 != FROZEN_K_SHA256
            or self.qualification_sha256 != K_QUALIFICATION_SHA256
            or resume or require_win or allow_immune_switch_recovery
        )):
            raise ValueError("wild training requires explicit bounded K development authority")
        expected_battle_state = 1 if wild_training else 2
        status_story = authority == "frozen-additive-story-development"
        if status_story and (
            self.model_sha256 != ADDITIVE_STORY_SHA256
            or self.qualification_sha256 != ADDITIVE_STORY_ADMISSION_SHA256
            or not resume or require_win
        ):
            raise ValueError("additive status execution requires admitted story continuation")
        if type(allow_immune_switch_recovery) is not bool or (
            allow_immune_switch_recovery
            and (
                self.model_sha256 != FROZEN_K_SHA256
                or self.qualification_sha256 != K_QUALIFICATION_SHA256
                or authority
                not in {
                    "frozen-k-league-development",
                    "frozen-k-league-development-continuation",
                }
            )
        ):
            raise ValueError("immune recovery requires explicit qualified K League authority")
        if type(maximum_decisions) is not int or not 1 <= maximum_decisions <= 80:
            raise ValueError("frozen battle decision remainder must be one through80")
        self.calls += 1
        directory = self.output / f"battle-{self.calls:04d}"
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        log = TrainerPracticeEventLog(
            directory / "events",
            run_identity={
                "model_sha256": self.model_sha256,
                "qualification_sha256": self.qualification_sha256,
                "source_commit": self.source_commit,
                "root_lineage_id": self.root_lineage_id,
                "parent_state_sha256": self.source_state_sha256,
                **({"allow_immune_switch_recovery": True} if allow_immune_switch_recovery else {}),
                "allow_stranded_accuracy_move": authority == "frozen-k-story-development",
                "allow_status_moves": status_story,
                "wild_training": wild_training,
                "authority": authority
                or (
                    "frozen-learned-trainer-continuation"
                    if resume
                    else "frozen-learned-ordinary-trainer"
                ),
            },
        )
        report: dict[str, object] | None = None
        try:
            raw = reader.read()
            party_limit = (story_party_limit(self.model_sha256, self.qualification_sha256)
                           if status_story else
                           qualified_party_limit(self.model_sha256, self.qualification_sha256))
            if type(raw.party_count) is not int or not 1 <= raw.party_count <= party_limit:
                raise ValueError("frozen battler party exceeds its authenticated execution scope")
            decision_guard(raw)
            if resume:
                if raw.battle_state != 2 or raw.map_id != expected_map:
                    raise ValueError("continuation requires the retained active trainer battle")
                special_boundary = raw.battler_hp == 0 or reader.trainer_switch_prompt_visible(raw)
                if not special_boundary and (
                    reader.read_battle_menu_state(raw).phase is not BattleMenuPhase.MAIN
                ):
                    raise ValueError("continuation lacks an owned policy boundary")
            else:
                special_boundary = False
                advance_battle_to_policy_boundary(
                    reader,
                    executor,
                    expected_map=expected_map,
                    expected_battle_state=expected_battle_state,
                    timing=timing,
                    label=label,
                )
            raw = reader.read()
            encoder = PokemonRedObservationEncoder.from_state_reader(
                reader,
                include_battle_stats=True,
                public_species_base_stats=self.public_species_base_stats,
            )
            observation_sha256 = (
                canonical_sha256(encoder.snapshot_from_raw(raw).to_dict())
                if special_boundary
                else prepare_red_battle_scenario(
                    encoder,
                    raw,
                    allow_no_attack=True,
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
                expected_map=expected_map,
                expected_battle_state=expected_battle_state,
                observation_schema=OBSERVATION_SCHEMA_V2,
            )
            _write(directory / "initial.state", state)
            _write(directory / "initial.state.json", manifest)
            capture = open_battle_scenario_capture(
                directory / "initial.state",
                directory / "initial.state.json",
            )
            episode = run_live_red_trainer_practice_episode(
                capture,
                session=self.session,
                policy=RedTrainerPracticeOutcomePolicy(
                    policy_id="frozen-player-trainer",
                    battle_plan_id=capture.manifest.capture_id,
                    model=self.model,
                    allow_immune_switch_recovery=allow_immune_switch_recovery,
                ),
                max_decisions=maximum_decisions,
                event_sink=log.emit,
                public_species_base_stats=self.public_species_base_stats,
                action_executor=executor,
                decision_guard=decision_guard,
                allow_stranded_accuracy_move=authority == "frozen-k-story-development",
                allow_status_moves=status_story,
                wild_training=wild_training,
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
                "model_sha256": self.model_sha256,
                "qualification_sha256": self.qualification_sha256,
                "actor_returned_win": report is not None and report.get("battle_won") is True,
                "outer_goal_verification_required": True,
            }
            _record(directory / "endpoint.json", terminal)
            if not log.closed:
                log.finish(terminal)
