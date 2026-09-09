"""Bounded deterministic party control for an already identified trainer.

This composes existing observed move and switch execution. It neither chooses
the story goal nor promotes the shadow battle learner. No recovery items,
boosts, sacrifices, hidden RNG waits or roster-specific switch recipe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .battle_actions import BattleAction, BattleControlRequest
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
from .red_goal_context import RedGoalContextEmulator
from .red_party import party_observation_from_raw
from .red_trainer_party import trainer_entry_candidates, trainer_matchup_candidates


class RedTrainerControlError(BattleRuntimeError):
    """The party-aware controller cannot safely continue its declared battle."""


class _SwitchRequest(BattleControlRequest):
    pass


@dataclass(slots=True)
class RedTrainerPartyController:
    reader: PokemonRedStateReader
    emulator: RedGoalContextEmulator
    maximum_switches: int = 6
    switches: list[int] = field(default_factory=list, init=False)
    moves_selected: int = field(default=0, init=False)
    _move_since_switch: bool = field(default=True, init=False)
    _claimed: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if type(self.maximum_switches) is not int or not 0 <= self.maximum_switches <= 6:
            raise ValueError("trainer control supports at most six switches")

    def choose(self, raw: RawGameState, move_policy: MoveSlotPolicy) -> int:
        """Request a reserve only for a material matchup gain or an unfit lead."""
        if raw.battle_state != 2 or raw.active_party_index is None:
            raise RedTrainerControlError("party control requires an observed trainer turn")
        party = party_observation_from_raw(raw)
        if not 0 <= raw.active_party_index < party.size:
            raise RedTrainerControlError("active party slot is outside the observed party")
        if party.fainted_count or (raw.battler_hp or 0) <= 0:
            raise RedTrainerControlError("party control never recovers by sacrificing a member")
        if raw.enemy_species_id is None or raw.enemy_level is None:
            raise RedTrainerControlError("opponent mechanics are unavailable")
        candidates = trainer_matchup_candidates(
            party, opponent_species=raw.enemy_species_id, opponent_level=raw.enemy_level,
        )
        active_slot = raw.active_party_index + 1
        active = next((c for c in candidates if c.party_slot == active_slot), None)
        if not candidates:
            raise RedTrainerControlError("no healthy offensive matchup remains")
        # A preparation match is not an entry qualification. Only screen when
        # a switch could be useful. A preferred switch with unknown incoming
        # mechanics must refuse, never interpret missing data as safe entry.
        reserves = tuple(c for c in candidates if c.party_slot != active_slot and (
            active is None or c.score - active.score >= 0.10
        ))
        if reserves and self._move_since_switch and len(self.switches) < self.maximum_switches:
            incoming = self.reader.read_trainer_entry_moves(raw)
            if incoming is None:
                raise RedTrainerControlError("incoming trainer moves are unavailable")
            reserves = trainer_entry_candidates(party, reserves, incoming_moves=incoming)
            if not reserves and active is None:
                raise RedTrainerControlError("no reserve passes the incoming move entry screen")
        best = reserves[0] if reserves else active
        if best is None:
            raise RedTrainerControlError("unfit active member cannot safely take another turn")
        should_switch = best.party_slot != active_slot and (
            active is None or best.score - active.score >= 0.10
        )
        if should_switch and self._move_since_switch:
            if len(self.switches) >= self.maximum_switches:
                if active is None:
                    raise RedTrainerControlError("trainer switch budget exhausted")
            else:
                raise _SwitchRequest(BattleAction.switch(best.party_slot))
        if active is None:
            raise RedTrainerControlError("unfit active member cannot safely take another turn")
        selected = move_policy(raw)
        self.moves_selected += 1
        self._move_since_switch = True
        return selected

    def run(
        self, reader: BattleStateReader, executor: BattleActionExecutor,
        move_slot_policy: MoveSlotPolicy, *, expected_map: int, intent: BattleIntent,
        timing: BattleRuntimeTiming, label: str, consume_battle_start_schedule: bool,
        move_decision_guard: MoveDecisionGuard,
        battle_exit_guard: MoveDecisionGuard | None = None,
    ) -> RawGameState:
        if self._claimed:
            raise RedTrainerControlError("trainer controller already consumed")
        self._claimed = True
        if reader is not self.reader or consume_battle_start_schedule:
            raise RedTrainerControlError("trainer controller binding differs")
        if battle_policy_override_active():
            raise RedTrainerControlError("learned battle controller authority is not enabled")
        before = reader.read()

        def guard(raw: RawGameState) -> None:
            move_decision_guard(raw)
            if raw.bag_items != before.bag_items:
                raise RedTrainerControlError("trainer control cannot spend bag resources")

        def policy(raw: RawGameState) -> int:
            return self.choose(raw, move_slot_policy)

        while True:
            try:
                return run_adaptive_trainer_battle(
                    reader, executor, policy, expected_map=expected_map, intent=intent,
                    timing=timing, label=label, consume_battle_start_schedule=False,
                    move_decision_guard=guard,
                    battle_exit_guard=battle_exit_guard,
                )
            except BattleRuntimeError as error:
                request = error.__cause__
                if not isinstance(request, _SwitchRequest):
                    raise
                slot = request.action.party_slot
                if slot is None or len(self.switches) >= self.maximum_switches:
                    raise RedTrainerControlError("invalid or exhausted switch request") from error
                guard(reader.read())
                # Re-evaluate the exact target immediately before controller input.
                try:
                    self.choose(reader.read(), move_slot_policy)
                except _SwitchRequest as fresh:
                    if fresh.action != request.action:
                        raise RedTrainerControlError("switch target changed") from error
                else:
                    raise RedTrainerControlError("switch request is no longer current") from error
                self.switches.append(slot)
                self._move_since_switch = False
                switch_active_battler(
                    executor, self.reader, self.emulator, slot - 1,
                    label="observed trainer matchup switch", wait_frames=180,
                )
                guard(reader.read())
