"""Explicit finite critical-hit exposure, never advertised as safe survival.

The default actor and its full critical upper bounds remain unchanged. This
separate support actor may submit a bounded active attack when every supported
ordinary incoming turn is survivable but a critical hit may faint that member.
Existing outer party guards stop on the first faint; this does not revive,
sacrifice, retry a battle, infer a risk probability or grant learned authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .actions import MacroAction
from .battle_runtime import (
    BattleActionExecutor,
    BattleIntent,
    BattleRuntimeError,
    BattleRuntimeTiming,
    BattleStateReader,
    MoveDecisionGuard,
    MoveSlotPolicy,
)
from .observation import RawGameState
from .red_party import party_observation_from_raw
from .red_trainer_damage import incoming_damage_bounds
from .red_trainer_party import trainer_matchup_candidates
from .red_trainer_survival import (
    NoTrainerSurvivalAction,
    RedTrainerSurvivalController,
    TrainerSurvivalDecision,
)


@dataclass(slots=True)
class _StopOnFaintExecutor:
    reader: BattleStateReader
    delegate: BattleActionExecutor

    def execute(self, action: MacroAction) -> object:
        raw = self.reader.read()
        if (
            raw.party_hp is None or not raw.party_hp
            or len(raw.party_hp) != raw.party_count or any(hp <= 0 for hp in raw.party_hp)
            or (raw.battle_state == 2 and (raw.battler_hp is None or raw.battler_hp <= 0))
        ):
            # The runtime can acknowledge UNKNOWN dialogue before its next
            # MAIN guard. Do not allow that to select a replacement after faint.
            raise BattleRuntimeError("critical-exposure attempt reached a faint boundary")
        return self.delegate.execute(action)


@dataclass(slots=True)
class RedTrainerRiskController(RedTrainerSurvivalController):
    maximum_critical_exposures: int = 0
    previous_critical_exposures: int = 0
    critical_exposures_claimed: int = field(default=0, init=False)
    _ordinary_bound: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        RedTrainerSurvivalController.__post_init__(self)
        if (
            self.maximum_full_restores != 0
            or type(self.maximum_critical_exposures) is not int
            or type(self.previous_critical_exposures) is not int
            or not 1 <= self.maximum_critical_exposures <= 2
            or not 0 <= self.previous_critical_exposures <= 2 - self.maximum_critical_exposures
        ):
            raise ValueError("risk actor requires a nonrefreshed one/two-intent zero-item budget")

    def decide(self, raw: RawGameState) -> TrainerSurvivalDecision:
        self._ordinary_bound = None
        try:
            return RedTrainerSurvivalController.decide(self, raw)
        except NoTrainerSurvivalAction:
            if self.critical_exposures_claimed >= self.maximum_critical_exposures:
                raise
            observation = self.reader.read_trainer_damage_observation(raw)
            ordinary = incoming_damage_bounds(observation, include_critical=False)
            critical = incoming_damage_bounds(observation)
            active = raw.active_party_index
            assert active is not None and raw.party_hp is not None
            candidates = trainer_matchup_candidates(
                party_observation_from_raw(raw),
                opponent_species=raw.enemy_species_id,
                opponent_level=raw.enemy_level,
                minimum_hp_ratio=0.0,
            ) if raw.enemy_species_id is not None and raw.enemy_level is not None else ()
            if (
                any(candidate.party_slot == active + 1 for candidate in candidates)
                and ordinary[active] < raw.party_hp[active] <= critical[active]
            ):
                self._ordinary_bound = ordinary[active]
                return TrainerSurvivalDecision("risk_attack", active, critical[active])
            raise

    def _record(self, report: dict[str, object]) -> None:
        if report.get("kind") != "risk_attack":
            RedTrainerSurvivalController._record(self, report)
            return
        if (
            self._ordinary_bound is None
            or self.critical_exposures_claimed >= self.maximum_critical_exposures
        ):
            raise NoTrainerSurvivalAction("critical exposure budget or qualification changed")
        claim = self.critical_exposures_claimed + 1
        RedTrainerSurvivalController._record(self, {
            **report,
            "ordinary_incoming_bound": self._ordinary_bound,
            "critical_faint_possible": True,
            "risk_probability_estimated": False,
            "critical_exposure_claim": self.previous_critical_exposures + claim,
            "maximum_total_critical_exposures": (
                self.previous_critical_exposures + self.maximum_critical_exposures
            ),
            "claim_unit": "attack_intent_not_pp_spend",
        })
        # Durable receipt succeeds before this claim and before any input. A
        # confusion turn can consume the intent without spending move PP.
        self.critical_exposures_claimed = claim

    def run(
        self, reader: BattleStateReader, executor: BattleActionExecutor,
        move_slot_policy: MoveSlotPolicy, *, expected_map: int, intent: BattleIntent,
        timing: BattleRuntimeTiming, label: str, consume_battle_start_schedule: bool,
        move_decision_guard: MoveDecisionGuard,
        battle_exit_guard: MoveDecisionGuard | None = None,
    ) -> RawGameState:
        return RedTrainerSurvivalController.run(
            self, reader, _StopOnFaintExecutor(reader, executor), move_slot_policy,
            expected_map=expected_map, intent=intent, timing=timing, label=label,
            consume_battle_start_schedule=consume_battle_start_schedule,
            move_decision_guard=move_decision_guard,
            battle_exit_guard=battle_exit_guard,
        )
