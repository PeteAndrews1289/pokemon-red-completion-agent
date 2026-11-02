"""Explicit one-battle diagnostic scope, never an ordinary model admission."""

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from .battle_runtime import BattleRuntimeTiming, advance_battle_to_policy_boundary
from .battle_scenario_capture import (
    OBSERVATION_SCHEMA_V2,
    build_battle_scenario_capture_payload,
    open_battle_scenario_capture,
)
from .observation import EventFlag, MapId, event_flag_is_set
from .provenance import canonical_sha256
from .red_autonomous_player import _record, _write
from .red_story_battle import StoryTrainerContract
from .red_trainer_battle_lifecycle import continue_learned_trainer_battle
from .red_trainer_practice_episode import run_live_red_trainer_practice_episode
from .red_trainer_practice_fit import TrainerPracticeThreeHeadModel
from .red_trainer_practice_log import TrainerPracticeEventLog
from .red_trainer_practice_outcome_policy import RedTrainerPracticeOutcomePolicy
from .red_trajectory import PokemonRedObservationEncoder
from .scenario_lab import ScenarioPartition


@dataclass(frozen=True)
class StoryCopyScope:
    """Runner-supplied exact experiment binding; not a deployable receipt."""

    source: Path
    source_sha256: str
    campaign_directory: Path
    output: Path
    model_sha256: str
    model_content_sha256: str
    contract: StoryTrainerContract
    maximum_decisions: int = 80
    isolated_copy: bool = True
    mechanics_aware_choices: bool = False
    diagnostic_stay_when_productive: bool = False

    def validate(self):
        paths = (self.source, self.campaign_directory, self.output)
        if any(not isinstance(p, Path) or not p.is_absolute() or p.resolve() != p for p in paths):
            raise ValueError("copy scope requires absolute non-aliased paths")
        if (
            self.isolated_copy is not True
            or type(self.mechanics_aware_choices) is not bool
            or type(self.diagnostic_stay_when_productive) is not bool
            or (self.diagnostic_stay_when_productive and not self.mechanics_aware_choices)
            or not self.source.is_file()
            or not self.source.is_relative_to(self.campaign_directory)
            or self.output.is_relative_to(self.campaign_directory)
            or self.campaign_directory.is_relative_to(self.output)
            or sha256(self.source.read_bytes()).hexdigest() != self.source_sha256
            or not isinstance(self.contract, StoryTrainerContract)
            or self.contract.victory_items
            or self.contract.victory_badge_bits
            or type(self.maximum_decisions) is not int
            or not 1 <= self.maximum_decisions <= 80
        ):
            raise ValueError("invalid isolated story-copy scope")
        for value in (self.source_sha256, self.model_sha256, self.model_content_sha256):
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError("copy identity must be a SHA256")

    def load_model(self, payload):
        import json

        self.validate()
        if sha256(payload).hexdigest() != self.model_sha256:
            raise ValueError("copy model bytes differ from frozen experiment")
        model = TrainerPracticeThreeHeadModel.from_dict(json.loads(payload))
        self.require_model(model)
        return model

    def require_model(self, model):
        self.validate()
        if not isinstance(model, TrainerPracticeThreeHeadModel) or (
            canonical_sha256(model.to_dict()) != self.model_content_sha256
        ):
            raise ValueError("copy model object differs from frozen experiment")


@dataclass
class StoryCopyBattler:
    scope: StoryCopyScope
    session: object
    model: TrainerPracticeThreeHeadModel
    source_commit: str
    root_lineage_id: str
    public_species_base_stats: object
    calls: int = field(default=0, init=False)

    def require_scope(self, scope, contract=None):
        if type(scope) is not StoryCopyScope or scope is not self.scope:
            raise ValueError("copy battler requires its exact bound scope")
        scope.require_model(self.model)
        if contract is not None and contract != scope.contract:
            raise ValueError("copy battle target differs")

    def continue_battle(
        self, reader, executor, *, expected_map, timing, decision_guard, maximum_decisions=80
    ):
        self.require_scope(self.scope)
        if expected_map != self.scope.contract.map_id or (
            type(maximum_decisions) is not int
            or not 1 <= maximum_decisions <= self.scope.maximum_decisions
        ):
            raise ValueError("copy battle exceeds frozen target or decision bound")
        raw = reader.read()
        if (
            raw.battle_state != 2
            or raw.map_id != expected_map
            or (reader.read_active_trainer_identity() != self.scope.contract.trainer_identity)
        ):
            raise ValueError("copy battle identity differs")
        decision_guard(raw)
        # Exclusive directory is the durable one-battle claim, even after a crash.
        directory = self.scope.output / "battle"
        directory.mkdir(parents=False, mode=0o700, exist_ok=False)
        self.calls += 1
        log = TrainerPracticeEventLog(
            directory / "events",
            run_identity={
                "authority": "isolated-story-copy-development",
                "model_sha256": self.scope.model_sha256,
                "source_commit": self.source_commit,
                "parent_state_sha256": self.scope.source_sha256,
                "root_lineage_id": self.root_lineage_id,
                "allow_status_moves": True,
                "allow_forced_struggle": False,
                "campaign_execution": False,
                "mechanics_aware_choices": self.scope.mechanics_aware_choices,
                "diagnostic_stay_when_productive": self.scope.diagnostic_stay_when_productive,
            },
        )
        report = None
        try:
            encoder = PokemonRedObservationEncoder.from_state_reader(
                reader,
                include_battle_stats=True,
                public_species_base_stats=self.public_species_base_stats,
            )
            state = self.session.save_state_bytes()
            manifest = build_battle_scenario_capture_payload(
                capture_id="isolated-story-copy",
                root_lineage_id=self.root_lineage_id,
                partition=ScenarioPartition.DEVELOPMENT,
                state_bytes=state,
                initial_observation_sha256=canonical_sha256(
                    encoder.snapshot_from_raw(raw).to_dict()
                ),
                source_state_sha256=self.scope.source_sha256,
                source_commit=self.source_commit,
                expected_map=expected_map,
                expected_battle_state=2,
                observation_schema=OBSERVATION_SCHEMA_V2,
            )
            _write(directory / "initial.state", state)
            _write(directory / "initial.state.json", manifest)
            capture = open_battle_scenario_capture(
                directory / "initial.state", directory / "initial.state.json"
            )
            episode = run_live_red_trainer_practice_episode(
                capture,
                session=self.session,
                policy=RedTrainerPracticeOutcomePolicy(
                    "isolated-story-copy",
                    capture.manifest.capture_id,
                    self.model,
                    mechanics_aware_choices=self.scope.mechanics_aware_choices,
                    diagnostic_stay_when_productive=self.scope.diagnostic_stay_when_productive,
                ),
                max_decisions=maximum_decisions,
                event_sink=log.emit,
                public_species_base_stats=self.public_species_base_stats,
                action_executor=executor,
                decision_guard=decision_guard,
                allow_status_moves=True,
            )
            report = episode.public_dict()
            _record(directory / "outcome.json", report)
            return episode
        except BaseException as error:
            log.fail(error)
            raise
        finally:
            final = self.session.save_state_bytes()
            _write(directory / "final.state", final)
            terminal = dict(
                final_state_sha256=sha256(final).hexdigest(),
                outcome_sha256=canonical_sha256(report) if report is not None else None,
                model_sha256=self.scope.model_sha256,
                campaign_execution=False,
            )
            _record(directory / "endpoint.json", terminal)
            if not log.closed:
                log.finish(terminal)


@dataclass
class StoryCopyController:
    battler: StoryCopyBattler
    last_completion: object = field(default=None, init=False)
    moves_selected: int = field(default=0, init=False)
    switches: list = field(default_factory=list, init=False)
    maximum_switches: int = field(default=80, init=False)
    heals_claimed: int = field(default=0, init=False)
    controller_name = "isolated-story-copy-development"
    recovery_contract = "league-profit-recovery-v1"

    @property
    def binding_identity(self):
        return (id(self.battler), self.battler.scope)

    def require_objective(self, objective_id, *, rematch=False):
        self.battler.require_scope(self.battler.scope)
        if rematch is not False or objective_id != self.battler.scope.contract.objective_id:
            raise ValueError("copy objective differs or attempts a rematch")

    def require_cartridge_target(self, trainer, quote):
        scope = self.battler.scope
        self.battler.require_scope(scope)
        contract = scope.contract
        if (
            trainer.map_id,
            trainer.event_flag,
            trainer.trainer_class,
            trainer.trainer_set,
            quote.expected_victory_money,
        ) != (
            contract.map_id,
            contract.defeated_event,
            contract.trainer_identity[0],
            contract.trainer_identity[2],
            contract.victory_money,
        ):
            raise ValueError("copy target differs from live cartridge quote")

    def require_champion_target(self, script, quote):
        """Authenticate the distinct final-story script before any entry input."""
        self.require_objective("defeat_champion")
        contract = self.battler.scope.contract
        if (
            contract.battle_plan_id != "cartridge-final-story"
            or contract.map_id != int(MapId.CHAMPIONS_ROOM)
            or contract.defeated_event != int(EventFlag.BEAT_CHAMPION_RIVAL)
            or contract.trainer_identity != script.active_identity
            or contract.defeated_event != script.event_flag
            or contract.victory_money != quote.expected_victory_money
            or (quote.opponent_id, quote.trainer_set) != (script.opponent, script.trainer_set)
            or self.battler.calls != 0
            or (self.battler.scope.output / "battle").exists()
        ):
            raise ValueError("copy Champion target differs from bound cartridge script")

    def require_party_hp(self, raw):
        hp, maximum = raw.party_hp, raw.party_max_hp
        if (
            type(raw.party_count) is not int
            or not 1 <= raw.party_count <= 6
            or hp is None
            or maximum is None
            or len(hp) != raw.party_count
            or len(maximum) != raw.party_count
            or any(
                type(h) is not int or type(m) is not int or not 0 <= h <= m or m <= 0
                for h, m in zip(hp, maximum, strict=True)
            )
            or not any(hp)
        ):
            raise ValueError("copy final scene requires a coherent living party")

    def run(
        self,
        reader,
        executor,
        move_slot_policy,
        *,
        expected_map,
        intent,
        timing,
        label,
        consume_battle_start_schedule,
        move_decision_guard,
        battle_exit_guard=None,
    ):
        scope = self.battler.scope
        self.battler.require_scope(scope)
        contract = scope.contract
        if consume_battle_start_schedule or (
            expected_map,
            intent.objective_id,
            intent.battle_plan_id,
        ) != (contract.map_id, contract.objective_id, contract.battle_plan_id):
            raise ValueError("undeclared copy battle boundary")
        if (scope.output / "battle").exists():
            raise ValueError("copy battle already consumed")
        before = reader.read()
        if (
            before.battle_state != 2
            or reader.read_active_trainer_identity() != contract.trainer_identity
            or (
                before.event_flags is None
                or event_flag_is_set(before.event_flags, contract.defeated_event)
            )
        ):
            raise ValueError("copy target is stale")
        move_decision_guard(before)
        advance_battle_to_policy_boundary(
            reader,
            executor,
            expected_map=expected_map,
            expected_battle_state=2,
            timing=timing,
            label="isolated story-copy entry",
        )
        after = reader.read()
        for name in (
            "party_count",
            "party_species_ids",
            "party_hp",
            "party_moves",
            "party_pp",
            "bag_items",
            "player_money",
            "badge_bits",
            "event_flags",
        ):
            if getattr(before, name) != getattr(after, name):
                raise ValueError("copy introduction changed protected resources")
        result = continue_learned_trainer_battle(
            self.battler,
            reader,
            executor,
            trainer_identity=contract.trainer_identity,
            defeated_event=contract.defeated_event,
            ordinary_victory_money=contract.victory_money,
            timing=timing or BattleRuntimeTiming(),
            remaining_decisions=scope.maximum_decisions,
            copy_scope=scope,
        )
        self.last_completion = result
        self.moves_selected = sum(d.get("kind") == "attack" for d in result.episode.decisions)
        self.switches[:] = [
            d
            for d in result.episode.decisions
            if d.get("kind") in {"voluntary_switch", "forced_switch", "switch_prompt"}
        ]
        if result.outcome != "won" or not result.field_ready:
            raise RuntimeError(f"retained isolated story-copy outcome: {result.outcome}")
        raw = reader.read()
        if battle_exit_guard is not None:
            battle_exit_guard(raw)
        return raw
