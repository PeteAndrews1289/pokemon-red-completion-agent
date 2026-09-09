"""Explicitly budgeted deterministic recovery, not promoted model authority.

Ordinary controllers keep their historical thresholds. This separate recovery
actor substitutes observed incoming-turn bounds for a flat half-HP gate and may
make an emergency switch without forcing the threatened member to attack first.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from .battle_recovery import switch_active_battler
from .battle_runtime import (
    BattleActionExecutor,
    BattleIntent,
    BattleRuntimeError,
    BattleRuntimeTiming,
    BattleStateReader,
    MoveDecisionGuard,
    MoveSlotPolicy,
    battle_policy_override_active,
    run_adaptive_trainer_battle,
)
from .observation import PokemonRedStateReader, RawGameState
from .red_battle_catalog import RED_BATTLE_CATALOG, pokemon_red_move_ref
from .red_goal_context import RedGoalContextEmulator
from .red_party import party_observation_from_raw
from .red_trainer_damage import incoming_damage_bounds
from .red_trainer_healing import bag_after_full_restores, use_active_full_restore
from .red_trainer_party import trainer_matchup_candidates


@dataclass(frozen=True, slots=True)
class TrainerSurvivalDecision:
    kind: str
    party_index: int
    incoming_bound: int


class _RecoveryRequest(Exception):
    def __init__(self, decision: TrainerSurvivalDecision):
        self.decision = decision
        super().__init__(decision.kind)


class NoTrainerSurvivalAction(BattleRuntimeError):
    """Supported mechanics, but no action meets the strict survival contract."""


@dataclass(slots=True)
class RedTrainerSurvivalController:
    reader: PokemonRedStateReader
    emulator: RedGoalContextEmulator
    previous_switches: tuple[int, ...]
    maximum_full_restores: int = 2
    decision_sink: Callable[[dict[str, object]], None] | None = None
    switches: list[int] = field(default_factory=list, init=False)
    heals_claimed: int = field(default=0, init=False)
    reports: list[dict[str, object]] = field(default_factory=list, init=False)
    _claimed: bool = field(default=False, init=False)

    def _record(self, report: dict[str, object]) -> None:
        if self.decision_sink is not None:
            self.decision_sink(report)
        self.reports.append(report)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.previous_switches, tuple)
            or len(self.previous_switches) > 6
            or any(type(slot) is not int or not 1 <= slot <= 6 for slot in self.previous_switches)
            or type(self.maximum_full_restores) is not int
            or not 0 <= self.maximum_full_restores <= 2
        ):
            raise ValueError("trainer survival resource or historical switch budget differs")

    def decide(self, raw: RawGameState) -> TrainerSurvivalDecision:
        if (
            raw.battle_state != 2
            or raw.party_hp is None
            or raw.party_max_hp is None
            or raw.party_status is None
            or raw.active_party_index is None
            or not all(hp > 0 for hp in raw.party_hp)
        ):
            raise BattleRuntimeError("trainer survival requires a preserved living party")
        bounds = incoming_damage_bounds(self.reader.read_trainer_damage_observation(raw))
        party = party_observation_from_raw(raw)
        active = raw.active_party_index
        if not 0 <= active < party.size:
            raise BattleRuntimeError("trainer survival active index differs")
        candidates = (
            trainer_matchup_candidates(
                party,
                opponent_species=raw.enemy_species_id,
                opponent_level=raw.enemy_level,
                minimum_hp_ratio=0.0,
            )
            if raw.enemy_species_id is not None and raw.enemy_level is not None
            else ()
        )
        active_candidate = any(c.party_slot == active + 1 for c in candidates)
        if active_candidate and raw.party_hp[active] > bounds[active]:
            return TrainerSurvivalDecision("attack", active, bounds[active])
        if (
            raw.party_max_hp[active] > bounds[active]
            and (raw.party_hp[active] < raw.party_max_hp[active] or raw.party_status[active])
            and self.heals_claimed < self.maximum_full_restores
            and dict(raw.bag_items or ()).get(16, 0) > 0
        ):
            return TrainerSurvivalDecision("heal", active, bounds[active])
        if len(self.previous_switches) + len(self.switches) < 6:
            for candidate in candidates:
                slot = candidate.party_slot - 1
                if slot != active and raw.party_hp[slot] > bounds[slot]:
                    return TrainerSurvivalDecision("switch", slot, bounds[slot])
        raise NoTrainerSurvivalAction(
            "no supported survival action within the remaining recovery budget"
        )

    def run(
        self,
        reader: BattleStateReader,
        executor: BattleActionExecutor,
        move_slot_policy: MoveSlotPolicy,
        *,
        expected_map: int,
        intent: BattleIntent,
        timing: BattleRuntimeTiming,
        label: str,
        consume_battle_start_schedule: bool,
        move_decision_guard: MoveDecisionGuard,
    ) -> RawGameState:
        if self._claimed:
            raise BattleRuntimeError("trainer survival controller already consumed")
        self._claimed = True
        if (
            reader is not self.reader
            or consume_battle_start_schedule
            or battle_policy_override_active()
        ):
            raise BattleRuntimeError("trainer survival binding or fixed authority differs")
        initial = reader.read()
        if initial.bag_items is None:
            raise BattleRuntimeError("trainer survival bag unavailable")
        initial_bag = initial.bag_items

        def guard(raw: RawGameState) -> None:
            move_decision_guard(raw)
            if raw.bag_items != bag_after_full_restores(initial_bag, self.heals_claimed):
                raise BattleRuntimeError("trainer survival bag differs from claimed items")

        def choose(raw: RawGameState) -> int:
            decision = self.decide(raw)
            if decision.kind not in {"attack", "risk_attack"}:
                raise _RecoveryRequest(decision)
            if raw.battler_moves is None or raw.battler_pp is None:
                raise BattleRuntimeError("trainer survival moves unavailable")
            pp = tuple(
                value
                if move
                and RED_BATTLE_CATALOG.recovery_attack_supported(
                    pokemon_red_move_ref(move),
                )
                else 0
                for move, value in zip(raw.battler_moves, raw.battler_pp, strict=True)
            )
            if not any(pp):
                raise BattleRuntimeError("no single-turn nonrecoil recovery attack")
            selected = move_slot_policy(replace(raw, active_party_pp=pp))
            if type(selected) is not int or not 1 <= selected <= len(pp) or not pp[selected - 1]:
                raise BattleRuntimeError("recovery move policy selected an unsupported attack")
            self._record(
                {
                    "kind": decision.kind,
                    "party_index": decision.party_index,
                    "incoming_bound": decision.incoming_bound,
                    "hp_before": raw.battler_hp,
                    "move_slot": selected,
                }
            )
            return selected

        while True:
            try:
                return run_adaptive_trainer_battle(
                    reader,
                    executor,
                    choose,
                    expected_map=expected_map,
                    intent=intent,
                    timing=timing,
                    label=label,
                    consume_battle_start_schedule=False,
                    move_decision_guard=guard,
                )
            except BattleRuntimeError as error:
                request = error.__cause__
                if not isinstance(request, _RecoveryRequest):
                    raise
                before = reader.read()
                guard(before)
                decision = self.decide(before)
                if decision != request.decision:
                    raise BattleRuntimeError("recovery decision changed before input") from error
                self._record(
                    {
                        "kind": decision.kind,
                        "party_index": decision.party_index,
                        "incoming_bound": decision.incoming_bound,
                    }
                )
                if decision.kind == "heal":
                    self.heals_claimed += (
                        1  # Claim before the first input; never refund on failure.
                    )
                    use_active_full_restore(
                        executor,
                        self.reader,
                        self.emulator,
                        expected=before,
                        incoming_bound=decision.incoming_bound,
                    )
                else:
                    self.switches.append(decision.party_index + 1)
                    switch_active_battler(
                        executor,
                        self.reader,
                        self.emulator,
                        decision.party_index,
                        label="bounded survival recovery switch",
                    )
                    after = reader.read()
                    if (
                        after.party_hp is None
                        or before.party_hp is None
                        or after.party_pp != before.party_pp
                        or after.party_hp[decision.party_index]
                        < before.party_hp[decision.party_index] - decision.incoming_bound
                    ):
                        raise BattleRuntimeError(
                            "switch exceeded its qualified incoming damage",
                        ) from error
                guard(reader.read())
